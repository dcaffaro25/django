"""Local OAuth login against OpenAI's ChatGPT subscription endpoint.

Replicates OpenClaw / Codex CLI's flow exactly: spins up a loopback HTTP
server on ``http://localhost:1455``, opens the operator's browser to
OpenAI's authorization endpoint, captures the redirect, exchanges the
code for tokens, and either:

* writes them straight into the singleton :class:`OpenAITokenStore`
  (when run on the same host as the Django DB), or
* POSTs them to a remote Sysnord deployment via
  ``/api/agent/connection/import-tokens/`` (when ``--backend`` + ``--token``
  are supplied).

This is the ONLY supported way to connect — OpenAI's Codex ``client_id`` is
locked to ``http://localhost:1455/auth/callback`` so a server-side browser
redirect flow is impossible.

Usage
-----
::

    # Local dev (writes directly to local DB):
    python manage.py openai_oauth_login

    # Production (POSTs to remote Sysnord):
    python manage.py openai_oauth_login \\
        --backend https://app.sysnord.com \\
        --token <your-superuser-DRF-token>

After the browser flow completes, the command prints the connection
status and exits. The token is then live for every Sysnord user/tenant.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError

from agent.services import oauth_service


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """One-shot HTTP handler that captures ``?code=`` from the OAuth redirect.

    Stores the captured params on the server instance so the main thread
    can read them after :meth:`wait_for_callback`.
    """

    # Set by the wrapper before serve_forever()
    expected_state: str = ""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/auth/callback":
            self._respond(404, "Not found")
            return

        params = dict(urllib.parse.parse_qsl(parsed.query))
        if params.get("state") != self.expected_state:
            self._respond(400, "OAuth state mismatch.")
            return
        if "error" in params:
            self._respond(
                400,
                f"OpenAI returned error: {params['error']} — {params.get('error_description', '')}",
            )
            self.server.captured_error = params  # type: ignore[attr-defined]
            return
        if "code" not in params:
            self._respond(400, "Missing authorization code.")
            return

        self._respond(200, "OpenAI authentication completed. You can close this tab.")
        self.server.captured = params  # type: ignore[attr-defined]

    def log_message(self, format, *args):  # silence default access logs
        return

    def _respond(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            f"<!doctype html><meta charset='utf-8'><title>Sysnord OAuth</title>"
            f"<body style='font-family:system-ui;padding:40px'>{body}</body>".encode()
        )


def _run_loopback_server(state: str, timeout_seconds: int = 300) -> dict[str, str]:
    """Bind 127.0.0.1:1455 and wait for the callback. Returns the captured
    query params or raises ``TimeoutError``."""

    class _Server(socketserver.TCPServer):
        allow_reuse_address = True
        captured: dict[str, str] = {}
        captured_error: dict[str, str] = {}

    handler = type("Handler", (_CallbackHandler,), {"expected_state": state})
    httpd = _Server(("127.0.0.1", 1455), handler)

    def serve():
        httpd.serve_forever(poll_interval=0.2)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    deadline = time.time() + timeout_seconds
    try:
        while time.time() < deadline:
            if httpd.captured or httpd.captured_error:
                break
            time.sleep(0.2)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)

    if httpd.captured_error:
        raise CommandError(
            f"OAuth failed: {httpd.captured_error.get('error')} — "
            f"{httpd.captured_error.get('error_description', '')}"
        )
    if not httpd.captured:
        raise CommandError(
            "Timed out waiting for OpenAI to redirect back. Check that you "
            "completed the login in the browser."
        )
    return httpd.captured


class Command(BaseCommand):
    help = (
        "Run the OpenAI ChatGPT subscription OAuth flow locally and persist "
        "the tokens for the Sysnord agent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--backend",
            help=(
                "Remote Sysnord URL (e.g. https://app.sysnord.com). When "
                "set, tokens are POSTed to /api/agent/connection/import-tokens/ "
                "instead of being written to the local DB."
            ),
        )
        parser.add_argument(
            "--token",
            help=(
                "Sysnord DRF token of the superuser, used as Authorization "
                "header on the import-tokens POST. Required with --backend."
            ),
        )
        parser.add_argument(
            "--no-browser",
            action="store_true",
            help="Don't auto-open the browser; print the URL for manual paste.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=300,
            help="Seconds to wait for the OAuth callback (default 300).",
        )

    def handle(self, *args, **opts):
        if opts.get("backend") and not opts.get("token"):
            raise CommandError("--token is required when --backend is set.")

        # 1) Build authorization URL with PKCE
        verifier = oauth_service.new_code_verifier()
        state = oauth_service.new_state()
        auth_url = oauth_service.build_authorize_url(
            state=state, code_verifier=verifier,
        )

        # 2) Open browser + spin up loopback server
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== Sysnord agent: OpenAI OAuth login ==="
        ))
        self.stdout.write(
            "Bound http://127.0.0.1:1455/auth/callback — waiting for OpenAI redirect."
        )
        self.stdout.write(self.style.WARNING(
            "If your browser doesn't open automatically, paste this URL:"
        ))
        self.stdout.write(f"\n  {auth_url}\n")

        if not opts.get("no_browser"):
            try:
                webbrowser.open(auth_url, new=2)
            except Exception as exc:
                self.stderr.write(f"  (couldn't auto-open browser: {exc})")

        captured = _run_loopback_server(state, timeout_seconds=opts["timeout"])
        code = captured["code"]

        # 3) Exchange code for tokens at OpenAI
        self.stdout.write("Exchanging authorization code for tokens…")
        try:
            token_resp = oauth_service.exchange_code(code=code, code_verifier=verifier)
        except oauth_service.OAuthExchangeError as exc:
            raise CommandError(f"Code exchange failed: {exc}") from exc

        access = token_resp["access_token"]
        refresh = token_resp.get("refresh_token")
        expires_in = token_resp.get("expires_in")
        id_token = token_resp.get("id_token")

        try:
            chatgpt_account_id = oauth_service.extract_account_id(access)
        except oauth_service.JwtDecodeError as exc:
            raise CommandError(str(exc)) from exc

        account_email = oauth_service.extract_account_email(id_token or access)

        self.stdout.write(self.style.SUCCESS(
            f"  ✓ Got tokens. account_id={chatgpt_account_id} email={account_email or '(none)'}"
        ))

        # 4) Persist — either locally or via remote import-tokens endpoint
        if opts.get("backend"):
            self._post_to_backend(
                backend=opts["backend"].rstrip("/"),
                token=opts["token"],
                payload={
                    "access_token": access,
                    "refresh_token": refresh or "",
                    "expires_in": expires_in,
                    "chatgpt_account_id": chatgpt_account_id,
                    "account_email": account_email,
                    "id_token": id_token or "",
                },
            )
        else:
            store = oauth_service.persist_tokens(
                access_token=access,
                refresh_token=refresh,
                expires_in=expires_in,
                chatgpt_account_id=chatgpt_account_id,
                account_email=account_email,
                id_token=id_token,
            )
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ Wrote OpenAITokenStore (id={store.id}) — agent is connected."
            ))

    # ------------------------------------------------------------------
    def _post_to_backend(
        self, *, backend: str, token: str, payload: dict[str, Any],
    ) -> None:
        url = f"{backend}/api/agent/connection/import-tokens/"
        self.stdout.write(f"POSTing tokens to {url}…")
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Token {token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            raise CommandError(f"Failed to reach Sysnord backend: {exc}") from exc

        if resp.status_code >= 400:
            raise CommandError(
                f"Sysnord backend rejected the tokens ({resp.status_code}): "
                f"{resp.text[:500]}"
            )

        try:
            data = resp.json()
        except ValueError:
            data = {}

        self.stdout.write(self.style.SUCCESS(
            f"  ✓ Backend accepted tokens. is_connected={data.get('is_connected')} "
            f"account={data.get('account_email') or data.get('chatgpt_account_id') or '?'}"
        ))
