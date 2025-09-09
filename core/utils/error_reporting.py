# core/utils/error_reporting.py
import traceback
import datetime
from typing import Dict, Tuple, Any

from django.http import JsonResponse
from django.utils.html import escape
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import exception_handler as drf_exception_handler

def _format_stack_trace(exc: Exception) -> str:
    """
    Constrói uma string HTML com a stack trace, escapando HTML.
    """
    trace_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    trace_html = "<br>".join(escape(line) for line in trace_lines)
    return f"<details><summary>Stack trace</summary><pre>{trace_html}</pre></details>"

def format_error_html(
    exc: Exception,
    request_path: str,
    method: str,
    debug: bool = False,
) -> str:
    """
    Gera um bloco HTML com informações da exceção e contexto.
    - request_path: caminho/endpoint da requisição
    - method: GET, POST, etc.
    - debug: se True, inclui stack trace completa
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    exc_type = type(exc).__name__
    msg = str(exc) or repr(exc)

    html = [
        '<div style="font-family: sans-serif; padding: 10px;">',
        '<h3 style="color: #d32f2f;">Ocorreu um erro no processamento</h3>',
        '<ul style="line-height: 1.4;">',
        f"<li><strong>Data/hora:</strong> {now}</li>",
        f"<li><strong>Método:</strong> {escape(method)}</li>",
        f"<li><strong>Endpoint:</strong> {escape(request_path)}</li>",
        f"<li><strong>Tipo:</strong> {escape(exc_type)}</li>",
        f"<li><strong>Mensagem:</strong> {escape(msg)}</li>",
        "</ul>",
    ]
    if debug:
        html.append(_format_stack_trace(exc))
    html.append("</div>")
    return "".join(html)

def get_error_payload(
    request: Any,
    exc: Exception,
    *,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Constrói um dicionário com sucesso=False e HTML para envio ao frontend.
    - request: objeto HttpRequest ou DRF Request (usa .path e .method)
    - exc: exceção capturada
    - debug: se True, inclui stack trace no HTML
    """
    html = format_error_html(
        exc,
        request_path=getattr(request, "path", "<unknown>"),
        method=getattr(request, "method", "UNKNOWN"),
        debug=debug,
    )
    return {
        "success": False,
        "error": str(exc) or repr(exc),
        "html": html,
    }

def get_error_response(
    request: Any,
    exc: Exception,
    *,
    debug: bool = False,
) -> Response:
    """
    Cria um Response DRF com o payload de erro e status 500.
    Use em exception handler ou diretamente em views.
    """
    return Response(
        get_error_payload(request, exc, debug=debug),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

def custom_exception_handler(exc, context):
    """
    Usa o handler padrão do DRF para erros de validação (400), e o nosso
    formata‑erros para os demais casos (500).
    """
    # primeiro trata erros do DRF (ValidationError, AuthenticationFailed, etc.)
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    request = context.get("request")
    # debug=True se estiver em modo DEBUG
    debug = True#context.get("view").settings.DEBUG if hasattr(context.get("view"), "settings") else False
    return get_error_response(request, exc, debug=debug)