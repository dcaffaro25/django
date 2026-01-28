"""
Omie API endpoints with full parameter documentation.

Scraped from https://developer.omie.com.br/service-list/
Each endpoint includes:
- URL
- Available methods (Listar, Incluir, Alterar, Consultar, etc.)
- Parameter schemas for each method
- Default parameters
- Request/response types

Structure:
{
    "endpoint_name": {
        "url": "...",
        "description": "...",
        "methods": {
            "MethodName": {
                "param_schema": [...],
                "default_param": {...},
                "request_type": "...",
                "response_type": "..."
            }
        }
    }
}
"""

# Standard list method parameters (used by most endpoints)
STANDARD_LIST_PARAMS = [
    {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 50},
    {"name": "apenas_importado_api", "type": "string", "description": "Exibir apenas os registros gerados pela API (S/N)", "required": False, "default": "N"},
]

STANDARD_LIST_DEFAULTS = {"pagina": 1, "registros_por_pagina": 50, "apenas_importado_api": "N"}

STANDARD_CRUD_METHODS = {
    "Listar": {
        "param_schema": STANDARD_LIST_PARAMS,
        "default_param": STANDARD_LIST_DEFAULTS,
        "request_type": "list_request",
        "response_type": "list_response"
    },
    "Incluir": {
        "param_schema": [],
        "default_param": {},
        "request_type": "cadastro",
        "response_type": "status"
    },
    "Alterar": {
        "param_schema": [],
        "default_param": {},
        "request_type": "cadastro",
        "response_type": "status"
    },
    "Consultar": {
        "param_schema": [
            {"name": "codigo_omie", "type": "integer", "description": "Código no Omie", "required": False},
            {"name": "codigo_integracao", "type": "string", "description": "Código de Integração", "required": False},
        ],
        "default_param": {},
        "request_type": "chave",
        "response_type": "cadastro"
    },
    "Excluir": {
        "param_schema": [
            {"name": "codigo_omie", "type": "integer", "description": "Código no Omie", "required": False},
            {"name": "codigo_integracao", "type": "string", "description": "Código de Integração", "required": False},
        ],
        "default_param": {},
        "request_type": "chave",
        "response_type": "status"
    },
    "Upsert": {
        "param_schema": [],
        "default_param": {},
        "request_type": "cadastro",
        "response_type": "status"
    }
}

OMIE_API_ENDPOINTS = {
    # ============================================================================
    # GERAL - Clientes, Fornecedores, etc.
    # ============================================================================
    "Clientes": {
        "url": "https://app.omie.com.br/api/v1/geral/clientes/",
        "description": "Cria/edita/consulta o cadastro de clientes, fornecedores, transportadoras, etc",
        "methods": {
            "ListarClientes": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página retornada", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados na página", "required": False, "default": 50},
                    {"name": "apenas_importado_api", "type": "string", "description": "Exibir apenas os registros gerados pela API (S/N)", "required": False, "default": "N"},
                    {"name": "filtrar_por_data_de", "type": "string", "description": "Filtrar os registros a partir de uma data (dd/mm/aaaa)", "required": False},
                    {"name": "filtrar_por_data_ate", "type": "string", "description": "Filtrar os registros até uma data (dd/mm/aaaa)", "required": False},
                    {"name": "filtrar_por_hora_de", "type": "string", "description": "Filtro por hora a partir de (hh:mm:ss)", "required": False},
                    {"name": "filtrar_por_hora_ate", "type": "string", "description": "Filtro por hora até (hh:mm:ss)", "required": False},
                    {"name": "filtrar_apenas_inclusao", "type": "string", "description": "Filtrar apenas os registros incluídos (S/N)", "required": False, "default": "N"},
                    {"name": "filtrar_apenas_alteracao", "type": "string", "description": "Filtrar apenas os registros alterados (S/N)", "required": False, "default": "N"},
                    {"name": "exibir_caracteristicas", "type": "string", "description": "Exibe as características do cliente (S/N)", "required": False, "default": "N"},
                    {"name": "exibir_obs", "type": "string", "description": "Exibir as observações do cliente (S/N)", "required": False, "default": "N"},
                ],
                "default_param": {
                    "pagina": 1,
                    "registros_por_pagina": 50,
                    "apenas_importado_api": "N"
                },
                "request_type": "clientes_list_request",
                "response_type": "clientes_listfull_response"
            },
            "ListarClientesResumido": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página retornada", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados na página", "required": False, "default": 50},
                    {"name": "apenas_importado_api", "type": "string", "description": "Exibir apenas os registros gerados pela API (S/N)", "required": False, "default": "N"},
                ],
                "default_param": {
                    "pagina": 1,
                    "registros_por_pagina": 50,
                    "apenas_importado_api": "N"
                },
                "request_type": "clientes_list_request",
                "response_type": "clientes_list_response"
            },
            "IncluirCliente": {
                "param_schema": [
                    {"name": "codigo_cliente_integracao", "type": "string", "description": "Código de Integração com sistemas legados", "required": True},
                    {"name": "razao_social", "type": "string", "description": "Razão Social", "required": True},
                    {"name": "cnpj_cpf", "type": "string", "description": "CNPJ / CPF", "required": True},
                    {"name": "nome_fantasia", "type": "string", "description": "Nome Fantasia", "required": True},
                    {"name": "email", "type": "string", "description": "E-Mail", "required": False},
                    {"name": "telefone1_ddd", "type": "string", "description": "DDD Telefone", "required": False},
                    {"name": "telefone1_numero", "type": "string", "description": "Telefone para Contato", "required": False},
                    {"name": "endereco", "type": "string", "description": "Endereço", "required": False},
                    {"name": "endereco_numero", "type": "string", "description": "Número do Endereço", "required": False},
                    {"name": "complemento", "type": "string", "description": "Complemento para o Número do Endereço", "required": False},
                    {"name": "bairro", "type": "string", "description": "Bairro", "required": False},
                    {"name": "cidade", "type": "string", "description": "Código da Cidade (código IBGE ou nome)", "required": False},
                    {"name": "cidade_ibge", "type": "string", "description": "Código do IBGE para a Cidade", "required": False},
                    {"name": "estado", "type": "string", "description": "Sigla do Estado", "required": False},
                    {"name": "cep", "type": "string", "description": "CEP", "required": False},
                    {"name": "codigo_pais", "type": "string", "description": "Código do País", "required": False},
                    {"name": "inscricao_estadual", "type": "string", "description": "Inscrição Estadual", "required": False},
                    {"name": "inscricao_municipal", "type": "string", "description": "Inscrição Municipal", "required": False},
                    {"name": "optante_simples_nacional", "type": "string", "description": "Indica se é Optante do Simples Nacional (S/N)", "required": False},
                    {"name": "contribuinte", "type": "string", "description": "Indica se o cliente é contribuinte (S/N)", "required": False},
                    {"name": "observacao", "type": "text", "description": "Observações Internas", "required": False},
                ],
                "default_param": {},
                "request_type": "clientes_cadastro",
                "response_type": "clientes_status"
            },
            "AlterarCliente": {
                "param_schema": [
                    {"name": "codigo_cliente_omie", "type": "integer", "description": "Código de Cliente / Fornecedor", "required": False},
                    {"name": "codigo_cliente_integracao", "type": "string", "description": "Código de Integração com sistemas legados", "required": False},
                    {"name": "razao_social", "type": "string", "description": "Razão Social", "required": False},
                    {"name": "nome_fantasia", "type": "string", "description": "Nome Fantasia", "required": False},
                    {"name": "email", "type": "string", "description": "E-Mail", "required": False},
                ],
                "default_param": {},
                "request_type": "clientes_cadastro",
                "response_type": "clientes_status"
            },
            "ConsultarCliente": {
                "param_schema": [
                    {"name": "codigo_cliente_omie", "type": "integer", "description": "Código de Cliente / Fornecedor", "required": False},
                    {"name": "codigo_cliente_integracao", "type": "string", "description": "Código de Integração com sistemas legados", "required": False},
                ],
                "default_param": {},
                "request_type": "clientes_cadastro_chave",
                "response_type": "clientes_cadastro"
            },
            "ExcluirCliente": {
                "param_schema": [
                    {"name": "codigo_cliente_omie", "type": "integer", "description": "Código de Cliente / Fornecedor", "required": False},
                    {"name": "codigo_cliente_integracao", "type": "string", "description": "Código de Integração com sistemas legados", "required": False},
                ],
                "default_param": {},
                "request_type": "clientes_cadastro_chave",
                "response_type": "clientes_status"
            },
            "UpsertCliente": {
                "param_schema": [
                    {"name": "codigo_cliente_integracao", "type": "string", "description": "Código de Integração com sistemas legados", "required": True},
                    {"name": "razao_social", "type": "string", "description": "Razão Social", "required": True},
                    {"name": "cnpj_cpf", "type": "string", "description": "CNPJ / CPF", "required": True},
                    {"name": "nome_fantasia", "type": "string", "description": "Nome Fantasia", "required": True},
                ],
                "default_param": {},
                "request_type": "clientes_cadastro",
                "response_type": "clientes_status"
            },
            "UpsertClienteCpfCnpj": {
                "param_schema": [
                    {"name": "cnpj_cpf", "type": "string", "description": "CNPJ / CPF", "required": True},
                    {"name": "razao_social", "type": "string", "description": "Razão Social", "required": True},
                    {"name": "nome_fantasia", "type": "string", "description": "Nome Fantasia", "required": True},
                    {"name": "email", "type": "string", "description": "E-Mail", "required": False},
                ],
                "default_param": {},
                "request_type": "clientes_cadastro",
                "response_type": "clientes_status"
            },
        }
    },
    
    # ============================================================================
    # FINANÇAS - Contas a Pagar
    # ============================================================================
    "ContasAPagar": {
        "url": "https://app.omie.com.br/api/v1/financas/contapagar/",
        "description": "Cria/edita/consulta títulos a pagar",
        "methods": {
            "ListarContasPagar": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página que será listada", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 1000},
                    {"name": "apenas_importado_api", "type": "string", "description": "Exibir apenas os registros gerados pela API (S/N)", "required": False, "default": "N"},
                    {"name": "ordenar_por", "type": "string", "description": "CODIGO ou CODIGO_INTEGRACAO", "required": False, "default": "CODIGO"},
                    {"name": "ordem_descrescente", "type": "string", "description": "S ou N", "required": False, "default": "N"},
                    {"name": "filtrar_por_data_de", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": False},
                    {"name": "filtrar_por_data_ate", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": False},
                    {"name": "filtrar_apenas_inclusao", "type": "string", "description": "S ou N", "required": False, "default": "N"},
                    {"name": "filtrar_apenas_alteracao", "type": "string", "description": "S ou N", "required": False, "default": "N"},
                    {"name": "filtrar_por_emissao_de", "type": "string", "description": "dd/mm/aaaa", "required": False},
                    {"name": "filtrar_por_emissao_ate", "type": "string", "description": "dd/mm/aaaa", "required": False},
                    {"name": "filtrar_por_registro_de", "type": "string", "description": "Filtra registros a partir da data", "required": False},
                    {"name": "filtrar_por_registro_ate", "type": "string", "description": "Filtra registros até a data especificada", "required": False},
                    {"name": "filtrar_conta_corrente", "type": "integer", "description": "Código conta corrente", "required": False},
                    {"name": "filtrar_cliente", "type": "integer", "description": "Código cliente Omie", "required": False},
                    {"name": "filtrar_por_cpf_cnpj", "type": "string", "description": "CPF/CNPJ (apenas números)", "required": False},
                    {"name": "filtrar_por_status", "type": "string", "description": "CANCELADO, PAGO, LIQUIDADO, EMABERTO, PAGTO_PARCIAL, VENCEHOJE, AVENCER, ATRASADO", "required": False},
                    {"name": "filtrar_por_projeto", "type": "integer", "description": "Código projeto", "required": False},
                    {"name": "filtrar_por_vendedor", "type": "integer", "description": "Código vendedor", "required": False},
                    {"name": "exibir_obs", "type": "string", "description": "Exibir observações S/N", "required": False, "default": "N"},
                ],
                "default_param": {
                    "pagina": 1,
                    "registros_por_pagina": 1000,
                    "apenas_importado_api": "N"
                },
                "request_type": "lcpListarRequest",
                "response_type": "lcpListarResponse"
            },
            "IncluirContaPagar": {
                "param_schema": [
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código de Integração do Lançamento", "required": True},
                    {"name": "codigo_cliente_fornecedor", "type": "integer", "description": "Código do Favorecido / Fornecedor", "required": True},
                    {"name": "data_vencimento", "type": "string", "description": "Data de Vencimento (dd/mm/aaaa)", "required": True},
                    {"name": "valor_documento", "type": "decimal", "description": "Valor da Conta", "required": True},
                    {"name": "codigo_categoria", "type": "string", "description": "Código da Categoria", "required": False},
                    {"name": "data_previsao", "type": "string", "description": "Data da Previsão de Pagamento (dd/mm/aaaa)", "required": True},
                    {"name": "id_conta_corrente", "type": "integer", "description": "Código da Conta Corrente", "required": False},
                    {"name": "numero_documento_fiscal", "type": "string", "description": "Número da Nota Fiscal", "required": False},
                    {"name": "data_emissao", "type": "string", "description": "Data de Emissão (dd/mm/aaaa)", "required": False},
                    {"name": "observacao", "type": "text", "description": "Observação", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_pagar_cadastro",
                "response_type": "conta_pagar_cadastro_response"
            },
            "AlterarContaPagar": {
                "param_schema": [
                    {"name": "codigo_lancamento_omie", "type": "integer", "description": "Código do Lançamento de Contas a Pagar", "required": False},
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código de Integração do Lançamento", "required": False},
                    {"name": "valor_documento", "type": "decimal", "description": "Valor da Conta", "required": False},
                    {"name": "data_vencimento", "type": "string", "description": "Data de Vencimento (dd/mm/aaaa)", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_pagar_cadastro",
                "response_type": "conta_pagar_cadastro_response"
            },
            "ConsultarContaPagar": {
                "param_schema": [
                    {"name": "codigo_lancamento_omie", "type": "integer", "description": "Código do Lançamento de Contas a Pagar", "required": False},
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código de Integração do Lançamento", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_pagar_cadastro_chave",
                "response_type": "conta_pagar_cadastro"
            },
            "ExcluirContaPagar": {
                "param_schema": [
                    {"name": "codigo_lancamento_omie", "type": "integer", "description": "Código do Lançamento de Contas a Pagar", "required": False},
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código de Integração do Lançamento", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_pagar_cadastro_chave",
                "response_type": "conta_pagar_cadastro_response"
            },
            "LancarPagamento": {
                "param_schema": [
                    {"name": "codigo_lancamento", "type": "integer", "description": "Código do lançamento no contas a pagar", "required": False},
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código de Integração do Lançamento", "required": False},
                    {"name": "codigo_baixa_integracao", "type": "string", "description": "Código da baixa do integrador", "required": False},
                    {"name": "codigo_conta_corrente", "type": "integer", "description": "Código da Conta Corrente", "required": False},
                    {"name": "valor", "type": "decimal", "description": "Valor a ser baixado", "required": False},
                    {"name": "desconto", "type": "decimal", "description": "Valor do desconto", "required": False},
                    {"name": "juros", "type": "decimal", "description": "Valor do Juros", "required": False},
                    {"name": "multa", "type": "decimal", "description": "Valor da multa", "required": False},
                    {"name": "data", "type": "string", "description": "Data da Baixa (dd/mm/aaaa)", "required": False},
                    {"name": "observacao", "type": "text", "description": "Observação da Baixa", "required": False},
                    {"name": "conciliar_documento", "type": "string", "description": "Efetua a conciliação do documento automaticamente (S/N)", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_pagar_lancar_pagamento",
                "response_type": "conta_pagar_lancar_pagamento_resposta"
            },
            "CancelarPagamento": {
                "param_schema": [
                    {"name": "codigo_baixa", "type": "integer", "description": "Código para identificar a baixa do título", "required": False},
                    {"name": "codigo_baixa_integracao", "type": "string", "description": "Código da baixa do integrador", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_pagar_cancelar_pagamento",
                "response_type": "conta_pagar_cancelar_pagamento_resposta"
            },
            "UpsertContaPagar": {
                "param_schema": [
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código de Integração do Lançamento", "required": True},
                    {"name": "codigo_cliente_fornecedor", "type": "integer", "description": "Código do Favorecido / Fornecedor", "required": True},
                    {"name": "data_vencimento", "type": "string", "description": "Data de Vencimento (dd/mm/aaaa)", "required": True},
                    {"name": "valor_documento", "type": "decimal", "description": "Valor da Conta", "required": True},
                    {"name": "codigo_categoria", "type": "string", "description": "Código da Categoria", "required": False},
                    {"name": "data_previsao", "type": "string", "description": "Data da Previsão de Pagamento (dd/mm/aaaa)", "required": True},
                    {"name": "id_conta_corrente", "type": "integer", "description": "Código da Conta Corrente", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_pagar_cadastro",
                "response_type": "conta_pagar_cadastro_response"
            },
        }
    },
    
    # ============================================================================
    # FINANÇAS - Contas a Receber
    # ============================================================================
    "ContasAReceber": {
        "url": "https://app.omie.com.br/api/v1/financas/contareceber/",
        "description": "Cria/edita/consulta títulos a receber",
        "methods": {
            "ListarContasReceber": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página que será listada", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 20},
                    {"name": "apenas_importado_api", "type": "string", "description": "DEPRECATED", "required": False},
                    {"name": "ordenar_por", "type": "string", "description": "CODIGO, CODIGO_INTEGRACAO, DATA_EMISSAO, DATA_INCLUSAO, DATA_ALTERACAO, DATA_VENCIMENTO, DATA_PAGAMENTO", "required": False, "default": "CODIGO"},
                    {"name": "ordem_descrescente", "type": "string", "description": "Indica se a ordem de exibição é decrescente (S/N)", "required": False, "default": "N"},
                    {"name": "filtrar_por_data_de", "type": "string", "description": "Filtrar lançamentos incluídos e/ou alterados até a data (dd/mm/aaaa)", "required": False},
                    {"name": "filtrar_por_data_ate", "type": "string", "description": "Filtrar lançamentos incluídos e/ou alterados até a data (dd/mm/aaaa)", "required": False},
                    {"name": "filtrar_apenas_inclusao", "type": "string", "description": "Filtrar apenas registros incluídos (S/N)", "required": False, "default": "N"},
                    {"name": "filtrar_apenas_alteracao", "type": "string", "description": "Filtrar apenas registros alterados (S/N)", "required": False, "default": "N"},
                    {"name": "filtrar_por_emissao_de", "type": "string", "description": "Data de alteração inicial (dd/mm/aaaa)", "required": False},
                    {"name": "filtrar_por_registro_de", "type": "string", "description": "Filtra os registros a partir da data", "required": False},
                    {"name": "filtrar_por_emissao_ate", "type": "string", "description": "Data de alteração final (dd/mm/aaaa)", "required": False},
                    {"name": "filtrar_por_registro_ate", "type": "string", "description": "Filtra os registros até a data especificada", "required": False},
                    {"name": "filtrar_conta_corrente", "type": "integer", "description": "Código da Conta Corrente", "required": False},
                    {"name": "filtrar_apenas_titulos_em_aberto", "type": "string", "description": "Filtra os registros exibidos apenas os títulos em aberto (S/N)", "required": False},
                    {"name": "filtrar_cliente", "type": "integer", "description": "Filtra os registros exibidos por cliente", "required": False},
                    {"name": "filtrar_por_status", "type": "string", "description": "Filtrar por Status", "required": False},
                    {"name": "filtrar_por_cpf_cnpj", "type": "string", "description": "Filtrar os títulos por CPF/CNPJ", "required": False},
                    {"name": "filtrar_por_projeto", "type": "integer", "description": "Código do Projeto", "required": False},
                    {"name": "filtrar_por_vendedor", "type": "integer", "description": "Código do Vendedor", "required": False},
                    {"name": "exibir_obs", "type": "string", "description": "Exibir as observações do lançamento (S/N)", "required": False, "default": "N"},
                ],
                "default_param": {
                    "pagina": 1,
                    "registros_por_pagina": 20,
                    "apenas_importado_api": "N"
                },
                "request_type": "lcrListarRequest",
                "response_type": "lcrListarResponse"
            },
            "IncluirContaReceber": {
                "param_schema": [
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código do lançamento gerado pelo integrador", "required": True},
                    {"name": "codigo_cliente_fornecedor", "type": "integer", "description": "Código de Cliente / Fornecedor", "required": True},
                    {"name": "data_vencimento", "type": "string", "description": "Data de Vencimento (dd/mm/aaaa)", "required": True},
                    {"name": "valor_documento", "type": "decimal", "description": "Valor do Lançamento", "required": True},
                    {"name": "codigo_categoria", "type": "string", "description": "Código da Categoria", "required": False},
                    {"name": "data_previsao", "type": "string", "description": "Data de Previsão de Pagamento/Recebimento (dd/mm/aaaa)", "required": True},
                    {"name": "id_conta_corrente", "type": "integer", "description": "Id da Conta Corrente", "required": False},
                    {"name": "numero_documento", "type": "string", "description": "Número do Documento", "required": False},
                    {"name": "numero_parcela", "type": "string", "description": "Número da parcela (formato 999/999)", "required": False},
                    {"name": "observacao", "type": "text", "description": "Observação da Baixa do Contas a Receber", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_receber_cadastro",
                "response_type": "conta_receber_cadastro_response"
            },
            "AlterarContaReceber": {
                "param_schema": [
                    {"name": "codigo_lancamento_omie", "type": "integer", "description": "Chave do Lançamento", "required": False},
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código do lançamento gerado pelo integrador", "required": False},
                    {"name": "valor_documento", "type": "decimal", "description": "Valor do Lançamento", "required": False},
                    {"name": "data_vencimento", "type": "string", "description": "Data de Vencimento (dd/mm/aaaa)", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_receber_cadastro",
                "response_type": "conta_receber_cadastro_response"
            },
            "ConsultarContaReceber": {
                "param_schema": [
                    {"name": "codigo_lancamento_omie", "type": "integer", "description": "Chave do Lançamento", "required": False},
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código do lançamento gerado pelo integrador", "required": False},
                ],
                "default_param": {},
                "request_type": "lcrChave",
                "response_type": "conta_receber_cadastro"
            },
            "LancarRecebimento": {
                "param_schema": [
                    {"name": "codigo_lancamento", "type": "integer", "description": "Código do lançamento no contas a receber", "required": False},
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código do lançamento gerado pelo integrador", "required": False},
                    {"name": "codigo_baixa_integracao", "type": "string", "description": "Código de Integração da Baixa", "required": False},
                    {"name": "codigo_conta_corrente", "type": "integer", "description": "Código da Conta Corrente", "required": False},
                    {"name": "valor", "type": "decimal", "description": "Valor a ser baixado", "required": False},
                    {"name": "juros", "type": "decimal", "description": "Valor do Juros", "required": False},
                    {"name": "desconto", "type": "decimal", "description": "Valor do desconto", "required": False},
                    {"name": "multa", "type": "decimal", "description": "Valor da multa", "required": False},
                    {"name": "data", "type": "string", "description": "Data da Baixa (dd/mm/aaaa)", "required": False},
                    {"name": "observacao", "type": "text", "description": "Observação da Baixa do Contas a Receber", "required": False},
                    {"name": "conciliar_documento", "type": "string", "description": "Efetua a conciliação do documento automaticamente (S/N)", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_receber_lancar_recebimento",
                "response_type": "conta_receber_lancar_recebimento_resposta"
            },
            "CancelarRecebimento": {
                "param_schema": [
                    {"name": "codigo_baixa", "type": "integer", "description": "Código da Baixa", "required": False},
                    {"name": "codigo_baixa_integracao", "type": "string", "description": "Código de Integração da Baixa", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_receber_cancelar_recebimento",
                "response_type": "conta_receber_cancelar_recebimento_resposta"
            },
            "UpsertContaReceber": {
                "param_schema": [
                    {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código do lançamento gerado pelo integrador", "required": True},
                    {"name": "codigo_cliente_fornecedor", "type": "integer", "description": "Código de Cliente / Fornecedor", "required": True},
                    {"name": "data_vencimento", "type": "string", "description": "Data de Vencimento (dd/mm/aaaa)", "required": True},
                    {"name": "valor_documento", "type": "decimal", "description": "Valor do Lançamento", "required": True},
                    {"name": "codigo_categoria", "type": "string", "description": "Código da Categoria", "required": False},
                    {"name": "data_previsao", "type": "string", "description": "Data de Previsão de Pagamento/Recebimento (dd/mm/aaaa)", "required": True},
                    {"name": "id_conta_corrente", "type": "integer", "description": "Id da Conta Corrente", "required": False},
                ],
                "default_param": {},
                "request_type": "conta_receber_cadastro",
                "response_type": "conta_receber_cadastro_response"
            },
        }
    },
    
    # ============================================================================
    # Additional endpoints - Simplified structure (can be expanded later)
    # ============================================================================
    
    "ClientesCaracteristicas": {
        "url": "https://app.omie.com.br/api/v1/geral/clientescaract/",
        "description": "Cria/edita/consulta características de clientes",
        "methods": {
            "ListarCaracteristicas": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 50},
                ],
                "default_param": {"pagina": 1, "registros_por_pagina": 50},
                "request_type": "list_request",
                "response_type": "list_response"
            }
        }
    },
    
    "Tags": {
        "url": "https://app.omie.com.br/api/v1/geral/clientetag/",
        "description": "Cria/edita/consulta tags quem são usadas no cadastro de clientes, fornecedores, etc",
        "methods": {
            "ListarTags": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 50},
                ],
                "default_param": {"pagina": 1, "registros_por_pagina": 50},
                "request_type": "list_request",
                "response_type": "list_response"
            }
        }
    },
    
    "Projetos": {
        "url": "https://app.omie.com.br/api/v1/geral/projetos/",
        "description": "Cria/edita/consulta projetos",
        "methods": {
            "ListarProjetos": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 50},
                ],
                "default_param": {"pagina": 1, "registros_por_pagina": 50},
                "request_type": "list_request",
                "response_type": "list_response"
            }
        }
    },
    
    "Empresas": {
        "url": "https://app.omie.com.br/api/v1/geral/empresas/",
        "description": "Lista o cadastro da empresa",
        "methods": {
            "ListarEmpresas": {
                "param_schema": [],
                "default_param": {},
                "request_type": "list_request",
                "response_type": "list_response"
            }
        }
    },
    
    "Departamentos": {
        "url": "https://app.omie.com.br/api/v1/geral/departamentos/",
        "description": "Lista o cadastro de departamentos",
        "methods": {
            "ListarDepartamentos": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 50},
                ],
                "default_param": {"pagina": 1, "registros_por_pagina": 50},
                "request_type": "list_request",
                "response_type": "list_response"
            }
        }
    },
    
    "Categorias": {
        "url": "https://app.omie.com.br/api/v1/geral/categorias/",
        "description": "Lista o cadastro de categorias",
        "methods": {
            "ListarCategorias": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 50},
                ],
                "default_param": {"pagina": 1, "registros_por_pagina": 50},
                "request_type": "list_request",
                "response_type": "list_response"
            }
        }
    },
    
    "ContasCorrentes": {
        "url": "https://app.omie.com.br/api/v1/geral/contacorrente/",
        "description": "Cria/edita/consulta o cadastro de contas correntes",
        "methods": {
            "ListarContasCorrentes": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página que será listada", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 100},
                    {"name": "apenas_importado_api", "type": "string", "description": "Exibir apenas registros da API (S/N)", "required": False, "default": "N"},
                    {"name": "codigo", "type": "integer", "description": "Código da conta corrente no Omie", "required": False},
                    {"name": "codigo_integracao", "type": "string", "description": "Código de Integração do Parceiro", "required": False},
                    {"name": "ordenar_por", "type": "string", "description": "CODIGO, INTEGRACAO ou DATA_LANCAMENTO", "required": False},
                    {"name": "ordem_descrescente", "type": "string", "description": "Ordem decrescente (S/N)", "required": False},
                    {"name": "filtrar_por_data_de", "type": "string", "description": "Filtrar até a data (dd/mm/aaaa)", "required": False},
                    {"name": "filtrar_por_data_ate", "type": "string", "description": "Filtrar até a data (dd/mm/aaaa)", "required": False},
                    {"name": "filtrar_apenas_inclusao", "type": "string", "description": "Filtrar apenas incluídos (S/N)", "required": False},
                    {"name": "filtrar_apenas_alteracao", "type": "string", "description": "Filtrar apenas alterados (S/N)", "required": False},
                    {"name": "filtrar_apenas_ativo", "type": "string", "description": "Filtrar apenas contas ativas (S/N)", "required": False},
                ],
                "default_param": {"pagina": 1, "registros_por_pagina": 100, "apenas_importado_api": "N"},
                "request_type": "fin_conta_corrente_listar_request",
                "response_type": "fin_conta_corrente_listar_response"
            },
            "ListarResumoContasCorrentes": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros", "required": False, "default": 100},
                    {"name": "apenas_importado_api", "type": "string", "description": "Exibir apenas da API (S/N)", "required": False, "default": "N"},
                    {"name": "codigo", "type": "integer", "description": "Código da conta no Omie", "required": False},
                    {"name": "codigo_integracao", "type": "string", "description": "Código de Integração", "required": False},
                    {"name": "filtrar_apenas_ativo", "type": "string", "description": "Filtrar apenas ativas (S/N)", "required": False},
                ],
                "default_param": {"pagina": 1, "registros_por_pagina": 100, "apenas_importado_api": "N"},
                "request_type": "fin_conta_corrente_resumo_request",
                "response_type": "fin_conta_corrente_resumo_response"
            },
            "IncluirContaCorrente": {
                "param_schema": [
                    {"name": "cCodCCInt", "type": "string", "description": "Código de Integração", "required": True},
                    {"name": "tipo_conta_corrente", "type": "string", "description": "CX, CC, CR, CA, etc. (ver API)", "required": True},
                    {"name": "codigo_banco", "type": "string", "description": "Código do banco (ex: 341 Itaú)", "required": False},
                    {"name": "descricao", "type": "string", "description": "Descrição da conta", "required": True},
                    {"name": "saldo_inicial", "type": "decimal", "description": "Saldo inicial", "required": False, "default": 0},
                    {"name": "saldo_data", "type": "string", "description": "Data do saldo inicial (dd/mm/aaaa)", "required": False},
                    {"name": "codigo_agencia", "type": "string", "description": "Código da agência", "required": False},
                    {"name": "numero_conta_corrente", "type": "string", "description": "Número da conta", "required": False},
                ],
                "default_param": {"saldo_inicial": 0},
                "request_type": "fin_conta_corrente_cadastro",
                "response_type": "fin_conta_corrente_cadastro_response"
            },
            "AlterarContaCorrente": {
                "param_schema": [
                    {"name": "nCodCC", "type": "integer", "description": "Código da conta no Omie", "required": False},
                    {"name": "cCodCCInt", "type": "string", "description": "Código de Integração", "required": False},
                    {"name": "descricao", "type": "string", "description": "Descrição", "required": False},
                    {"name": "tipo_conta_corrente", "type": "string", "description": "Tipo da conta", "required": False},
                    {"name": "codigo_banco", "type": "string", "description": "Código do banco", "required": False},
                    {"name": "saldo_inicial", "type": "decimal", "description": "Saldo inicial", "required": False},
                ],
                "default_param": {},
                "request_type": "fin_conta_corrente_cadastro",
                "response_type": "fin_conta_corrente_cadastro_response"
            },
            "ConsultarContaCorrente": {
                "param_schema": [
                    {"name": "nCodCC", "type": "integer", "description": "Código da conta no Omie", "required": False},
                    {"name": "cCodCCInt", "type": "string", "description": "Código de Integração", "required": False},
                ],
                "default_param": {},
                "request_type": "fin_conta_corrente_chave",
                "response_type": "fin_conta_corrente_cadastro"
            },
            "ExcluirContaCorrente": {
                "param_schema": [
                    {"name": "nCodCC", "type": "integer", "description": "Código da conta no Omie", "required": False},
                    {"name": "cCodCCInt", "type": "string", "description": "Código de Integração", "required": False},
                ],
                "default_param": {},
                "request_type": "fin_conta_corrente_chave",
                "response_type": "fin_conta_corrente_cadastro_response"
            },
            "UpsertContaCorrente": {
                "param_schema": [
                    {"name": "cCodCCInt", "type": "string", "description": "Código de Integração", "required": True},
                    {"name": "tipo_conta_corrente", "type": "string", "description": "Tipo da conta", "required": True},
                    {"name": "codigo_banco", "type": "string", "description": "Código do banco", "required": False},
                    {"name": "descricao", "type": "string", "description": "Descrição", "required": True},
                    {"name": "saldo_inicial", "type": "decimal", "description": "Saldo inicial", "required": False, "default": 0},
                ],
                "default_param": {"saldo_inicial": 0},
                "request_type": "fin_conta_corrente_cadastro",
                "response_type": "fin_conta_corrente_cadastro_response"
            },
        }
    },

    "ExtratoContaCorrente": {
        "url": "https://app.omie.com.br/api/v1/financas/extrato/",
        "description": "Listagem do extrato de conta corrente",
        "methods": {
            "ListarExtrato": {
                "param_schema": [
                    {"name": "nCodCC", "type": "integer", "description": "Código da Conta Corrente no Omie", "required": False},
                    {"name": "cCodIntCC", "type": "string", "description": "Código de Integração da Conta Corrente", "required": False},
                    {"name": "dPeriodoInicial", "type": "string", "description": "Período inicial (DD/MM/AAAA)", "required": True},
                    {"name": "dPeriodoFinal", "type": "string", "description": "Período final (DD/MM/AAAA)", "required": True},
                    {"name": "cExibirApenasSaldo", "type": "string", "description": "Exibir apenas saldos (S/N)", "required": False, "default": "N"},
                ],
                "default_param": {"cExibirApenasSaldo": "N"},
                "request_type": "eccListarExtratoRequest",
                "response_type": "eccListarExtratoResponse"
            }
        }
    },
    
    "Produtos": {
        "url": "https://app.omie.com.br/api/v1/geral/produtos/",
        "description": "Cria/edita/consulta produtos",
        "methods": {
            "ListarProdutos": {
                "param_schema": [
                    {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 50},
                    {"name": "apenas_importado_api", "type": "string", "description": "Exibir apenas os registros gerados pela API (S/N)", "required": False, "default": "N"},
                ],
                "default_param": {"pagina": 1, "registros_por_pagina": 50, "apenas_importado_api": "N"},
                "request_type": "produtos_list_request",
                "response_type": "produtos_list_response"
            },
            "IncluirProduto": {
                "param_schema": [
                    {"name": "codigo_produto_integracao", "type": "string", "description": "Código de Integração do Produto", "required": True},
                    {"name": "descricao", "type": "string", "description": "Descrição do Produto", "required": True},
                    {"name": "unidade", "type": "string", "description": "Unidade de Medida", "required": False},
                    {"name": "valor_unitario", "type": "decimal", "description": "Valor Unitário", "required": False},
                ],
                "default_param": {},
                "request_type": "produtos_cadastro",
                "response_type": "produtos_status"
            }
        }
    },
}

# ============================================================================
# Additional endpoints - Standard CRUD methods pattern
# Detailed parameters can be fetched from API docs when needed
# ============================================================================

# Additional endpoints with standard methods
additional_endpoints = {
        "ClientesCaracteristicas": {
            "url": "https://app.omie.com.br/api/v1/geral/clientescaract/",
            "description": "Cria/edita/consulta características de clientes",
            "methods": STANDARD_CRUD_METHODS
        },
        "Tags": {
            "url": "https://app.omie.com.br/api/v1/geral/clientetag/",
            "description": "Cria/edita/consulta tags quem são usadas no cadastro de clientes, fornecedores, etc",
            "methods": STANDARD_CRUD_METHODS
        },
        "Projetos": {
            "url": "https://app.omie.com.br/api/v1/geral/projetos/",
            "description": "Cria/edita/consulta projetos",
            "methods": {
                "ListarProjetos": {
                    "param_schema": [
                        {"name": "pagina", "type": "integer", "description": "Número da página que será listada", "required": False, "default": 1},
                        {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 50},
                        {"name": "apenas_importado_api", "type": "string", "description": "Exibir apenas os registros gerados pela API (S/N)", "required": False, "default": "N"},
                        {"name": "ordenar_por", "type": "string", "description": "CODIGO, INTEGRACAO ou DATA_LANCAMENTO", "required": False, "default": "CODIGO"},
                        {"name": "ordem_descrescente", "type": "string", "description": "Ordem decrescente (S/N)", "required": False, "default": "N"},
                        {"name": "filtrar_por_data_de", "type": "string", "description": "Filtrar lançamentos até a data (dd/mm/aaaa)", "required": False},
                        {"name": "filtrar_por_data_ate", "type": "string", "description": "Filtrar lançamentos até a data (dd/mm/aaaa)", "required": False},
                        {"name": "filtrar_apenas_inclusao", "type": "string", "description": "Filtrar apenas registros incluídos (S/N)", "required": False, "default": "N"},
                        {"name": "filtrar_apenas_alteracao", "type": "string", "description": "Filtrar apenas registros alterados (S/N)", "required": False, "default": "N"},
                        {"name": "nome_projeto", "type": "string", "description": "Nome do projeto", "required": False},
                    ],
                    "default_param": {"pagina": 1, "registros_por_pagina": 50, "apenas_importado_api": "N"},
                    "request_type": "projListarRequest",
                    "response_type": "projListarResponse"
                },
                "IncluirProjeto": {
                    "param_schema": [
                        {"name": "codInt", "type": "string", "description": "Código de Integração do projeto", "required": True},
                        {"name": "nome", "type": "string", "description": "Nome do projeto", "required": True},
                        {"name": "inativo", "type": "string", "description": "Projeto inativo (S/N)", "required": False, "default": "N"},
                    ],
                    "default_param": {"inativo": "N"},
                    "request_type": "projIncluirRequest",
                    "response_type": "projIncluirResponse"
                },
                "AlterarProjeto": {
                    "param_schema": [
                        {"name": "codigo", "type": "integer", "description": "Código do projeto", "required": False},
                        {"name": "codInt", "type": "string", "description": "Código de Integração do projeto", "required": False},
                        {"name": "nome", "type": "string", "description": "Nome do projeto", "required": False},
                        {"name": "inativo", "type": "string", "description": "Projeto inativo (S/N)", "required": False, "default": "N"},
                    ],
                    "default_param": {},
                    "request_type": "projAlterarRequest",
                    "response_type": "projAlterarResponse"
                },
                "ConsultarProjeto": {
                    "param_schema": [
                        {"name": "codigo", "type": "integer", "description": "Código do projeto", "required": False},
                        {"name": "codInt", "type": "string", "description": "Código de Integração do projeto", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "projConsultarRequest",
                    "response_type": "projConsultarResponse"
                },
                "ExcluirProjeto": {
                    "param_schema": [
                        {"name": "codigo", "type": "integer", "description": "Código do projeto", "required": False},
                        {"name": "codInt", "type": "string", "description": "Código de Integração do projeto", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "projExcluirRequest",
                    "response_type": "projExcluirResponse"
                },
                "UpsertProjeto": {
                    "param_schema": [
                        {"name": "codigo", "type": "integer", "description": "Código do projeto", "required": False},
                        {"name": "codInt", "type": "string", "description": "Código de Integração do projeto", "required": False},
                        {"name": "nome", "type": "string", "description": "Nome do projeto", "required": True},
                        {"name": "inativo", "type": "string", "description": "Projeto inativo (S/N)", "required": False, "default": "N"},
                    ],
                    "default_param": {"inativo": "N"},
                    "request_type": "projUpsertRequest",
                    "response_type": "projUpsertResponse"
                },
            }
        },
        "Empresas": {
            "url": "https://app.omie.com.br/api/v1/geral/empresas/",
            "description": "Lista o cadastro da empresa",
            "methods": {
                "ListarEmpresas": {
                    "param_schema": [
                        {"name": "pagina", "type": "integer", "description": "Número da página retornada", "required": False, "default": 1},
                        {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados na página", "required": False, "default": 100},
                        {"name": "apenas_importado_api", "type": "string", "description": "Exibir apenas os registros gerados pela API (S/N)", "required": False, "default": "N"},
                    ],
                    "default_param": {"pagina": 1, "registros_por_pagina": 100, "apenas_importado_api": "N"},
                    "request_type": "empresas_list_request",
                    "response_type": "empresas_list_response"
                },
                "ConsultarEmpresa": {
                    "param_schema": [
                        {"name": "codigo_empresa", "type": "integer", "description": "Código da Empresa", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "empresas_consultar",
                    "response_type": "empresas_cadastro"
                },
            }
        },
        "Departamentos": {
            "url": "https://app.omie.com.br/api/v1/geral/departamentos/",
            "description": "Lista o cadastro de departamentos",
            "methods": {
                "ListarDepartamentos": {
                    "param_schema": [
                        {"name": "pagina", "type": "integer", "description": "Número da página que será listada", "required": False, "default": 1},
                        {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 50},
                    ],
                    "default_param": {"pagina": 1, "registros_por_pagina": 50},
                    "request_type": "departamento_listar_request",
                    "response_type": "departamento_listar_response"
                },
                "IncluirDepartamento": {
                    "param_schema": [
                        {"name": "codigo", "type": "string", "description": "Código do Departamento / Centro de Custo (onde incluir o novo)", "required": True},
                        {"name": "descricao", "type": "string", "description": "Nome do Departamento / Centro de Custo", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "departamento_incluir_request",
                    "response_type": "departamento_incluir_response"
                },
                "AlterarDepartamento": {
                    "param_schema": [
                        {"name": "codigo", "type": "string", "description": "Código do Departamento / Centro de Custo", "required": True},
                        {"name": "descricao", "type": "string", "description": "Nome do Departamento / Centro de Custo", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "departamento_alterar_request",
                    "response_type": "departamento_alterar_response"
                },
                "ConsultarDepartamento": {
                    "param_schema": [
                        {"name": "codigo", "type": "string", "description": "Código do Departamento / Centro de Custo", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "departamento_consultar",
                    "response_type": "departamentos"
                },
                "ExcluirDepartamento": {
                    "param_schema": [
                        {"name": "codigo", "type": "string", "description": "Código do Departamento / Centro de Custo", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "departamento_excluir_request",
                    "response_type": "departamento_excluir_response"
                },
            }
        },
        "Categorias": {
            "url": "https://app.omie.com.br/api/v1/geral/categorias/",
            "description": "Lista o cadastro de categorias",
            "methods": {
                "ListarCategorias": {
                    "param_schema": [
                        {"name": "pagina", "type": "integer", "description": "Número da página retornada", "required": False, "default": 1},
                        {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados na página", "required": False, "default": 50},
                        {"name": "filtrar_apenas_ativo", "type": "string", "description": "Filtrar apenas categorias ativas (S/N)", "required": False},
                        {"name": "filtrar_por_tipo", "type": "string", "description": "R - Receita ou D - Despesa", "required": False},
                    ],
                    "default_param": {"pagina": 1, "registros_por_pagina": 50},
                    "request_type": "categoria_list_request",
                    "response_type": "categoria_listfull_response"
                },
                "ConsultarCategoria": {
                    "param_schema": [
                        {"name": "codigo", "type": "string", "description": "Código da Categoria", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "categoria_consultar",
                    "response_type": "categoria_cadastro"
                },
                "IncluirCategoria": {
                    "param_schema": [
                        {"name": "categoria_superior", "type": "string", "description": "Código do grupo da categoria (4 dígitos, totalizadora)", "required": True},
                        {"name": "descricao", "type": "string", "description": "Descrição da Categoria", "required": True},
                        {"name": "natureza", "type": "string", "description": "Natureza da conta (Observação)", "required": False},
                        {"name": "tipo_categoria", "type": "string", "description": "Tipo de gasto/receita (API /api/v1/geral/tipocategoria/)", "required": False},
                        {"name": "codigo_dre", "type": "string", "description": "Código no DRE (API /api/v1/geral/dre/)", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "categoria_incluir",
                    "response_type": "categoria_cadastro_response"
                },
                "AlterarCategoria": {
                    "param_schema": [
                        {"name": "codigo", "type": "string", "description": "Código da Categoria", "required": True},
                        {"name": "descricao", "type": "string", "description": "Descrição da Categoria", "required": False},
                        {"name": "natureza", "type": "string", "description": "Natureza da conta", "required": False},
                        {"name": "tipo_categoria", "type": "string", "description": "Tipo de gasto/receita", "required": False},
                        {"name": "codigo_dre", "type": "string", "description": "Código no DRE", "required": False},
                        {"name": "conta_inativa", "type": "string", "description": "Categoria inativa (S/N)", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "categoria_alterar",
                    "response_type": "categoria_cadastro_response"
                },
                "IncluirGrupoCategoria": {
                    "param_schema": [
                        {"name": "descricao", "type": "string", "description": "Descrição do grupo", "required": True},
                        {"name": "tipo_grupo", "type": "string", "description": "R = Receita ou D = Despesa", "required": True},
                        {"name": "natureza", "type": "string", "description": "Natureza da conta", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "categoria_grupo_incluir",
                    "response_type": "categoria_cadastro_response"
                },
                "AlterarGrupoCategoria": {
                    "param_schema": [
                        {"name": "codigo", "type": "string", "description": "Código do grupo", "required": True},
                        {"name": "descricao", "type": "string", "description": "Descrição do grupo", "required": False},
                        {"name": "natureza", "type": "string", "description": "Natureza da conta", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "categoria_grupo_alterar",
                    "response_type": "categoria_cadastro_response"
                },
            }
        },
        "Parcelas": {
            "url": "https://app.omie.com.br/api/v1/geral/parcelas/",
            "description": "Lista as parcelas cadastradas",
            "methods": {"ListarParcelas": STANDARD_CRUD_METHODS["Listar"]}
        },
        "TiposAtividade": {
            "url": "https://app.omie.com.br/api/v1/geral/tpativ/",
            "description": "Lista os tipos de atividade da empresa",
            "methods": {"ListarTiposAtividade": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CNAE": {
            "url": "https://app.omie.com.br/api/v1/produtos/cnae/",
            "description": "Lista códigos CNAE",
            "methods": {"ListarCNAE": STANDARD_CRUD_METHODS["Listar"]}
        },
        "Cidades": {
            "url": "https://app.omie.com.br/api/v1/geral/cidades/",
            "description": "Lista o cadastro de cidades",
            "methods": {"PesquisarCidades": {
                "param_schema": [
                    {"name": "pesquisa", "type": "string", "description": "Nome ou código da cidade", "required": False},
                    {"name": "estado", "type": "string", "description": "Sigla do estado", "required": False},
                ],
                "default_param": {},
                "request_type": "cidades_request",
                "response_type": "cidades_response"
            }}
        },
        "Paises": {
            "url": "https://app.omie.com.br/api/v1/geral/paises/",
            "description": "Lista o cadastro de países",
            "methods": {"ListarPaises": STANDARD_CRUD_METHODS["Listar"]}
        },
        "TiposAnexos": {
            "url": "https://app.omie.com.br/api/v1/geral/tiposanexo/",
            "description": "Consulta Tipos de Anexos",
            "methods": {"ConsultarTiposAnexo": STANDARD_CRUD_METHODS["Consultar"]}
        },
        "DocumentosAnexos": {
            "url": "https://app.omie.com.br/api/v1/geral/anexo/",
            "description": "Criar/edita/consulta e exclui documentos anexos",
            "methods": STANDARD_CRUD_METHODS
        },
        "TipoEntrega": {
            "url": "https://app.omie.com.br/api/v1/geral/tiposentrega/",
            "description": "Criar/edita/consulta e exclui tipo de entrega de fornecedores",
            "methods": STANDARD_CRUD_METHODS
        },
        "TipoAssinante": {
            "url": "https://app.omie.com.br/api/v1/geral/tipoassinante/",
            "description": "Lista os Tipos de Assinante",
            "methods": {"ListarTipoAssinante": STANDARD_CRUD_METHODS["Listar"]}
        },
        "Tarefas": {
            "url": "https://app.omie.com.br/api/v1/geral/tarefas/",
            "description": "Cria/consulta/lista variações dos produtos",
            "methods": STANDARD_CRUD_METHODS
        },
        
        # CRM
        "CRMContas": {
            "url": "https://app.omie.com.br/api/v1/crm/contas/",
            "description": "Cria/edita/consulta Contas",
            "methods": STANDARD_CRUD_METHODS
        },
        "CRMContasCaracteristicas": {
            "url": "https://app.omie.com.br/api/v1/crm/contascaract/",
            "description": "Cria/edita/consulta caracterísitcas da conta",
            "methods": STANDARD_CRUD_METHODS
        },
        "CRMContatos": {
            "url": "https://app.omie.com.br/api/v1/crm/contatos/",
            "description": "Cria/edita/consulta Contatos",
            "methods": STANDARD_CRUD_METHODS
        },
        "CRMOportunidades": {
            "url": "https://app.omie.com.br/api/v1/crm/oportunidades/",
            "description": "Cria/edita/consulta Oportunidades",
            "methods": STANDARD_CRUD_METHODS
        },
        "CRMOportunidadesResumo": {
            "url": "https://app.omie.com.br/api/v1/crm/oportunidades-resumo/",
            "description": "Resumo de Oportunidades",
            "methods": {"ListarOportunidadesResumo": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMTarefas": {
            "url": "https://app.omie.com.br/api/v1/crm/tarefas/",
            "description": "Cria/edita/consulta Tarefas",
            "methods": STANDARD_CRUD_METHODS
        },
        "CRMTarefasResumo": {
            "url": "https://app.omie.com.br/api/v1/crm/tarefas-resumo/",
            "description": "Resumo de Tarefas",
            "methods": {"ListarTarefasResumo": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMSolucoes": {
            "url": "https://app.omie.com.br/api/v1/crm/solucoes/",
            "description": "Lista das soluções ofertadas através do CRM",
            "methods": {"ListarSolucoes": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMFases": {
            "url": "https://app.omie.com.br/api/v1/crm/fases/",
            "description": "Lista as fases da oportunidade",
            "methods": {"ListarFases": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMUsuarios": {
            "url": "https://app.omie.com.br/api/v1/crm/usuarios/",
            "description": "Lista dos usuários do CRM",
            "methods": {"ListarUsuarios": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMStatus": {
            "url": "https://app.omie.com.br/api/v1/crm/status/",
            "description": "Lista status possíveis de uma oportunidade",
            "methods": {"ListarStatus": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMMotivos": {
            "url": "https://app.omie.com.br/api/v1/crm/motivos/",
            "description": "Lista motivos de conclusão de uma oportunidade",
            "methods": {"ListarMotivos": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMTipos": {
            "url": "https://app.omie.com.br/api/v1/crm/tipos/",
            "description": "Lista os tipos disponíveis de uma oportunidade",
            "methods": {"ListarTipos": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMParceiros": {
            "url": "https://app.omie.com.br/api/v1/crm/parceiros/",
            "description": "Lista dos parceiros e equipes",
            "methods": {"ListarParceiros": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMFinders": {
            "url": "https://app.omie.com.br/api/v1/crm/finders/",
            "description": "Lista dos finders cadastrados",
            "methods": {"ListarFinders": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMOrigens": {
            "url": "https://app.omie.com.br/api/v1/crm/origens/",
            "description": "Lista de origens disponíveis para a oportunidade",
            "methods": {"ListarOrigens": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMConcorrentes": {
            "url": "https://app.omie.com.br/api/v1/crm/concorrentes/",
            "description": "Lista dos concorrentes cadastrados",
            "methods": {"ListarConcorrentes": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMVerticais": {
            "url": "https://app.omie.com.br/api/v1/crm/verticais/",
            "description": "Lista das verticais atendidas",
            "methods": {"ListarVerticais": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CRMTiposTarefas": {
            "url": "https://app.omie.com.br/api/v1/crm/tipostarefa/",
            "description": "Criar/edita/consulta e exclui Tipos de Tarefas",
            "methods": STANDARD_CRUD_METHODS
        },
        
        # Finanças - Auxiliares
        "Bancos": {
            "url": "https://app.omie.com.br/api/v1/geral/bancos/",
            "description": "Lista o cadastro de instituições bancárias",
            "methods": {"ListarBancos": STANDARD_CRUD_METHODS["Listar"]}
        },
        "TiposDocumento": {
            "url": "https://app.omie.com.br/api/v1/geral/tiposdoc/",
            "description": "Lista os tipos de documentos",
            "methods": {"ListarTiposDocumento": STANDARD_CRUD_METHODS["Listar"]}
        },
        "TiposContasCorrentes": {
            "url": "https://app.omie.com.br/api/v1/geral/tipocc/",
            "description": "Lista os tipos de contas correntes",
            "methods": {"ListarTiposContaCorrente": STANDARD_CRUD_METHODS["Listar"]}
        },
        "ContasDRE": {
            "url": "https://app.omie.com.br/api/v1/geral/dre/",
            "description": "Lista as Contas do DRE",
            "methods": {"ListarContasDRE": STANDARD_CRUD_METHODS["Listar"]}
        },
        "FinalidadeTransferencia": {
            "url": "https://app.omie.com.br/api/v1/geral/finaltransf/",
            "description": "Lista as Finalidades de Transferência do CNAB",
            "methods": {"ListarFinalidadeTransferencia": STANDARD_CRUD_METHODS["Listar"]}
        },
        "OrigemLancamento": {
            "url": "https://app.omie.com.br/api/v1/geral/origemlancamento/",
            "description": "Lista as origens dos títulos",
            "methods": {"ListarOrigemLancamento": STANDARD_CRUD_METHODS["Listar"]}
        },
        "BandeirasCartao": {
            "url": "https://app.omie.com.br/api/v1/geral/bandeiracartao/",
            "description": "Lista as Bandeiras de Cartão de débito e crédito",
            "methods": {"ListarBandeirasCartao": STANDARD_CRUD_METHODS["Listar"]}
        },
        "ContasCorrentesLancamentos": {
            "url": "https://app.omie.com.br/api/v1/financas/contacorrentelancamentos/",
            "description": "Cria/edita/consulta lançamentos na conta corrente",
            "methods": STANDARD_CRUD_METHODS
        },
        "ContasReceberBoletos": {
            "url": "https://app.omie.com.br/api/v1/financas/contareceberboleto/",
            "description": "Gera/Obtém/Prorroga e Cancela Boletos de um título a receber",
            "methods": {
                "GerarBoleto": {
                    "param_schema": [
                        {"name": "codigo_lancamento_omie", "type": "integer", "description": "Código do lançamento", "required": False},
                        {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código de integração", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "boleto_request",
                    "response_type": "boleto_response"
                }
            }
        },
        "ContasReceberPIX": {
            "url": "https://app.omie.com.br/api/v1/financas/pix/",
            "description": "Gera um PIX para um contas a receber do Omie.CASH",
            "methods": {
                "GerarPIX": {
                    "param_schema": [
                        {"name": "codigo_lancamento_omie", "type": "integer", "description": "Código do lançamento", "required": False},
                        {"name": "codigo_lancamento_integracao", "type": "string", "description": "Código de integração", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "pix_request",
                    "response_type": "pix_response"
                }
            }
        },
        "OrcamentoCaixa": {
            "url": "https://app.omie.com.br/api/v1/financas/caixa/",
            "description": "Listagem do orçamento de caixa (Previsto x Realizado)",
            "methods": {
                "ListarOrcamentoCaixa": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": True},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": True},
                        {"name": "id_conta_corrente", "type": "integer", "description": "Código da Conta Corrente", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "caixa_request",
                    "response_type": "caixa_response"
                }
            }
        },
        "PesquisarTitulos": {
            "url": "https://app.omie.com.br/api/v1/financas/pesquisartitulos/",
            "description": "Lista de títulos a pagar e receber",
            "methods": {
                "PesquisarTitulos": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": False},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": False},
                        {"name": "tipo", "type": "string", "description": "PAGAR ou RECEBER", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "pesquisar_titulos_request",
                    "response_type": "pesquisar_titulos_response"
                }
            }
        },
        "MovimentosFinanceiros": {
            "url": "https://app.omie.com.br/api/v1/financas/mf/",
            "description": "Consulta de pagamentos, baixas, lançamentos no Conta Corrente",
            "methods": {
                "ConsultarMovimentos": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": True},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": True},
                        {"name": "id_conta_corrente", "type": "integer", "description": "Código da Conta Corrente", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "mf_request",
                    "response_type": "mf_response"
                }
            }
        },
        "ResumoFinancas": {
            "url": "https://app.omie.com.br/api/v1/financas/resumo/",
            "description": "Resumo de Finanças",
            "methods": {
                "ListarResumo": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": True},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "resumo_request",
                    "response_type": "resumo_response"
                }
            }
        },
        
        # Produtos/Compras
        "ProdutosCaracteristicas": {
            "url": "https://app.omie.com.br/api/v1/geral/prodcaract/",
            "description": "Cria/edita/consulta características de um determinado produto",
            "methods": STANDARD_CRUD_METHODS
        },
        "ProdutosEstrutura": {
            "url": "https://app.omie.com.br/api/v1/geral/malha/",
            "description": "Consulta estrutura de um determinado produto",
            "methods": {"ConsultarEstrutura": {
                "param_schema": [
                    {"name": "codigo_produto_omie", "type": "integer", "description": "Código do produto", "required": False},
                    {"name": "codigo_produto_integracao", "type": "string", "description": "Código de integração", "required": False},
                ],
                "default_param": {},
                "request_type": "produto_chave",
                "response_type": "estrutura_response"
            }}
        },
        "ProdutosKit": {
            "url": "https://app.omie.com.br/api/v1/geral/produtoskit/",
            "description": "Edita kit de produtos",
            "methods": {"AlterarKit": STANDARD_CRUD_METHODS["Alterar"]}
        },
        "ProdutosVariacao": {
            "url": "https://app.omie.com.br/api/v1/produtos/variacao/",
            "description": "Cria/consulta/lista variações dos produtos",
            "methods": STANDARD_CRUD_METHODS
        },
        "ProdutosLote": {
            "url": "https://app.omie.com.br/api/v1/produtos/produtoslote/",
            "description": "Consulta/lista lotes dos produtos",
            "methods": {"ListarLotes": STANDARD_CRUD_METHODS["Listar"]}
        },
        "RequisicoesCompra": {
            "url": "https://app.omie.com.br/api/v1/produtos/requisicaocompra/",
            "description": "Cria/edita/consulta requisições de compra",
            "methods": STANDARD_CRUD_METHODS
        },
        "PedidosCompra": {
            "url": "https://app.omie.com.br/api/v1/produtos/pedidocompra/",
            "description": "Cria/edita/consulta pedidos de compra",
            "methods": STANDARD_CRUD_METHODS
        },
        "OrdensProducao": {
            "url": "https://app.omie.com.br/api/v1/produtos/op/",
            "description": "Cria/edita/consulta ordens de produção",
            "methods": STANDARD_CRUD_METHODS
        },
        "NotaEntrada": {
            "url": "https://app.omie.com.br/api/v1/produtos/notaentrada/",
            "description": "Cria/EditaConsulta Notas de Entrada",
            "methods": STANDARD_CRUD_METHODS
        },
        "NotaEntradaFaturamento": {
            "url": "https://app.omie.com.br/api/v1/produtos/notaentradafat/",
            "description": "Operações de faturamento de Notas de Entrada",
            "methods": {
                "FaturarNotaEntrada": {
                    "param_schema": [
                        {"name": "codigo_nota_omie", "type": "integer", "description": "Código da nota", "required": False},
                        {"name": "codigo_nota_integracao", "type": "string", "description": "Código de integração", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "faturamento_request",
                    "response_type": "faturamento_response"
                }
            }
        },
        "RecebimentoNotaFiscal": {
            "url": "https://app.omie.com.br/api/v1/produtos/recebimentonfe/",
            "description": "Edita os dados do Recebimento de uma NF-e",
            "methods": {"AlterarRecebimento": STANDARD_CRUD_METHODS["Alterar"]}
        },
        "ResumoCompras": {
            "url": "https://app.omie.com.br/api/v1/produtos/compras-resumo/",
            "description": "Resumo de compras",
            "methods": {
                "ListarResumo": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": True},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "resumo_request",
                    "response_type": "resumo_response"
                }
            }
        },
        "FamiliasProduto": {
            "url": "https://app.omie.com.br/api/v1/geral/familias/",
            "description": "Cria/edita/consulta famílias de produto",
            "methods": STANDARD_CRUD_METHODS
        },
        "Unidades": {
            "url": "https://app.omie.com.br/api/v1/geral/unidade/",
            "description": "Consulta unidades de medida",
            "methods": {"ListarUnidades": STANDARD_CRUD_METHODS["Listar"]}
        },
        "Compradores": {
            "url": "https://app.omie.com.br/api/v1/estoque/comprador/",
            "description": "Consulta lista de compradores cadastrados",
            "methods": {"ListarCompradores": STANDARD_CRUD_METHODS["Listar"]}
        },
        "ProdutoFornecedor": {
            "url": "https://app.omie.com.br/api/v1/estoque/produtofornecedor/",
            "description": "Lista relação entre produtos e fornecedores",
            "methods": {"ListarProdutoFornecedor": STANDARD_CRUD_METHODS["Listar"]}
        },
        "FormasPagamentoCompras": {
            "url": "https://app.omie.com.br/api/v1/produtos/formaspagcompras/",
            "description": "Lista as opções de forma de pagamento de uma compra",
            "methods": {"ListarFormasPagamento": STANDARD_CRUD_METHODS["Listar"]}
        },
        "NCM": {
            "url": "https://app.omie.com.br/api/v1/produtos/ncm/",
            "description": "Lista/consulta de códigos NCM (Nomenclatura Comum do Mercosul)",
            "methods": {"ListarNCM": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CenariosImpostos": {
            "url": "https://app.omie.com.br/api/v1/geral/cenarios/",
            "description": "Lista os Cenários de Impostos",
            "methods": {"ListarCenarios": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CFOP": {
            "url": "https://app.omie.com.br/api/v1/produtos/cfop/",
            "description": "Lista códigos CFOP",
            "methods": {"ListarCFOP": STANDARD_CRUD_METHODS["Listar"]}
        },
        "ICMSCST": {
            "url": "https://app.omie.com.br/api/v1/produtos/icmscst/",
            "description": "Lista códigos CST do ICMS",
            "methods": {"ListarICMSCST": STANDARD_CRUD_METHODS["Listar"]}
        },
        "ICMSCSOSN": {
            "url": "https://app.omie.com.br/api/v1/produtos/icmscsosn/",
            "description": "Lista códigos CSOSN do ICMS",
            "methods": {"ListarICMSCSOSN": STANDARD_CRUD_METHODS["Listar"]}
        },
        "ICMSOrigem": {
            "url": "https://app.omie.com.br/api/v1/produtos/icmsorigem/",
            "description": "Lista origens da mercadoria para ICMS",
            "methods": {"ListarICMSOrigem": STANDARD_CRUD_METHODS["Listar"]}
        },
        "PISCST": {
            "url": "https://app.omie.com.br/api/v1/produtos/piscst/",
            "description": "Lista códigos CST do PIS",
            "methods": {"ListarPISCST": STANDARD_CRUD_METHODS["Listar"]}
        },
        "COFINSCST": {
            "url": "https://app.omie.com.br/api/v1/produtos/cofinscst/",
            "description": "Lista códigos CST do COFINS",
            "methods": {"ListarCOFINSCST": STANDARD_CRUD_METHODS["Listar"]}
        },
        "IPICST": {
            "url": "https://app.omie.com.br/api/v1/produtos/ipicst/",
            "description": "Lista códigos CST do IPI",
            "methods": {"ListarIPICST": STANDARD_CRUD_METHODS["Listar"]}
        },
        "IPIEnquadramento": {
            "url": "https://app.omie.com.br/api/v1/produtos/ipienq/",
            "description": "Lista enquadramentos do IPI",
            "methods": {"ListarIPIEnquadramento": STANDARD_CRUD_METHODS["Listar"]}
        },
        "TipoCalculo": {
            "url": "https://app.omie.com.br/api/v1/produtos/tpcalc/",
            "description": "Lista tipos de cálculo",
            "methods": {"ListarTipoCalculo": STANDARD_CRUD_METHODS["Listar"]}
        },
        "CEST": {
            "url": "https://app.omie.com.br/api/v1/produtos/cest/",
            "description": "Lista códigos CEST",
            "methods": {"ListarCEST": STANDARD_CRUD_METHODS["Listar"]}
        },
        "AjustesEstoque": {
            "url": "https://app.omie.com.br/api/v1/estoque/ajuste/",
            "description": "Cria/exclui movimentações do estoque",
            "methods": {
                "IncluirAjuste": {
                    "param_schema": [
                        {"name": "codigo_produto_omie", "type": "integer", "description": "Código do produto", "required": True},
                        {"name": "quantidade", "type": "decimal", "description": "Quantidade a ajustar", "required": True},
                        {"name": "tipo", "type": "string", "description": "ENTRADA ou SAIDA", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "ajuste_request",
                    "response_type": "ajuste_response"
                },
                "ExcluirAjuste": STANDARD_CRUD_METHODS["Excluir"]
            }
        },
        "ConsultaEstoque": {
            "url": "https://app.omie.com.br/api/v1/estoque/consulta/",
            "description": "Consulta consolidada do estoque do produto",
            "methods": {
                "ConsultarEstoque": {
                    "param_schema": [
                        {"name": "codigo_produto_omie", "type": "integer", "description": "Código do produto", "required": False},
                        {"name": "codigo_produto_integracao", "type": "string", "description": "Código de integração", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "produto_chave",
                    "response_type": "estoque_response"
                }
            }
        },
        "MovimentoEstoque": {
            "url": "https://app.omie.com.br/api/v1/estoque/movestoque/",
            "description": "Lista os movimentos de estoque de entrada/saida por período",
            "methods": {
                "ListarMovimentos": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": True},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": True},
                        {"name": "codigo_produto_omie", "type": "integer", "description": "Código do produto", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "movimento_request",
                    "response_type": "movimento_response"
                }
            }
        },
        "LocaisEstoque": {
            "url": "https://app.omie.com.br/api/v1/estoque/local/",
            "description": "Listagem dos Locais de Estoque",
            "methods": {"ListarLocais": STANDARD_CRUD_METHODS["Listar"]}
        },
        "ResumoEstoque": {
            "url": "https://app.omie.com.br/api/v1/estoque/resumo/",
            "description": "Resumo do Estoque de um produto",
            "methods": {
                "ListarResumo": {
                    "param_schema": [
                        {"name": "codigo_produto_omie", "type": "integer", "description": "Código do produto", "required": False},
                        {"name": "codigo_produto_integracao", "type": "string", "description": "Código de integração", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "produto_chave",
                    "response_type": "resumo_response"
                }
            }
        },
        
        # Vendas
        "PedidosVendaResumido": {
            "url": "https://app.omie.com.br/api/v1/produtos/pedidovenda/",
            "description": "Adiciona pedidos e itens de venda de produto",
            "methods": {
                "IncluirPedidoResumido": {
                    "param_schema": [],
                    "default_param": {},
                    "request_type": "pedido_resumido_request",
                    "response_type": "pedido_response"
                }
            }
        },
        "PedidosVenda": {
            "url": "https://app.omie.com.br/api/v1/produtos/pedido/",
            "description": "Cria/edita/consulta pedidos e orçamentos",
            "methods": STANDARD_CRUD_METHODS
        },
        "PedidosVendaFaturamento": {
            "url": "https://app.omie.com.br/api/v1/produtos/pedidovendafat/",
            "description": "Operações de faturamento de pedido",
            "methods": {
                "FaturarPedido": {
                    "param_schema": [
                        {"name": "codigo_pedido_omie", "type": "integer", "description": "Código do pedido", "required": False},
                        {"name": "codigo_pedido_integracao", "type": "string", "description": "Código de integração", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "faturamento_request",
                    "response_type": "faturamento_response"
                }
            }
        },
        "PedidosVendaEtapas": {
            "url": "https://app.omie.com.br/api/v1/produtos/pedidoetapas/",
            "description": "Consulta das etapas de pedido",
            "methods": {
                "ConsultarEtapas": {
                    "param_schema": [
                        {"name": "codigo_pedido_omie", "type": "integer", "description": "Código do pedido", "required": False},
                        {"name": "codigo_pedido_integracao", "type": "string", "description": "Código de integração", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "pedido_chave",
                    "response_type": "etapas_response"
                }
            }
        },
        "CTe": {
            "url": "https://app.omie.com.br/api/v1/produtos/cte/",
            "description": "Adiciona/Cancela Conhecimento de Transporte",
            "methods": {
                "IncluirCTe": {
                    "param_schema": [],
                    "default_param": {},
                    "request_type": "cte_request",
                    "response_type": "cte_response"
                },
                "CancelarCTe": {
                    "param_schema": [
                        {"name": "chave_cte", "type": "string", "description": "Chave do CT-e", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "cancelar_request",
                    "response_type": "cancelar_response"
                }
            }
        },
        "RemessaProdutos": {
            "url": "https://app.omie.com.br/api/v1/produtos/remessa/",
            "description": "Cria/edita uma NF de remessa de produto",
            "methods": STANDARD_CRUD_METHODS
        },
        "RemessaProdutosFaturamento": {
            "url": "https://app.omie.com.br/api/v1/produtos/remessafat/",
            "description": "Operações de faturamento da Remessa",
            "methods": {
                "FaturarRemessa": {
                    "param_schema": [
                        {"name": "codigo_remessa_omie", "type": "integer", "description": "Código da remessa", "required": False},
                        {"name": "codigo_remessa_integracao", "type": "string", "description": "Código de integração", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "faturamento_request",
                    "response_type": "faturamento_response"
                }
            }
        },
        "ResumoVendas": {
            "url": "https://app.omie.com.br/api/v1/produtos/vendas-resumo/",
            "description": "Resumo de vendas de NF-e, CT-e e Cupom Fiscal",
            "methods": {
                "ListarResumo": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": True},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "resumo_request",
                    "response_type": "resumo_response"
                }
            }
        },
        "ObterDocumentos": {
            "url": "https://app.omie.com.br/api/v1/produtos/dfedocs/",
            "description": "Disponibiliza PDF e XML de documentos fiscais (NF-e, NFC-e, CT-e, etc)",
            "methods": {
                "ObterDocumento": {
                    "param_schema": [
                        {"name": "chave_nfe", "type": "string", "description": "Chave da NF-e", "required": False},
                        {"name": "tipo_documento", "type": "string", "description": "PDF ou XML", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "documento_request",
                    "response_type": "documento_response"
                }
            }
        },
        "FormasPagamentoVendas": {
            "url": "https://app.omie.com.br/api/v1/produtos/formaspagvendas/",
            "description": "Lista as formas de pagamento de um pedido de venda",
            "methods": {"ListarFormasPagamento": STANDARD_CRUD_METHODS["Listar"]}
        },
        "TabelaPrecos": {
            "url": "https://app.omie.com.br/api/v1/produtos/tabelaprecos/",
            "description": "Cria/edita/consulta tabelas de preço usadas no pedido de venda",
            "methods": STANDARD_CRUD_METHODS
        },
        "CaracteristicasProdutos": {
            "url": "https://app.omie.com.br/api/v1/geral/caracteristicas/",
            "description": "Cria/edita/consulta características que serão usadas nos produtos",
            "methods": STANDARD_CRUD_METHODS
        },
        "EtapasFaturamento": {
            "url": "https://app.omie.com.br/api/v1/produtos/etapafat/",
            "description": "Lista as etapas do faturamento",
            "methods": {"ListarEtapas": STANDARD_CRUD_METHODS["Listar"]}
        },
        "MeiosPagamento": {
            "url": "https://app.omie.com.br/api/v1/geral/meiospagamento/",
            "description": "Listagem de meios de pagamentos (parcelas)",
            "methods": {"ListarMeiosPagamento": STANDARD_CRUD_METHODS["Listar"]}
        },
        "OrigemPedido": {
            "url": "https://app.omie.com.br/api/v1/geral/origempedido/",
            "description": "Lista as origens de pedidos disponíveis",
            "methods": {"ListarOrigens": STANDARD_CRUD_METHODS["Listar"]}
        },
        "MotivosDevolucao": {
            "url": "https://app.omie.com.br/api/v1/geral/motivodevolucao/",
            "description": "Lista os Motivos de Devolução",
            "methods": {"ListarMotivos": STANDARD_CRUD_METHODS["Listar"]}
        },
        "ConsultasNFE": {
            "url": "https://app.omie.com.br/api/v1/produtos/nfconsultar/",
            "description": "Lista de NF-e emitidas",
            "methods": {
                "ListarNFE": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": False},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": False},
                        {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                        {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros", "required": False, "default": 50},
                    ],
                    "default_param": {"pagina": 1, "registros_por_pagina": 50},
                    "request_type": "nf_consultar_request",
                    "response_type": "nf_consultar_response"
                }
            }
        },
        "UtilitariosNFE": {
            "url": "https://app.omie.com.br/api/v1/produtos/notafiscalutil/",
            "description": "Recupera URL da NF-e (XML), do Danfe ou do logotipo da empresa",
            "methods": {
                "ObterURL": {
                    "param_schema": [
                        {"name": "chave_nfe", "type": "string", "description": "Chave da NF-e", "required": False},
                        {"name": "tipo", "type": "string", "description": "XML, DANFE ou LOGOTIPO", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "util_request",
                    "response_type": "util_response"
                }
            }
        },
        "ImportarNFE": {
            "url": "https://app.omie.com.br/api/v1/produtos/nfe/",
            "description": "Importação de XML de NF-e",
            "methods": {
                "ImportarXML": {
                    "param_schema": [
                        {"name": "xml", "type": "text", "description": "Conteúdo XML da NF-e", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "importar_request",
                    "response_type": "importar_response"
                }
            }
        },
        "AdicionarCupomFiscal": {
            "url": "https://app.omie.com.br/api/v1/produtos/cupomfiscalincluir/",
            "description": "Adicionar cupom fiscal/NFC-e/CF-e SAT",
            "methods": {
                "IncluirCupom": {
                    "param_schema": [],
                    "default_param": {},
                    "request_type": "cupom_request",
                    "response_type": "cupom_response"
                }
            }
        },
        "CancelarCupomFiscal": {
            "url": "https://app.omie.com.br/api/v1/produtos/cupomfiscal/",
            "description": "Cancelar/excluir/inutilizar cupons fiscais",
            "methods": {
                "CancelarCupom": {
                    "param_schema": [
                        {"name": "chave_cupom", "type": "string", "description": "Chave do cupom", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "cancelar_request",
                    "response_type": "cancelar_response"
                }
            }
        },
        "ConsultarCupomFiscal": {
            "url": "https://app.omie.com.br/api/v1/produtos/cupomfiscalconsultar/",
            "description": "Consultas de Cupom Fiscal",
            "methods": {
                "ConsultarCupom": {
                    "param_schema": [
                        {"name": "chave_cupom", "type": "string", "description": "Chave do cupom", "required": False},
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": False},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "consultar_request",
                    "response_type": "consultar_response"
                }
            }
        },
        "ImportarNFCE": {
            "url": "https://app.omie.com.br/api/v1/produtos/nfce/",
            "description": "Importação de XML de NFC-e",
            "methods": {
                "ImportarXML": {
                    "param_schema": [
                        {"name": "xml", "type": "text", "description": "Conteúdo XML da NFC-e", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "importar_request",
                    "response_type": "importar_response"
                }
            }
        },
        "ImportarCFESAT": {
            "url": "https://app.omie.com.br/api/v1/produtos/sat/",
            "description": "Importação de XML de CFe-Sat",
            "methods": {
                "ImportarXML": {
                    "param_schema": [
                        {"name": "xml", "type": "text", "description": "Conteúdo XML do CFe-Sat", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "importar_request",
                    "response_type": "importar_response"
                }
            }
        },
        
        # Serviços
        "Servicos": {
            "url": "https://app.omie.com.br/api/v1/servicos/servico/",
            "description": "Cria/edita/consulta serviços prestados pela empresa",
            "methods": {
                "ListarCadastroServico": {
                    "param_schema": [
                        {"name": "nPagina", "type": "integer", "description": "Número da página retornada", "required": False, "default": 1},
                        {"name": "nRegPorPagina", "type": "integer", "description": "Número de registros retornados na página", "required": False, "default": 20},
                        {"name": "cOrdenarPor", "type": "string", "description": "Ordem de exibição (padrão: Código)", "required": False},
                        {"name": "cOrdemDecrescente", "type": "string", "description": "Ordem decrescente (S/N)", "required": False},
                        {"name": "dInclusaoInicial", "type": "string", "description": "Data da Inclusão Inicial (dd/mm/aaaa)", "required": False},
                        {"name": "dInclusaoFinal", "type": "string", "description": "Data da Inclusão final (dd/mm/aaaa)", "required": False},
                        {"name": "dAlteracaoInicial", "type": "string", "description": "Data da Alteração Inicial (dd/mm/aaaa)", "required": False},
                        {"name": "dAlteracaoFinal", "type": "string", "description": "Data da Alteração final (dd/mm/aaaa)", "required": False},
                        {"name": "cDescricao", "type": "string", "description": "Descrição resumida do serviço", "required": False},
                        {"name": "cCodigo", "type": "string", "description": "Código do Serviço", "required": False},
                        {"name": "inativo", "type": "string", "description": "Serviço inativo (S/N)", "required": False},
                        {"name": "cExibirProdutos", "type": "string", "description": "Exibir produtos utilizados (S/N)", "required": False},
                    ],
                    "default_param": {"nPagina": 1, "nRegPorPagina": 20},
                    "request_type": "srvListarRequest",
                    "response_type": "srvListarResponse"
                },
                "ConsultarCadastroServico": {
                    "param_schema": [
                        {"name": "cCodIntServ", "type": "string", "description": "Código de Integração do Serviço", "required": False},
                        {"name": "nCodServ", "type": "integer", "description": "Código do serviço no Omie", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "srvConsultarRequest",
                    "response_type": "srvConsultarResponse"
                },
                "IncluirCadastroServico": {
                    "param_schema": [
                        {"name": "cCodIntServ", "type": "string", "description": "Código de Integração", "required": True},
                        {"name": "cDescrCompleta", "type": "text", "description": "Descrição completa do serviço", "required": True},
                        {"name": "cDescricao", "type": "string", "description": "Descrição resumida", "required": True},
                        {"name": "cCodigo", "type": "string", "description": "Código do Serviço", "required": False},
                        {"name": "cIdTrib", "type": "string", "description": "ID da Tributação", "required": False},
                        {"name": "cCodServMun", "type": "string", "description": "Código do Serviço Municipal", "required": False},
                        {"name": "cCodLC116", "type": "string", "description": "Código LC 116", "required": False},
                        {"name": "nIdNBS", "type": "string", "description": "Id do NBS", "required": False},
                        {"name": "nPrecoUnit", "type": "decimal", "description": "Preço Unitário", "required": False},
                        {"name": "cCodCateg", "type": "string", "description": "Código da Categoria", "required": False},
                        {"name": "nAliqISS", "type": "decimal", "description": "Alíquota ISS", "required": False},
                        {"name": "cRetISS", "type": "string", "description": "Retém ISS (S/N)", "required": False, "default": "N"},
                        {"name": "nAliqPIS", "type": "decimal", "description": "Alíquota PIS", "required": False},
                        {"name": "cRetPIS", "type": "string", "description": "Retém PIS (S/N)", "required": False, "default": "N"},
                        {"name": "nAliqCOFINS", "type": "decimal", "description": "Alíquota COFINS", "required": False},
                        {"name": "cRetCOFINS", "type": "string", "description": "Retém COFINS (S/N)", "required": False, "default": "N"},
                        {"name": "nAliqCSLL", "type": "decimal", "description": "Alíquota CSLL", "required": False},
                        {"name": "cRetCSLL", "type": "string", "description": "Retém CSLL (S/N)", "required": False, "default": "N"},
                        {"name": "nAliqIR", "type": "decimal", "description": "Alíquota IR", "required": False},
                        {"name": "cRetIR", "type": "string", "description": "Retém IR (S/N)", "required": False, "default": "N"},
                        {"name": "nAliqINSS", "type": "decimal", "description": "Alíquota INSS", "required": False},
                        {"name": "cRetINSS", "type": "string", "description": "Retém INSS (S/N)", "required": False, "default": "N"},
                    ],
                    "default_param": {"cRetISS": "N", "cRetPIS": "N", "cRetCOFINS": "N", "cRetCSLL": "N", "cRetIR": "N", "cRetINSS": "N"},
                    "request_type": "srvIncluirRequest",
                    "response_type": "srvIncluirResponse"
                },
                "AlterarCadastroServico": {
                    "param_schema": [
                        {"name": "cCodIntServ", "type": "string", "description": "Código de Integração", "required": False},
                        {"name": "nCodServ", "type": "integer", "description": "Código do serviço no Omie", "required": False},
                        {"name": "cDescrCompleta", "type": "text", "description": "Descrição completa", "required": False},
                        {"name": "cDescricao", "type": "string", "description": "Descrição resumida", "required": False},
                        {"name": "cCodigo", "type": "string", "description": "Código do Serviço", "required": False},
                        {"name": "nPrecoUnit", "type": "decimal", "description": "Preço Unitário", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "srvEditarRequest",
                    "response_type": "srvEditarResponse"
                },
                "ExcluirCadastroServico": {
                    "param_schema": [
                        {"name": "cCodIntServ", "type": "string", "description": "Código de Integração", "required": False},
                        {"name": "nCodServ", "type": "integer", "description": "Código do serviço no Omie", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "srvExcluirRequest",
                    "response_type": "srvExcluirResponse"
                },
                "UpsertCadastroServico": {
                    "param_schema": [
                        {"name": "cCodIntServ", "type": "string", "description": "Código de Integração", "required": False},
                        {"name": "nCodServ", "type": "integer", "description": "Código no Omie", "required": False},
                        {"name": "cDescricao", "type": "string", "description": "Descrição resumida", "required": True},
                        {"name": "cCodigo", "type": "string", "description": "Código do Serviço", "required": False},
                        {"name": "nPrecoUnit", "type": "decimal", "description": "Preço Unitário", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "srvUpsertRequest",
                    "response_type": "srvUpsertResponse"
                },
                "AssociarCodIntServico": {
                    "param_schema": [
                        {"name": "nCodServ", "type": "integer", "description": "Código do serviço no Omie", "required": False},
                        {"name": "cCodIntServ", "type": "string", "description": "Código de Integração a associar", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "srvAssociarRequest",
                    "response_type": "srvAssociarResponse"
                },
            }
        },
        "OrdensServico": {
            "url": "https://app.omie.com.br/api/v1/servicos/os/",
            "description": "Cria/edita/consulta uma ordem de serviço",
            "methods": {
                "ListarOS": {
                    "param_schema": [
                        {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                        {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 50},
                        {"name": "apenas_importado_api", "type": "string", "description": "Apenas da API (S/N)", "required": False, "default": "N"},
                        {"name": "ordenar_por", "type": "string", "description": "Ordem de exibição (padrão: Código)", "required": False},
                        {"name": "ordem_decrescente", "type": "string", "description": "Ordem decrescente (S/N)", "required": False},
                        {"name": "ordem_descrescente", "type": "string", "description": "Ordem decrescente (S/N) [alt]", "required": False},
                        {"name": "filtrar_por_data_de", "type": "string", "description": "Data inclusão/alteração inicial (dd/mm/aaaa)", "required": False},
                        {"name": "filtrar_por_data_ate", "type": "string", "description": "Data inclusão/alteração final (dd/mm/aaaa)", "required": False},
                        {"name": "filtrar_apenas_inclusao", "type": "string", "description": "Filtrar apenas incluídos (S/N)", "required": False},
                        {"name": "filtrar_apenas_alteracao", "type": "string", "description": "Filtrar apenas alterados (S/N)", "required": False},
                        {"name": "filtrar_por_status", "type": "string", "description": "F-Faturada, N-Não faturada, C-Cancelada", "required": False},
                        {"name": "filtrar_por_etapa", "type": "string", "description": "10, 20, 30, 40, 50", "required": False},
                        {"name": "filtrar_por_cliente", "type": "integer", "description": "ID do cliente", "required": False},
                        {"name": "filtrar_por_data_previsao_de", "type": "string", "description": "Data previsão inicial (dd/mm/aaaa)", "required": False},
                        {"name": "filtrar_por_data_previsao_ate", "type": "string", "description": "Data previsão final (dd/mm/aaaa)", "required": False},
                        {"name": "filtrar_por_data_faturamento_de", "type": "string", "description": "Data faturamento inicial (dd/mm/aaaa)", "required": False},
                        {"name": "filtrar_por_data_faturamento_ate", "type": "string", "description": "Data faturamento final (dd/mm/aaaa)", "required": False},
                        {"name": "filtrar_por_data_cancelamento_de", "type": "string", "description": "Data cancelamento inicial (dd/mm/aaaa)", "required": False},
                        {"name": "filtrar_por_data_cancelamento_ate", "type": "string", "description": "Data cancelamento final (dd/mm/aaaa)", "required": False},
                        {"name": "cExibirDespesas", "type": "string", "description": "Exibir despesas reembolsáveis (S/N)", "required": False},
                        {"name": "cExibirProdutos", "type": "string", "description": "Exibir produtos utilizados (S/N)", "required": False},
                        {"name": "cTipoFat", "type": "string", "description": "REC, NFS, VUF, VUA", "required": False},
                    ],
                    "default_param": {"pagina": 1, "registros_por_pagina": 50, "apenas_importado_api": "N"},
                    "request_type": "osListarRequest",
                    "response_type": "osListarResponse"
                },
                "ConsultarOS": {
                    "param_schema": [
                        {"name": "cCodIntOS", "type": "string", "description": "Código de Integração da OS", "required": False},
                        {"name": "nCodOS", "type": "integer", "description": "Código da Ordem de Serviço", "required": False},
                        {"name": "cNumOS", "type": "string", "description": "Número da OS (conforme tela)", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "osChave",
                    "response_type": "osCadastro"
                },
                "IncluirOS": {
                    "param_schema": [
                        {"name": "cCodIntOS", "type": "string", "description": "Código de Integração da OS", "required": True},
                        {"name": "cCodParc", "type": "string", "description": "Código parcela/condição pagamento (API formaspagvendas)", "required": True},
                        {"name": "cEtapa", "type": "string", "description": "10, 20, 30, 40, 50", "required": False},
                        {"name": "dDtPrevisao", "type": "string", "description": "Data de previsão (dd/mm/aaaa)", "required": True},
                        {"name": "nCodCli", "type": "integer", "description": "Código do cliente", "required": True},
                        {"name": "nQtdeParc", "type": "integer", "description": "Quantidade de parcelas", "required": False},
                        {"name": "cCodCateg", "type": "string", "description": "Categoria", "required": False},
                        {"name": "nCodCC", "type": "integer", "description": "Conta corrente", "required": False},
                        {"name": "cCidPrestServ", "type": "string", "description": "Cidade da prestação", "required": False},
                        {"name": "cDadosAdicNF", "type": "text", "description": "Dados adicionais NF", "required": False},
                        {"name": "cEnviarPara", "type": "string", "description": "E-mail para envio", "required": False},
                        {"name": "ServicosPrestados", "type": "array", "description": "Lista de serviços (nCodServico/nCodIntServico, cTribServ, cCodServMun, cCodServLC116, nQtde, nValUnit, cDescServ, etc.)", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "osCadastro",
                    "response_type": "osStatus"
                },
                "AlterarOS": {
                    "param_schema": [
                        {"name": "nCodOS", "type": "integer", "description": "Código da OS", "required": False},
                        {"name": "cCodIntOS", "type": "string", "description": "Código de Integração", "required": False},
                        {"name": "cNumOS", "type": "string", "description": "Número da OS", "required": False},
                        {"name": "dDtPrevisao", "type": "string", "description": "Data previsão (dd/mm/aaaa)", "required": False},
                        {"name": "cEtapa", "type": "string", "description": "Etapa 10-50", "required": False},
                        {"name": "ServicosPrestados", "type": "array", "description": "Serviços (nSeqItem, cAcaoItem A/E/I)", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "osCadastro",
                    "response_type": "osStatus"
                },
                "ExcluirOS": {
                    "param_schema": [
                        {"name": "cCodIntOS", "type": "string", "description": "Código de Integração da OS", "required": False},
                        {"name": "nCodOS", "type": "integer", "description": "Código da Ordem de Serviço", "required": False},
                        {"name": "cNumOS", "type": "string", "description": "Número da OS", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "osChave",
                    "response_type": "osStatus"
                },
                "StatusOS": {
                    "param_schema": [
                        {"name": "cCodIntOS", "type": "string", "description": "Código de Integração da OS", "required": False},
                        {"name": "nCodOS", "type": "integer", "description": "Código da Ordem de Serviço", "required": False},
                        {"name": "lPdfDemo", "type": "boolean", "description": "Exibir URL PDF Demonstrativo NFS-e", "required": False, "default": False},
                        {"name": "lPdfDest", "type": "boolean", "description": "Exibir URL PDF Destinatário", "required": False, "default": False},
                        {"name": "lRps", "type": "boolean", "description": "Exibir URL da RPS", "required": False, "default": False},
                        {"name": "lPdfRecibo", "type": "boolean", "description": "Exibir URL do Recibo", "required": False, "default": False},
                        {"name": "lMsg", "type": "boolean", "description": "Retornar todas mensagens prefeitura (S/N)", "required": False, "default": False},
                    ],
                    "default_param": {},
                    "request_type": "osStatusRequest",
                    "response_type": "osStatusResponse"
                },
                "TrocarEtapaOS": {
                    "param_schema": [
                        {"name": "nCodOS", "type": "integer", "description": "Código da Ordem de Serviço", "required": False},
                        {"name": "cCodIntOS", "type": "string", "description": "Código de Integração da OS", "required": False},
                        {"name": "cNumOS", "type": "string", "description": "Número da OS", "required": False},
                        {"name": "cEtapa", "type": "string", "description": "10, 20, 30, 40 ou 50", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "osTrocarEtapaRequest",
                    "response_type": "osTrocarEtapaResponse"
                },
            }
        },
        "OrdensServicoFaturamento": {
            "url": "https://app.omie.com.br/api/v1/servicos/osp/",
            "description": "Operações de faturamento de OS",
            "methods": {
                "FaturarOS": {
                    "param_schema": [
                        {"name": "codigo_os_omie", "type": "integer", "description": "Código da OS", "required": False},
                        {"name": "codigo_os_integracao", "type": "string", "description": "Código de integração", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "faturamento_request",
                    "response_type": "faturamento_response"
                }
            }
        },
        "OrdensServicoFaturamentoLote": {
            "url": "https://app.omie.com.br/api/v1/servicos/oslote/",
            "description": "Faturamento de Ordens de Serviço em Lote",
            "methods": {
                "FaturarOSLote": {
                    "param_schema": [
                        {"name": "lote", "type": "integer", "description": "Número do lote", "required": True},
                        {"name": "codigos_os", "type": "array", "description": "Lista de códigos de OS", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "lote_request",
                    "response_type": "lote_response"
                }
            }
        },
        "ContratosServico": {
            "url": "https://app.omie.com.br/api/v1/servicos/contrato/",
            "description": "Cria/edita/consulta contratos de serviço (recorrência)",
            "methods": STANDARD_CRUD_METHODS
        },
        "ContratosServicoFaturamento": {
            "url": "https://app.omie.com.br/api/v1/servicos/contratofat/",
            "description": "Operações de faturamento do Contrato de Serviço",
            "methods": {
                "FaturarContrato": {
                    "param_schema": [
                        {"name": "codigo_contrato_omie", "type": "integer", "description": "Código do contrato", "required": False},
                        {"name": "codigo_contrato_integracao", "type": "string", "description": "Código de integração", "required": False},
                    ],
                    "default_param": {},
                    "request_type": "faturamento_request",
                    "response_type": "faturamento_response"
                }
            }
        },
        "ContratosServicoFaturamentoLote": {
            "url": "https://app.omie.com.br/api/v1/servicos/contratolote/",
            "description": "Faturamento de Contratos de Serviço em Lote",
            "methods": {
                "FaturarContratoLote": {
                    "param_schema": [
                        {"name": "lote", "type": "integer", "description": "Número do lote", "required": True},
                        {"name": "codigos_contrato", "type": "array", "description": "Lista de códigos de contrato", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "lote_request",
                    "response_type": "lote_response"
                }
            }
        },
        "ResumoServicos": {
            "url": "https://app.omie.com.br/api/v1/servicos/resumo/",
            "description": "Resumo do Faturamento de Serviços",
            "methods": {
                "ListarResumo": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": True},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "resumo_request",
                    "response_type": "resumo_response"
                }
            }
        },
        "ObterDocumentosServicos": {
            "url": "https://app.omie.com.br/api/v1/servicos/osdocs/",
            "description": "Disponibiliza PDF e XML de documentos fiscais (NFS-e, Recibo, Via Única, etc)",
            "methods": {
                "ObterDocumento": {
                    "param_schema": [
                        {"name": "codigo_os_omie", "type": "integer", "description": "Código da OS", "required": False},
                        {"name": "codigo_os_integracao", "type": "string", "description": "Código de integração", "required": False},
                        {"name": "tipo_documento", "type": "string", "description": "PDF ou XML", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "documento_request",
                    "response_type": "documento_response"
                }
            }
        },
        "ConsultasNFSE": {
            "url": "https://app.omie.com.br/api/v1/servicos/nfse/",
            "description": "Listagem de NFS-e emitidas",
            "methods": {
                "ListarNFSE": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": False},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": False},
                        {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                        {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros", "required": False, "default": 50},
                    ],
                    "default_param": {"pagina": 1, "registros_por_pagina": 50},
                    "request_type": "nfse_consultar_request",
                    "response_type": "nfse_consultar_response"
                }
            }
        },
        "ServicosMunicipio": {
            "url": "https://app.omie.com.br/api/v1/servicos/listaservico/",
            "description": "Lista serviços disponíveis para o município",
            "methods": {
                "ListarServicosMunicipio": {
                    "param_schema": [
                        {"name": "codigo_municipio", "type": "string", "description": "Código do município", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "municipio_request",
                    "response_type": "municipio_response"
                }
            }
        },
        "TiposTributacao": {
            "url": "https://app.omie.com.br/api/v1/servicos/tipotrib/",
            "description": "Lista os tipos de tributação",
            "methods": {"ListarTiposTributacao": STANDARD_CRUD_METHODS["Listar"]}
        },
        "LC116": {
            "url": "https://app.omie.com.br/api/v1/servicos/lc116/",
            "description": "Lista os códigos da Lei Complementar 116",
            "methods": {"ListarLC116": STANDARD_CRUD_METHODS["Listar"]}
        },
        "NBS": {
            "url": "https://app.omie.com.br/api/v1/servicos/nbs/",
            "description": "Lista os códigos de Nomenclatura Brasileira Serviços (NBS)",
            "methods": {"ListarNBS": STANDARD_CRUD_METHODS["Listar"]}
        },
        "IBPT": {
            "url": "https://app.omie.com.br/api/v1/servicos/ibpt/",
            "description": "Lista de impostos definidos na tabela do IBPT",
            "methods": {"ListarIBPT": STANDARD_CRUD_METHODS["Listar"]}
        },
        "TipoFaturamentoContrato": {
            "url": "https://app.omie.com.br/api/v1/servicos/contratotpfat/",
            "description": "Lista os tipos de faturamento de contratos",
            "methods": {"ListarTiposFaturamento": STANDARD_CRUD_METHODS["Listar"]}
        },
        "TipoUtilizacao": {
            "url": "https://app.omie.com.br/api/v1/servicos/tipoutilizacao/",
            "description": "Lista os Tipos de utilização",
            "methods": {"ListarTiposUtilizacao": STANDARD_CRUD_METHODS["Listar"]}
        },
        "ClassificacaoServico": {
            "url": "https://app.omie.com.br/api/v1/servicos/classificacaoservico/",
            "description": "Lista as Classificações do Serviço",
            "methods": {"ListarClassificacoes": STANDARD_CRUD_METHODS["Listar"]}
        },
        
        # Contador
        "DocumentosFiscais": {
            "url": "https://app.omie.com.br/api/v1/contador/xml/",
            "description": "Listagem dos XMLs de Documentos Fiscais (NF-e/NFC-e/CF-e SAT/NFS-e)",
            "methods": {
                "ListarDocumentos": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": False},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": False},
                        {"name": "tipo_documento", "type": "string", "description": "NFE, NFCE, CFE_SAT, NFSE", "required": False},
                        {"name": "pagina", "type": "integer", "description": "Número da página", "required": False, "default": 1},
                        {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros", "required": False, "default": 50},
                    ],
                    "default_param": {"pagina": 1, "registros_por_pagina": 50},
                    "request_type": "documentos_request",
                    "response_type": "documentos_response"
                }
            }
        },
        "ResumoContador": {
            "url": "https://app.omie.com.br/api/v1/contador/resumo/",
            "description": "Resumo do Fechamento Contábil",
            "methods": {
                "ListarResumo": {
                    "param_schema": [
                        {"name": "data_inicial", "type": "string", "description": "Data inicial (dd/mm/aaaa)", "required": True},
                        {"name": "data_final", "type": "string", "description": "Data final (dd/mm/aaaa)", "required": True},
                    ],
                    "default_param": {},
                    "request_type": "resumo_request",
                    "response_type": "resumo_response"
                }
            }
        },
}

# Merge additional endpoints into main dict (defined above)
OMIE_API_ENDPOINTS.update(additional_endpoints)


def get_all_endpoints_list():
    """
    Returns a simple list format: [(name, url, description), ...]
    Compatible with the original format.
    """
    result = []
    for name, data in OMIE_API_ENDPOINTS.items():
        result.append((name, data["url"], data["description"]))
    return result


def get_endpoint_methods(endpoint_name):
    """
    Get all available methods for an endpoint.
    
    Returns: dict of {method_name: {param_schema, default_param, ...}}
    """
    endpoint = OMIE_API_ENDPOINTS.get(endpoint_name)
    if not endpoint:
        return {}
    return endpoint.get("methods", {})


def get_method_params(endpoint_name, method_name):
    """
    Get parameter schema and defaults for a specific method.
    
    Returns: {
        "param_schema": [...],
        "default_param": {...},
        "request_type": "...",
        "response_type": "..."
    }
    """
    methods = get_endpoint_methods(endpoint_name)
    return methods.get(method_name, {})
