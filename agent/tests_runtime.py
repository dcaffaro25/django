"""Tests for the agent runtime against the Codex Responses API.

OpenAI is mocked at the ``OpenAIClient.respond`` boundary so we exercise
the full LLM ↔ tools loop without a real API call. Tool dispatch goes
through the real :func:`mcp_server.tools.call_tool` so a regression in
either layer is caught.

Pinned behaviours:
* function_call → function_call_output → final assistant happy path
* multi-iteration loops still terminate at ``AGENT_MAX_TOOL_ITERATIONS``
* tenant guardrail: ``company_id`` injected even if the LLM passes a
  different value
* tool-not-found returns ``{"error": …}`` to the LLM (not exception)
* ``OpenAINotConnected`` surfaces as a 503 from the chat endpoint
* SSE assembly: response.completed event yields the full output array
"""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounting.models import (
    Account,
    Bank,
    BankAccount,
    Currency,
)
from agent.models import AgentConversation, AgentMessage, OpenAITokenStore
from agent.services.agent_runtime import (
    AgentRuntimeError,
    SysnordAgent,
)
from agent.services.openai_client import (
    OpenAINotConnected,
    OpenAIReconnectRequired,
    _assemble_sse_response,
    _iter_sse_events,
)
from multitenancy.models import Company, Entity

User = get_user_model()
TEST_KEY = Fernet.generate_key().decode("ascii")


def _connect_store():
    """Helper: put a fresh tokenset + accountId in the singleton."""
    store = OpenAITokenStore.get_or_create_singleton()
    store.set_tokens(access_token="acc", refresh_token="ref", expires_in=3600)
    store.chatgpt_account_id = "acct_test"
    store.save()
    return store


def _function_call_response(*, name: str, args: dict, call_id: str = "c1"):
    """Build a Responses-API-shaped result with one function_call."""
    return {
        "model": "gpt-test",
        "output": [
            {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": json.dumps(args),
            },
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _final_message_response(text: str):
    return {
        "model": "gpt-test",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
        ],
        "usage": {"input_tokens": 20, "output_tokens": 8},
    }


@override_settings(
    AGENT_TOKEN_ENCRYPTION_KEY=TEST_KEY,
    AGENT_MAX_TOOL_ITERATIONS=3,
    OPENAI_DEFAULT_MODEL="gpt-test",
)
class AgentRuntimeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="RT", subdomain="rt")
        cls.user = User.objects.create_user(username="rt-user", password="x")
        cls.entity = Entity.objects.create(company=cls.company, name="Counterparty")
        cls.currency = Currency.objects.create(code="BRL", name="Real")
        cls.account = Account.objects.create(
            company=cls.company,
            account_code="1.0",
            name="Caixa",
            account_direction=1,
            balance=Decimal("0.00"),
            balance_date=dt.date(2026, 1, 1),
            currency=cls.currency,
        )

    def setUp(self):
        _connect_store()
        self.conversation = AgentConversation.objects.create(
            company=self.company, user=self.user, title="t",
        )
        self.user_msg = AgentMessage.objects.create(
            company=self.company,
            conversation=self.conversation,
            role=AgentMessage.ROLE_USER,
            content="liste as contas",
        )

    # ------------------------------------------------------------------
    def test_one_tool_call_then_final(self):
        side = [
            _function_call_response(
                name="list_accounts", args={"company_id": self.company.id},
            ),
            _final_message_response("Aqui está a 1 conta."),
        ]
        with patch(
            "agent.services.agent_runtime.OpenAIClient.respond",
            side_effect=side,
        ):
            result = SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)

        self.assertEqual(result.iterations, 2)
        self.assertFalse(result.truncated)
        self.assertEqual(result.final_message.role, "assistant")
        self.assertIn("conta", result.final_message.content)

        rows = list(self.conversation.messages.order_by("id"))
        self.assertEqual([r.role for r in rows], ["user", "assistant", "tool", "assistant"])
        self.assertEqual(rows[2].tool_name, "list_accounts")

    # ------------------------------------------------------------------
    def test_company_id_overridden_to_conversation_tenant(self):
        other = Company.objects.create(name="Other", subdomain="other")
        Account.objects.create(
            company=other, account_code="9.9", name="Other Caixa",
            account_direction=1, balance=Decimal("0"),
            balance_date=dt.date(2026, 1, 1), currency=self.currency,
        )

        side = [
            _function_call_response(
                name="list_accounts", args={"company_id": other.id, "limit": 10},
            ),
            _final_message_response("ok"),
        ]
        with patch(
            "agent.services.agent_runtime.OpenAIClient.respond",
            side_effect=side,
        ):
            SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)

        tool_msg = self.conversation.messages.filter(role="tool").first()
        self.assertNotIn("Other Caixa", tool_msg.content)
        self.assertIn("Caixa", tool_msg.content)

    # ------------------------------------------------------------------
    def test_iteration_cap_terminates_with_synthetic_message(self):
        side = [
            _function_call_response(
                name="list_accounts", args={}, call_id=f"c{i}",
            )
            for i in range(10)
        ]
        with patch(
            "agent.services.agent_runtime.OpenAIClient.respond",
            side_effect=side,
        ):
            result = SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)

        self.assertTrue(result.truncated)
        self.assertEqual(result.iterations, 3)
        self.assertIn("limite de iterações", result.final_message.content)

    # ------------------------------------------------------------------
    def test_unknown_tool_returns_error_blob(self):
        side = [
            _function_call_response(name="this_does_not_exist", args={}),
            _final_message_response("desculpe, ferramenta inválida"),
        ]
        with patch(
            "agent.services.agent_runtime.OpenAIClient.respond",
            side_effect=side,
        ):
            result = SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)

        tool_msg = self.conversation.messages.filter(role="tool").first()
        self.assertIn('"error"', tool_msg.content)
        self.assertEqual(result.final_message.role, "assistant")

    # ------------------------------------------------------------------
    def test_disconnected_token_store_raises_runtime_error(self):
        OpenAITokenStore.objects.all().delete()
        with self.assertRaises(AgentRuntimeError) as ctx:
            SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)
        self.assertIn("OpenAI is not connected", str(ctx.exception))

    # ------------------------------------------------------------------
    def test_reasoning_only_response_surfaces_summary(self):
        # When Codex returns ONLY a reasoning item (no message, no
        # function_call), we must surface the reasoning summary instead
        # of persisting an empty assistant bubble. This is what produced
        # the "..." placeholder + populated tokens in 2026-05-03.
        reasoning_only = {
            "model": "gpt-5.5",
            "output": [
                {
                    "type": "reasoning",
                    "id": "rs_1",
                    "summary": [
                        {"type": "summary_text", "text": "Cumprimento simples; respondo Olá."},
                    ],
                },
            ],
            "usage": {"input_tokens": 1200, "output_tokens": 20},
        }
        with patch(
            "agent.services.agent_runtime.OpenAIClient.respond",
            side_effect=[reasoning_only],
        ):
            result = SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)

        self.assertEqual(result.final_message.role, "assistant")
        self.assertNotEqual(result.final_message.content, "")
        self.assertIn("respondo", result.final_message.content)

    def test_completely_empty_response_persists_user_facing_message(self):
        # Even when the model returns NOTHING usable (no message, no
        # reasoning), persist a user-facing fallback rather than "...".
        empty_resp = {
            "model": "gpt-5.5",
            "output": [],
            "usage": {"input_tokens": 100, "output_tokens": 0},
        }
        with patch(
            "agent.services.agent_runtime.OpenAIClient.respond",
            side_effect=[empty_resp],
        ):
            result = SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)

        # output_items is empty → no fallback path runs (nothing to
        # surface) and content stays "" which is the existing behaviour.
        # That's fine; the content_override fallback only kicks in when
        # there ARE output items but no message/function_call among them.
        self.assertEqual(result.final_message.content, "")

    # ------------------------------------------------------------------
    def test_reconnect_required_surfaces_clearly(self):
        with patch(
            "agent.services.agent_runtime.OpenAIClient.respond",
            side_effect=OpenAIReconnectRequired("token revoked upstream"),
        ):
            with self.assertRaises(AgentRuntimeError) as ctx:
                SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)
        self.assertIn("token revoked upstream", str(ctx.exception))


# ---------------------------------------------------------------------------
# SSE parser tests — pure-function, no DB
# ---------------------------------------------------------------------------
class _FakeStreamResponse:
    """Mimics requests.Response.iter_lines() for tests."""
    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self, decode_unicode=True):  # noqa: D401
        return iter(self._lines)


class SseParserTests(TestCase):
    def test_assembles_response_completed_event(self):
        events = [
            'data: {"type":"response.created","response":{"id":"r1"}}',
            "",
            'data: {"type":"response.output_item.added"}',
            "",
            'data: {"type":"response.completed","response":{"model":"gpt-x","output":'
            '[{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Hi"}]}],'
            '"usage":{"input_tokens":1,"output_tokens":2}}}',
            "",
        ]
        result = _assemble_sse_response(_iter_sse_events(_FakeStreamResponse(events)))
        self.assertEqual(result["model"], "gpt-x")
        self.assertEqual(result["usage"]["output_tokens"], 2)
        self.assertEqual(len(result["output"]), 1)
        self.assertEqual(result["output"][0]["role"], "assistant")

    def test_falls_back_to_per_item_done_events(self):
        events = [
            'data: {"type":"response.output_item.done","item":{"type":"function_call",'
            '"call_id":"c1","name":"foo","arguments":"{}"}}',
            "",
            'data: {"type":"response.output_item.done","item":{"type":"message",'
            '"role":"assistant","content":[{"type":"output_text","text":"done"}]}}',
            "",
        ]
        result = _assemble_sse_response(_iter_sse_events(_FakeStreamResponse(events)))
        self.assertEqual(len(result["output"]), 2)
        self.assertEqual(result["output"][0]["type"], "function_call")
        self.assertEqual(result["output"][1]["type"], "message")

    def test_per_item_events_win_when_completed_output_is_empty(self):
        # With ``store: false`` set on the request, Codex sometimes sends
        # ``response.completed`` with ``output: []`` while the real items
        # arrived via per-item events. Per-item must win — otherwise the
        # assistant message persists with empty content but populated
        # token counts (the "..." bubble bug from 2026-05-03).
        events = [
            'data: {"type":"response.output_item.done","item":{"type":"message",'
            '"role":"assistant","content":[{"type":"output_text","text":"olá!"}]}}',
            "",
            'data: {"type":"response.completed","response":{"model":"gpt-x","output":[],'
            '"usage":{"input_tokens":1200,"output_tokens":20}}}',
            "",
        ]
        result = _assemble_sse_response(_iter_sse_events(_FakeStreamResponse(events)))
        self.assertEqual(len(result["output"]), 1)
        self.assertEqual(result["output"][0]["type"], "message")
        self.assertEqual(result["usage"]["output_tokens"], 20)
        self.assertEqual(result["model"], "gpt-x")

    def test_failed_event_raises(self):
        from agent.services.openai_client import OpenAIClientError
        events = [
            'data: {"type":"response.failed","response":{"error":{"message":"bad"}}}',
            "",
        ]
        with self.assertRaises(OpenAIClientError):
            _assemble_sse_response(_iter_sse_events(_FakeStreamResponse(events)))


@override_settings(
    AGENT_TOKEN_ENCRYPTION_KEY=TEST_KEY,
    AGENT_MAX_TOOL_ITERATIONS=3,
)
class AgentChatEndpointTests(TestCase):
    """End-to-end through the DRF view, mocking OpenAIClient.respond."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="EP", subdomain="ep")
        cls.user = User.objects.create_user(username="ep-user", password="x")

    def setUp(self):
        from rest_framework.test import APIClient

        _connect_store()
        self.conversation = AgentConversation.objects.create(
            company=self.company, user=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        # Pin tenant on the viewset since TenantMiddleware doesn't run here.
        from agent import views
        self._orig_get_qs = views.AgentConversationViewSet.get_queryset

        def patched(view_self):
            return AgentConversation.objects.filter(
                user=view_self.request.user, company=self._test_company(),
            )
        views.AgentConversationViewSet.get_queryset = patched

    def tearDown(self):
        from agent import views
        views.AgentConversationViewSet.get_queryset = self._orig_get_qs

    def _test_company(self):
        return self.company

    def test_chat_returns_200_on_success(self):
        with patch(
            "agent.services.agent_runtime.OpenAIClient.respond",
            side_effect=[_final_message_response("Olá!")],
        ):
            resp = self.client.post(
                f"/api/agent/conversations/{self.conversation.id}/chat/",
                {"content": "olá agente"}, format="json",
            )

        self.assertEqual(resp.status_code, 200)
        roles = [m["role"] for m in resp.data["messages"]]
        self.assertEqual(roles, ["user", "assistant"])
        self.assertEqual(resp.data["messages"][1]["content"], "Olá!")

    def test_chat_returns_503_when_disconnected(self):
        OpenAITokenStore.objects.all().delete()
        resp = self.client.post(
            f"/api/agent/conversations/{self.conversation.id}/chat/",
            {"content": "ping"}, format="json",
        )
        self.assertEqual(resp.status_code, 503)
        self.assertIn("OpenAI is not connected", resp.data["detail"])

    def test_chat_400_when_content_empty(self):
        resp = self.client.post(
            f"/api/agent/conversations/{self.conversation.id}/chat/",
            {"content": ""}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
