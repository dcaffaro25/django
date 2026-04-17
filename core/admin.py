from django.contrib import admin
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist


class _ErpIdListDisplayMixin:
    """Include erp_id on the changelist when the model defines that field."""

    def get_list_display(self, request):
        cols = list(super().get_list_display(request))
        try:
            self.model._meta.get_field("erp_id")
        except FieldDoesNotExist:
            return cols
        if "erp_id" in cols:
            return cols
        if "id" in cols:
            cols.insert(cols.index("id") + 1, "erp_id")
        else:
            cols.insert(0, "erp_id")
        return cols


_app_config = apps.get_app_config("core")
for _model in _app_config.get_models():
    if admin.site.is_registered(_model):
        admin.site.unregister(_model)
    _Admin = type(
        f"{_model.__name__}Admin",
        (_ErpIdListDisplayMixin, admin.ModelAdmin),
        {},
    )
    admin.site.register(_model, _Admin)
