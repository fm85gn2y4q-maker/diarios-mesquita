"""Testes do reconhecimento de cabeçalho — a parte que pode mentir.

Perder um ato se percebe contando. Confundir citação com cabeçalho, não: cria
um ato que nunca existiu, ou atribui a um ato o texto de outro, e o resultado
sai bem formatado, com número e data. Cada caso aqui veio do acervo real, e os
marcados como REGRESSÃO são erros que a primeira versão cometeu.

    python -m pytest test_segmentar.py -q
"""

from __future__ import annotations

import pytest

from segmentar_atos import achar_cabecalho, segmentar_edicao


def cab(linha: str, anterior: str = "", proxima: str = "O PREFEITO DO MUNICÍPIO"):
    return achar_cabecalho(linha, anterior, proxima)


# -- reconhece o que é cabeçalho -----------------------------------------

@pytest.mark.parametrize("linha,especie,numero,ano", [
    ("PORTARIA Nº 678/2015.", "portaria", "678", 2015),
    ("DECRETO Nº 2343 DE 05 DE SETEMBRO DE 2018", "decreto", "2343", 2018),
    ("LEI Nº 1.206, DE 03 DE NOVEMBRO DE 2022", "lei", "1206", 2022),
    ("LEI COMPLEMENTAR Nº 50, DE 20 DE MAIO DE 2024", "lei_complementar", "50", 2024),
    ("RESOLUÇÃO Nº 019/2015", "resolucao", "19", 2015),
])
def test_cabecalhos_legitimos(linha, especie, numero, ano):
    achado = cab(linha)
    assert achado is not None, linha
    assert (achado["especie"], achado["numero"], achado["ano"]) == (especie, numero, ano)


def test_sigla_do_orgao_e_capturada():
    """Cada secretaria numera a sua portaria: sem o órgão, SEMED nº 1 e SEMUS
    nº 1 viram o mesmo ato."""
    achado = cab("PORTARIA SEMED Nº 023/2015")
    assert achado["orgao"] == "SEMED"
    assert achado["numero"] == "23"


def test_ordinal_seguido_de_ponto():
    """REGRESSÃO: `Nº.` traz o ordinal E o ponto; aceitar só um perdia 80 atos
    de 2015-2016, quando essa era a grafia corrente."""
    achado = cab("PORTARIA Nº. 001/2016.")
    assert achado is not None
    assert achado["numero"] == "1"


def test_numero_com_separador_de_milhar_nao_e_truncado():
    """REGRESSÃO herdada do acervo de legislação: com o quantificador errado,
    `LEI Nº 1.106` virava a Lei 110 — um ato que existe. Perda se percebe
    contando; troca de identidade, não."""
    achado = cab("LEI Nº 1.106, DE 20 DE DEZEMBRO DE 2019")
    assert achado["numero"] == "1106"


# -- recusa o que é citação ----------------------------------------------

def test_citacao_no_meio_de_artigo_nao_e_cabecalho():
    """REGRESSÃO: `Decreto 052/2001.` aparecia 5 vezes numa página, sempre
    entre "Art.1º … Decreto 052/2001." e "Art.2º …". A linha seguinte era
    "Art.2º", que satisfazia a confirmação — só a anterior denunciava."""
    achado = achar_cabecalho(
        "Decreto 052/2001.",
        anterior="Gonçalves Pereira, a execução dos serviços de acordo com o",
        proxima="Art.2° - Esta permissão passará a operar na data",
    )
    assert achado is None


@pytest.mark.parametrize("linha", [
    "Lei Municipal nº 1.229, de 28 de setembro de 2021.",
    "LEI FEDERAL Nº 8.666, DE 21 DE JUNHO DE 1993",
    "Decreto Estadual nº 45.600 de 2016.",
])
def test_qualificador_de_ente_denuncia_citacao(linha):
    """Cabeçalho nenhum diz de que ente o ato é — quem qualifica está citando."""
    assert cab(linha) is None


def test_caixa_mista_sem_confirmacao_abaixo_e_citacao():
    assert achar_cabecalho(
        "Lei nº 1.166/2021.", anterior="", proxima="5.1.1. Os interessados em votar"
    ) is None


def test_caixa_mista_com_promulgacao_abaixo_e_cabecalho():
    """A caixa mista não é descartada — é submetida a exigência extra."""
    achado = achar_cabecalho(
        "Resolução CMAS nº 004/2017", anterior="",
        proxima="O CONSELHO MUNICIPAL DE ASSISTÊNCIA SOCIAL, no uso",
    )
    assert achado is not None
    assert achado["orgao"] == "CMAS"


def test_linha_que_continua_a_oracao_nao_e_cabecalho():
    assert cab("COMBINADA COM A LEI COMPLEMENTAR Nº 004") is None


def test_texto_solto_sem_especie_conhecida_nao_vira_ato():
    for linha in ("LOTE 13", "Matricula. 11.007.652", "PMMQ0521/2015."):
        assert cab(linha) is None, linha


# -- segmentação da edição inteira ---------------------------------------

class _Pagina(dict):
    """sqlite3.Row aceita índice por nome; um dict basta para o teste."""


def _pagina(numero, texto, origem="pdf"):
    return _Pagina(pagina=numero, texto=texto, origem=origem)


def test_ato_atravessa_a_virada_da_pagina():
    paginas = [
        _pagina(1, "PORTARIA Nº 100/2024\nNomear FULANO DE TAL para o cargo"),
        _pagina(2, "em comissão de Assessor, a partir desta data.\nMesquita, 2024."),
    ]
    atos = segmentar_edicao(paginas)
    assert len(atos) == 1
    assert (atos[0]["pagina_inicial"], atos[0]["pagina_final"]) == (1, 2)
    assert "Assessor" in atos[0]["texto"]


def test_dois_atos_na_mesma_pagina_nao_se_misturam():
    """É o defeito que a segmentação existe para evitar: sem ela, 'fiscalizar
    o contrato' responderia sob o cabeçalho do decreto."""
    paginas = [_pagina(1,
        "DECRETO Nº 3204/2022\n"
        "“Declara de utilidade pública para fins de desapropriação.”\n"
        "PORTARIA Nº 210/2022\n"
        "Designar servidor para fiscalizar o contrato.")]
    atos = segmentar_edicao(paginas)
    assert [a["especie"] for a in atos] == ["decreto", "portaria"]
    assert "fiscalizar" not in atos[0]["texto"]
    assert "desapropriação" not in atos[1]["texto"]


def test_ementa_entre_aspas_e_extraida():
    paginas = [_pagina(1,
        "DECRETO Nº 3204/2022\n“Declara de utilidade pública o imóvel referido.”\nO PREFEITO")]
    atos = segmentar_edicao(paginas)
    assert atos[0]["ementa"] == "Declara de utilidade pública o imóvel referido."


def test_marca_de_retificacao_no_corpo_do_ato():
    paginas = [_pagina(1,
        "PORTARIA Nº 026/2024\n*Republicação por haver saído com incorreção.\nTornar público")]
    atos = segmentar_edicao(paginas)
    assert atos[0]["tem_retificacao"] == 1


def test_edicao_sem_ato_reconhecido_devolve_lista_vazia():
    """3,8% das edições são só balancete ou extrato — devolver vazio é o certo,
    não inventar um ato."""
    paginas = [_pagina(1, "EXTRATO DE CONTRATO\nContratada: EMPRESA LTDA\nValor: R$ 10,00")]
    assert segmentar_edicao(paginas) == []


def test_origem_mista_quando_o_ato_cruza_pagina_digitalizada():
    paginas = [
        _pagina(1, "PORTARIA Nº 375/2020\nProcessar a republicação do relatório"),
        _pagina(2, "RESUMO GERAL DA RECEITA 2020", origem="ocr_local"),
    ]
    assert segmentar_edicao(paginas)[0]["origem_texto"] == "misto"
