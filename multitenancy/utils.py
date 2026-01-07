from multitenancy.models import Company
from accounting.models import Transaction, JournalEntry

from django.apps import apps
from faker import Faker

fake = Faker()
from django.apps import apps

def print_all_installed_models():
    """
    Prints all models from every installed app in the format:
        app_label.ModelName
    """
    for app_config in apps.get_app_configs():
        for model in app_config.get_models():
            print(f"{app_config.label}.{model.__name__}")
            
            
# A list (array) of (app_label, model_name) tuples
ALL_MODELS = [
    ("admin", "LogEntry"),
    ("auth", "Permission"),
    ("auth", "Group"),
    ("contenttypes", "ContentType"),
    ("sessions", "Session"),
    ("authtoken", "Token"),
    ("authtoken", "TokenProxy"),
    ("multitenancy", "CustomUser"),
    ("multitenancy", "Company"),
    ("multitenancy", "Entity"),
    ("multitenancy", "IntegrationRule"),
    ("multitenancy", "IntegrationRuleLog"),
    ("multitenancy", "SubstitutionRule"),
    ("core", "FinancialIndex"),
    ("core", "IndexQuote"),
    ("core", "FinancialIndexQuoteForecast"),
    ("accounting", "Currency"),
    ("accounting", "CostCenter"),
    ("accounting", "AllocationBase"),
    ("accounting", "Account"),
    ("accounting", "Transaction"),
    ("accounting", "JournalEntry"),
    ("accounting", "Rule"),
    ("accounting", "Bank"),
    ("accounting", "BankAccount"),
    ("accounting", "BankTransaction"),
    ("accounting", "Reconciliation"),
    ("hr", "Position"),
    ("hr", "Employee"),
    ("hr", "TimeTracking"),
    ("hr", "KPI"),
    ("hr", "Bonus"),
    ("hr", "RecurringAdjustment"),
    ("hr", "Payroll"),
    ("billing", "BusinessPartnerCategory"),
    ("billing", "BusinessPartner"),
    ("billing", "ProductServiceCategory"),
    ("billing", "ProductService"),
    ("billing", "Contract"),
    ("billing", "Invoice"),
    ("billing", "InvoiceLine"),
    ("npl", "DocTypeRule"),
    ("npl", "SpanRule")

]

def get_app_for_model(model_name):
    """
    Given a model_name (e.g. 'Group'), return the app label (e.g. 'auth').
    Returns None if not found or if you have duplicates.
    """
    for app_label, m_name in ALL_MODELS:
        if m_name.lower() == model_name.lower():
            return app_label
    return None

if __name__ == "__main__":
    # Example usage:
    print(get_app_for_model("Group"))        # => "auth"
    print(get_app_for_model("JournalEntry")) # => "accounting"
    print(get_app_for_model("XYZ"))         # => None
            
def generate_mock_data(app_name, model_name, num_records=10):
    """
    Generate mock data for a given model.

    Args:
        app_name (str): The app name where the model resides.
        model_name (str): The name of the model to generate data for.
        num_records (int): Number of mock records to generate.

    Returns:
        list[dict]: A list of dictionaries representing mock data.
    """
    model = apps.get_model(app_name, model_name)
    if not model:
        raise ValueError(f"Model '{model_name}' not found in app '{app_name}'.")

    mock_data = []
    for _ in range(num_records):
        record = {}
        for field in model._meta.fields:
            # Skip auto-generated fields like ID
            if field.auto_created or field.primary_key:
                continue

            field_name = field.name
            field_type = type(field).__name__

            # Generate mock values based on field type
            if field_type == "CharField":
                record[field_name] = fake.text(max_nb_chars=50)
            elif field_type == "IntegerField":
                record[field_name] = fake.random_int(min=0, max=1000)
            elif field_type == "DecimalField":
                record[field_name] = fake.pydecimal(left_digits=5, right_digits=2, positive=True)
            elif field_type == "BooleanField":
                record[field_name] = fake.boolean()
            elif field_type == "DateField":
                record[field_name] = fake.date()
            elif field_type == "DateTimeField":
                record[field_name] = fake.date_time()
            elif field_type == "ForeignKey":
                related_model = field.related_model
                record[field_name] = related_model.objects.order_by('?').first().id if related_model.objects.exists() else None
            else:
                # Default to None for unsupported field types
                record[field_name] = None

        mock_data.append(record)

    return mock_data

def resolve_tenant(subdomain_or_id):
    # 1. Try subdomain lookup first
    try:
        return Company.objects.get(subdomain=subdomain_or_id)
    except Company.DoesNotExist:
        pass  # Move on to ID lookup

    # 2. If subdomain lookup failed, try interpreting as an ID
    try:
        tenant_id = int(subdomain_or_id)
        return Company.objects.get(pk=tenant_id)
    except (ValueError, Company.DoesNotExist):
        return None
    
def resolve_fk_value(
    value, 
    model_class, 
    id_field="id", 
    name_field="name", 
    allow_null=False
):
    """
    Attempt to resolve an FK field into a valid primary key (int) 
    or return None if allow_null is True and no record is found.

    :param value: The input value for the FK (could be int, str, dict, or None).
    :param model_class: The Django model class to query (e.g. Company, Account, etc.).
    :param id_field: The field name that is a PK (usually "id").
    :param name_field: The unique field name to fetch by (usually "name").
    :param allow_null: If True, return None if value is invalid or record not found 
                      (instead of raising an error).
    :return: An int representing the PK, or None if null is allowed or if record not found.
    """
    # 1) If value is None and null is allowed, return None
    if value is None:
        if allow_null:
            return None
        raise ValueError("FK field cannot be null unless allow_null=True.")

    # 2) If value is an integer, assume it's the primary key
    if isinstance(value, int):
        # Check if a record with that PK exists; if not raise or return None
        if model_class.objects.filter(pk=value).exists():
            return value
        else:
            msg = (f"No {model_class.__name__} found with {id_field}={value}.")
            if allow_null:
                print(msg)  # or debug_log
                return None
            raise ValueError(msg)

    # 3) If value is a string, assume it's the unique field (e.g. "name")
    if isinstance(value, str):
        try:
            obj = model_class.objects.get(**{name_field: value})
            return getattr(obj, id_field)
        except model_class.DoesNotExist:
            msg = (f"No {model_class.__name__} found with {name_field}='{value}'.")
            if allow_null:
                print(msg)
                return None
            raise ValueError(msg)

    # 4) If value is a dictionary, check if it has 'id' or 'name'
    if isinstance(value, dict):
        # If it has "id", try integer pk
        if "id" in value and value["id"] is not None:
            pk_candidate = value["id"]
            if not isinstance(pk_candidate, int):
                raise ValueError(
                    f"Expecting an integer 'id' in dict for {model_class.__name__}, got {pk_candidate}."
                )
            # Check if record exists
            if model_class.objects.filter(pk=pk_candidate).exists():
                return pk_candidate
            msg = (f"No {model_class.__name__} found with {id_field}={pk_candidate}.")
            if allow_null:
                print(msg)
                return None
            raise ValueError(msg)

        # If it has "name", treat as the unique field
        if name_field in value and value[name_field] is not None:
            name_candidate = value[name_field]
            try:
                obj = model_class.objects.get(**{name_field: name_candidate})
                return getattr(obj, id_field)
            except model_class.DoesNotExist:
                msg = (
                    f"No {model_class.__name__} found with {name_field}='{name_candidate}'."
                )
                if allow_null:
                    print(msg)
                    return None
                raise ValueError(msg)

        # If neither 'id' nor 'name' were provided, or both are null
        msg = (f"Dictionary provided for {model_class.__name__} but neither "
               f"'{id_field}' nor '{name_field}' could be resolved.")
        if allow_null:
            print(msg)
            return None
        raise ValueError(msg)

    # 5) If none of the above match, the value type is unsupported
    msg = (f"Unsupported type {type(value).__name__} for resolving "
           f"{model_class.__name__} FK. Expected int, str, or dict.")
    if allow_null:
        print(msg)
        return None
    raise ValueError(msg)

def create_payroll_transaction(payload):
    """
    Create a transaction based on payroll details.
    """
    transaction = Transaction.objects.create(
        company=payload['company'],
        date=payload['date'],
        entity_id=payload['entity_id'],
        description=f"Payroll for {payload['period']}",
        amount=payload['total_amount'],
        currency_id=payload['currency_id']
    )
    # Create associated journal entries
    JournalEntry.objects.create(
        transaction=transaction,
        account_id=payload['account_id'],
        debit_amount=payload['total_amount']
    )
    return transaction.id


def build_notes_metadata(
    source: str,
    filename: str = None,
    function: str = None,
    user: str = None,
    user_id: int = None,
    **kwargs
) -> str:
    """
    Build a formatted notes string with metadata about how a record was created.
    
    Note: This function excludes information that's already available in model fields:
    - created_by / updated_by (who created/edited)
    - created_at / updated_at (when created/edited)
    
    Args:
        source: Source of creation (e.g., "ETL", "Import", "API", "Manual")
        filename: Source filename if applicable (e.g., "2025.01.xlsx")
        function: Function/method that created the record (e.g., "execute_import_job", "ETLPipelineService._import_data")
        user: Username of the user who created it (deprecated - not included in notes)
        user_id: User ID (deprecated - not included in notes)
        **kwargs: Additional metadata fields (e.g., sheet_name, row_number, log_id, etc.)
    
    Returns:
        Formatted notes string with relevant metadata (excluding who/when created/edited)
    """
    parts = []
    
    # Source
    parts.append(f"Source: {source}")
    
    # Function/method
    if function:
        parts.append(f"Function: {function}")
    
    # Filename
    if filename:
        parts.append(f"File: {filename}")
    
    # Additional metadata (excluding user/user_id as they're in created_by/updated_by fields)
    for key, value in kwargs.items():
        if value is not None:
            # Format key nicely (e.g., "sheet_name" -> "Sheet Name")
            formatted_key = key.replace('_', ' ').title()
            parts.append(f"{formatted_key}: {value}")
    
    return "\n".join(parts)