"""Atualiza o acervo com o que o portal publicou desde a última coleta.

Encadeia os quatro passos na ordem obrigatória — baixar, extrair, reconhecer,
segmentar — e para no primeiro que falhar. Todos são incrementais: reexecutar
sem novidade custa os três minutos da varredura do portal e não reprocessa
nada.

    python atualizar.py            # atualiza o acervo local
    python atualizar.py --release  # e prepara o pacote para publicar

A ordem não é arbitrária. O OCR só enxerga o que o extrator marcou como página
sem texto, e a segmentação lê o texto que os dois produziram: inverter perde a
edição nova ou a segmenta pela metade.

Depois disto, publicar é assunto do repositório do servidor — veja o que este
script imprime no fim.
"""

from __future__ import annotations

import argparse
import subprocess
import sqlite3
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
BANCO = BASE / "acervo.db"
PYTHON_OCR = BASE / ".venv-ocr" / "Scripts" / "python.exe"

PASSOS = [
    ("baixando o que falta do portal", [sys.executable, "baixar_diarios.py",
                                        "--fonte", "municipio"]),
    ("extraindo o texto nativo", [sys.executable, "extrair_texto.py"]),
    ("reconhecendo as páginas digitalizadas", [str(PYTHON_OCR), "ocr_paginas.py"]),
    ("segmentando as edições em atos", [sys.executable, "segmentar_atos.py"]),
]


def _estado() -> dict:
    if not BANCO.exists():
        return {}
    con = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    try:
        edicoes, ultima = con.execute(
            "SELECT COUNT(*), MAX(data) FROM edicao").fetchone()
        paginas = con.execute("SELECT COUNT(*) FROM pagina").fetchone()[0]
        try:
            atos = con.execute("SELECT COUNT(*) FROM ato").fetchone()[0]
        except sqlite3.OperationalError:
            atos = 0
        return {"edicoes": edicoes, "ultima": ultima, "paginas": paginas, "atos": atos}
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Atualiza o acervo do Diário Oficial")
    ap.add_argument("--release", metavar="VERSAO",
                    help="prepara o pacote para publicar (ex.: 1.1.0)")
    args = ap.parse_args()

    if not PYTHON_OCR.exists():
        print(f"venv do OCR não encontrado em {PYTHON_OCR}", file=sys.stderr)
        return 2

    antes = _estado()
    if antes:
        print(f"antes: {antes['edicoes']} edições até {antes['ultima']}, "
              f"{antes['paginas']} páginas, {antes['atos']} atos\n")

    inicio = time.time()
    for descricao, comando in PASSOS:
        print(f"── {descricao}")
        resultado = subprocess.run(comando, cwd=BASE)
        if resultado.returncode != 0:
            print(f"\nfalhou em '{descricao}' (código {resultado.returncode}). "
                  "O acervo ficou no estado anterior a este passo; corrija e "
                  "rode de novo — os passos já concluídos não se repetem.",
                  file=sys.stderr)
            return resultado.returncode
        print()

    depois = _estado()
    print("─" * 62)
    print(f"depois: {depois['edicoes']} edições até {depois['ultima']}, "
          f"{depois['paginas']} páginas, {depois['atos']} atos")
    if antes:
        novas = depois["edicoes"] - antes["edicoes"]
        print(f"novidade: {novas} edição(ões), "
              f"{depois['paginas'] - antes['paginas']} páginas, "
              f"{depois['atos'] - antes['atos']} atos")
        if not novas:
            print("Nada novo no portal — não há o que publicar.")
    print(f"tempo: {(time.time() - inicio) / 60:.1f} min")

    if args.release:
        # O -wal precisa ser consolidado ANTES de comprimir, ou o pacote sai
        # sem as escritas mais recentes e sem erro nenhum.
        con = sqlite3.connect(BANCO)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
        print("\n── preparando o pacote para publicação")
        subprocess.run(
            [sys.executable, "preparar_release.py", args.release],
            cwd=Path.home() / "projetos" / "diarios-mesquita",
        )
    else:
        print("\nO servidor local (Claude Desktop) já enxerga o acervo novo.")
        print("Para atualizar o servidor hospedado, rode de novo com "
              "--release <versão>.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
