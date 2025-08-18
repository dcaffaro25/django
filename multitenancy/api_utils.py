# NORD/multitenancy/api_utils.py

import csv
import io
import pandas as pd
from django.apps import apps
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from io import BytesIO
from django.http import HttpResponse
from openpyxl import Workbook
from django.forms.models import model_to_dict
from django.utils.timezone import now
from multitenancy.models import Company, Entity
from accounting.models import Currency, Bank, BankAccount, Account, CostCenter, Transaction, JournalEntry, BankTransaction
from core.models import FinancialIndex, IndexQuote, FinancialIndexQuoteForecast
from billing.models import (
    BusinessPartnerCategory, BusinessPartner,
    ProductServiceCategory, ProductService,
    Contract, Invoice, InvoiceLine
)

# -----------------------
# MPTT PATH SUPPORT (generic)
# -----------------------
PATH_COLS = ("path", "Caminho")
PATH_SEPARATOR = " > "

def _is_mptt_model(model) -> bool:
    """True if model is an MPTT model with a 'parent' foreign key and a 'name' field."""
    return hasattr(model, "_mptt_meta") and any(f.name == "parent" for f in model._meta.fields) and any(f.name == "name" for f in model._meta.fields)

def _get_path_value(row_dict):
    """Return the path string if present under any accepted column name; else None."""
    for c in PATH_COLS:
        val = row_dict.get(c)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None

def _split_path(path_str):
    return [p.strip() for p in str(path_str).split(PATH_SEPARATOR) if p and p.strip()]

def _sort_df_by_path_depth_if_mptt(model, df):
    """Stable-sort by path depth so ancestors come before children (only if a path col exists)."""
    if not _is_mptt_model(model):
        return df
    if not any(col in df.columns for col in PATH_COLS):
        return df
    df = df.copy()
    def depth(row):
        p = _get_path_value(row.dropna().to_dict())
        return len(_split_path(p)) if p else 0
    df["_depth"] = df.apply(depth, axis=1)
    df.sort_values(by=["_depth"], inplace=True, kind="stable")
    df.drop(columns=["_depth"], inplace=True)
    return df

def _resolve_parent_from_path_chain(model, parts):
    """
    Walk the chain of names (all but the last are ancestors) and return the parent instance.
    Raises ValueError if any ancestor is missing.
    """
    parent = None
    for idx, node_name in enumerate(parts):
        inst = model.objects.filter(name=node_name, parent=parent).first()
        if not inst:
            missing = " > ".join(parts[: idx + 1])
            raise ValueError(f"{model.__name__}: missing ancestor '{missing}'. Provide this row before its children.")
        parent = inst
    return parent
# -----------------------

def success_response(data, message="Success"):
    return Response({"status": "success", "data": data, "message": message})

def error_response(message, status_code=400):
    return Response({"status": "error", "message": message}, status=status_code)

@transaction.atomic
def generic_bulk_create(viewset, request_data):
    serializer_class = viewset.get_serializer_class()
    serializer = serializer_class(data=request_data, many=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@transaction.atomic
def generic_bulk_update(viewset, request_data):
    serializer_class = viewset.get_serializer_class()
    model = viewset.get_queryset().model
    for item in request_data:
        instance = model.objects.get(id=item['id'])
        serializer = serializer_class(instance, data=item)
        if serializer.is_valid():
            serializer.save()
        else:
            transaction.set_rollback(True)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response({'status': 'bulk update successful'}, status=status.HTTP_200_OK)

@transaction.atomic
def generic_bulk_delete(viewset, ids):
    model = viewset.get_queryset().model
    model.objects.filter(id__in=ids).delete()
    return Response({'status': 'bulk delete successful'}, status=status.HTTP_204_NO_CONTENT)

# Function for CSV response
def create_csv_response(data, delimiter=','):
    csvfile = io.StringIO()
    writer = csv.DictWriter(csvfile, fieldnames=data[0].keys(), delimiter=delimiter)
    writer.writeheader()
    writer.writerows(data)
    csvfile.seek(0)
    return Response(csvfile.getvalue(), content_type='text/csv')

# Function for Excel response
def create_excel_response(data):
    df = pd.DataFrame(data)
    excel_file = io.BytesIO()
    with pd.ExcelWriter(excel_file, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Sheet1')
    excel_file.seek(0)
    return Response(excel_file.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

MODEL_APP_MAP = {
    "Account": "accounting",
    "CostCenter": "accounting",
    "Entity": "multitenancy",
    "Company": "multitenancy",
    "Currency": "accounting",
    "Bank": "accounting",
    "BankAccount": "accounting",
    "Transaction": "accounting",
    "JournalEntry": "accounting",
    "BankTransaction": "accounting",
    "BusinessPartnerCategory": "billing",
    "BusinessPartner": "billing",
    "ProductServiceCategory": "billing",
    "ProductService": "billing",
    "Contract": "billing",
    "Invoice": "billing",
    "InvoiceLine": "billing",
    "FinancialIndex": "core",
    "IndexQuote": "core",
    "FinancialIndexQuoteForecast": "core"
}

def safe_model_dict(instance, exclude_fields=None):
    data = model_to_dict(instance)
    exclude_fields = exclude_fields or []
    for field in exclude_fields:
        data.pop(field, None)
    for field in instance._meta.fields:
        if field.is_relation and field.name in data:
            related_obj = getattr(instance, field.name)
            data[field.name] = related_obj.id if related_obj else None
    return data

class BulkImportPreview(APIView):
    def post(self, request, *args, **kwargs):
        try:
            file = request.FILES['file']
            print("[INFO] File received:", file.name)

            xls = pd.read_excel(file, sheet_name=None)
            print(f"[INFO] Loaded {len(xls)} sheets from Excel.")

            preview_data = {}
            errors = []
            row_id_map = {}

            with transaction.atomic():
                savepoint = transaction.savepoint()
                print("[DEBUG] Started transaction with savepoint.")
                model_preview = []
                for model_name, df in xls.items():
                    if model_name != "References":
                        print(f"\n[INFO] Processing sheet: {model_name}")
                        app_label = MODEL_APP_MAP.get(model_name)

                        if not app_label:
                            msg = f"Unknown model: {model_name}"
                            print("[ERROR]", msg)
                            errors.append({"model": model_name, "row": None, "field": None, "message": msg})
                            continue

                        model = apps.get_model(app_label, model_name)

                        # ----- OPTIONAL: keep ancestors first if 'path' given on MPTT models
                        df = _sort_df_by_path_depth_if_mptt(model, df)

                        for i, row in df.iterrows():
                            print(f"[DEBUG] Processing row {i} of model {model_name}")
                            row_data = row.dropna().to_dict()
                            row_id = row_data.pop('__row_id', None)
                            print("  Raw data:", row_data)
                            print("  __row_id:", row_id)
                            action = None
                            instance = None
                            try:
                                # Handle FK fields (original behavior)
                                fk_fields = {k: v for k, v in row_data.items() if k.endswith('_fk')}
                                for fk_field, fk_ref in fk_fields.items():
                                    field_name = fk_field[:-3]
                                    print(f"  Resolving FK for {field_name} -> {fk_ref}")
                                    try:
                                        if isinstance(fk_ref, str) and fk_ref in row_id_map:
                                            fk_instance = row_id_map[fk_ref]
                                        elif isinstance(fk_ref, (int, float)) or (isinstance(fk_ref, str) and fk_ref.isdigit()):
                                            related_field = model._meta.get_field(field_name)
                                            fk_model = related_field.related_model
                                            fk_instance = fk_model.objects.get(id=int(fk_ref))
                                        else:
                                            raise ValueError(f"Invalid FK reference format: {fk_ref}")
                                    except Exception as e:
                                        error_msg = f"FK reference '{fk_ref}' not found for field '{field_name}' in model {model_name}: {str(e)}"
                                        print("[ERROR]", error_msg)
                                        raise ValueError(error_msg)
                                    row_data[field_name] = fk_instance
                                    del row_data[fk_field]

                                # --------- MPTT PATH SUPPORT (derive name/parent from path if provided)
                                if _is_mptt_model(model):
                                    path_val = _get_path_value(row_data)
                                    if path_val:
                                        parts = _split_path(path_val)
                                        if not parts:
                                            raise ValueError(f"{model_name}: empty path.")
                                        leaf_name = parts[-1]
                                        parent = None
                                        if len(parts) > 1:
                                            parent = _resolve_parent_from_path_chain(model, parts[:-1])
                                        # Set/override name & parent based on path
                                        row_data['name'] = row_data.get('name', leaf_name) or leaf_name
                                        row_data['parent'] = parent
                                        # Remove possible conflicting parent hints
                                        row_data.pop('parent_id', None)
                                        row_data.pop('parent_fk', None)
                                        # Remove the path column itself
                                        for c in PATH_COLS:
                                            row_data.pop(c, None)

                                # Original create/update
                                if 'id' in row_data and row_data['id']:
                                    instance = model.objects.get(id=row_data['id'])
                                    for field, value in row_data.items():
                                        setattr(instance, field, value)
                                    action = 'update'
                                    print(f"[UPDATE] {model_name} ID {row_data['id']}")
                                else:
                                    instance = model(**row_data)
                                    action = 'create'
                                    print(f"[CREATE] New {model_name} instance")

                                instance.save()
                                print(f"[SAVE] {model_name} row saved successfully.")

                                if row_id:
                                    row_id_map[row_id] = instance
                                    print(f"[MAP] __row_id '{row_id}' bound to ID {instance.pk}")

                                model_preview.append({
                                    "model": model_name,
                                    "__row_id": row_id,
                                    "status": "success",
                                    "action": action,
                                    "data": model_to_dict(instance, exclude=['created_by', 'updated_by', 'is_deleted', 'is_active']),
                                    "message": "ok"
                                })
                            except Exception as e:
                                error = f"{model_name} row {i}: {str(e)}"
                                print("[ERROR]", error)
                                model_preview.append({
                                    "model": model_name,
                                    "__row_id": row_id,
                                    "status": "error",
                                    "action": action,
                                    "data": {},
                                    "message": str(e)
                                })
                                errors.append({"model": model_name, "row": i, "field": None, "message": str(e)})
                    preview_data = model_preview

                    transaction.savepoint_rollback(savepoint)
                    print("[INFO] Rolled back transaction after preview.")

            return Response({
                "success": not errors,
                "preview": preview_data,
                "errors": errors if errors else []
            })

        except Exception as e:
            print("[FATAL ERROR]", str(e))
            errors.append({"model": model_name, "row": i, "field": None, "message": str(e)})
            return Response({"success": False, "preview": [], "errors": errors})

class BulkImportExecute(APIView):
    def post(self, request, *args, **kwargs):
        try:
            file = request.FILES['file']
            print("[INFO] File received:", file.name)

            xls = pd.read_excel(file, sheet_name=None)
            print(f"[INFO] Loaded {len(xls)} sheets from Excel.")

            row_id_map = {}
            results = []
            errors = []

            with transaction.atomic():
                for model_name, df in xls.items():
                    print(f"\n[INFO] Processing sheet: {model_name}")
                    app_label = MODEL_APP_MAP.get(model_name)

                    if not app_label:
                        errors.append({"model": model_name, "message": f"Unknown model: {model_name}"})
                        continue

                    model = apps.get_model(app_label, model_name)

                    # Optional: ensure ancestors first when path is present
                    df = _sort_df_by_path_depth_if_mptt(model, df)

                    for i, row in df.iterrows():
                        row_data = row.dropna().to_dict()
                        row_id = row_data.pop('__row_id', None)
                        action = None
                        try:
                            # Handle FK fields (original behavior)
                            fk_fields = {k: v for k, v in row_data.items() if k.endswith('_fk')}
                            for fk_field, fk_ref in fk_fields.items():
                                field_name = fk_field[:-3]
                                print(f"  Resolving FK for {field_name} -> {fk_ref}")
                                try:
                                    if isinstance(fk_ref, str) and fk_ref in row_id_map:
                                        fk_instance = row_id_map[fk_ref]
                                    elif isinstance(fk_ref, (int, float)) or (isinstance(fk_ref, str) and fk_ref.isdigit()):
                                        related_field = model._meta.get_field(field_name)
                                        fk_model = related_field.related_model
                                        fk_instance = fk_model.objects.get(id=int(fk_ref))
                                    else:
                                        raise ValueError(f"Invalid FK reference format: {fk_ref}")
                                except Exception as e:
                                    error_msg = f"FK reference '{fk_ref}' not found for field '{field_name}' in model {model_name}: {str(e)}"
                                    print("[ERROR]", error_msg)
                                    raise ValueError(error_msg)
                                row_data[field_name] = fk_instance
                                del row_data[fk_field]

                            # --------- MPTT PATH SUPPORT
                            if _is_mptt_model(model):
                                path_val = _get_path_value(row_data)
                                if path_val:
                                    parts = _split_path(path_val)
                                    if not parts:
                                        raise ValueError(f"{model_name}: empty path.")
                                    leaf_name = parts[-1]
                                    parent = None
                                    if len(parts) > 1:
                                        parent = _resolve_parent_from_path_chain(model, parts[:-1])
                                    row_data['name'] = row_data.get('name', leaf_name) or leaf_name
                                    row_data['parent'] = parent
                                    row_data.pop('parent_id', None)
                                    row_data.pop('parent_fk', None)
                                    for c in PATH_COLS:
                                        row_data.pop(c, None)

                            if 'id' in row_data and row_data['id']:
                                instance = model.objects.get(id=row_data['id'])
                                for field, value in row_data.items():
                                    setattr(instance, field, value)
                                action = 'update'
                            else:
                                instance = model(**row_data)
                                action = 'create'

                            instance.save()
                            row_id_map[row_id] = instance

                            results.append({
                                "model": model_name,
                                "__row_id": row_id,
                                "status": "success",
                                "action": action,
                                "data": safe_model_dict(instance, exclude_fields=['created_by', 'updated_by', 'is_deleted', 'is_active']),
                                "message": "ok"
                            })

                        except Exception as e:
                            results.append({
                                "model": model_name,
                                "__row_id": row_id,
                                "status": "error",
                                "message": str(e)
                            })
                            errors.append(str(e))

            return Response({
                "success": not errors,
                "results": results,
                "errors": errors
            }, status=200 if not errors else 400)

        except Exception as e:
            return Response({
                "success": False,
                "results": [],
                "errors": [str(e)]
            }, status=400)
