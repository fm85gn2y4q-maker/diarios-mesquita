# Medição do ambiente da nuvem

Medição automatizada, executada em 2026-08-04, para verificar se esta sessão de nuvem (Claude Code on the web) serve para rodar a coleta do Diário Oficial de Mesquita. Nenhuma alteração foi feita no projeto além deste arquivo.

## 1. Ambiente

Comando: `uname -a`

```
Linux vm 6.18.5 #1 SMP PREEMPT_DYNAMIC @0 x86_64 x86_64 x86_64 GNU/Linux
```

Comando: `cat /etc/os-release`

```
PRETTY_NAME="Ubuntu 24.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.4 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo
```

Comando: `whoami`

```
root
```

Comando: `sudo -n true; echo $?`

```
0
```

(Já executando como root, então sudo sem senha responde imediatamente com sucesso.)

## 2. Tesseract

Comando: `sudo apt-get update`

Saída relevante (dois repositórios de terceiros, não usados pelo projeto, falharam; os repositórios oficiais do Ubuntu sincronizaram normalmente):

```
Hit:5 http://archive.ubuntu.com/ubuntu noble InRelease
Get:6 http://archive.ubuntu.com/ubuntu noble-updates InRelease [126 kB]
Get:7 https://download.docker.com/linux/ubuntu noble/stable amd64 Packages [75.7 kB]
Get:8 http://security.ubuntu.com/ubuntu noble-security/restricted amd64 Packages [1587 kB]
Get:9 http://archive.ubuntu.com/ubuntu noble-backports InRelease [126 kB]
Get:10 http://security.ubuntu.com/ubuntu noble-security/main amd64 Packages [1110 kB]
Get:11 http://security.ubuntu.com/ubuntu noble-security/multiverse amd64 Packages [50.0 kB]
Get:12 http://security.ubuntu.com/ubuntu noble-security/universe amd64 Packages [1522 kB]
Get:13 http://archive.ubuntu.com/ubuntu noble-updates/main amd64 Packages [1433 kB]
Get:14 http://archive.ubuntu.com/ubuntu noble-updates/restricted amd64 Packages [1700 kB]
Get:15 http://archive.ubuntu.com/ubuntu noble-updates/multiverse amd64 Packages [55.8 kB]
Get:16 http://archive.ubuntu.com/ubuntu noble-updates/universe amd64 Packages [2138 kB]
Get:17 http://archive.ubuntu.com/ubuntu noble-backports/main amd64 Packages [48.9 kB]
Get:18 http://archive.ubuntu.com/ubuntu noble-backports/universe amd64 Packages [35.9 kB]
Get:19 http://archive.ubuntu.com/ubuntu noble-backports/multiverse amd64 Packages [671 B]
Reading package lists...
E: Failed to fetch https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu/dists/noble/InRelease  403  Forbidden [IP: 185.125.189.186 443]
E: The repository 'https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu noble InRelease' is no longer signed.
E: Failed to fetch https://ppa.launchpadcontent.net/ondrej/php/ubuntu/dists/noble/InRelease  403  Forbidden [IP: 185.125.189.186 443]
E: The repository 'https://ppa.launchpadcontent.net/ondrej/php/ubuntu noble InRelease' is no longer signed.
```

Comando: `sudo apt-get install -y tesseract-ocr tesseract-ocr-por`

Saída (resumida, sem as barras de progresso de "Reading database"):

```
After this operation, 23.9 MB of additional disk space will be used.
Get:1 http://archive.ubuntu.com/ubuntu noble/main amd64 libwebpmux3 amd64 1.3.2-0.4build3 [25.7 kB]
Get:2 http://archive.ubuntu.com/ubuntu noble/universe amd64 liblept5 amd64 1.82.0-3build4 [1099 kB]
Get:3 http://archive.ubuntu.com/ubuntu noble/universe amd64 libtesseract5 amd64 5.3.4-1build5 [1291 kB]
Get:4 http://archive.ubuntu.com/ubuntu noble/universe amd64 tesseract-ocr-eng all 1:4.1.0-2 [1818 kB]
Get:5 http://archive.ubuntu.com/ubuntu noble/universe amd64 tesseract-ocr-osd all 1:4.1.0-2 [3841 kB]
Get:6 http://archive.ubuntu.com/ubuntu noble/universe amd64 tesseract-ocr amd64 5.3.4-1build5 [328 kB]
Get:7 http://archive.ubuntu.com/ubuntu noble/universe amd64 tesseract-ocr-por all 1:4.1.0-2 [951 kB]
Fetched 9354 kB in 2s (5093 kB/s)
Setting up tesseract-ocr-por (1:4.1.0-2) ...
Setting up tesseract-ocr-eng (1:4.1.0-2) ...
Setting up tesseract-ocr-osd (1:4.1.0-2) ...
Setting up libwebpmux3:amd64 (1.3.2-0.4build3) ...
Setting up liblept5:amd64 (1.82.0-3build4) ...
Setting up libtesseract5:amd64 (5.3.4-1build5) ...
Setting up tesseract-ocr (5.3.4-1build5) ...
Processing triggers for libc-bin (2.39-0ubuntu8.7) ...
```

Instalação via apt funcionou de primeira. Não foi necessário baixar `por.traineddata` do GitHub manualmente.

Comando: `tesseract --version`

```
tesseract 5.3.4
 leptonica-1.82.0
  libgif 5.2.1 : libjpeg 8d (libjpeg-turbo 2.1.5) : libpng 1.6.43 : libtiff 4.5.1 : zlib 1.3 : libwebp 1.3.2 : libopenjp2 2.5.0
 Found AVX512BW
 Found AVX512F
 Found AVX512VNNI
 Found AVX2
 Found AVX
 Found FMA
 Found SSE4.1
 Found OpenMP 201511
 Found libarchive 3.7.2 zlib/1.3 liblzma/5.4.5 bz2lib/1.0.8 liblz4/1.9.4 libzstd/1.5.5
 Found libcurl/8.5.0 OpenSSL/3.0.13 zlib/1.3 brotli/1.1.0 zstd/1.5.5 libidn2/2.3.7 libpsl/0.21.2 (+libidn2/2.3.7) libssh/0.10.6/openssl/zlib nghttp2/1.59.0 librtmp/2.3 OpenLDAP/2.6.10
```

Comando: `tesseract --list-langs`

```
List of available languages in "/usr/share/tesseract-ocr/5/tessdata/" (3):
eng
osd
por
```

O idioma `por` ficou disponível.

## 3. Qualidade do OCR

Instalação: `pip install pymupdf` (ver detalhes na seção 6).

Script Python usado para gerar o PDF de teste com acentuação em português:

```python
import pymupdf

doc = pymupdf.open()
page = doc.new_page(width=842, height=200)  # página larga, para não cortar o texto
text = "DOTAÇÃO ORÇAMENTÁRIA - PORTARIA No 049/2025 - EXONERAÇÃO"
page.insert_text((50, 100), text, fontsize=18, fontname="helv")
doc.save("test2.pdf")

doc2 = pymupdf.open("test2.pdf")
p = doc2[0]
mat = pymupdf.Matrix(300/72, 300/72)  # 300 dpi
pix = p.get_pixmap(matrix=mat)
pix.save("test2.png")
```

Nota: a primeira tentativa usou o tamanho de página padrão (A4, ~595pt de largura) e o texto foi cortado na borda da página antes mesmo de chegar ao tesseract ("...EXONER"). Isso era um artefato da geração do PDF de teste, não do OCR — corrigido usando uma página mais larga (842pt).

Comando: `tesseract test2.png out2 -l por` e depois `cat out2.txt`

Texto original:
```
DOTAÇÃO ORÇAMENTÁRIA - PORTARIA No 049/2025 - EXONERAÇÃO
```

Texto devolvido pelo tesseract:
```
DOTAÇÃO ORÇAMENTÁRIA - PORTARIA No 049/2025 - EXONERAÇÃO
```

Os dois textos são idênticos, caractere por caractere. Todos os acentos (Ç, Ã, Á) voltaram corretos.

## 4. Rede até o portal da prefeitura

Comando:
```
curl -s -o /dev/null -w '%{http_code}' -X POST https://transparencia.mesquita.rj.gov.br/diario_oficial_get.php -d 'mesano=8/2026'
```

Resultado: `000` (curl exit code 56 — falha de recebimento, sem código HTTP real).

Diagnóstico com `curl -v` no mesmo endereço:

```
* Uses proxy env variable https_proxy == 'http://127.0.0.1:41709'
*   Trying 127.0.0.1:41709...
* Connected to 127.0.0.1 (127.0.0.1) port 41709
* CONNECT tunnel: HTTP/1.1 negotiated
* allocate connect buffer
* Establish HTTP proxy tunnel to transparencia.mesquita.rj.gov.br:443
> CONNECT transparencia.mesquita.rj.gov.br:443 HTTP/1.1
> Host: transparencia.mesquita.rj.gov.br:443
> User-Agent: curl/8.5.0
> Proxy-Connection: Keep-Alive
> 
< HTTP/1.1 403 Forbidden
< Content-Length: 36
< 
* CONNECT tunnel failed, response 403
* Closing connection
```

Confirmado pelo status do proxy do ambiente (`curl -sS "$HTTPS_PROXY/__agentproxy/status"`):

```json
"recentRelayFailures": [
  {
    "ts": "2026-08-04T00:17:44.643Z",
    "kind": "connect_rejected",
    "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
    "host": "transparencia.mesquita.rj.gov.br:443"
  },
  {
    "ts": "2026-08-04T00:17:44.997Z",
    "kind": "connect_rejected",
    "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
    "host": "transparencia.mesquita.rj.gov.br:443"
  },
  {
    "ts": "2026-08-04T00:17:49.398Z",
    "kind": "connect_rejected",
    "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
    "host": "transparencia.mesquita.rj.gov.br:443"
  }
]
```

Todo o tráfego HTTPS de saída desta sessão passa por um proxy de política ("agent proxy") que reterminaliza o TLS. Segundo o README desse proxy (`/root/.ccr/README.md`), um 403/407 no CONNECT indica que o host de destino **não está liberado pela política de saída da organização para esta sessão**, e instrui explicitamente a não tentar contornar isso ("Do not retry or route around it — report the blocked host.").

Consequência: o segundo teste (download do PDF de exemplo, `diario_oficial_get_anexo.php?codigo=14326`) também falhou pelo mesmo motivo, sem sequer completar o handshake:

```
curl -s -o /tmp/t.pdf -w '%{http_code} %{size_download} %{speed_download}' -L 'https://transparencia.mesquita.rj.gov.br/diario_oficial_get_anexo.php?codigo=14326'
```

Resultado: `000 0 0` — nenhum byte baixado, nenhum código HTTP recebido do servidor real (a rejeição aconteceu no proxy, antes de chegar ao portal). Não foi possível medir tamanho nem velocidade de download porque a conexão nunca chegou a se estabelecer com o servidor de destino.

**Não é uma falha do portal da prefeitura** — é uma política de rede deste ambiente de nuvem que bloqueia esse host especificamente. Não houve nova tentativa após a negação de política, conforme instruído pelo próprio proxy.

## 5. Espaço em disco e memória

Comando: `df -h .`

```
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda        252G  7.2G   30G  20% /
```

Comando: `free -m`

```
               total        used        free      shared  buff/cache   available
Mem:           16075         601       14560           4        1175       15474
Swap:              0           0           0
```

30 GB disponíveis é muito mais que suficiente para o acervo aberto (245 MB), o pacote comprimido (83 MB) e os PDFs baixados durante a coleta (~1 MB por edição). Memória disponível (15,4 GB) também não é fator limitante.

## 6. PyMuPDF

Comando: `pip install pymupdf`

```
Collecting pymupdf
  Downloading pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl.metadata (26 kB)
Downloading pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl (25.7 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 25.7/25.7 MB 19.5 MB/s eta 0:00:00
Installing collected packages: pymupdf
Successfully installed pymupdf-1.28.0
WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv
```

Comando: `python3 -c "import pymupdf; print(pymupdf.__version__)"`

```
PyMuPDF 1.28.0: Python bindings for the MuPDF 1.29.0 library.
Python 3.11 running on linux (64-bit).
pymupdf version: 1.28.0
```

Instalação funcionou sem erros (fora o aviso de rotina sobre rodar pip como root). Baixado do PyPI (`pypi.org`/`files.pythonhosted.org`), que está na lista de hosts liberados pela política de rede — diferente do portal da prefeitura.

## Veredito

(a) **Dá para instalar o Tesseract com português?** Sim — `apt-get install tesseract-ocr tesseract-ocr-por` funciona sem obstáculos, o idioma `por` fica disponível, e o teste de OCR com acentuação (Ç, Ã, Á) devolveu o texto perfeitamente correto.

(b) **Dá para alcançar o portal da prefeitura?** Não — a política de rede de saída deste ambiente de nuvem bloqueia `transparencia.mesquita.rj.gov.br` (o proxy responde 403 Forbidden ao CONNECT), então nenhuma requisição HTTPS a esse host se completa, seja POST na busca de diário, seja GET de anexo em PDF.

(c) **Dá para rodar a coleta inteira aqui?** Não, não nesta sessão/ambiente tal como configurado hoje: disco, memória, Tesseract, idioma português e PyMuPDF estão todos prontos, mas a coleta depende de baixar os PDFs do Diário Oficial diretamente do portal da prefeitura, e esse acesso está bloqueado pela política de rede do ambiente — seria necessário que um administrador liberasse `transparencia.mesquita.rj.gov.br` na política de egress para esta coleta rodar aqui.
