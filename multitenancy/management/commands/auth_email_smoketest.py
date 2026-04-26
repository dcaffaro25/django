"""Send a real authentication email through the configured SMTP backend.

This is a smoke / integration tool — distinct from the unit tests
in ``multitenancy/tests/test_auth.py`` which use Django's locmem
backend and capture emails without actually transmitting them.

Use this when:
  * You're verifying ``EMAIL_HOST_USER`` / ``EMAIL_HOST_PASSWORD``
    work against the production SMTP relay (Office 365 by default).
  * You're reviewing the deliverability / spam-folder behaviour of
    a brand-new email template.
  * You're debugging a "users say emails don't arrive" report.

The default recipient is ``dcaffaro@nordventures.com.br``; override
with ``--recipient`` for any other inbox.

Examples:
  python manage.py auth_email_smoketest                       # default: reset + default recipient
  python manage.py auth_email_smoketest --scenario invite     # invite email
  python manage.py auth_email_smoketest --recipient ops@nv.br
  python manage.py auth_email_smoketest --scenario both --no-celery   # bypass Celery, send synchronously

Environment vars required (already set on Railway):
  EMAIL_HOST_USER, EMAIL_HOST_PASSWORD

Notes:
  * By default the Celery task path is exercised. If ``REDIS_URL`` is
    set the task goes through the broker (worker must be running).
    Pass ``--no-celery`` to call ``send_mail`` directly — useful for
    local development without a Celery worker.
  * No DB rows are mutated; this command does NOT create users or
    change anyone's password. It only sends the email.
"""
from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


DEFAULT_RECIPIENT = "dcaffaro@nordventures.com.br"

INVITE_SUBJECT = "[Nord smoke test] Convite — sua conta foi criada"
INVITE_BODY_TMPL = """\
Olá {name},

Esta é uma mensagem de teste do comando ``auth_email_smoketest``.
Em produção, este é o template usado quando um administrador cria
uma nova conta de operador.

Username: {username}
Senha temporária: {temp_password}

Ao fazer login pela primeira vez, você será solicitado a alterar
a senha imediatamente.

— Equipe Nord
"""

RESET_SUBJECT = "[Nord smoke test] Sua senha foi redefinida"
RESET_BODY_TMPL = """\
Olá {name},

Esta é uma mensagem de teste do comando ``auth_email_smoketest``.
Em produção, este é o template usado quando um administrador
redefine a sua senha.

Senha temporária: {temp_password}

Ao fazer login com a senha temporária, você será solicitado a
alterá-la imediatamente.

— Equipe Nord
"""


class Command(BaseCommand):
    help = "Send a real authentication email through the configured SMTP backend."

    def add_arguments(self, parser):
        parser.add_argument(
            "--recipient",
            default=DEFAULT_RECIPIENT,
            help=(
                f"Email address to send to. Default: {DEFAULT_RECIPIENT}. "
                "Use a real inbox you control — this hits the real SMTP."
            ),
        )
        parser.add_argument(
            "--scenario",
            choices=("invite", "reset", "both"),
            default="reset",
            help=(
                "Which template to send. ``invite`` mirrors UserCreateView's "
                "email; ``reset`` mirrors PasswordResetForceView's; ``both`` "
                "fires both in sequence."
            ),
        )
        parser.add_argument(
            "--name",
            default="Operador de Teste",
            help="Display name to fill into the salutation. Default: 'Operador de Teste'.",
        )
        parser.add_argument(
            "--username",
            default="smoketest",
            help="Username to show in the invite body. Default: 'smoketest'.",
        )
        parser.add_argument(
            "--temp-password",
            default="SmokeTest123!",
            help=(
                "Temporary password value to inline into the email body. "
                "Default: 'SmokeTest123!'. NOT applied to any user — this is "
                "purely a string substitution in the template."
            ),
        )
        parser.add_argument(
            "--no-celery",
            action="store_true",
            help=(
                "Skip the Celery task and call ``send_mail`` directly. "
                "Use for local dev without a worker; default is to go "
                "through ``send_user_invite_email`` / ``send_user_email``."
            ),
        )

    def handle(self, *args, **opts):
        recipient = opts["recipient"]
        scenario = opts["scenario"]
        name = opts["name"]
        username = opts["username"]
        temp_password = opts["temp_password"]
        no_celery = opts["no_celery"]

        if not getattr(settings, "EMAIL_HOST_USER", None):
            raise CommandError(
                "EMAIL_HOST_USER is not set. Set it in the environment "
                "(plus EMAIL_HOST_PASSWORD) or run with the env vars "
                "directly: EMAIL_HOST_USER=... EMAIL_HOST_PASSWORD=... "
                "python manage.py auth_email_smoketest"
            )

        from_email = settings.DEFAULT_FROM_EMAIL
        sender_label = "via send_mail (sync)" if no_celery else "via Celery task"
        backend = getattr(settings, "EMAIL_BACKEND", "<unset>")

        self.stdout.write(self.style.NOTICE(
            f"Email smoke test — backend={backend} sender={from_email} "
            f"recipient={recipient} {sender_label}"
        ))

        scenarios = (
            ["reset"] if scenario == "reset" else
            ["invite"] if scenario == "invite" else
            ["invite", "reset"]
        )

        for sc in scenarios:
            if sc == "invite":
                subject = INVITE_SUBJECT
                body = INVITE_BODY_TMPL.format(
                    name=name, username=username, temp_password=temp_password,
                )
                # Production sender for invites:
                from multitenancy.tasks import send_user_invite_email
                task = send_user_invite_email
            else:
                subject = RESET_SUBJECT
                body = RESET_BODY_TMPL.format(
                    name=name, temp_password=temp_password,
                )
                from multitenancy.tasks import send_user_email
                task = send_user_email

            self.stdout.write(f"  → sending {sc} email to {recipient}…")
            try:
                if no_celery:
                    send_mail(
                        subject, body, from_email, [recipient],
                        fail_silently=False,
                    )
                else:
                    # ``.apply()`` runs synchronously in this process AND
                    # exercises the task code path (retry policy, time
                    # limits, etc.). ``.delay()`` would fire-and-forget
                    # against the broker, which is fine for prod but
                    # makes the smoketest's exit code unreliable.
                    result = task.apply(args=[subject, body, recipient])
                    if result.failed():
                        raise CommandError(
                            f"Celery task failed: {result.traceback}"
                        )
                self.stdout.write(self.style.SUCCESS(f"  ✓ {sc} email sent"))
            except Exception as exc:
                raise CommandError(
                    f"Failed to send {sc} email: {type(exc).__name__}: {exc}"
                ) from exc

        self.stdout.write(self.style.SUCCESS(
            f"Done. Check the inbox at {recipient} (and spam folder)."
        ))
