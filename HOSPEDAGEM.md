# Publicar o servidor — GitHub e Render

O que muda em relação ao acervo de legislação está em **um ponto só**: lá o
banco viaja dentro do repositório (21 MB comprimido); aqui ele tem **84 MB
comprimido, 257 MB descomprimido**, acima dos 50 MB em que o GitHub adverte, e
cada nova coleta acrescentaria outros 84 MB ao histórico do Git, para sempre.

Por isso o acervo vai como **asset de release**, e a imagem o busca na
construção conferindo o sha256. O resto do caminho é o mesmo.

## O que já está pronto

| arquivo | para quê |
|---|---|
| `Dockerfile` | imagem do servidor; baixa o acervo e confere o hash |
| `render.yaml` | Blueprint com as três variáveis de ambiente |
| `requirements-servidor.txt` | só o SDK `mcp`, pinado em `<2` |
| `instalar_acervo.py` | baixa/descomprime conferindo sha256 **antes** |
| `preparar_release.py` | comprime o acervo e imprime o que colar no Dockerfile |
| `.gitignore` | mantém banco, `.venv` e `dist/` fora do Git |

## 1. Preparar o acervo

```bash
python preparar_release.py 1.0.0
```

Ele comprime `~/Mesquita_Diarios_Oficiais/acervo.db`, calcula o sha256 e
imprime as duas linhas do `Dockerfile` e o comando `gh` da release.

**Feche o que estiver escrevendo no banco antes** — servidor MCP, script de
coleta. Havendo um `-wal` ao lado, o script avisa: publicar com ele aberto
produz um acervo sem as últimas escritas, e sem erro nenhum.

## 2. Criar o repositório e subir o código

Esta parte é sua: criar repositório e publicar release vincula a sua
identidade, e isso não se delega.

```bash
cd ~/projetos/diarios-mesquita
git init && git add . && git commit -m "Servidor MCP do Diário Oficial de Mesquita"
gh repo create diarios-mesquita --public --source=. --push
```

O banco não vai nesse push — o `.gitignore` o mantém fora. Vão o código, os
testes e os arquivos de hospedagem.

## 3. Publicar a release com o acervo

```bash
gh release create v1.0.0 dist/diarios-mesquita-v1.0.0.db.gz \
  --title "Acervo v1.0.0" --notes "2658 edições, 27921 páginas, 17755 atos"
```

**A release precisa ser pública.** Repositório privado devolve 404 no download
durante a construção, e o log do Render mostra só o erro da requisição.

Depois, troque no `Dockerfile` as duas linhas `ARG` pelo que o
`preparar_release.py` imprimiu — a URL com o seu usuário e o sha256 — e
commite.

## 4. Aplicar o Blueprint

No Render: **Dashboard → Blueprints → New Blueprint**, apontando para o
repositório. O `render.yaml` já declara o serviço.

Criar a conta e autorizar o GitHub também é você.

## 5. Declarar o endereço público — o passo que todo mundo esquece

O endereço só existe depois do primeiro deploy. Até ser declarado, o servidor
**recusa toda requisição externa com 421** — é proteção contra DNS rebinding, e
não há curinga: a comparação de Host é exata.

Terminado o primeiro deploy, em **Environment**:

| Variável | Valor |
|---|---|
| `DIARIOS_DOMINIOS` | `diarios-mesquita.onrender.com` *(sem `https://`)* |
| `DIARIOS_URL_PUBLICA` | `https://diarios-mesquita.onrender.com` |
| `DIARIOS_SEGREDO_OAUTH` | valor longo e aleatório — use **Generate** no Render |

`DIARIOS_URL_PUBLICA` liga o fluxo OAuth, que o **ChatGPT exige** para aceitar
um conector. O Claude conecta sem ele.

**As três, não duas.** `DIARIOS_SEGREDO_OAUTH` só nasce sozinho quando o
serviço vem de um Blueprint (`generateValue: true`). Criando o serviço à mão
por **New → Web Service**, ela não existe, e o servidor sorteia um segredo novo
a cada partida. Como a instância gratuita hiberna, isso invalida todas as
autorizações do ChatGPT a cada soneca: o conector pede autorização o dia
inteiro, e parece defeito do acervo. O log avisa quando falta.

## 6. Ligar nos clientes

- **ChatGPT**: Configurações → Conectores → novo conector, URL
  `https://<seu-serviço>.onrender.com/mcp`. Ele conduz o OAuth sozinho.
- **Claude** (web/desktop): adicionar conector com a mesma URL. Sem OAuth
  também funciona.
- **Claude Desktop local**: já está configurado apontando para o `.venv` e o
  banco em `~/Mesquita_Diarios_Oficiais/acervo.db`. Não depende do Render.

## 7. Conferir que subiu o acervo certo

Pergunte a cobertura pelo cliente. Devem vir:

```
2658 edições · 15/07/2015 a 31/07/2026 · 27921 páginas · 17755 atos segmentados
```

Vindo número diferente, o `ARG ACERVO` aponta para outra release.

## O que esperar do plano gratuito

A instância hiberna por inatividade e leva ~1 minuto para acordar: a primeira
pergunta do dia demora. O download de 84 MB acontece na **construção**, não a
cada partida.

## Ao publicar acervo novo

```bash
python preparar_release.py 1.1.0
gh release create v1.1.0 dist/diarios-mesquita-v1.1.0.db.gz --title "Acervo v1.1.0" --notes "…"
# trocar ARG ACERVO e ARG ACERVO_SHA256 no Dockerfile, commitar
```

O Render reconstrói ao receber o commit e confere o hash. Divergindo, a
construção falha — que é o comportamento desejado: melhor não subir do que
subir um acervo diferente do que foi testado.
