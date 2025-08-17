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
    Contract, Invoice, InvoiceLine)


PATH_COLS = ("path", "Caminho")   # accepted path column names
PATH_SEPARATOR = " > "
NAME_FIELD = "name"               # adjust if your MPTT model uses a different field
PARENT_FIELD = "parent"           # adjust if your MPTT model uses a different field

from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist

def is_mptt_model(model):
    return hasattr(model, "_mptt_meta")

def has_field(model, field_name):
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False

def get_path_value(row_dict):
    for c in PATH_COLS:
        val = row_dict.get(c)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None

def split_path(path_str, sep=PATH_SEPARATOR):
    parts = [p.strip() for p in str(path_str).split(sep)]
    return [p for p in parts if p]

def path_depth(path_str):
    return len(split_path(path_str)) if path_str else 0

def sort_df_by_path_depth(df):
    df = df.copy()
    def depth_of_row(r):
        d = r.dropna().to_dict()
        p = get_path_value(d)
        if p:
            return path_depth(p)
        # if has 'parent' only, count it as depth 1 to order under roots
        if isinstance(d.get("parent"), str) and d.get("parent").strip():
            return 1
        return 0
    df["_depth"] = df.apply(depth_of_row, axis=1)
    df.sort_values(by=["_depth"], inplace=True, kind="stable")
    return df

def resolve_parent_or_error(model, row_data, name_field=NAME_FIELD, parent_field=PARENT_FIELD):
    """
    Returns the parent instance or None (root), respecting precedence:
      1) parent_id
      2) parent as path  ("A > B > C")
      3) parent as root  (plain name at root)
      4) None (root)
    Raises ValueError if any referenced ancestor is missing.
    """
    parent_id = row_data.get("parent_id")
    parent_val = row_data.get("parent")

    # 1) parent_id wins
    if parent_id not in (None, "", float("nan")):
        try:
            return model.objects.get(pk=int(parent_id))
        except (ValueError, ObjectDoesNotExist):
            raise ValueError(f"{model.__name__}: parent_id '{parent_id}' not found.")

    # 2) parent as path
    if isinstance(parent_val, str) and parent_val.strip() and PATH_SEPARATOR in parent_val:
        parts = split_path(parent_val)
        parent = None
        for idx, name in enumerate(parts):
            inst = model.objects.filter(**{name_field: name, parent_field: parent}).first()
            if not inst:
                missing = " > ".join(parts[: idx + 1])
                raise ValueError(
                    f"{model.__name__}: missing ancestor '{missing}' for parent path '{parent_val}'. "
                    f"Ensure the ancestor rows exist (and are processed first)."
                )
            parent = inst
        return parent

    # 3) parent as root name
    if isinstance(parent_val, str) and parent_val.strip():
        inst = model.objects.filter(**{name_field: parent_val.strip(), parent_field: None}).first()
        if not inst:
            raise ValueError(
                f"{model.__name__}: parent '{parent_val}' (root) not found. "
                f"Ensure the parent row exists before children."
            )
        return inst

    # 4) No parent provided => root
    return None

def validate_path_vs_parent_and_name(model, parent, name, path_str, name_field=NAME_FIELD, parent_field=PARENT_FIELD):
    """
    If path is provided, ensure last segment == name and ancestor chain == parent's chain.
    Raise a helpful error when inconsistent.
    """
    if not path_str:
        return
    parts = split_path(path_str)
    if not parts:
        return
    if parts[-1] != name:
        raise ValueError(
            f"{model.__name__}: path/name mismatch. Leaf in path is '{parts[-1]}', but row has name '{name}'."
        )
    # Rebuild parent's chain from DB (root → ... → direct parent)
    chain = []
    p = parent
    while p is not None:
        chain.append(getattr(p, name_field))
        p = getattr(p, parent_field)
    chain = list(reversed(chain))
    if parts[:-1] != chain:
        exp = " > ".join(chain) if chain else "(root)"
        got = " > ".join(parts[:-1]) if parts[:-1] else "(root)"
        raise ValueError(
            f"{model.__name__}: parent chain differs from path. Expected '{exp}', got '{got}'."
        )


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
    
    # Add other model-app mappings as needed
}

def safe_model_dict(instance, exclude_fields=None):
    data = model_to_dict(instance)
    exclude_fields = exclude_fields or []

    # Remove campos indesejados
    for field in exclude_fields:
        data.pop(field, None)

    # Substitui FKs por seus respectivos IDs
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

            preview_data = []
            errors = []
            row_id_map = {}

            with transaction.atomic():
                savepoint = transaction.savepoint()
                print("[DEBUG] Started transaction with savepoint.")

                for model_name, df in xls.items():
                    if model_name == "References":
                        continue

                    print(f"\n[INFO] Processing sheet: {model_name}")
                    app_label = MODEL_APP_MAP.get(model_name)
                    if not app_label:
                        msg = f"Unknown model: {model_name}"
                        print("[ERROR]", msg)
                        errors.append({"model": model_name, "row": None, "field": None, "message": msg})
                        continue

                    model = apps.get_model(app_label, model_name)

                    # detect MPTT model
                    model_is_mptt = is_mptt_model(model)
                    if model_is_mptt and not (has_field(model, NAME_FIELD) and has_field(model, PARENT_FIELD)):
                        msg = f"MPTT model {model_name} must have '{NAME_FIELD}' and '{PARENT_FIELD}' fields."
                        print("[ERROR]", msg)
                        errors.append({"model": model_name, "row": None, "field": None, "message": msg})
                        continue

                    # sort rows by path depth to ensure ancestors first
                    df = sort_df_by_path_depth(df)

                    for i, row in df.iterrows():
                        row_data = row.dropna().to_dict()
                        row_id = row_data.pop('__row_id', None)
                        action = None
                        instance = None

                        try:
                            # Resolve FKs the same way as before
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

                            # MPTT strict handling
                            if model_is_mptt:
                                if not row_data.get(NAME_FIELD):
                                    raise ValueError(f"{model_name}: missing required column '{NAME_FIELD}'.")

                                name = row_data.get(NAME_FIELD)
                                path_str = get_path_value(row_data)
                                parent = resolve_parent_or_error(model, row_data, name_field=NAME_FIELD, parent_field=PARENT_FIELD)
                                validate_path_vs_parent_and_name(model, parent, name, path_str, name_field=NAME_FIELD, parent_field=PARENT_FIELD)

                                # Upsert by (parent, name) if no 'id'
                                if 'id' in row_data and row_data['id']:
                                    instance = model.objects.get(id=row_data['id'])
                                    action = 'update'
                                else:
                                    instance = model.objects.filter(**{NAME_FIELD: name, PARENT_FIELD: parent}).first()
                                    action = 'update' if instance else 'create'
                                    if not instance:
                                        instance = model(**{NAME_FIELD: name, PARENT_FIELD: parent})

                                # apply remaining fields (skip identity/parent/path columns)
                                for skip in ("id", "parent_id", "parent") + PATH_COLS:
                                    row_data.pop(skip, None)
                                for field, value in row_data.items():
                                    setattr(instance, field, value)

                            else:
                                # Non-MPTT: your original upsert by id
                                if 'id' in row_data and row_data['id']:
                                    instance = model.objects.get(id=row_data['id'])
                                    for field, value in row_data.items():
                                        setattr(instance, field, value)
                                    action = 'update'
                                else:
                                    instance = model(**row_data)
                                    action = 'create'

                            instance.save()
                            if row_id:
                                row_id_map[row_id] = instance

                            preview_data.append({
                                "model": model_name,
                                "__row_id": row_id,
                                "status": "success",
                                "action": action,
                                "data": model_to_dict(instance, exclude=['created_by', 'updated_by', 'is_deleted', 'is_active']),
                                "message": "ok"
                            })

                        except Exception as e:
                            print("[ERROR]", f"{model_name} row {i+1}: {str(e)}")
                            preview_data.append({
                                "model": model_name,
                                "__row_id": row_id,
                                "status": "error",
                                "action": action,
                                "data": {},
                                "message": str(e)
                            })
                            errors.append({"model": model_name, "row": i+1, "field": None, "message": str(e)})

                transaction.savepoint_rollback(savepoint)
                print("[INFO] Rolled back transaction after preview.")

            return Response({
                "success": not errors,
                "preview": preview_data,
                "errors": errors
            })

        except Exception as e:
            print("[FATAL ERROR]", str(e))
            return Response({"success": False, "preview": [], "errors": [{"message": str(e)}]})


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

                    model_is_mptt = is_mptt_model(model)
                    if model_is_mptt and not (has_field(model, NAME_FIELD) and has_field(model, PARENT_FIELD)):
                        errors.append({"model": model_name, "message": f"MPTT model {model_name} must have '{NAME_FIELD}' and '{PARENT_FIELD}' fields."})
                        continue

                    # sort to ensure ancestors first
                    df = sort_df_by_path_depth(df)

                    for i, row in df.iterrows():
                        row_data = row.dropna().to_dict()
                        row_id = row_data.pop('__row_id', None)
                        action = None
                        try:
                            # Handle FK fields (as before)
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

                            if model_is_mptt:
                                if not row_data.get(NAME_FIELD):
                                    raise ValueError(f"{model_name}: missing required column '{NAME_FIELD}'.")

                                name = row_data.get(NAME_FIELD)
                                path_str = get_path_value(row_data)
                                parent = resolve_parent_or_error(model, row_data, name_field=NAME_FIELD, parent_field=PARENT_FIELD)
                                validate_path_vs_parent_and_name(model, parent, name, path_str, name_field=NAME_FIELD, parent_field=PARENT_FIELD)

                                if 'id' in row_data and row_data['id']:
                                    instance = model.objects.get(id=row_data['id'])
                                    action = 'update'
                                else:
                                    instance = model.objects.filter(**{NAME_FIELD: name, PARENT_FIELD: parent}).first()
                                    action = 'update' if instance else 'create'
                                    if not instance:
                                        instance = model(**{NAME_FIELD: name, PARENT_FIELD: parent})

                                # apply remaining fields (skip identity/parent/path cols)
                                for skip in ("id", "parent_id", "parent") + PATH_COLS:
                                    row_data.pop(skip, None)
                                for field, value in row_data.items():
                                    setattr(instance, field, value)

                            else:
                                # Non-MPTT: original behavior
                                if 'id' in row_data and row_data['id']:
                                    instance = model.objects.get(id=row_data['id'])
                                    for field, value in row_data.items():
                                        setattr(instance, field, value)
                                    action = 'update'
                                else:
                                    instance = model(**row_data)
                                    action = 'create'

                            instance.save()
                            if row_id:
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
                            errors.append(f"{model_name} row {i+1}: {str(e)}")

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
        
        
def generate_bulk_import_template():
    wb = Workbook()

    # Ensure sheets are ordered logically
    sheet_defs = {
        "company": ["__row_id", "name", "subdomain"],
        "currency": ["__row_id", "code", "name"],
        "bank": ["__row_id", "name", "bank_code"],
        "bankaccount": ["__row_id", "name", "account_number", "company_fk", "entity_fk", "currency_fk", "bank_fk"],
        "account": ["__row_id", "name", "account_code", "description", "company_fk", "currency_fk", "bank_account_fk", "account_direction", "balance_date", "balance"],
        "costcenter": ["__row_id", "name", "company_fk"],
        "entity": ["__row_id", "name", "company_fk", "parent_fk", "inherit_accounts", "inherit_cost_centers"],
        "BusinessPartnerCategory": ["__row_id", "name", "company_fk", "parent_fk"],
        "BusinessPartner": ["__row_id", "name", "company_fk", "partner_type", "category_fk", "identifier", "address", 
                            "city", "state", "zipcode", "country", "email", "phone", "currency_fk", "payment_terms", "is_active", ""],
        
        "FinancialIndex": ["__row_id", "name", "index_type", "code", "interpolation_strategy", "description", 
                           "quote_frequency", "expected_quote_format", "is_forecastable"],
        
        
        "IndexQuote": ["__row_id", "index_fk", "date", "value"],
        "FinancialIndexQuoteForecast": ["__row_id", "index_fk", "date", "estimated_value", "source"],
        
        
        "ProductServiceCategory": ["__row_id", "name", "company_fk", "parent_fk"],
        
        "ProductService": ["__row_id", "name", "company_fk", "code", "category_fk", "description", 
                           "item_type", "price", "cost", "currency_fk", "track_inventory", "stock_quantity"],
        
        "Contract": ["__row_id", "name", "company_fk", "partner_fk", "contract_number", "start_date", "end_date",
                     "recurrence_rule", "base_value", "base_index_date", "adjustment_index_fk", "adjustment_frequency", 
                     "adjustment_cap", "description"],
        
        "Invoice": ["__row_id", "name", "company_fk", "partner_fk", "invoice_type", "invoice_number", "invoice_date", 
                    "due_date", "status", "currency", "total_amount", "tax_amount", "discount_amount", "recurrence_rule", 
                    "recurrence_start_date", "recurrence_end_date", "description"],
        
        "InvoiceLine": ["__row_id", "name", "company_fk", "invoice_fk", "product_service_fk", "description", 
                        "quantity", "unit_price", "tax_amount"],
        
        
    }



    sample_data = {
        "company": [["c1", "Acme Inc.", "acme"]],
        "currency": [["cur1", "USD", "US Dollar"]],
        "bank": [["b1", "Bank of Nowhere", "999"]],
        "bankaccount": [["ba1", "Main Account", "12345-6", "c1", "e1", "cur1", "b1"]],
        "account": [["a1", "Cash", "1.01.01", "c1", "cur1", "ba1", 1, "2023-12-31", 10000.00]],
        "costcenter": [["cc1", "Operations", "c1"]],
        "entity": [["e1", "Headquarters", "c1", "", True, True]],
        "BusinessPartnerCategory": [["bpc1", "Suppliers", "c1", ""]],
    "BusinessPartner": [["bp1", "Globex Corp.", "c1", "supplier", "bpc1", "123456789", "123 Market St", 
                          "San Francisco", "CA", "94105", "USA", "contact@globex.com", "+14155552671", 
                          "cur1", "30 days", True, ""]],
    
    "FinancialIndex": [["fi1", "CPI", "inflation", "CPI", "linear", "Consumer Price Index", 
                         "monthly", "accumulated", True]],

    "IndexQuote": [["iq1", "fi1", "2024-01-01", 110.5],
                   ["iq2", "fi1", "2024-02-01", 111.0],
                   ["iq3", "fi1", "2024-03-01", 111.7]],

    "FinancialIndexQuoteForecast": [["iqf1", "fi1", "2024-04-01", 112.3, "internal forecast"],
                                    ["iqf2", "fi1", "2024-05-01", 113.0, "internal forecast"]],

    "ProductServiceCategory": [["psc1", "Office Supplies", "c1", ""]],
    "ProductService": [["ps1", "Printer Paper", "c1", "PP001", "psc1", "A4 white printer paper", 
                         "product", 5.00, 2.00, "cur1", True, 500]],

    "Contract": [["ct1", "Office Supplies Agreement", "c1", "bp1", "CT2024-001", "2024-01-01", "2024-12-31",
                  "FREQ=MONTHLY", 1000.00, "2024-01-01", "", "monthly", "", "Contract for monthly supply of office items."]],

    "Invoice": [["inv1", "January Invoice", "c1", "bp1", "purchase", "INV2024-001", "2024-01-01", 
                 "2024-01-30", "issued", "cur1", 500.00, 50.00, 0.00, "", "", "", "Monthly supply invoice."]],

    "InvoiceLine": [["il1", "Paper Order", "c1", "inv1", "ps1", "A4 white printer paper", 
                     100, 5.00, 50.00]],


    }

    for sheet_name, columns in sheet_defs.items():
        if sheet_name == "company":
            ws = wb.active
            ws.title = sheet_name
        else:
            ws = wb.create_sheet(sheet_name)

        ws.append(columns)
        for row in sample_data.get(sheet_name, []):
            ws.append(row)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


class BulkImportTemplateDownloadView2(APIView):
    #permission_classes = [IsAuthenticated]  # (opcional) restrinja para usuários autenticados

    def get(self, request):
        wb = Workbook()

        sheet_defs = {
            "company": ["__row_id", "name", "subdomain"],
            "currency": ["__row_id", "code", "name"],
            "bank": ["__row_id", "name", "bank_code"],
            "bankaccount": ["__row_id", "name", "account_number", "company_fk", "entity_fk", "currency_fk", "bank_fk"],
            "account": ["__row_id", "name", "account_code", "description", "company_fk", "currency_fk", "bank_account_fk", "account_direction", "balance_date", "balance"],
            "costcenter": ["__row_id", "name", "company_fk"],
            "entity": ["__row_id", "name", "company_fk", "parent_fk", "inherit_accounts", "inherit_cost_centers"],
            "businesspartnercategory": ["__row_id", "name", "company_fk", "parent_fk"],
            "businesspartner": ["__row_id", "name", "company_fk", "partner_type", "category_fk", "identifier", "address", "city", "state", "zipcode", "country", "email", "phone", "currency_fk", "payment_terms", "is_active", ""],
            "financialindex": ["__row_id", "name", "index_type", "code", "interpolation_strategy", "description", "quote_frequency", "expected_quote_format", "is_forecastable"],
            "indexquote": ["__row_id", "index_fk", "date", "value"],
            "financialindexquoteforecast": ["__row_id", "index_fk", "date", "estimated_value", "source"],
            "productservicecategory": ["__row_id", "name", "company_fk", "parent_fk"],
            "productservice": ["__row_id", "name", "company_fk", "code", "category_fk", "description", "item_type", "price", "cost", "currency_fk", "track_inventory", "stock_quantity"],
            "contract": ["__row_id", "name", "company_fk", "partner_fk", "contract_number", "start_date", "end_date", "recurrence_rule", "base_value", "base_index_date", "adjustment_index_fk", "adjustment_frequency", "adjustment_cap", "description"],
            "invoice": ["__row_id", "name", "company_fk", "partner_fk", "invoice_type", "invoice_number", "invoice_date", "due_date", "status", "currency", "total_amount", "tax_amount", "discount_amount", "recurrence_rule", "recurrence_start_date", "recurrence_end_date", "description"],
            "invoiceline": ["__row_id", "name", "company_fk", "invoice_fk", "product_service_fk", "description", "quantity", "unit_price", "tax_amount"],
        }

        sample_data = {
            "company": [["c1", "Acme Inc.", "acme"]],
            "currency": [["cur1", "USD", "US Dollar"]],
            "bank": [["b1", "Bank of Nowhere", "999"]],
            "bankaccount": [["ba1", "Main Account", "12345-6", "c1", "e1", "cur1", "b1"]],
            "account": [["a1", "Cash", "1.01.01", "c1", "cur1", "ba1", 1, "2023-12-31", 10000.00]],
            "costcenter": [["cc1", "Operations", "c1"]],
            "entity": [["e1", "Headquarters", "c1", "", True, True]],
            "BusinessPartnerCategory": [["bpc1", "Suppliers", "c1", ""]],
            "BusinessPartner": [["bp1", "Globex Corp.", "c1", "supplier", "bpc1", "123456789", "123 Market St", "San Francisco", "CA", "94105", "USA", "contact@globex.com", "+14155552671", "cur1", "30 days", True, ""]],
            "FinancialIndex": [["fi1", "CPI", "inflation", "CPI", "linear", "Consumer Price Index", "monthly", "accumulated", True]],
            "IndexQuote": [["iq1", "fi1", "2024-01-01", 110.5], ["iq2", "fi1", "2024-02-01", 111.0], ["iq3", "fi1", "2024-03-01", 111.7]],
            "FinancialIndexQuoteForecast": [["iqf1", "fi1", "2024-04-01", 112.3, "internal forecast"], ["iqf2", "fi1", "2024-05-01", 113.0, "internal forecast"]],
            "ProductServiceCategory": [["psc1", "Office Supplies", "c1", ""]],
            "ProductService": [["ps1", "Printer Paper", "c1", "PP001", "psc1", "A4 white printer paper", "product", 5.00, 2.00, "cur1", True, 500]],
            "Contract": [["ct1", "Office Supplies Agreement", "c1", "bp1", "CT2024-001", "2024-01-01", "2024-12-31", "FREQ=MONTHLY", 1000.00, "2024-01-01", "", "monthly", "", "Contract for monthly supply of office items."]],
            "Invoice": [["inv1", "January Invoice", "c1", "bp1", "purchase", "INV2024-001", "2024-01-01", "2024-01-30", "issued", "cur1", 500.00, 50.00, 0.00, "", "", "", "Monthly supply invoice."]],
            "InvoiceLine": [["il1", "Paper Order", "c1", "inv1", "ps1", "A4 white printer paper", 100, 5.00, 50.00]],
        }

        for sheet_name, columns in sheet_defs.items():
            if sheet_name == "company":
                ws = wb.active
                ws.title = sheet_name
            else:
                ws = wb.create_sheet(sheet_name)

            ws.append(columns)
            for row in sample_data.get(sheet_name, []):
                ws.append(row)

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"bulk_import_template_{now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
    

def get_dynamic_value(obj, field_name):
    """
    Dynamically fetch either an attribute or a computed value based on the @ convention.
    - If the field starts with '@', call the corresponding get_<field>() method if it exists.
    - Otherwise, return the attribute directly.
    """
    if field_name.startswith('@'):
        method_name = f"get_{field_name[1:]}"  # Remove '@' and prepend 'get_'
        method = getattr(obj, method_name, None)
        if callable(method):
            return method()
        else:
            return None  # or raise Exception(f"Method {method_name} not found")
    else:
        return getattr(obj, field_name, None)

class BulkImportTemplateDownloadView(APIView):
    def get(self, request, tenant_id):
        wb = Workbook()

        # -------- Main sheets with templates --------
        sheet_defs = {
            "Company": ["__row_id", "name", "subdomain"],
            "Currency": ["__row_id", "code", "name"],
            "Bank": ["__row_id", "name", "bank_code", "country"],
            "BankAccount": ["__row_id", "name", "branch_id", "account_number", "company_fk", "entity_fk", "currency_fk", "bank_fk", "balance_date", "balance"],
            "Account": ["__row_id", "name", "parent_fk", "account_code", "description", 'key_words', 'examples', "company_fk", "currency_fk", "bank_account_fk", "account_direction", "balance_date", "balance"],
            "CostCenter": ["__row_id", "name", "company_fk"],
            "Entity": ["__row_id", "name", "company_fk", "parent_fk", "inherit_accounts", "inherit_cost_centers"],
            "BusinessPartnerCategory": ["__row_id", "name", "company_fk", "parent_fk"],
            "BusinessPartner": ["__row_id", "name", "company_fk", "partner_type", "category_fk", "identifier", "address", "city", "state", "zipcode", "country", "email", "phone", "currency_fk", "payment_terms", "is_active"],
            "FinancialIndex": ["__row_id", "name", "index_type", "code", "interpolation_strategy", "description", "quote_frequency", "expected_quote_format", "is_forecastable"],
            "IndexQuote": ["__row_id", "index_fk", "date", "value"],
            "FinancialIndexQuoteForecast": ["__row_id", "index_fk", "date", "estimated_value", "source"],
            "ProductServiceCategory": ["__row_id", "name", "company_fk", "parent_fk"],
            "ProductService": ["__row_id", "name", "company_fk", "code", "category_fk", "description", "item_type", "price", "cost", "currency_fk", "track_inventory", "stock_quantity"],
            "Contract": ["__row_id", "name", "company_fk", "partner_fk", "contract_number", "start_date", "end_date", "recurrence_rule", "base_value", "base_index_date", "adjustment_index_fk", "adjustment_frequency", "adjustment_cap", "description"],
            "Invoice": ["__row_id", "name", "company_fk", "partner_fk", "invoice_type", "invoice_number", "invoice_date", "due_date", "status", "currency", "total_amount", "tax_amount", "discount_amount", "recurrence_rule", "recurrence_start_date", "recurrence_end_date", "description"],
            "InvoiceLine": ["__row_id", "name", "company_fk", "invoice_fk", "product_service_fk", "description", "quantity", "unit_price", "tax_amount"],
            "Transaction": ["__row_id", "company_fk", "date", "entity_fk", "description", "amount", "currency_fk"],
            "JournalEntry": ["__row_id", "date", "company_fk", "transaction_fk", "account_fk", "cost_center_fk", "debit_amount", "credit_amount"],
            "BankTransaction": ["__row_id", "company_fk", "entity_fk", "bank_account_fk", "date", "amount", "description", "currency_fk", "transaction_type", "check_number", "reference_number", "payee", "memo", "account_number", "routing_number", "transaction_id"],
        }

        ws = wb.active
        ws.title = 'Company'
        ws.append(sheet_defs['Company'])

        for sheet_name, columns in sheet_defs.items():
            if sheet_name == 'Company':
                continue
            sheet = wb.create_sheet(sheet_name)
            sheet.append(columns)

        # -------- References sheet --------
        ref_ws = wb.create_sheet("References")
        col_position = 1  # Start at column A

        references = [
            ("Company", Company.objects.all(), ["id", "name", "subdomain"]),
            ('Currency', Currency.objects.all(), ['id', 'code', 'name']),
            ('Bank', Bank.objects.all(), ['id', 'name', 'bank_code']),
            ("BankAccount", BankAccount.objects.all(), ["id", "name", "branch_id", "account_number", "company_id", "entity_id", "currency_id", "bank_id", "balance_date", "balance"],),
            ('Entity', Entity.objects.filter(company_id=tenant_id), ['id', 'name', 'parent_id', '@path']),
            ('CostCenter', CostCenter.objects.filter(company_id=tenant_id), ['id', 'name']),
            ('Account', Account.objects.filter(company_id=tenant_id), ['id', 'name', 'account_code', 'parent_id', '@path', 'account_direction', "description", 'key_words', 'examples', 'bank_account_id', 'balance_date', 'balance']),
            ('BusinessPartnerCategory', BusinessPartnerCategory.objects.filter(company_id=tenant_id), ['id', 'name', 'parent_id', '@path']),
            ('BusinessPartner', BusinessPartner.objects.filter(company_id=tenant_id), ['id', 'name', 'partner_type']),
            ('ProductServiceCategory', ProductServiceCategory.objects.filter(company_id=tenant_id), ['id', 'name', 'parent_id', '@path']),
            ('ProductService', ProductService.objects.filter(company_id=tenant_id), ['id', 'name', 'code']),
            ('FinancialIndex', FinancialIndex.objects.all(), ['id', 'name', 'code']),
            ('Invoice', Invoice.objects.filter(company_id=tenant_id), ['id', 'invoice_number', 'invoice_date']),
            ('Contract', Contract.objects.filter(company_id=tenant_id), ['id', 'contract_number', 'start_date']),
            ('Transaction', Transaction.objects.filter(company_id=tenant_id), ['id', 'date', 'entity_id', 'description', 'amount', 'state']),
            ('JournalEntry', JournalEntry.objects.filter(company_id=tenant_id), ['id', 'transaction_id', 'account_id', 'debit_amount', 'credit_amount', 'date']),
            ('BankTransaction', BankTransaction.objects.filter(company_id=tenant_id), ['id', 'entity_id', 'bank_account_id', 'date', 'amount', 'description', 'transaction_type', 'status']),
        ]

        for title, queryset, columns in references:
            start_col = col_position

            # Write table title
            ref_ws.cell(row=1, column=start_col, value=title)

            # Write header
            for idx, col_name in enumerate(columns):
                ref_ws.cell(row=2, column=start_col + idx, value=col_name)

            # Write data rows
            for row_idx, obj in enumerate(queryset, start=3):
                for col_idx, field in enumerate(columns):
                    value = get_dynamic_value(obj, field)
                    ref_ws.cell(row=row_idx, column=start_col + col_idx, value=value)

            col_position += len(columns) + 1  # Move to next table

        # -------- Output --------
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"bulk_import_template_{now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )