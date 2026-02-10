from django.contrib import admin
from django.apps import apps
from .models import *  # includes NotaFiscal, NotaFiscalItem from models_nfe


class NotaFiscalItemInline(admin.TabularInline):
    model = NotaFiscalItem
    fk_name = 'nota_fiscal'
    extra = 0
    fields = ('numero_item', 'codigo_produto', 'descricao', 'ncm', 'cfop', 'quantidade', 'valor_unitario', 'valor_total', 'produto')
    readonly_fields = ('numero_item', 'codigo_produto', 'descricao', 'ncm', 'cfop', 'quantidade', 'valor_unitario', 'valor_total')
    can_delete = True
    show_change_link = True


@admin.register(NotaFiscal)
class NotaFiscalAdmin(admin.ModelAdmin):
    list_display = ('numero', 'serie', 'chave', 'data_emissao', 'emit_nome', 'dest_nome', 'valor_nota', 'status_sefaz')
    list_filter = ('tipo_operacao', 'finalidade', 'data_emissao')
    search_fields = ('chave', 'numero', 'emit_nome', 'emit_cnpj', 'dest_nome', 'dest_cnpj')
    date_hierarchy = 'data_emissao'
    inlines = [NotaFiscalItemInline]
    readonly_fields = ('chave', 'protocolo', 'status_sefaz', 'data_autorizacao')


@admin.register(NotaFiscalItem)
class NotaFiscalItemAdmin(admin.ModelAdmin):
    list_display = ('nota_fiscal', 'numero_item', 'codigo_produto', 'descricao', 'ncm', 'cfop', 'quantidade', 'valor_total', 'produto')
    list_filter = ('ncm', 'cfop')
    search_fields = ('codigo_produto', 'descricao', 'ncm')


# Register remaining billing models (exclude NFe, already registered above)
app_models = apps.get_app_config('billing').get_models()
nfe_models = {NotaFiscal, NotaFiscalItem}
for model in app_models:
    if model not in nfe_models:
        admin.site.register(model)
