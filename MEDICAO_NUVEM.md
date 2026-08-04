# Medição do ambiente da nuvem — viabilidade da coleta do Diário Oficial de Mesquita

Medição executada em 2026-08-04, em sessão de Claude Code on the web (ambiente remoto efêmero). Nenhuma alteração de projeto foi feita além deste arquivo.

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
sudo_exit=0
```

Rodando como `root` diretamente; sudo sem senha funciona (exit 0). Não é necessário sudo para instalar pacotes, já que a sessão já é root.

## 2. Tesseract

Comando: `apt-get update`

Resultado: bem-sucedido para os repositórios oficiais do Ubuntu (archive.ubuntu.com, security.ubuntu.com, download.docker.com). Duas PPAs de terceiros (deadsnakes, ondrej/php) falharam por bloqueio do proxy da sessão:

```
Err:4 https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu noble InRelease
  Invalid response from proxy: HTTP/1.1 403 Forbidden  Content-Length: 36     [IP: 127.0.0.1 43485]
Err:5 https://ppa.launchpadcontent.net/ondrej/php/ubuntu noble InRelease
  Invalid response from proxy: HTTP/1.1 403 Forbidden  Content-Length: 36     [IP: 127.0.0.1 43485]
W: Failed to fetch https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu/dists/noble/InRelease  Invalid response from proxy: HTTP/1.1 403 Forbidden  Content-Length: 36     [IP: 127.0.0.1 43485]
W: Failed to fetch https://ppa.launchpadcontent.net/ondrej/php/ubuntu/dists/noble/InRelease  Invalid response from proxy: HTTP/1.1 403 Forbidden  Content-Length: 36     [IP: 127.0.0.1 43485]
W: Some index files failed to download. They have been ignored, or old ones used instead.
```

Essas PPAs não são necessárias para o tesseract; a instalação seguiu normalmente pelos repositórios oficiais.

Comando: `apt-get install -y tesseract-ocr tesseract-ocr-por`

```
The following additional packages will be installed:
  liblept5 libtesseract5 libwebpmux3 tesseract-ocr-eng tesseract-ocr-osd
The following NEW packages will be installed:
  liblept5 libtesseract5 libwebpmux3 tesseract-ocr tesseract-ocr-eng
  tesseract-ocr-osd tesseract-ocr-por
0 upgraded, 7 newly installed, 0 to remove and 146 not upgraded.
Need to get 9354 kB of archives.
After this operation, 23.9 MB of additional disk space will be used.
...
Setting up tesseract-ocr-por (1:4.1.0-2) ...
Setting up tesseract-ocr-eng (1:4.1.0-2) ...
Setting up tesseract-ocr-osd (1:4.1.0-2) ...
Setting up libwebpmux3:amd64 (1.3.2-0.4build3) ...
Setting up liblept5:amd64 (1.82.0-3build4) ...
Setting up libtesseract5:amd64 (5.3.4-1build5) ...
Setting up tesseract-ocr (5.3.4-1build5) ...
Processing triggers for libc-bin (2.39-0ubuntu8.7) ...
```

Instalação concluída sem erros, via `apt-get` normal (repositório oficial do Ubuntu), sem necessidade de baixar `por.traineddata` do GitHub.

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

O idioma `por` ficou disponível. Não foi necessário recorrer ao download do `por.traineddata` do GitHub (tessdata_fast) — mas registre-se que esse caminho alternativo **também estaria bloqueado** neste ambiente: um teste de alcance a `github.com` (usado como proxy do domínio do tessdata_fast) devolveu `HTTP_CODE=403` pelo mesmo proxy de saída da sessão (ver seção 4). Ou seja, se o apt não tivesse funcionado, a alternativa sugerida na tarefa não teria funcionado aqui.

## 3. Qualidade do OCR

`pip install pymupdf` (ver também seção 6) e geração de um PDF de teste com o texto:

`DOTAÇÃO ORÇAMENTÁRIA - PORTARIA No 049/2025 - EXONERAÇÃO`

Script usado (`fitz`/pymupdf), renderizado a 300 dpi e passado por `tesseract -l por`.

Primeira tentativa, com a página estreita demais (595pt de largura), o texto foi cortado e o OCR devolveu:

```
DOTAÇÃO ORÇAMENTÁRIA - PORTARIA No 049/2025 - EXONERA(
```

Corrigido o teste com página mais larga (900pt, PNG resultante 3750×834 px a 300 dpi), o resultado do `tesseract test_por2.png - -l por` foi:

```
DOTAÇÃO ORÇAMENTÁRIA - PORTARIA No 049/2025 - EXONERAÇÃO
```

**Os acentos voltaram corretos** (Ç, Ã, Á) quando o texto não é cortado pela borda da página. Isso confirma que o pacote `por` do tesseract reconhece corretamente a acentuação do português, e que o cuidado a tomar na coleta real é garantir que o corte/paginação de cada página do diário não corte texto na borda da imagem.

## 4. Rede até o portal da prefeitura

Comando:

```
curl -s -o /dev/null -w '%{http_code}' -X POST https://transparencia.mesquita.rj.gov.br/diario_oficial_get.php -d 'mesano=8/2026'
```

Resultado: `HTTP_CODE=000`, `TIME=0.317519s` (curl exit code 56 — falha de leitura, conexão não estabelecida).

Diagnóstico com `curl -v`:

```
* Uses proxy env variable https_proxy == 'http://127.0.0.1:43485'
*   Trying 127.0.0.1:43485...
* Connected to 127.0.0.1 (127.0.0.1) port 43485
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
curl: (56) CONNECT tunnel failed, response 403
```

Comando (download do PDF de teste):

```
curl -s -o /tmp/t.pdf -w '%{http_code} %{size_download} %{speed_download}' -L 'https://transparencia.mesquita.rj.gov.br/diario_oficial_get_anexo.php?codigo=14326'
```

Resultado: `HTTP_CODE=000 SIZE=0 SPEED=0` (exit code 56, mesmo bloqueio de proxy). Nenhum byte foi baixado.

Diagnóstico consultado em `$HTTPS_PROXY/__agentproxy/status` (`recentRelayFailures`):

```
2026-08-04T03:01:51.948Z transparencia.mesquita.rj.gov.br:443 gateway answered 403 to CONNECT (policy denial or upstream failure)
2026-08-04T03:01:55.337Z transparencia.mesquita.rj.gov.br:443 gateway answered 403 to CONNECT (policy denial or upstream failure)
2026-08-04T03:02:07.466Z transparencia.mesquita.rj.gov.br:443 gateway answered 403 to CONNECT (policy denial or upstream failure)
```

Ou seja: **não é uma falha de rede transitória, é uma negação de política do proxy de saída do ambiente** ("policy denial"). O domínio `transparencia.mesquita.rj.gov.br` não está na lista liberada para este ambiente.

Como referência adicional, testei também `github.com` (para avaliar a alternativa de baixar `por.traineddata` — item 2) e obtive o mesmo padrão de bloqueio:

```
curl -s -o /dev/null -w 'HTTP_CODE=%{http_code}\n' -L 'https://github.com/tesseract-ocr/tessdata_fast/raw/main/por.traineddata'
HTTP_CODE=403
```

Os domínios que funcionaram neste ambiente (confirmados por uso bem-sucedido nesta mesma sessão): `archive.ubuntu.com`, `security.ubuntu.com`, `download.docker.com`, `pypi.org`/`files.pythonhosted.org` (via `pip install`). Esses estão consistentes com a lista de `noProxy`/liberados reportada por `$HTTPS_PROXY/__agentproxy/status`.

## 5. Espaço em disco e memória

Comando: `df -h .`

```
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda        252G  7.2G   30G  20% /
```

30 GB disponíveis — muito acima do necessário para o acervo aberto (245 MB) ou o pacote comprimido (83 MB), e para os PDFs de ~1 MB por edição baixados durante a coleta.

Comando: `free -m`

```
               total        used        free      shared  buff/cache   available
Mem:           16075         608       14547           4        1180       15467
Swap:              0           0           0
```

16 GB de RAM, 15,4 GB disponíveis. Memória não é fator limitante.

## 6. PyMuPDF

Comando: `pip install pymupdf`

```
Collecting pymupdf
  Downloading pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl.metadata (26 kB)
Downloading pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl (25.7 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 25.7/25.7 MB 25.1 MB/s eta 0:00:00
Installing collected packages: pymupdf
Successfully installed pymupdf-1.28.0
WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv
```

Funcionou sem problemas. Versão instalada: **pymupdf 1.28.0**. Foi usado com sucesso para gerar e renderizar o PDF de teste da seção 3 (via `fitz`).

## Veredito

**(a) Dá para instalar o Tesseract com português?** Sim — `apt-get install tesseract-ocr tesseract-ocr-por` funciona neste ambiente sem sudo especial (já é root), o idioma `por` fica disponível, e o OCR devolve acentuação portuguesa correta (testado com "DOTAÇÃO ORÇAMENTÁRIA... EXONERAÇÃO").

**(b) Dá para alcançar o portal?** Não — todo acesso a `transparencia.mesquita.rj.gov.br` é bloqueado pelo proxy de saída do ambiente com HTTP 403 ("policy denial"), tanto para a consulta de mês/ano quanto para o download de anexo em PDF; a alternativa de baixar `por.traineddata` do GitHub também é bloqueada pelo mesmo motivo.

**(c) Dá para rodar a coleta inteira aqui?** Não, neste ambiente específico — falta exclusivamente o alcance de rede ao portal da Prefeitura de Mesquita (item b); disco, memória, Tesseract/português e PyMuPDF estão todos prontos e funcionando. A coleta rodaria de ponta a ponta assim que o domínio `transparencia.mesquita.rj.gov.br` fosse liberado na política de saída do ambiente.
