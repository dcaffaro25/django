"""Tests for the agent runtime (Phase 2).

OpenAI is mocked at the ``OpenAIClient.chat_completions`` boundary so we
exercise the full LLM ↔ tools loop without a real API call. Tool dispatch
goes through the real :func:`mcp_server.tools.call_tool` so a regression
in either layer is caught.

What's pinned:

* tool-call → tool-result → assistant happy path
* multi-iteration loops still terminate at AGENT_MAX_TOOL_ITERATIONS
* tenant guardrail: ``company_id`` injected even when the LLM omits it /
  passes a different value
* tool-not-found returns ``{"error": …}`` to the LLM, not an exception
* OpenAINotConnected surfaces as a 503 from the chat endpoint
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounting.models import (
    Account,
    Bank,
    BankAccount,
    BankTransaction,
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
)
from multitenancy.models import Company, Entity

User = get_user_model()
TEST_KEY = Fernet.generate_key().decode("ascii")


def _connected_token_store():
    """Helper: put a fresh tokenset in the singleton so ``OpenAINotConnected``
    isn't raised by the runtime under test."""
    store = OpenAITokenStore.get_or_create_singleton()
    store.set_tokens(access_token="acc", refresh_token="ref", expires_in=3600)
    store.save()
    return store


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
        _connected_token_store()
        self.conversation = AgentConversation.objects.create(
            company=self.company, user=self.user, title="t",
        )
        self.user_msg = AgentMessage.objects.create(
            company=self.company,
            conversation=self.conversation,
            role=AgentMessage.ROLE_USER,
            content="liste 5 contas",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _llm_tool_call(self, *, name: str, args: dict, call_id: str = "c1"):
        import json

        return {
            "model": "gpt-test",
            "choices": [{
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }],
                },
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    def _llm_final(self, content: str):
        return {
            "model": "gpt-test",
            "choices": [{
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8},
        }

    # ------------------------------------------------------------------
    # Happy path: tool call → tool result → final
    # ------------------------------------------------------------------
    def test_one_tool_call_then_final(self):
        side = [
            self._llm_tool_call(name="list_accounts", args={"company_id": self.company.id}),
            self._llm_final("Aqui estão as 1 conta."),
        ]
        with patch(
            "agent.services.agent_runtime.OpenAIClient.chat_completions",
            side_effect=side,
        ):
            result = SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)

        self.assertEqual(result.iterations, 2)
        self.assertFalse(result.truncated)
        self.assertEqual(result.final_message.role, "assistant")
        self.assertIn("conta", result.final_message.content)

        # 1 assistant tool-request + 1 tool result + 1 final assistant = 3 new rows
        # plus the 1 user message that already existed = 4 in conversation.
        rows = list(self.conversation.messages.order_by("id"))
        self.assertEqual([r.role for r in rows], ["user", "assistant", "tool", "assistant"])
        self.assertEqual(rows[2].tool_name, "list_accounts")

    # ------------------------------------------------------------------
    # Tenant guardrail: LLM trying to read another tenant gets clamped
    # ------------------------------------------------------------------
    def test_company_id_is_overridden_to_conversation_tenant(self):
        other = Company.objects.create(name="Other", subdomain="other")
        Account.objects.create(
            company=other, account_code="9.9", name="Other Caixa",
            account_direction=1, balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=self.currency,
        )

        # LLM asks for company_id=other.id; agent must overwrite.
        side = [
            self._llm_tool_call(
                name="list_accounts",
                args={"company_id": other.id, "limit": 10},
            ),
            self._llm_final("ok"),
        ]
        with patch(
            "agent.services.agent_runtime.OpenAIClient.chat_completions",
            side_effect=side,
        ):
            SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)

        tool_msg = self.conversation.messages.filter(role="tool").first()
        # The tool result is JSON; the names listed should belong to ``self.company``,
        # not ``other``. Easiest assertion: 'Other Caixa' must NOT appear.
        self.assertNotIn("Other Caixa", tool_msg.content)
        self.assertIn("Caixa", tool_msg.content)

    # ------------------------------------------------------------------
    # Iteration cap: looping LLM is bounded
    # ------------------------------------------------------------------
    def test_iteration_cap_terminates_with_synthetic_message(self):
        # Always-tool-calling LLM
        side = [
            self._llm_tool_call(
                name="list_accounts", args={}, call_id=f"c{i}",
            )
            for i in range(10)
        ]
        with patch(
            "agent.services.agent_runtime.OpenAIClient.chat_completions",
            side_effect=side,
        ):
            result = SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)

        self.assertTrue(result.truncated)
        self.assertEqual(result.iterations, 3)  # AGENT_MAX_TOOL_ITERATIONS=3 above
        self.assertIn("limite de iterações", result.final_message.content)

    # ------------------------------------------------------------------
    # Tool not found returns error to LLM
    # ------------------------------------------------------------------
    def test_unknown_tool_returns_error_blob_not_exception(self):
        side = [
            self._llm_tool_call(name="this_does_not_exist", args={}),
            self._llm_final("desculpe, ferramenta inválida"),
        ]
        with patch(
            "agent.services.agent_runtime.OpenAIClient.chat_completions",
            side_effect=side,
        ):
            result = SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)

        tool_msg = self.conversation.messages.filter(role="tool").first()
        self.assertIn('"error"', tool_msg.content)
        self.assertEqual(result.final_message.role, "assistant")

    # ------------------------------------------------------------------
    # OpenAINotConnected surfaces as runtime error
    # ------------------------------------------------------------------
    def test_disconnected_token_store_raises_runtime_error(self):
        OpenAITokenStore.objects.all().delete()

        with self.assertRaises(AgentRuntimeError) as ctx:
            SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)
        self.assertIn("OpenAI is not connected", str(ctx.exception))

    # ------------------------------------------------------------------
    # Reconnect-required surfaces clearly
    # ------------------------------------------------------------------
    def test_reconnect_required_surfaces_clearly(self):
        with patch(
            "agent.services.agent_runtime.OpenAIClient.chat_completions",
            side_effect=OpenAIReconnectRequired("token revoked upstream"),
        ):
            with self.assertRaises(AgentRuntimeError) as ctx:
                SysnordAgent(self.conversation).run_turn(user_message=self.user_msg)
        self.assertIn("token revoked upstream", str(ctx.exception))


@override_settings(
    AGENT_TOKEN_ENCRYPTION_KEY=TEST_KEY,
    AGENT_MAX_TOOL_ITERATIONS=3,
)
class AgentChatEndpointTests(TestCase):
    """End-to-end through the DRF view, mocking the OpenAI client."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="EP", subdomain="ep")
        cls.user = User.objects.create_user(username="ep-user", password="x")

    def setUp(self):
        from rest_framework.test import APIClient

        _connected_token_store()
        self.conversation = AgentConversation.objects.create(
            company=self.company, user=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        # Pin request.tenant on the test client by patching the view's
        # get_queryset — simpler than wiring TenantMiddleware here.
        from agent import views
        self._orig_get_qs = views.AgentConversationViewSet.get_queryset

        def patched_get_qs(view_self):
            return AgentConversation.objects.filter(
                user=view_self.request.user, company=self._test_company(),
            )

        # bind class-level
        views.AgentConversationViewSet.get_queryset = patched_get_qs

    def tearDown(self):
        from agent import views
        views.AgentConversationViewSet.get_queryset = self._orig_get_qs

    def _test_company(self):
        return self.company

    def test_chat_returns_200_with_messages_on_success(self):
        side = [
            {
                "model": "gpt-test",
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Olá!"},
                }],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        ]
        with patch(
            "agent.services.agent_runtime.OpenAIClient.chat_completions",
            side_effect=side,
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
