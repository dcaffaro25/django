"""One-off probe: discover the real Omie call name per endpoint.

For each (endpoint_url, [candidates]) pair, try each candidate against
the live Omie API and print the first one that doesn't return
"Method X not exists". A 200 OK or a structural-error 500 (e.g. "Tag
[PAGINA] não faz parte da estrutura...") both confirm the call exists
— we just need to refine its param schema.
"""
import requests

import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nord_backend.settings")
django.setup()

from erp_integrations.models import ERPConnection

conn = ERPConnection.objects.filter(company_id=5, provider__slug="omie").first()
assert conn, "No Omie connection for company 5"


def try_call(url, call, params=None):
    payload = {
        "call": call,
        "param": [params or {}],
        "app_key": conn.app_key,
        "app_secret": conn.app_secret,
    }
    r = requests.post(url, json=payload, timeout=15)
    body = {}
    try:
        body = r.json()
    except Exception:
        pass
    msg = body.get("message") or body.get("faultstring") or ""
    miss = "not exists" in msg
    return r.status_code, miss, msg


TESTS = [
    ("https://app.omie.com.br/api/v1/geral/tpativ/",
     ["LtsTiposAtv", "PesquisarTipoAtividade", "ListarTpAtividade",
      "PesquisarAtividade", "ListarAtividade"]),
    ("https://app.omie.com.br/api/v1/geral/tiposanexo/",
     ["ListarAnexo", "ConsultarAnexo", "PesquisarAnexo", "ListarTipoAnexos"]),
    ("https://app.omie.com.br/api/v1/geral/tiposdoc/",
     ["ListarTiposDocumentoFiscal", "ListarTpDoc", "PesquisarTpDoc",
      "ListarDoc", "PesquisarTipoDoc"]),
    ("https://app.omie.com.br/api/v1/geral/dre/",
     ["LtsContasDre", "ListarDre", "PesquisarDre", "ListarContaDre"]),
    ("https://app.omie.com.br/api/v1/geral/finaltransf/",
     ["LtsFinTransf", "ListarFinalidades", "PesquisarFinalTransf"]),
    ("https://app.omie.com.br/api/v1/geral/origemlancamento/",
     ["ListarOrigemLanc", "PesquisarOrigemLancamento", "LtsOrigemLanc"]),
    ("https://app.omie.com.br/api/v1/geral/familias/",
     ["LtsFamilias", "PesquisarFamilia", "PesquisarFamilias"]),
    ("https://app.omie.com.br/api/v1/geral/origempedido/",
     ["PesquisarOrigemPedido", "LtsOrigemPedido"]),
    ("https://app.omie.com.br/api/v1/geral/motivodevolucao/",
     ["PesquisarMotivoDevolucao", "LtsMotivoDevolucao"]),
    # Resumir* candidates
    ("https://app.omie.com.br/api/v1/crm/oportunidades-resumo/",
     ["ConsultarResumoOportunidades", "ListarResumoOportunidades",
      "ResumoOportunidades", "GetResumoOportunidades"]),
    ("https://app.omie.com.br/api/v1/crm/tarefas-resumo/",
     ["ConsultarResumoTarefas", "ListarResumoTarefas"]),
    ("https://app.omie.com.br/api/v1/financas/resumo/",
     ["ConsultarResumoFinanceiro", "ListarResumoFinanceiro",
      "GetResumoFinanceiro", "ResumoFinanceiro"]),
    ("https://app.omie.com.br/api/v1/produtos/vendas-resumo/",
     ["ConsultarResumoVendas", "ListarResumoVendas"]),
    ("https://app.omie.com.br/api/v1/produtos/compras-resumo/",
     ["ConsultarResumoCompras", "ListarResumoCompras"]),
    ("https://app.omie.com.br/api/v1/estoque/resumo/",
     ["ConsultarResumoEstoque", "ListarResumoEstoque"]),
    ("https://app.omie.com.br/api/v1/servicos/resumo/",
     ["ConsultarResumoServicos", "ListarResumoServicos"]),
    ("https://app.omie.com.br/api/v1/contador/resumo/",
     ["ConsultarResumoContabil", "ListarResumoContabil",
      "ResumoMovContabil"]),
    # Other failures
    ("https://app.omie.com.br/api/v1/produtos/dfedocs/",
     ["ObterDFE", "ListarDFE", "ConsultarDFE", "ListarDocsFiscais"]),
    ("https://app.omie.com.br/api/v1/servicos/osdocs/",
     ["ObterDocOS", "ListarDocOS", "ListarDocumentosOS"]),
    ("https://app.omie.com.br/api/v1/produtos/notafiscalutil/",
     ["ObterUtilNotaFiscal", "UtilNotaFiscal", "ListarUtilNotaFiscal"]),
    ("https://app.omie.com.br/api/v1/produtos/pedidovenda/",
     ["ConsultarPedidoVenda", "ListarPedidoVenda", "ListarPedidos",
      "PesquisarPedidoVenda"]),
    ("https://app.omie.com.br/api/v1/produtos/pedidoetapas/",
     ["ListarEtapasPedido", "ListarEtapas", "PesquisarEtapasPedido"]),
    ("https://app.omie.com.br/api/v1/produtos/etapafat/",
     ["ListarEtapaFat", "ListarEtapasFat", "PesquisarEtapaFat"]),
    ("https://app.omie.com.br/api/v1/servicos/nfse/",
     ["ListarNFSe", "ListarNfse", "ConsultarNFSe", "PesquisarNFSe"]),
    ("https://app.omie.com.br/api/v1/servicos/listaservico/",
     ["ListarServicosMunicipio", "PesquisarServicoMunicipio",
      "ListarItensServ"]),
    ("https://app.omie.com.br/api/v1/servicos/tipotrib/",
     ["ListarTipoTrib", "ListarTiposTrib", "PesquisarTipoTrib"]),
    ("https://app.omie.com.br/api/v1/servicos/ibpt/",
     ["ListarIBPT", "PesquisarIBPT", "ConsultarIBPT"]),
    ("https://app.omie.com.br/api/v1/servicos/contratotpfat/",
     ["ListarTipoFat", "ListarTiposFat", "PesquisarTipoFat"]),
    ("https://app.omie.com.br/api/v1/servicos/tipoutilizacao/",
     ["ListarTipoUtil", "ListarTiposUtil", "PesquisarTipoUtil"]),
    ("https://app.omie.com.br/api/v1/servicos/classificacaoservico/",
     ["ListarClassifServ", "PesquisarClassifServ"]),
    ("https://app.omie.com.br/api/v1/produtos/tabelaprecos/",
     ["ListarTabelaPrecos", "ListarTabelasPrecos", "PesquisarTabelaPrecos"]),
    ("https://app.omie.com.br/api/v1/financas/caixa/",
     ["ListarOrcamento", "ListarCaixa", "PesquisarCaixa"]),
    ("https://app.omie.com.br/api/v1/financas/pesquisartitulos/",
     ["PesquisarTitulos", "ListarTitulos"]),
    ("https://app.omie.com.br/api/v1/produtos/icmscst/",
     ["ListarICMSCST", "ListarIcmsCst", "PesquisarIcmsCst"]),
    ("https://app.omie.com.br/api/v1/produtos/icmscsosn/",
     ["ListarICMSCSOSN", "ListarIcmsCsosn"]),
    ("https://app.omie.com.br/api/v1/produtos/icmsorigem/",
     ["ListarICMSOrigem", "ListarIcmsOrigem"]),
    ("https://app.omie.com.br/api/v1/produtos/piscst/",
     ["ListarPISCST", "ListarPisCst"]),
    ("https://app.omie.com.br/api/v1/produtos/cofinscst/",
     ["ListarCOFINSCST", "ListarCofinsCst"]),
    ("https://app.omie.com.br/api/v1/produtos/ipicst/",
     ["ListarIPICST", "ListarIpiCst"]),
    ("https://app.omie.com.br/api/v1/produtos/ipienq/",
     ["ListarIPIEnq", "ListarIpiEnq"]),
    ("https://app.omie.com.br/api/v1/estoque/consulta/",
     ["ListarPosEstoque", "ConsultarEstoque", "ListarEstoque"]),
    ("https://app.omie.com.br/api/v1/estoque/movestoque/",
     ["ListarMovimentos", "ListarMovEstoque"]),
]


hits = {}
for url, candidates in TESTS:
    last = url.rstrip("/").rsplit("/", 1)[-1]
    found = None
    last_msg = ""
    for c in candidates:
        s, miss, msg = try_call(url, c, params={"pagina": 1, "registros_por_pagina": 1})
        last_msg = msg[:80]
        if not miss and s < 500:
            # 200 OK confirms the call works
            found = c
            break
        if not miss and s == 500:
            # Method exists but param schema rejected — still confirms the name
            found = c + "  (param-rejected, but call name valid)"
            break
    if found:
        hits[last] = found
        print(f"  OK  {last:30s} -> {found}")
    else:
        print(f"  XX  {last:30s}     last_msg={last_msg}")

print("\n=== Verified call names ===")
for k, v in hits.items():
    print(f"  {k:30s} {v}")
