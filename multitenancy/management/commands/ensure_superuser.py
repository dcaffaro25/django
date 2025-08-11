import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

class Command(BaseCommand):
    help = "Create an admin superuser from env if missing (idempotent)."

    def handle(self, *args, **kwargs):
        User = get_user_model()
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "nord-admin")
        #email = os.getenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD")
        reset = os.getenv("DJANGO_SUPERUSER_RESET", "0") == "1"

        # If your CustomUser has extra REQUIRED fields, set them here:
        extra = {}
        # e.g. extra["first_name"] = os.getenv("DJANGO_SUPERUSER_FIRST_NAME", "Admin")

        if not password:
            self.stdout.write(self.style.WARNING("DJANGO_SUPERUSER_PASSWORD not set; skipping."))
            return

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"is_staff": True, "is_superuser": True, **extra},
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'"))
            else:
                changed = False
                if reset:  # optional: allow password rotation via env
                    user.set_password(password); changed = True
                if not user.is_superuser or not user.is_staff:
                    user.is_superuser = True; user.is_staff = True; changed = True
                if changed:
                    user.save()
                self.stdout.write(self.style.SUCCESS(f"Ensured superuser '{username}' (updated={changed})"))