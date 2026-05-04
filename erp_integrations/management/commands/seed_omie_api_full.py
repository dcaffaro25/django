"""Seed read-style Omie APIs into ``ERPAPIDefinition``.

Catalog comes from the official service list at
https://developer.omie.com.br/service-list/. Each entry was probed
against the live Omie API (using evolat's credentials) to verify that
the chosen call name is actually a registered method.

* Verified entries → ``is_active=True`` and ready for the agent.
* Unverified entries → ``is_active=False``, registered for visibility
  but excluded from agent listings until someone confirms the real
  call name from Omie's per-endpoint docs.

Idempotent. Re-running with ``--update`` refreshes URL / description /
param_schema / is_active for already-seeded rows.

Usage::

    python manage.py seed_omie_api_full
    python manage.py seed_omie_api_full --update
    python manage.py seed_omie_api_full --probe --probe-company 5
"""

from django.core.management.base import BaseCommand

from erp_integrations.models import ERPAPIDefinition, ERPProvider


# ---------------------------------------------------------------------------
# Common parameter blocks
# ---------------------------------------------------------------------------
PAGINATION_PARAMS = [
    {"name": "pagina", "type": "integer",
     "description": "Número da página que será listada.",
     "required": False, "default": 1},
    {"name": "registros_por_pagina", "type": "integer",
     "description": "Número de registros retornados por página.",
     "required": False, "default": 50},
]

# Some Omie endpoints use a different naming convention for pagination
# (CamelCase ``nPagina`` / ``nRegPorPagina``) instead of the snake_case
# variant used by the financial Listar* family. Probed live and
# confirmed for: ListarMovimentos, ListarBandeiras, ListarCaracteristicas,
# ListarEtapasPedido, ListarTiposCC.
N_PAGINATION_PARAMS = [
    {"name": "nPagina", "type": "integer",
     "description": "Número da página (CamelCase variant).",
     "required": False, "default": 1},
    {"name": "nRegPorPagina", "type": "integer",
     "description": "Registros por página (CamelCase variant).",
     "required": False, "default": 50},
]

# Only the financial Listar* family accepts ``apenas_importado_api`` —
# kept as an opt-in block for those entries.
APENAS_IMPORTADO_PARAM = [
    {"name": "apenas_importado_api", "type": "string",
     "description": "Exibir apenas registros gerados pela API (S/N).",
     "required": False, "default": "N"},
]

DATE_RANGE_PARAMS = [
    {"name": "filtrar_por_data_de", "type": "string",
     "description": "Data inicial (dd/mm/aaaa).", "required": False},
    {"name": "filtrar_por_data_ate", "type": "string",
     "description": "Data final (dd/mm/aaaa).", "required": False},
]


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
# Each entry: (call, url, description, list_key, extra_params, verified).
# - ``verified=True``: probed live and accepted by Omie.
# - ``verified=False``: from the service-list page but call name wasn't
#   confirmed in our probes; seeded as is_active=False until verified.
OMIE_BASE = "https://app.omie.com.br/api/v1"

# fmt: off
CATALOG: list[tuple[str, str, str, str, list, bool]] = [
    # ----- Geral / Cadastros Auxiliares (verified live) ----------------------
    ("ListarEmpresas",             f"{OMIE_BASE}/geral/empresas/",
     "Listar empresas (multi-empresa).", "empresas_cadastro", [], True),
    ("ListarDepartamentos",        f"{OMIE_BASE}/geral/departamentos/",
     "Listar departamentos.", "departamentos", [], True),
    ("ListarCategorias",           f"{OMIE_BASE}/geral/categorias/",
     "Listar categorias do plano de contas Omie.", "categoria_cadastro", [], True),
    ("ListarParcelas",             f"{OMIE_BASE}/geral/parcelas/",
     "Listar parcelamentos cadastrados.", "parcelaCadastro", [], True),
    ("PesquisarCidades",           f"{OMIE_BASE}/geral/cidades/",
     "Pesquisar cidades cadastradas.", "ListarCidadesResposta", [], True),
    ("ListarPaises",               f"{OMIE_BASE}/geral/paises/",
     "Listar países cadastrados. Bespoke param schema (paisListarRequest); "
     "needs verification of the right field names.",
     "paises", [], False),
    ("ListarBancos",               f"{OMIE_BASE}/geral/bancos/",
     "Listar bancos (registry).", "bancos_cadastro", [], True),
    ("ListarTiposCC",              f"{OMIE_BASE}/geral/tipocc/",
     "Listar tipos de conta corrente.", "tipocc_cadastro", [], True),
    ("ListarBandeiras",            f"{OMIE_BASE}/geral/bandeiracartao/",
     "Listar bandeiras de cartão. Uses nPagina/nRegPorPagina.",
     "lista_bandeiras", [], True),
    ("ListarCaracteristicas",      f"{OMIE_BASE}/geral/caracteristicas/",
     "Listar características de produto. Uses nPagina/nRegPorPagina.",
     "caracteristica_cadastro", [], True),
    ("ListarEtapasPedido",         f"{OMIE_BASE}/produtos/pedidoetapas/",
     "Listar etapas de pedido. Uses nPagina/nRegPorPagina.",
     "etapas_pedido", [], True),
    ("PesquisarFamilias",          f"{OMIE_BASE}/geral/familias/",
     "Pesquisar famílias de produtos.", "familias_produto_cadastro", [], True),
    ("ListarUnidades",             f"{OMIE_BASE}/geral/unidade/",
     "Listar unidades de medida. Bespoke param schema (unidade_pesquisa); "
     "needs verification.",
     "unidades_cadastro", [], False),
    ("ListarVendedores",           f"{OMIE_BASE}/geral/vendedores/",
     "Listar vendedores cadastrados.", "cadastro", [], True),

    # ----- Geral / unverified ------------------------------------------------
    ("ListarTiposAtividade",       f"{OMIE_BASE}/geral/tpativ/",
     "Listar tipos de atividade. (call name not yet verified)",
     "lista_tipo_atividade", [], False),
    ("ConsultarTipoAnexo",         f"{OMIE_BASE}/geral/tiposanexo/",
     "Listar tipos de anexos. (call name not yet verified)",
     "tipos_anexo", [], False),
    ("ListarTiposDoc",             f"{OMIE_BASE}/geral/tiposdoc/",
     "Listar tipos de documento. (call name not yet verified)",
     "cadastros", [], False),
    ("ListarDREs",                 f"{OMIE_BASE}/geral/dre/",
     "Listar contas DRE. (call name not yet verified)",
     "dre_cadastro", [], False),
    ("ListarFinTransf",            f"{OMIE_BASE}/geral/finaltransf/",
     "Listar finalidades de transferência. (call name not yet verified)",
     "lista_finalidades", [], False),
    ("ListarOrigens",              f"{OMIE_BASE}/geral/origemlancamento/",
     "Listar origens de lançamento. (call name not yet verified)",
     "origem_cadastro", [], False),
    ("ListarCenarios",             f"{OMIE_BASE}/geral/cenarios/",
     "Listar cenários de impostos. (call name not yet verified)",
     "lista_cenarios", [], False),
    ("ListarMeiosPagamento",       f"{OMIE_BASE}/geral/meiospagamento/",
     "Listar meios de pagamento. (call name not yet verified)",
     "meiospagamento", [], False),
    ("ListarOrigensPedido",        f"{OMIE_BASE}/geral/origempedido/",
     "Listar origens de pedido. (call name not yet verified)",
     "origens_pedido", [], False),
    ("ListarMotivosDevolucao",     f"{OMIE_BASE}/geral/motivodevolucao/",
     "Listar motivos de devolução. (call name not yet verified)",
     "motivos_devolucao", [], False),

    # ----- CRM (verified live) ----------------------------------------------
    ("ListarSolucoes",             f"{OMIE_BASE}/crm/solucoes/",
     "Listar soluções (catálogo CRM).", "solucoesEncontradas", [], True),
    ("ListarFases",                f"{OMIE_BASE}/crm/fases/",
     "Listar fases de oportunidade.", "fasesEncontradas", [], True),
    ("ListarUsuarios",             f"{OMIE_BASE}/crm/usuarios/",
     "Listar usuários CRM.", "usuariosEncontrados", [], True),
    ("ListarStatus",               f"{OMIE_BASE}/crm/status/",
     "Listar status CRM.", "statusEncontrados", [], True),
    ("ListarMotivos",              f"{OMIE_BASE}/crm/motivos/",
     "Listar motivos CRM.", "motivosEncontrados", [], True),
    ("ListarTipos",                f"{OMIE_BASE}/crm/tipos/",
     "Listar tipos CRM.", "tiposEncontrados", [], True),
    ("ListarParceiros",            f"{OMIE_BASE}/crm/parceiros/",
     "Listar parceiros CRM.", "parceirosEncontrados", [], True),
    ("ListarVerticais",            f"{OMIE_BASE}/crm/verticais/",
     "Listar verticais CRM.", "verticaisEncontradas", [], True),
    ("ListarFinders",              f"{OMIE_BASE}/crm/finders/",
     "Listar finders CRM.", "findersEncontrados", [], True),
    ("ListarConcorrentes",         f"{OMIE_BASE}/crm/concorrentes/",
     "Listar concorrentes CRM.", "concorrentesEncontrados", [], True),
    ("ListarOrigensCrm",           f"{OMIE_BASE}/crm/origens/",
     "Listar origens CRM. Probe says 'method not exists' — call name "
     "(or endpoint URL) needs verification.",
     "origensEncontradas", [], False),

    # ----- CRM resumo (unverified) ------------------------------------------
    ("ResumirOportunidades",       f"{OMIE_BASE}/crm/oportunidades-resumo/",
     "Resumo de oportunidades CRM. (call name not yet verified)",
     "", DATE_RANGE_PARAMS, False),
    ("ResumirTarefas",             f"{OMIE_BASE}/crm/tarefas-resumo/",
     "Resumo de tarefas CRM. (call name not yet verified)",
     "", DATE_RANGE_PARAMS, False),

    # ----- Finanças (verified) ----------------------------------------------
    ("ListarContasPagar",          f"{OMIE_BASE}/financas/contapagar/",
     "Listar contas a pagar.", "conta_pagar_cadastro",
     APENAS_IMPORTADO_PARAM + DATE_RANGE_PARAMS, True),
    ("ListarContasReceber",        f"{OMIE_BASE}/financas/contareceber/",
     "Listar contas a receber.", "conta_receber_cadastro",
     APENAS_IMPORTADO_PARAM + DATE_RANGE_PARAMS, True),
    ("ListarMovimentos",           f"{OMIE_BASE}/financas/mf/",
     "Listar movimentos financeiros (extrato consolidado).",
     "movimentos", DATE_RANGE_PARAMS, True),

    # ----- Finanças (unverified) --------------------------------------------
    ("ListarExtrato",              f"{OMIE_BASE}/financas/extrato/",
     "Listar extrato financeiro consolidado. (call name not yet verified)",
     "ListarExtratoResponse", DATE_RANGE_PARAMS, False),
    ("ListarOrcamento",            f"{OMIE_BASE}/financas/caixa/",
     "Listar orçamento de caixa. (call name not yet verified)",
     "orcamentos", DATE_RANGE_PARAMS, False),
    ("PesquisarTitulos",           f"{OMIE_BASE}/financas/pesquisartitulos/",
     "Pesquisar títulos financeiros. (call name not yet verified)",
     "titulosEncontrados", DATE_RANGE_PARAMS, False),
    ("ResumirFinanceiro",          f"{OMIE_BASE}/financas/resumo/",
     "Resumo financeiro do período. (call name not yet verified)",
     "", DATE_RANGE_PARAMS, False),

    # ----- Vendas / Pedidos (verified) --------------------------------------
    ("ListarPedidos",              f"{OMIE_BASE}/produtos/pedido/",
     "Listar pedidos de venda.", "pedido_venda_produto", DATE_RANGE_PARAMS, True),

    # ----- Vendas / Pedidos (unverified) ------------------------------------
    ("ConsultarPedidoVenda",       f"{OMIE_BASE}/produtos/pedidovenda/",
     "Consultar pedidos de venda (visão resumida). "
     "(call name not yet verified — different endpoint than /produtos/pedido/)",
     "pedidos_venda", DATE_RANGE_PARAMS, False),
    ("ResumirVendas",              f"{OMIE_BASE}/produtos/vendas-resumo/",
     "Resumo de vendas. (call name not yet verified)",
     "", DATE_RANGE_PARAMS, False),
    ("ObterDocumentosFiscais",     f"{OMIE_BASE}/produtos/dfedocs/",
     "Obter documentos fiscais. (call name not yet verified)",
     "documentos", DATE_RANGE_PARAMS, False),
    ("ListarFormasPagVendas",      f"{OMIE_BASE}/produtos/formaspagvendas/",
     "Listar formas de pagamento (vendas). (call name not yet verified)",
     "lista_formas_pag", [], False),
    ("ListarTabelaPrecos",         f"{OMIE_BASE}/produtos/tabelaprecos/",
     "Listar tabelas de preços. (call name not yet verified)",
     "tabelas", [], False),
    ("ListarEtapasFat",            f"{OMIE_BASE}/produtos/etapafat/",
     "Listar etapas de faturamento. (call name not yet verified)",
     "lista_etapas", [], False),

    # ----- NF-e (verified) --------------------------------------------------
    ("ConsultarNF",                f"{OMIE_BASE}/produtos/nfconsultar/",
     "Consultar uma NF-e por chave/id/pedido.", "", [
        {"name": "nIdNF", "type": "integer",
         "description": "Id Omie da NF.", "required": False},
        {"name": "nIdPedido", "type": "integer",
         "description": "Id do pedido vinculado.", "required": False},
        {"name": "cChaveNFe", "type": "string",
         "description": "Chave de 44 dígitos da NF-e.", "required": False},
     ], True),

    # ----- NF-e (unverified) ------------------------------------------------
    ("ObterUtilNotaFiscal",        f"{OMIE_BASE}/produtos/notafiscalutil/",
     "Obter utilitários NF-e. (call name not yet verified)",
     "", [], False),

    # ----- Cadastros (verified) ---------------------------------------------
    ("ListarClientes",             f"{OMIE_BASE}/geral/clientes/",
     "Listar clientes/fornecedores (parceiros).", "clientes_cadastro", [
        {"name": "clientesFiltro", "type": "object",
         "description": "Objeto de filtros aninhado.",
         "required": False, "default": {}},
     ], True),
    ("ConsultarCliente",           f"{OMIE_BASE}/geral/clientes/",
     "Consultar um cliente por código ou CNPJ/CPF.", "", [
        {"name": "codigo_cliente_omie", "type": "integer",
         "description": "Código do cliente no Omie.", "required": False},
        {"name": "cnpj_cpf", "type": "string",
         "description": "CPF/CNPJ (apenas números).", "required": False},
     ], True),
    ("ListarProdutos",             f"{OMIE_BASE}/geral/produtos/",
     "Listar produtos.", "produto_servico_cadastro", [], True),
    ("ConsultarProduto",           f"{OMIE_BASE}/geral/produtos/",
     "Consultar um produto por código.", "", [
        {"name": "codigo_produto", "type": "integer",
         "description": "Código do produto no Omie.", "required": False},
        {"name": "codigo_produto_integracao", "type": "string",
         "description": "Código de integração externo.", "required": False},
     ], True),

    # ----- Compras / Estoque (verified) -------------------------------------
    ("ListarProdutoFornecedor",    f"{OMIE_BASE}/estoque/produtofornecedor/",
     "Listar relação produto x fornecedor.", "ListarProdFornCadastro", [], True),

    # ----- Compras / Estoque (unverified) -----------------------------------
    ("ListarCompradores",          f"{OMIE_BASE}/estoque/comprador/",
     "Listar compradores. (no records in current tenant; call name needs verification)",
     "compradoresCadastro", [], False),
    ("ListarFormasPagCompras",     f"{OMIE_BASE}/produtos/formaspagcompras/",
     "Listar formas de pagamento (compras). (call name not yet verified)",
     "lista_formas_pag", [], False),
    ("ListarNCM",                  f"{OMIE_BASE}/produtos/ncm/",
     "Listar NCMs. (call name not yet verified)",
     "ListarNCMResponse", [], False),
    ("ListarEstoque",              f"{OMIE_BASE}/estoque/consulta/",
     "Consultar posição de estoque. (call name not yet verified)",
     "produtos", [], False),
    ("ListarMovEstoque",           f"{OMIE_BASE}/estoque/movestoque/",
     "Listar movimentos de estoque. (call name not yet verified)",
     "cadastros", DATE_RANGE_PARAMS, False),
    ("ListarLocaisEstoque",        f"{OMIE_BASE}/estoque/local/",
     "Listar locais de estoque. (call name not yet verified)",
     "ListarLocaisEstoqueCadastro", [], False),
    ("ResumirEstoque",             f"{OMIE_BASE}/estoque/resumo/",
     "Resumo do estoque. (call name not yet verified)",
     "", [], False),
    ("ResumirCompras",             f"{OMIE_BASE}/produtos/compras-resumo/",
     "Resumo de compras. (call name not yet verified)",
     "", DATE_RANGE_PARAMS, False),

    # ----- Impostos (unverified — likely need different schema) -------------
    ("ListarCFOP",                 f"{OMIE_BASE}/produtos/cfop/",
     "Listar códigos CFOP. (rejects pagination; needs schema refinement)",
     "cadastros", [], False),
    ("ListarCNAE",                 f"{OMIE_BASE}/produtos/cnae/",
     "Listar CNAEs. (rejects pagination; needs schema refinement)",
     "cadastros", [], False),
    ("ListarICMSCST",              f"{OMIE_BASE}/produtos/icmscst/",
     "Listar ICMS CST. (call name not yet verified)",
     "cadastros", [], False),
    ("ListarICMSCSOSN",            f"{OMIE_BASE}/produtos/icmscsosn/",
     "Listar ICMS CSOSN. (call name not yet verified)",
     "cadastros", [], False),
    ("ListarICMSOrigem",           f"{OMIE_BASE}/produtos/icmsorigem/",
     "Listar origens de mercadoria. (call name not yet verified)",
     "cadastros", [], False),
    ("ListarPISCST",               f"{OMIE_BASE}/produtos/piscst/",
     "Listar PIS CST. (call name not yet verified)",
     "cadastros", [], False),
    ("ListarCOFINSCST",            f"{OMIE_BASE}/produtos/cofinscst/",
     "Listar COFINS CST. (call name not yet verified)",
     "cadastros", [], False),
    ("ListarIPICST",               f"{OMIE_BASE}/produtos/ipicst/",
     "Listar IPI CST. (call name not yet verified)",
     "cadastros", [], False),
    ("ListarIPIEnq",               f"{OMIE_BASE}/produtos/ipienq/",
     "Listar enquadramentos IPI. (call name not yet verified)",
     "cadastros", [], False),
    ("ListarTpCalc",               f"{OMIE_BASE}/produtos/tpcalc/",
     "Listar tipos de cálculo. (rejects pagination)",
     "cadastros", [], False),
    ("ListarCEST",                 f"{OMIE_BASE}/produtos/cest/",
     "Listar CEST. (rejects pagination)",
     "cadastros", [], False),

    # ----- Serviços / NFS-e (verified) --------------------------------------
    ("ListarLC116",                f"{OMIE_BASE}/servicos/lc116/",
     "Listar LC 116 (lista de serviços).", "lista_lc116", [], True),
    ("ListarNBS",                  f"{OMIE_BASE}/servicos/nbs/",
     "Listar NBS (Nomenclatura Brasileira de Serviços).",
     "lista_nbs", [], True),
    ("ListarTiposTrib",            f"{OMIE_BASE}/servicos/tipotrib/",
     "Listar tipos de tributação.", "tipotrib_cadastro", [], True),

    # ----- Serviços / NFS-e (unverified) ------------------------------------
    ("ResumirServicos",            f"{OMIE_BASE}/servicos/resumo/",
     "Resumo de serviços. (call name not yet verified)",
     "", DATE_RANGE_PARAMS, False),
    ("ObterDocumentosOS",          f"{OMIE_BASE}/servicos/osdocs/",
     "Obter documentos OS. (call name not yet verified)",
     "documentos", DATE_RANGE_PARAMS, False),
    ("ConsultarNfse",              f"{OMIE_BASE}/servicos/nfse/",
     "Consultar NFS-e. (call name not yet verified)",
     "", [], False),
    ("ListarServicoMunicipio",     f"{OMIE_BASE}/servicos/listaservico/",
     "Listar serviços do município. (call name not yet verified)",
     "lista_servicos", [], False),
    ("ListarLC116",                f"{OMIE_BASE}/servicos/lc116/",
     "(duplicated above — kept verified)", "lista_lc116", [], True),
    ("ListarNBS",                  f"{OMIE_BASE}/servicos/nbs/",
     "(duplicated above — kept verified)", "lista_nbs", [], True),
    ("ListarIBPT",                 f"{OMIE_BASE}/servicos/ibpt/",
     "Listar IBPT. (call name not yet verified)",
     "lista_ibpt", [], False),
    ("ListarTipoFat",              f"{OMIE_BASE}/servicos/contratotpfat/",
     "Listar tipos de faturamento. (call name not yet verified)",
     "tipofat_cadastro", [], False),
    ("ListarTipoUtil",             f"{OMIE_BASE}/servicos/tipoutilizacao/",
     "Listar tipos de utilização. (call name not yet verified)",
     "tipoutilizacao_cadastro", [], False),
    ("ListarClassifServ",          f"{OMIE_BASE}/servicos/classificacaoservico/",
     "Listar classificações de serviço. (call name not yet verified)",
     "classifserv_cadastro", [], False),

    # ----- Painel do Contador (unverified) ----------------------------------
    ("ListarDocumentos",           f"{OMIE_BASE}/contador/xml/",
     "Listar XMLs do painel do contador. (call name not yet verified)",
     "ListarDocumentosResponse", DATE_RANGE_PARAMS, False),
    ("ResumirContabil",            f"{OMIE_BASE}/contador/resumo/",
     "Resumo contábil. (call name not yet verified)",
     "", DATE_RANGE_PARAMS, False),
]
# fmt: on


# Calls that use the CamelCase pagination convention instead of the
# default snake_case one. Discovered by live probing.
_N_PAGINATION_CALLS = {
    "ListarMovimentos",
    "ListarBandeiras",
    "ListarCaracteristicas",
    "ListarEtapasPedido",
}


def _build_param_schema(call: str, extra: list) -> list:
    by_name: dict[str, dict] = {}
    pagination = N_PAGINATION_PARAMS if call in _N_PAGINATION_CALLS else PAGINATION_PARAMS
    for p in pagination:
        by_name[p["name"]] = dict(p)
    for p in extra or []:
        by_name[p["name"]] = dict(p)
    return list(by_name.values())


def _transform_config_for(list_key: str) -> dict:
    if not list_key:
        return {
            "records": {
                "path": "",
                "autoDiscover": True,
                "rootAsOneRow": True,
            },
        }
    return {
        "records": {
            "path": list_key,
            "fallbackPaths": [f"data.{list_key}"],
            "autoDiscover": True,
            "rootAsOneRow": False,
        },
    }


class Command(BaseCommand):
    help = "Seed the read-only Omie API catalog into ERPAPIDefinition."

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true",
            help="Refresh url/description/param_schema/transform_config/is_active for existing rows.")
        parser.add_argument("--probe", action="store_true",
            help="After seeding, call each ACTIVE endpoint to verify it works.")
        parser.add_argument("--probe-company", type=int, default=5,
            help="Company id whose ERPConnection credentials to use when probing.")

    def handle(self, *args, **options):
        provider, created = ERPProvider.objects.get_or_create(
            slug="omie",
            defaults={"name": "Omie", "base_url": OMIE_BASE, "is_active": True},
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created ERPProvider: Omie"))

        # Dedupe: if the same call appears twice in CATALOG (we do this
        # in a few places where the verified entry was added later), the
        # last one wins.
        seen: dict[str, tuple] = {}
        for entry in CATALOG:
            seen[entry[0]] = entry

        n_created = 0
        n_updated = 0
        n_unchanged = 0

        for call, url, description, list_key, extra, verified in seen.values():
            param_schema = _build_param_schema(call, extra)
            transform_config = _transform_config_for(list_key)
            defaults = {
                "url": url, "method": "POST", "description": description,
                "param_schema": param_schema,
                "transform_config": transform_config,
                "is_active": verified,
            }
            obj, was_created = ERPAPIDefinition.objects.get_or_create(
                provider=provider, call=call, defaults=defaults,
            )
            if was_created:
                n_created += 1
                marker = "+" if verified else "?"
                self.stdout.write(self.style.SUCCESS(f"  {marker} {call}"))
                continue

            if options["update"]:
                changed = False
                for field, value in defaults.items():
                    if getattr(obj, field) != value:
                        setattr(obj, field, value)
                        changed = True
                if changed:
                    obj.save()
                    n_updated += 1
                    self.stdout.write(f"  ~ {call}")
                else:
                    n_unchanged += 1
            else:
                n_unchanged += 1

        # Deactivate any stale rows for this provider that aren't in
        # the current catalog (left over from earlier seeds with
        # different / wrong call names).
        catalog_calls = set(seen.keys())
        stale = ERPAPIDefinition.objects.filter(
            provider=provider, is_active=True,
        ).exclude(call__in=catalog_calls)
        n_stale = stale.count()
        if n_stale and options["update"]:
            for row in stale:
                row.is_active = False
                row.description = (row.description or "") + " [DEACTIVATED: not in current catalog]"
                row.save(update_fields=["is_active", "description", "updated_at"])
                self.stdout.write(f"  - {row.call}  (deactivated, not in catalog)")

        self.stdout.write("")
        n_active = sum(1 for e in seen.values() if e[5])
        n_inactive = len(seen) - n_active
        self.stdout.write(self.style.SUCCESS(
            f"Seed: created={n_created} updated={n_updated} "
            f"unchanged={n_unchanged} stale_deactivated={n_stale if options['update'] else 0} | "
            f"active={n_active} inactive={n_inactive} "
            f"total_in_catalog={len(seen)}"
        ))

        if options.get("probe"):
            self._probe(provider, options["probe_company"])

    def _probe(self, provider: ERPProvider, company_id: int):
        from erp_integrations.models import ERPConnection
        from mcp_server.tools import call_erp_api

        conn = ERPConnection.objects.filter(
            company_id=company_id, provider=provider, is_active=True,
        ).first()
        if not conn:
            self.stdout.write(self.style.ERROR(
                f"No active ERPConnection for company_id={company_id}; cannot probe."
            ))
            return

        self.stdout.write("")
        self.stdout.write("Probing ACTIVE endpoints (this hits Omie live)...")
        self.stdout.write("=" * 70)

        active = ERPAPIDefinition.objects.filter(
            provider=provider, is_active=True,
        ).order_by("call")

        n_ok = 0
        n_fail = 0
        failures: list[tuple[str, str]] = []

        for api in active:
            try:
                # Skip Consultar* — they need specific IDs to work
                # meaningfully and "method exists" is implied by the
                # Listar variant on the same URL.
                if api.call.startswith("Consultar"):
                    self.stdout.write(f"  [..] {api.call:36s} (skipped — needs id args)")
                    continue
                # Use empty params: build_payload then injects the
                # schema defaults (pagina=1 OR nPagina=1 depending on
                # the endpoint's convention). Hardcoding ``pagina`` here
                # would clash with endpoints that use ``nPagina``.
                result = call_erp_api(
                    company_id=company_id, call=api.call, params={},
                )
            except Exception as exc:
                failures.append((api.call, f"{type(exc).__name__}: {exc}"))
                n_fail += 1
                self.stdout.write(self.style.ERROR(f"  [EX] {api.call:36s} {exc}"))
                continue

            err = ""
            resp = result.get("response") or {}
            if isinstance(resp, dict):
                err = (
                    resp.get("faultstring") or resp.get("message")
                    or resp.get("faultcode") or resp.get("error") or ""
                )
            if not err and not result.get("ok"):
                err = result.get("error") or "(no detail)"
            err_lower = str(err).lower()

            # Empty-tenant signal — Omie returns these when the method works
            # but the company has no rows yet. Should count as a passing
            # probe (call name is valid).
            empty_ok = (
                "não existem registros" in err_lower
                or "nenhum registro" in err_lower
            )

            if result.get("ok") or empty_ok:
                n_ok += 1
                tag = "(empty)" if empty_ok and not result.get("ok") else ""
                self.stdout.write(self.style.SUCCESS(
                    f"  [OK] {api.call:36s} {api.url} {tag}"
                ))
            else:
                err = str(err)[:80]
                failures.append((api.call, err))
                n_fail += 1
                self.stdout.write(self.style.WARNING(f"  [NO] {api.call:36s} {err}"))

        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS(
            f"Probe done: ok={n_ok} fail={n_fail} active={active.count()}"
        ))
        if failures:
            self.stdout.write("")
            self.stdout.write("Failures (call -> error):")
            for call, err in failures:
                self.stdout.write(f"  {call:36s} -> {err}")
