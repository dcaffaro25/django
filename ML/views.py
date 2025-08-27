import io
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import MLModel
from .serializers import MLModelSerializer

from .utils.train import (
    train_categorization_model,
    train_journal_model,
)
from .utils.predict import predict_top_accounts_with_names
from .utils.journal import suggest_journal_entries

class MLModelViewSet(viewsets.ModelViewSet):
    """
    CRUD and actions for stored ML models.
    """
    queryset = MLModel.objects.all().order_by("-trained_at")
    serializer_class = MLModelSerializer

    @action(detail=False, methods=["post"])
    def train(self, request):
        """
        Trigger training of a model. Required keys:
          - company_id: int
          - model_name: "categorization" or "journal"
          - training_fields: list of strings
          - prediction_fields: list of strings
          - records_per_account: int
        """
        company_id = request.data.get("company_id")
        model_name = request.data.get("model_name")
        training_fields = request.data.get("training_fields")
        prediction_fields = request.data.get("prediction_fields")
        records_per_account = request.data.get("records_per_account")

        if not (company_id and model_name and training_fields and prediction_fields and records_per_account):
            return Response(
                {"error": "company_id, model_name, training_fields, prediction_fields, and records_per_account are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            records_per_account = int(records_per_account)
        except Exception:
            return Response({"error": "records_per_account must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

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
                return Response({"error": "Unsupported model_name"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(ml_record)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def predict(self, request, pk=None):
        """
        Use the specified model to make a prediction.
        The request body must include all fields listed in the model's prediction_fields.
        """
        ml_model = self.get_object()

        payload = {}
        missing = []
        for field in (ml_model.prediction_fields or []):
            if field in request.data:
                payload[field] = request.data[field]
            else:
                missing.append(field)
        if missing:
            return Response(
                {"error": f"Missing required prediction fields: {missing}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if ml_model.name == "categorization":
                result = predict_top_accounts_with_names(payload, ml_model, top_n=3)
                return Response({"predictions": result})
            elif ml_model.name == "journal":
                result = suggest_journal_entries(payload, ml_model, top_k=2)
                return Response({"suggestions": result})
            else:
                return Response({"error": f"Prediction not implemented for model {ml_model.name}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
