"""Baixa os Diários Oficiais publicados no Portal da Transparência de Mesquita-RJ.

O portal tem uma API interna (a mesma que a página do diário usa por AJAX):

    POST /diario_oficial_get.php          body: mesano=<mês>/<ano>   -> JSON do mês
    GET  /diario_oficial_get_anexo.php?codigo=<Codigo_ANEXO>         -> 302 -> PDF

São quatro cadernos, cada um com seu par de endpoints:
municipal, estadual, grande circulação e União.

O script roda em duas fases — primeiro monta o catálogo mês a mês, depois baixa
o que falta. É seguro reexecutar: arquivo já baixado e íntegro não é rebaixado,
o que torna a atualização mensal barata.

Uso:
    python baixar_diarios.py                      # tudo
    python baixar_diarios.py --fonte municipio    # só o diário do município
    python baixar_diarios.py --ano-inicial 2024   # recorte de período
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PORTAL = "https://transparencia.mesquita.rj.gov.br"
BASE = Path(__file__).resolve().parent

# rótulo -> (endpoint de listagem, molde da URL do anexo, prefixo do arquivo).
# O caderno municipal passa por um .php que redireciona; os outros três apontam
# direto para a regra do WebRun. Foi assim que cada página do portal foi escrita.
_RULE = PORTAL + "/ver20240713/WEB-ObterAnexo{}.rule?sys=LAI&codigo={{}}"
FONTES = {
    "municipio": ("diario_oficial_get.php", PORTAL + "/diario_oficial_get_anexo.php?codigo={}", "DOM"),
    "estado": ("diario_oficial_getestado.php", _RULE.format("estado"), "DOE"),
    "grande_circulacao": ("diario_oficial_getmaior.php", _RULE.format("maior"), "DOGC"),
    "uniao": ("diario_oficial_getuniao.php", _RULE.format("uniao"), "DOU"),
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) baixador-diarios-mesquita/1.0"
PAUSA = 0.3          # entre requisições de listagem
TENTATIVAS = 4
THREADS = 5


def _abrir(url: str, dados: bytes | None = None, timeout: int = 180):
    req = urllib.request.Request(url, data=dados, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Referer": f"{PORTAL}/diario_oficial_busca.php",
    })
    if dados is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("X-Requested-With", "XMLHttpRequest")
    return urllib.request.urlopen(req, timeout=timeout)


def _com_retentativa(fn, descricao: str):
    """O servidor do portal é modesto e derruba conexão sob rajada."""
    erro = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - qualquer falha de rede vale retry
            erro = exc
            if tentativa < TENTATIVAS:
                time.sleep(2 ** tentativa)
    raise RuntimeError(f"{descricao}: {erro}") from erro


def listar_mes(fonte: str, mes: int, ano: int) -> list[dict]:
    endpoint = FONTES[fonte][0]
    corpo = urllib.parse.urlencode({"mesano": f"{mes}/{ano}"}).encode()

    def busca():
        with _abrir(f"{PORTAL}/{endpoint}", corpo, timeout=90) as r:
            return r.read().decode("utf-8-sig", errors="replace")

    bruto = _com_retentativa(busca, f"listagem {fonte} {mes}/{ano}").strip()
    if not bruto:
        return []
    dados = json.loads(bruto)
    return dados if isinstance(dados, list) else []


def _numero(item: dict) -> str:
    """'Nº 002490' -> '002490'. Alguns cadernos não numeram; cai no código."""
    texto = str(item.get("ANEXO") or item.get("DESCRICAO") or "")
    digitos = "".join(c for c in texto if c.isdigit())
    return digitos or f"cod{item.get('Codigo_ANEXO')}"


def _data_iso(item: dict) -> str:
    bruto = str(item.get("DATA_PUBLICACAO") or "")[:10]
    try:
        datetime.strptime(bruto, "%Y-%m-%d")
        return bruto
    except ValueError:
        pass
    try:
        return datetime.strptime(item.get("Data_Formatada", ""), "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return "sem-data"


def montar_catalogo(fontes: list[str], ano_inicial: int, ano_final: int) -> list[dict]:
    catalogo: list[dict] = []
    vistos: set[tuple[str, int]] = set()
    for fonte in fontes:
        prefixo = FONTES[fonte][2]
        total_fonte = 0
        for ano in range(ano_inicial, ano_final + 1):
            do_ano = 0
            for mes in range(1, 13):
                for item in listar_mes(fonte, mes, ano):
                    codigo = item.get("Codigo_ANEXO")
                    if codigo is None or (fonte, codigo) in vistos:
                        continue
                    vistos.add((fonte, codigo))
                    data = _data_iso(item)
                    numero = _numero(item)
                    catalogo.append({
                        "fonte": fonte,
                        "ano": ano,
                        "data": data,
                        "numero": numero,
                        "codigo_anexo": codigo,
                        "descricao": (item.get("DESCRICAO") or "").strip(),
                        "arquivo": f"{fonte}/{ano}/{prefixo}_{data}_{numero}.pdf",
                        "url": FONTES[fonte][1].format(codigo),
                    })
                    do_ano += 1
                time.sleep(PAUSA)
            if do_ano:
                print(f"  {fonte:18s} {ano}: {do_ano} edições")
            total_fonte += do_ano
        print(f"{fonte}: {total_fonte} edições catalogadas")

    # O portal às vezes registra a mesma edição sob dois códigos, e aí dois
    # registros disputam o mesmo nome de arquivo. Nos casos conferidos o
    # conteúdo era idêntico — mas se um dia não for, o segundo download
    # sobrescreveria uma edição de verdade sem deixar rastro. Os marcados aqui
    # saem da fila paralela e são resolvidos por conteúdo, um a um.
    repetidos = collections.Counter(r["arquivo"] for r in catalogo)
    for registro in catalogo:
        registro["colisao"] = repetidos[registro["arquivo"]] > 1
    return catalogo


def baixar(registro: dict) -> tuple[dict, str, str]:
    destino = BASE / registro["arquivo"]
    ja_existe = destino.exists() and destino.stat().st_size > 1024
    if ja_existe and not registro.get("colisao"):
        return registro, "JA_EXISTIA", ""
    destino.parent.mkdir(parents=True, exist_ok=True)

    def pega() -> bytes:
        with _abrir(registro["url"]) as r:
            return r.read()

    try:
        conteudo = _com_retentativa(pega, registro["arquivo"])
    except RuntimeError as exc:
        return registro, "ERRO", str(exc)[:200]

    # O endpoint responde 302 para o PDF real; se o portal devolver HTML é
    # página de erro, e gravá-la como .pdf esconderia a falha do acervo.
    if not conteudo.startswith(b"%PDF"):
        return registro, "NAO_E_PDF", f"{len(conteudo)} bytes, início {conteudo[:20]!r}"

    if registro.get("colisao") and ja_existe:
        atual = destino.read_bytes()
        if hashlib.sha256(atual).digest() == hashlib.sha256(conteudo).digest():
            return registro, "DUPLICADO_NO_PORTAL", f"mesmo conteúdo, código {registro['codigo_anexo']}"
        # Documentos distintos sob o mesmo rótulo: guarda os dois.
        destino = destino.with_name(f"{destino.stem}_cod{registro['codigo_anexo']}.pdf")
        registro["arquivo"] = str(destino.relative_to(BASE)).replace("\\", "/")

    temporario = destino.with_suffix(".pdf.parcial")
    temporario.write_bytes(conteudo)
    temporario.replace(destino)
    return registro, "OK", str(len(conteudo))


def main() -> int:
    ap = argparse.ArgumentParser(description="Baixa os Diários Oficiais de Mesquita-RJ")
    ap.add_argument("--fonte", choices=[*FONTES, "todas"], default="todas")
    ap.add_argument("--ano-inicial", type=int, default=2013)
    ap.add_argument("--ano-final", type=int, default=datetime.now().year)
    ap.add_argument("--somente-catalogo", action="store_true")
    args = ap.parse_args()

    fontes = list(FONTES) if args.fonte == "todas" else [args.fonte]

    print(f"Catalogando {args.ano_inicial}-{args.ano_final} em {len(fontes)} caderno(s)...")
    catalogo = montar_catalogo(fontes, args.ano_inicial, args.ano_final)
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "catalogo.json").write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nTotal catalogado: {len(catalogo)} edições\n")
    if args.somente_catalogo:
        return 0

    resultados: list[tuple[dict, str, str]] = []
    paralelos = [r for r in catalogo if not r.get("colisao")]
    disputados = [r for r in catalogo if r.get("colisao")]

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        futuros = {pool.submit(baixar, r): r for r in paralelos}
        for feito, futuro in enumerate(as_completed(futuros), 1):
            resultados.append(futuro.result())
            if feito % 25 == 0 or feito == len(paralelos):
                ok = sum(1 for _, s, _ in resultados if s in ("OK", "JA_EXISTIA"))
                print(f"  {feito}/{len(paralelos)} — {ok} íntegros")

    for registro in disputados:  # em série: dois deles gravariam o mesmo nome
        resultados.append(baixar(registro))

    resultados.sort(key=lambda t: (t[0]["fonte"], t[0]["data"], t[0]["numero"]))
    with (BASE / "indice.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["fonte", "data", "numero", "descricao", "arquivo", "url", "status", "detalhe"])
        for reg, status, detalhe in resultados:
            w.writerow([reg["fonte"], reg["data"], reg["numero"], reg["descricao"],
                        reg["arquivo"], reg["url"], status, detalhe])

    print("\nResumo:")
    for status in ("OK", "JA_EXISTIA", "DUPLICADO_NO_PORTAL", "NAO_E_PDF", "ERRO"):
        n = sum(1 for _, s, _ in resultados if s == status)
        if n:
            print(f"  {status:11s} {n}")
    falhas = [(r, d) for r, s, d in resultados if s in ("ERRO", "NAO_E_PDF")]
    for reg, detalhe in falhas[:15]:
        print(f"  falha: {reg['arquivo']} — {detalhe}")
    print(f"\nPasta: {BASE}\nÍndice: {BASE / 'indice.csv'}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
