from django.contrib import admin
from django.contrib.admin.utils import model_ngettext
from django.apps import apps
from django.db import transaction as db_transaction
from .models import *  # includes NotaFiscal, NotaFiscalItem, NFeEvento from models_nfe

# Batch size for bulk operations
BULK_DELETE_BATCH_SIZE = 1000


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

    @admin.action(description="Delete selected Notas Fiscais (with items, references, events)")
    def fast_delete_selected(self, request, queryset):
        """Bulk delete Notas Fiscais. CASCADE deletes items, referencias, and eventos."""
        ids = list(queryset.values_list('id', flat=True))
        total = len(ids)
        if not total:
            self.message_user(request, "No Notas Fiscais selected.", level='warning')
            return
        deleted = 0
        with db_transaction.atomic():
            for i in range(0, total, BULK_DELETE_BATCH_SIZE):
                batch = ids[i:i + BULK_DELETE_BATCH_SIZE]
                deleted += NotaFiscal.objects.filter(id__in=batch).delete()[0]
        self.message_user(
            request,
            f"Successfully deleted {deleted} {model_ngettext(self.model, deleted)}.",
            level='success'
        )

    actions = ['fast_delete_selected']


@admin.register(NotaFiscalItem)
class NotaFiscalItemAdmin(admin.ModelAdmin):
    list_display = ('nota_fiscal', 'numero_item', 'codigo_produto', 'descricao', 'ncm', 'cfop', 'quantidade', 'valor_total', 'produto')
    list_filter = ('ncm', 'cfop')
    search_fields = ('codigo_produto', 'descricao', 'ncm')

    @admin.action(description="Delete selected Nota Fiscal items")
    def fast_delete_selected(self, request, queryset):
        """Bulk delete Nota Fiscal items."""
        ids = list(queryset.values_list('id', flat=True))
        total = len(ids)
        if not total:
            self.message_user(request, "No items selected.", level='warning')
            return
        deleted = 0
        with db_transaction.atomic():
            for i in range(0, total, BULK_DELETE_BATCH_SIZE):
                batch = ids[i:i + BULK_DELETE_BATCH_SIZE]
                deleted += NotaFiscalItem.objects.filter(id__in=batch).delete()[0]
        self.message_user(
            request,
            f"Successfully deleted {deleted} {model_ngettext(self.model, deleted)}.",
            level='success'
        )

    actions = ['fast_delete_selected']


@admin.register(NFeEvento)
class NFeEventoAdmin(admin.ModelAdmin):
    list_display = ('chave_nfe', 'tipo_evento', 'n_seq_evento', 'data_evento', 'status_sefaz', 'protocolo')
    list_filter = ('tipo_evento', 'status_sefaz')
    search_fields = ('chave_nfe', 'descricao')
    date_hierarchy = 'data_evento'
    readonly_fields = ('chave_nfe', 'protocolo', 'status_sefaz', 'data_registro')

    @admin.action(description="Delete selected NFe eventos")
    def fast_delete_selected(self, request, queryset):
        """Bulk delete NFe eventos."""
        ids = list(queryset.values_list('id', flat=True))
        total = len(ids)
        if not total:
            self.message_user(request, "No eventos selected.", level='warning')
            return
        deleted = 0
        with db_transaction.atomic():
            for i in range(0, total, BULK_DELETE_BATCH_SIZE):
                batch = ids[i:i + BULK_DELETE_BATCH_SIZE]
                deleted += NFeEvento.objects.filter(id__in=batch).delete()[0]
        self.message_user(
            request,
            f"Successfully deleted {deleted} {model_ngettext(self.model, deleted)}.",
            level='success'
        )

    actions = ['fast_delete_selected']


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

    @admin.action(description="Delete selected Nota Fiscal referências")
    def fast_delete_selected(self, request, queryset):
        """Bulk delete Nota Fiscal referências."""
        ids = list(queryset.values_list('id', flat=True))
        total = len(ids)
        if not total:
            self.message_user(request, "No referências selected.", level='warning')
            return
        deleted = 0
        with db_transaction.atomic():
            for i in range(0, total, BULK_DELETE_BATCH_SIZE):
                batch = ids[i:i + BULK_DELETE_BATCH_SIZE]
                deleted += NotaFiscalReferencia.objects.filter(id__in=batch).delete()[0]
        self.message_user(
            request,
            f"Successfully deleted {deleted} {model_ngettext(self.model, deleted)}.",
            level='success'
        )

    actions = ['fast_delete_selected']


# Custom ProductService admin with account mapping fields
from multitenancy.admin import CompanyScopedAdmin


@admin.register(ProductServiceCategory)
class ProductServiceCategoryAdmin(CompanyScopedAdmin):
    list_display = ("name", "parent", "company")
    list_filter = ("company",)
    search_fields = ("name",)


@admin.register(ProductService)
class ProductServiceAdmin(CompanyScopedAdmin):
    list_display = ("code", "name", "item_type", "price", "track_inventory", "is_active")
    list_filter = ("item_type", "track_inventory", "is_active", "company")
    search_fields = ("code", "name", "description")
    autocomplete_fields = (
        "category",
        "currency",
        "inventory_account",
        "cogs_account",
        "adjustment_account",
        "revenue_account",
        "purchase_account",
        "discount_given_account",
    )
    fieldsets = (
        (None, {
            "fields": ("name", "code", "category", "description", "item_type", "price", "cost", "currency"),
        }),
        ("Inventory", {
            "fields": ("track_inventory", "stock_quantity"),
        }),
        ("Account Mapping", {
            "fields": (
                "inventory_account",
                "cogs_account",
                "adjustment_account",
                "revenue_account",
                "purchase_account",
                "discount_given_account",
            ),
            "description": "Override tenant defaults for inventory reporting. Leave blank to use TenantCostingConfig.",
        }),
        (None, {"fields": ("tax_code", "is_active")}),
    )


# Register remaining billing models (exclude NFe, ProductService, ProductServiceCategory - already registered above)
app_models = apps.get_app_config('billing').get_models()
nfe_models = {NotaFiscal, NotaFiscalItem, NotaFiscalReferencia, NFeEvento, NFeInutilizacao}
exclude_models = nfe_models | {ProductService, ProductServiceCategory}
for model in app_models:
    if model not in exclude_models:
        admin.site.register(model)
