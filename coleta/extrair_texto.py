"""Extrai o texto do acervo para `acervo.db` — uma linha por página.

Duas fontes de texto, nesta ordem de preferência:

1. **Camada de texto do PDF** (PyMuPDF). Onde existe, é melhor que qualquer OCR:
   preserva a ordem de leitura. Conferido no acervo — na edição de 27/03/2024 a
   extração devolve "DECRETO Nº 3.543 ... ABRE CRÉDITO ADICIONAL SUPLEMENTAR"
   na ordem certa, enquanto o OCR pronto do portal embaralha as colunas e
   intercala o nome do prefeito no meio da ementa do decreto.
2. **OCR**, só para as páginas digitalizadas, que não têm camada nenhuma.

A página é a unidade porque é assim que se cita um diário oficial ("DOM de
24/07/2026, p. 3"), e porque permite dizer de onde veio cada trecho: texto
nativo e texto reconhecido por máquina não merecem a mesma confiança numa peça.

Uso:
    python extrair_texto.py            # incremental: só o que ainda não está no banco
    python extrair_texto.py --refazer  # reprocessa tudo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

import fitz

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
BANCO = BASE / "acervo.db"

# Abaixo disto a página não sustenta busca: é cabeçalho solto ou ruído de
# digitalização. Vira candidata a OCR.
MINIMO_UTIL = 200

ESQUEMA = """
CREATE TABLE IF NOT EXISTS edicao (
    id            INTEGER PRIMARY KEY,
    data          TEXT NOT NULL,
    numero        TEXT NOT NULL,
    descricao     TEXT,
    arquivo       TEXT NOT NULL UNIQUE,
    codigo_anexo  INTEGER,
    url           TEXT,
    paginas       INTEGER,
    sha256        TEXT
);
CREATE INDEX IF NOT EXISTS idx_edicao_data ON edicao(data);

CREATE TABLE IF NOT EXISTS pagina (
    id         INTEGER PRIMARY KEY,
    edicao_id  INTEGER NOT NULL REFERENCES edicao(id) ON DELETE CASCADE,
    pagina     INTEGER NOT NULL,
    texto      TEXT NOT NULL,
    origem     TEXT NOT NULL,   -- 'pdf' | 'ocr_portal' | 'ocr_local' | 'vazia'
    chars      INTEGER NOT NULL,
    UNIQUE(edicao_id, pagina)
);

-- FTS5 de conteúdo externo: o índice não duplica o texto, lê da tabela pagina.
-- remove_diacritics 2 faz "resolucao" casar com "RESOLUÇÃO" — o advogado
-- digita a consulta sem acento com frequência, e o acervo é todo acentuado.
CREATE VIRTUAL TABLE IF NOT EXISTS pagina_fts USING fts5(
    texto,
    content='pagina',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
"""


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(BANCO)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(ESQUEMA)
    return con


def limpar(texto: str) -> str:
    """O PDF do diário devolve muita linha só de espaços (a diagramação em
    caixas). Isso infla o tamanho e atrapalha o trecho de contexto na busca."""
    linhas = [" ".join(l.split()) for l in texto.splitlines()]
    return "\n".join(l for l in linhas if l)


def indexar_edicao(con: sqlite3.Connection, pdf: Path, meta: dict) -> tuple[int, int]:
    """Devolve (páginas com texto, páginas pendentes de OCR)."""
    dados = pdf.read_bytes()
    sha = hashlib.sha256(dados).hexdigest()
    rel = str(pdf.relative_to(BASE)).replace("\\", "/")

    doc = fitz.open(pdf)
    cur = con.execute(
        """INSERT INTO edicao (data, numero, descricao, arquivo, codigo_anexo, url, paginas, sha256)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(arquivo) DO UPDATE SET
             data=excluded.data, numero=excluded.numero, descricao=excluded.descricao,
             codigo_anexo=excluded.codigo_anexo, url=excluded.url,
             paginas=excluded.paginas, sha256=excluded.sha256
           RETURNING id""",
        (meta["data"], meta["numero"], meta["descricao"], rel,
         meta["codigo_anexo"], meta["url"], doc.page_count, sha),
    )
    edicao_id = cur.fetchone()[0]
    con.execute("DELETE FROM pagina WHERE edicao_id=?", (edicao_id,))

    com_texto = pendentes = 0
    for n, pagina in enumerate(doc, 1):
        texto = limpar(pagina.get_text())
        if len(texto) >= MINIMO_UTIL:
            origem = "pdf"
            com_texto += 1
        else:
            origem = "vazia"   # candidata a OCR; preenchida por ocr_paginas.py
            pendentes += 1
        con.execute(
            "INSERT INTO pagina (edicao_id, pagina, texto, origem, chars) VALUES (?,?,?,?,?)",
            (edicao_id, n, texto, origem, len(texto)),
        )
    doc.close()
    return com_texto, pendentes


def reconstruir_fts(con: sqlite3.Connection) -> None:
    con.execute("INSERT INTO pagina_fts(pagina_fts) VALUES('rebuild')")


def main() -> int:
    ap = argparse.ArgumentParser(description="Extrai o texto do acervo para SQLite")
    ap.add_argument("--refazer", action="store_true")
    args = ap.parse_args()

    indice = BASE / "indice.csv"
    if not indice.exists():
        print("indice.csv não encontrado — rode baixar_diarios.py antes.")
        return 2

    registros: dict[str, dict] = {}
    with indice.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            if r["fonte"] != "municipio":
                continue
            # O índice do baixador não traz o código em coluna própria; ele
            # está na URL do anexo, e é a chave para rebaixar ou pedir o OCR.
            achado = re.search(r"codigo=(\d+)", r["url"])
            registros[r["arquivo"]] = {
                "data": r["data"], "numero": r["numero"], "descricao": r["descricao"],
                "codigo_anexo": int(achado.group(1)) if achado else None,
                "url": r["url"],
            }

    con = conectar()
    if args.refazer:
        con.executescript("DELETE FROM pagina; DELETE FROM edicao;")

    ja_no_banco = {
        arquivo for (arquivo,) in con.execute(
            "SELECT e.arquivo FROM edicao e WHERE EXISTS (SELECT 1 FROM pagina p WHERE p.edicao_id=e.id)"
        )
    }

    pdfs = sorted((BASE / "municipio").rglob("*.pdf"))
    a_fazer = [p for p in pdfs
               if args.refazer or str(p.relative_to(BASE)).replace("\\", "/") not in ja_no_banco]
    print(f"{len(pdfs)} edições no acervo | {len(a_fazer)} a processar")

    total_texto = total_pend = falhas = 0
    for i, pdf in enumerate(a_fazer, 1):
        rel = str(pdf.relative_to(BASE)).replace("\\", "/")
        meta = registros.get(rel)
        if meta is None:
            # Arquivo em disco fora do índice: não dá para datar nem citar.
            print(f"  ! fora do índice, ignorado: {rel}")
            falhas += 1
            continue
        try:
            t, p = indexar_edicao(con, pdf, meta)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! erro em {rel}: {str(exc)[:120]}")
            falhas += 1
            continue
        total_texto += t
        total_pend += p
        if i % 200 == 0:
            con.commit()
            print(f"  {i}/{len(a_fazer)}")
    con.commit()

    print("\nreconstruindo índice de busca...")
    reconstruir_fts(con)
    con.commit()

    edicoes, paginas = con.execute(
        "SELECT (SELECT COUNT(*) FROM edicao), (SELECT COUNT(*) FROM pagina)"
    ).fetchone()
    # Contar por origem, não subtrair as vazias do total: numa reexecução as
    # páginas já reconhecidas têm origem 'ocr_local', e a conta por subtração
    # as somava ao texto nativo — o relatório dizia que o acervo inteiro era
    # nativo justamente depois de o OCR ter rodado.
    por_origem = dict(con.execute("SELECT origem, COUNT(*) FROM pagina GROUP BY 1"))
    print(f"\nedições no banco: {edicoes}")
    print(f"páginas: {paginas}")
    for origem, quantas in sorted(por_origem.items(), key=lambda x: -x[1]):
        print(f"  {origem:16s} {quantas:6d}")
    print(f"pendentes de OCR: {por_origem.get('vazia', 0)}")
    if falhas:
        print(f"falhas: {falhas}")
    print(f"banco: {BANCO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
