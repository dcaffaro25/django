"""
Seed Omie provider and ListarContasPagar API definition.

Usage:
    python manage.py seed_omie_api
"""

from django.core.management.base import BaseCommand

from erp_integrations.models import ERPAPIDefinition, ERPProvider


# lcpListarRequest params from https://app.omie.com.br/api/v1/financas/contapagar/#lcpListarRequest
LISTAR_CONTAS_PAGAR_PARAM_SCHEMA = [
    {"name": "pagina", "type": "integer", "description": "Número da página que será listada.", "required": False, "default": 1},
    {"name": "registros_por_pagina", "type": "integer", "description": "Número de registros retornados", "required": False, "default": 1000},
    {"name": "apenas_importado_api", "type": "string", "description": "Exibir apenas os registros gerados pela API. S ou N.", "required": False, "default": "N"},
    {"name": "ordenar_por", "type": "string", "description": "CODIGO ou CODIGO_INTEGRACAO", "required": False, "default": "CODIGO"},
    {"name": "ordem_descrescente", "type": "string", "description": "S ou N", "required": False, "default": "N"},
    {"name": "filtrar_por_data_de", "type": "string", "description": "Data inicial dd/mm/aaaa", "required": False},
    {"name": "filtrar_por_data_ate", "type": "string", "description": "Data final dd/mm/aaaa", "required": False},
    {"name": "filtrar_apenas_inclusao", "type": "string", "description": "S ou N", "required": False, "default": "N"},
    {"name": "filtrar_apenas_alteracao", "type": "string", "description": "S ou N", "required": False, "default": "N"},
    {"name": "filtrar_por_emissao_de", "type": "string", "description": "dd/mm/aaaa", "required": False},
    {"name": "filtrar_por_emissao_ate", "type": "string", "description": "dd/mm/aaaa", "required": False},
    {"name": "filtrar_por_registro_de", "type": "string", "description": "Filtra registros a partir da data", "required": False},
    {"name": "filtrar_por_registro_ate", "type": "string", "description": "Filtra registros até a data", "required": False},
    {"name": "filtrar_conta_corrente", "type": "integer", "description": "Código conta corrente", "required": False},
    {"name": "filtrar_cliente", "type": "integer", "description": "Código cliente Omie", "required": False},
    {"name": "filtrar_por_cpf_cnpj", "type": "string", "description": "CPF/CNPJ (apenas números)", "required": False},
    {"name": "filtrar_por_status", "type": "string", "description": "CANCELADO, PAGO, LIQUIDADO, EMABERTO, PAGTO_PARCIAL, VENCEHOJE, AVENCER, ATRASADO", "required": False},
    {"name": "filtrar_por_projeto", "type": "integer", "description": "Código projeto", "required": False},
    {"name": "filtrar_por_vendedor", "type": "integer", "description": "Código vendedor", "required": False},
    {"name": "exibir_obs", "type": "string", "description": "Exibir observações S/N", "required": False, "default": "N"},
]

CONTAPAGAR_URL = "https://app.omie.com.br/api/v1/financas/contapagar/"


class Command(BaseCommand):
    help = "Seed Omie ERP provider and ListarContasPagar API definition"

    def handle(self, *args, **options):
        provider, created = ERPProvider.objects.get_or_create(
            slug="omie",
            defaults={
                "name": "Omie",
                "base_url": CONTAPAGAR_URL,
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created ERPProvider: Omie"))
        else:
            self.stdout.write("ERPProvider Omie already exists")

        api_def, created = ERPAPIDefinition.objects.get_or_create(
            provider=provider,
            call="ListarContasPagar",
            defaults={
                "url": CONTAPAGAR_URL,
                "method": "POST",
                "param_schema": LISTAR_CONTAS_PAGAR_PARAM_SCHEMA,
                "description": "Listar Contas a Pagar (lcpListarRequest)",
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created ERPAPIDefinition: ListarContasPagar"))
        else:
            self.stdout.write("ERPAPIDefinition ListarContasPagar already exists")
