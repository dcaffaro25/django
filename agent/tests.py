"""Tests for Phase 1 of the Sysnord agent app — OAuth bridge, token store,
and connection endpoints.

The OAuth dance against a real OpenAI server is out of scope (and would
need OpenAI credentials); we mock ``requests.post`` instead and pin:

* PKCE verifier/challenge correctness (RFC 7636)
* state-collision rejection
* token encryption round-trip via Fernet
* singleton invariant on :class:`OpenAITokenStore`
* superuser-only enforcement on the connection endpoints
* tenant + user scoping on :class:`AgentConversationViewSet`
"""
from __future__ import annotations

import base64
import hashlib
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from multitenancy.models import Company

from agent.models import AgentConversation, OAuthAuthorizationFlow, OpenAITokenStore
from agent.services import oauth_service

User = get_user_model()


TEST_KEY = Fernet.generate_key().decode("ascii")


@override_settings(
    AGENT_TOKEN_ENCRYPTION_KEY=TEST_KEY,
    OPENAI_OAUTH_AUTH_URL="https://oauth.example/authorize",
    OPENAI_OAUTH_TOKEN_URL="https://oauth.example/token",
    OPENAI_OAUTH_CLIENT_ID="cid-test",
    OPENAI_OAUTH_CLIENT_SECRET="",
    OPENAI_OAUTH_REDIRECT_URI="http://localhost:8000/api/agent/connection/callback/",
    OPENAI_OAUTH_SCOPES="openid email offline_access",
    OPENAI_OAUTH_POST_CONNECT_REDIRECT="",
)
class OpenAITokenStoreEncryptionTests(TestCase):
    def test_round_trip(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(
            access_token="acc-123",
            refresh_token="ref-456",
            expires_in=3600,
            scopes="openid email",
        )
        store.save()

        store.refresh_from_db()
        access, refresh = store.tokens()
        self.assertEqual(access, "acc-123")
        self.assertEqual(refresh, "ref-456")
        self.assertTrue(store.is_connected)
        self.assertFalse(store.is_expired)

    def test_disconnect_clears(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(access_token="x", refresh_token="y", expires_in=60)
        store.save()
        store.clear()
        store.save()
        self.assertFalse(store.is_connected)
        self.assertEqual(store.tokens(), (None, None))

    def test_decryption_with_wrong_key_fails(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(access_token="x", refresh_token="y", expires_in=60)
        store.save()

        # Tampering with the key must surface as InvalidToken.
        from cryptography.fernet import InvalidToken

        with override_settings(AGENT_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            with self.assertRaises(InvalidToken):
                store.tokens()


@override_settings(
    AGENT_TOKEN_ENCRYPTION_KEY=TEST_KEY,
    OPENAI_OAUTH_AUTH_URL="https://oauth.example/authorize",
    OPENAI_OAUTH_TOKEN_URL="https://oauth.example/token",
    OPENAI_OAUTH_CLIENT_ID="cid-test",
    OPENAI_OAUTH_CLIENT_SECRET="",
    OPENAI_OAUTH_REDIRECT_URI="http://localhost:8000/api/agent/connection/callback/",
    OPENAI_OAUTH_SCOPES="openid email offline_access",
    OPENAI_OAUTH_POST_CONNECT_REDIRECT="",
)
class PkceFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="root", email="root@example.com", password="x",
        )

    def test_authorization_url_includes_pkce(self):
        url, flow = oauth_service.build_authorization_url(user=self.user)

        self.assertIn("response_type=code", url)
        self.assertIn("client_id=cid-test", url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn(f"state={flow.state}", url)
        self.assertNotIn(flow.code_verifier, url, "verifier must stay server-side")

        # Challenge in the URL must be base64-url(SHA256(verifier)) without padding.
        digest = hashlib.sha256(flow.code_verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        self.assertIn(f"code_challenge={expected}", url)

    def test_exchange_code_consumes_state(self):
        _, flow = oauth_service.build_authorization_url(user=self.user)
        with patch("agent.services.oauth_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "access_token": "acc-1",
                "refresh_token": "ref-1",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "openid email",
            }
            store = oauth_service.exchange_code(
                state=flow.state, code="auth-code", user=self.user,
            )

        self.assertTrue(store.is_connected)
        access, refresh = store.tokens()
        self.assertEqual(access, "acc-1")
        self.assertEqual(refresh, "ref-1")
        self.assertEqual(store.connected_by, self.user)

        flow.refresh_from_db()
        self.assertIsNotNone(flow.consumed_at)

        # Replay must fail.
        with self.assertRaises(oauth_service.OAuthExchangeError):
            oauth_service.exchange_code(state=flow.state, code="auth-code", user=self.user)

    def test_unknown_state_rejected(self):
        with self.assertRaises(oauth_service.OAuthExchangeError):
            oauth_service.exchange_code(state="bogus", code="x", user=self.user)

    def test_refresh_swaps_access_token(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(access_token="old", refresh_token="ref-1", expires_in=60)
        store.save()

        with patch("agent.services.oauth_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "access_token": "new",
                "refresh_token": "ref-2",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
            oauth_service.refresh_access_token(store=store)

        store.refresh_from_db()
        access, refresh = store.tokens()
        self.assertEqual(access, "new")
        self.assertEqual(refresh, "ref-2")

    def test_token_endpoint_failure_records_last_error(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(access_token="old", refresh_token="ref-1", expires_in=60)
        store.save()

        with patch("agent.services.oauth_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 400
            mock_post.return_value.text = '{"error":"invalid_grant"}'
            with self.assertRaises(oauth_service.OAuthExchangeError):
                oauth_service.refresh_access_token(store=store)

        store.refresh_from_db()
        self.assertIn("invalid_grant", store.last_error)


@override_settings(
    AGENT_TOKEN_ENCRYPTION_KEY=TEST_KEY,
    OPENAI_OAUTH_AUTH_URL="https://oauth.example/authorize",
    OPENAI_OAUTH_TOKEN_URL="https://oauth.example/token",
    OPENAI_OAUTH_CLIENT_ID="cid-test",
    OPENAI_OAUTH_CLIENT_SECRET="",
    OPENAI_OAUTH_REDIRECT_URI="http://localhost:8000/api/agent/connection/callback/",
    OPENAI_OAUTH_SCOPES="openid email offline_access",
    OPENAI_OAUTH_POST_CONNECT_REDIRECT="",
)
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

    def test_start_returns_authorization_url(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post("/api/agent/connection/start/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("authorization_url", resp.data)
        self.assertTrue(
            resp.data["authorization_url"].startswith("https://oauth.example/authorize?"),
            resp.data["authorization_url"],
        )
        # A flow row was created.
        self.assertTrue(OAuthAuthorizationFlow.objects.filter(state=resp.data["state"]).exists())

    def test_callback_exchanges_and_persists(self):
        self.client.force_authenticate(self.superuser)
        # Kick off start to create a flow row.
        start = self.client.post("/api/agent/connection/start/")
        state = start.data["state"]

        with patch("agent.services.oauth_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "access_token": "acc-cb",
                "refresh_token": "ref-cb",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "openid email",
            }
            resp = self.client.get(
                f"/api/agent/connection/callback/?code=abc&state={state}"
            )

        self.assertEqual(resp.status_code, 200)
        store = OpenAITokenStore.current()
        self.assertTrue(store.is_connected)

    def test_revoke_clears(self):
        store = OpenAITokenStore.get_or_create_singleton()
        store.set_tokens(access_token="x", refresh_token="y", expires_in=60)
        store.save()

        self.client.force_authenticate(self.superuser)
        resp = self.client.delete("/api/agent/connection/")
        self.assertEqual(resp.status_code, 200)

        store.refresh_from_db()
        self.assertFalse(store.is_connected)


class ConversationQuerysetScopingTests(TestCase):
    """Conversations are scoped to (user, company). The HTTP layer depends
    on ``TenantMiddleware`` for ``request.tenant``; here we exercise the
    viewset's ``get_queryset`` directly with a hand-built request to keep
    the test independent of subdomain resolution."""

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

    def _make_request(self, user, tenant):
        from django.test import RequestFactory

        rf = RequestFactory()
        req = rf.get("/api/agent/conversations/")
        req.user = user
        req.tenant = tenant
        return req

    def _ids_for(self, user, tenant):
        from agent.views import AgentConversationViewSet

        view = AgentConversationViewSet()
        view.request = self._make_request(user, tenant)
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
