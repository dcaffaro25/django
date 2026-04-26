"""Coverage for the existing auth surface — login, change-password,
admin-initiated password reset, user-create.

These tests lock in the current behaviour BEFORE we extend it with
self-service forgot-password, server-side first-login enforcement,
HTML templates, etc. They also act as the regression catch for a
signature mismatch we discovered in
``PasswordResetForceView.post()``: the call to
``send_user_email.delay(...)`` was passing 4 positional args + a
``fail_silently`` keyword to a task that only accepts 3 positional
args. In production (Celery worker) that's silent — the task crashes
with TypeError before ``send_mail`` runs, so the operator sees a
green 200 + cooldown set but never receives the email.

The tests below run with ``EMAIL_BACKEND=locmem`` so Django captures
emails into ``django.core.mail.outbox`` for inspection. Celery is in
eager mode by default in this test environment (no ``REDIS_URL``),
which means ``.delay()`` runs inline — so a signature mismatch
surfaces as a 500 in the test response.
"""
from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from multitenancy.models import CustomUser


EMAIL_LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@override_settings(EMAIL_BACKEND=EMAIL_LOCMEM)
class LoginViewTests(TestCase):
    """``POST /login/`` — token-based REST login."""

    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(
            username="alice", password="hunter2", email="alice@example.com",
        )

    def setUp(self):
        self.client = APIClient()
        mail.outbox = []

    def test_happy_path_returns_token_and_user_payload(self):
        resp = self.client.post(
            reverse("login"),
            {"username": "alice", "password": "hunter2"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertIn("token", body)
        self.assertTrue(body["token"])
        self.assertEqual(body["user"]["username"], "alice")
        self.assertEqual(body["user"]["email"], "alice@example.com")
        self.assertFalse(body["user"]["must_change_password"])

    def test_bad_password_returns_400(self):
        resp = self.client.post(
            reverse("login"),
            {"username": "alice", "password": "wrong"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_must_change_password_flag_surfaces_in_response(self):
        """Frontend uses this flag to gate the password-change form;
        keep it present in the login payload even though server-side
        enforcement isn't wired yet."""
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])
        resp = self.client.post(
            reverse("login"),
            {"username": "alice", "password": "hunter2"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["user"]["must_change_password"])


@override_settings(EMAIL_BACKEND=EMAIL_LOCMEM)
class ChangePasswordViewTests(TestCase):
    """``PUT /change-password/`` — authenticated user changes own password."""

    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(
            username="bob", password="oldpass1", email="bob@example.com",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_happy_path_updates_password_and_clears_must_change_flag(self):
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])

        resp = self.client.put(
            reverse("change-password"),
            {"old_password": "oldpass1", "new_password": "newpass2"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpass2"))
        self.assertFalse(self.user.must_change_password)

    def test_wrong_old_password_returns_400_and_does_not_change(self):
        resp = self.client.put(
            reverse("change-password"),
            {"old_password": "wrong", "new_password": "newpass2"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("oldpass1"))


@override_settings(
    EMAIL_BACKEND=EMAIL_LOCMEM,
    PASSWORD_RESET_EMAIL_COOLDOWN=5,
    TEMP_PASSWORD="ResetTemp123",
)
class PasswordResetForceViewTests(TestCase):
    """``POST /reset-password/`` — admin endpoint that emails a temporary
    password to the target user.

    Lock-in tests for current behaviour:
      * Resets the password to ``settings.TEMP_PASSWORD``.
      * Sets ``must_change_password=True``.
      * Sends an email containing the temp password.
      * Returns 429 when called again within the cooldown window.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = CustomUser.objects.create_user(
            username="admin", password="x", email="admin@example.com",
            is_staff=True, is_superuser=True,
        )
        cls.target = CustomUser.objects.create_user(
            username="carol", password="oldcarol", email="carol@example.com",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        mail.outbox = []
        # Test isolation: clear any timestamp left over from another test.
        self.target.email_last_sent_at = None
        self.target.save(update_fields=["email_last_sent_at"])

    def test_happy_path_resets_password_and_sends_email(self):
        resp = self.client.post(
            reverse("reset-password"),
            {"email": "carol@example.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        self.target.refresh_from_db()
        self.assertTrue(self.target.must_change_password)
        self.assertTrue(self.target.check_password("ResetTemp123"))
        self.assertIsNotNone(self.target.email_last_sent_at)

        # Email actually sent — captures the bug where the call site
        # passed args that didn't match the task signature, so the
        # task crashed silently before send_mail ran.
        self.assertEqual(len(mail.outbox), 1, "expected exactly one email queued")
        self.assertIn("carol@example.com", mail.outbox[0].to)
        self.assertIn("ResetTemp123", mail.outbox[0].body)

    def test_cooldown_returns_429(self):
        # Pretend an email was sent 1 minute ago — cooldown is 5 minutes.
        self.target.email_last_sent_at = timezone.now() - timedelta(minutes=1)
        self.target.save(update_fields=["email_last_sent_at"])

        resp = self.client.post(
            reverse("reset-password"),
            {"email": "carol@example.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, 429, resp.content)
        self.assertIn("minutes", resp.json()["detail"].lower())

    def test_cooldown_expired_allows_new_email(self):
        # 10 minutes ago — past the 5-minute cooldown.
        self.target.email_last_sent_at = timezone.now() - timedelta(minutes=10)
        self.target.save(update_fields=["email_last_sent_at"])

        resp = self.client.post(
            reverse("reset-password"),
            {"email": "carol@example.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_email_returns_400(self):
        """Current behaviour exposes whether an email is registered;
        the self-service forgot-password flow we're about to ship will
        return a uniform 200 to prevent enumeration."""
        resp = self.client.post(
            reverse("reset-password"),
            {"email": "nobody@example.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)


@override_settings(EMAIL_BACKEND=EMAIL_LOCMEM, TEMP_PASSWORD="CreateTemp123")
class UserCreateViewTests(TestCase):
    """``POST /users/create/`` — admin endpoint that creates a user with
    a temporary password and ``must_change_password=True``."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = CustomUser.objects.create_user(
            username="admin2", password="x", email="admin2@example.com",
            is_staff=True, is_superuser=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        mail.outbox = []

    def test_creates_user_with_must_change_password_true(self):
        resp = self.client.post(
            reverse("user-create"),
            {
                "username": "dan",
                "email": "dan@example.com",
                "first_name": "Dan",
                "last_name": "Smith",
                "is_superuser": False,
                "is_staff": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        u = CustomUser.objects.get(username="dan")
        self.assertTrue(u.must_change_password)
        self.assertTrue(u.is_active)
        self.assertTrue(u.check_password("CreateTemp123"))
        # Invite email is currently commented out at views.py:105 — no
        # mail goes out. This assertion records the present state; we
        # uncomment + extend the email in a later commit and update
        # the assertion to match.
        self.assertEqual(len(mail.outbox), 0)
