import logging
from celery import shared_task
from django.utils import timezone

from .models import MLModel
from .utils.train import train_categorization_model, train_journal_model

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def train_model_task(self, company_id, model_name, training_fields, prediction_fields, records_per_account):
    """
    Celery task to train and store a new ML model.
    """
    logger.info(f"[ML] Starting training: company={company_id}, model={model_name}")

    try:
        if model_name == "categorization":
            ml_record = train_categorization_model(
                company_id=company_id,
                records_per_account=records_per_account,
                training_fields=training_fields,
                prediction_fields=prediction_fields,
            )
        elif model_name == "journal":
            ml_record = train_journal_model(
                company_id=company_id,
                records_per_account=records_per_account,
                training_fields=training_fields,
                prediction_fields=prediction_fields,
            )
        else:
            raise ValueError(f"Unsupported model_name: {model_name}")

        logger.info(f"[ML] Training completed: {ml_record}")
        return {"status": "success", "ml_model_id": ml_record.id}

    except Exception as exc:
        logger.error(f"[ML] Training failed: {exc}", exc_info=True)
        return {"status": "failed", "error": str(exc)}
