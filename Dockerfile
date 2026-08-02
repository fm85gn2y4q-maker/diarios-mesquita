# Imagem do servidor do Diário Oficial de Mesquita (Render, Cloud Run, Fly e afins).
FROM python:3.12-slim

WORKDIR /app

# As dependências mudam menos que o código: instaladas antes, para aproveitar o
# cache entre construções.
COPY requirements-servidor.txt ./
RUN pip install --no-cache-dir -r requirements-servidor.txt

COPY diarios/ ./diarios/

# O acervo NÃO viaja no repositório, e aqui a decisão difere da do acervo de
# legislação — de propósito, e por tamanho: lá são 21 MB comprimidos, que cabem
# no Git; aqui são 84 MB, acima dos 50 MB em que o GitHub adverte, e cada nova
# coleta acrescentaria outros 84 MB ao histórico, para sempre.
#
# Vem como asset de release, com o sha256 declarado aqui e conferido ANTES de
# descomprimir. Divergindo o arquivo publicado do declarado, a construção falha
# em vez de subir um acervo diferente do que foi testado.
#
# Os três modos de falha conhecidos desta escolha, para reconhecê-los no log:
#   - repositório privado devolve 404 no download (a release precisa ser pública);
#   - asset errado anexado à tag (o hash pega, e a mensagem diz o que veio);
#   - URL divergente do nome do repositório depois de renomeá-lo.
#
# Publicar acervo novo é rodar `python preparar_release.py <versão>`, anexar o
# .gz à release e trocar estas duas linhas.
# O sha256 abaixo é o do dist/diarios-mesquita-v1.0.0.db.gz publicado na release
# v1.0.0, conferido de ponta a ponta (comprimir → hash → descomprimir → servir).
ARG ACERVO=https://github.com/fm85gn2y4q-maker/diarios-mesquita/releases/download/v1.0.0/diarios-mesquita-v1.0.0.db.gz
ARG ACERVO_SHA256=f072188b204eeb0e1f87cc7234770b995bfe92a29757762b30dac8161a2af942
COPY instalar_acervo.py ./
RUN python instalar_acervo.py "$ACERVO" dados/diarios.sqlite "$ACERVO_SHA256"

# O serviço define a porta; 8080 é o padrão do Cloud Run quando ele não define.
ENV PORT=8080 \
    DIARIOS_HOST=0.0.0.0 \
    DIARIOS_BANCO=/app/dados/diarios.sqlite \
    PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# DIARIOS_DOMINIOS é definido depois do primeiro deploy, quando o endereço
# público passa a existir. Sem ele, só requisições locais são aceitas — o que
# na prática significa que o serviço responde 421 a tudo.
CMD ["python", "-m", "diarios", "--http"]
