# -*- coding: utf-8 -*-
"""
Product Service Groups — consolidação curada de produtos / serviços.

Mirrors ``BusinessPartnerGroup`` but for ``ProductService``. Solves the
case where the same physical SKU has multiple ``ProductService`` rows
because different ERP codes / vendor catalogs / data migrations brought
in independent records (Evolat: e.g. "1003 - NAVEIA ORIGINAL 1L X 12"
exists 4 times under codes ``10595``, ``11957``, ``000093``,
``PRD00001``).

Why a group instead of "merge then delete":
- Historical NF items, invoice lines, and journal entries are already
  linked to specific ``ProductService.id``s. Merging would either
  re-write those FKs (lossy audit trail) or leave dangling references.
- The group lets us *report* one row per family without rewriting
  history. ``GROUP BY COALESCE(group_id, ps_id)`` collapses members
  for analytics; the underlying rows stay untouched.
- A "primary" member becomes the consolidated row's display label,
  matching the BP-Group story.

Auto-discovery (``ps_group_service``) buckets products by normalized
name and emits ``suggested`` memberships when ≥2 rows share a name.
Operator review on ``/billing/grupos`` accepts → membership flips to
``accepted`` and the constraint enforces ≤1 accepted group per
product.

This is conceptually distinct from:
- ``ProductServiceCategory`` — taxonomy (family / variant tree, e.g.
  Naveia → Deleitinho → Chocolate). One product belongs to one
  category. A group consolidates equivalents within a single SKU.
- Bundles (planned, separate model) — a parent product made up of
  ``N × component`` rows; not equivalence, but composition.
"""
from django.db import models
from django.db.models import Q

from multitenancy.models import TenantAwareBaseModel


class ProductServiceGroup(TenantAwareBaseModel):
    """Grupo de produtos / serviços — consolidação curada de SKUs equivalentes."""

    name = models.CharField(
        max_length=255,
        help_text="Nome de exibição do grupo (geralmente o do primary_product).",
    )
    description = models.TextField(blank=True)
    primary_product = models.ForeignKey(
        'billing.ProductService',
        on_delete=models.PROTECT,
        related_name='primary_of_group',
        help_text="Produto que representa o grupo nas listagens consolidadas.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Grupo de Produtos"
        verbose_name_plural = "Grupos de Produtos"
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'primary_product'],
                name='psgroup_one_primary_per_product',
            ),
        ]
        indexes = [
            models.Index(
                fields=['company', 'is_active'],
                name='psgroup_company_active_idx',
            ),
        ]

    def __str__(self):
        return f"GrupoProd #{self.id} — {self.name}"


class ProductServiceGroupMembership(TenantAwareBaseModel):
    """Vínculo de um ProductService a um Group, com estado de revisão."""

    ROLE_PRIMARY = 'primary'
    ROLE_MEMBER = 'member'
    ROLE_CHOICES = [
        (ROLE_PRIMARY, 'Primário'),
        (ROLE_MEMBER, 'Membro'),
    ]

    REVIEW_SUGGESTED = 'suggested'
    REVIEW_ACCEPTED = 'accepted'
    REVIEW_REJECTED = 'rejected'
    REVIEW_CHOICES = [
        (REVIEW_SUGGESTED, 'Sugerido'),
        (REVIEW_ACCEPTED, 'Aceito'),
        (REVIEW_REJECTED, 'Rejeitado'),
    ]

    # Methods that can spawn grouping suggestions.
    METHOD_AUTO_NAME = 'auto_name'              # exact normalized name match
    METHOD_AUTO_HEAD = 'auto_head'              # first-N-token prefix match
    METHOD_AUTO_CODE_PATTERN = 'auto_code'      # vendor-prefix code clusters
    METHOD_NF_ITEM_LINK = 'nf_item_link'        # observed via NF item attach
    METHOD_MANUAL = 'manual'

    group = models.ForeignKey(
        ProductServiceGroup,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    product_service = models.ForeignKey(
        'billing.ProductService',
        on_delete=models.CASCADE,
        related_name='group_memberships',
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default=ROLE_MEMBER,
    )
    review_status = models.CharField(
        max_length=10,
        choices=REVIEW_CHOICES,
        default=REVIEW_SUGGESTED,
        db_index=True,
    )
    confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=0,
        help_text="Confiança máxima entre as evidências acumuladas (0..1).",
    )
    hit_count = models.PositiveIntegerField(
        default=1,
        help_text=(
            "Quantos sinais distintos sustentam esta sugestão. "
            "Ao atingir o threshold (default 1 para auto_name por já ser "
            "match exato; 3 para auto_head por ser fuzzier) o membership "
            "promove automaticamente para 'accepted'."
        ),
    )
    evidence = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Histórico de sinais que sustentam a sugestão: lista de "
            '{"method", "source_id", "at", "confidence", "kind"}.'
        ),
    )
    reviewed_by = models.ForeignKey(
        'multitenancy.CustomUser',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ps_group_memberships_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Membro de Grupo de Produtos"
        verbose_name_plural = "Membros de Grupos de Produtos"
        constraints = [
            models.UniqueConstraint(
                fields=['group', 'product_service'],
                name='psgm_unique_group_product',
            ),
            # A product can only have ONE accepted group membership at
            # a time -- mirrors BPGM. Suggestions for other groups stay
            # suggested until either accepted (would conflict) or
            # rejected.
            models.UniqueConstraint(
                fields=['product_service'],
                condition=Q(review_status='accepted'),
                name='psgm_one_accepted_per_product',
            ),
            models.UniqueConstraint(
                fields=['group'],
                condition=Q(role='primary'),
                name='psgm_one_primary_per_group',
            ),
        ]
        indexes = [
            models.Index(
                fields=['company', 'product_service', 'review_status'],
                name='psgm_company_prod_status_idx',
            ),
            models.Index(
                fields=['group', 'role'],
                name='psgm_group_role_idx',
            ),
        ]

    def __str__(self):
        return (
            f"PS#{self.product_service_id} ↔ GrupoProd#{self.group_id} "
            f"({self.role}/{self.review_status})"
        )


class ProductServiceAlias(TenantAwareBaseModel):
    """Resolver hint: external string → ProductService.

    Mirrors ``BusinessPartnerAlias`` (with ``kind`` distinguishing
    ``code`` from ``name``) but on the product side. Stops the import
    pipeline from creating a fresh ``ProductService`` row every time
    it sees a slightly different code or descricao for an SKU we
    already know.

    Two flavours:
    - ``kind='code'`` — a vendor / ERP code (e.g. ``PRD00003``,
      ``11957``) observed in an NF item or import file. Resolves to
      the canonical ProductService for the SKU. Common when ERP
      migrations re-key the catalog.
    - ``kind='name'`` — a normalized name token from an NF item
      ``descricao``. Resolves the same SKU even when the code is
      brand-new but the name matches a known entry.

    Auto-promotion threshold is conservative -- the product side has
    less semantic verification than the BP side (no CNPJ to anchor),
    so we wait for a few independent observations before treating
    a learned mapping as authoritative.
    """

    REVIEW_SUGGESTED = 'suggested'
    REVIEW_ACCEPTED = 'accepted'
    REVIEW_REJECTED = 'rejected'
    REVIEW_CHOICES = [
        (REVIEW_SUGGESTED, 'Sugerido'),
        (REVIEW_ACCEPTED, 'Aceito'),
        (REVIEW_REJECTED, 'Rejeitado'),
    ]

    SOURCE_NF_ITEM = 'nf_item'
    SOURCE_IMPORT = 'import'
    SOURCE_MANUAL = 'manual'

    KIND_CODE = 'code'
    KIND_NAME = 'name'
    KIND_CHOICES = [
        (KIND_CODE, 'Código ERP'),
        (KIND_NAME, 'Nome'),
    ]

    product_service = models.ForeignKey(
        'billing.ProductService',
        on_delete=models.CASCADE,
        related_name='aliases',
    )
    kind = models.CharField(
        max_length=8,
        choices=KIND_CHOICES,
        default=KIND_CODE,
        db_index=True,
    )
    alias_identifier = models.CharField(
        max_length=80,
        db_index=True,
        help_text=(
            "String identificadora que deve resolver para este produto. "
            "Para ``kind=code``: código vendor/ERP (case-insensitive, "
            "espaços colapsados). Para ``kind=name``: token de nome "
            "normalizado (lower, sem acentos, ≤80 chars)."
        ),
    )
    review_status = models.CharField(
        max_length=10,
        choices=REVIEW_CHOICES,
        default=REVIEW_SUGGESTED,
        db_index=True,
    )
    source = models.CharField(
        max_length=32,
        default=SOURCE_NF_ITEM,
        help_text="Como esta sugestão foi gerada.",
    )
    confidence = models.DecimalField(
        max_digits=4, decimal_places=3, default=0,
    )
    hit_count = models.PositiveIntegerField(default=1)
    last_used_at = models.DateTimeField(null=True, blank=True)
    evidence = models.JSONField(default=list, blank=True)
    reviewed_by = models.ForeignKey(
        'multitenancy.CustomUser', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='ps_aliases_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Apelido de Produto"
        verbose_name_plural = "Apelidos de Produtos"
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'kind', 'alias_identifier'],
                condition=Q(review_status='accepted'),
                name='psalias_one_accepted_per_identifier',
            ),
            models.UniqueConstraint(
                fields=['product_service', 'kind', 'alias_identifier'],
                name='psalias_unique_prod_identifier',
            ),
        ]
        indexes = [
            models.Index(
                fields=['company', 'kind', 'alias_identifier', 'review_status'],
                name='psalias_lookup_idx',
            ),
        ]

    def __str__(self):
        return (
            f"alias({self.kind}:{self.alias_identifier}) → PS#{self.product_service_id}"
        )
