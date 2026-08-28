"""Segmenta as edições em atos — a portaria, o decreto, a lei, não a página.

Por que isto existe: medido neste acervo, **89,6% das edições trazem mais de um
ato**, mediana de 6, uma delas com 106. Indexar a página faz o trecho de uma
portaria responder sob o cabeçalho do decreto que estava acima. É erro de
sentido, não de precisão, e invisível para qualquer métrica de busca — o texto
casa perfeitamente.

COMO O CABEÇALHO É RECONHECIDO, E POR QUE ASSIM

Três exigências, cada uma calibrada contra o acervo inteiro (23.808 páginas de
texto nativo), não contra amostra:

1. **Vocabulário fechado.** Sem ele, o começo de linha devolve "CADASTRADO SOB
   O nº", "COMBINADA COM A LEI COMPLEMENTAR nº", "ATRAVÉS DA LEI nº" — citações
   no meio da frase que a quebra de linha do PDF jogou para o início. Eram os
   três padrões mais frequentes de todos.

2. **O cabeçalho ocupa a linha sozinho**, admitindo depois só a data e um
   ponto. A citação continua a oração, e é isso que a denuncia.

3. **Caixa alta.** Aqui esta base diverge da legislação municipal, e a
   divergência foi medida: lá, exigir caixa alta descartava 60 de 400 arquivos
   legítimos (15%), porque o modelo antigo escrevia `Lei nº 005 de 05 de março
   de 2001`. No Diário são 17.630 cabeçalhos em caixa alta contra 201 em caixa
   mista — 1,1%, estável ano a ano. A regra que lá era proibida, aqui custa 1%.

   E o que sobra em caixa mista é majoritariamente citação: "Lei Municipal nº
   1.122/2019.", "Decreto nº 763 de 01 de julho de 2009." Por isso o candidato
   em caixa mista não é descartado — é submetido à exigência extra de trazer,
   logo abaixo, fórmula de promulgação, ementa ou verbo dispositivo.

4. **Qualificador de origem derruba.** Cabeçalho nenhum diz "LEI MUNICIPAL" ou
   "LEI FEDERAL" — o ato não se apresenta dizendo de que ente é. Quem escreve
   assim está citando.

O NÚMERO, E A LIÇÃO QUE CUSTOU CARO NO PROJETO ANTERIOR

O padrão do número é `\\d{1,3}(?:\\.\\d{3})+|\\d+` — a alternativa com milhar
vem primeiro e exige `+`, não `*`. Com `*`, a primeira alternativa casa "110"
de `LEI Nº 1106` e o motor aceita: o ato vira outro ato, que existe. No acervo
de legislação esse defeito registrou que o Decreto 252/2005 fora revogado —
falso, e sustentado por um trecho de aparência impecável. Perda se percebe
contando; troca de identidade, não.

O QUE FICA DE FORA, E É PRECISO DIZER

Extratos de contrato, editais, avisos de licitação e atas de registro de preços
não têm cabeçalho numerado no padrão acima e **não são segmentados**. Continuam
pesquisáveis por página. Chamar de "atos" só o que esta segmentação alcança
seria esconder metade do que o Município publica.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
BANCO = BASE / "acervo.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ato (
    id              INTEGER PRIMARY KEY,
    edicao_id       INTEGER NOT NULL REFERENCES edicao(id) ON DELETE CASCADE,
    especie         TEXT NOT NULL,
    orgao           TEXT,
    numero          TEXT NOT NULL,
    ano             INTEGER,
    data_ato        TEXT,
    cabecalho       TEXT NOT NULL,
    ementa          TEXT,
    pagina_inicial  INTEGER NOT NULL,
    pagina_final    INTEGER NOT NULL,
    texto           TEXT NOT NULL,
    origem_texto    TEXT NOT NULL,
    tem_retificacao INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ato_chave ON ato(especie, numero, ano);
CREATE INDEX IF NOT EXISTS idx_ato_edicao ON ato(edicao_id);

CREATE VIRTUAL TABLE IF NOT EXISTS ato_fts USING fts5(
    cabecalho, ementa, texto,
    content='ato', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
"""

# Vocabulário fechado, descoberto por frequência no acervo — não inventado.
ESPECIES = r"PORTARIA|DECRETO|LEI\s+COMPLEMENTAR|LEI|RESOLU[ÇC][ÃA]O"

# Milhar primeiro e com `+`: ver a nota sobre o quantificador no cabeçalho.
NUMERO = r"\d{1,3}(?:\.\d{3})+|\d+"

DATA = (
    r"(?:,?\s*DE\s+(\d{1,2})\s*[ºo]?\s*DE\s+([A-ZÀ-Ýa-zà-ý]+)\s+DE\s+(\d{4}))"
)

CABECALHO = re.compile(
    r"^\s*(" + ESPECIES + r")"
    r"((?:\s+[A-ZÀ-Ý]{2,10})?)"          # sigla do órgão: DPMM, SEMED, CMAS…
    # `Nº.` traz o ordinal E o ponto: aceitar só um dos dois perdia 80 atos,
    # todos de 2015-2016, quando essa grafia era a corrente.
    r"\s*[Nn]?[º°]?\s*\.?\s*(" + NUMERO + r")"
    r"(?:\s*/\s*(\d{4}))?"
    + DATA + r"?"
    r"\s*\.?\s*$",
    re.IGNORECASE,
)

# "LEI MUNICIPAL", "DECRETO FEDERAL": quem qualifica o ente está citando.
QUALIFICADOR = re.compile(r"^\s*\w+\s+(MUNICIPAL|FEDERAL|ESTADUAL)\b", re.IGNORECASE)

# Só exigido de candidato em caixa mista. Vocabulário aprendido do que de fato
# aparece abaixo dos cabeçalhos deste Diário.
CONFIRMA = re.compile(
    r"^\s*(?:[\"“”']"
    r"|ART\.?\s*\d"
    r"|[OA]\s+(?:PREFEIT|SECRET|PRESIDENT|DIRETOR|PROCURADOR|CONSELHO|CÂMARA|CAMARA)"
    r"|CONSIDERANDO|ONDE\s+SE\s+L|LEIA-SE|FICA|RESOLVE|DECRETA|DISP[ÕO]E|AUTOR\s*:"
    r"|\*?REPUBLICAD|INSTITUI|ALTERA|CRIA|CONCEDE"
    r"|[A-ZÀ-Ý][A-ZÀ-Ýa-zà-ý]{3,}(?:ar|er|ir|AR|ER|IR)\b)",
    re.IGNORECASE,
)

# Linha que termina em vírgula, dois-pontos ou minúscula não acabou a frase —
# o que vier depois dela é continuação, não começo de ato.
CONTINUA_ORACAO = re.compile(r"[,;:]$|[a-zà-ÿ]$")

# O substantivo tem de estar aqui junto do particípio: a frase de fato usada
# nestas páginas é "*Republicação por haver saído com incorreção", e a versão
# que só reconhecia "republicado" deixava esses atos passar sem aviso — bem no
# ponto em que esta base mais erra.
RETIFICACAO = re.compile(
    r"\b(errata|retifica[çc][ãa]o|retificad[oa]|republica[çc][ãa]o|"
    r"republicad[oa]|leia-se|onde se l[êe]|torna[- ]se sem efeito)\b",
    re.IGNORECASE,
)

MESES = {m: i for i, m in enumerate(
    ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
     "agosto", "setembro", "outubro", "novembro", "dezembro"], 1)}

ROTULOS = {
    "PORTARIA": "portaria", "DECRETO": "decreto", "LEI": "lei",
    "LEI COMPLEMENTAR": "lei_complementar", "RESOLUÇÃO": "resolucao",
    "RESOLUCAO": "resolucao",
}


def _especie(bruta: str) -> str:
    chave = " ".join(bruta.upper().split())
    return ROTULOS.get(chave, chave.lower())


def _data_do_ato(dia, mes, ano) -> str | None:
    if not (dia and mes and ano):
        return None
    numero_mes = MESES.get(mes.lower())
    if not numero_mes:
        return None
    return f"{ano}-{numero_mes:02d}-{int(dia):02d}"


def achar_cabecalho(linha: str, anterior: str, proxima: str) -> dict | None:
    """Devolve os campos do cabeçalho, ou None se a linha não for um."""
    achado = CABECALHO.match(linha)
    if not achado:
        return None
    if QUALIFICADOR.match(linha):
        return None

    especie_bruta, orgao, numero, ano_barra, dia, mes, ano_extenso = achado.groups()
    rotulo = linha[: achado.end(2)]
    if rotulo != rotulo.upper():
        # Caixa mista: é citação até prova em contrário. Duas provas, e a
        # segunda foi aprendida de um erro — "Decreto 052/2001." aparecia cinco
        # vezes numa página, sempre no meio de "Art.1º … Decreto 052/2001. /
        # Art.2º …". A linha seguinte era "Art.2º", que satisfazia a
        # confirmação; foi a linha ANTERIOR, continuando a oração, que
        # denunciou a citação. Olhar só para frente não basta.
        if CONTINUA_ORACAO.search(anterior) or not CONFIRMA.match(proxima):
            return None

    ano = ano_barra or ano_extenso
    return {
        "especie": _especie(especie_bruta),
        "orgao": " ".join(orgao.split()).upper() or None,
        "numero": numero.replace(".", "").lstrip("0") or numero,
        "ano": int(ano) if ano else None,
        "data_ato": _data_do_ato(dia, mes, ano_extenso),
        "cabecalho": " ".join(linha.split()),
    }


def _ementa(linhas: list[str]) -> str | None:
    """A ementa do Diário vem entre aspas curvas logo abaixo do cabeçalho."""
    juntas = " ".join(l for l in linhas[:12] if l)
    achado = re.search(r"[“\"]([^”\"]{15,400})[”\"]", juntas)
    if achado:
        return " ".join(achado.group(1).split())
    return None


def segmentar_edicao(paginas: list[sqlite3.Row]) -> list[dict]:
    """Concatena as páginas da edição e corta nos cabeçalhos.

    A concatenação é necessária porque o ato atravessa a virada da página: um
    decreto que começa na p. 3 e termina na p. 5 é um ato, não três pedaços.
    """
    linhas: list[tuple[str, int, str]] = []   # (texto, página, origem)
    for p in paginas:
        for linha in p["texto"].split("\n"):
            linhas.append((linha.strip(), p["pagina"], p["origem"]))

    marcos: list[tuple[int, dict]] = []
    for i, (linha, _, _) in enumerate(linhas):
        if not linha:
            continue
        proxima = next((l for l, _, _ in linhas[i + 1:i + 4] if l), "")
        anterior = next((l for l, _, _ in reversed(linhas[max(0, i - 3):i]) if l), "")
        campos = achar_cabecalho(linha, anterior, proxima)
        if campos:
            marcos.append((i, campos))

    atos = []
    for ordem, (inicio, campos) in enumerate(marcos):
        fim = marcos[ordem + 1][0] if ordem + 1 < len(marcos) else len(linhas)
        corpo = linhas[inicio:fim]
        texto = "\n".join(l for l, _, _ in corpo if l)
        origens = {o for l, _, o in corpo if l}
        atos.append({
            **campos,
            "pagina_inicial": corpo[0][1],
            "pagina_final": corpo[-1][1],
            "texto": texto,
            "ementa": _ementa([l for l, _, _ in corpo[1:]]),
            "origem_texto": ("pdf" if origens == {"pdf"}
                             else "ocr" if origens <= {"ocr_local", "ocr_sem_texto"}
                             else "misto"),
            "tem_retificacao": int(bool(RETIFICACAO.search(texto))),
        })
    return atos


def main() -> int:
    ap = argparse.ArgumentParser(description="Segmenta as edições em atos")
    ap.add_argument("--amostra", type=int, default=0,
                    help="processa só N edições, para conferir antes")
    args = ap.parse_args()

    con = sqlite3.connect(BANCO)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    con.execute("DELETE FROM ato")

    edicoes = con.execute(
        "SELECT id, data FROM edicao ORDER BY data" +
        (f" LIMIT {int(args.amostra)}" if args.amostra else "")
    ).fetchall()
    print(f"{len(edicoes)} edições a segmentar")

    total = 0
    sem_ato = 0
    for n, edicao in enumerate(edicoes, 1):
        paginas = con.execute(
            "SELECT pagina, texto, origem FROM pagina WHERE edicao_id=? ORDER BY pagina",
            (edicao["id"],),
        ).fetchall()
        atos = segmentar_edicao(paginas)
        if not atos:
            sem_ato += 1
        for ato in atos:
            con.execute(
                """INSERT INTO ato (edicao_id, especie, orgao, numero, ano, data_ato,
                                    cabecalho, ementa, pagina_inicial, pagina_final,
                                    texto, origem_texto, tem_retificacao)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (edicao["id"], ato["especie"], ato["orgao"], ato["numero"], ato["ano"],
                 ato["data_ato"], ato["cabecalho"], ato["ementa"],
                 ato["pagina_inicial"], ato["pagina_final"], ato["texto"],
                 ato["origem_texto"], ato["tem_retificacao"]),
            )
        total += len(atos)
        if n % 400 == 0:
            con.commit()
            print(f"  {n}/{len(edicoes)} — {total} atos")
    con.commit()

    print("\nreconstruindo índice de busca dos atos...")
    con.execute("INSERT INTO ato_fts(ato_fts) VALUES('rebuild')")
    con.commit()

    print(f"\natos segmentados: {total}")
    print(f"edições sem nenhum ato reconhecido: {sem_ato} "
          f"({100 * sem_ato / len(edicoes):.1f}%)")
    for especie, n in con.execute(
        "SELECT especie, COUNT(*) FROM ato GROUP BY 1 ORDER BY 2 DESC"
    ):
        print(f"  {especie:18s} {n:6d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
