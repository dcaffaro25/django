"""
Standalone mock Omie-style HTTP server. Used for live sandbox browser testing.

Run:
  python scripts/mock_omie_server.py
Exposes:
  POST /clientes  -> returns { pagina, total_de_paginas, clientes_cadastro: [...] }
  POST /cliente   -> returns one detail object keyed by request param "codigo"
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

STEP1_BODY = {
    "pagina": 1,
    "total_de_paginas": 1,
    "total_de_registros": 3,
    "registros": 3,
    "clientes_cadastro": [
        {"codigo": "C1", "nome": "Alpha LTDA"},
        {"codigo": "C2", "nome": "Beta SA"},
        {"codigo": "C3", "nome": "Gamma ME"},
    ],
}

STEP2_DETAILS = {
    "C1": {"codigo": "C1", "nome": "Alpha LTDA", "cnpj_cpf": "11.111.111/0001-11", "cidade": "SP", "email": "alpha@x.com"},
    "C2": {"codigo": "C2", "nome": "Beta SA", "cnpj_cpf": "22.222.222/0001-22", "cidade": "RJ", "email": "beta@x.com"},
    "C3": {"codigo": "C3", "nome": "Gamma ME", "cnpj_cpf": "33.333.333/0001-33", "cidade": "BH", "email": "gamma@x.com"},
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}

        if self.path.endswith("/clientes"):
            body = STEP1_BODY
        elif self.path.endswith("/cliente"):
            codigo = None
            params = payload.get("param") or []
            if isinstance(params, list) and params:
                codigo = (params[0] or {}).get("codigo")
            body = STEP2_DETAILS.get(str(codigo), {"codigo": codigo, "nome": "?"})
        else:
            body = {"call": payload.get("call"), "echoed": payload}

        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"[mock-omie] {fmt % args}")


if __name__ == "__main__":
    port = 9912
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
