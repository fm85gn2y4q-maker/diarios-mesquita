# Coleta — como o acervo é construído

Estes scripts **não** rodam daqui. A cópia viva mora em
`C:\Users\...\Mesquita_Diarios_Oficiais`, ao lado do `acervo.db` e da junção
`municipio` que aponta para os PDFs no HD externo — eles usam
`Path(__file__).parent` como raiz, então o lugar onde estão define onde
procuram o acervo.

O que está aqui é a **versão** deles: até 28/08/2026 não havia cópia nenhuma
fora daquela pasta, e o que estes arquivos carregam nos comentários não é
código trivial — é o registro de defeitos que custaram caro para achar.

> Mexeu na cópia viva, traga para cá. Divergiram, a de lá é a que roda.

## A ordem, que não é arbitrária

```bash
python atualizar.py            # encadeia os quatro passos
python publicar_automatico.py  # os quatro + release + push (é o que o Agendador roda)
```

| passo | o que faz | por que nesta ordem |
|---|---|---|
| `baixar_diarios.py` | baixa do portal o que falta | nada existe antes disto |
| `extrair_texto.py` | texto nativo do PDF → `acervo.db` | marca as páginas sem texto |
| `ocr_paginas.py` | Tesseract `por` nas marcadas | só enxerga o que o extrator marcou |
| `segmentar_atos.py` | corta as edições em atos | lê o texto que os dois produziram |

Inverter perde a edição nova ou a segmenta pela metade.

## O que cada um aprendeu na marra

Está nos cabeçalhos de cada arquivo, com os números. Em resumo:

- **`baixar_diarios.py`** — o endpoint de anexo devolve HTML de erro em vez de
  404, então confere a assinatura `%PDF` antes de gravar; e o portal registra a
  mesma edição sob dois códigos, o que faz dois registros disputarem um nome de
  arquivo — desempatados por conteúdo, nunca sobrescritos.
- **`ocr_paginas.py`** — por que Tesseract e não os outros dois candidatos
  testados, com a medição de cada um.
- **`segmentar_atos.py`** — como distinguir cabeçalho de citação, com o custo
  medido de cada critério. É o arquivo mais denso: errar aqui cria ato que não
  existe, ou atribui a um ato o texto de outro.
- **`publicar_automatico.py`** — duas guardas nascidas de uma falha silenciosa
  de 18 dias, em que o site serviu acervo velho enquanto o log dizia
  "push feito".

## Fora daqui

`acervo.db`, `indice.csv`, `catalogo.json`, os logs, o venv do OCR e o
`por.traineddata` não entram no Git: são dados ou artefatos, e o banco vai como
asset de release.
