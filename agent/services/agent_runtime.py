"""Sysnord agent runtime — the LLM ↔ MCP-tools loop on Codex Responses API.

Per turn:

1. Load the conversation's prior messages (already includes assistant +
   tool sidecar rows from previous turns).
2. Translate them into the Responses API ``input`` array — a flat list
   of typed items: ``{role,content}`` for user/assistant text,
   ``{type:"function_call", call_id, name, arguments}`` for previous
   tool requests, ``{type:"function_call_output", call_id, output}`` for
   results.
3. Call :class:`OpenAIClient.respond` with ``instructions`` (the system
   prompt) + that input + the MCP tool catalog.
4. Walk the response ``output`` items: any ``function_call`` item ⇒
   execute the tool and persist a ``tool`` :class:`AgentMessage`; any
   ``message`` item ⇒ persist as an assistant message.
5. If we consumed any tool calls this iteration, loop back to step 2;
   otherwise the message is final and we return.

Iteration cap: :data:`settings.AGENT_MAX_TOOL_ITERATIONS`.

Tenant scoping: ``company_id`` on every tool call is overwritten to
``conversation.company_id`` — the LLM cannot read another tenant's
data even if a prompt smuggles a different value.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from agent.models import AgentConversation, AgentMessage
from agent.services import ui_tools
from agent.services.openai_client import (
    OpenAIClient,
    OpenAIClientError,
    OpenAINotConnected,
    OpenAIReconnectRequired,
    build_tool_specs,
)

log = logging.getLogger(__name__)


SYSTEM_PROMPT_TEMPLATE = """\
Você é o assistente interno do Sysnord, uma plataforma de contabilidade,
fiscal (NFe) e conciliação bancária multi-tenant. O usuário atual está
operando dentro do tenant **{tenant_subdomain}** (id={company_id}).

Você tem acesso a um conjunto de ferramentas read-only que consultam o
banco de dados do Sysnord. Use-as livremente para responder perguntas com
dados reais — nunca invente números. Se uma ferramenta retornar `error`,
informe o usuário e ofereça uma alternativa.

Convenções:
- Toda chamada de ferramenta de dados deve usar `company_id={company_id}`.
  O sistema sobrescreve esse argumento por segurança.
- Valores monetários são em BRL salvo indicação contrária.
- Datas no formato ISO (YYYY-MM-DD).
- Você NÃO pode criar, atualizar ou deletar dados nesta versão.

Quando precisar da decisão do usuário antes de prosseguir, use as
**ferramentas de UI**:
- `request_user_choice` para perguntas com 2-6 alternativas claras
  (qual fatura, qual período, qual relacionamento). NÃO invente
  alternativas — só use se houver opções reais que você possa derivar
  dos dados.
- `request_user_confirmation` para sim/não antes de assumir uma premissa
  ou rodar uma análise demorada.
Após chamar uma dessas, PARE — o sistema renderiza botões e o usuário
responderá na próxima mensagem. Não tente seguir adivinhando.

Responda em **português** salvo se o usuário escrever em outro idioma.
Seja conciso; mostre tabelas quando ajudar a leitura.{page_context_block}
"""


PAGE_CONTEXT_BLOCK_TEMPLATE = """

[CONTEXTO DA TELA ATUAL]
O usuário está atualmente em **{title}** (rota `{route}`). {summary}
{data_block}
"""


# Tools that don't need company_id — list_companies is the only one.
TOOLS_WITHOUT_COMPANY_ID = {"list_companies"}


@dataclass
class AgentTurnResult:
    final_message: AgentMessage
    intermediate_messages: list[AgentMessage] = field(default_factory=list)
    iterations: int = 0
    truncated: bool = False


class AgentRuntimeError(RuntimeError):
    """Catch-all for runtime failures the operator should see verbatim."""


class SysnordAgent:
    """One agent run for one conversation. Construct per-turn (cheap).

    Per-conversation knobs (``model``, ``reasoning_effort``) are read from
    the :class:`AgentConversation` row. Per-turn knobs (``page_context``)
    are passed at construction. The system prompt is regenerated each
    turn so changes to either propagate without editing history.
    """

    def __init__(
        self,
        conversation: AgentConversation,
        *,
        page_context: dict[str, Any] | None = None,
    ):
        self.conversation = conversation
        self.company = conversation.company
        self.client = OpenAIClient()
        self._max_iterations = int(
            getattr(settings, "AGENT_MAX_TOOL_ITERATIONS", 8)
        )
        # Stable session_id per conversation — Codex uses it for
        # prompt caching across turns.
        self._session_id = f"sysnord:conv:{conversation.id}"
        # Page context only honoured if the conversation opted in.
        self._page_context = (
            page_context if conversation.include_page_context else None
        )

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    def run_turn(self, *, user_message: AgentMessage) -> AgentTurnResult:
        intermediates: list[AgentMessage] = []

        for iteration in range(1, self._max_iterations + 1):
            input_items = self._build_input_items()
            tools = self._build_tool_catalog()

            try:
                response = self.client.respond(
                    instructions=self._system_prompt(),
                    input_items=input_items,
                    tools=tools,
                    session_id=self._session_id,
                    model=self.conversation.model or None,
                    reasoning_effort=self.conversation.reasoning_effort or None,
                )
            except (OpenAINotConnected, OpenAIReconnectRequired) as exc:
                raise AgentRuntimeError(str(exc)) from exc
            except OpenAIClientError as exc:
                raise AgentRuntimeError(f"OpenAI call failed: {exc}") from exc

            output_items = response.get("output") or []
            usage = response.get("usage") or {}
            model_used = response.get("model") or ""

            tool_calls_in_turn = [
                item for item in output_items if item.get("type") == "function_call"
            ]
            assistant_text_items = [
                item for item in output_items if item.get("type") == "message"
            ]

            if tool_calls_in_turn:
                # Persist the assistant turn that requested the tool calls
                # so the next iteration picks them up from history.
                request_msg = self._persist_assistant_tool_request(
                    assistant_text_items=assistant_text_items,
                    tool_calls=tool_calls_in_turn,
                    model_used=model_used,
                    usage=usage,
                )
                intermediates.append(request_msg)

                # Persist a result row for every tool call (including UI
                # tools, which get a placeholder so the API contract for
                # the *next* call stays valid).
                ui_calls: list[dict[str, Any]] = []
                for call in tool_calls_in_turn:
                    if ui_tools.is_ui_tool(call.get("name", "")):
                        ui_calls.append(call)
                        intermediates.append(self._persist_ui_placeholder(call))
                    else:
                        intermediates.append(self._dispatch_tool_call(call))

                if ui_calls:
                    # Terminal: hand control to the user. The "final"
                    # message returned to the frontend is the assistant
                    # turn carrying the function_call(s) — that's what
                    # the widget renders the action buttons on.
                    self._touch_conversation()
                    # Drop the assistant request_msg from intermediates
                    # since we're returning it as final.
                    intermediates.remove(request_msg)
                    return AgentTurnResult(
                        final_message=request_msg,
                        intermediate_messages=intermediates,
                        iterations=iteration,
                        truncated=False,
                    )
                continue  # only normal data tools — loop back to the LLM

            # No tool calls → this is the final assistant turn.
            final = self._persist_assistant_final(
                assistant_text_items=assistant_text_items,
                model_used=model_used, usage=usage,
            )
            self._touch_conversation()
            return AgentTurnResult(
                final_message=final,
                intermediate_messages=intermediates,
                iterations=iteration,
                truncated=False,
            )

        # Iteration cap reached
        cap_msg = self._persist_assistant_final(
            assistant_text_items=[],
            content_override=(
                "Atingi o limite de iterações de ferramentas sem produzir "
                "uma resposta final. Refine sua pergunta ou aumente "
                "AGENT_MAX_TOOL_ITERATIONS."
            ),
            model_used="", usage={},
        )
        self._touch_conversation()
        return AgentTurnResult(
            final_message=cap_msg,
            intermediate_messages=intermediates,
            iterations=self._max_iterations,
            truncated=True,
        )

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------
    def _dispatch_tool_call(self, call: dict[str, Any]) -> AgentMessage:
        """Execute one tool call and persist the result. The Responses API
        wraps each tool request as ``{type:"function_call", call_id, name,
        arguments: "<json string>"}``."""
        from mcp_server.tools import call_tool

        call_id = call.get("call_id") or call.get("id") or ""
        name = call.get("name") or ""
        raw_args = call.get("arguments") or "{}"

        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except (TypeError, ValueError):
            args = {}

        # Tenant guardrail: overwrite company_id before invoking.
        if name not in TOOLS_WITHOUT_COMPANY_ID:
            args["company_id"] = self.company.id

        try:
            result = call_tool(name, args)
        except KeyError:
            result = {"error": f"Tool '{name}' is not available."}
        except Exception as exc:  # pragma: no cover — defensive net
            log.exception("agent.tool_failed name=%s: %s", name, exc)
            result = {"error": f"{type(exc).__name__}: {exc}"}

        return AgentMessage.objects.create(
            company=self.company,
            conversation=self.conversation,
            role=AgentMessage.ROLE_TOOL,
            content=json.dumps(result, default=str),
            tool_call_id=call_id,
            tool_name=name,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    @transaction.atomic
    def _persist_assistant_tool_request(
        self,
        *,
        assistant_text_items: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]],
        model_used: str,
        usage: dict[str, Any],
    ) -> AgentMessage:
        return AgentMessage.objects.create(
            company=self.company,
            conversation=self.conversation,
            role=AgentMessage.ROLE_ASSISTANT,
            content=_extract_text_from_items(assistant_text_items),
            tool_calls=tool_calls,
            model_used=model_used,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
        )

    @transaction.atomic
    def _persist_assistant_final(
        self,
        *,
        assistant_text_items: list[dict[str, Any]],
        model_used: str,
        usage: dict[str, Any],
        content_override: str | None = None,
    ) -> AgentMessage:
        content = (
            content_override
            if content_override is not None
            else _extract_text_from_items(assistant_text_items)
        )
        return AgentMessage.objects.create(
            company=self.company,
            conversation=self.conversation,
            role=AgentMessage.ROLE_ASSISTANT,
            content=content,
            tool_calls=[],
            model_used=model_used,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
        )

    def _persist_ui_placeholder(self, call: dict[str, Any]) -> AgentMessage:
        """Synthetic ``tool`` row for a UI tool call (request_user_choice
        etc). Carries no real result — the user's next reply is what
        matters — but keeps the OpenAI API contract intact for subsequent
        calls (every ``function_call`` needs a matching
        ``function_call_output``)."""
        call_id = call.get("call_id") or call.get("id") or ""
        name = call.get("name") or ""
        return AgentMessage.objects.create(
            company=self.company,
            conversation=self.conversation,
            role=AgentMessage.ROLE_TOOL,
            content=json.dumps(ui_tools.PLACEHOLDER_RESULT),
            tool_call_id=call_id,
            tool_name=name,
        )

    def _build_tool_catalog(self) -> list[dict[str, Any]]:
        """Combine MCP data tools with the virtual UI tools. The Codex
        Responses API treats them uniformly — only the runtime cares
        about which is which (we short-circuit on UI tools)."""
        from mcp_server.tools import TOOLS as MCP_TOOLS

        tool_defs = list(MCP_TOOLS) + list(ui_tools.UI_TOOLS)
        return [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
                "strict": False,
            }
            for t in tool_defs
        ]

    def _touch_conversation(self) -> None:
        AgentConversation.objects.filter(id=self.conversation.id).update(
            updated_at=timezone.now()
        )

    # ------------------------------------------------------------------
    # History → Responses API input
    # ------------------------------------------------------------------
    def _build_input_items(self) -> list[dict[str, Any]]:
        """Materialise the ``input`` array for the Responses API.

        Each prior history row becomes one or more typed items::

            user msg          → {"role":"user","content":[{"type":"input_text","text":"..."}]}
            assistant text    → {"role":"assistant","content":[{"type":"output_text","text":"..."}]}
            assistant tool    → list of {"type":"function_call","call_id","name","arguments"}
            tool result       → {"type":"function_call_output","call_id","output":"<json>"}

        Note: the system prompt is sent via the top-level ``instructions``
        field (not in the input list) per the Responses API spec.
        """
        out: list[dict[str, Any]] = []

        history = list(
            self.conversation.messages.order_by("created_at", "id").values(
                "role", "content", "tool_calls", "tool_call_id", "tool_name",
            )
        )
        for row in history:
            role = row["role"]
            content = row["content"] or ""

            if role == AgentMessage.ROLE_USER:
                out.append({
                    "role": "user",
                    "content": [{"type": "input_text", "text": content}],
                })
                continue

            if role == AgentMessage.ROLE_ASSISTANT:
                # Assistant turns can carry both text content and tool calls.
                # The Responses API accepts them as separate items in order.
                if content:
                    out.append({
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": content}],
                    })
                for call in row["tool_calls"] or []:
                    if not isinstance(call, dict):
                        continue
                    out.append({
                        "type": "function_call",
                        "call_id": call.get("call_id") or call.get("id") or "",
                        "name": call.get("name", ""),
                        "arguments": call.get("arguments") or "{}",
                    })
                continue

            if role == AgentMessage.ROLE_TOOL:
                out.append({
                    "type": "function_call_output",
                    "call_id": row["tool_call_id"] or "",
                    "output": content,
                })
                continue

            # ROLE_SYSTEM is sent via instructions; ignore here.
        return out

    def _system_prompt(self) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(
            tenant_subdomain=getattr(self.company, "subdomain", "?"),
            company_id=self.company.id,
            page_context_block=self._page_context_block(),
        )

    def _page_context_block(self) -> str:
        ctx = self._page_context
        if not ctx or not isinstance(ctx, dict):
            return ""
        title = str(ctx.get("title") or "?")[:120]
        route = str(ctx.get("route") or "?")[:120]
        summary = str(ctx.get("summary") or "")[:600]
        data = ctx.get("data")
        if isinstance(data, (dict, list)) and data:
            try:
                data_dump = json.dumps(data, default=str)[:1500]
                data_block = f"Dados estruturados na tela:\n```json\n{data_dump}\n```"
            except (TypeError, ValueError):
                data_block = ""
        else:
            data_block = ""
        return PAGE_CONTEXT_BLOCK_TEMPLATE.format(
            title=title, route=route, summary=summary, data_block=data_block,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_text_from_items(items: list[dict[str, Any]]) -> str:
    """Pull the concatenated text out of ``message`` items in a Responses
    API output. Each ``message`` item carries a ``content`` array of typed
    parts; we keep ``output_text`` (and tolerate ``text`` as fallback)."""
    chunks: list[str] = []
    for item in items:
        content = item.get("content")
        if isinstance(content, str):
            chunks.append(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type", "")
            text = part.get("text") or ""
            if ptype in ("output_text", "text", "input_text") and text:
                chunks.append(text)
    return "".join(chunks)
