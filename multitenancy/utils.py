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









'''
@action(detail=False, methods=['post'])
def match_many_to_many(self, request, tenant_id):
    """
    Many-to-many matching for reconciliation.
    
    Expected JSON payload:
    {
        "bank_filters": {
           "start_date": "2024-01-01",
           "end_date": "2024-01-31",
           "min_amount": 100,
           "max_amount": 1000
        },
        "book_filters": {
           "start_date": "2024-01-01",
           "end_date": "2024-01-31",
           "min_amount": 50,
           "max_amount": 500
        },
        "enforce_same_bank": true,
        "enforce_same_entity": true,
        "max_bank_entries": 2,
        "max_book_entries": 3,
        "amount_tolerance": 10.0,
        "date_tolerance_days": 2,
        "weight_date": 0.4,
        "weight_amount": 0.6,
        "max_suggestions": 3,
        "min_confidence": 0.0
    }
    
    Only records that are not already reconciled are considered.
    A record is considered reconciled if it has a related Reconciliation record with status "matched" or "approved".
    """
    data = request.data
    bank_filters = data.get("bank_filters", {})
    book_filters = data.get("book_filters", {})

    enforce_same_bank = data.get("enforce_same_bank", True)
    enforce_same_entity = data.get("enforce_same_entity", True)
    max_bank_entries = int(data.get("max_bank_entries", 1))
    max_book_entries = int(data.get("max_book_entries", 1))
    amount_tolerance = Decimal(str(data.get("amount_tolerance", "10.0")))
    date_tolerance_days = float(data.get("date_tolerance_days", 2))
    weight_date = float(data.get("weight_date", 0.4))
    weight_amount = float(data.get("weight_amount", 0.6))
    max_suggestions = int(data.get("max_suggestions", 10))
    min_confidence = float(data.get("min_confidence", 0.0))

    # --- STEP 1: Query Candidate Bank Transactions ---
    # Exclude bank transactions that have any reconciliation with status 'matched' or 'approved'
    bank_qs = self.queryset.exclude(reconciliations__status__in=['matched', 'approved'])
    if bank_filters.get("start_date"):
        bank_qs = bank_qs.filter(date__gte=bank_filters["start_date"])
    if bank_filters.get("end_date"):
        bank_qs = bank_qs.filter(date__lte=bank_filters["end_date"])
    if bank_filters.get("min_amount") is not None:
        bank_qs = bank_qs.filter(amount__gte=bank_filters["min_amount"])
    if bank_filters.get("max_amount") is not None:
        bank_qs = bank_qs.filter(amount__lte=bank_filters["max_amount"])
    candidate_bank = list(bank_qs.order_by('date'))
    # (Optional candidate limit can be applied here.)

    # --- STEP 2: Query Candidate Journal Entries (Book Side) ---
    from accounting.models import JournalEntry
    # Exclude journal entries that are already reconciled
    book_qs = JournalEntry.objects.exclude(reconciliations__status__in=['matched', 'approved'])
    if book_filters.get("start_date"):
        book_qs = book_qs.filter(transaction__date__gte=book_filters["start_date"])
    if book_filters.get("end_date"):
        book_qs = book_qs.filter(transaction__date__lte=book_filters["end_date"])
    if book_filters.get("min_amount") is not None:
        book_qs = book_qs.filter(
            Q(debit_amount__gte=book_filters["min_amount"]) | Q(credit_amount__gte=book_filters["min_amount"])
        )
    if book_filters.get("max_amount") is not None:
        book_qs = book_qs.filter(
            Q(debit_amount__lte=book_filters["max_amount"]) | Q(credit_amount__lte=book_filters["max_amount"])
        )
    candidate_book = list(book_qs.order_by('transaction__date'))
    # (Optional candidate limit can be applied here.)

    # --- STEP 3: Iterate over Combinations and Compute Scores ---
    suggestions = []
    for r_bank in range(1, max_bank_entries + 1):
        for bank_combo in combinations(candidate_bank, r_bank):
            sum_bank = sum(tx.amount for tx in bank_combo)
            if enforce_same_bank:
                bank_account_ids = {tx.bank_account.id for tx in bank_combo}
                if len(bank_account_ids) != 1:
                    continue
            if enforce_same_entity:
                bank_entity_ids = {tx.entity.id for tx in bank_combo if tx.entity}
                if len(bank_entity_ids) != 1:
                    continue

            filtered_candidate_book = candidate_book
            if enforce_same_bank and bank_combo:
                bank_account_id = next(iter({tx.bank_account.id for tx in bank_combo}))
                filtered_candidate_book = [entry for entry in candidate_book 
                                           if entry.account and entry.account.bank_account and entry.account.bank_account.id == bank_account_id]
            if enforce_same_entity and bank_combo:
                entity_id = next(iter({tx.entity.id for tx in bank_combo if tx.entity}))
                filtered_candidate_book = [entry for entry in filtered_candidate_book 
                                           if entry.entity and entry.entity.id == entity_id]

            # Use the recursive helper to generate journal entry combinations within tolerance.
            book_combos = find_book_combos(
                filtered_candidate_book,
                target=sum_bank,
                max_items=max_book_entries,
                tolerance=str(amount_tolerance)
            )

            for book_combo in book_combos:
                # Assume each JournalEntry has a method get_effective_amount() that accounts for account_direction.
                sum_book = sum(entry.get_effective_amount() for entry in book_combo)
                diff = abs(sum_bank - sum_book)
                if diff > amount_tolerance:
                    continue
                amount_score = max(0, 1 - (diff / amount_tolerance)) if amount_tolerance > 0 else (1 if diff == 0 else 0)
                
                date_diffs = [abs((tx.date - entry.transaction.date).days) for tx in bank_combo for entry in book_combo]
                avg_date_diff = sum(date_diffs) / len(date_diffs) if date_diffs else 0
                date_score = max(0, 1 - (avg_date_diff / date_tolerance_days)) if date_tolerance_days > 0 else (1 if avg_date_diff == 0 else 0)
                
                weight_amount_dec = Decimal(str(weight_amount))
                weight_date_dec = Decimal(str(weight_date))
                confidence_score = (weight_amount_dec * Decimal(str(amount_score))) + (weight_date_dec * Decimal(str(date_score)))
                
                
                suggestions.append({
                    "bank_transaction_ids": [tx.id for tx in bank_combo],
                    "bank_transactions": [{
                        "id": tx.id,
                        "date": tx.date,
                        "amount": tx.amount,
                        "bank_account_id": tx.bank_account.id,
                        "entity_id": tx.entity.id if tx.entity else None
                    } for tx in bank_combo],
                    "journal_entry_ids": [entry.id for entry in book_combo],
                    "journal_entries": [{
                        "id": entry.id,
                        "date": entry.transaction.date,
                        "amount": entry.get_amount(),  # raw amount; effective value is used in sum_book
                        "bank_account_id": entry.account.bank_account.id if entry.account and entry.account.bank_account else None,
                        "entity_id": entry.entity.id if entry.entity else None
                    } for entry in book_combo],
                    "sum_bank": sum_bank,
                    "sum_book": sum_book,
                    "difference": diff,
                    "avg_date_diff": avg_date_diff,
                    "confidence_score": float(confidence_score)
                })
    suggestions.sort(key=lambda x: x["confidence_score"], reverse=True)
    filtered_suggestions = [s for s in suggestions if s["confidence_score"] >= min_confidence]
    final_suggestions = filtered_suggestions[:max_suggestions]
    
    return Response({"suggestions": final_suggestions})

@action(detail=False, methods=['post'])
def match_many_to_many_with_set(self, request, tenant_id):
    """
    Many-to-many matching for reconciliation.
    
    Expected JSON payload:
    {
        "bank_filters": { ... },
        "book_filters": { ... },
        "enforce_same_bank": true,
        "enforce_same_entity": true,
        "max_bank_entries": 2,
        "max_book_entries": 3,
        "amount_tolerance": 10.0,
        "date_tolerance_days": 2,
        "weight_date": 0.4,
        "weight_amount": 0.6,
        "max_suggestions": 3,
        "min_confidence": 0.0,
        "bank_ids": [1, 2, 3],          // optional list of bank transaction IDs
        "bank_ids_strict": false,       // if true, candidate bank set is limited to these IDs
        "book_ids": [10, 20, 30],         // optional list of journal entry IDs
        "book_ids_strict": false         // if true, candidate book set is limited to these IDs
    }
    
    Only records that are not already reconciled are considered.
    A record is considered reconciled if it has a related Reconciliation record with status "matched" or "approved".
    """
    from decimal import Decimal
    from itertools import combinations
    from django.db.models import Q
    data = request.data
    print('data', data)
    bank_filters = data.get("bank_filters", {})
    book_filters = data.get("book_filters", {})
    
    enforce_same_bank = data.get("enforce_same_bank", True)
    enforce_same_entity = data.get("enforce_same_entity", True)
    max_bank_entries = int(data.get("max_bank_entries", 1))
    max_book_entries = int(data.get("max_book_entries", 1))
    amount_tolerance = Decimal(str(data.get("amount_tolerance", "10.0")))
    date_tolerance_days = float(data.get("date_tolerance_days", 2))
    weight_date = float(data.get("weight_date", 0.4))
    weight_amount = float(data.get("weight_amount", 0.6))
    max_suggestions = int(data.get("max_suggestions", 10))
    min_confidence = float(data.get("min_confidence", 0.0))

    # Optional: provided IDs for bank transactions and journal entries.
    provided_bank_ids = data.get("bank_ids", None)  # should be a list of ints
    if provided_bank_ids == []:
        provided_bank_ids = None
    strict_bank = data.get("bank_ids_strict", False)
    provided_book_ids = data.get("book_ids", None)  # should be a list of ints
    if provided_book_ids == []:
        provided_book_ids = None
    strict_book = data.get("book_ids_strict", False)

    # --- STEP 1: Query Candidate Bank Transactions ---
    bank_qs = self.queryset.exclude(reconciliations__status__in=['matched', 'approved'])
    if bank_filters.get("start_date"):
        bank_qs = bank_qs.filter(date__gte=bank_filters["start_date"])
    if bank_filters.get("end_date"):
        bank_qs = bank_qs.filter(date__lte=bank_filters["end_date"])
    if bank_filters.get("min_amount") is not None:
        bank_qs = bank_qs.filter(amount__gte=bank_filters["min_amount"])
    if bank_filters.get("max_amount") is not None:
        bank_qs = bank_qs.filter(amount__lte=bank_filters["max_amount"])
    if provided_bank_ids and strict_bank:
        bank_qs = bank_qs.filter(id__in=provided_bank_ids)
    candidate_bank = list(bank_qs.order_by('date'))
    
    # --- STEP 2: Query Candidate Journal Entries (Book Side) ---
    from accounting.models import JournalEntry
    book_qs = JournalEntry.objects.exclude(reconciliations__status__in=['matched', 'approved'])
    if book_filters.get("start_date"):
        book_qs = book_qs.filter(transaction__date__gte=book_filters["start_date"])
    if book_filters.get("end_date"):
        book_qs = book_qs.filter(transaction__date__lte=book_filters["end_date"])
    if book_filters.get("min_amount") is not None:
        book_qs = book_qs.filter(
            Q(debit_amount__gte=book_filters["min_amount"]) | Q(credit_amount__gte=book_filters["min_amount"])
        )
    if book_filters.get("max_amount") is not None:
        book_qs = book_qs.filter(
            Q(debit_amount__lte=book_filters["max_amount"]) | Q(credit_amount__lte=book_filters["max_amount"])
        )
    if provided_book_ids and strict_book:
        book_qs = book_qs.filter(transaction__id__in=provided_book_ids)
    candidate_book = list(book_qs.order_by('transaction__date'))

    # --- STEP 3: Iterate over Combinations and Compute Scores ---
    suggestions = []
    for r_bank in range(1, max_bank_entries + 1):
        for bank_combo in combinations(candidate_bank, r_bank):
            # If provided bank ids were given and not strict, ensure the match includes all provided bank IDs.
            if provided_bank_ids and not strict_bank:
                bank_combo_ids = {tx.id for tx in bank_combo}
                if not set(provided_bank_ids).issubset(bank_combo_ids):
                    continue

            sum_bank = sum(tx.amount for tx in bank_combo)
            if enforce_same_bank:
                bank_account_ids = {tx.bank_account.id for tx in bank_combo}
                if len(bank_account_ids) != 1:
                    continue
            if enforce_same_entity:
                bank_entity_ids = {tx.entity.id for tx in bank_combo if tx.entity}
                if len(bank_entity_ids) != 1:
                    continue

            filtered_candidate_book = candidate_book
            print(filtered_candidate_book)
            if enforce_same_bank and bank_combo:
                bank_account_id = next(iter({tx.bank_account.id for tx in bank_combo}))
                filtered_candidate_book = [entry for entry in candidate_book 
                                           if entry.account and entry.account.bank_account and entry.account.bank_account.id == bank_account_id]
            if enforce_same_entity and bank_combo:
                entity_id = next(iter({tx.entity.id for tx in bank_combo if tx.entity}))
                filtered_candidate_book = [entry for entry in filtered_candidate_book 
                                           if entry.entity and entry.entity.id == entity_id]

            # Use the recursive helper to generate journal entry combinations within tolerance.
            book_combos = find_book_combos(
                filtered_candidate_book,
                target=sum_bank,
                max_items=max_book_entries,
                tolerance=str(amount_tolerance)
            )
            
            print('================')
            print(book_combos)
            
            for book_combo in book_combos:
                # If provided book ids were given and not strict, ensure the match includes them.
                if provided_book_ids and not strict_book:
                    book_combo_ids = {entry.transaction.id for entry in book_combo}
                    if not set(provided_book_ids).issubset(book_combo_ids):
                        continue

                # Assume each JournalEntry has a method get_effective_amount() that adjusts by account_direction.
                sum_book = sum(entry.get_effective_amount() for entry in book_combo)
                diff = abs(sum_bank - sum_book)
                if diff > amount_tolerance:
                    continue
                amount_score = max(0, 1 - (diff / amount_tolerance)) if amount_tolerance > 0 else (1 if diff == 0 else 0)
                
                date_diffs = [abs((tx.date - entry.transaction.date).days) for tx in bank_combo for entry in book_combo]
                avg_date_diff = sum(date_diffs) / len(date_diffs) if date_diffs else 0
                date_score = max(0, 1 - (avg_date_diff / date_tolerance_days)) if date_tolerance_days > 0 else (1 if avg_date_diff == 0 else 0)
                
                weight_amount_dec = Decimal(str(weight_amount))
                weight_date_dec = Decimal(str(weight_date))
                confidence_score = (weight_amount_dec * Decimal(str(amount_score))) + (weight_date_dec * Decimal(str(date_score)))
                
                # Create bank transaction summary as a text field.
                bank_summary = ""
                bank_summary = " | ".join([
                    f"ID: {tx.id}, Date: {tx.date}, Amount: {tx.amount}, Desc: {tx.description}"
                    for tx in bank_combo
                ])
                # Create journal entries summary as a text field.
                journal_lines = []
                for tx in book_combo:
                    account_code = tx.account.account_code if tx.account else 'N/A'
                    account_name = tx.account.name if tx.account else 'N/A'
                    direction = 'DEBIT ' if tx.debit_amount else 'CREDIT '
                    debit = tx.debit_amount or 0
                    credit = tx.credit_amount or 0
                    amount = debit + credit
                    journal_lines.append(f"ID: {tx.transaction.id}, Date: {tx.transaction.date}, JE: {direction}{amount} - ({account_code}) {account_name}, Desc: {tx.transaction.description}")
                journal_summary = "\n".join(journal_lines)
                #journal_summary = ""
                #journal_summary = "\n".join([
                #    f"ID: {tx.transaction.id}, Date: {tx.transaction.date}, Desc: {tx.transaction.description}, JE: {direction}{amount} - ({account_code}) {account_name}"
                #    for tx in book_combo
                #])
                
                suggestions.append({
                    "bank_transaction_details": [{
                        "id": tx.id,
                        "date": tx.date,
                        "amount": tx.amount,
                        "description": tx.description,
                        "tx_hash": tx.tx_hash,
                        "bank_account": {
                            "id": tx.bank_account.id,
                            "name": tx.bank_account.name
                        },
                        "entity": tx.entity.id if tx.entity else None,
                        "currency": tx.currency.id
                    } for tx in bank_combo],
                    "journal_entry_details": [{
                        "id": entry.id,
                        "date": entry.transaction.date,
                        "amount": entry.get_amount(),
                        "account": {
                            "id": entry.account.id,
                            "account_code": entry.account.account_code,
                            "name": entry.account.name
                        } if entry.account else None,
                        "entity": {
                            "id": entry.entity.id,
                            "name": entry.entity.name
                        } if entry.entity else None,
                        "transaction": {
                            "id": entry.transaction.id,
                            "description": entry.transaction.description,
                            "date": entry.transaction.date
                        } if entry.transaction else None
                    } for entry in book_combo],
                    "bank_transaction_summary": bank_summary,
                    "bank_ids": [tx.id for tx in bank_combo],
                    "journal_entries_summary": journal_summary,
                    "journal_entries_ids": [tx.id for tx in book_combo],
                    "sum_bank": sum_bank,
                    "sum_book": sum_book,
                    "difference": diff,
                    "avg_date_diff": avg_date_diff,
                    "confidence_score": float(confidence_score)
                })
    suggestions.sort(key=lambda x: x["confidence_score"], reverse=True)
    filtered_suggestions = [s for s in suggestions if s["confidence_score"] >= min_confidence]
    final_suggestions = filtered_suggestions[:max_suggestions]

    return Response({"suggestions": final_suggestions})


@action(detail=False, methods=['post'])
def match_many_to_many_with_set2(self, request, tenant_id):
    """
    Optimized Many-to-Many Matching for reconciliation.
    Uses bipartite graph matching for best results while maintaining filtering.
    """
    data = request.data
    bank_filters = data.get("bank_filters", {})
    book_filters = data.get("book_filters", {})
    
    enforce_same_bank = data.get("enforce_same_bank", True)
    enforce_same_entity = data.get("enforce_same_entity", True)
    max_bank_entries = int(data.get("max_bank_entries", 2))
    max_book_entries = int(data.get("max_book_entries", 3))
    amount_tolerance = Decimal(str(data.get("amount_tolerance", "10.0")))
    date_tolerance_days = float(data.get("date_tolerance_days", 2))
    weight_date = float(data.get("weight_date", 0.4))
    weight_amount = float(data.get("weight_amount", 0.6))
    max_suggestions = int(data.get("max_suggestions", 10))
    min_confidence = float(data.get("min_confidence", 0.0))

    # Optional: provided IDs for filtering
    provided_bank_ids = data.get("bank_ids", None) or None
    strict_bank = data.get("bank_ids_strict", False)
    provided_book_ids = data.get("book_ids", None) or None
    strict_book = data.get("book_ids_strict", False)

    # STEP 1: Query Bank Transactions
    bank_qs = self.queryset.exclude(reconciliations__status__in=['matched', 'approved'])
    if bank_filters.get("start_date"):
        bank_qs = bank_qs.filter(date__gte=bank_filters["start_date"])
    if bank_filters.get("end_date"):
        bank_qs = bank_qs.filter(date__lte=bank_filters["end_date"])
    if bank_filters.get("min_amount") is not None:
        bank_qs = bank_qs.filter(amount__gte=bank_filters["min_amount"])
    if bank_filters.get("max_amount") is not None:
        bank_qs = bank_qs.filter(amount__lte=bank_filters["max_amount"])
    if provided_bank_ids and strict_bank:
        bank_qs = bank_qs.filter(id__in=provided_bank_ids)
    
    candidate_bank = list(bank_qs.order_by('date'))

    # STEP 2: Query Journal Entries
    from accounting.models import JournalEntry
    book_qs = JournalEntry.objects.exclude(reconciliations__status__in=['matched', 'approved'])
    if book_filters.get("start_date"):
        book_qs = book_qs.filter(transaction__date__gte=book_filters["start_date"])
    if book_filters.get("end_date"):
        book_qs = book_qs.filter(transaction__date__lte=book_filters["end_date"])
    if book_filters.get("min_amount") is not None:
        book_qs = book_qs.filter(
            Q(debit_amount__gte=book_filters["min_amount"]) | Q(credit_amount__gte=book_filters["min_amount"])
        )
    if book_filters.get("max_amount") is not None:
        book_qs = book_qs.filter(
            Q(debit_amount__lte=book_filters["max_amount"]) | Q(credit_amount__lte=book_filters["max_amount"])
        )
    if provided_book_ids and strict_book:
        book_qs = book_qs.filter(transaction__id__in=provided_book_ids)
    
    candidate_book = list(book_qs.order_by('transaction__date'))

    # STEP 3: Create Bipartite Graph
    G = nx.Graph()
    edge_metadata = {}  # Store transaction metadata separately
    
    for bank_tx, book_tx in product(candidate_bank, candidate_book):
        amount_diff = abs(bank_tx.amount - book_tx.get_effective_amount())
        date_diff = abs((bank_tx.date - book_tx.transaction.date).days)
    
        if amount_diff > amount_tolerance or date_diff > date_tolerance_days:
            continue  # Skip non-matching pairs
    
        amount_score = max(0, 1 - (amount_diff / amount_tolerance))
        date_score = max(0, 1 - (date_diff / date_tolerance_days))
        confidence_score = (Decimal(str(weight_amount)) * Decimal(str(amount_score))) + (Decimal(str(weight_date)) * Decimal(str(date_score)))
    
        if confidence_score >= min_confidence:
            bank_node = f"bank_{bank_tx.id}"
            book_node = f"book_{book_tx.id}"
    
            G.add_edge(bank_node, book_node, weight=float(1 - confidence_score))  # Store only numeric weight
    
            # Store metadata separately (to avoid object dtype errors)
            edge_metadata[(bank_node, book_node)] = {
                "bank": bank_tx,
                "book": book_tx,
                "confidence_score": confidence_score
            }
    
    # Define sets for bipartite graph
    bank_nodes = {n for n in G.nodes if str(n).startswith("bank_")}
    book_nodes = {n for n in G.nodes if str(n).startswith("book_")}
    
    # Ensure the graph has edges before trying to match
    if not G.edges:
        return Response({"suggestions": []})  # No matches possible
    
    # Solve the min-cost matching problem
    #matched_edges = nx.algorithms.bipartite.minimum_weight_full_matching(G, top_nodes=bank_nodes)
    matched_edges = nx.algorithms.bipartite.maximum_weight_matching(G, top_nodes=bank_nodes)
    
    # STEP 5: Process Matches
    suggestions = []
    for bank_node, book_node in matched_edges.items():
        metadata = edge_metadata.get((bank_node, book_node))  # Retrieve stored metadata
        
        # Skip if metadata does not exist (to prevent NoneType errors)
        if not metadata:
            continue
    
        bank_tx = metadata.get("bank")
        book_tx = metadata.get("book")
        confidence_score = metadata.get("confidence_score", 0)
    
        # Ensure bank_tx and book_tx are not None
        if not bank_tx or not book_tx:
            continue
    
        suggestions.append({
            "bank_transaction_details": {
                "id": bank_tx.id,
                "date": bank_tx.date,
                "amount": bank_tx.amount,
                "description": bank_tx.description
            },
            "journal_entry_details": {
                "id": book_tx.transaction.id,
                "date": book_tx.transaction.date,
                "amount": book_tx.get_effective_amount(),
                "account": {
                    "id": book_tx.account.id if book_tx.account else None,
                    "name": book_tx.account.name if book_tx.account else None
                }
            },
            "difference": abs(bank_tx.amount - book_tx.get_effective_amount()),
            "date_difference": abs((bank_tx.date - book_tx.transaction.date).days),
            "confidence_score": confidence_score
        })
    
    # Sort by confidence and limit to max_suggestions
    suggestions.sort(key=lambda x: x["confidence_score"], reverse=True)
    final_suggestions = suggestions[:max_suggestions]
    
    return Response({"suggestions": final_suggestions})


@action(detail=False, methods=['post'])
def match_many_to_many_with_set3(self, request, tenant_id):
    """
    Optimized many-to-many matching for reconciliation with optional ID restrictions and two matching strategies.
    
    Expected JSON payload:
    {
        "strategy": "full_screen" | "optimized",
        "bank_filters": { 
             "start_date": "2024-01-01",
             "end_date": "2024-01-31",
             "min_amount": 100,
             "max_amount": 1000 
        },
        "book_filters": { 
             "start_date": "2024-01-01",
             "end_date": "2024-01-31",
             "min_amount": 50,
             "max_amount": 500 
        },
        "enforce_same_bank": true,
        "enforce_same_entity": true,
        "max_bank_entries": 2,
        "max_book_entries": 3,
        "amount_tolerance": 100,
        "date_tolerance_days": 2,
        "weight_date": 0.4,
        "weight_amount": 0.6,
        "max_suggestions": 3,
        "min_confidence": 0.0,
        "bank_ids": [1, 2, 3],           // optional list of bank transaction IDs
        "bank_ids_strict": false,
        "book_ids": [10, 20, 30],         // optional list of JournalEntry.transaction IDs
        "book_ids_strict": false
    }
    
    Only records not already reconciled (i.e. with no Reconciliation record having status 'matched' or 'approved')
    are considered.
    """
    data = request.data
    strategy = data.get("strategy", "optimized")
    print("DEBUG: Matching strategy:", strategy)
    
    # Load parameters.
    bank_filters = data.get("bank_filters", {})
    book_filters = data.get("book_filters", {})
    enforce_same_bank = data.get("enforce_same_bank", True)
    enforce_same_entity = data.get("enforce_same_entity", True)
    max_bank_entries = int(data.get("max_bank_entries", 1))
    max_book_entries = int(data.get("max_book_entries", 1))
    user_amount_tolerance = Decimal(str(data.get("amount_tolerance", "100")))
    user_date_tolerance = float(data.get("date_tolerance_days", 2))
    weight_date = float(data.get("weight_date", 0.4))
    weight_amount = float(data.get("weight_amount", 0.6))
    max_suggestions = int(data.get("max_suggestions", 3))
    min_confidence = float(data.get("min_confidence", 0.0))
    
    provided_bank_ids = data.get("bank_ids", None)
    if provided_bank_ids == []:
        provided_bank_ids = None
    strict_bank = data.get("bank_ids_strict", False)
    provided_book_ids = data.get("book_ids", None)
    if provided_book_ids == []:
        provided_book_ids = None
    strict_book = data.get("book_ids_strict", False)
    
    print("DEBUG: Parameters loaded:")
    print("  Bank Filters:", bank_filters)
    print("  Book Filters:", book_filters)
    print("  enforce_same_bank:", enforce_same_bank, "enforce_same_entity:", enforce_same_entity)
    print("  max_bank_entries:", max_bank_entries, "max_book_entries:", max_book_entries)
    print("  amount_tolerance:", user_amount_tolerance, "date_tolerance_days:", user_date_tolerance)
    print("  provided_bank_ids:", provided_bank_ids, "strict_bank:", strict_bank)
    print("  provided_book_ids:", provided_book_ids, "strict_book:", strict_book)
    
    # --- STEP 1: Query Candidate Bank Transactions ---
    bank_qs = self.queryset.exclude(reconciliations__status__in=['matched', 'approved'])
    if bank_filters.get("start_date"):
        bank_qs = bank_qs.filter(date__gte=bank_filters["start_date"])
    if bank_filters.get("end_date"):
        bank_qs = bank_qs.filter(date__lte=bank_filters["end_date"])
    if bank_filters.get("min_amount") is not None:
        bank_qs = bank_qs.filter(amount__gte=bank_filters["min_amount"])
    if bank_filters.get("max_amount") is not None:
        bank_qs = bank_qs.filter(amount__lte=bank_filters["max_amount"])
    if provided_bank_ids and strict_bank:
        bank_qs = bank_qs.filter(id__in=provided_bank_ids)
    candidate_bank = list(bank_qs.order_by('date'))
    print("DEBUG: Candidate bank transactions count:", len(candidate_bank))
    if not provided_bank_ids:
        candidate_bank = candidate_bank[:20]
    
    # --- STEP 2: Query Candidate Journal Entries ---
    from accounting.models import JournalEntry
    book_qs = JournalEntry.objects.exclude(reconciliations__status__in=['matched', 'approved'])
    if book_filters.get("start_date"):
        book_qs = book_qs.filter(transaction__date__gte=book_filters["start_date"])
    if book_filters.get("end_date"):
        book_qs = book_qs.filter(transaction__date__lte=book_filters["end_date"])
    if book_filters.get("min_amount") is not None:
        book_qs = book_qs.filter(Q(debit_amount__gte=book_filters["min_amount"]) | Q(credit_amount__gte=book_filters["min_amount"]))
    if book_filters.get("max_amount") is not None:
        book_qs = book_qs.filter(Q(debit_amount__lte=book_filters["max_amount"]) | Q(credit_amount__lte=book_filters["max_amount"]))
    if provided_book_ids and strict_book:
        book_qs = book_qs.filter(transaction__id__in=provided_book_ids)
    candidate_book = list(book_qs.order_by('transaction__date'))
    print("DEBUG: Candidate journal entries count:", len(candidate_book))
    if not provided_book_ids:
        candidate_book = candidate_book[:20]
    
    # --- STEP 3: Pre-Bucket the Records by Mandatory Keys ---
    def bucket_bank(tx):
        key = ""
        if enforce_same_bank and tx.bank_account:
            key += f"bank:{tx.bank_account.id}-"
        if enforce_same_entity and tx.entity:
            key += f"entity:{tx.entity.id}"
        return key or "default"
    
    def bucket_book(entry):
        key = ""
        if enforce_same_bank and entry.account and entry.account.bank_account:
            key += f"bank:{entry.account.bank_account.id}-"
        if enforce_same_entity and entry.entity:
            key += f"entity:{entry.entity.id}"
        return key or "default"
    
    bank_buckets = {}
    for tx in candidate_bank:
        key = bucket_bank(tx)
        bank_buckets.setdefault(key, []).append(tx)
    book_buckets = {}
    for entry in candidate_book:
        key = bucket_book(entry)
        book_buckets.setdefault(key, []).append(entry)
    
    print("DEBUG: Bank buckets created:", {k: len(v) for k, v in bank_buckets.items()})
    print("DEBUG: Book buckets created:", {k: len(v) for k, v in book_buckets.items()})
    
    # --- STEP 4: Optimized Matching Functions ---
    def optimized_one_to_one(bank_list, book_list):
        local_matches = []
        steps = 5
        for step in range(1, steps + 1):
            current_amt_tol = user_amount_tolerance * Decimal(step) / Decimal(steps)
            current_date_tol = user_date_tolerance * (step / steps)
            print(f"DEBUG [1-to-1]: Step {step}: Amt tol={current_amt_tol}, Date tol={current_date_tol}")
            for bank_tx in bank_list:
                for book_entry in book_list:
                    if enforce_same_bank:
                        if not (bank_tx.bank_account and book_entry.account and book_entry.account.bank_account and bank_tx.bank_account.id == book_entry.account.bank_account.id):
                            continue
                    if enforce_same_entity:
                        if not (bank_tx.entity and book_entry.entity and bank_tx.entity.id == book_entry.entity.id):
                            continue
                    amt_diff = abs(bank_tx.amount - book_entry.get_effective_amount())
                    date_diff = abs((bank_tx.date - book_entry.transaction.date).days)
                    print(f"DEBUG [1-to-1]: Comparing Bank TX {bank_tx.id} with Book Entry {book_entry.id}: amt_diff={amt_diff}, date_diff={date_diff}")
                    if amt_diff <= current_amt_tol and date_diff <= current_date_tol:
                        # Check provided IDs if not strict.
                        if provided_bank_ids and not strict_bank:
                            if not set(provided_bank_ids).issubset({bank_tx.id}):
                                continue
                        if provided_book_ids and not strict_book:
                            if not set(provided_book_ids).issubset({book_entry.transaction.id}):
                                continue
                        amount_score = float(max(0, 1 - (amt_diff / current_amt_tol))) if current_amt_tol > 0 else (1 if amt_diff == 0 else 0)
                        date_score = float(max(0, 1 - (date_diff / current_date_tol))) if current_date_tol > 0 else (1 if date_diff == 0 else 0)
                        confidence = weight_amount * amount_score + weight_date * date_score
                        print(f"DEBUG [1-to-1]: Found match: Bank TX {bank_tx.id} & Book Entry {book_entry.id} (confidence={confidence})")
                        match = {
                            "bank_transaction_details": [{
                                "id": bank_tx.id,
                                "date": bank_tx.date,
                                "amount": bank_tx.amount,
                                "description": bank_tx.description,
                                "tx_hash": bank_tx.tx_hash,
                                "bank_account": {"id": bank_tx.bank_account.id, "name": bank_tx.bank_account.name},
                                "entity": bank_tx.entity.id if bank_tx.entity else None,
                                "currency": bank_tx.currency.id
                            }],
                            "journal_entry_details": [{
                                "id": book_entry.id,
                                "date": book_entry.transaction.date,
                                "amount": book_entry.get_effective_amount(),
                                #"memo": book_entry.memo,
                                "account": {
                                    "id": book_entry.account.id,
                                    "account_code": book_entry.account.account_code,
                                    "name": book_entry.account.name
                                } if book_entry.account else None,
                                "entity": {
                                    "id": book_entry.entity.id,
                                    "name": book_entry.entity.name
                                } if book_entry.entity else None,
                                "transaction": {
                                    "id": book_entry.transaction.id,
                                    "description": book_entry.transaction.description,
                                    "date": book_entry.transaction.date
                                } if book_entry.transaction else None
                            }],
                            "bank_transaction_summary": f"ID: {bank_tx.id}, Date: {bank_tx.date}, Amount: {bank_tx.amount}, Desc: {bank_tx.description}",
                            "journal_entries_summary": f"ID: {book_entry.transaction.id}, Date: {book_entry.transaction.date}, JE: {('DEBIT' if book_entry.debit_amount else 'CREDIT')} {book_entry.get_effective_amount()} - ({book_entry.account.account_code if book_entry.account else 'N/A'}) {book_entry.account.name if book_entry.account else 'N/A'}, Desc: {book_entry.transaction.description}",
                            "bank_ids": [bank_tx.id],
                            "journal_entries_ids": [book_entry.id],
                            "sum_bank": bank_tx.amount,
                            "sum_book": book_entry.get_effective_amount(),
                            "difference": float(amt_diff),
                            "avg_date_diff": date_diff,
                            "confidence_score": confidence
                        }
                        local_matches.append(match)
            if local_matches:
                print(f"DEBUG [1-to-1]: Matches found at step {step}: {len(local_matches)}")
                return local_matches
        return local_matches

    def optimized_combination_matches(bank_list, book_list):
        local_matches = []
        for r_bank in range(1, max_bank_entries + 1):
            for bank_combo in combinations(bank_list, r_bank):
                if provided_bank_ids and not strict_bank:
                    if not set(provided_bank_ids).issubset({tx.id for tx in bank_combo}):
                        continue
                sum_bank = sum(tx.amount for tx in bank_combo)
                if enforce_same_bank and len({tx.bank_account.id for tx in bank_combo}) != 1:
                    continue
                if enforce_same_entity and len({tx.entity.id for tx in bank_combo if tx.entity}) != 1:
                    continue
                filtered_book = book_list
                if enforce_same_bank and bank_combo:
                    const_bank_account_id = bank_combo[0].bank_account.id
                    filtered_book = [entry for entry in book_list if entry.account and entry.account.bank_account and entry.account.bank_account.id == const_bank_account_id]
                if enforce_same_entity and bank_combo:
                    const_entity = bank_combo[0].entity
                    if const_entity:
                        filtered_book = [entry for entry in filtered_book if entry.entity and entry.entity.id == const_entity.id]
                for r_book in range(1, max_book_entries + 1):
                    for book_combo in combinations(filtered_book, r_book):
                        if provided_book_ids and not strict_book:
                            if not set(provided_book_ids).issubset({entry.transaction.id for entry in book_combo}):
                                continue
                        sum_book = sum(entry.get_effective_amount() for entry in book_combo)
                        diff = abs(sum_bank - sum_book)
                        if diff > user_amount_tolerance:
                            continue
                        date_diffs = [abs((tx.date - entry.transaction.date).days) for tx in bank_combo for entry in book_combo]
                        avg_date_diff = sum(date_diffs) / len(date_diffs) if date_diffs else 0
                        if avg_date_diff > user_date_tolerance:
                            continue
                        amount_score = float(max(0, 1 - (diff / user_amount_tolerance))) if user_amount_tolerance > 0 else (1 if diff == 0 else 0)
                        date_score = float(max(0, 1 - (avg_date_diff / user_date_tolerance))) if user_date_tolerance > 0 else (1 if avg_date_diff == 0 else 0)
                        weight_amount_dec = Decimal(str(weight_amount))
                        weight_date_dec = Decimal(str(weight_date))
                        # Using the to_string() method may vary by Decimal version; use str() if needed.
                        confidence_score = float((weight_amount_dec * Decimal(str(amount_score)) + weight_date_dec * Decimal(str(date_score))))
        
                        bank_summary = " | ".join([f"ID: {tx.id}, Date: {tx.date}, Amount: {tx.amount}, Desc: {tx.description}" for tx in bank_combo])
                        journal_lines = []
                        for entry in book_combo:
                            account_code = entry.account.account_code if entry.account else 'N/A'
                            account_name = entry.account.name if entry.account else 'N/A'
                            direction = 'DEBIT' if entry.debit_amount else 'CREDIT'
                            journal_lines.append(f"ID: {entry.transaction.id}, Date: {entry.transaction.date}, JE: {direction} {entry.get_effective_amount()} - ({account_code}) {account_name}, Desc: {entry.transaction.description}")
                        journal_summary = "\n".join(journal_lines)
        
                        local_matches.append({
                            "bank_transaction_details": [{
                                "id": tx.id,
                                "date": tx.date,
                                "amount": tx.amount,
                                "description": tx.description,
                                "tx_hash": tx.tx_hash,
                                "bank_account": {"id": tx.bank_account.id, "name": tx.bank_account.name},
                                "entity": tx.entity.id if tx.entity else None,
                                "currency": tx.currency.id
                            } for tx in bank_combo],
                            "journal_entry_details": [{
                                "id": entry.id,
                                "date": entry.transaction.date,
                                "amount": entry.get_amount(),
                                "memo": entry.memo,
                                "account": {
                                    "id": entry.account.id,
                                    "account_code": entry.account.account_code,
                                    "name": entry.account.name
                                } if entry.account else None,
                                "entity": {
                                    "id": entry.entity.id,
                                    "name": entry.entity.name
                                } if entry.entity else None,
                                "transaction": {
                                    "id": entry.transaction.id,
                                    "description": entry.transaction.description,
                                    "date": entry.transaction.date
                                } if entry.transaction else None
                            } for entry in book_combo],
                            "bank_transaction_summary": bank_summary,
                            "journal_entries_summary": journal_summary,
                            "bank_ids": [tx.id for tx in bank_combo],
                            "journal_entries_ids": [entry.id for entry in book_combo],
                            "sum_bank": sum_bank,
                            "sum_book": sum_book,
                            "difference": float(diff),
                            "avg_date_diff": avg_date_diff,
                            "confidence_score": confidence_score
                        })
                        print(f"DEBUG [combination]: Bank IDs {[tx.id for tx in bank_combo]}, Book IDs {[entry.id for entry in book_combo]}, confidence: {confidence_score}")
        if local_matches:
            print("DEBUG [combination]: Total matches found:", len(local_matches))
        else:
            print("DEBUG [combination]: No combination matches found.")
        return local_matches
    
    # --- STEP 5: Main Matching Logic ---
    suggestions = []
    # Pre-bucket candidate records by mandatory keys.
    bank_buckets = {}
    for tx in candidate_bank:
        key = ""
        if enforce_same_bank and tx.bank_account:
            key += f"bank:{tx.bank_account.id}-"
        if enforce_same_entity and tx.entity:
            key += f"entity:{tx.entity.id}"
        key = key or "default"
        bank_buckets.setdefault(key, []).append(tx)
    
    book_buckets = {}
    for entry in candidate_book:
        key = ""
        if enforce_same_bank and entry.account and entry.account.bank_account:
            key += f"bank:{entry.account.bank_account.id}-"
        if enforce_same_entity and entry.entity:
            key += f"entity:{entry.entity.id}"
        key = key or "default"
        book_buckets.setdefault(key, []).append(entry)
    
    print("DEBUG: Bank buckets:", {k: len(v) for k, v in bank_buckets.items()})
    print("DEBUG: Book buckets:", {k: len(v) for k, v in book_buckets.items()})
    
    if strategy == "optimized":
        for bucket_key, bank_list in bank_buckets.items():
            if bucket_key in book_buckets:
                book_list = book_buckets[bucket_key]
                bucket_matches = optimized_one_to_one(bank_list, book_list)
                if not bucket_matches:
                    bucket_matches = optimized_combination_matches(bank_list, book_list)
                if bucket_matches:
                    bucket_matches.sort(key=lambda x: x["confidence_score"], reverse=True)
                    suggestions.extend(bucket_matches[:max_suggestions])
    else:
        suggestions = optimized_combination_matches(candidate_bank, candidate_book)
    
    # --- STEP 6: Group suggestions by bank combination and remove duplicates.
    # If duplicates exist for a bank combination key, exclude them altogether.
    grouped = {}
    for suggestion in suggestions:
        key = "-".join(sorted(str(id) for id in suggestion["bank_ids"]))
        grouped.setdefault(key, []).append(suggestion)
    unique_suggestions = []
    for key, group in grouped.items():
        if len(group) == 1:
            unique_suggestions.append(group[0])
        else:
            print(f"DEBUG: Duplicate match for bank IDs {key} found; excluding these matches.")
    unique_suggestions.sort(key=lambda x: x["confidence_score"], reverse=True)
    print("DEBUG: Final unique suggestions count:", len(unique_suggestions))
    
    return Response({"suggestions": unique_suggestions})


@action(detail=False, methods=['post'])
def match_many_to_many_with_set4(self, request, tenant_id):
    """
    Optimized many-to-many matching for reconciliation with optional ID restrictions and two matching strategies.
    
    Expected JSON payload:
    {
        "strategy": "full_screen" | "optimized",
        "bank_filters": { 
             "start_date": "2024-01-01",
             "end_date": "2024-01-31",
             "min_amount": 100,
             "max_amount": 1000 
        },
        "book_filters": { 
             "start_date": "2024-01-01",
             "end_date": "2024-01-31",
             "min_amount": 50,
             "max_amount": 500 
        },
        "enforce_same_bank": true,
        "enforce_same_entity": true,
        "max_bank_entries": 2,
        "max_book_entries": 3,
        "amount_tolerance": 100,
        "date_tolerance_days": 2,
        "weight_date": 0.4,
        "weight_amount": 0.6,
        "max_suggestions": 3,
        "min_confidence": 0.0,
        "bank_ids": [1, 2, 3],
        "bank_ids_strict": false,
        "book_ids": [10, 20, 30],
        "book_ids_strict": false
    }
    
    Only records not already reconciled (i.e. with no Reconciliation record having status 'matched' or 'approved')
    are considered.
    """
    data = request.data
    strategy = data.get("strategy", "optimized")
    print("DEBUG: Matching strategy:", strategy)
    
    # Load parameters.
    bank_filters = data.get("bank_filters", {})
    book_filters = data.get("book_filters", {})
    enforce_same_bank = data.get("enforce_same_bank", True)
    enforce_same_entity = data.get("enforce_same_entity", True)
    max_bank_entries = int(data.get("max_bank_entries", 1))
    max_book_entries = int(data.get("max_book_entries", 1))
    user_amount_tolerance = Decimal(str(data.get("amount_tolerance", "100")))
    user_date_tolerance = float(data.get("date_tolerance_days", 2))
    weight_date = float(data.get("weight_date", 0.4))
    weight_amount = float(data.get("weight_amount", 0.6))
    max_suggestions = int(data.get("max_suggestions", 3))
    min_confidence = float(data.get("min_confidence", 0.0))
    
    provided_bank_ids = data.get("bank_ids", None)
    if provided_bank_ids == []:
        provided_bank_ids = None
    strict_bank = data.get("bank_ids_strict", False)
    provided_book_ids = data.get("book_ids", None)
    if provided_book_ids == []:
        provided_book_ids = None
    strict_book = data.get("book_ids_strict", False)
    
    print("DEBUG: Parameters loaded:")
    print("  Bank Filters:", bank_filters)
    print("  Book Filters:", book_filters)
    print("  enforce_same_bank:", enforce_same_bank, "enforce_same_entity:", enforce_same_entity)
    print("  max_bank_entries:", max_bank_entries, "max_book_entries:", max_book_entries)
    print("  amount_tolerance:", user_amount_tolerance, "date_tolerance_days:", user_date_tolerance)
    print("  provided_bank_ids:", provided_bank_ids, "strict_bank:", strict_bank)
    print("  provided_book_ids:", provided_book_ids, "strict_book:", strict_book)
    
    # --- STEP 1: Query Candidate Bank Transactions ---
    bank_qs = self.queryset.exclude(reconciliations__status__in=['matched', 'approved'])
    if bank_filters.get("start_date"):
        bank_qs = bank_qs.filter(date__gte=bank_filters["start_date"])
    if bank_filters.get("end_date"):
        bank_qs = bank_qs.filter(date__lte=bank_filters["end_date"])
    if bank_filters.get("min_amount") is not None:
        bank_qs = bank_qs.filter(amount__gte=bank_filters["min_amount"])
    if bank_filters.get("max_amount") is not None:
        bank_qs = bank_qs.filter(amount__lte=bank_filters["max_amount"])
    if provided_bank_ids and strict_bank:
        bank_qs = bank_qs.filter(id__in=provided_bank_ids)
    candidate_bank = list(bank_qs.order_by('date'))
    print("DEBUG: Candidate bank transactions count:", len(candidate_bank))
    if not provided_bank_ids:
        candidate_bank = candidate_bank[:20]  # Limit candidate set if not explicitly filtered
    
    # --- STEP 2: Query Candidate Journal Entries ---
    from accounting.models import JournalEntry
    book_qs = JournalEntry.objects.exclude(reconciliations__status__in=['matched', 'approved'])
    if book_filters.get("start_date"):
        book_qs = book_qs.filter(transaction__date__gte=book_filters["start_date"])
    if book_filters.get("end_date"):
        book_qs = book_qs.filter(transaction__date__lte=book_filters["end_date"])
    if book_filters.get("min_amount") is not None:
        book_qs = book_qs.filter(Q(debit_amount__gte=book_filters["min_amount"]) | Q(credit_amount__gte=book_filters["min_amount"]))
    if book_filters.get("max_amount") is not None:
        book_qs = book_qs.filter(Q(debit_amount__lte=book_filters["max_amount"]) | Q(credit_amount__lte=book_filters["max_amount"]))
    if provided_book_ids and strict_book:
        book_qs = book_qs.filter(transaction__id__in=provided_book_ids)
    candidate_book = list(book_qs.order_by('transaction__date'))
    print("DEBUG: Candidate journal entries count:", len(candidate_book))
    if not provided_book_ids:
        candidate_book = candidate_book[:20]
    
    # --- STEP 3: Pre-Bucket the Records by Mandatory Keys ---
    def bucket_bank(tx):
        key = ""
        if enforce_same_bank and tx.bank_account:
            key += f"bank:{tx.bank_account.id}-"
        if enforce_same_entity and tx.entity:
            key += f"entity:{tx.entity.id}"
        return key or "default"
    
    def bucket_book(entry):
        key = ""
        if enforce_same_bank and entry.account and entry.account.bank_account:
            key += f"bank:{entry.account.bank_account.id}-"
        if enforce_same_entity and entry.entity:
            key += f"entity:{entry.entity.id}"
        return key or "default"
    
    bank_buckets = {}
    for tx in candidate_bank:
        key = bucket_bank(tx)
        bank_buckets.setdefault(key, []).append(tx)
    book_buckets = {}
    for entry in candidate_book:
        key = bucket_book(entry)
        book_buckets.setdefault(key, []).append(entry)
    
    print("DEBUG: Bank buckets created:", {k: len(v) for k, v in bank_buckets.items()})
    print("DEBUG: Book buckets created:", {k: len(v) for k, v in book_buckets.items()})
    
    # --- STEP 4: Optimized Matching Functions ---
    def optimized_one_to_one(bank_list, book_list):
        local_matches = []
        steps = 5
        for step in range(1, steps + 1):
            current_amt_tol = user_amount_tolerance * Decimal(step) / Decimal(steps)
            current_date_tol = user_date_tolerance * (step / steps)
            print(f"DEBUG [1-to-1]: Step {step}: Amt tol={current_amt_tol}, Date tol={current_date_tol}")
            for bank_tx in bank_list:
                for book_entry in book_list:
                    # Enforce same bank and entity if required.
                    if enforce_same_bank:
                        if not (bank_tx.bank_account and book_entry.account and book_entry.account.bank_account and bank_tx.bank_account.id == book_entry.account.bank_account.id):
                            continue
                    if enforce_same_entity:
                        if not (bank_tx.entity and book_entry.entity and bank_tx.entity.id == book_entry.entity.id):
                            continue
                    amt_diff = abs(bank_tx.amount - book_entry.get_effective_amount())
                    date_diff = abs((bank_tx.date - book_entry.transaction.date).days)
                    print(f"DEBUG [1-to-1]: Comparing Bank TX {bank_tx.id} with Book Entry {book_entry.id}: amt_diff={amt_diff}, date_diff={date_diff}")
                    if amt_diff <= current_amt_tol and date_diff <= current_date_tol:
                        # Check provided IDs if not strict.
                        if provided_bank_ids and not strict_bank:
                            if not set(provided_bank_ids).issubset({bank_tx.id}):
                                continue
                        if provided_book_ids and not strict_book:
                            if not set(provided_book_ids).issubset({book_entry.transaction.id}):
                                continue
                        amount_score = float(max(0, 1 - (amt_diff / current_amt_tol))) if current_amt_tol > 0 else (1 if amt_diff == 0 else 0)
                        date_score = float(max(0, 1 - (date_diff / current_date_tol))) if current_date_tol > 0 else (1 if date_diff == 0 else 0)
                        confidence = weight_amount * amount_score + weight_date * date_score
                        print(f"DEBUG [1-to-1]: Found match: Bank TX {bank_tx.id} & Book Entry {book_entry.id} (confidence={confidence})")
                        match = {
                            "bank_transaction_details": [{
                                "id": bank_tx.id,
                                "date": bank_tx.date,
                                "amount": bank_tx.amount,
                                "description": bank_tx.description,
                                "tx_hash": bank_tx.tx_hash,
                                "bank_account": {"id": bank_tx.bank_account.id, "name": bank_tx.bank_account.name} if bank_tx.bank_account else None,
                                "entity": bank_tx.entity.id if bank_tx.entity else None,
                                "currency": bank_tx.currency.id
                            }],
                            "journal_entry_details": [{
                                "id": book_entry.id,
                                "date": book_entry.transaction.date,
                                "amount": book_entry.get_effective_amount(),
                                "account": {
                                    "id": book_entry.account.id,
                                    "account_code": book_entry.account.account_code,
                                    "name": book_entry.account.name
                                } if book_entry.account else None,
                                "entity": {
                                    "id": book_entry.entity.id,
                                    "name": book_entry.entity.name
                                } if book_entry.entity else None,
                                "transaction": {
                                    "id": book_entry.transaction.id,
                                    "description": book_entry.transaction.description,
                                    "date": book_entry.transaction.date
                                } if book_entry.transaction else None
                            }],
                            "bank_transaction_summary": f"ID: {bank_tx.id}, Date: {bank_tx.date}, Amount: {bank_tx.amount}, Desc: {bank_tx.description}",
                            "journal_entries_summary": f"ID: {book_entry.transaction.id}, Date: {book_entry.transaction.date}, JE: {('DEBIT' if book_entry.debit_amount else 'CREDIT')} {book_entry.get_effective_amount()} - ({book_entry.account.account_code if book_entry.account else 'N/A'}) {book_entry.account.name if book_entry.account else 'N/A'}, Desc: {book_entry.transaction.description}",
                            "bank_ids": [bank_tx.id],
                            "journal_entries_ids": [book_entry.id],
                            "sum_bank": bank_tx.amount,
                            "sum_book": book_entry.get_effective_amount(),
                            "difference": float(amt_diff),
                            "avg_date_diff": date_diff,
                            "confidence_score": confidence
                        }
                        local_matches.append(match)
            if local_matches:
                print(f"DEBUG [1-to-1]: Matches found at step {step}: {len(local_matches)}")
                return local_matches
        return local_matches

    def optimized_combination_matches(bank_list, book_list):
        local_matches = []
        for r_bank in range(1, max_bank_entries + 1):
            for bank_combo in combinations(bank_list, r_bank):
                if provided_bank_ids and not strict_bank:
                    if not set(provided_bank_ids).issubset({tx.id for tx in bank_combo}):
                        continue
                sum_bank = sum(tx.amount for tx in bank_combo)
                if enforce_same_bank and len({tx.bank_account.id for tx in bank_combo}) != 1:
                    continue
                if enforce_same_entity and len({tx.entity.id for tx in bank_combo if tx.entity}) != 1:
                    continue
                filtered_book = book_list
                if enforce_same_bank and bank_combo:
                    const_bank_account_id = bank_combo[0].bank_account.id
                    filtered_book = [entry for entry in book_list if entry.account and entry.account.bank_account and entry.account.bank_account.id == const_bank_account_id]
                if enforce_same_entity and bank_combo:
                    const_entity = bank_combo[0].entity
                    if const_entity:
                        filtered_book = [entry for entry in filtered_book if entry.entity and entry.entity.id == const_entity.id]
                for r_book in range(1, max_book_entries + 1):
                    for book_combo in combinations(filtered_book, r_book):
                        if provided_book_ids and not strict_book:
                            if not set(provided_book_ids).issubset({entry.transaction.id for entry in book_combo}):
                                continue
                        sum_book = sum(entry.get_effective_amount() for entry in book_combo)
                        diff = abs(sum_bank - sum_book)
                        if diff > user_amount_tolerance:
                            continue
                        date_diffs = [abs((tx.date - entry.transaction.date).days) for tx in bank_combo for entry in book_combo]
                        avg_date_diff = sum(date_diffs) / len(date_diffs) if date_diffs else 0
                        if avg_date_diff > user_date_tolerance:
                            continue
                        amount_score = float(max(0, 1 - (diff / user_amount_tolerance))) if user_amount_tolerance > 0 else (1 if diff == 0 else 0)
                        date_score = float(max(0, 1 - (avg_date_diff / user_date_tolerance))) if user_date_tolerance > 0 else (1 if avg_date_diff == 0 else 0)
                        confidence_score = float((Decimal(str(weight_amount)) * Decimal(str(amount_score)) + Decimal(str(weight_date)) * Decimal(str(date_score))))
            
                        bank_summary = " | ".join([f"ID: {tx.id}, Date: {tx.date}, Amount: {tx.amount}, Desc: {tx.description}" for tx in bank_combo])
                        journal_lines = []
                        for entry in book_combo:
                            account_code = entry.account.account_code if entry.account else 'N/A'
                            account_name = entry.account.name if entry.account else 'N/A'
                            direction = 'DEBIT' if entry.debit_amount else 'CREDIT'
                            journal_lines.append(f"ID: {entry.transaction.id}, Date: {entry.transaction.date}, JE: {direction} {entry.get_effective_amount()} - ({account_code}) {account_name}, Desc: {entry.transaction.description}")
                        journal_summary = "\n".join(journal_lines)
            
                        local_matches.append({
                            "bank_transaction_details": [{
                                "id": tx.id,
                                "date": tx.date,
                                "amount": tx.amount,
                                "description": tx.description,
                                "tx_hash": tx.tx_hash,
                                "bank_account": {"id": tx.bank_account.id, "name": tx.bank_account.name} if tx.bank_account else None,
                                "entity": tx.entity.id if tx.entity else None,
                                "currency": tx.currency.id
                            } for tx in bank_combo],
                            "journal_entry_details": [{
                                "id": entry.id,
                                "date": entry.transaction.date,
                                "amount": entry.get_effective_amount(),
                                "memo": entry.memo,
                                "account": {
                                    "id": entry.account.id,
                                    "account_code": entry.account.account_code,
                                    "name": entry.account.name
                                } if entry.account else None,
                                "entity": {
                                    "id": entry.entity.id,
                                    "name": entry.entity.name
                                } if entry.entity else None,
                                "transaction": {
                                    "id": entry.transaction.id,
                                    "description": entry.transaction.description,
                                    "date": entry.transaction.date
                                } if entry.transaction else None
                            } for entry in book_combo],
                            "bank_transaction_summary": bank_summary,
                            "journal_entries_summary": journal_summary,
                            "bank_ids": [tx.id for tx in bank_combo],
                            "journal_entries_ids": [entry.id for entry in book_combo],
                            "sum_bank": sum_bank,
                            "sum_book": sum_book,
                            "difference": float(diff),
                            "avg_date_diff": avg_date_diff,
                            "confidence_score": confidence_score
                        })
                        print(f"DEBUG [combination]: Bank IDs {[tx.id for tx in bank_combo]}, Book IDs {[entry.id for entry in book_combo]}, confidence: {confidence_score}")
        if local_matches:
            print("DEBUG [combination]: Total combination matches found:", len(local_matches))
        else:
            print("DEBUG [combination]: No combination matches found.")
        return local_matches
    
    # --- STEP 5: Main Matching Logic ---
    suggestions = []
    # Pre-bucket candidate records by mandatory keys.
    bank_buckets = {}
    for tx in candidate_bank:
        key = ""
        if enforce_same_bank and tx.bank_account:
            key += f"bank:{tx.bank_account.id}-"
        if enforce_same_entity and tx.entity:
            key += f"entity:{tx.entity.id}"
        key = key or "default"
        bank_buckets.setdefault(key, []).append(tx)
    
    book_buckets = {}
    for entry in candidate_book:
        key = ""
        if enforce_same_bank and entry.account and entry.account.bank_account:
            key += f"bank:{entry.account.bank_account.id}-"
        if enforce_same_entity and entry.entity:
            key += f"entity:{entry.entity.id}"
        key = key or "default"
        book_buckets.setdefault(key, []).append(entry)
    
    print("DEBUG: Bank buckets:", {k: len(v) for k, v in bank_buckets.items()})
    print("DEBUG: Book buckets:", {k: len(v) for k, v in book_buckets.items()})
    
    if strategy == "optimized":
        for bucket_key, bank_list in bank_buckets.items():
            if bucket_key in book_buckets:
                book_list = book_buckets[bucket_key]
                bucket_matches = optimized_one_to_one(bank_list, book_list)
                if not bucket_matches:
                    bucket_matches = optimized_combination_matches(bank_list, book_list)
                if bucket_matches:
                    bucket_matches.sort(key=lambda x: x["confidence_score"], reverse=True)
                    suggestions.extend(bucket_matches[:max_suggestions])
    else:
        suggestions = optimized_combination_matches(candidate_bank, candidate_book)
    
    # --- STEP 6: Group suggestions by bank combination key and deduplicate.
    # If multiple suggestions share the same bank_ids key, then if they are exactly identical (i.e. same sums, difference, and confidence),
    # we keep one; otherwise, we drop them as ambiguous.
    grouped = {}
    for suggestion in suggestions:
        key = "-".join(sorted(str(id) for id in suggestion["bank_ids"]))
        grouped.setdefault(key, []).append(suggestion)
    unique_suggestions = []
    for key, group in grouped.items():
        if len(group) == 1:
            unique_suggestions.append(group[0])
        else:
            first = group[0]
            all_same = all(
                suggestion["sum_bank"] == first["sum_bank"] and
                suggestion["sum_book"] == first["sum_book"] and
                abs(suggestion["difference"] - first["difference"]) < 1e-6 and
                abs(suggestion["confidence_score"] - first["confidence_score"]) < 1e-6
                for suggestion in group
            )
            if all_same:
                print(f"DEBUG: Duplicate exact match for bank IDs {key} found; selecting one.")
                unique_suggestions.append(first)
            else:
                print(f"DEBUG: Duplicate match for bank IDs {key} with differing details found; excluding these matches.")
    unique_suggestions.sort(key=lambda x: x["confidence_score"], reverse=True)
    print("DEBUG: Final unique suggestions count:", len(unique_suggestions))
    
    return Response({"suggestions": unique_suggestions})


class Account(TenantAwareBaseModel):
    account_code = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=50)
    account_direction = models.IntegerField()
    balance_date = models.DateField()
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('company', 'account_code', 'name')
        
    def __str__(self):
        return f'({self.id}) {self.company} - {self.account_code} - {self.name}'
        
    def get_depth(self):
        return len(self.account_code.split('-'))
    
    def get_current_balance(self):
        last_balance_date = self.balance_date
        validated_balance = self.balance

        transactions = JournalEntry.objects.filter(
            account=self,
            transaction__date__gt=last_balance_date,
            transaction__state='posted',
            transaction__balance_validated=False  # <-- include only not yet validated transactions
        ).aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        )

        total_debit = transactions['total_debit'] or Decimal('0.00')
        total_credit = transactions['total_credit'] or Decimal('0.00')

        effective_amount = (total_debit - total_credit) * self.account_direction

        current_balance = validated_balance + effective_amount

        return current_balance
    
    def calculate_balance(self, include_pending=False, beginning_date=None, end_date=None):
        entries = self.journal_entries.filter(state='posted')
        if include_pending:
            entries = entries | self.journal_entries.filter(state='pending')

        # Apply date filters if provided
        date_filter = Q()
        if beginning_date:
            date_filter &= Q(date__gte=beginning_date)
        if end_date:
            date_filter &= Q(date__lte=end_date)
        
        entries = entries.filter(date_filter)

        return entries.aggregate(balance=Sum('amount'))['balance']

    @staticmethod
    def get_accounts_summary(company_id, entity_id=None, min_depth=1, include_pending=False, beginning_date=None, end_date=None):
        Account = apps.get_model('accounting', 'Account') 
        accounts_query = Account.objects.filter(company_id=company_id, depth__gte=min_depth)

        if entity_id:
            accounts_query = accounts_query.filter(entity_id=entity_id)

        accounts = accounts_query.annotate(depth=Length('account_code'))
        return [(account, account.calculate_balance(include_pending, beginning_date, end_date)) for account in accounts]




'''