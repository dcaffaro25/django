"""Tests for the agent app's OAuth + import-tokens surface.

The OAuth dance against real OpenAI is out of scope; we mock
``requests.post`` and pin:

* PKCE verifier/challenge correctness (RFC 7636)
* Authorize URL contains all required Codex query params
* JWT account_id extraction from the ``https://api.openai.com/auth`` claim
* Token encryption round-trip via Fernet
* Refresh + persist updates the singleton with new tokens + accountId
* Superuser-only enforcement on connection endpoints
* import-tokens validates payload and persists correctly
* (user, company) scoping on AgentConversationViewSet.get_queryset
"""
from __future__ import annotations

import base64
import hashlib
import json
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from multitenancy.models import Company

from agent.models import AgentConversation, OpenAITokenStore
from agent.services import oauth_service

User = get_user_model()
TEST_KEY = Fernet.generate_key().decode("ascii")


def _make_jwt(payload: dict) -> str:
    """Build a fake JWT (header.payload.sig) for tests. Signature is empty
    — we don't verify, only parse."""
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
    header = _b64(b'{"alg":"none","typ":"JWT"}')
    body = _b64(json.dumps(payload).encode("utf-8"))
    return f"{header}.{body}.sig"


@override_settings(AGENT_TOKEN_ENCRYPTION_KEY=TEST_KEY)
class OpenAITokenStoreEncryptionTests(TestCase):
    def test_round_trip(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(
            access_token="acc-123", refresh_token="ref-456",
            expires_in=3600, scopes="openid email",
        )
        store.chatgpt_account_id = "acct_test"
        store.save()

        store.refresh_from_db()
        access, refresh = store.tokens()
        self.assertEqual(access, "acc-123")
        self.assertEqual(refresh, "ref-456")
        self.assertEqual(store.chatgpt_account_id, "acct_test")
        self.assertTrue(store.is_connected)

    def test_clear_disconnects(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(access_token="x", refresh_token="y", expires_in=60)
        store.save()
        store.clear()
        store.save()
        self.assertFalse(store.is_connected)


@override_settings(AGENT_TOKEN_ENCRYPTION_KEY=TEST_KEY)
class OAuthBuildersTests(TestCase):
    def test_authorize_url_includes_codex_params(self):
        verifier = oauth_service.new_code_verifier()
        state = oauth_service.new_state()
        url = oauth_service.build_authorize_url(state=state, code_verifier=verifier)

        # PKCE
        self.assertIn("response_type=code", url)
        self.assertIn(f"state={state}", url)
        self.assertIn("code_challenge_method=S256", url)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        self.assertIn(f"code_challenge={expected_challenge}", url)

        # Codex-specific extras
        self.assertIn("id_token_add_organizations=true", url)
        self.assertIn("codex_cli_simplified_flow=true", url)
        self.assertIn("originator=", url)

        # Default client_id from OpenClaw
        self.assertIn(f"client_id={oauth_service.DEFAULT_CLIENT_ID}", url)

        # Hardcoded loopback redirect
        self.assertIn("redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback", url)

    def test_extract_account_id_from_jwt(self):
        token = _make_jwt({
            "https://api.openai.com/auth": {"chatgpt_account_id": "acct_xyz"},
            "email": "foo@bar.com",
        })
        self.assertEqual(oauth_service.extract_account_id(token), "acct_xyz")
        self.assertEqual(oauth_service.extract_account_email(token), "foo@bar.com")

    def test_extract_account_id_missing_claim_raises(self):
        token = _make_jwt({"sub": "x"})
        with self.assertRaises(oauth_service.JwtDecodeError):
            oauth_service.extract_account_id(token)


@override_settings(AGENT_TOKEN_ENCRYPTION_KEY=TEST_KEY)
class OAuthExchangeTests(TestCase):
    def test_exchange_code_calls_token_endpoint(self):
        with patch("agent.services.oauth_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "access_token": "acc-1",
                "refresh_token": "ref-1",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
            resp = oauth_service.exchange_code(code="abc", code_verifier="ver")

        self.assertEqual(resp["access_token"], "acc-1")
        # Must POST to OpenAI's token endpoint with form-encoded body
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], oauth_service.DEFAULT_TOKEN_URL)
        body = kwargs["data"]
        self.assertEqual(body["grant_type"], "authorization_code")
        self.assertEqual(body["code"], "abc")
        self.assertEqual(body["code_verifier"], "ver")
        self.assertEqual(body["client_id"], oauth_service.DEFAULT_CLIENT_ID)

    def test_refresh_swaps_access_token(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(access_token="old", refresh_token="ref-1", expires_in=60)
        store.chatgpt_account_id = "acct_old"
        store.save()

        new_jwt = _make_jwt({
            "https://api.openai.com/auth": {"chatgpt_account_id": "acct_old"},
        })

        with patch("agent.services.oauth_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "access_token": new_jwt,
                "refresh_token": "ref-2",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
            oauth_service.refresh_and_persist(store=store)

        store.refresh_from_db()
        access, refresh = store.tokens()
        self.assertEqual(access, new_jwt)
        self.assertEqual(refresh, "ref-2")
        self.assertEqual(store.chatgpt_account_id, "acct_old")

    def test_refresh_failure_records_last_error(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(access_token="old", refresh_token="ref", expires_in=60)
        store.save()
        with patch("agent.services.oauth_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 400
            mock_post.return_value.text = '{"error":"invalid_grant"}'
            with self.assertRaises(oauth_service.OAuthExchangeError):
                oauth_service.refresh_and_persist(store=store)

        store.refresh_from_db()
        self.assertIn("invalid_grant", store.last_error)


@override_settings(AGENT_TOKEN_ENCRYPTION_KEY=TEST_KEY)
class ConnectionEndpointsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="root", email="root@example.com", password="x",
        )
        cls.regular = User.objects.create_user(
            username="alice", email="alice@example.com", password="x",
        )

    def setUp(self):
        self.client = APIClient()

    def test_status_requires_superuser(self):
        self.client.force_authenticate(self.regular)
        resp = self.client.get("/api/agent/connection/")
        self.assertIn(resp.status_code, (401, 403))

    def test_status_disconnected_when_no_row(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get("/api/agent/connection/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["is_connected"])

    def test_import_tokens_requires_superuser(self):
        self.client.force_authenticate(self.regular)
        resp = self.client.post(
            "/api/agent/connection/import-tokens/",
            {"access_token": "x", "chatgpt_account_id": "a"},
            format="json",
        )
        self.assertIn(resp.status_code, (401, 403))

    def test_import_tokens_validates_required_fields(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            "/api/agent/connection/import-tokens/",
            {"access_token": "x"},  # missing chatgpt_account_id
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_import_tokens_persists_singleton(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            "/api/agent/connection/import-tokens/",
            {
                "access_token": "acc-via-cli",
                "refresh_token": "ref-via-cli",
                "expires_in": 3600,
                "chatgpt_account_id": "acct_imported",
                "account_email": "ops@sysnord.com",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["is_connected"])
        self.assertEqual(resp.data["chatgpt_account_id"], "acct_imported")
        self.assertEqual(resp.data["account_email"], "ops@sysnord.com")

        store = OpenAITokenStore.current()
        access, refresh = store.tokens()
        self.assertEqual(access, "acc-via-cli")
        self.assertEqual(refresh, "ref-via-cli")
        self.assertEqual(store.connected_by, self.superuser)

    def test_revoke_clears(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(access_token="x", refresh_token="y", expires_in=60)
        store.chatgpt_account_id = "acct"
        store.save()

        self.client.force_authenticate(self.superuser)
        resp = self.client.delete("/api/agent/connection/")
        self.assertEqual(resp.status_code, 200)

        store.refresh_from_db()
        self.assertFalse(store.is_connected)
        self.assertEqual(store.chatgpt_account_id, "")


class ConversationQuerysetScopingTests(TestCase):
    """Conversations are scoped to (user, company). The HTTP layer depends
    on ``TenantMiddleware`` for ``request.tenant``; here we exercise the
    viewset's ``get_queryset`` directly."""

    @classmethod
    def setUpTestData(cls):
        cls.company_a = Company.objects.create(name="A", subdomain="a")
        cls.company_b = Company.objects.create(name="B", subdomain="b")
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")

        cls.conv_alice_a = AgentConversation.objects.create(
            company=cls.company_a, user=cls.alice, title="Alice in A",
        )
        cls.conv_alice_b = AgentConversation.objects.create(
            company=cls.company_b, user=cls.alice, title="Alice in B",
        )
        cls.conv_bob_a = AgentConversation.objects.create(
            company=cls.company_a, user=cls.bob, title="Bob in A",
        )

    def _ids_for(self, user, tenant):
        from django.test import RequestFactory
        from agent.views import AgentConversationViewSet

        rf = RequestFactory()
        req = rf.get("/api/agent/conversations/")
        req.user = user
        req.tenant = tenant
        view = AgentConversationViewSet()
        view.request = req
        return list(view.get_queryset().values_list("id", flat=True))

    def test_alice_in_a_sees_only_her_a_thread(self):
        ids = self._ids_for(self.alice, self.company_a)
        self.assertIn(self.conv_alice_a.id, ids)
        self.assertNotIn(self.conv_alice_b.id, ids)
        self.assertNotIn(self.conv_bob_a.id, ids)

    def test_alice_in_b_sees_only_her_b_thread(self):
        ids = self._ids_for(self.alice, self.company_b)
        self.assertEqual(ids, [self.conv_alice_b.id])

    def test_bob_in_a_sees_only_his_a_thread(self):
        ids = self._ids_for(self.bob, self.company_a)
        self.assertEqual(ids, [self.conv_bob_a.id])
