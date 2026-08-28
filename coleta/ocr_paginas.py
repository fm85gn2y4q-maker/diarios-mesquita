"""Reconhece o texto das páginas digitalizadas e devolve para `acervo.db`.

Só toca nas páginas marcadas `origem='vazia'` pelo extrator — as que não têm
camada de texto no PDF. Rodar de novo depois de baixar edições novas processa
apenas o que ainda falta.

**Por que Tesseract com `por`, e não os outros dois candidatos testados:**

- RapidOCR (modelo padrão, chinês/inglês): devolve "IMPOSTOSSOBREARENDA" e
  "Orcamento" — cola as palavras e perde todo acento. Palavra colada é fatal
  para o índice: vira um único termo, e "imposto sobre a renda" não acha nada.
- OCR pronto do portal: acentua e espaça certo, mas entrega a edição inteira
  sem número de página e com as colunas embaralhadas.
- Tesseract `por`: "DIÁRIO OFICIAL", "Orçamento", "Especificação" — acento e
  espaço corretos, e a página continua sendo a unidade.

A variante `tessdata_fast` empatou em qualidade com a `tessdata_best` na página
de conferência (3.423 contra 3.436 caracteres, mesmo texto) gastando 3,8 s
contra 8,6 s. Ficou a rápida.

Uso:
    python ocr_paginas.py                # tudo que está pendente
    python ocr_paginas.py --limite 50    # amostra, para conferir antes
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import fitz

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
BANCO = BASE / "acervo.db"
TESSDATA = BASE / "tessdata"

TESSERACT = next(
    (p for p in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Tesseract-OCR/tesseract.exe",
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path(shutil.which("tesseract") or "/nao-existe"),
    ) if p.exists()),
    None,
)

DPI = 300          # abaixo disto o corpo 6 das tabelas de orçamento se perde
MINIMO_UTIL = 200  # mesmo corte do extrator: abaixo disso a página segue vazia


def ocr_de_uma(tarefa: tuple[int, str, int]) -> tuple[int, str]:
    """Roda no processo filho. Devolve (id da página, texto reconhecido)."""
    pagina_id, arquivo, numero = tarefa
    try:
        doc = fitz.open(BASE / arquivo)
        pix = doc[numero - 1].get_pixmap(dpi=DPI)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            temporario = fh.name
        pix.save(temporario)
        doc.close()
        try:
            saida = subprocess.run(
                [str(TESSERACT), temporario, "stdout", "-l", "por", "--psm", "3"],
                capture_output=True,
                env=dict(os.environ, TESSDATA_PREFIX=str(TESSDATA)),
                timeout=180,
            )
            texto = saida.stdout.decode("utf-8", errors="replace")
        finally:
            os.unlink(temporario)
    except Exception as exc:  # noqa: BLE001
        return pagina_id, f"__ERRO__{exc}"

    linhas = [" ".join(l.split()) for l in texto.splitlines()]
    return pagina_id, "\n".join(l for l in linhas if l)


def main() -> int:
    ap = argparse.ArgumentParser(description="OCR das páginas digitalizadas")
    ap.add_argument("--limite", type=int, default=0, help="processa só N páginas")
    ap.add_argument("--processos", type=int, default=max(1, (os.cpu_count() or 4) - 6))
    args = ap.parse_args()

    if TESSERACT is None:
        print("tesseract.exe não encontrado — instale o Tesseract OCR antes.")
        return 2
    if not (TESSDATA / "por.traineddata").exists():
        print(f"falta {TESSDATA / 'por.traineddata'} (pacote de português).")
        return 2

    con = sqlite3.connect(BANCO)
    con.execute("PRAGMA journal_mode=WAL")
    consulta = """SELECT p.id, e.arquivo, p.pagina
                  FROM pagina p JOIN edicao e ON e.id = p.edicao_id
                  WHERE p.origem = 'vazia'
                  ORDER BY e.data, p.pagina"""
    if args.limite:
        consulta += f" LIMIT {int(args.limite)}"
    tarefas = con.execute(consulta).fetchall()

    if not tarefas:
        print("nada pendente.")
        return 0
    print(f"{len(tarefas)} páginas pendentes | {args.processos} processos | {TESSERACT}")

    inicio = time.time()
    feitos = reconhecidas = ainda_vazias = erros = 0
    with ProcessPoolExecutor(max_workers=args.processos) as pool:
        for pagina_id, texto in pool.map(ocr_de_uma, tarefas, chunksize=4):
            feitos += 1
            if texto.startswith("__ERRO__"):
                erros += 1
            elif len(texto) >= MINIMO_UTIL:
                con.execute(
                    "UPDATE pagina SET texto=?, origem='ocr_local', chars=? WHERE id=?",
                    (texto, len(texto), pagina_id),
                )
                reconhecidas += 1
            else:
                # Página que é só carimbo, assinatura ou folha em branco. Marcar
                # como reconhecida evita reprocessá-la em toda execução futura,
                # e `origem` guarda que ali não há texto — não que ele falte.
                con.execute(
                    "UPDATE pagina SET texto=?, origem='ocr_sem_texto', chars=? WHERE id=?",
                    (texto, len(texto), pagina_id),
                )
                ainda_vazias += 1
            if feitos % 100 == 0:
                con.commit()
                decorrido = time.time() - inicio
                resta = (len(tarefas) - feitos) * decorrido / feitos
                print(f"  {feitos}/{len(tarefas)} — {reconhecidas} com texto "
                      f"— faltam ~{resta / 60:.0f} min")
    con.commit()

    print("\nreconstruindo índice de busca...")
    con.execute("INSERT INTO pagina_fts(pagina_fts) VALUES('rebuild')")
    con.commit()

    print(f"\npáginas processadas: {feitos}")
    print(f"  com texto reconhecido: {reconhecidas}")
    print(f"  sem texto algum (carimbo/branco): {ainda_vazias}")
    print(f"  erros: {erros}")
    print(f"tempo: {(time.time() - inicio) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
