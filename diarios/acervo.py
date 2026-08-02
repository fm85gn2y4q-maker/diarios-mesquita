"""Camada de dados sobre `acervo.db` — o Diário Oficial de Mesquita/RJ.

O banco é construído fora daqui, pelos scripts em `~/Mesquita_Diarios_Oficiais`
(baixar → extrair → OCR). Este módulo só consulta, e é o único lugar que sabe
SQL: o servidor MCP acima dele lida com o que dizer ao advogado, não com como
o dado está guardado.

Duas particularidades desta base, que moldam tudo o que vem a seguir:

1. **Um diário não é um documento, é um continente.** Medido no acervo:
   89,6% das edições trazem mais de um ato, mediana de 6, uma delas com 106.
   Achar "a edição de 24/07/2026" não é achar o ato — é achar onde ele mora.

2. **A parte reconhecida por máquina não vale o mesmo que a nativa.** 4.113 das
   27.921 páginas vieram de digitalização e passaram por OCR. O texto é bom,
   mas cabeçalho estilizado sai como "2OI6". Toda passagem devolvida diz de
   qual das duas origens veio, porque transcrever OCR numa peça sem conferir o
   PDF é como citar de memória.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_OPERADORES = {"and", "or", "not", "near"}

# Quem consulta é um modelo, que repassa a pergunta inteira do advogado ("saiu
# alguma coisa sobre desapropriação na Chatuba?"). Com os termos ligados por E,
# um "alguma" zera o resultado. Nenhuma destas palavras distingue uma
# publicação de outra.
_VAZIAS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos", "e",
    "em", "entre", "essa", "esse", "esta", "este", "eh", "existe", "existem",
    "foi", "ha", "isso", "meu", "minha", "na", "nas", "no", "nos", "num", "numa",
    "o", "os", "ou", "para", "pela", "pelo", "por", "pode", "podem", "posso",
    "qual", "quais", "quando", "que", "quem", "se", "sem", "ser", "sao", "seu",
    "sob", "sobre", "sua", "tem", "ter", "um", "uma", "uns", "umas", "alguma",
    "algum", "saiu", "publicado", "publicada", "diario", "oficial",
    # Ficam de fora de propósito palavras que PARECEM de formulação mas são o
    # objeto da pergunta: "nomeação", "exoneração", "prazo", "contrato".
}

ROTULOS_ESPECIE = {
    "portaria": "Portaria", "decreto": "Decreto", "lei": "Lei",
    "lei_complementar": "Lei Complementar", "resolucao": "Resolução",
}

ORIGENS = {
    "pdf": "texto nativo do PDF",
    "ocr_local": "reconhecido por OCR",
    "ocr_sem_texto": "página sem texto (carimbo, assinatura ou branco)",
    "vazia": "ainda não processada",
}

# O que o diário chama de retificação. Medido: 391 ocorrências de errata ou
# retificação e 452 de "republicado" em 996 edições examinadas — nesta base a
# republicação é rotina, não exceção.
PADRAO_RETIFICACAO = re.compile(
    r"\b(errata|retifica[çc][ãa]o|retificad[oa]|republicad[oa]|"
    r"republica[çc][ãa]o|torna[- ]se sem efeito|sem efeito)\b",
    re.IGNORECASE,
)


# Separar quem ASSINA de quem é OBJETO do ato. Medido nesta base: o nome do
# Prefeito casa em 750 atos, e em 748 ele é o signatário — buscar por nome de
# autoridade devolve, quase inteiro, o que ela despachou, e não o que lhe
# aconteceu. O sinal que funciona é o verbo dispositivo ANTES do nome
# ("Exonerar a pedido, FULANO…"); o contrário — cargo na linha seguinte ao
# nome — é bloco de assinatura.
VERBO_DISPOSITIVO = re.compile(
    r"\b(exonerar|exonerad[oa]s?|nomear|nomead[oa]s?|designar|designad[oa]s?|"
    r"conceder|conced[ei]d[oa]s?|contratar|contratad[oa]s?|admitir|admitid[oa]s?|"
    r"remover|promover|rescindir|aposentar|tornar sem efeito|lotar|transferir|"
    r"prorrogar|instaurar|suspender|advertir|penalizar)\b",
    re.IGNORECASE,
)
CARGO_EM_ASSINATURA = re.compile(
    r"^(procurador|procuradora|secret[áa]ri[oa]|prefeito|vice-prefeito|diretor|"
    r"diretora|presidente|chefe|coordenador|coordenadora|membro|titular|"
    r"suplente|assessor|assessora|subsecret[áa]ri[oa]|controlador)",
    re.IGNORECASE,
)
PAPEIS = {
    "objeto": "a pessoa é objeto do ato (nomeada, exonerada, designada…)",
    "assinatura": "a pessoa assina ou é citada como autoridade",
    "indefinido": "não foi possível classificar — leia o ato",
}


def papel_no_ato(texto: str, nome: str) -> str:
    """Classifica, por heurística, o papel da pessoa no ato.

    É heurística e a resposta diz isso: 25% dos casos medidos ficam em
    `indefinido`, e esses não podem ser descartados em silêncio — some-los
    seria repetir, de outro jeito, o erro do corte mudo.
    """
    # O token mais LONGO, não o último: "da Costa" é sobrenome corrente e casa
    # na primeira linha errada do ato, enquanto "Menegatti" identifica. Foi o
    # que fez a primeira versão classificar 167 atos e não achar nenhum objeto.
    particulas = {"da", "de", "do", "das", "dos", "e", "dr", "dra"}
    alvo = [t for t in sem_acento(nome).split() if t not in particulas and len(t) > 3]
    if not alvo:
        return "indefinido"
    chave = max(alvo, key=len)

    linhas = texto.splitlines()
    achou_assinatura = False
    # Todas as ocorrências, não a primeira: num ato que exonera A e é assinado
    # por B, o nome de A pode aparecer depois do de B na linearização das
    # colunas. Bastando uma ocorrência regida por verbo dispositivo, é objeto.
    for i, linha in enumerate(linhas):
        if chave not in sem_acento(linha):
            continue
        contexto = " ".join(linhas[max(0, i - 1):i + 1])
        corte = sem_acento(contexto).find(chave)
        antes = contexto[:corte] if corte > 0 else contexto
        if VERBO_DISPOSITIVO.search(antes[-160:]):
            return "objeto"
        seguinte = linhas[i + 1].strip() if i + 1 < len(linhas) else ""
        if CARGO_EM_ASSINATURA.match(seguinte):
            achou_assinatura = True
    return "assinatura" if achou_assinatura else "indefinido"


def sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    ).lower()


def _trecho_ao_redor(texto: str, nome: str, margem: int = 220) -> str:
    """O pedaço do ato em que o nome aparece, para leitura direta."""
    particulas = {"da", "de", "do", "das", "dos", "e", "dr", "dra"}
    alvo = [t for t in sem_acento(nome).split() if t not in particulas and len(t) > 3]
    plano = " ".join(texto.split())
    if not alvo:
        return plano[:2 * margem]
    corte = sem_acento(plano).find(max(alvo, key=len))
    if corte < 0:
        return plano[:2 * margem]
    inicio = max(0, corte - margem)
    return ("… " if inicio else "") + plano[inicio:corte + margem] + " …"


def montar_consulta_fts(texto: str, operador: str = "AND") -> str:
    """Traduz linguagem natural para a sintaxe do FTS5.

    Cada termo vai entre aspas para que pontuação e operadores acidentais não
    quebrem a consulta: o `MATCH` rejeita a expressão inteira com erro de
    sintaxe, e o advogado só veria "a busca falhou". Trechos que ele mesmo
    aspeou são preservados como expressão exata.
    """
    partes: list[str] = []
    for frase in re.findall(r'"([^"]+)"', texto):
        limpa = frase.replace('"', " ").strip()
        if limpa:
            partes.append(f'"{limpa}"')

    resto = re.sub(r'"[^"]*"', " ", texto)
    livres = re.findall(r"[\wÀ-ɏ]+", resto)
    uteis = [
        t for t in livres
        if len(t) > 1 and sem_acento(t) not in _VAZIAS and sem_acento(t) not in _OPERADORES
    ]
    # Número de ato ("449/2026") é o termo mais discriminante que existe aqui;
    # o `re` acima já o quebrou em 449 e 2026, e ambos servem.
    partes += [f'"{t}"' for t in uteis]
    return f" {operador} ".join(partes)


@dataclass
class Passagem:
    """Um trecho encontrado, com o endereço que se leva para a peça."""

    data: str
    numero: str
    descricao: str
    pagina: int
    paginas: int
    origem: str
    arquivo: str
    url: str
    achado: str
    tem_marca_de_retificacao: bool = False
    termos_encontrados: list[str] = field(default_factory=list)

    @property
    def citacao(self) -> str:
        rotulo = self.descricao or f"nº {self.numero}"
        return f"DOM de Mesquita, {_data_br(self.data)}, {rotulo}, p. {self.pagina}"

    def para_dict(self) -> dict[str, Any]:
        d = {
            "citacao": self.citacao,
            "data": _data_br(self.data),
            "edicao": self.descricao or self.numero,
            "pagina": self.pagina,
            "de_paginas": self.paginas,
            "trecho": self.achado,
            "origem_do_texto": ORIGENS.get(self.origem, self.origem),
            "url_pdf": self.url,
        }
        if self.origem.startswith("ocr"):
            d["aviso_ocr"] = (
                "Trecho reconhecido por OCR. Confira no PDF antes de transcrever."
            )
        if self.tem_marca_de_retificacao:
            d["aviso_retificacao"] = (
                "Esta página contém marca de errata, retificação ou republicação. "
                "Verifique se alcança o ato que você pretende citar."
            )
        return d


@dataclass
class Edicao:
    data: str
    numero: str
    descricao: str
    paginas: int
    arquivo: str
    url: str

    def para_dict(self) -> dict[str, Any]:
        return {
            "data": _data_br(self.data),
            "edicao": self.descricao or self.numero,
            "paginas": self.paginas,
            "url_pdf": self.url,
        }


def _data_br(iso: str) -> str:
    try:
        a, m, d = iso.split("-")
        return f"{d}/{m}/{a}"
    except ValueError:
        return iso


def _para_iso(data: str | None, *, fim: bool = False) -> str | None:
    """Aceita 24/07/2026, 2026-07-24 e 2026 — o modelo manda qualquer um.

    `fim=True` expande o que veio incompleto para o último instante do período,
    para que `data_max="2026"` inclua dezembro em vez de excluir o ano inteiro
    (a comparação é textual: "2026-07-24" > "2026").
    """
    if not data:
        return None
    data = data.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
        return data
    achado = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", data)
    if achado:
        d, m, a = achado.groups()
        return f"{a}-{int(m):02d}-{int(d):02d}"
    if re.fullmatch(r"\d{4}", data):
        return f"{data}-12-31" if fim else f"{data}-01-01"
    achado = re.fullmatch(r"(\d{1,2})/(\d{4})", data)  # "07/2026"
    if achado:
        m, a = achado.groups()
        return f"{a}-{int(m):02d}-31" if fim else f"{a}-{int(m):02d}-01"
    return data


class Acervo:
    def __init__(self, banco: str | Path) -> None:
        self.caminho = Path(banco)
        if not self.caminho.exists():
            raise FileNotFoundError(f"acervo não encontrado: {self.caminho}")
        self.conexao = sqlite3.connect(
            f"file:{self.caminho}?mode=ro", uri=True, check_same_thread=False
        )
        self.conexao.row_factory = sqlite3.Row

    def fechar(self) -> None:
        self.conexao.close()

    # -- busca ------------------------------------------------------------

    def pesquisar(
        self,
        consulta: str,
        *,
        data_min: str | None = None,
        data_max: str | None = None,
        limite: int = 10,
        deslocamento: int = 0,
        ordenar: str = "relevancia",
    ) -> tuple[list[Passagem], bool, str, int]:
        """Procura no texto das páginas. Devolve também o TOTAL de ocorrências.

        Exige todos os termos; não achando, repete aceitando qualquer um.
        Devolver a página mais próxima avisando que a correspondência foi
        parcial é melhor do que devolver vazio porque a pergunta trazia uma
        palavra a mais.

        O total não é enfeite. Medido nesta base: "IPTU" casa em 3.385 páginas
        e um nome de procurador em 930. Devolvendo 30 sem dizer quantas
        existem, o advogado lê "estas são as ocorrências" onde o certo é
        "estas são trinta de novecentas e trinta" — e contar custa 2 ms.
        """
        expressao = ""
        for operador in ("AND", "OR"):
            expressao = montar_consulta_fts(consulta, operador)
            if not expressao:
                return [], False, "", 0
            achados = self._consultar(expressao, data_min, data_max, limite,
                                      deslocamento, ordenar)
            if achados:
                total = self._contar("pagina_fts", expressao, data_min, data_max)
                return achados, operador == "OR", expressao, total
        return [], False, expressao, 0

    def _contar(self, tabela, expressao, data_min, data_max) -> int:
        alvo = "pagina" if tabela == "pagina_fts" else "ato"
        sql = [f"SELECT COUNT(*) FROM {tabela} f",
               f"JOIN {alvo} x ON x.id = f.rowid",
               "JOIN edicao e ON e.id = x.edicao_id",
               f"WHERE {tabela} MATCH ?"]
        parametros: list[Any] = [expressao]
        if data_min:
            sql.append("AND e.data >= ?")
            parametros.append(_para_iso(data_min))
        if data_max:
            sql.append("AND e.data <= ?")
            parametros.append(_para_iso(data_max, fim=True))
        return self.conexao.execute(" ".join(sql), parametros).fetchone()[0]

    def _consultar(self, expressao, data_min, data_max, limite, deslocamento=0,
                   ordenar="relevancia") -> list[Passagem]:
        sql = [
            "SELECT e.data, e.numero, e.descricao, e.paginas, e.arquivo, e.url,",
            "       p.pagina, p.origem, p.texto,",
            "       snippet(pagina_fts, 0, '', '', ' … ', 28) AS achado",
            "FROM pagina_fts f",
            "JOIN pagina p ON p.id = f.rowid",
            "JOIN edicao e ON e.id = p.edicao_id",
            "WHERE pagina_fts MATCH ?",
        ]
        parametros: list[Any] = [expressao]
        if data_min:
            sql.append("AND e.data >= ?")
            parametros.append(_para_iso(data_min))
        if data_max:
            sql.append("AND e.data <= ?")
            parametros.append(_para_iso(data_max, fim=True))
        ordem = ("e.data DESC, p.pagina" if ordenar == "data"
                 else "bm25(pagina_fts), e.data DESC")
        sql.append(f"ORDER BY {ordem} LIMIT ? OFFSET ?")
        parametros.append(max(1, min(int(limite), 30)))
        parametros.append(max(0, int(deslocamento)))

        linhas = self.conexao.execute(" ".join(sql), parametros).fetchall()
        return [
            Passagem(
                data=l["data"], numero=l["numero"], descricao=l["descricao"],
                pagina=l["pagina"], paginas=l["paginas"], origem=l["origem"],
                arquivo=l["arquivo"], url=l["url"], achado=" ".join(l["achado"].split()),
                tem_marca_de_retificacao=bool(PADRAO_RETIFICACAO.search(l["texto"])),
            )
            for l in linhas
        ]

    # -- leitura ----------------------------------------------------------

    def ler_pagina(self, data: str, pagina: int) -> dict[str, Any] | None:
        linha = self.conexao.execute(
            """SELECT e.data, e.numero, e.descricao, e.paginas, e.url,
                      p.pagina, p.texto, p.origem
               FROM pagina p JOIN edicao e ON e.id = p.edicao_id
               WHERE e.data = ? AND p.pagina = ?""",
            (_para_iso(data), int(pagina)),
        ).fetchone()
        if linha is None:
            return None
        return {
            "data": _data_br(linha["data"]),
            "edicao": linha["descricao"] or linha["numero"],
            "pagina": linha["pagina"],
            "de_paginas": linha["paginas"],
            "origem_do_texto": ORIGENS.get(linha["origem"], linha["origem"]),
            "texto": linha["texto"],
            "url_pdf": linha["url"],
        }

    def listar_edicoes(
        self, data_min: str | None = None, data_max: str | None = None,
        limite: int = 30,
    ) -> list[Edicao]:
        sql = ["SELECT * FROM edicao WHERE 1=1"]
        parametros: list[Any] = []
        if data_min:
            sql.append("AND data >= ?")
            parametros.append(_para_iso(data_min))
        if data_max:
            sql.append("AND data <= ?")
            parametros.append(_para_iso(data_max, fim=True))
        sql.append("ORDER BY data DESC LIMIT ?")
        parametros.append(max(1, min(int(limite), 200)))
        return [
            Edicao(data=l["data"], numero=l["numero"], descricao=l["descricao"],
                   paginas=l["paginas"], arquivo=l["arquivo"], url=l["url"])
            for l in self.conexao.execute(" ".join(sql), parametros)
        ]

    # -- atos -------------------------------------------------------------

    def pesquisar_atos(
        self,
        consulta: str,
        *,
        especie: str | None = None,
        orgao: str | None = None,
        ano_min: int | None = None,
        ano_max: int | None = None,
        limite: int = 10,
        deslocamento: int = 0,
        ordenar: str = "relevancia",
    ) -> tuple[list[dict], bool, str, int]:
        expressao = ""
        for operador in ("AND", "OR"):
            expressao = montar_consulta_fts(consulta, operador)
            if not expressao:
                return [], False, "", 0
            achados = self._consultar_atos(
                expressao, especie, orgao, ano_min, ano_max, limite,
                deslocamento, ordenar
            )
            if achados:
                total = self._contar_atos(expressao, especie, orgao, ano_min, ano_max)
                return achados, operador == "OR", expressao, total
        return [], False, expressao, 0

    def _contar_atos(self, expressao, especie, orgao, ano_min, ano_max) -> int:
        sql = ["SELECT COUNT(*) FROM ato_fts f JOIN ato a ON a.id = f.rowid",
               "JOIN edicao e ON e.id = a.edicao_id WHERE ato_fts MATCH ?"]
        parametros: list[Any] = [expressao]
        if especie:
            sql.append("AND a.especie = ?")
            parametros.append(especie.strip().lower().replace(" ", "_"))
        if orgao:
            sql.append("AND a.orgao = ?")
            parametros.append(orgao.strip().upper())
        if ano_min:
            sql.append("AND e.data >= ?")
            parametros.append(f"{int(ano_min)}-01-01")
        if ano_max:
            sql.append("AND e.data <= ?")
            parametros.append(f"{int(ano_max)}-12-31")
        return self.conexao.execute(" ".join(sql), parametros).fetchone()[0]

    def _consultar_atos(self, expressao, especie, orgao, ano_min, ano_max, limite,
                        deslocamento=0, ordenar="relevancia"):
        sql = [
            "SELECT a.*, e.data AS data_edicao, e.url,",
            "       snippet(ato_fts, 2, '', '', ' … ', 28) AS achado",
            "FROM ato_fts f JOIN ato a ON a.id = f.rowid",
            "JOIN edicao e ON e.id = a.edicao_id",
            "WHERE ato_fts MATCH ?",
        ]
        parametros: list[Any] = [expressao]
        if especie:
            sql.append("AND a.especie = ?")
            parametros.append(especie.strip().lower().replace(" ", "_"))
        if orgao:
            sql.append("AND a.orgao = ?")
            parametros.append(orgao.strip().upper())
        if ano_min:
            sql.append("AND e.data >= ?")
            parametros.append(f"{int(ano_min)}-01-01")
        if ano_max:
            sql.append("AND e.data <= ?")
            parametros.append(f"{int(ano_max)}-12-31")
        ordem = ("e.data DESC" if ordenar == "data" else "bm25(ato_fts), e.data DESC")
        sql.append(f"ORDER BY {ordem} LIMIT ? OFFSET ?")
        parametros.append(max(1, min(int(limite), 30)))
        parametros.append(max(0, int(deslocamento)))
        return [self._ato_para_dict(l) for l in
                self.conexao.execute(" ".join(sql), parametros)]

    def _ato_para_dict(self, l: sqlite3.Row) -> dict[str, Any]:
        rotulo = ROTULOS_ESPECIE.get(l["especie"], l["especie"])
        orgao = f" {l['orgao']}" if l["orgao"] else ""
        numero = f"{l['numero']}/{l['ano']}" if l["ano"] else l["numero"]
        paginas = (f"p. {l['pagina_inicial']}" if l["pagina_inicial"] == l["pagina_final"]
                   else f"p. {l['pagina_inicial']}-{l['pagina_final']}")
        d = {
            "citacao": (f"{rotulo}{orgao} nº {numero} — DOM de Mesquita, "
                        f"{_data_br(l['data_edicao'])}, {paginas}"),
            "especie": l["especie"],
            "orgao": l["orgao"],
            "numero": l["numero"],
            "ano": l["ano"],
            "publicado_em": _data_br(l["data_edicao"]),
            "data_do_ato": _data_br(l["data_ato"]) if l["data_ato"] else None,
            "ementa": l["ementa"],
            "paginas": paginas,
            "url_pdf": l["url"],
        }
        if "achado" in l.keys():
            d["trecho"] = " ".join((l["achado"] or "").split())
        if l["origem_texto"] != "pdf":
            d["aviso_ocr"] = (
                "Ato com texto reconhecido por OCR. Confira no PDF antes de "
                "transcrever."
            )
        if l["tem_retificacao"]:
            d["aviso_retificacao"] = (
                "O texto deste ato traz marca de errata, retificação ou "
                "republicação."
            )
        return d

    def atos_sobre_pessoa(
        self, nome: str, papel: str = "objeto", limite: int = 30,
        ano_min: int | None = None, ano_max: int | None = None,
    ) -> dict[str, Any]:
        """Acha os atos de uma pessoa separando o que ela ASSINOU do que lhe aconteceu.

        Buscar por nome de autoridade sem isto devolve uma enxurrada inútil: o
        nome do Prefeito casa em 750 atos, e em 748 ele é apenas quem assina.
        """
        expressao = montar_consulta_fts(nome, "AND")
        if not expressao:
            return {"nome": nome, "resultados": [], "total_examinado": 0}

        sql = ["SELECT a.*, e.data AS data_edicao, e.url",
               "FROM ato_fts f JOIN ato a ON a.id = f.rowid",
               "JOIN edicao e ON e.id = a.edicao_id",
               "WHERE ato_fts MATCH ?"]
        parametros: list[Any] = [expressao]
        if ano_min:
            sql.append("AND e.data >= ?")
            parametros.append(f"{int(ano_min)}-01-01")
        if ano_max:
            sql.append("AND e.data <= ?")
            parametros.append(f"{int(ano_max)}-12-31")
        sql.append("ORDER BY e.data DESC")

        contagem = {"objeto": 0, "assinatura": 0, "indefinido": 0}
        escolhidos: list[dict] = []
        aceitos = {papel} if papel in PAPEIS else set(PAPEIS)
        for linha in self.conexao.execute(" ".join(sql), parametros):
            qual = papel_no_ato(linha["texto"], nome)
            contagem[qual] += 1
            if qual in aceitos and len(escolhidos) < max(1, min(int(limite), 50)):
                item = self._ato_para_dict(linha)
                item["papel_da_pessoa"] = qual
                # Sem o trecho, a portaria de exoneração chega como uma citação
                # vazia: portaria não tem ementa entre aspas, e o advogado
                # precisa ler o que o ato fez antes de abrir o PDF.
                item["trecho"] = _trecho_ao_redor(linha["texto"], nome)
                escolhidos.append(item)
        return {
            "nome": nome,
            "papel_pedido": papel,
            "total_examinado": sum(contagem.values()),
            "classificacao": contagem,
            "resultados": escolhidos,
        }

    def localizar_ato(
        self, especie: str, numero: str, ano: int | None = None,
        orgao: str | None = None,
    ) -> list[dict]:
        """Acha um ato pelo número — e devolve TODAS as ocorrências.

        Devolver mais de uma não é defeito: é a informação mais importante que
        esta base tem. Duas publicações do mesmo número significam republicação
        ou errata, e é exatamente aí que se erra ao citar.
        """
        sql = [
            "SELECT a.*, e.data AS data_edicao, e.url FROM ato a",
            "JOIN edicao e ON e.id = a.edicao_id",
            "WHERE a.especie = ? AND CAST(a.numero AS INTEGER) = CAST(? AS INTEGER)",
        ]
        parametros: list[Any] = [
            especie.strip().lower().replace(" ", "_"),
            re.sub(r"\D", "", str(numero)) or "0",
        ]
        if ano:
            sql.append("AND a.ano = ?")
            parametros.append(int(ano))
        if orgao:
            sql.append("AND a.orgao = ?")
            parametros.append(orgao.strip().upper())
        sql.append("ORDER BY e.data")
        return [self._ato_para_dict(l) for l in
                self.conexao.execute(" ".join(sql), parametros)]

    def mencoes_ao_ato(
        self, especie: str, numero: str, ano: int | None = None, limite: int = 20,
    ) -> list[dict]:
        """Procura quem CITOU o ato depois — é onde a republicação aparece.

        A errata quase nunca repete o cabeçalho do ato que corrige; ela diz
        "Errata: no Decreto nº 2.763 … onde se lê … leia-se". Só a busca pela
        menção acha isso.
        """
        rotulo = ROTULOS_ESPECIE.get(especie.strip().lower().replace(" ", "_"), especie)
        so_digitos = re.sub(r"\D", "", str(numero))
        # O número aparece com e sem separador de milhar: 2763 e 2.763.
        formas = {so_digitos, so_digitos.lstrip("0")}
        if len(so_digitos) > 3:
            formas.add(f"{so_digitos[:-3]}.{so_digitos[-3:]}")
        numeros = " OR ".join(f'"{f}"' for f in sorted(formas) if f)
        # Espécie E número na mesma expressão: "2763" sozinho casa com valor
        # monetário, matrícula e número de processo — a base é cheia deles.
        expressao = f'"{rotulo}" AND ({numeros})'
        sql = """SELECT a.*, e.data AS data_edicao, e.url,
                        snippet(ato_fts, 2, '', '', ' … ', 30) AS achado
                 FROM ato_fts f JOIN ato a ON a.id = f.rowid
                 JOIN edicao e ON e.id = a.edicao_id
                 WHERE ato_fts MATCH ?
                 ORDER BY e.data LIMIT ?"""
        return [self._ato_para_dict(l) for l in
                self.conexao.execute(sql, (expressao, max(1, min(limite, 50))))]

    # -- cobertura --------------------------------------------------------

    def cobertura(self) -> dict[str, Any]:
        primeira, ultima, edicoes = self.conexao.execute(
            "SELECT MIN(data), MAX(data), COUNT(*) FROM edicao"
        ).fetchone()
        paginas = self.conexao.execute("SELECT COUNT(*) FROM pagina").fetchone()[0]
        por_origem = {
            l["origem"]: l["n"] for l in self.conexao.execute(
                "SELECT origem, COUNT(*) AS n FROM pagina GROUP BY origem"
            )
        }
        por_ano = {
            l["ano"]: l["n"] for l in self.conexao.execute(
                "SELECT substr(data,1,4) AS ano, COUNT(*) AS n FROM edicao GROUP BY 1 ORDER BY 1"
            )
        }
        # Banco construído antes da segmentação não tem a tabela `ato`, e o
        # servidor precisa subir assim mesmo — declarando que não a tem.
        try:
            atos = self.conexao.execute("SELECT COUNT(*) FROM ato").fetchone()[0]
            por_especie = {
                ROTULOS_ESPECIE.get(l["especie"], l["especie"]): l["n"]
                for l in self.conexao.execute(
                    "SELECT especie, COUNT(*) AS n FROM ato GROUP BY 1 ORDER BY 2 DESC")
            }
        except sqlite3.OperationalError:
            atos, por_especie = 0, {}
        return {
            "primeira_edicao": _data_br(primeira),
            "ultima_edicao": _data_br(ultima),
            "edicoes": edicoes,
            "paginas": paginas,
            "edicoes_por_ano": por_ano,
            "atos_segmentados": atos,
            "atos_por_especie": por_especie,
            "paginas_por_origem": {
                ORIGENS.get(k, k): v for k, v in sorted(por_origem.items())
            },
            "limites": [
                "O acervo começa em 15/07/2015 — é onde a publicação do portal "
                "começa, não onde o Município começou a publicar.",
                "Só o Diário Oficial do Município. Publicações de Mesquita no "
                "Diário do Estado, no da União ou em jornal de grande "
                "circulação estão fora desta base.",
                "Portarias, decretos, leis, leis complementares e resoluções "
                "são segmentados como atos próprios. Extratos de contrato, "
                "editais, avisos de licitação e atas de registro de preços NÃO "
                "são — continuam pesquisáveis só por página.",
                "3,8% das edições não tiveram nenhum ato reconhecido: em regra "
                "são edições só de balancete, extrato ou anexo.",
            ],
        }
