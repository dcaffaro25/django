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
from collections.abc import Iterator
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


# Tools that don't need company_id — tenant-agnostic by design.
# ``list_companies`` is cross-tenant; the rest hit external public APIs
# (Receita Federal via BrasilAPI, BCB SGS, IBGE) or are pure local
# lookups (CFOP, Simples Nacional anexos).
TOOLS_WITHOUT_COMPANY_ID = {
    "list_companies",
    "fetch_cnpj_from_receita",
    "fetch_bcb_indicator",
    "fetch_ptax",
    "fetch_cep",
    "fetch_holidays_brazil",
    "fetch_bank_by_code",
    "fetch_ncm",
    "fetch_cnae_info",
    "validate_cfop",
    "simples_nacional_annex_for_cnae",
    # Meta-API tools — they take ``method``/``path``, not ``company_id``.
    # Tenant + acting-user context are injected separately below.
    "discover_api",
    "call_internal_api",
}

# Tools that need the conversation's tenant slug and acting user injected.
# We force-override these to prevent the agent from passing a different
# tenant in the URL path (and to spare the LLM from having to remember
# which user it is).
TOOLS_REQUIRING_AGENT_CONTEXT = {"call_internal_api"}


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

        # Token-budget gate — Phase 0 expansion. Reject the new turn
        # cleanly before we burn another LLM call.
        enforce_cumulative_budget = bool(
            getattr(settings, "AGENT_ENFORCE_CUMULATIVE_TOKEN_BUDGET", False)
        )
        budget = int(getattr(settings, "AGENT_TOKEN_BUDGET_PER_CONVERSATION", 0) or 0)
        if enforce_cumulative_budget and budget > 0:
            from django.db.models import Sum
            agg = self.conversation.messages.aggregate(
                p=Sum("prompt_tokens"), c=Sum("completion_tokens"),
            )
            used = (agg.get("p") or 0) + (agg.get("c") or 0)
            if used >= budget:
                cap_msg = self._persist_assistant_final(
                    assistant_text_items=[],
                    content_override=(
                        f"Esta conversa já consumiu {used:,} tokens, acima do "
                        f"orçamento configurado de {budget:,}. Comece uma nova "
                        f"conversa para continuar — o histórico ficará disponível "
                        f"aqui mas não será mais expandido."
                    ),
                    model_used="", usage={},
                )
                self._touch_conversation()
                return AgentTurnResult(
                    final_message=cap_msg,
                    intermediate_messages=intermediates,
                    iterations=0,
                    truncated=True,
                )

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

            # Hosted web_search calls arrive as their own item type. They're
            # handled entirely upstream — the model already gets the results
            # back inline before we see the response. We only log so the
            # operator can confirm the experiment is firing.
            web_search_calls = [
                item for item in output_items if item.get("type") == "web_search_call"
            ]
            if web_search_calls:
                log.info(
                    "agent.web_search_invoked conv=%s queries=%s",
                    self.conversation.id,
                    [c.get("query") or c.get("action", {}).get("query") for c in web_search_calls],
                )

            # Diagnostic: Codex occasionally returns only reasoning items
            # (no message, no function_call) — usually with reasoning models
            # on trivial prompts. Without this log, the only symptom is a
            # blank assistant bubble with token counts populated, which is
            # genuinely confusing. Log the item shape so we can tell.
            if not tool_calls_in_turn and not assistant_text_items and output_items:
                log.warning(
                    "agent.empty_assistant_response conv=%s types=%s usage=%s",
                    self.conversation.id,
                    [it.get("type") for it in output_items],
                    usage,
                )

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
                        intermediates.append(self._dispatch_tool_call(call, iteration=iteration))

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

            # No tool calls → this is the final assistant turn. If the
            # message items don't yield text (or there are none at all),
            # surface the reasoning summary or a clear fallback so the
            # user never sees the empty "..." bubble that consumed tokens.
            extracted = _extract_text_from_items(assistant_text_items)
            content_override: str | None = None
            if not extracted and output_items:
                reasoning_text = _extract_reasoning_summary(output_items)
                if reasoning_text:
                    content_override = reasoning_text
                else:
                    content_override = (
                        "(O modelo não retornou texto. Tente reformular a pergunta "
                        "ou trocar o modelo.)"
                    )

            final = self._persist_assistant_final(
                assistant_text_items=assistant_text_items,
                model_used=model_used, usage=usage,
                content_override=content_override,
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
    # Streaming entrypoint -- mirrors :meth:`run_turn` but yields one
    # event per persisted message + lifecycle marker. The view layer
    # frames each event as Server-Sent Events. The shape mirrors the
    # eventual cache shape on the client (every event carries the
    # serialized AgentMessage in ``_message`` for the view to swap with
    # the serializer output -- keeps the runtime free of DRF imports).
    # ------------------------------------------------------------------
    def run_turn_stream(
        self, *, user_message: AgentMessage,
    ) -> Iterator[dict[str, Any]]:
        # Token-budget gate -- same as :meth:`run_turn`.
        enforce_cumulative_budget = bool(
            getattr(settings, "AGENT_ENFORCE_CUMULATIVE_TOKEN_BUDGET", False)
        )
        budget = int(getattr(settings, "AGENT_TOKEN_BUDGET_PER_CONVERSATION", 0) or 0)
        if enforce_cumulative_budget and budget > 0:
            from django.db.models import Sum
            agg = self.conversation.messages.aggregate(
                p=Sum("prompt_tokens"), c=Sum("completion_tokens"),
            )
            used = (agg.get("p") or 0) + (agg.get("c") or 0)
            if used >= budget:
                cap_msg = self._persist_assistant_final(
                    assistant_text_items=[],
                    content_override=(
                        f"Esta conversa já consumiu {used:,} tokens, acima do "
                        f"orçamento configurado de {budget:,}. Comece uma nova "
                        f"conversa para continuar — o histórico ficará disponível "
                        f"aqui mas não será mais expandido."
                    ),
                    model_used="", usage={},
                )
                self._touch_conversation()
                yield {"type": "message", "_message": cap_msg}
                yield {"type": "final", "iterations": 0, "truncated": True}
                return

        for iteration in range(1, self._max_iterations + 1):
            yield {"type": "iteration", "n": iteration}
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
            web_search_calls = [
                item for item in output_items if item.get("type") == "web_search_call"
            ]
            if web_search_calls:
                log.info(
                    "agent.web_search_invoked conv=%s queries=%s",
                    self.conversation.id,
                    [c.get("query") or c.get("action", {}).get("query") for c in web_search_calls],
                )

            if not tool_calls_in_turn and not assistant_text_items and output_items:
                log.warning(
                    "agent.empty_assistant_response conv=%s types=%s usage=%s",
                    self.conversation.id,
                    [it.get("type") for it in output_items],
                    usage,
                )

            if tool_calls_in_turn:
                request_msg = self._persist_assistant_tool_request(
                    assistant_text_items=assistant_text_items,
                    tool_calls=tool_calls_in_turn,
                    model_used=model_used,
                    usage=usage,
                )

                ui_calls: list[dict[str, Any]] = []
                ui_request_msg: AgentMessage | None = None
                # Surface the tool-request as a streamed event so the UI
                # can render the "calling tool" pill before the result
                # arrives. For UI-tool turns we hold off until after the
                # placeholder so the operator sees the question and the
                # placeholder atomically.
                if any(ui_tools.is_ui_tool(call.get("name", "")) for call in tool_calls_in_turn):
                    ui_request_msg = request_msg
                else:
                    yield {"type": "message", "_message": request_msg}

                placeholders: list[AgentMessage] = []
                for call in tool_calls_in_turn:
                    if ui_tools.is_ui_tool(call.get("name", "")):
                        placeholder = self._persist_ui_placeholder(call)
                        placeholders.append(placeholder)
                        ui_calls.append(call)
                    else:
                        result_msg = self._dispatch_tool_call(call, iteration=iteration)
                        yield {"type": "message", "_message": result_msg}

                if ui_calls:
                    # The "final" message in this branch is the assistant
                    # turn carrying the function_call(s), not a placeholder
                    # -- the widget renders action buttons on it. Emit it
                    # last so the client picks up the placeholders first
                    # (keeps the OpenAI API contract intact for the next
                    # turn) and then sees the actionable assistant turn.
                    for placeholder in placeholders:
                        yield {"type": "message", "_message": placeholder}
                    if ui_request_msg is not None:
                        yield {"type": "message", "_message": ui_request_msg}
                    self._touch_conversation()
                    yield {"type": "final", "iterations": iteration, "truncated": False}
                    return
                continue  # only data tools — loop back to the LLM

            extracted = _extract_text_from_items(assistant_text_items)
            content_override: str | None = None
            if not extracted and output_items:
                reasoning_text = _extract_reasoning_summary(output_items)
                if reasoning_text:
                    content_override = reasoning_text
                else:
                    content_override = (
                        "(O modelo não retornou texto. Tente reformular a pergunta "
                        "ou trocar o modelo.)"
                    )

            final = self._persist_assistant_final(
                assistant_text_items=assistant_text_items,
                model_used=model_used, usage=usage,
                content_override=content_override,
            )
            self._touch_conversation()
            yield {"type": "message", "_message": final}
            yield {"type": "final", "iterations": iteration, "truncated": False}
            return

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
        yield {"type": "message", "_message": cap_msg}
        yield {"type": "final", "iterations": self._max_iterations, "truncated": True}

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------
    def _dispatch_tool_call(self, call: dict[str, Any], *, iteration: int = 0) -> AgentMessage:
        """Execute one tool call and persist the result. The Responses API
        wraps each tool request as ``{type:"function_call", call_id, name,
        arguments: "<json string>"}``.

        Each call is audited via :func:`agent.services.audit.log_tool_call`
        — Phase 0. The audit row captures latency, status, error type +
        truncated message, response size, and iteration number. PII risk
        is bounded by ``args_summary`` truncation; full args are not
        persisted."""
        from mcp_server.tools import call_tool, get_tool_domain
        from agent.services.audit import log_tool_call

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

        # Inject conversation context for tools that need to dispatch as
        # the user inside the conversation's tenant. Force-overrides any
        # value the LLM may have supplied for these underscore-prefixed
        # parameters — they're internal contract, not user-facing args.
        if name in TOOLS_REQUIRING_AGENT_CONTEXT:
            args["_tenant_slug"] = getattr(self.company, "subdomain", "") or ""
            args["_acting_user_id"] = self.conversation.user_id

        from agent.services.rate_limit import check_rate_limit

        with log_tool_call(
            company=self.company,
            conversation=self.conversation,
            user=getattr(self.conversation, "user", None),
            tool_name=name,
            tool_domain=get_tool_domain(name),
            args=args,
            iteration=iteration,
        ) as audit_ctx:
            # Rate limit check first — keeps a runaway loop bounded
            # without consuming the actual tool's compute budget.
            limit_err = check_rate_limit(tool_name=name, company_id=self.company.id)
            if limit_err is not None:
                result = limit_err
                audit_ctx["status_override"] = "rejected"
            else:
                try:
                    result = call_tool(name, args)
                except KeyError:
                    result = {"error": f"Tool '{name}' is not available."}
                except Exception as exc:  # pragma: no cover — defensive net
                    log.exception("agent.tool_failed name=%s: %s", name, exc)
                    result = {"error": f"{type(exc).__name__}: {exc}"}
            audit_ctx["result"] = result

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
        about which is which (we short-circuit on UI tools).

        Also appends the hosted ``web_search`` tool when
        ``AGENT_ENABLE_WEB_SEARCH`` is set. The Codex backend may 400 on
        unsupported hosted tools depending on plan/originator — see the
        setting's docstring.

        Tool catalog is filtered by ``AGENT_DISABLED_TOOLS`` and
        ``AGENT_DISABLED_DOMAINS`` to keep token cost down and let
        operators feature-gate at the env-var level. UI tools are
        never filtered — they're load-bearing for the
        request_user_choice / confirmation pattern."""
        from mcp_server.tools import TOOLS as MCP_TOOLS

        disabled_tools = set(getattr(settings, "AGENT_DISABLED_TOOLS", []) or [])
        disabled_domains = set(getattr(settings, "AGENT_DISABLED_DOMAINS", []) or [])

        catalog: list[dict[str, Any]] = []
        for t in MCP_TOOLS:
            if t.name in disabled_tools:
                continue
            if getattr(t, "domain", "") in disabled_domains:
                continue
            catalog.append({
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
                "strict": False,
            })
        # UI tools are unconditional.
        for t in ui_tools.UI_TOOLS:
            catalog.append({
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
                "strict": False,
            })
        if getattr(settings, "AGENT_ENABLE_WEB_SEARCH", False):
            catalog.append({"type": "web_search"})
        return catalog

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

            user msg          → {"role":"user","content":[{"type":"input_text","text":"..."}, ...]}
            assistant text    → {"role":"assistant","content":[{"type":"output_text","text":"..."}]}
            assistant tool    → list of {"type":"function_call","call_id","name","arguments"}
            tool result       → {"type":"function_call_output","call_id","output":"<json>"}

        User messages can carry attachments — Phase 2. Each attachment
        becomes an additional content part on the same user item:
        ``input_image`` for PDFs/images, ``input_text`` for parsed XML
        and OFX (the structured fields are easier for the LLM than raw
        markup).

        Note: the system prompt is sent via the top-level ``instructions``
        field (not in the input list) per the Responses API spec.
        """
        out: list[dict[str, Any]] = []

        # Pre-fetch attachments grouped by message id so we don't N+1
        # the history loop. Only inspect user messages — assistant
        # turns never carry attachments.
        from agent.models import AgentMessageAttachment
        attachments_by_msg: dict[int, list[AgentMessageAttachment]] = {}
        for att in AgentMessageAttachment.objects.filter(
            conversation=self.conversation, message__isnull=False,
        ).order_by("created_at", "id"):
            attachments_by_msg.setdefault(att.message_id, []).append(att)

        history = list(
            self.conversation.messages.order_by("created_at", "id").values(
                "id", "role", "content", "tool_calls", "tool_call_id", "tool_name",
            )
        )
        newest_user_id = max(
            (int(row["id"]) for row in history if row["role"] == AgentMessage.ROLE_USER),
            default=0,
        )

        for row in history:
            role = row["role"]
            content = row["content"] or ""

            if role == AgentMessage.ROLE_USER:
                parts: list[dict[str, Any]] = [{"type": "input_text", "text": content}]
                for att in attachments_by_msg.get(row["id"], []):
                    part = self._attachment_to_content_part(att)
                    if part is not None:
                        parts.append(part)
                out.append({"role": "user", "content": parts})
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
                if int(row["id"]) < newest_user_id:
                    content = _compact_historical_tool_output(
                        tool_name=row["tool_name"] or "",
                        content=content,
                    )
                out.append({
                    "type": "function_call_output",
                    "call_id": row["tool_call_id"] or "",
                    "output": content,
                })
                continue

            # ROLE_SYSTEM is sent via instructions; ignore here.
        return out

    def _attachment_to_content_part(self, attachment) -> dict[str, Any] | None:
        """Convert an ``AgentMessageAttachment`` row into a Responses-API
        content part — Phase 2.

        * NF-e XML / OFX  → ``input_text`` containing the cached
          ``extracted_text`` (set by the ``ingest_document`` tool the
          first time it runs against this attachment). If extraction
          hasn't happened yet, the part is a short hint asking the
          model to call ``ingest_document``.
        * PDF / image     → ``input_image`` with a base64 data-URL.
          Codex multimodal handles OCR + layout.
        * Other           → None (skipped, with a hint emitted as text).
        """
        from agent.models import AgentMessageAttachment

        if attachment.kind in (
            AgentMessageAttachment.KIND_NFE_XML,
            AgentMessageAttachment.KIND_OFX,
        ):
            text = attachment.extracted_text or (
                f"[Anexo {attachment.filename!r} ({attachment.kind}) ainda não "
                f"foi processado. Chame ingest_document(attachment_id="
                f"{attachment.id}) para extrair o conteúdo.]"
            )
            return {"type": "input_text", "text": text}

        if attachment.kind in (AgentMessageAttachment.KIND_PDF, AgentMessageAttachment.KIND_IMAGE):
            try:
                import base64
                with attachment.file.open("rb") as fh:
                    raw = fh.read()
                ct = attachment.content_type or (
                    "application/pdf" if attachment.kind == AgentMessageAttachment.KIND_PDF
                    else "image/png"
                )
                data_url = f"data:{ct};base64,{base64.b64encode(raw).decode('ascii')}"
                return {"type": "input_image", "image_url": data_url}
            except Exception as exc:
                log.warning(
                    "agent.attachment.read_failed id=%s err=%s",
                    attachment.id, exc,
                )
                return {
                    "type": "input_text",
                    "text": (
                        f"[Falha ao ler o anexo {attachment.filename!r}: {exc}]"
                    ),
                }

        # KIND_OTHER or unknown — surface as a tiny hint.
        return {
            "type": "input_text",
            "text": (
                f"[Anexo {attachment.filename!r} ({attachment.content_type or '?'}) "
                f"não é suportado.]"
            ),
        }

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


def _compact_historical_tool_output(*, tool_name: str, content: str) -> str:
    """Shrink older tool outputs before sending them back to the model.

    The full payload stays in the database for UI inspection. The next turn
    only needs a compact reminder; otherwise tables returned by tools get
    resent on every request and quickly dominate the context window.
    """
    limit = int(getattr(settings, "AGENT_HISTORY_TOOL_OUTPUT_CHARS", 1800))
    if limit <= 0 or len(content) <= limit:
        return content

    summary: dict[str, Any] = {
        "tool": tool_name,
        "historical_output_compacted": True,
        "original_chars": len(content),
    }
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        summary["preview"] = content[:limit]
        return json.dumps(summary, ensure_ascii=False, default=str)

    if isinstance(parsed, dict):
        summary["keys"] = list(parsed.keys())[:20]
        for key in ("count", "ok", "error", "status", "run_id", "dry_run_effective"):
            if key in parsed:
                summary[key] = parsed[key]
        for key, value in parsed.items():
            if isinstance(value, list):
                summary[f"{key}_count"] = len(value)
                if value:
                    summary[f"{key}_sample"] = value[:2]
            elif isinstance(value, dict) and key in ("counters", "totals", "summary"):
                summary[key] = value
    elif isinstance(parsed, list):
        summary["items_count"] = len(parsed)
        summary["items_sample"] = parsed[:2]
    else:
        summary["preview"] = str(parsed)[:limit]

    dumped = json.dumps(summary, ensure_ascii=False, default=str)
    if len(dumped) > limit:
        summary.pop("rows_sample", None)
        summary.pop("results_sample", None)
        summary["preview"] = dumped[:limit]
        dumped = json.dumps(summary, ensure_ascii=False, default=str)
    return dumped


def _extract_reasoning_summary(items: list[dict[str, Any]]) -> str:
    """Last-resort text extraction from ``reasoning`` items.

    When Codex returns only reasoning (no ``message``) we'd otherwise
    persist an empty assistant bubble. Reasoning items carry a
    ``summary`` array of ``{type:"summary_text", text:"..."}`` parts;
    surfacing that gives the user *something* visible while keeping
    the turn shape unchanged. Joined with newlines if multiple."""
    chunks: list[str] = []
    for item in items:
        if item.get("type") != "reasoning":
            continue
        summary = item.get("summary")
        if not isinstance(summary, list):
            continue
        for part in summary:
            if not isinstance(part, dict):
                continue
            text = part.get("text") or ""
            if text and part.get("type") in ("summary_text", "text", "output_text"):
                chunks.append(text)
    return "\n".join(chunks)
