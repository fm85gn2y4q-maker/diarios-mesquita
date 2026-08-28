"""Atualiza o acervo e publica, sem ninguém olhando. Roda pelo Agendador.

Encadeia tudo: coleta → extração → OCR → segmentação → release no GitHub →
Dockerfile → push. O Render reconstrói ao receber o commit.

**Não publica quando não há edição nova.** É a primeira guarda, e existe porque
o portal não publica todo dia: sem ela, seriam 52 releases por ano, quase todas
idênticas à anterior.

**Confere o que publicou antes de apontar para lá.** Entre criar a release e
trocar o `ARG` do Dockerfile, o arquivo é baixado da URL pública e o sha256 é
recalculado. Divergindo, o Dockerfile não é tocado: melhor o servidor continuar
servindo o acervo antigo, que funciona, do que apontar para um pacote que a
construção vai recusar — e a falha só apareceria no log do Render, horas depois.

Tudo o que faz vai para `publicacao.log`, com data. Sem isso, uma tarefa
agendada que falha em silêncio é pior do que tarefa nenhuma: cria a impressão
de que o acervo está atualizado.

    python publicar_automatico.py            # o que a tarefa de sábado roda
    python publicar_automatico.py --ensaio   # faz tudo menos publicar
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
BANCO = BASE / "acervo.db"
SERVIDOR = Path.home() / "projetos" / "diarios-mesquita"
REGISTRO = BASE / "publicacao.log"
REPOSITORIO = "fm85gn2y4q-maker/diarios-mesquita"
BLOCO = 4 * 1024 * 1024

# O sinal de vida vai para uma branch só dele, NÃO para o master. O Render
# observa o master e reconstrói a cada push: mandar o sinal para lá faria o
# serviço rebaixar 86 MB toda semana, sem nada ter mudado no acervo.
RAMO_SINAL = "sinal-de-vida"
ARQUIVO_SINAL = "sinal_de_vida.json"
ENSAIO = False   # em ensaio não se grava sinal, para não falsear o monitor

PASSOS = [
    ("coleta", [sys.executable, "baixar_diarios.py", "--fonte", "municipio"]),
    ("extração", [sys.executable, "extrair_texto.py"]),
    ("OCR", [str(BASE / ".venv-ocr" / "Scripts" / "python.exe"), "ocr_paginas.py"]),
    ("segmentação", [sys.executable, "segmentar_atos.py"]),
]


def gravar_sinal(resultado: str, detalhe: str = "", numeros: dict | None = None) -> None:
    """Deixa no GitHub a prova de que a tarefa rodou — e como terminou.

    Existe porque tarefa agendada que falha em silêncio é pior do que tarefa
    nenhuma: passa a impressão de acervo em dia. Uma rotina na nuvem lê este
    arquivo e avisa se ele envelhecer, o que denuncia a tarefa parada.

    Escreve pela API do GitHub, não por `git push`, para não tocar na árvore de
    trabalho — o mesmo script está mexendo no Dockerfile do master ao lado.
    """
    if ENSAIO:
        anotar(f"ensaio: sinal NÃO gravado (seria '{resultado}')")
        return
    conteudo = {
        "quando": datetime.now().astimezone().isoformat(timespec="seconds"),
        "resultado": resultado,
        "detalhe": detalhe,
        **(numeros or {}),
    }
    carga = base64.b64encode(
        json.dumps(conteudo, ensure_ascii=False, indent=1).encode()).decode()

    # O `ref` vai na QUERY STRING, não como `-f`: `-f` manda o campo no corpo, e
    # o GitHub ignora corpo em GET. Com o ref perdido, a consulta cai no ramo
    # padrão (master), onde este arquivo não existe, e volta 404 — o sha sai
    # vazio e toda gravação a partir da segunda morre com 422 "sha wasn't
    # supplied". O sinal congelava na primeira execução.
    codigo, saida = rodar(["gh", "api",
                           f"repos/{REPOSITORIO}/contents/{ARQUIVO_SINAL}"
                           f"?ref={RAMO_SINAL}"], SERVIDOR)
    sha = ""
    if codigo == 0:
        try:
            sha = json.loads(saida)["sha"]
        except Exception:  # noqa: BLE001
            sha = ""
    if not sha:
        # Normal só na primeiríssima gravação, quando o arquivo ainda não existe.
        # Depois disso é sintoma: a gravação vai falhar com 422 e o sinal congela.
        anotar(f"aviso: sha do sinal anterior veio vazio (código {codigo}) — "
               "se o arquivo já existe no ramo, a gravação vai falhar com 422")

    comando = ["gh", "api", "-X", "PUT",
               f"repos/{REPOSITORIO}/contents/{ARQUIVO_SINAL}",
               "-f", f"message=sinal de vida: {resultado}",
               "-f", f"content={carga}",
               "-f", f"branch={RAMO_SINAL}"]
    if sha:
        comando += ["-f", f"sha={sha}"]
    codigo, saida = rodar(comando, SERVIDOR)
    if codigo != 0:
        anotar(f"aviso: não consegui gravar o sinal de vida ({codigo})")
        anotar("  " + " / ".join(saida.strip().splitlines()[-2:]))
    else:
        anotar(f"sinal de vida gravado: {resultado}")


def anotar(mensagem: str) -> None:
    linha = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {mensagem}"
    print(linha)
    with REGISTRO.open("a", encoding="utf-8") as fh:
        fh.write(linha + "\n")


def estado() -> dict:
    con = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    try:
        edicoes, ultima = con.execute("SELECT COUNT(*), MAX(data) FROM edicao").fetchone()
        paginas = con.execute("SELECT COUNT(*) FROM pagina").fetchone()[0]
        atos = con.execute("SELECT COUNT(*) FROM ato").fetchone()[0]
        ocr = con.execute("SELECT COUNT(*) FROM pagina WHERE origem LIKE 'ocr%'").fetchone()[0]
    finally:
        con.close()
    return {"edicoes": edicoes, "ultima": ultima, "paginas": paginas,
            "atos": atos, "ocr": ocr}


def resumo_sha(caminho: Path) -> str:
    d = hashlib.sha256()
    with caminho.open("rb") as fh:
        for bloco in iter(lambda: fh.read(BLOCO), b""):
            d.update(bloco)
    return d.hexdigest()


def rodar(comando: list[str], cwd: Path) -> tuple[int, str]:
    r = subprocess.run(comando, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Atualiza e publica o acervo")
    ap.add_argument("--ensaio", action="store_true",
                    help="faz tudo menos criar a release e dar push")
    ap.add_argument("--forcar", action="store_true",
                    help="publica mesmo sem edição nova (para testar o caminho)")
    args = ap.parse_args()
    global ENSAIO
    ENSAIO = args.ensaio

    anotar("=" * 58)
    anotar("iniciando atualização automática")

    antes = estado()
    anotar(f"antes: {antes['edicoes']} edições até {antes['ultima']}, "
           f"{antes['atos']} atos")

    # Guarda de branch. Sem ela, este script já falhou em silêncio por 18 dias:
    # o repositório estava numa branch de trabalho, `git commit` gravou nela,
    # e `git push origin master` empurrou o master LOCAL — intocado. O Git
    # respondeu "Everything up-to-date" e saiu com codigo 0, que o script leu
    # como sucesso. Duas releases foram publicadas e o site continuou servindo
    # o acervo de 03/08, sem um único erro no log.
    codigo, ramo = rodar(["git", "rev-parse", "--abbrev-ref", "HEAD"], SERVIDOR)
    ramo = ramo.strip()
    if codigo != 0 or ramo != "master":
        aviso = (f"o repositório do servidor está na branch '{ramo}', não em "
                 "master. Não publico daqui: o commit iria para a branch errada "
                 "e o push do master não levaria nada.")
        anotar("ABORTADO: " + aviso)
        gravar_sinal("abortado: repositório fora do master", aviso, antes)
        return 1
    codigo, sujo = rodar(["git", "status", "--porcelain"], SERVIDOR)
    if sujo.strip():
        aviso = ("há alterações não commitadas no repositório do servidor: "
                 + " / ".join(sujo.strip().splitlines()[:3]))
        anotar("ABORTADO: " + aviso)
        gravar_sinal("abortado: árvore de trabalho suja", aviso, antes)
        return 1

    for nome, comando in PASSOS:
        inicio = time.time()
        codigo, saida = rodar(comando, BASE)
        if codigo != 0:
            anotar(f"FALHOU na {nome} (código {codigo})")
            detalhe = " / ".join(saida.strip().splitlines()[-3:])
            anotar("  " + detalhe)
            gravar_sinal(f"falhou na {nome}", detalhe[:400], antes)
            return codigo
        anotar(f"{nome}: ok ({time.time() - inicio:.0f}s)")

    depois = estado()
    novas = depois["edicoes"] - antes["edicoes"]
    anotar(f"depois: {depois['edicoes']} edições até {depois['ultima']}, "
           f"{depois['atos']} atos  (+{novas} edições, "
           f"+{depois['atos'] - antes['atos']} atos)")

    if not novas and not args.forcar:
        anotar("nada novo no portal — nada a publicar. Encerrado.")
        gravar_sinal("sem novidade", "o portal não publicou edição nova", depois)
        return 0

    versao = f"{depois['ultima'].replace('-', '.')}"
    arquivo = SERVIDOR / "dist" / f"diarios-mesquita-v{versao}.db.gz"
    arquivo.parent.mkdir(parents=True, exist_ok=True)

    # O -wal precisa ser consolidado ANTES de comprimir, ou o pacote sai sem as
    # escritas mais recentes — e sem erro nenhum que denuncie isso.
    con = sqlite3.connect(BANCO)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()

    inicio = time.time()
    with BANCO.open("rb") as e, gzip.open(arquivo, "wb", compresslevel=9) as s:
        shutil.copyfileobj(e, s, length=BLOCO)
    esperado = resumo_sha(arquivo)
    anotar(f"pacote v{versao}: {arquivo.stat().st_size / 1048576:.1f} MB "
           f"({time.time() - inicio:.0f}s) sha256 {esperado[:16]}…")

    if args.ensaio:
        anotar("ensaio: não publica, não faz push. Encerrado.")
        return 0

    notas = (f"{depois['edicoes']} edicoes (ate {depois['ultima']}), "
             f"{depois['paginas']} paginas ({depois['ocr']} por OCR), "
             f"{depois['atos']} atos segmentados.")
    codigo, saida = rodar(["gh", "release", "create", f"v{versao}", str(arquivo),
                           "--title", f"Acervo v{versao}", "--notes", notas], SERVIDOR)
    if codigo != 0:
        anotar(f"FALHOU ao criar a release (código {codigo})")
        detalhe = " / ".join(saida.strip().splitlines()[-3:])
        anotar("  " + detalhe)
        gravar_sinal("falhou ao publicar a release", detalhe[:400], depois)
        return codigo
    url = (f"https://github.com/{REPOSITORIO}/releases/download/"
           f"v{versao}/{arquivo.name}")
    anotar(f"release publicada: v{versao}")

    # Conferir o que de fato ficou publicado, antes de o Dockerfile apontar
    # para lá. Um asset truncado ou trocado só apareceria no log do Render.
    import urllib.request
    baixado = arquivo.with_suffix(".conferencia")
    try:
        with urllib.request.urlopen(url, timeout=900) as resposta, \
             baixado.open("wb") as destino:
            shutil.copyfileobj(resposta, destino, length=BLOCO)
        obtido = resumo_sha(baixado)
    finally:
        baixado.unlink(missing_ok=True)
    if obtido != esperado:
        anotar(f"ABORTADO: o asset publicado não confere (obtido {obtido[:16]}…). "
               "O Dockerfile NÃO foi alterado; o servidor segue no acervo anterior.")
        gravar_sinal("abortado: asset publicado não confere",
                     f"esperado {esperado[:16]}, obtido {obtido[:16]}", depois)
        return 1
    anotar("asset publicado conferido")

    docker = SERVIDOR / "Dockerfile"
    texto = docker.read_text(encoding="utf-8")
    import re
    texto = re.sub(r"^ARG ACERVO=.*$", f"ARG ACERVO={url}", texto, flags=re.M)
    texto = re.sub(r"^ARG ACERVO_SHA256=.*$", f"ARG ACERVO_SHA256={esperado}",
                   texto, flags=re.M)
    docker.write_text(texto, encoding="utf-8")

    for comando in (["git", "add", "Dockerfile"],
                    ["git", "commit", "-m",
                     f"Acervo v{versao} — {novas} edição(ões) nova(s)\n\n{notas}"],
                    ["git", "push", "origin", "master"]):
        codigo, saida = rodar(comando, SERVIDOR)
        if codigo != 0:
            anotar(f"FALHOU em `{' '.join(comando[:2])}` (código {codigo})")
            detalhe = " / ".join(saida.strip().splitlines()[-3:])
            anotar("  " + detalhe)
            gravar_sinal(f"falhou em {' '.join(comando[:2])}", detalhe[:400], depois)
            return codigo
    # `git push` responde "Everything up-to-date" com código 0 quando não há o
    # que empurrar. Conferir o codigo de saida nao prova nada: o que prova é o
    # remoto apontar para o commit local.
    _, local = rodar(["git", "rev-parse", "HEAD"], SERVIDOR)
    rodar(["git", "fetch", "origin", "master"], SERVIDOR)
    _, remoto = rodar(["git", "rev-parse", "origin/master"], SERVIDOR)
    if local.strip() != remoto.strip():
        aviso = (f"o push saiu sem erro, mas origin/master ficou em "
                 f"{remoto.strip()[:8]} e o commit local é {local.strip()[:8]}. "
                 "O Render vai continuar servindo o acervo anterior.")
        anotar("ABORTADO: " + aviso)
        gravar_sinal("abortado: push não alcançou o master", aviso, depois)
        return 1
    anotar(f"push conferido: origin/master em {remoto.strip()[:8]}")
    anotar("push feito — o Render reconstrói sozinho e confere o hash")
    gravar_sinal("publicado", f"release v{versao}, {novas} edição(ões) nova(s)", depois)
    anotar("concluído")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
