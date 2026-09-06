"""Pergunta ao servidor hospedado o que ele está servindo, de fora.

Existe porque o log da publicação não prova o deploy. Em 21/08/2026 o acervo
local estava em dia, as releases publicadas, o log dizia "push feito" — e o
site serviu acervo de 18 dias antes, sem um único erro em lugar nenhum. Só
perguntar ao endereço público desfaz esse tipo de engano.

Completa o OAuth sozinho (a aprovação do servidor é automática) e chama
`cobertura_do_acervo`. Compara com o banco local, se ele estiver ao alcance.

    python verificar_site.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SERVIDOR = "https://diarios-mesquita.onrender.com"
BANCO = Path(__file__).resolve().parent / "acervo.db"


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """O código de autorização vem no Location; seguir o redirecionamento o perde."""

    def redirect_request(self, *a, **k):
        return None


_abridor = urllib.request.build_opener(_SemRedirecionar)


def _chamar(url, dados=None, formulario=None, cabecalhos=None, espera=180):
    h = {"Accept": "application/json, text/event-stream"}
    if dados is not None:
        h["Content-Type"] = "application/json"
    if formulario is not None:
        h["Content-Type"] = "application/x-www-form-urlencoded"
    h.update(cabecalhos or {})
    corpo = (json.dumps(dados).encode() if dados is not None
             else formulario.encode() if formulario else None)
    pedido = urllib.request.Request(url, data=corpo, headers=h)
    try:
        r = _abridor.open(pedido, timeout=espera)
        return r.status, r.headers, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8", "replace")


def _autenticar() -> dict:
    """Registro dinâmico + PKCE. O servidor aprova sem interação."""
    _, _, b = _chamar(SERVIDOR + "/register", {
        "client_name": "verificacao", "redirect_uris": ["http://localhost:9999/cb"],
        # O registro exige exatamente estes dois grant_types; só um devolve 400.
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "token_endpoint_auth_method": "none",
        "scope": "diario-oficial"})
    cliente = json.loads(b)["client_id"]

    verificador = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
    desafio = base64.urlsafe_b64encode(
        hashlib.sha256(verificador.encode()).digest()).decode().rstrip("=")
    _, cab, _ = _chamar(SERVIDOR + "/authorize?" + urllib.parse.urlencode({
        "client_id": cliente, "redirect_uri": "http://localhost:9999/cb",
        "response_type": "code", "scope": "diario-oficial",
        "code_challenge": desafio, "code_challenge_method": "S256",
        "state": "x", "resource": SERVIDOR + "/mcp"}))
    # O cabeçalho vem em minúsculas: procurar por "Location" devolve vazio.
    codigo = urllib.parse.parse_qs(
        urllib.parse.urlparse(cab.get("location")).query)["code"][0]

    _, _, b = _chamar(SERVIDOR + "/token", formulario=urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": codigo, "client_id": cliente,
        "redirect_uri": "http://localhost:9999/cb", "code_verifier": verificador,
        "resource": SERVIDOR + "/mcp"}))
    return {"Authorization": "Bearer " + json.loads(b)["access_token"]}


def _abrir_sessao(cabecalhos: dict) -> dict:
    _, cab, _ = _chamar(SERVIDOR + "/mcp", {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "verificacao", "version": "1"}}},
        cabecalhos=cabecalhos)
    if cab.get("mcp-session-id"):
        cabecalhos = dict(cabecalhos, **{"mcp-session-id": cab["mcp-session-id"]})
    _chamar(SERVIDOR + "/mcp",
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            cabecalhos=cabecalhos)
    return cabecalhos


def _chamar_ferramenta(cabecalhos: dict, nome: str, argumentos: dict) -> dict:
    _, _, b = _chamar(SERVIDOR + "/mcp", {
        "jsonrpc": "2.0", "id": 9, "method": "tools/call",
        "params": {"name": nome, "arguments": argumentos}}, cabecalhos=cabecalhos)
    achado = re.search(r"data: (.*)", b)
    resultado = json.loads(achado.group(1) if achado else b)["result"]
    estruturado = resultado.get("structuredContent") or {}
    estruturado = estruturado.get("result", estruturado)
    if not estruturado:
        texto = (resultado.get("content") or [{}])[0].get("text", "")
        estruturado = json.loads(texto) if texto.startswith("{") else {}
    return estruturado


def local() -> dict | None:
    if not BANCO.exists():
        return None
    con = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    try:
        edicoes, ultima = con.execute(
            "SELECT COUNT(*), MAX(data) FROM edicao").fetchone()
        atos = con.execute("SELECT COUNT(*) FROM ato").fetchone()[0]
    finally:
        con.close()
    a, m, d = ultima.split("-")
    return {"edicoes": edicoes, "ultima": f"{d}/{m}/{a}", "atos": atos}


def main() -> int:
    tentativas = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    for tentativa in range(1, tentativas + 1):
        try:
            cabecalhos = _abrir_sessao(_autenticar())
            _, _, b = _chamar(SERVIDOR + "/mcp",
                              {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                              cabecalhos=cabecalhos)
            ferramentas = sorted(set(re.findall(r'"name":"([a-z_]+)"', b)))
            servido = _chamar_ferramenta(cabecalhos, "cobertura_do_acervo", {})
            break
        except Exception as exc:  # noqa: BLE001
            if tentativa == tentativas:
                print(f"não consegui falar com o servidor: {str(exc)[:160]}")
                return 1
            # A instância gratuita hiberna: a primeira chamada acorda a máquina.
            print(f"  tentativa {tentativa} falhou, esperando o servidor acordar…")
            time.sleep(30)

    print(f"ferramentas no ar ({len(ferramentas)}): {', '.join(ferramentas)}")
    print(f"servido: {servido.get('edicoes')} edições, última "
          f"{servido.get('ultima_edicao')}, {servido.get('atos_segmentados')} atos")

    aqui = local()
    if aqui is None:
        print("banco local fora de alcance — não dá para comparar.")
        return 0
    print(f"local  : {aqui['edicoes']} edições, última {aqui['ultima']}, "
          f"{aqui['atos']} atos")
    if (servido.get("edicoes") == aqui["edicoes"]
            and servido.get("atos_segmentados") == aqui["atos"]):
        print("CONFEREM — o site está servindo o acervo atual.")
        return 0
    print("DIVERGEM — o Render ainda não reconstruiu, ou o push não chegou ao "
          "master. Confira o ARG ACERVO do Dockerfile em origin/master.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
