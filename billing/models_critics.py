# -*- coding: utf-8 -*-
"""
CriticAcknowledgement — operator-facing "this finding is expected, ignore it".

Critics are computed live from NF data (see billing/services/critics_service.py),
but operators need a way to mark legitimate exceptions (e.g. a known bundle
expansion case) so the count stops nagging on every page load. Acknowledgement
is keyed on (invoice, kind, subject_type, subject_id) — so acknowledging one
"unit price drift" finding doesn't suppress all of them.
"""
from django.conf import settings
from django.db import models

from multitenancy.models import TenantAwareBaseModel


class CriticAcknowledgement(TenantAwareBaseModel):
    """
    A single ack on a specific (invoice, critic-kind, subject) tuple.
    Re-running the critics engine after an ack adds an
    ``acknowledged: true`` flag on the matching record but doesn't
    remove it — operators keep visibility of past triage decisions.
    """
    invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.CASCADE,
        related_name="critic_acknowledgements",
    )
    kind = models.CharField(
        max_length=64, db_index=True,
        help_text="Critic kind from critics_service (e.g. unit_price_drift).",
    )
    subject_type = models.CharField(
        max_length=32,
        help_text="'invoice' / 'nota_fiscal' / 'nota_fiscal_item' — matches Critic.subject_type.",
    )
    subject_id = models.IntegerField(
        db_index=True,
        help_text="ID of the subject record the critic refers to.",
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="critic_acks",
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = "Aceite de Crítica"
        verbose_name_plural = "Aceites de Críticas"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "invoice", "kind", "subject_type", "subject_id"],
                name="billing_critic_ack_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["company", "invoice", "kind"],
                name="bill_critack_inv_kind_idx",
            ),
        ]

    def __str__(self):
        return f"Ack: invoice#{self.invoice_id} {self.kind} subj={self.subject_type}#{self.subject_id}"
