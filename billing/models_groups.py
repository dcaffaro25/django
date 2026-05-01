# -*- coding: utf-8 -*-
"""
Business Partner Groups — consolidação econômica curada por usuário.

Resolve casos que ``cnpj_root`` não cobre:
- CPF de sócio que paga conta da PJ.
- Outro CNPJ (raiz diferente) que opera no mesmo grupo econômico.
- Adquirente / marketplace na ponta bancária vs cliente real no livro
  (Cielo ↔ cliente, Mercado Livre ↔ consumidor, etc.).

Modelo:
- ``BusinessPartnerGroup`` é a unidade de consolidação. Tem um ``primary_partner``
  que serve de "rosto" do grupo nos relatórios.
- ``BusinessPartnerGroupMembership`` é o through-model com estado
  ``suggested → accepted → rejected`` (mesma máquina de estados de
  ``NFTransactionLink``). Sugestões aparecem para revisão; aceitação é
  excludente — um BP pertence a no máximo um Group ao mesmo tempo
  (constraint parcial no DB).

Sugestões são populadas por ``billing.services.bp_group_service.upsert_membership_suggestion``
chamada nos hooks de aceitação de links NF↔Tx, conciliação banco↔livro
e attach Invoice↔NF.
"""
from django.db import models
from django.db.models import Q

from multitenancy.models import TenantAwareBaseModel


class BusinessPartnerGroup(TenantAwareBaseModel):
    """Grupo econômico — consolidação curada de Business Partners."""

    name = models.CharField(
        max_length=255,
        help_text="Nome de exibição do grupo (geralmente o do primary_partner).",
    )
    description = models.TextField(blank=True)
    primary_partner = models.ForeignKey(
        'billing.BusinessPartner',
        on_delete=models.PROTECT,
        related_name='primary_of_group',
        help_text="BP que representa o grupo nas listagens consolidadas.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Grupo de Parceiros"
        verbose_name_plural = "Grupos de Parceiros"
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'primary_partner'],
                name='bpgroup_one_primary_per_partner',
            ),
        ]
        indexes = [
            models.Index(
                fields=['company', 'is_active'],
                name='bpgroup_company_active_idx',
            ),
        ]

    def __str__(self):
        return f"Grupo #{self.id} — {self.name}"


class BusinessPartnerGroupMembership(TenantAwareBaseModel):
    """Vínculo de um BusinessPartner a um Group, com estado de revisão."""

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

    # Métodos que podem disparar sugestões de agrupamento.
    METHOD_NF_TX_LINK = 'nf_tx_link'
    METHOD_BANK_RECONCILIATION = 'bank_reconciliation'
    METHOD_NF_INVOICE_ATTACH = 'nf_invoice_attach'
    METHOD_MANUAL = 'manual'
    METHOD_AUTO_ROOT = 'auto_root'  # mesma raiz CNPJ, agrupamento estrutural

    group = models.ForeignKey(
        BusinessPartnerGroup,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    business_partner = models.ForeignKey(
        'billing.BusinessPartner',
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
            "Ao atingir o threshold (default 3) o membership promove "
            "automaticamente para 'accepted'."
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
        related_name='bp_group_memberships_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Membro de Grupo"
        verbose_name_plural = "Membros de Grupos"
        constraints = [
            # Uma linha por (group, BP) — re-sugestões atualizam evidence.
            models.UniqueConstraint(
                fields=['group', 'business_partner'],
                name='bpgm_unique_group_partner',
            ),
            # Constraint parcial: um BP só pode ter UM membership aceito,
            # garantindo "um BP pertence a no máximo um Group ativo".
            models.UniqueConstraint(
                fields=['business_partner'],
                condition=Q(review_status='accepted'),
                name='bpgm_one_accepted_per_partner',
            ),
            # Um único 'primary' por grupo.
            models.UniqueConstraint(
                fields=['group'],
                condition=Q(role='primary'),
                name='bpgm_one_primary_per_group',
            ),
        ]
        indexes = [
            models.Index(
                fields=['company', 'business_partner', 'review_status'],
                name='bpgm_company_bp_status_idx',
            ),
            models.Index(
                fields=['group', 'role'],
                name='bpgm_group_role_idx',
            ),
        ]

    def __str__(self):
        return (
            f"BP#{self.business_partner_id} ↔ Group#{self.group_id} "
            f"({self.role}/{self.review_status})"
        )


class BusinessPartnerAlias(TenantAwareBaseModel):
    """Resolver hint para casos em que a string de CNPJ/CPF observada num
    extrato bancário ou descrição não bate com nenhum BP cadastrado.

    Diferente de ``BusinessPartnerGroupMembership`` (que liga DOIS BPs),
    aqui ligamos uma **string** (identificador observado) a UM BP. Útil para
    adquirentes (Cielo, Stone), marketplaces (Mercado Livre), gateways,
    apelidos de razão social etc. — qualquer coisa que apareça do lado
    bancário sem ter um BP correspondente cadastrado.

    Aprendido sob demanda: quando o usuário aceita uma reconciliação em que
    a CNPJ/CPF do extrato não resolve para nenhum BP, registramos uma
    sugestão; ao bater o threshold a sugestão promove para 'accepted' e
    passa a participar do scoring de matching futuro
    (``nf_link_service._score`` ganha ``+0.18`` quando o CNPJ bancário é
    alias de algum BP candidato).
    """

    REVIEW_SUGGESTED = 'suggested'
    REVIEW_ACCEPTED = 'accepted'
    REVIEW_REJECTED = 'rejected'
    REVIEW_CHOICES = [
        (REVIEW_SUGGESTED, 'Sugerido'),
        (REVIEW_ACCEPTED, 'Aceito'),
        (REVIEW_REJECTED, 'Rejeitado'),
    ]

    SOURCE_BANK_RECONCILIATION = 'bank_reconciliation'
    SOURCE_NF_TX_LINK = 'nf_tx_link'
    SOURCE_MANUAL = 'manual'

    KIND_CNPJ = 'cnpj'
    KIND_NAME = 'name'
    KIND_CHOICES = [
        (KIND_CNPJ, 'CNPJ/CPF'),
        (KIND_NAME, 'Nome'),
    ]

    business_partner = models.ForeignKey(
        'billing.BusinessPartner',
        on_delete=models.CASCADE,
        related_name='aliases',
    )
    kind = models.CharField(
        max_length=8,
        choices=KIND_CHOICES,
        default=KIND_CNPJ,
        db_index=True,
        help_text=(
            "Tipo de string aprendida. ``cnpj`` → dígitos de CNPJ/CPF "
            "(legacy, padrão). ``name`` → token de nome normalizado "
            "extraído da descrição da transação, para casos em que "
            "o lado banco não traz CNPJ (exportações, PIX informal, "
            "gateways e-commerce sem CPF do cliente, etc.)."
        ),
    )
    alias_identifier = models.CharField(
        max_length=80,
        db_index=True,
        help_text=(
            "String identificadora que deve resolver para este BP. "
            "Para ``kind=cnpj``: apenas dígitos do CNPJ/CPF. "
            "Para ``kind=name``: token de nome normalizado (lower, sem "
            "acentos, espaços colapsados, máx 80 chars)."
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
        default=SOURCE_BANK_RECONCILIATION,
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
        related_name='bp_aliases_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Apelido de Parceiro"
        verbose_name_plural = "Apelidos de Parceiros"
        constraints = [
            # Mesma string só pode resolver para um BP por tenant (caso
            # contrário o boost ficaria ambíguo). Compound em ``kind``
            # para que um CNPJ "12345678000199" e um nome com a mesma
            # forma (improvável, mas possível) coexistam sem conflito.
            models.UniqueConstraint(
                fields=['company', 'kind', 'alias_identifier'],
                condition=Q(review_status='accepted'),
                name='bpalias_one_accepted_per_identifier',
            ),
            # Uma linha por (BP, kind, identifier) — re-sugestões atualizam evidence.
            models.UniqueConstraint(
                fields=['business_partner', 'kind', 'alias_identifier'],
                name='bpalias_unique_bp_identifier',
            ),
        ]
        indexes = [
            models.Index(
                fields=['company', 'kind', 'alias_identifier', 'review_status'],
                name='bpalias_lookup_idx',
            ),
        ]

    def __str__(self):
        return f"alias({self.alias_identifier}) → BP#{self.business_partner_id}"
