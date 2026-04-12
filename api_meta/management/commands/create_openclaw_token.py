"""
Management command: create_openclaw_token

Creates (or retrieves) the dedicated ``openclaw_agent`` user and its
long-lived DRF Token.  This is the token OpenClaw uses to authenticate
against the API in read-only mode.

Usage:
    python manage.py create_openclaw_token
"""
import secrets

from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from api_meta.permissions import OPENCLAW_USERNAME


class Command(BaseCommand):
    help = "Create (or show) the OpenClaw read-only API token."

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model

        User = get_user_model()

        user, created = User.objects.get_or_create(
            username=OPENCLAW_USERNAME,
            defaults={
                "email": "openclaw@nordventures.ai",
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
                "first_name": "OpenClaw",
                "last_name": "Agent",
            },
        )

        if created:
            password = secrets.token_urlsafe(32)
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created user '{OPENCLAW_USERNAME}'."))
        else:
            self.stdout.write(f"User '{OPENCLAW_USERNAME}' already exists.")

        token, tok_created = Token.objects.get_or_create(user=user)
        if tok_created:
            self.stdout.write(self.style.SUCCESS(f"Token created: {token.key}"))
        else:
            self.stdout.write(f"Existing token: {token.key}")

        self.stdout.write(
            "\nUsage:\n"
            f"  curl -H 'Authorization: Token {token.key}' "
            "https://your-api.example.com/api/meta/health/\n"
        )
