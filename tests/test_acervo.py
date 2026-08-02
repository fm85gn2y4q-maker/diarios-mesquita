"""Testes da camada de dados.

Montam um acervo mínimo em memória de disco temporário, com o mesmo esquema
que `extrair_texto.py` cria. O que se testa aqui não é o SQLite — é o
comportamento de que a resposta ao advogado depende: se a busca degrada para
correspondência parcial em vez de devolver vazio, se a marca de retificação é
detectada, e se a origem do texto chega até a citação.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from diarios.acervo import Acervo, _para_iso, montar_consulta_fts  # noqa: E402

ESQUEMA = """
CREATE TABLE edicao (
    id INTEGER PRIMARY KEY, data TEXT, numero TEXT, descricao TEXT,
    arquivo TEXT UNIQUE, codigo_anexo INTEGER, url TEXT, paginas INTEGER, sha256 TEXT
);
CREATE TABLE pagina (
    id INTEGER PRIMARY KEY, edicao_id INTEGER, pagina INTEGER,
    texto TEXT, origem TEXT, chars INTEGER
);
CREATE TABLE ato (
    id INTEGER PRIMARY KEY, edicao_id INTEGER, especie TEXT, orgao TEXT,
    numero TEXT, ano INTEGER, data_ato TEXT, cabecalho TEXT, ementa TEXT,
    pagina_inicial INTEGER, pagina_final INTEGER, texto TEXT,
    origem_texto TEXT, tem_retificacao INTEGER DEFAULT 0
);
CREATE VIRTUAL TABLE ato_fts USING fts5(
    cabecalho, ementa, texto, content='ato', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
CREATE VIRTUAL TABLE pagina_fts USING fts5(
    texto, content='pagina', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
"""

PAGINAS = [
    # (data, numero, pagina, origem, texto)
    ("2022-05-13", "001485", 1, "pdf",
     "DECRETO Nº 3.204 Declara de utilidade pública para fins de desapropriação "
     "o imóvel situado na Rua Arthur Oliveira Vechi."),
    ("2022-05-13", "001485", 2, "pdf",
     "PORTARIA Nº 210/2022 Designa servidor para fiscalizar o contrato."),
    ("2024-03-27", "001939", 1, "pdf",
     "Republicado por haver saído com incorreção. DECRETO Nº 3.543 abre crédito "
     "adicional suplementar ao orçamento fiscal."),
    ("2020-01-02", "00904", 5, "ocr_local",
     "RESUMO GERAL DA RECEITA Orçamento de 2020 IMPOSTOS TAXAS E CONTRIBUIÇÕES "
     "DE MELHORIA receitas correntes."),
]


@pytest.fixture()
def acervo(tmp_path: Path) -> Acervo:
    caminho = tmp_path / "acervo.db"
    con = sqlite3.connect(caminho)
    con.executescript(ESQUEMA)
    edicoes: dict[str, int] = {}
    for data, numero, pagina, origem, texto in PAGINAS:
        if data not in edicoes:
            cur = con.execute(
                "INSERT INTO edicao (data,numero,descricao,arquivo,url,paginas) "
                "VALUES (?,?,?,?,?,?)",
                (data, numero, f"Nº {numero}", f"municipio/x/{data}.pdf",
                 f"https://exemplo/{data}.pdf", 6),
            )
            edicoes[data] = cur.lastrowid
        con.execute(
            "INSERT INTO pagina (edicao_id,pagina,texto,origem,chars) VALUES (?,?,?,?,?)",
            (edicoes[data], pagina, texto, origem, len(texto)),
        )
    con.execute("INSERT INTO pagina_fts(pagina_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    return Acervo(caminho)


def test_acha_pelo_termo_sem_acento(acervo: Acervo):
    achados, parcial, _ = acervo.pesquisar("desapropriacao")
    assert achados, "acento não pode separar a consulta do texto"
    assert not parcial
    assert "3.204" in achados[0].achado


def test_degrada_para_parcial_em_vez_de_vazio(acervo: Acervo):
    """A pergunta do advogado traz palavras a mais; devolver nada é pior."""
    achados, parcial, _ = acervo.pesquisar("desapropriação helicóptero submarino")
    assert achados
    assert parcial is True


def test_palavra_de_formulacao_nao_zera_a_busca(acervo: Acervo):
    achados, parcial, _ = acervo.pesquisar("existe algum decreto de desapropriação?")
    assert achados
    assert not parcial, "as vazias deveriam ter sido descartadas, não exigidas"


def test_marca_de_retificacao_e_detectada(acervo: Acervo):
    achados, _, _ = acervo.pesquisar("crédito adicional suplementar")
    assert achados
    assert achados[0].tem_marca_de_retificacao
    assert "aviso_retificacao" in achados[0].para_dict()


def test_pagina_sem_retificacao_nao_recebe_aviso(acervo: Acervo):
    achados, _, _ = acervo.pesquisar("fiscalizar o contrato")
    assert achados
    assert "aviso_retificacao" not in achados[0].para_dict()


def test_origem_ocr_vira_aviso_na_resposta(acervo: Acervo):
    achados, _, _ = acervo.pesquisar("resumo geral da receita")
    assert achados
    d = achados[0].para_dict()
    assert d["origem_do_texto"] == "reconhecido por OCR"
    assert "aviso_ocr" in d


def test_citacao_tem_o_que_vai_para_a_peca(acervo: Acervo):
    achados, _, _ = acervo.pesquisar("desapropriação")
    assert achados[0].citacao == "DOM de Mesquita, 13/05/2022, Nº 001485, p. 1"


def test_filtro_de_data_por_ano_inclui_o_ano_inteiro(acervo: Acervo):
    """data_max='2022' não pode excluir dezembro por comparação textual."""
    achados, _, _ = acervo.pesquisar("desapropriação", data_min="2022", data_max="2022")
    assert achados, "o recorte por ano cortou o próprio ano"


def test_filtro_de_data_exclui_fora_do_periodo(acervo: Acervo):
    achados, _, _ = acervo.pesquisar("desapropriação", data_min="2023-01-01")
    assert not achados


def test_ler_pagina_aceita_os_dois_formatos_de_data(acervo: Acervo):
    a = acervo.ler_pagina("13/05/2022", 1)
    b = acervo.ler_pagina("2022-05-13", 1)
    assert a and b and a["texto"] == b["texto"]


def test_ler_pagina_inexistente_devolve_none(acervo: Acervo):
    assert acervo.ler_pagina("13/05/2022", 99) is None


def test_listar_edicoes_ordena_da_mais_recente(acervo: Acervo):
    edicoes = acervo.listar_edicoes()
    assert [e.data for e in edicoes] == ["2024-03-27", "2022-05-13", "2020-01-02"]


def test_cobertura_declara_os_limites(acervo: Acervo):
    cob = acervo.cobertura()
    assert cob["primeira_edicao"] == "02/01/2020"
    assert cob["edicoes"] == 3
    assert any("Município" in l for l in cob["limites"])


@pytest.mark.parametrize("bruto,esperado", [
    ("2026", "2026-01-01"),
    ("24/07/2026", "2026-07-24"),
    ("2026-07-24", "2026-07-24"),
    ("07/2026", "2026-07-01"),
])
def test_normalizacao_de_data(bruto, esperado):
    assert _para_iso(bruto) == esperado


def test_aspas_do_usuario_viram_expressao_exata():
    expressao = montar_consulta_fts('contrato "dispensa de licitação"')
    assert '"dispensa de licitação"' in expressao


def test_consulta_so_de_palavras_vazias_nao_explode():
    assert montar_consulta_fts("o que é isso") == ""
