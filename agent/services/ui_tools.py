"""Virtual UI tools the agent can call to drive the chat widget.

Unlike :data:`mcp_server.tools.TOOLS` (which actually query the Sysnord
DB), these tools are **never executed server-side** — they exist purely
as structured affordances for the LLM to surface interactive UI in the
chat widget. When the LLM calls one, the runtime:

1. Persists the function_call as an ``assistant`` :class:`AgentMessage`
   (so the frontend can render the buttons), AND
2. Persists a synthetic ``tool`` :class:`AgentMessage` carrying a
   placeholder result (``{"status":"awaiting_user_response"}``) — this
   keeps the OpenAI API contract intact so the next request validates,
3. **Stops** the iteration loop. The user's next typed/clicked answer
   becomes the next ``user`` message, and the LLM resumes from there.

This is the "ask the user something" pattern from Anthropic's
computer-use + OpenAI's Assistants — same shape, just spelled with our
own tool names so we can render them with custom UI.

When to use which tool (the LLM is told this in the system prompt):

* ``request_user_choice`` — multiple-choice questions ("Qual fatura?",
  "Devolução ou ajuste?"). Avoid free-text when a closed list works.
* ``request_user_confirmation`` — irreversible-ish actions ("Posso
  considerar essa NF como cancelada nas próximas perguntas?"). Two
  options by default (``confirm`` / ``cancel``).

Add new ones here as the UX needs them; the frontend renders any tool
in :data:`UI_TOOL_NAMES` with action buttons (others stay as the
default "tool: <name>" pill).
"""
from __future__ import annotations

from typing import Any

from mcp_server.tools import ToolDef


REQUEST_USER_CHOICE = "request_user_choice"
REQUEST_USER_CONFIRMATION = "request_user_confirmation"


# These tool names short-circuit the runtime loop — the next iteration
# requires the user's response, not another LLM call.
UI_TOOL_NAMES: frozenset[str] = frozenset({
    REQUEST_USER_CHOICE,
    REQUEST_USER_CONFIRMATION,
})


# Result blob persisted as the function_call_output for any UI tool.
# Carries no data — the user's reply is what matters.
PLACEHOLDER_RESULT: dict[str, Any] = {"status": "awaiting_user_response"}


def _request_user_choice() -> ToolDef:
    return ToolDef(
        name=REQUEST_USER_CHOICE,
        description=(
            "Faça uma pergunta de múltipla escolha ao usuário. Use isto "
            "quando a próxima decisão depende de uma escolha entre alternativas "
            "claras (ex: qual fatura, qual período, qual relacionamento). "
            "NÃO use para sim/não — para isso, use request_user_confirmation."
        ),
        handler=lambda **kwargs: PLACEHOLDER_RESULT,  # never actually called
        input_schema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Pergunta exibida ao usuário (1-2 frases).",
                },
                "options": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Texto do botão."},
                            "value": {"type": "string", "description": "Valor enviado de volta na resposta do usuário."},
                            "description": {"type": "string", "description": "Texto secundário curto (opcional)."},
                            "variant": {
                                "type": "string",
                                "enum": ["primary", "secondary", "destructive"],
                                "description": "Estilo do botão. Default: secondary.",
                            },
                        },
                        "required": ["label", "value"],
                    },
                },
            },
            "required": ["question", "options"],
        },
    )


def _request_user_confirmation() -> ToolDef:
    return ToolDef(
        name=REQUEST_USER_CONFIRMATION,
        description=(
            "Peça uma confirmação binária ao usuário antes de prosseguir "
            "com algo que tenha consequência (ex: assumir uma premissa, "
            "executar uma análise demorada, considerar um caso resolvido). "
            "Mais leve que request_user_choice quando a resposta é sim/não."
        ),
        handler=lambda **kwargs: PLACEHOLDER_RESULT,
        input_schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "O que o agente pretende fazer / assumir, em 1 frase.",
                },
                "confirm_label": {
                    "type": "string",
                    "description": "Rótulo do botão de confirmação. Default: 'Sim, prosseguir'.",
                },
                "cancel_label": {
                    "type": "string",
                    "description": "Rótulo do botão de cancelar. Default: 'Não'.",
                },
            },
            "required": ["action"],
        },
    )


UI_TOOLS: tuple[ToolDef, ...] = (
    _request_user_choice(),
    _request_user_confirmation(),
)


def is_ui_tool(name: str) -> bool:
    return name in UI_TOOL_NAMES
