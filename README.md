# Diário Oficial de Mesquita/RJ — servidor MCP

Expõe o Diário Oficial do Município de Mesquita como ferramenta de pesquisa
para o Claude e o ChatGPT. **2.659 edições, 27.931 páginas, de 15/07/2015 a
hoje**, coletadas do Portal da Transparência da Prefeitura.

É o terceiro acervo construído sobre a mesma arquitetura, depois do Ementário
do TCE-RJ e da Legislação de Mesquita: SQLite com FTS5 de conteúdo externo,
busca tolerante a acento, `.mcpb` para o Claude Desktop e Docker + Render com
OAuth para o ChatGPT.

## O risco desta base

Cada acervo tem um risco jurídico próprio, e é ele que define a ferramenta
central. Na jurisprudência é a **proveniência** (de que parte do acórdão veio o
trecho); na legislação, a **vigência** (a norma pode estar revogada).

Aqui é a **republicação**. O Município publica o ato, percebe o erro e o
republica dias depois. Medido no acervo: **452 menções a republicação e 391 a
errata ou retificação em 996 edições examinadas** — não é exceção, é rotina.
A busca devolve a versão errada e a corrigida com a mesma confiança, e nada no
texto da primeira avisa que ela foi refeita.

Daí o `aviso_retificacao` em toda página que traga marca de errata, e a
instrução, no prompt do servidor, de procurar republicação posterior antes de
citar qualquer ato.

## O segundo risco: a página não é o ato

Medido: **89,6% das edições trazem mais de um ato**, mediana de 6 por edição,
uma delas com 106. Uma página pode conter o fim de uma portaria, um decreto
inteiro e o começo de um extrato de contrato.

Daí a segmentação: **17.765 atos** com número, órgão emissor, ementa e
intervalo de páginas — portaria (14.506), decreto (2.246), resolução (660),
lei (332) e lei complementar (11). O ato atravessa a virada da página quando é
o caso; o maior deles ocupa 138 páginas, porque a portaria manda republicar o
relatório orçamentário inteiro e diz isso no próprio texto ("EM PÁGS. 02 À 139").

Como o cabeçalho é distinguido de uma citação está em `segmentar_atos.py`, com
os números de cada decisão. Um resumo: vocabulário fechado (sem ele, os três
padrões mais frequentes no começo de linha eram "CADASTRADO SOB O nº",
"COMBINADA COM A LEI COMPLEMENTAR nº" e "ATRAVÉS DA LEI nº" — todos citações);
cabeçalho sozinho na linha; caixa alta, que aqui custa 1% enquanto no acervo de
legislação custava 15%; e recusa de "LEI MUNICIPAL"/"LEI FEDERAL", porque ato
nenhum se apresenta dizendo de que ente é.

**Fora da segmentação:** extrato de contrato, edital, aviso de licitação e ata
de registro de preços não têm cabeçalho numerado no padrão, e continuam
pesquisáveis só por página. 3,8% das edições não têm nenhum ato reconhecido —
em regra são edições só de balancete ou anexo.

## O terceiro: duas origens de texto

| origem | páginas | confiança |
|---|---:|---|
| texto nativo do PDF | 23.808 | fiel ao publicado |
| reconhecido por OCR | ~4.100 | bom no corpo, ruim em cabeçalho estilizado |

Toda passagem diz de qual origem veio. Trecho de OCR não se transcreve numa
peça sem conferir o PDF.

## Ferramentas

| ferramenta | para quê |
|---|---|
| `pesquisar_atos` | procura o ato delimitado, por espécie, órgão e ano |
| `historico_do_ato` | todas as publicações de um número + quem o citou depois |
| `pesquisar_publicacoes` | procura no texto das páginas, com recorte por data |
| `ler_pagina` | texto inteiro da página, para ver onde o ato começa e acaba |
| `listar_edicoes` | que edições houve num período (útil para prazo) |
| `cobertura_do_acervo` | o que a base alcança e o que não alcança |
| `search` / `fetch` | assinaturas exigidas pelo conector do ChatGPT |

## Uso

```bash
pip install -r requirements.txt
python -m diarios                 # stdio, para o Claude Desktop
python -m diarios --http          # HTTP em 127.0.0.1:8766, para o ChatGPT
```

Onde cada coisa mora, e por quê:

| o quê | onde | motivo |
|---|---|---|
| `acervo.db` (246 MB) | `C:\Users\...\Mesquita_Diarios_Oficiais\` | é o que responde às buscas |
| PDFs (3,5 GB) | `D:\Mesquita_Diarios_Oficiais\municipio\` (HD USB) | matéria-prima, lida só na coleta |

A pasta `municipio` em C: é uma **junção** para o HD externo, então todo caminho
em script e índice continua valendo sem alteração.

A divisão foi medida, não estimada: servir este SQLite do HD USB leva **16 a
30 s por busca**, contra **0,01 a 0,02 s** no NVMe. Não é o tamanho do banco —
é o FTS5 fazendo leitura aleatória pelo índice, e disco que gira paga ~10 ms por
salto. O sintoma não aparece em teste nenhum: `pytest` passa, a coleta roda, e
só a pesquisa fica inutilizável.

O servidor procura o banco nesta ordem: `DIARIOS_BANCO`, depois o disco rápido,
depois o HD externo. Com o HD desconectado, a coleta falha — a busca, não.

## Como o acervo é construído

Fora deste repositório, em `C:\Users\...\Mesquita_Diarios_Oficiais`, por
quatro scripts que se executam nesta ordem e são todos incrementais —
reexecutar só processa o que chegou depois:

```bash
python atualizar.py                # os quatro passos, na ordem certa
python atualizar.py --release 1.2.0  # e já prepara o pacote para publicar
```

Os quatro passos que ele encadeia — baixar, extrair, reconhecer, segmentar —
também rodam soltos, mas a ordem não é arbitrária: o OCR só enxerga o que o
extrator marcou como página sem texto, e a segmentação lê o que os dois
produziram.

O OCR mora num venv separado de propósito: ele arrasta dependências pesadas que
não têm por que conviver com o resto do ambiente.

O acervo fica fora do Git, como asset de release com conferência de sha256 —
**A coleta semanal depende de o HD externo estar conectado**: sem ele a tarefa
falha e o sinal de vida envelhece, que é como o monitor percebe. A busca não
depende do HD — o banco está no disco rápido.
