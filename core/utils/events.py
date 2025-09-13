# core/utils/events.py
from core.models import ActionEvent

def log_event(*, company_id:int, verb:str, level:str="info", actor=None,
              target=None, message:str="", meta:dict|None=None):
    target_app = target_model = target_id = ""
    if target is not None:
        target_app   = target._meta.app_label
        target_model = target._meta.model_name
        target_id    = str(getattr(target, "pk", ""))
    ActionEvent.objects.create(
        company_id=company_id, actor=actor, verb=verb, level=level,
        target_app=target_app, target_model=target_model, target_id=target_id,
        message=message, meta=meta or {}
    )
