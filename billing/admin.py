from django.contrib import admin
from django.apps import apps
from .models import *  # includes NotaFiscal, NotaFiscalItem, NFeEvento from models_nfe


class NotaFiscalItemInline(admin.TabularInline):
    model = NotaFiscalItem
    fk_name = 'nota_fiscal'
    extra = 0
    fields = ('numero_item', 'codigo_produto', 'descricao', 'ncm', 'cfop', 'quantidade', 'valor_unitario', 'valor_total', 'produto')
    readonly_fields = ('numero_item', 'codigo_produto', 'descricao', 'ncm', 'cfop', 'quantidade', 'valor_unitario', 'valor_total')
    can_delete = True
    show_change_link = True


class NotaFiscalReferenciaInline(admin.TabularInline):
    model = NotaFiscalReferencia
    fk_name = 'nota_fiscal'
    extra = 0
    fields = ('chave_referenciada', 'nota_referenciada')
    readonly_fields = ('chave_referenciada', 'nota_referenciada')
    can_delete = True
    show_change_link = True
    verbose_name = 'Referência a outra NF'
    verbose_name_plural = 'Referências a outras NFs'


@admin.register(NotaFiscal)
class NotaFiscalAdmin(admin.ModelAdmin):
    list_display = ('numero', 'serie', 'chave', 'data_emissao', 'emit_nome', 'dest_nome', 'valor_nota', 'status_sefaz')
    list_filter = ('tipo_operacao', 'finalidade', 'data_emissao')
    search_fields = ('chave', 'numero', 'emit_nome', 'emit_cnpj', 'dest_nome', 'dest_cnpj')
    date_hierarchy = 'data_emissao'
    inlines = [NotaFiscalItemInline, NotaFiscalReferenciaInline]
    readonly_fields = ('chave', 'protocolo', 'status_sefaz', 'data_autorizacao')


@admin.register(NotaFiscalItem)
class NotaFiscalItemAdmin(admin.ModelAdmin):
    list_display = ('nota_fiscal', 'numero_item', 'codigo_produto', 'descricao', 'ncm', 'cfop', 'quantidade', 'valor_total', 'produto')
    list_filter = ('ncm', 'cfop')
    search_fields = ('codigo_produto', 'descricao', 'ncm')


@admin.register(NFeEvento)
class NFeEventoAdmin(admin.ModelAdmin):
    list_display = ('chave_nfe', 'tipo_evento', 'n_seq_evento', 'data_evento', 'status_sefaz', 'protocolo')
    list_filter = ('tipo_evento', 'status_sefaz')
    search_fields = ('chave_nfe', 'descricao')
    date_hierarchy = 'data_evento'
    readonly_fields = ('chave_nfe', 'protocolo', 'status_sefaz', 'data_registro')


@admin.register(NFeInutilizacao)
class NFeInutilizacaoAdmin(admin.ModelAdmin):
    list_display = ('ano', 'serie', 'n_nf_ini', 'n_nf_fin', 'status_sefaz', 'data_registro')
    list_filter = ('ano', 'serie', 'status_sefaz')
    search_fields = ('cnpj', 'x_just', 'protocolo')
    date_hierarchy = 'data_registro'
    readonly_fields = ('protocolo', 'status_sefaz', 'data_registro')


@admin.register(NotaFiscalReferencia)
class NotaFiscalReferenciaAdmin(admin.ModelAdmin):
    list_display = ('nota_fiscal', 'chave_referenciada', 'nota_referenciada')
    list_filter = ('nota_fiscal__finalidade',)
    search_fields = ('chave_referenciada', 'nota_fiscal__chave')
    raw_id_fields = ('nota_fiscal', 'nota_referenciada')


# Register remaining billing models (exclude NFe, already registered above)
app_models = apps.get_app_config('billing').get_models()
nfe_models = {NotaFiscal, NotaFiscalItem, NotaFiscalReferencia, NFeEvento, NFeInutilizacao}
for model in app_models:
    if model not in nfe_models:
        admin.site.register(model)
