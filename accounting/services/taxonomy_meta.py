"""Canonical taxonomy enums + reference metadata for the chart of accounts.

This module is the single source of truth for the two new fields on
:class:`accounting.models.Account` introduced in the CoA enrichment work:

* ``report_category`` — closed enum, 14 values aligned to CPC 26's
  statement-of-financial-position + statement-of-comprehensive-income
  line items. One per account; descendants inherit via MPTT walk.

* ``tags`` — closed enum, ~40 blessed values for cross-cutting markers
  (cash, debt, EBITDA addback, non-recurring, value-added input, etc.)
  that don't follow tree hierarchy. Many per account; descendants
  union with ancestors via MPTT walk.

Why a Python module and not a DB table:
  * Reference data with no operator editing belongs in code — easier to
    review, version, ship, and update than DB rows.
  * Definitions, examples and antiexamples are read by the operator UI
    for tooltips and by the AI prompt builder; both are call sites that
    don't want a DB roundtrip.
  * The closed-enum guarantee is enforced at the model level via
    ``choices=`` — if the enum changes, the migration is the single
    place that documents the change.

If/when operators need to edit definitions in production, this module
gets promoted to a DB table. Don't pre-emptively pay that cost.

The corresponding Plan agent design (2026-04-28) deferred the fine-
grained ``report_role`` field, the ``sped_referencial_code`` /
``ifrs_concept`` cross-walks, and the multi-tier AI enrichment
audit fields (``enrichment_*``). Those land in Phase 1.5+ when a
specific use case requires them — see the project memory for the
full rationale.
"""
from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


# ---------------------------------------------------------------------
# report_category — 14 values aligned to CPC 26
# ---------------------------------------------------------------------

REPORT_CATEGORY_CHOICES = [
    ("ativo_circulante", "Ativo Circulante"),
    ("ativo_nao_circulante", "Ativo Não Circulante"),
    ("passivo_circulante", "Passivo Circulante"),
    ("passivo_nao_circulante", "Passivo Não Circulante"),
    ("patrimonio_liquido", "Patrimônio Líquido"),
    ("receita_bruta", "Receita Bruta"),
    ("deducao_receita", "Deduções da Receita"),
    ("custo", "Custo"),
    ("despesa_operacional", "Despesa Operacional"),
    ("receita_financeira", "Receita Financeira"),
    ("despesa_financeira", "Despesa Financeira"),
    ("outras_receitas", "Outras Receitas/Despesas"),
    ("imposto_sobre_lucro", "Tributos sobre Lucro"),
    ("memo", "Memo / Compensação"),
]

REPORT_CATEGORY_VALUES = frozenset(code for code, _ in REPORT_CATEGORY_CHOICES)


class CategoryMeta(TypedDict):
    label_pt: str
    label_en: str
    definition_pt: str
    cpc_reference: str
    sign_hint: str  # "debit_natural" | "credit_natural" | "any"
    used_by_reports: List[str]
    examples_pt: List[str]
    antiexamples_pt: List[str]


REPORT_CATEGORY_META: Dict[str, CategoryMeta] = {
    "ativo_circulante": {
        "label_pt": "Ativo Circulante",
        "label_en": "Current Assets",
        "definition_pt": (
            "Bens e direitos realizáveis em até 12 meses do exercício social ou no "
            "curso normal do ciclo operacional. Inclui caixa, equivalentes, contas "
            "a receber, estoques e despesas antecipadas."
        ),
        "cpc_reference": "CPC 26.66",
        "sign_hint": "debit_natural",
        "used_by_reports": ["bp", "dfc", "metrics"],
        "examples_pt": [
            "Caixa", "Bancos Conta Movimento", "Aplicações Financeiras",
            "Clientes", "Estoques de Mercadorias", "Adiantamentos a Fornecedores",
            "Impostos a Recuperar",
        ],
        "antiexamples_pt": [
            "Imobilizado (vai em ativo_nao_circulante)",
            "Investimentos de longo prazo",
            "Realizável a longo prazo",
        ],
    },
    "ativo_nao_circulante": {
        "label_pt": "Ativo Não Circulante",
        "label_en": "Non-Current Assets",
        "definition_pt": (
            "Bens e direitos realizáveis após 12 meses ou destinados ao uso "
            "permanente da entidade. Inclui investimentos, imobilizado, "
            "intangível e suas contas retificadoras."
        ),
        "cpc_reference": "CPC 26.66",
        "sign_hint": "debit_natural",
        "used_by_reports": ["bp", "metrics"],
        "examples_pt": [
            "Investimentos em Coligadas", "Móveis e Utensílios", "Veículos",
            "Software", "Marcas e Patentes", "(-) Depreciação Acumulada",
            "(-) Amortização Acumulada", "Depósitos Judiciais",
        ],
        "antiexamples_pt": [
            "Aplicações de curto prazo (vai em ativo_circulante)",
            "Estoques (sempre circulante)",
        ],
    },
    "passivo_circulante": {
        "label_pt": "Passivo Circulante",
        "label_en": "Current Liabilities",
        "definition_pt": (
            "Obrigações a serem liquidadas em até 12 meses do exercício social ou "
            "no curso normal do ciclo operacional."
        ),
        "cpc_reference": "CPC 26.69",
        "sign_hint": "credit_natural",
        "used_by_reports": ["bp", "dfc", "metrics"],
        "examples_pt": [
            "Fornecedores", "Empréstimos a Curto Prazo", "Salários a Pagar",
            "INSS a Pagar", "ICMS a Recolher", "Adiantamentos de Clientes",
            "Provisão para Férias",
        ],
        "antiexamples_pt": [
            "Empréstimos com vencimento >12 meses",
            "Provisões trabalhistas judiciais (longo prazo)",
        ],
    },
    "passivo_nao_circulante": {
        "label_pt": "Passivo Não Circulante",
        "label_en": "Non-Current Liabilities",
        "definition_pt": (
            "Obrigações a serem liquidadas após 12 meses ou no decorrer do ciclo "
            "operacional quando este for superior a 12 meses."
        ),
        "cpc_reference": "CPC 26.69",
        "sign_hint": "credit_natural",
        "used_by_reports": ["bp", "metrics"],
        "examples_pt": [
            "Empréstimos a Longo Prazo", "Debêntures",
            "Provisões para Contingências Trabalhistas",
            "Impostos Diferidos Passivo", "Arrendamento a Pagar (IFRS 16)",
        ],
        "antiexamples_pt": [
            "Parcela corrente de empréstimo de longo prazo (passivo_circulante)",
        ],
    },
    "patrimonio_liquido": {
        "label_pt": "Patrimônio Líquido",
        "label_en": "Equity",
        "definition_pt": (
            "Valor residual dos ativos da entidade após dedução de todos os "
            "passivos. Compreende capital social, reservas, ajustes de avaliação "
            "patrimonial e lucros ou prejuízos acumulados."
        ),
        "cpc_reference": "CPC 26.78",
        "sign_hint": "credit_natural",
        "used_by_reports": ["bp", "dmpl", "dva", "metrics"],
        "examples_pt": [
            "Capital Social", "(-) Capital a Integralizar", "Reserva Legal",
            "Reserva de Lucros", "Lucros Acumulados",
            "Ajustes de Avaliação Patrimonial", "(-) Ações em Tesouraria",
        ],
        "antiexamples_pt": [
            "Lucro do exercício (esse é flow, não estoque)",
        ],
    },
    "receita_bruta": {
        "label_pt": "Receita Bruta",
        "label_en": "Gross Revenue",
        "definition_pt": (
            "Receita bruta de vendas e serviços antes das deduções de impostos "
            "sobre vendas, devoluções e abatimentos. Reconhecida conforme CPC 47 "
            "(transferência de controle)."
        ),
        "cpc_reference": "CPC 26.82(a) + CPC 47",
        "sign_hint": "credit_natural",
        "used_by_reports": ["dre", "dva", "metrics"],
        "examples_pt": [
            "Receita Bruta de Vendas de Mercadorias",
            "Receita Bruta de Vendas de Produtos",
            "Receita de Prestação de Serviços",
            "Receita de Aluguel (atividade-fim)",
        ],
        "antiexamples_pt": [
            "Receita financeira (vai em receita_financeira)",
            "Ganho na venda de imobilizado (outras_receitas)",
            "ICMS sobre vendas (deducao_receita, não receita_bruta)",
        ],
    },
    "deducao_receita": {
        "label_pt": "Deduções da Receita",
        "label_en": "Revenue Deductions",
        "definition_pt": (
            "Tributos incidentes sobre vendas, devoluções, abatimentos e "
            "descontos comerciais que reduzem a receita bruta para chegar à "
            "receita líquida."
        ),
        "cpc_reference": "CPC 47.B49 + Lei 6.404/76 art. 187",
        "sign_hint": "debit_natural",
        "used_by_reports": ["dre", "metrics"],
        "examples_pt": [
            "(-) ICMS sobre Vendas", "(-) PIS sobre Vendas",
            "(-) COFINS sobre Vendas", "(-) ISS sobre Serviços",
            "(-) IPI sobre Vendas", "(-) Devoluções de Vendas",
            "(-) Abatimentos sobre Vendas",
        ],
        "antiexamples_pt": [
            "IRPJ/CSLL (imposto_sobre_lucro)",
            "Despesas com tributos administrativos (despesa_operacional)",
        ],
    },
    "custo": {
        "label_pt": "Custo",
        "label_en": "Cost of Goods/Services Sold",
        "definition_pt": (
            "Custo dos produtos vendidos, mercadorias vendidas ou serviços "
            "prestados — diretamente atribuível à geração da receita. Subtraído "
            "da Receita Líquida para apurar o Lucro Bruto."
        ),
        "cpc_reference": "CPC 16 + CPC 26.82(b)",
        "sign_hint": "debit_natural",
        "used_by_reports": ["dre", "dva", "metrics"],
        "examples_pt": [
            "CMV - Custo das Mercadorias Vendidas",
            "CPV - Custo dos Produtos Vendidos",
            "CSV - Custo dos Serviços Prestados",
            "Mão-de-Obra Direta", "Matéria-Prima Consumida",
        ],
        "antiexamples_pt": [
            "Despesa comercial (despesa_operacional)",
            "Despesas com vendedores (despesa_operacional, não custo)",
            "Frete sobre vendas (despesa_operacional)",
        ],
    },
    "despesa_operacional": {
        "label_pt": "Despesa Operacional",
        "label_en": "Operating Expenses",
        "definition_pt": (
            "Despesas necessárias à operação da empresa, incluindo comerciais, "
            "administrativas, depreciação/amortização e outras operacionais. "
            "Subtraídas do Lucro Bruto para apurar o EBIT."
        ),
        "cpc_reference": "CPC 26.99 + CPC 26.103",
        "sign_hint": "debit_natural",
        "used_by_reports": ["dre", "metrics"],
        "examples_pt": [
            "Despesa Comercial", "Despesa Administrativa",
            "Salários do Administrativo", "Aluguel do Escritório",
            "Honorários Advocatícios", "Depreciação e Amortização",
            "Perdas com Créditos (PCLD)", "Marketing e Publicidade",
        ],
        "antiexamples_pt": [
            "Juros sobre empréstimos (despesa_financeira)",
            "Custo da matéria-prima consumida (custo)",
            "IRPJ/CSLL (imposto_sobre_lucro)",
        ],
    },
    "receita_financeira": {
        "label_pt": "Receita Financeira",
        "label_en": "Finance Income",
        "definition_pt": (
            "Receitas decorrentes de aplicações financeiras, juros ativos, "
            "variações cambiais ativas e descontos obtidos. Apresentada no "
            "Resultado Financeiro líquido."
        ),
        "cpc_reference": "CPC 26.82(b) + CPC 48",
        "sign_hint": "credit_natural",
        "used_by_reports": ["dre", "metrics"],
        "examples_pt": [
            "Rendimentos de Aplicações Financeiras", "Juros Recebidos",
            "Variação Cambial Ativa",
            "Descontos Obtidos por Pagamento Antecipado",
        ],
        "antiexamples_pt": [
            "Receita de aluguel da atividade-fim (receita_bruta)",
            "Ganho na venda de investimento (outras_receitas)",
        ],
    },
    "despesa_financeira": {
        "label_pt": "Despesa Financeira",
        "label_en": "Finance Costs",
        "definition_pt": (
            "Despesas com juros sobre empréstimos, encargos financeiros, "
            "variações cambiais passivas, IOF, tarifas bancárias e descontos "
            "concedidos."
        ),
        "cpc_reference": "CPC 26.82(b) + CPC 48",
        "sign_hint": "debit_natural",
        "used_by_reports": ["dre", "metrics"],
        "examples_pt": [
            "Juros sobre Empréstimos", "Variação Cambial Passiva",
            "IOF sobre Operações de Crédito", "Tarifas Bancárias",
            "Descontos Concedidos por Pagamento Antecipado",
            "Encargos sobre Antecipação de Recebíveis",
        ],
        "antiexamples_pt": [
            "Despesa com tarifa de cartão da máquina (despesa_operacional)",
            "Imposto sobre lucro (imposto_sobre_lucro)",
        ],
    },
    "outras_receitas": {
        "label_pt": "Outras Receitas/Despesas",
        "label_en": "Other Operating Items",
        "definition_pt": (
            "Resultados não recorrentes ou periféricos à operação principal: "
            "ganhos/perdas na alienação de ativo permanente, recuperação de "
            "créditos, doações recebidas, indenizações."
        ),
        "cpc_reference": "CPC 26.99",
        "sign_hint": "any",
        "used_by_reports": ["dre"],
        "examples_pt": [
            "Ganho na Alienação de Imobilizado",
            "Perda na Alienação de Imobilizado",
            "Recuperação de Créditos Tributários",
            "Doações Recebidas", "Indenizações Recebidas",
        ],
        "antiexamples_pt": [
            "Receita de aluguel da atividade-fim (receita_bruta)",
            "Multa contratual recebida na operação (receita_bruta)",
        ],
    },
    "imposto_sobre_lucro": {
        "label_pt": "Tributos sobre Lucro",
        "label_en": "Income Taxes",
        "definition_pt": (
            "IRPJ e CSLL (correntes e diferidos) calculados sobre o Lucro antes "
            "do Imposto de Renda (LAIR). Apresentados em linha separada na DRE "
            "conforme CPC 32."
        ),
        "cpc_reference": "CPC 32",
        "sign_hint": "debit_natural",
        "used_by_reports": ["dre", "dfc", "metrics"],
        "examples_pt": [
            "IRPJ a Pagar", "CSLL a Pagar",
            "IRPJ Diferido", "CSLL Diferido",
        ],
        "antiexamples_pt": [
            "ICMS, PIS, COFINS, ISS (deducao_receita)",
            "INSS, FGTS (despesa_operacional via encargos)",
        ],
    },
    "memo": {
        "label_pt": "Memo / Compensação",
        "label_en": "Memo / Off-Statement",
        "definition_pt": (
            "Contas de compensação e contas memo que não compõem ativo, "
            "passivo, PL nem resultado. Usadas para registro paralelo "
            "(garantias, ações em poder de terceiros, contratos)."
        ),
        "cpc_reference": "ITG 2000.32",
        "sign_hint": "any",
        "used_by_reports": [],
        "examples_pt": [
            "Garantias Concedidas - Memo",
            "Avais e Fianças - Memo",
            "Ações em Poder de Terceiros",
        ],
        "antiexamples_pt": [
            "Qualquer conta com efeito patrimonial real (não vai aqui)",
        ],
    },
}


# ---------------------------------------------------------------------
# tags — closed enum, ~40 blessed values for cross-cutting markers
# ---------------------------------------------------------------------

TAG_CHOICES = [
    # Cash and equivalents
    ("cash", "Caixa"),
    ("bank_account", "Conta Bancária"),
    ("restricted_cash", "Caixa Restrito"),
    # Account-level structure
    ("contra_account", "Conta Retificadora"),
    # DFC support
    ("non_cash", "Item Não-Caixa"),
    ("working_capital", "Capital de Giro"),
    # EBITDA / metrics support
    ("ebitda_addback", "Adicionado no EBITDA"),
    ("non_recurring", "Não-Recorrente"),
    # DVA support
    ("value_added_input", "Insumo da DVA"),
    # Asset classification
    ("fixed_asset", "Imobilizado Depreciável"),
    ("intangible_asset", "Intangível Amortizável"),
    # Debt classification
    ("debt", "Dívida Onerosa"),
    ("short_term", "Curto Prazo"),
    ("long_term", "Longo Prazo"),
    # Brazilian taxes (cross-cutting)
    ("icms", "ICMS"),
    ("pis", "PIS"),
    ("cofins", "COFINS"),
    ("iss", "ISS"),
    ("ipi", "IPI"),
    ("inss", "INSS"),
    ("fgts", "FGTS"),
    ("irrf", "IRRF a Compensar"),
    # Currency / consolidation
    ("foreign_currency", "Moeda Estrangeira"),
    ("intercompany", "Intercompany"),
    ("elimination", "Eliminação Consolidação"),
    # Timing
    ("accrual", "Provisão (Accrual)"),
    ("prepaid", "Antecipado"),
    # Revenue analytics
    ("product_sales", "Venda de Produtos"),
    ("service_revenue", "Receita de Serviços"),
    ("subscription_revenue", "Receita Recorrente / Assinatura"),
    ("export_revenue", "Receita de Exportação"),
    # Brazilian-specific equity / distribution
    ("jcp", "Juros sobre Capital Próprio"),
    ("dividends", "Dividendos"),
    # Comprehensive income / IFRS-specific
    ("comprehensive_income", "Outros Resultados Abrangentes"),
    ("ifrs16_lease", "Arrendamento IFRS 16"),
    # Memo
    ("guaranteed", "Garantia Concedida"),
]

TAG_VALUES = frozenset(code for code, _ in TAG_CHOICES)


class TagMeta(TypedDict):
    label_pt: str
    label_en: str
    definition_pt: str
    cpc_reference: Optional[str]
    used_by_reports: List[str]
    examples_pt: List[str]


TAG_META: Dict[str, TagMeta] = {
    "cash": {
        "label_pt": "Caixa",
        "label_en": "Cash",
        "definition_pt": (
            "Componente de Caixa para fins de Liquidez Imediata e DFC. Aplica-se "
            "a contas com saldo disponível imediatamente — caixa, bancos, "
            "aplicações de liquidez diária."
        ),
        "cpc_reference": "CPC 03.6",
        "used_by_reports": ["dfc", "metrics"],
        "examples_pt": ["Conta Movimento Itaú", "BTG Liquidez Diária"],
    },
    "bank_account": {
        "label_pt": "Conta Bancária",
        "label_en": "Bank Account",
        "definition_pt": (
            "Marca conta vinculada a um BankAccount via FK. Auto-aplicada pelo "
            "importador quando há link; operadores podem aplicar manualmente."
        ),
        "cpc_reference": None,
        "used_by_reports": ["dfc"],
        "examples_pt": ["Itaú Conta Movimento", "BTG Conta Movimento"],
    },
    "restricted_cash": {
        "label_pt": "Caixa Restrito",
        "label_en": "Restricted Cash",
        "definition_pt": (
            "Caixa cuja disponibilidade está restrita por covenant, garantia ou "
            "afetação legal. Excluído de Liquidez Imediata e da soma `cash`."
        ),
        "cpc_reference": "CPC 03.8",
        "used_by_reports": ["bp", "metrics"],
        "examples_pt": [
            "Conta Caução", "Reserva de Garantia",
            "Aplicação Vinculada a Empréstimo",
        ],
    },
    "contra_account": {
        "label_pt": "Conta Retificadora",
        "label_en": "Contra Account",
        "definition_pt": (
            "Conta com saldo natural oposto à conta principal que retifica. "
            "Inclui depreciação acumulada, capital a integralizar, ações em "
            "tesouraria, PCLD."
        ),
        "cpc_reference": "Lei 6.404/76",
        "used_by_reports": [],
        "examples_pt": [
            "(-) Depreciação Acumulada", "(-) Capital a Integralizar",
            "(-) PCLD",
        ],
    },
    "non_cash": {
        "label_pt": "Item Não-Caixa",
        "label_en": "Non-Cash Item",
        "definition_pt": (
            "Despesa/receita sem efeito caixa. Adicionada de volta no ajuste do "
            "FCO na DFC indireta."
        ),
        "cpc_reference": "CPC 03.18",
        "used_by_reports": ["dfc"],
        "examples_pt": [
            "Depreciação", "Amortização", "PCLD",
            "Provisão para Contingências",
        ],
    },
    "working_capital": {
        "label_pt": "Capital de Giro",
        "label_en": "Working Capital",
        "definition_pt": (
            "Componente de capital de giro. Variações entram no FCO indireto. "
            "Inclui contas a receber, estoques, fornecedores, adiantamentos."
        ),
        "cpc_reference": "CPC 03.20",
        "used_by_reports": ["dfc", "metrics"],
        "examples_pt": [
            "Clientes", "Estoques", "Fornecedores",
            "Adiantamentos a Fornecedores",
        ],
    },
    "ebitda_addback": {
        "label_pt": "Adicionado no EBITDA",
        "label_en": "EBITDA Addback",
        "definition_pt": (
            "Item adicionado de volta no cálculo do EBITDA: depreciação, "
            "amortização. Subset de non_cash que afeta EBIT."
        ),
        "cpc_reference": "CVM 527/2012",
        "used_by_reports": ["dre", "metrics"],
        "examples_pt": ["Depreciação e Amortização"],
    },
    "non_recurring": {
        "label_pt": "Não-Recorrente",
        "label_en": "Non-Recurring",
        "definition_pt": (
            "Item considerado atípico/não-recorrente, excluído no cálculo do "
            "EBITDA Ajustado conforme política de divulgação da empresa."
        ),
        "cpc_reference": "CVM 527/2012",
        "used_by_reports": ["metrics"],
        "examples_pt": [
            "Indenização Trabalhista Atípica",
            "Multa Tributária Não-Recorrente",
            "Despesa de Reestruturação",
        ],
    },
    "value_added_input": {
        "label_pt": "Insumo da DVA",
        "label_en": "Value Added Input",
        "definition_pt": (
            "Insumo subtraído na 'Geração de Valor' da DVA: matérias-primas, "
            "mercadorias, serviços de terceiros, energia."
        ),
        "cpc_reference": "CPC 09.13",
        "used_by_reports": ["dva"],
        "examples_pt": ["CMV", "CPV", "Energia Elétrica Industrial"],
    },
    "fixed_asset": {
        "label_pt": "Imobilizado Depreciável",
        "label_en": "Depreciable Fixed Asset",
        "definition_pt": (
            "Bem do imobilizado sujeito a depreciação. Não inclui terrenos. "
            "Aplicada para análise de CAPEX e da DFC investing."
        ),
        "cpc_reference": "CPC 27",
        "used_by_reports": ["dfc", "metrics"],
        "examples_pt": [
            "Edifícios", "Máquinas", "Veículos", "Móveis e Utensílios",
        ],
    },
    "intangible_asset": {
        "label_pt": "Intangível Amortizável",
        "label_en": "Amortisable Intangible",
        "definition_pt": "Ativo intangível com vida útil definida, sujeito a amortização.",
        "cpc_reference": "CPC 04.97",
        "used_by_reports": ["dfc"],
        "examples_pt": ["Software", "Marcas com Vida Útil Definida"],
    },
    "debt": {
        "label_pt": "Dívida Onerosa",
        "label_en": "Interest-Bearing Debt",
        "definition_pt": (
            "Passivo oneroso usado no cálculo de Dívida Bruta e Dívida Líquida. "
            "Distingue empréstimos de fornecedores comerciais."
        ),
        "cpc_reference": "CPC 48",
        "used_by_reports": ["bp", "metrics"],
        "examples_pt": [
            "Empréstimos Bancários", "Debêntures",
            "Arrendamento Financeiro IFRS 16",
        ],
    },
    "short_term": {
        "label_pt": "Curto Prazo",
        "label_en": "Short-Term",
        "definition_pt": "Vencimento ≤12 meses. Usada para reclassificação automática.",
        "cpc_reference": "CPC 26.66",
        "used_by_reports": [],
        "examples_pt": ["Empréstimo Curto Prazo"],
    },
    "long_term": {
        "label_pt": "Longo Prazo",
        "label_en": "Long-Term",
        "definition_pt": "Vencimento >12 meses.",
        "cpc_reference": "CPC 26.66",
        "used_by_reports": [],
        "examples_pt": ["Empréstimo Longo Prazo"],
    },
    "icms": {
        "label_pt": "ICMS", "label_en": "ICMS Tax",
        "definition_pt": "Imposto sobre Circulação de Mercadorias e Serviços. Para análise de carga tributária.",
        "cpc_reference": None,
        "used_by_reports": ["metrics"],
        "examples_pt": ["(-) ICMS sobre Vendas", "ICMS a Recolher"],
    },
    "pis": {
        "label_pt": "PIS", "label_en": "PIS Tax",
        "definition_pt": "Programa de Integração Social. Análise tributária.",
        "cpc_reference": None,
        "used_by_reports": ["metrics"],
        "examples_pt": ["(-) PIS sobre Vendas", "PIS a Recolher"],
    },
    "cofins": {
        "label_pt": "COFINS", "label_en": "COFINS Tax",
        "definition_pt": "Contribuição para Financiamento da Seguridade Social.",
        "cpc_reference": None,
        "used_by_reports": ["metrics"],
        "examples_pt": ["(-) COFINS sobre Vendas", "COFINS a Recolher"],
    },
    "iss": {
        "label_pt": "ISS", "label_en": "ISS Tax",
        "definition_pt": "Imposto sobre Serviços. Tributo municipal sobre prestação de serviços.",
        "cpc_reference": None,
        "used_by_reports": ["metrics"],
        "examples_pt": ["(-) ISS sobre Serviços"],
    },
    "ipi": {
        "label_pt": "IPI", "label_en": "IPI Tax",
        "definition_pt": "Imposto sobre Produtos Industrializados.",
        "cpc_reference": None,
        "used_by_reports": ["metrics"],
        "examples_pt": ["(-) IPI sobre Vendas"],
    },
    "inss": {
        "label_pt": "INSS", "label_en": "Social Security Tax",
        "definition_pt": "Contribuição previdenciária. Encargo sobre folha.",
        "cpc_reference": None,
        "used_by_reports": ["metrics"],
        "examples_pt": ["INSS a Recolher", "INSS sobre Folha"],
    },
    "fgts": {
        "label_pt": "FGTS", "label_en": "FGTS Severance Fund",
        "definition_pt": "Fundo de Garantia por Tempo de Serviço. Encargo sobre folha.",
        "cpc_reference": None,
        "used_by_reports": ["metrics"],
        "examples_pt": ["FGTS a Recolher"],
    },
    "irrf": {
        "label_pt": "IRRF a Compensar",
        "label_en": "Withholding Tax Recoverable",
        "definition_pt": (
            "Imposto de Renda Retido na Fonte recuperável via compensação no "
            "IRPJ devido."
        ),
        "cpc_reference": None,
        "used_by_reports": ["bp"],
        "examples_pt": ["IRRF sobre Aplicações Financeiras"],
    },
    "foreign_currency": {
        "label_pt": "Moeda Estrangeira",
        "label_en": "Foreign Currency",
        "definition_pt": (
            "Conta denominada em moeda estrangeira. Aplicada para análise de "
            "exposição cambial e cálculo de variação."
        ),
        "cpc_reference": "CPC 02",
        "used_by_reports": ["metrics"],
        "examples_pt": [
            "Conta Bancária USD", "Empréstimo em USD", "Cliente Exportação",
        ],
    },
    "intercompany": {
        "label_pt": "Intercompany",
        "label_en": "Intercompany",
        "definition_pt": (
            "Saldo com partes relacionadas (controladas, coligadas, "
            "controladora). Eliminado em demonstrações consolidadas."
        ),
        "cpc_reference": "CPC 36 + CPC 05",
        "used_by_reports": ["bp", "dre"],
        "examples_pt": [
            "Mútuo com Controlada",
            "Receita de Serviços para Coligada",
        ],
    },
    "elimination": {
        "label_pt": "Eliminação Consolidação",
        "label_en": "Consolidation Elimination",
        "definition_pt": (
            "Conta usada APENAS para eliminação em consolidação. Não aparece "
            "em demonstrações individuais."
        ),
        "cpc_reference": "CPC 36",
        "used_by_reports": [],
        "examples_pt": ["Eliminação Receita Intercompany"],
    },
    "accrual": {
        "label_pt": "Provisão (Accrual)",
        "label_en": "Accrued Item",
        "definition_pt": (
            "Item provisionado pelo regime de competência, ainda não transitado "
            "pelo caixa."
        ),
        "cpc_reference": "CPC 26.27",
        "used_by_reports": [],
        "examples_pt": ["Provisão para Férias", "13º Salário a Pagar"],
    },
    "prepaid": {
        "label_pt": "Antecipado",
        "label_en": "Prepaid",
        "definition_pt": "Pagamento ou recebimento antecipado relativo a período futuro.",
        "cpc_reference": "CPC 25",
        "used_by_reports": [],
        "examples_pt": ["Seguros a Apropriar", "Receita Diferida"],
    },
    "product_sales": {
        "label_pt": "Venda de Produtos",
        "label_en": "Product Sales",
        "definition_pt": "Receita de vendas de produtos físicos. Para análise por linha de receita.",
        "cpc_reference": None,
        "used_by_reports": ["metrics"],
        "examples_pt": ["Receita Bruta de Vendas de Mercadorias"],
    },
    "service_revenue": {
        "label_pt": "Receita de Serviços",
        "label_en": "Service Revenue",
        "definition_pt": "Receita de prestação de serviços.",
        "cpc_reference": None,
        "used_by_reports": ["metrics"],
        "examples_pt": ["Receita de Consultoria"],
    },
    "subscription_revenue": {
        "label_pt": "Receita Recorrente / Assinatura",
        "label_en": "Subscription Revenue",
        "definition_pt": (
            "Receita recorrente de assinaturas (SaaS, mensalidades). Para "
            "métricas de MRR/ARR."
        ),
        "cpc_reference": "CPC 47",
        "used_by_reports": ["metrics"],
        "examples_pt": ["Receita de Assinatura SaaS"],
    },
    "export_revenue": {
        "label_pt": "Receita de Exportação",
        "label_en": "Export Revenue",
        "definition_pt": (
            "Receita oriunda de exportação. Análise de mix nacional vs "
            "exportação e exposição cambial."
        ),
        "cpc_reference": "CPC 02",
        "used_by_reports": ["metrics"],
        "examples_pt": ["Receita Bruta de Exportação"],
    },
    "jcp": {
        "label_pt": "Juros sobre Capital Próprio (JCP)",
        "label_en": "Interest on Equity (Brazilian)",
        "definition_pt": (
            "Forma brasileira de remunerar acionistas com vantagem tributária. "
            "Despesa dedutível para o IRPJ até a TJLP do PL. Tratada como "
            "destinação de lucro na DMPL."
        ),
        "cpc_reference": "Lei 9.249/95 art. 9º",
        "used_by_reports": ["dre", "dmpl", "dfc"],
        "examples_pt": ["JCP a Pagar", "Despesa de JCP"],
    },
    "dividends": {
        "label_pt": "Dividendos",
        "label_en": "Dividends",
        "definition_pt": "Distribuição de lucros aos acionistas/sócios.",
        "cpc_reference": "Lei 6.404/76 art. 202",
        "used_by_reports": ["dmpl", "dfc"],
        "examples_pt": ["Dividendos a Pagar", "Dividendos Pagos"],
    },
    "comprehensive_income": {
        "label_pt": "Outros Resultados Abrangentes (ORA)",
        "label_en": "Other Comprehensive Income",
        "definition_pt": (
            "Item de Outros Resultados Abrangentes que entra na DRA mas não na "
            "DRE: variação cambial de operações no exterior, ajustes atuariais, "
            "FVOCI."
        ),
        "cpc_reference": "CPC 26.81 + CPC 26.106",
        "used_by_reports": ["dra", "dmpl"],
        "examples_pt": [
            "Variação Cambial de Investimento no Exterior",
            "Ganho/Perda Atuarial", "Ajuste FVOCI",
        ],
    },
    "ifrs16_lease": {
        "label_pt": "Arrendamento IFRS 16",
        "label_en": "IFRS 16 Lease",
        "definition_pt": (
            "Conta relativa a arrendamento mercantil capitalizado conforme "
            "CPC 06 (R2) / IFRS 16. Aplicada ao ativo de direito de uso e ao "
            "passivo de arrendamento."
        ),
        "cpc_reference": "CPC 06 (R2)",
        "used_by_reports": ["bp", "metrics"],
        "examples_pt": [
            "Direito de Uso - Imóveis",
            "Passivo de Arrendamento - Imóveis",
        ],
    },
    "guaranteed": {
        "label_pt": "Garantia Concedida",
        "label_en": "Guarantee Provided",
        "definition_pt": (
            "Conta de compensação que registra avais e fianças concedidas. "
            "Não compõe ativo/passivo, apenas memo."
        ),
        "cpc_reference": "CPC 25 (divulgação)",
        "used_by_reports": [],
        "examples_pt": [
            "Avais Concedidos a Terceiros",
            "Fianças a Empresas Coligadas",
        ],
    },
}


# Sanity check at import time -- if the choices list and the meta dict
# diverge, fail fast at startup instead of mysteriously at request time.
_CATEGORY_CODES = REPORT_CATEGORY_VALUES
_CATEGORY_META_CODES = frozenset(REPORT_CATEGORY_META.keys())
assert _CATEGORY_CODES == _CATEGORY_META_CODES, (
    f"REPORT_CATEGORY_CHOICES and REPORT_CATEGORY_META disagree: "
    f"missing meta = {_CATEGORY_CODES - _CATEGORY_META_CODES}; "
    f"extra meta = {_CATEGORY_META_CODES - _CATEGORY_CODES}"
)

_TAG_CODES = TAG_VALUES
_TAG_META_CODES = frozenset(TAG_META.keys())
assert _TAG_CODES == _TAG_META_CODES, (
    f"TAG_CHOICES and TAG_META disagree: "
    f"missing meta = {_TAG_CODES - _TAG_META_CODES}; "
    f"extra meta = {_TAG_META_CODES - _TAG_CODES}"
)


# ---------------------------------------------------------------------
# cashflow_category — 15 values aligned to CPC 03 / IAS 7 (direct method)
# ---------------------------------------------------------------------
# Each value's prefix encodes the section (``fco_`` / ``fci_`` / ``fcf_``)
# so the FCO/FCI/FCF aggregation is a string-prefix lookup, no separate
# mapping table. Inheritance follows the same MPTT walk as
# ``report_category`` (nearest tagged ancestor wins; self overrides).
#
# The 15 sub-lines are the standard CPC 03 disclosures expanded one
# level beyond the bare three sections. Operators usually tag at L1
# (e.g. "Caixa Operacional → fco_outros") with an override at L2/L3
# for the specific sub-line. Cash and bank accounts themselves should
# stay UNTAGGED — they are the cash, not a flow.
#
# Why a separate field instead of deriving from ``report_category`` +
# ``tags`` (the previous approach):
#   * BS/PnL category and DFC sub-line are independent decisions —
#     "Aplicações Financeiras de Liquidez Imediata" is BS-side
#     ``ativo_circulante`` AND DFC-side ``fci_investimentos_financeiros``;
#     deriving one from the other forces a wrong default in either
#     report.
#   * Tags stop doing double-duty (they were doing both
#     "operational marker" AND "DFC routing" jobs); they go back to
#     pure cross-cutting markers.
#   * Operators can override per-account in the wiring modal without
#     a code change, exactly like ``report_category``.

CASHFLOW_CATEGORY_CHOICES = [
    # FCO — Atividades Operacionais
    ("fco_recebimentos_clientes", "FCO · Recebimentos de Clientes"),
    ("fco_pagamentos_fornecedores", "FCO · Pagamentos a Fornecedores"),
    ("fco_pagamentos_empregados", "FCO · Pagamentos a Empregados"),
    ("fco_impostos_indiretos", "FCO · Impostos Indiretos"),
    ("fco_imposto_renda", "FCO · IR/CSLL Pagos"),
    ("fco_juros", "FCO · Juros Pagos/Recebidos"),
    ("fco_outros", "FCO · Outros Recebimentos/Pagamentos"),
    # FCI — Atividades de Investimento
    ("fci_imobilizado", "FCI · Imobilizado"),
    ("fci_intangivel", "FCI · Intangível"),
    ("fci_investimentos_financeiros", "FCI · Investimentos Financeiros"),
    ("fci_outros", "FCI · Outros Investimentos"),
    # FCF — Atividades de Financiamento
    ("fcf_emprestimos", "FCF · Empréstimos e Financiamentos"),
    ("fcf_capital", "FCF · Aporte/Redução de Capital"),
    ("fcf_dividendos_jcp", "FCF · Dividendos e JCP"),
    ("fcf_outros", "FCF · Outros Financiamentos"),
]

CASHFLOW_CATEGORY_VALUES = frozenset(code for code, _ in CASHFLOW_CATEGORY_CHOICES)


class CashflowCategoryMeta(TypedDict):
    label_pt: str
    section: str  # "operacional" | "investimento" | "financiamento"
    definition_pt: str
    cpc_reference: str
    examples_pt: List[str]
    antiexamples_pt: List[str]


CASHFLOW_CATEGORY_META: Dict[str, CashflowCategoryMeta] = {
    "fco_recebimentos_clientes": {
        "label_pt": "FCO · Recebimentos de Clientes",
        "section": "operacional",
        "definition_pt": (
            "Entradas de caixa decorrentes de vendas de produtos e serviços, "
            "líquidas de impostos retidos e descontos comerciais."
        ),
        "cpc_reference": "CPC 03.14(a)",
        "examples_pt": [
            "Clientes a Receber", "Duplicatas a Receber", "Recebimentos por Cartão",
        ],
        "antiexamples_pt": [
            "Receita Bruta de Vendas (é DRE, não caixa)",
            "Adiantamentos de clientes recebidos (vão em fco_outros)",
        ],
    },
    "fco_pagamentos_fornecedores": {
        "label_pt": "FCO · Pagamentos a Fornecedores",
        "section": "operacional",
        "definition_pt": (
            "Saídas de caixa decorrentes da aquisição de matérias-primas, "
            "mercadorias para revenda, e serviços operacionais. Inclui fretes "
            "e estoques pagos."
        ),
        "cpc_reference": "CPC 03.14(c)",
        "examples_pt": [
            "Fornecedores a Pagar", "Matérias-Primas Pagas",
            "Frete sobre Compras", "Estoque de Mercadorias",
        ],
        "antiexamples_pt": [
            "Folha de pagamento (vai em fco_pagamentos_empregados)",
            "Imposto de renda (vai em fco_imposto_renda)",
        ],
    },
    "fco_pagamentos_empregados": {
        "label_pt": "FCO · Pagamentos a Empregados",
        "section": "operacional",
        "definition_pt": (
            "Saídas de caixa para folha de pagamento, encargos sociais "
            "(INSS, FGTS), benefícios e pró-labore."
        ),
        "cpc_reference": "CPC 03.14(d)",
        "examples_pt": [
            "Salários", "INSS a Recolher", "FGTS a Recolher",
            "Vale Refeição", "Plano de Saúde", "Pró-Labore",
        ],
        "antiexamples_pt": [
            "Comissões a representantes externos (vai em fco_pagamentos_fornecedores)",
        ],
    },
    "fco_impostos_indiretos": {
        "label_pt": "FCO · Impostos Indiretos",
        "section": "operacional",
        "definition_pt": (
            "Tributos sobre receitas e operações: ICMS, PIS, COFINS, ISS, IPI. "
            "Apresentados líquidos quando há recuperação de créditos."
        ),
        "cpc_reference": "CPC 03.14(e)",
        "examples_pt": [
            "ICMS a Recolher", "PIS/COFINS a Recolher", "ISS a Recolher",
            "IPI a Recolher", "DIFAL a Recolher",
        ],
        "antiexamples_pt": [
            "IRPJ/CSLL (vai em fco_imposto_renda)",
            "INSS empresa (vai em fco_pagamentos_empregados)",
        ],
    },
    "fco_imposto_renda": {
        "label_pt": "FCO · IR/CSLL Pagos",
        "section": "operacional",
        "definition_pt": (
            "Pagamentos de IRPJ e CSLL, incluindo antecipações e ajustes "
            "de balanço. Apresentados separadamente conforme CPC 03.35."
        ),
        "cpc_reference": "CPC 03.35",
        "examples_pt": [
            "IRPJ a Pagar", "CSLL a Pagar", "IRRF sobre Aplicações",
        ],
        "antiexamples_pt": [
            "ICMS / PIS / COFINS (vão em fco_impostos_indiretos)",
        ],
    },
    "fco_juros": {
        "label_pt": "FCO · Juros Pagos/Recebidos",
        "section": "operacional",
        "definition_pt": (
            "Juros pagos sobre empréstimos operacionais (capital de giro) "
            "e juros recebidos sobre aplicações de gestão de caixa. "
            "CPC 03 permite classificá-los em FCO ou FCF — adotamos FCO "
            "por consistência com a maioria das práticas brasileiras. "
            "Use a tag ``debt`` em uma sub-conta específica para mover "
            "juros de empréstimos de longo prazo para FCF."
        ),
        "cpc_reference": "CPC 03.31-32",
        "examples_pt": [
            "Juros Bancários", "Juros sobre Capital de Giro",
            "Rendimento de Aplicações", "Tarifas Bancárias",
        ],
        "antiexamples_pt": [
            "Variação cambial passiva (vai em fco_outros)",
            "Dividendos recebidos (vão em fci_investimentos_financeiros)",
        ],
    },
    "fco_outros": {
        "label_pt": "FCO · Outros Recebimentos/Pagamentos",
        "section": "operacional",
        "definition_pt": (
            "Saco de gato operacional — adiantamentos diversos, ressarcimentos, "
            "indenizações, e tudo que não cabe nas linhas mais específicas."
        ),
        "cpc_reference": "CPC 03.14",
        "examples_pt": [
            "Adiantamentos Diversos", "Ressarcimentos a Receber",
            "Indenizações", "Variações Cambiais Operacionais",
        ],
        "antiexamples_pt": [],
    },
    "fci_imobilizado": {
        "label_pt": "FCI · Imobilizado",
        "section": "investimento",
        "definition_pt": (
            "Aquisição e venda de bens do imobilizado: terrenos, edificações, "
            "máquinas, equipamentos, veículos, móveis. Inclui adições e baixas."
        ),
        "cpc_reference": "CPC 03.16(a)(b)",
        "examples_pt": [
            "Compra de Máquinas e Equipamentos", "Venda de Veículos",
            "Aquisição de Móveis e Utensílios",
        ],
        "antiexamples_pt": [
            "Software (vai em fci_intangivel)",
            "Depreciação acumulada (não-caixa, fica fora da DFC)",
        ],
    },
    "fci_intangivel": {
        "label_pt": "FCI · Intangível",
        "section": "investimento",
        "definition_pt": (
            "Aquisição e venda de ativos intangíveis: software, marcas, "
            "patentes, ágio, direitos de uso."
        ),
        "cpc_reference": "CPC 03.16",
        "examples_pt": [
            "Compra de Software", "Aquisição de Marcas e Patentes",
            "Licenças de Uso", "Ágio em Aquisições",
        ],
        "antiexamples_pt": [
            "Imobilizado físico (vai em fci_imobilizado)",
        ],
    },
    "fci_investimentos_financeiros": {
        "label_pt": "FCI · Investimentos Financeiros",
        "section": "investimento",
        "definition_pt": (
            "Aplicações financeiras de longo prazo, fundos de investimento, "
            "renda fixa não-equivalente-de-caixa, participações societárias. "
            "Aplicações de liquidez imediata (≤90 dias) podem ser tratadas "
            "como equivalentes de caixa via tag ``cash``; o resto entra aqui."
        ),
        "cpc_reference": "CPC 03.16(c)(d)",
        "examples_pt": [
            "CDB > 90 dias", "Fundos de Investimento",
            "Tesouro Direto", "Saldo do Principal Aplicado",
            "Investimentos em Coligadas", "Participações Societárias",
        ],
        "antiexamples_pt": [
            "CDB liquidez diária (tag cash, fica fora da DFC)",
        ],
    },
    "fci_outros": {
        "label_pt": "FCI · Outros Investimentos",
        "section": "investimento",
        "definition_pt": (
            "Saco de gato de investimento: depósitos judiciais, fundo "
            "de garantia, antecipações de aquisição."
        ),
        "cpc_reference": "CPC 03.16",
        "examples_pt": [
            "Depósitos Judiciais", "Antecipações para Aquisições",
        ],
        "antiexamples_pt": [],
    },
    "fcf_emprestimos": {
        "label_pt": "FCF · Empréstimos e Financiamentos",
        "section": "financiamento",
        "definition_pt": (
            "Captação e amortização de empréstimos, financiamentos, "
            "debêntures e demais dívidas onerosas. Juros sobre dívidas "
            "ficam em fco_juros (ou fcf_emprestimos se a empresa adotar "
            "IFRS Option B com tag ``debt`` específica)."
        ),
        "cpc_reference": "CPC 03.17(a)(b)(c)",
        "examples_pt": [
            "Empréstimos Bancários a Pagar", "Debêntures",
            "Financiamento BNDES", "Operações de Hedge",
        ],
        "antiexamples_pt": [
            "Fornecedores a pagar (vai em fco_pagamentos_fornecedores)",
        ],
    },
    "fcf_capital": {
        "label_pt": "FCF · Aporte/Redução de Capital",
        "section": "financiamento",
        "definition_pt": (
            "Movimentações de capital social — integralizações de "
            "acionistas, reduções de capital, recompra de ações em tesouraria."
        ),
        "cpc_reference": "CPC 03.17(a)",
        "examples_pt": [
            "Capital Social Subscrito", "Aporte de Capital",
            "Ações em Tesouraria", "Redução de Capital",
        ],
        "antiexamples_pt": [
            "Reservas de lucro (não geram movimento de caixa)",
        ],
    },
    "fcf_dividendos_jcp": {
        "label_pt": "FCF · Dividendos e JCP",
        "section": "financiamento",
        "definition_pt": (
            "Distribuição de dividendos e juros sobre capital próprio (JCP) "
            "aos acionistas/sócios."
        ),
        "cpc_reference": "CPC 03.17(d), 31",
        "examples_pt": [
            "Dividendos a Pagar", "JCP a Pagar",
            "Distribuição de Lucros",
        ],
        "antiexamples_pt": [],
    },
    "fcf_outros": {
        "label_pt": "FCF · Outros Financiamentos",
        "section": "financiamento",
        "definition_pt": (
            "Saco de gato de financiamento: arrendamento mercantil "
            "(IFRS 16), e demais movimentos de financiamento atípicos."
        ),
        "cpc_reference": "CPC 03.17",
        "examples_pt": [
            "Arrendamento Mercantil (IFRS 16)",
        ],
        "antiexamples_pt": [],
    },
}


_CF_CODES = CASHFLOW_CATEGORY_VALUES
_CF_META_CODES = frozenset(CASHFLOW_CATEGORY_META.keys())
assert _CF_CODES == _CF_META_CODES, (
    f"CASHFLOW_CATEGORY_CHOICES and CASHFLOW_CATEGORY_META disagree: "
    f"missing meta = {_CF_CODES - _CF_META_CODES}; "
    f"extra meta = {_CF_META_CODES - _CF_CODES}"
)


def cashflow_section_for_category(code: Optional[str]) -> Optional[str]:
    """Resolve the FCO/FCI/FCF section from a ``cashflow_category`` code.
    The section is encoded in the prefix (``fco_`` / ``fci_`` / ``fcf_``)
    so this is a constant-time lookup with no extra mapping table."""
    if not code:
        return None
    prefix = code.split("_", 1)[0]
    return {
        "fco": "operacional",
        "fci": "investimento",
        "fcf": "financiamento",
    }.get(prefix)
