"""Sysnord agent runtime — the LLM ↔ MCP-tools loop.

Per turn:

1. Load the conversation's prior messages (already includes assistant +
   tool sidecar rows from previous turns).
2. Call :class:`OpenAIClient` with the full message history + the tool
   catalog from :mod:`mcp_server.tools`.
3. If the LLM responded with ``tool_calls``: execute each via
   ``mcp_server.tools.call_tool``, persist one ``tool`` :class:`AgentMessage`
   per call, then loop back to step 2.
4. If the LLM responded with plain content: persist one ``assistant``
   :class:`AgentMessage` and return.

Iteration cap is :data:`settings.AGENT_MAX_TOOL_ITERATIONS` so a misbehaving
LLM can't burn quota in an infinite tool-call loop.

Tenant scoping happens here: the runtime injects ``company_id`` into every
tool call (taken from ``conversation.company_id``) — the LLM never has to
*know* the tenant, and a malicious prompt can't ask for another tenant's
data because we just overwrite that argument.
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
informe o usuário e ofereça uma alternativa (consulta diferente, filtro,
etc.).

Convenções:
- Toda chamada de ferramenta deve usar `company_id={company_id}`. O
  sistema sobrescreve esse argumento por segurança, mas inclua-o
  explicitamente.
- Valores monetários são em BRL salvo indicação contrária.
- Datas no formato ISO (YYYY-MM-DD).
- Você NÃO pode criar, atualizar ou deletar dados nesta versão. Se o
  usuário pedir uma ação que requer escrita, explique que ainda não está
  habilitado.

Responda em **português** salvo se o usuário escrever em outro idioma.
Seja conciso; mostre tabelas quando ajudar a leitura.
"""


# Tools that don't need company_id — list_companies is the only one. We
# pass ``None`` to it as the override and the dispatcher tolerates an
# empty kwargs dict.
TOOLS_WITHOUT_COMPANY_ID = {"list_companies"}


@dataclass
class AgentTurnResult:
    """Returned by :meth:`SysnordAgent.run_turn`."""

    final_message: AgentMessage
    intermediate_messages: list[AgentMessage] = field(default_factory=list)
    iterations: int = 0
    truncated: bool = False  # True if we hit AGENT_MAX_TOOL_ITERATIONS


class AgentRuntimeError(RuntimeError):
    """Catch-all for runtime failures the operator should see verbatim."""


class SysnordAgent:
    """One agent run for one conversation.

    Construct per-turn (cheap; the OpenAI client is stateless). Invariant:
    the conversation row + all messages stay tenant-scoped to
    ``conversation.company`` and user-scoped to ``conversation.user``.
    """

    def __init__(self, conversation: AgentConversation):
        self.conversation = conversation
        self.company = conversation.company
        self.client = OpenAIClient()
        self._max_iterations = int(
            getattr(settings, "AGENT_MAX_TOOL_ITERATIONS", 8)
        )

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    def run_turn(self, *, user_message: AgentMessage) -> AgentTurnResult:
        """Run the LLM ↔ tools loop until a plain assistant reply or the
        iteration cap. ``user_message`` must already be persisted; it's
        the latest entry in the conversation."""

        intermediates: list[AgentMessage] = []
        truncated = False

        for iteration in range(1, self._max_iterations + 1):
            messages = self._build_messages_for_llm()
            tools = build_tool_specs()

            try:
                response = self.client.chat_completions(messages, tools=tools)
            except (OpenAINotConnected, OpenAIReconnectRequired) as exc:
                raise AgentRuntimeError(str(exc)) from exc
            except OpenAIClientError as exc:
                raise AgentRuntimeError(f"OpenAI call failed: {exc}") from exc

            choice = self._first_choice(response)
            msg = choice.get("message") or {}
            tool_calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            usage = response.get("usage") or {}
            model_used = response.get("model") or ""

            if tool_calls:
                # Persist the assistant's tool-request message so the
                # next iteration includes it in history.
                assistant_request = self._persist_assistant_tool_request(
                    content=content, tool_calls=tool_calls,
                    model_used=model_used, usage=usage,
                )
                intermediates.append(assistant_request)

                # Execute each tool and persist the result.
                for call in tool_calls:
                    result_msg = self._dispatch_tool_call(call)
                    intermediates.append(result_msg)
                continue  # loop back to the LLM

            # No tool calls → final answer.
            final = self._persist_assistant_final(
                content=content, model_used=model_used, usage=usage,
            )
            self._touch_conversation()
            return AgentTurnResult(
                final_message=final,
                intermediate_messages=intermediates,
                iterations=iteration,
                truncated=False,
            )

        # Hit the iteration cap. Persist a synthetic assistant message so
        # the operator sees *something*.
        truncated = True
        cap_msg = self._persist_assistant_final(
            content=(
                "Atingi o limite de iterações de ferramentas sem produzir "
                "uma resposta final. Refine sua pergunta ou aumente "
                "AGENT_MAX_TOOL_ITERATIONS."
            ),
            model_used="",
            usage={},
        )
        self._touch_conversation()
        return AgentTurnResult(
            final_message=cap_msg,
            intermediate_messages=intermediates,
            iterations=self._max_iterations,
            truncated=truncated,
        )

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------
    def _dispatch_tool_call(self, call: dict[str, Any]) -> AgentMessage:
        """Execute one tool call and persist the result as a ``tool``
        :class:`AgentMessage`. The LLM gets the JSON output verbatim."""
        from mcp_server.tools import call_tool

        call_id = call.get("id", "")
        fn = call.get("function") or {}
        name = fn.get("name", "")
        raw_args = fn.get("arguments") or "{}"

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

        content = json.dumps(result, default=str)
        return AgentMessage.objects.create(
            company=self.company,
            conversation=self.conversation,
            role=AgentMessage.ROLE_TOOL,
            content=content,
            tool_call_id=call_id,
            tool_name=name,
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    @transaction.atomic
    def _persist_assistant_tool_request(
        self,
        *,
        content: str,
        tool_calls: list[dict[str, Any]],
        model_used: str,
        usage: dict[str, Any],
    ) -> AgentMessage:
        return AgentMessage.objects.create(
            company=self.company,
            conversation=self.conversation,
            role=AgentMessage.ROLE_ASSISTANT,
            content=content or "",
            tool_calls=tool_calls,
            model_used=model_used,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    @transaction.atomic
    def _persist_assistant_final(
        self,
        *,
        content: str,
        model_used: str,
        usage: dict[str, Any],
    ) -> AgentMessage:
        return AgentMessage.objects.create(
            company=self.company,
            conversation=self.conversation,
            role=AgentMessage.ROLE_ASSISTANT,
            content=content,
            tool_calls=[],
            model_used=model_used,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    def _touch_conversation(self) -> None:
        # Triggers ``auto_now`` so the list endpoint can sort by recency.
        AgentConversation.objects.filter(id=self.conversation.id).update(
            updated_at=timezone.now()
        )

    # ------------------------------------------------------------------
    # Message-history → OpenAI payload
    # ------------------------------------------------------------------
    def _build_messages_for_llm(self) -> list[dict[str, Any]]:
        """Materialise the OpenAI-formatted message list for this turn.

        The system prompt is regenerated each call so changes to the
        template propagate without editing history; previous assistant +
        tool rows are streamed back so the LLM has full context."""

        out: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt()},
        ]

        history = list(
            self.conversation.messages.order_by("created_at", "id").values(
                "role", "content", "tool_calls", "tool_call_id", "tool_name",
            )
        )
        for row in history:
            entry: dict[str, Any] = {"role": row["role"], "content": row["content"] or ""}
            if row["role"] == AgentMessage.ROLE_ASSISTANT and row["tool_calls"]:
                entry["tool_calls"] = row["tool_calls"]
                entry["content"] = row["content"] or None  # OpenAI tolerates null
            elif row["role"] == AgentMessage.ROLE_TOOL:
                entry["tool_call_id"] = row["tool_call_id"]
                entry["name"] = row["tool_name"]
            out.append(entry)
        return out

    def _system_prompt(self) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(
            tenant_subdomain=getattr(self.company, "subdomain", "?"),
            company_id=self.company.id,
        )

    @staticmethod
    def _first_choice(response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices") or []
        if not choices:
            raise AgentRuntimeError("OpenAI returned no choices")
        return choices[0]
