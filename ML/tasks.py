import logging
from celery import shared_task
from django.utils import timezone

from .models import MLTrainingTask, MLModel
from .utils.train import train_categorization_model, train_journal_model

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def train_model_task(self, task_id, company_id, model_name,
                     training_fields, prediction_fields, records_per_account):
    """
    Tarefa Celery para treinar um modelo ML e atualizar o status.
    """
    task_obj = MLTrainingTask.objects.get(id=task_id)
    try:
        task_obj.status = "running"
        task_obj.save(update_fields=["status"])

        if model_name == "categorization":
            ml_record = train_categorization_model(
                company_id, records_per_account,
                training_fields, prediction_fields
            )
        elif model_name == "journal":
            ml_record = train_journal_model(
                company_id, records_per_account,
                training_fields, prediction_fields
            )
        else:
            raise ValueError("Unsupported model_name")

        # Marca conclusão e retorna métricas no result, se existirem
        task_obj.status = "completed"
        result_data = {"ml_model_id": ml_record.id}
        if ml_record.training_metrics:
            result_data["training_metrics"] = ml_record.training_metrics
        task_obj.result = result_data
        task_obj.save(update_fields=["status", "result"])
        return result_data

    except Exception as e:
        task_obj.status = "failed"
        task_obj.result = {"error": str(e)}
        task_obj.save(update_fields=["status", "result"])
        raise

@shared_task(bind=True)
def train_model_task2(self, company_id, model_name, training_fields, prediction_fields, records_per_account):
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
