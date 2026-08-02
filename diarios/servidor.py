"""Servidor MCP do Diário Oficial de Mesquita/RJ.

Fala os dois transportes porque os clientes divergem: o Claude conversa por
stdio com um processo local, enquanto o ChatGPT só aceita servidor remoto por
HTTP — e exige as ferramentas `search` e `fetch` com essa exata assinatura.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .acervo import Acervo, PADRAO_RETIFICACAO

_LOCAIS = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*"]


def seguranca_de_transporte(dominios: list[str] | None) -> TransportSecuritySettings:
    """Monta a política de Host/Origin aceitos.

    O SDK bloqueia por padrão qualquer Host que não seja local — é proteção
    contra DNS rebinding, e sem ela um site malicioso poderia falar com o
    servidor pelo navegador da vítima. Servir por um endereço público exige
    declarar o domínio aqui; não há curinga, a comparação é exata.
    """
    hosts = list(_LOCAIS)
    origens = [f"http://{h}" for h in _LOCAIS if "*" not in h]

    for dominio in dominios or []:
        limpo = dominio.strip().removeprefix("https://").removeprefix("http://")
        limpo = limpo.rstrip("/")
        if not limpo:
            continue
        hosts += [limpo, f"{limpo}:*"]
        origens.append(f"https://{limpo}")

    if dominios:
        origens += ["https://chatgpt.com", "https://chat.openai.com"]

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origens,
    )


INSTRUCOES = """
Diário Oficial do Município de Mesquita/RJ, de 15/07/2015 em diante, coletado
do Portal da Transparência da Prefeitura. Traz o que o Município publicou:
decretos, portarias, leis sancionadas, extratos de contrato, editais, avisos de
licitação, atas de registro de preços e nomeações.

Como responder ao advogado:
- Entregue a publicação e a análise, não o funcionamento da ferramenta. Não
  cite nomes de tools, identificadores internos nem estrutura de URL.
- Cite no formato do campo `citacao` — é a referência que vai para a peça.
- Ofereça sempre o `url_pdf` junto da citação: é por ele que se confere o que
  foi de fato publicado. Apresente como "[Inteiro teor](url)", sem comentar o
  endereço.
- Chame `cobertura_do_acervo` quando precisar saber o alcance da base, e
  declare os limites que afetarem a resposta.

A REGRA QUE NÃO PODE SER QUEBRADA: O QUE FOI PUBLICADO PODE TER SIDO REFEITO

Num acervo de jurisprudência o risco é a proveniência; num de legislação, a
vigência. Aqui é a **republicação**. O Município publica o ato, percebe o erro
e o republica dias depois — "*Republicado por haver saído com incorreção*" é
frase corrente nestas páginas. Medido nesta base: 452 menções a republicação e
391 a errata ou retificação em 996 edições examinadas. Não é exceção; é rotina.

A busca textual devolve a versão errada e a corrigida com a mesma confiança, e
**nada no texto da primeira avisa que ela foi refeita**.

Por isso:
- Quando um resultado trouxer `aviso_retificacao`, aquela página contém marca
  de errata, retificação ou republicação. Leia antes de usar: pode alcançar o
  ato que interessa, pode alcançar outro da mesma página.
- Achando um ato relevante, **procure republicação posterior** antes de citá-lo
  — pesquise o número do ato em datas seguintes. Um decreto de março pode ter
  sido republicado em abril com outro texto.
- Diga "localizei a publicação de tal data", nunca "o texto do ato é este".
  A segunda frase promete que não houve republicação, e esta base não sustenta
  essa promessa.

DUAS UNIDADES: O ATO E A PÁGINA. SAIBA QUAL VOCÊ ESTÁ USANDO

Medido: 89,6% das edições trazem mais de um ato, mediana de 6 por edição, uma
delas com 106. Uma página pode conter o fim de uma portaria, um decreto inteiro
e o começo de um extrato de contrato.

Por isso há duas buscas, e escolher errado gera erro de sentido:

- `pesquisar_atos` devolve o **ato delimitado** — portaria, decreto, lei, lei
  complementar e resolução, 17.755 deles, com número, órgão emissor, ementa e
  o intervalo de páginas. Use esta quando a pergunta for sobre um ato.
- `pesquisar_publicacoes` devolve a **página**. Use quando `pesquisar_atos` não
  achar, ou quando a matéria não for um ato numerado.

**O que NÃO está segmentado, e é muita coisa:** extrato de contrato, edital,
aviso de licitação e ata de registro de preços não têm cabeçalho numerado no
padrão reconhecido. Existem no acervo e são achados por `pesquisar_publicacoes`
— nunca por `pesquisar_atos`. Não encontrar um extrato entre os atos não é
prova de que ele não foi publicado.

Trabalhando com página, o erro mais fácil continua sendo atribuir ao ato do
cabeçalho um trecho que é do ato vizinho: confirme com `ler_pagina`.

ANTES DE CITAR UM ATO, CHAME `historico_do_ato`

Ele devolve todas as publicações daquele número — mais de uma significa
republicação — e os atos posteriores que o citam, que é onde moram a errata, a
alteração e a revogação. A errata quase nunca repete o cabeçalho do ato que
corrige; ela diz "no Decreto nº 2.763 … onde se lê … leia-se". Só a busca pela
menção acha isso.

DUAS ORIGENS DE TEXTO, DUAS CONFIANÇAS

- `texto nativo do PDF`: o que a Prefeitura gerou. Fiel.
- `reconhecido por OCR`: 4.113 das 27.921 páginas são digitalização, e passaram
  por reconhecimento óptico. O corpo do texto sai bom, mas cabeçalho estilizado
  vira "2OI6", e número em tabela é onde o OCR mais erra.

Trecho marcado com `aviso_ocr` **não se transcreve numa peça sem conferir o
PDF**. Pode-se dizer que a matéria consta da edição; não se pode garantir a
literalidade do que está escrito.

O QUE ESTA BASE NÃO TEM

- Nada antes de 15/07/2015 — é onde o portal começa, não onde o Município
  começou a publicar.
- Só o Diário Oficial **do Município**. Publicação de Mesquita no Diário do
  Estado, no da União ou em jornal de grande circulação está fora daqui, e
  algumas matérias exigem justamente essas.
- Não há texto consolidado nem acompanhamento de vigência. Quem responde sobre
  a legislação municipal em vigor é o acervo de legislação, não este.

Não encontrando algo, antes de dizer que não foi publicado: tente outra
formulação (a busca é literal), amplie o intervalo de datas, e verifique na
cobertura se o período pedido existe na base.
"""


def _caminho_padrao() -> Path:
    do_ambiente = os.environ.get("DIARIOS_BANCO")
    if do_ambiente:
        return Path(do_ambiente)
    return Path.home() / "Mesquita_Diarios_Oficiais" / "acervo.db"


def construir(
    banco: str | Path | None = None,
    dominios: list[str] | None = None,
    url_publica: str | None = None,
    segredo_oauth: str | None = None,
    **ajustes: Any,
) -> FastMCP:
    acervo = Acervo(banco or _caminho_padrao())

    # O ChatGPT recusa servidor MCP sem OAuth; o Claude conecta sem. O fluxo só
    # é montado quando há URL pública, porque os metadados precisam apontar
    # para endereços que o cliente alcance.
    if url_publica:
        from .autenticacao import montar

        provedor, definicoes = montar(url_publica, segredo_oauth)
        ajustes |= {"auth_server_provider": provedor, "auth": definicoes}

    mcp = FastMCP(
        "diarios-mesquita",
        instructions=INSTRUCOES,
        transport_security=seguranca_de_transporte(dominios),
        **ajustes,
    )

    @mcp.tool()
    def pesquisar_publicacoes(
        consulta: str,
        data_min: str | None = None,
        data_max: str | None = None,
        limite: int = 10,
    ) -> dict[str, Any]:
        """Procura no texto das páginas do Diário Oficial de Mesquita.

        Busca sem sensibilidade a acento ("licitacao" acha "licitação") e
        combina os termos com E. Para expressão exata, use aspas dentro da
        própria consulta: 'contrato "dispensa de licitação"'.

        Args:
            consulta: palavras ou expressão a procurar.
            data_min: data inicial (24/07/2026, 2026-07-24 ou 2026).
            data_max: data final, nos mesmos formatos.
            limite: quantos trechos devolver (máximo 30).
        """
        achados, parcial, expressao = acervo.pesquisar(
            consulta, data_min=data_min, data_max=data_max, limite=limite
        )
        if not achados:
            observacao = (
                "Nada com esta formulação. A busca é literal: o Município pode "
                "nomear a mesma coisa com outras palavras (\"cessão de uso\" e "
                "\"permissão de uso\", \"auxílio\" e \"subvenção\"). Tente ao "
                "menos uma variante, e confira o período em `cobertura_do_acervo`, "
                "antes de concluir que não houve publicação."
            )
        elif parcial:
            observacao = (
                "Nenhuma página reunia todos os termos; estas atendem a parte "
                "deles, ordenadas por relevância."
            )
        else:
            observacao = None

        com_marca = sum(1 for a in achados if a.tem_marca_de_retificacao)
        return {
            "consulta": consulta,
            "expressao_executada": expressao,
            "quantidade": len(achados),
            "correspondencia_parcial": parcial,
            "resultados": [a.para_dict() for a in achados],
            "observacao": observacao,
            "lembrete": (
                "O trecho pode pertencer a outro ato da mesma página — confirme "
                "com `ler_pagina` antes de atribuí-lo. E procure republicação "
                "posterior antes de citar."
                + (f" {com_marca} destes resultados têm marca de retificação."
                   if com_marca else "")
            ),
        }

    @mcp.tool()
    def ler_pagina(data: str, pagina: int) -> dict[str, Any]:
        """Devolve o texto inteiro de uma página, para ver onde o ato começa e acaba.

        É o passo obrigatório entre achar um trecho e atribuí-lo a um ato: a
        página do diário costuma abrigar vários atos, e o cabeçalho no alto não
        governa tudo o que vem abaixo.

        Args:
            data: data da edição (24/07/2026 ou 2026-07-24).
            pagina: número da página dentro daquela edição.
        """
        achado = acervo.ler_pagina(data, pagina)
        if achado is None:
            return {
                "encontrado": False,
                "observacao": (
                    f"Não há página {pagina} na edição de {data}. Confira a data "
                    "com `listar_edicoes` — pode não ter havido publicação nesse "
                    "dia, ou a edição pode ter menos páginas."
                ),
            }
        achado["encontrado"] = True
        if PADRAO_RETIFICACAO.search(achado["texto"]):
            achado["aviso_retificacao"] = (
                "Há marca de errata, retificação ou republicação nesta página."
            )
        if "OCR" in achado["origem_do_texto"]:
            achado["aviso_ocr"] = (
                "Página reconhecida por OCR. Não transcreva literalmente sem "
                "conferir o PDF."
            )
        return achado

    @mcp.tool()
    def listar_edicoes(
        data_min: str | None = None,
        data_max: str | None = None,
        limite: int = 30,
    ) -> dict[str, Any]:
        """Lista as edições publicadas num período.

        Serve para saber se houve publicação em determinado dia — útil para
        contagem de prazo, e para distinguir "não achei" de "não houve edição".

        Args:
            data_min: data inicial (24/07/2026, 2026-07-24 ou 2026).
            data_max: data final, nos mesmos formatos.
            limite: quantas edições devolver (máximo 200).
        """
        achados = acervo.listar_edicoes(data_min, data_max, limite)
        return {
            "quantidade": len(achados),
            "edicoes": [e.para_dict() for e in achados],
            "observacao": (
                None if achados else
                "Nenhuma edição neste período. Confira o alcance da base em "
                "`cobertura_do_acervo`."
            ),
            "lembrete": (
                "A ausência de edição num dia não significa que o prazo não "
                "correu: a contagem depende da publicação, e há edição "
                "extraordinária fora do calendário regular."
            ),
        }

    @mcp.tool()
    def pesquisar_atos(
        consulta: str,
        especie: str | None = None,
        orgao: str | None = None,
        ano_min: int | None = None,
        ano_max: int | None = None,
        limite: int = 10,
    ) -> dict[str, Any]:
        """Procura o ATO — a portaria, o decreto, a lei —, não a página.

        Prefira esta a `pesquisar_publicacoes` quando a pergunta for sobre um
        ato ("que decreto tratou de desapropriação?"): o resultado já vem
        delimitado, com ementa e número, sem o risco de o trecho pertencer ao
        ato vizinho da mesma página.

        Args:
            consulta: palavras ou expressão a procurar.
            especie: portaria, decreto, lei, lei_complementar ou resolucao.
            orgao: sigla da secretaria emissora (SEMED, SEMUS, DPMM, CMAS…).
            ano_min: ano mais antigo aceito.
            ano_max: ano mais recente aceito.
            limite: quantos atos devolver (máximo 30).
        """
        achados, parcial, expressao = acervo.pesquisar_atos(
            consulta, especie=especie, orgao=orgao,
            ano_min=ano_min, ano_max=ano_max, limite=limite,
        )
        if not achados:
            observacao = (
                "Nada entre os atos segmentados. Duas causas possíveis, e elas "
                "pedem respostas diferentes: a matéria pode estar num extrato de "
                "contrato, edital ou aviso de licitação — que NÃO são "
                "segmentados —, e aí `pesquisar_publicacoes` acha; ou a "
                "formulação pode estar errada, e aí vale tentar uma variante."
            )
        elif parcial:
            observacao = (
                "Nenhum ato reunia todos os termos; estes atendem a parte deles."
            )
        else:
            observacao = None
        return {
            "consulta": consulta,
            "expressao_executada": expressao,
            "quantidade": len(achados),
            "correspondencia_parcial": parcial,
            "resultados": achados,
            "observacao": observacao,
            "lembrete": (
                "Antes de citar qualquer um destes, chame `historico_do_ato` "
                "com a espécie e o número: republicação e errata são rotina "
                "nesta base, e não aparecem no texto do ato original."
            ),
        }

    @mcp.tool()
    def historico_do_ato(
        especie: str, numero: str, ano: int | None = None, limite: int = 20,
    ) -> dict[str, Any]:
        """Reúne tudo o que o Diário publicou sobre um ato — inclusive o que o refez.

        É a ferramenta central desta base. Devolve duas coisas:

        1. as publicações do próprio ato (mais de uma significa republicação);
        2. os atos posteriores que o citam — onde estão a errata, a alteração
           e a revogação, que nunca repetem o cabeçalho do ato corrigido.

        Args:
            especie: portaria, decreto, lei, lei_complementar ou resolucao.
            numero: número do ato (com ou sem separador de milhar).
            ano: ano do ato, quando conhecido.
            limite: quantas menções devolver (máximo 50).
        """
        publicacoes = acervo.localizar_ato(especie, numero, ano)
        mencoes = acervo.mencoes_ao_ato(especie, numero, ano, limite=limite)
        chave = {(p["publicado_em"], p["paginas"]) for p in publicacoes}
        posteriores = [m for m in mencoes if (m["publicado_em"], m["paginas"]) not in chave]

        if not publicacoes:
            aviso = (
                "Não localizei publicação deste ato entre os segmentados. Isso "
                "NÃO significa que ele não existe: pode estar em edição de "
                "página digitalizada, ou o número pode divergir. Procure por "
                "`pesquisar_publicacoes` antes de afirmar que não foi publicado."
            )
        elif len(publicacoes) > 1:
            aviso = (
                f"ATENÇÃO: este ato aparece em {len(publicacoes)} publicações "
                "diferentes. Leia todas antes de citar — a posterior costuma ser "
                "a republicação corrigida, e é ela que vale."
            )
        else:
            aviso = (
                "Uma única publicação localizada. Ainda assim, veja as menções "
                "posteriores: a alteração vem em ato próprio, não neste texto."
            )
        return {
            "publicacoes_do_ato": publicacoes,
            "mencoes_posteriores": posteriores,
            "aviso": aviso,
            "limite_declarado": (
                "As menções são procuradas entre os atos segmentados "
                "(portarias, decretos, leis, resoluções). Errata publicada "
                "dentro de um edital ou extrato não é alcançada aqui."
            ),
        }

    @mcp.tool()
    def cobertura_do_acervo() -> dict[str, Any]:
        """Diz o que esta base alcança e o que ela não alcança.

        Chame antes de afirmar que algo não foi publicado — a ausência aqui
        pode ser ausência da base, não do Diário.
        """
        return acervo.cobertura()

    # -- exigidas pelo conector do ChatGPT --------------------------------

    @mcp.tool()
    def search(query: str) -> dict[str, Any]:
        """Procura no Diário Oficial de Mesquita e devolve os trechos achados.

        Args:
            query: o que procurar.
        """
        achados, _, _ = acervo.pesquisar(query, limite=10)
        return {
            "results": [
                {
                    "id": f"{a.data}#{a.pagina}",
                    "title": a.citacao,
                    "text": a.achado,
                    "url": a.url,
                }
                for a in achados
            ]
        }

    @mcp.tool()
    def fetch(id: str) -> dict[str, Any]:
        """Devolve o texto inteiro de uma página achada por `search`.

        Args:
            id: identificador devolvido por `search`, no formato data#pagina.
        """
        data, _, pagina = id.partition("#")
        achado = acervo.ler_pagina(data, int(pagina or 1))
        if achado is None:
            return {"id": id, "title": "não encontrado", "text": "", "url": ""}
        return {
            "id": id,
            "title": f"DOM de Mesquita, {achado['data']}, p. {achado['pagina']}",
            "text": achado["texto"],
            "url": achado["url_pdf"],
            "metadata": {"origem_do_texto": achado["origem_do_texto"]},
        }

    return mcp
