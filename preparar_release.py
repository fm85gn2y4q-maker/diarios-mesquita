"""Comprime o acervo e imprime o que vai para o Dockerfile e para a release.

O banco tem 257 MB e 84 MB comprimido — acima dos 50 MB em que o GitHub
adverte. Não entra no Git: vai como asset de release, e a imagem o busca na
construção conferindo o sha256. Divergindo o arquivo publicado do declarado, o
build falha em vez de subir um acervo diferente daquele que foi testado.

    python preparar_release.py 1.0.0
"""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _achar_banco() -> Path:
    """Localiza o acervo, que vive fora do repositório e mudou de disco.

    Em 23/08/2026 os 4 GB foram para o HD externo. A busca é por candidatos,
    em ordem, para que o erro seja legível quando o HD estiver desconectado —
    e não um "arquivo não encontrado" apontando um caminho que já não é o certo.
    """
    do_ambiente = os.environ.get("DIARIOS_BANCO")
    candidatos = ([Path(do_ambiente)] if do_ambiente else []) + [
        # O disco rápido vem primeiro, e a ordem não é estética: servir este
        # SQLite de HD USB leva de 16 a 30 s por busca contra 0,01 s no NVMe —
        # o FTS5 faz leitura aleatória, e disco que gira paga ~10 ms por salto.
        # Medido em 23/08/2026. Para o HD externo vai só a matéria-prima (os
        # PDFs), alcançada por junção; o banco que responde fica aqui.
        Path.home() / "Mesquita_Diarios_Oficiais" / "acervo.db",
        Path("D:/Mesquita_Diarios_Oficiais/acervo.db"),
    ]
    for caminho in candidatos:
        if caminho.exists():
            return caminho
    return candidatos[0]


BANCO = _achar_banco()
BLOCO = 4 * 1024 * 1024


def _resumo(caminho: Path) -> str:
    digestor = hashlib.sha256()
    with caminho.open("rb") as fluxo:
        for bloco in iter(lambda: fluxo.read(BLOCO), b""):
            digestor.update(bloco)
    return digestor.hexdigest()


def _numeros(banco: Path) -> str:
    """Os números entram na descrição da release — é o que identifica a coleta."""
    con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    try:
        edicoes, primeira, ultima = con.execute(
            "SELECT COUNT(*), MIN(data), MAX(data) FROM edicao"
        ).fetchone()
        paginas = con.execute("SELECT COUNT(*) FROM pagina").fetchone()[0]
        try:
            atos = con.execute("SELECT COUNT(*) FROM ato").fetchone()[0]
        except sqlite3.OperationalError:
            atos = 0
        ocr = con.execute(
            "SELECT COUNT(*) FROM pagina WHERE origem LIKE 'ocr%'"
        ).fetchone()[0]
    finally:
        con.close()
    return (f"{edicoes} edições ({primeira} a {ultima}), {paginas} páginas "
            f"({ocr} por OCR), {atos} atos segmentados")


def preparar(versao: str, repositorio: str = "fm85gn2y4q-maker/diarios-mesquita") -> int:
    if not BANCO.exists():
        print(f"Acervo não encontrado em {BANCO}. "
              "Se ele está no HD externo, confira se o disco D: está conectado; "
              "senão, aponte DIARIOS_BANCO para o arquivo.", file=sys.stderr)
        return 1

    # Rodar com o servidor no ar deixaria o -wal por fora e o acervo publicado
    # sairia sem as últimas escritas — silenciosamente.
    if BANCO.with_name(BANCO.name + "-wal").exists():
        print("AVISO: há um -wal ao lado do banco. Feche o que estiver escrevendo\n"
              "       nele (servidor, script de coleta) e rode de novo, ou o\n"
              "       acervo publicado sairá sem as últimas alterações.",
              file=sys.stderr)

    destino = RAIZ / "dist" / f"diarios-mesquita-v{versao}.db.gz"
    destino.parent.mkdir(parents=True, exist_ok=True)

    print(f"Comprimindo {BANCO.stat().st_size / 1048576:.0f} MB… (leva ~40 s)")
    with BANCO.open("rb") as entrada, gzip.open(destino, "wb", compresslevel=9) as saida:
        shutil.copyfileobj(entrada, saida, length=BLOCO)

    digest = _resumo(destino)
    arquivo = destino.name
    url = (f"https://github.com/{repositorio}/releases/download/"
           f"v{versao}/{arquivo}")

    print(f"\n{destino}  ({destino.stat().st_size / 1048576:.1f} MB)")
    print(f"conteúdo: {_numeros(BANCO)}\n")
    print("1. Publique a release e anexe o .gz:\n")
    print(f'   gh release create v{versao} "{destino}" \\')
    print(f'     --title "Acervo v{versao}" --notes "{_numeros(BANCO)}"\n')
    print("2. Troque estas duas linhas no Dockerfile:\n")
    print(f"   ARG ACERVO={url}")
    print(f"   ARG ACERVO_SHA256={digest}\n")
    print("3. Commite o Dockerfile. O Render reconstrói e confere o hash.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    raise SystemExit(preparar(sys.argv[1], *sys.argv[2:3]))
