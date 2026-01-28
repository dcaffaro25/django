# multitenancy/etl_service.py
"""
ETL Pipeline Service for Excel file transformation, substitution, and import.

Pipeline Flow:
1. TRANSFORMATION: Read Excel sheets, apply ImportTransformationRules
2. SUBSTITUTION: Apply SubstitutionRules to clean/standardize data
3. VALIDATION: Validate data before import
4. IMPORT: Create records using existing bulk import logic
5. TRIGGERS: Fire IntegrationRule events for created records

Features:
- Case-insensitive column matching
- Continues processing other sheets on error
- Returns all rows in preview mode
- No cross-sheet dependencies
- Extra fields can be passed to IntegrationRules via extra_fields_for_trigger
- Use IntegrationRules with create_transaction_with_entries() for Transaction + JournalEntries
"""

import hashlib
import logging
import re
import time
from datetime import datetime, date, timedelta
from datetime import time as time_type
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from django.apps import apps
from django.db import transaction
from django.db import models as dj_models
from django.utils import timezone

from .models import ImportTransformationRule, ETLPipelineLog, SubstitutionRule
from .tasks import execute_import_job, MODEL_APP_MAP

logger = logging.getLogger(__name__)


def _parse_notes_metadata_newline(notes: str) -> dict:
    """
    Parse notes metadata that uses newline-separated format from build_notes_metadata.
    Format: "Key: value\nKey2: value2"
    """
    meta = {}
    if not notes:
        return meta
    for line in notes.split("\n"):
        if ":" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                k = parts[0].strip().lower()
                v = parts[1].strip()
                # Normalize key names (e.g., "file" -> "filename", "row number" -> "row_number")
                if k == "file":
                    meta["filename"] = v
                elif k == "row number":
                    meta["row_number"] = v
                elif k == "sheet name":
                    meta["sheet_name"] = v
                elif k == "log id":
                    meta["log_id"] = v
                else:
                    meta[k] = v
    return meta


def _find_existing_transaction_by_metadata(
    company_id: int,
    filename: str,
    sheet_name: Optional[str] = None,
    description: Optional[str] = None,
    amount: Optional[Any] = None,
    date: Optional[Any] = None,
    log_id: Optional[str] = None,
) -> Optional[Any]:
    """
    Find an existing Transaction by matching notes metadata (filename, sheet_name) 
    and then matching by description, amount, and date.
    
    Args:
        company_id: Company ID to filter by
        filename: Filename from import metadata
        sheet_name: Sheet name from import metadata
        description: Transaction description to match
        amount: Transaction amount to match
        date: Transaction date to match
        log_id: Optional log ID for disambiguation
        
    Returns:
        Transaction instance if found, None otherwise
    """
    from accounting.models import Transaction
    from decimal import Decimal
    
    if not filename:
        return None
    
    # First, filter by filename in notes metadata
    candidates_qs = Transaction.objects.filter(
        company_id=company_id,
        notes__icontains=filename
    )
    
    # Filter by sheet_name if provided (parse notes metadata for each candidate)
    candidates = []
    for tx in candidates_qs:
        meta = _parse_notes_metadata_newline(tx.notes or "")
        fname = meta.get("filename") or meta.get("file", "").strip()
        if fname != filename:
            continue
        if sheet_name and meta.get("sheet_name") != sheet_name:
            continue
        candidates.append(tx)
    
    if not candidates:
        return None
    
    # Now match by description, amount, and date
    matching_tx = None
    for tx in candidates:
        # Match description (case-insensitive, trimmed)
        if description:
            tx_desc = (tx.description or "").strip()
            new_desc = str(description).strip()
            if tx_desc.lower() != new_desc.lower():
                continue
        
        # Match amount (with tolerance for decimal precision)
        if amount is not None:
            tx_amount = Decimal(str(tx.amount)) if tx.amount else None
            new_amount = Decimal(str(amount)) if amount else None
            if tx_amount is None or new_amount is None:
                continue
            if abs(tx_amount - new_amount) > Decimal('0.01'):  # Allow 1 cent tolerance
                continue
        
        # Match date (exact match)
        if date:
            tx_date = tx.date
            match_date = date
            if isinstance(match_date, str):
                from django.utils.dateparse import parse_date
                match_date = parse_date(match_date)
            if not match_date or tx_date != match_date:
                continue
        
        # If we get here, we have a match
        if matching_tx:
            # Multiple matches - ambiguous
            logger.warning(f"Multiple transactions found for filename={filename}, sheet_name={sheet_name}, description={description}, amount={amount}, date={date}")
            return None
        matching_tx = tx
    
    return matching_tx


def _handle_already_imported_records(
    company_id: int,
    transaction: Any,
    import_metadata: dict = None,
    extra_fields: dict = None,
    auto_config: dict = None,
    pending_bank_cache: dict = None,
    substitution_rules_cache: dict = None,
    apply_substitution_fast: callable = None,
) -> dict:
    """
    Handle already imported records by checking for existing transactions and journal entries,
    and adjusting them if needed.
    
    This function is separate from the main ETL commit logic to keep concerns separated.
    It can be called after the main import to handle duplicates and adjustments.
    
    Args:
        company_id: Company ID
        transaction: Transaction instance to check
        import_metadata: Import metadata dict (filename, log_id, etc.)
        extra_fields: Extra fields from the import row
        auto_config: Auto-create journal entries configuration
        pending_bank_cache: Cache of pending bank accounts by currency_id
        substitution_rules_cache: Cache of substitution rules
        apply_substitution_fast: Function to apply substitutions quickly
        
    Returns:
        dict with:
            - existing_transaction: Transaction instance if found, None otherwise
            - existing_bank_je: Bank JournalEntry if found, None otherwise
            - existing_book_je: Book JournalEntry if found, None otherwise
            - updated: bool indicating if any records were updated
    """
    from accounting.models import JournalEntry
    from decimal import Decimal
    
    result = {
        'existing_transaction': None,
        'existing_bank_je': None,
        'existing_book_je': None,
        'updated': False
    }
    
    if not import_metadata or not transaction:
        return result
    
    # Check for existing transaction
    filename = import_metadata.get('filename')
    log_id = import_metadata.get('log_id')
    excel_sheet_name = extra_fields.get('__excel_sheet_name') if extra_fields else None
    
    if filename:
        existing_tx = _find_existing_transaction_by_metadata(
            company_id=company_id,
            filename=filename,
            sheet_name=excel_sheet_name,
            description=transaction.description,
            amount=transaction.amount,
            date=transaction.date,
            log_id=log_id,
        )
        
        if existing_tx:
            result['existing_transaction'] = existing_tx
            logger.info(f"ETL: Found existing Transaction {existing_tx.id} for filename={filename}, sheet_name={excel_sheet_name}, description={transaction.description}, amount={transaction.amount}, date={transaction.date}")
            
            # Check for existing journal entries
            existing_jes = list(JournalEntry.objects.filter(
                transaction_id=existing_tx.id,
                company_id=company_id
            ))
            
            for je in existing_jes:
                if getattr(je, 'bank_designation_pending', False):
                    result['existing_bank_je'] = je
                else:
                    result['existing_book_je'] = je
            
            # Update journal entries if needed (only if auto_config is provided)
            if auto_config and auto_config.get('enabled', False):
                use_pending_bank = auto_config.get('use_pending_bank_account', False)
                
                # Apply substitutions to extra_fields if needed
                substituted_extra_fields = extra_fields.copy() if extra_fields else {}
                if apply_substitution_fast and substitution_rules_cache:
                    # Apply substitutions similar to main import logic
                    account_path_value = substituted_extra_fields.get('account_path')
                    if account_path_value:
                        substituted_extra_fields['account_path'] = apply_substitution_fast(
                            account_path_value,
                            'Account',
                            'path',
                            row_context=substituted_extra_fields
                        )
                
                # Update bank JE if it exists and is not posted
                if result['existing_bank_je'] and use_pending_bank:
                    if result['existing_bank_je'].state != 'posted':
                        # Get pending bank account
                        currency_id = existing_tx.currency_id
                        if pending_bank_cache and currency_id in pending_bank_cache:
                            pending_ba, pending_gl = pending_bank_cache[currency_id]
                            
                            # Calculate amounts
                            amount = Decimal(str(existing_tx.amount))
                            abs_amount = abs(amount)
                            if amount >= 0:
                                bank_debit, bank_credit = abs_amount, None
                            else:
                                bank_debit, bank_credit = None, abs_amount
                            
                            # Get dates
                            je_bank_date = substituted_extra_fields.get('je_bank_date')
                            if je_bank_date:
                                from datetime import date as date_type
                                if isinstance(je_bank_date, str):
                                    from django.utils.dateparse import parse_date
                                    je_bank_date = parse_date(je_bank_date)
                                if je_bank_date and je_bank_date < existing_tx.date:
                                    je_bank_date = None
                            final_bank_date = je_bank_date if je_bank_date else existing_tx.date
                            
                            # Update fields if needed
                            update_fields = []
                            if result['existing_bank_je'].date != final_bank_date:
                                result['existing_bank_je'].date = final_bank_date
                                update_fields.append('date')
                            
                            if result['existing_bank_je'].debit_amount != bank_debit:
                                result['existing_bank_je'].debit_amount = bank_debit
                                update_fields.append('debit_amount')
                            
                            if result['existing_bank_je'].credit_amount != bank_credit:
                                result['existing_bank_je'].credit_amount = bank_credit
                                update_fields.append('credit_amount')
                            
                            if result['existing_bank_je'].account_id != pending_gl.id:
                                result['existing_bank_je'].account_id = pending_gl.id
                                update_fields.append('account')
                            
                            if update_fields:
                                logger.info(f"ETL: Updating bank JE {result['existing_bank_je'].id} with new data: {update_fields}")
                                result['existing_bank_je'].save(update_fields=update_fields)
                                result['updated'] = True
                
                # Update book JE if it exists and is not posted
                if result['existing_book_je']:
                    account_path_value = substituted_extra_fields.get('account_path')
                    if account_path_value and result['existing_book_je'].state != 'posted':
                        # Look up opposing account
                        from accounting.models import Account
                        opposing_account = None
                        # Simple lookup - can be enhanced with proper path resolution
                        try:
                            opposing_account = Account.objects.filter(
                                company_id=company_id,
                                path__icontains=account_path_value
                            ).first()
                        except:
                            pass
                        
                        if opposing_account:
                            # Calculate amounts
                            amount = Decimal(str(existing_tx.amount))
                            abs_amount = abs(amount)
                            if amount >= 0:
                                opp_debit, opp_credit = None, abs_amount
                            else:
                                opp_debit, opp_credit = abs_amount, None
                            
                            # Get dates
                            je_book_date = substituted_extra_fields.get('je_book_date')
                            if je_book_date:
                                from datetime import date as date_type
                                if isinstance(je_book_date, str):
                                    from django.utils.dateparse import parse_date
                                    je_book_date = parse_date(je_book_date)
                                if je_book_date and je_book_date < existing_tx.date:
                                    je_book_date = None
                            final_book_date = je_book_date if je_book_date else existing_tx.date
                            
                            # Update fields if needed
                            update_fields = []
                            if result['existing_book_je'].date != final_book_date:
                                result['existing_book_je'].date = final_book_date
                                update_fields.append('date')
                            
                            if result['existing_book_je'].debit_amount != opp_debit:
                                result['existing_book_je'].debit_amount = opp_debit
                                update_fields.append('debit_amount')
                            
                            if result['existing_book_je'].credit_amount != opp_credit:
                                result['existing_book_je'].credit_amount = opp_credit
                                update_fields.append('credit_amount')
                            
                            if result['existing_book_je'].account_id != opposing_account.id:
                                result['existing_book_je'].account_id = opposing_account.id
                                update_fields.append('account')
                            
                            if update_fields:
                                logger.info(f"ETL: Updating book JE {result['existing_book_je'].id} with new data: {update_fields}")
                                result['existing_book_je'].save(update_fields=update_fields)
                                result['updated'] = True
    
    return result


class ETLPipelineError(Exception):
    """Base exception for ETL pipeline errors."""
    def __init__(self, message: str, stage: str, details: dict = None):
        self.message = message
        self.stage = stage
        self.details = details or {}
        super().__init__(message)


class ETLPipelineService:
    """
    Orchestrates the full ETL pipeline: Transform → Substitute → Validate → Import
    
    Usage:
        service = ETLPipelineService(company_id=1, file=uploaded_file, commit=False)
        result = service.execute()
    """
    
    # Safe builtins for computed columns
    SAFE_BUILTINS = {
        'abs': abs,
        'str': str,
        'int': int,
        'float': float,
        'len': len,
        'round': round,
        'min': min,
        'max': max,
        'sum': sum,
        'bool': bool,
        'Decimal': Decimal,
        'datetime': datetime,
        're': re,
        'None': None,
        'True': True,
        'False': False,
    }
    
    def __init__(self, company_id: int, file, commit: bool = False, auto_create_journal_entries: Optional[dict] = None, row_limit: Optional[int] = None, preview_record_limit: Optional[int] = None, debug_account_substitution: bool = False):
        self.company_id = company_id
        self.file = file
        self.commit = commit
        self.auto_create_journal_entries = auto_create_journal_entries or {}
        # row_limit: None = use default (10), 0 = process all rows, >0 = limit to that number
        self.row_limit = row_limit if row_limit is not None else 10  # Default to 10 for testing
        # preview_record_limit: None = use default (50), 0 = show all records, >0 = limit to that number
        self.preview_record_limit = preview_record_limit if preview_record_limit is not None else 50  # Default to 50 for preview
        # debug_account_substitution: Enable debug logging for account substitution (default: False)
        self.debug_account_substitution = debug_account_substitution
        
        # Initialize lookup cache for efficient FK resolution
        from multitenancy.lookup_cache import LookupCache
        self.lookup_cache = LookupCache(company_id)
        self.lookup_cache.load()  # Pre-load all lookup data
        
        # State
        self.log: Optional[ETLPipelineLog] = None
        self.errors: List[dict] = []
        self.warnings: List[dict] = []
        self.substitution_errors: List[dict] = []  # Track substitution not found errors
        self.database_errors: List[dict] = []  # Track database errors
        self.python_errors: List[dict] = []  # Track Python exceptions
        self.file_hash: Optional[str] = None
        self.file_name: str = getattr(file, 'name', 'unknown')
        
        # Results
        self.sheets_found: List[str] = []
        self.sheets_processed: List[str] = []
        self.sheets_skipped: List[str] = []
        self.sheets_failed: List[str] = []
        self.transformed_data: Dict[str, List[dict]] = {}  # model_name -> rows
        self.transformation_rules: Dict[str, ImportTransformationRule] = {}  # model_name -> rule
        self.extra_fields_by_model: Dict[str, List[dict]] = {}  # Store for v2 response building
        
    def execute(self) -> dict:
        """
        Main entry point - runs the full pipeline.
        
        IMPORTANT: When commit=True, the entire pipeline is atomic. If any errors
        (including substitution errors) are found after substitution or validation,
        the transaction will be rolled back and no data will be committed.
        """
        start_time = time.monotonic()
        
        try:
            # Create log entry
            self._create_log()
            
            # 1. Parse Excel
            self._update_log_status('transforming')
            sheets = self._parse_excel()
            
            # 2. Transform each sheet
            for sheet_name, df in sheets.items():
                self._transform_sheet(sheet_name, df)
            
            # If all sheets failed, return error
            if not self.sheets_processed and self.sheets_failed:
                return self._build_response(start_time, success=False)
            
            # 3. Apply substitutions
            self._update_log_status('substituting')
            self._apply_substitutions()
            
            # Check for errors after substitution - if any exist, fail immediately
            if self.errors:
                logger.error(f"ETL: Found {len(self.errors)} errors after substitution phase. Aborting import.")
                self._update_log_status('failed')
                return self._build_response(start_time, success=False)
            
            # 4. Post-process (e.g., JournalEntry debit/credit calculation)
            self._post_process_data()
            
            # 5. Validate
            self._update_log_status('validating')
            self._validate_data()
            
            # Check for errors after validation - if any exist, fail immediately
            if self.errors:
                logger.error(f"ETL: Found {len(self.errors)} errors after validation phase. Aborting import.")
                self._update_log_status('failed')
                return self._build_response(start_time, success=False)
            
            # 6. Import or Preview
            if self.commit and self.transformed_data:
                # Wrap entire import in atomic transaction
                # If any errors occur during import, everything will be rolled back
                with transaction.atomic():
                    self._update_log_status('importing')
                    result = self._import_data()
                    
                    # Check for errors after import - if any exist, rollback will occur
                    if self.errors:
                        logger.error(f"ETL: Found {len(self.errors)} errors during import phase. Rolling back transaction.")
                        # Raise exception to trigger rollback
                        raise Exception(f"ETL import failed with {len(self.errors)} errors. Transaction rolled back.")
            else:
                result = self._preview_data()
            
            # Determine final status
            if self.errors:
                status = 'partial' if self.sheets_processed else 'failed'
            else:
                status = 'completed'
            
            self._update_log_status(status)
            return self._build_response(start_time, success=(status != 'failed'), import_result=result)
            
        except Exception as e:
            import traceback
            logger.exception("ETL Pipeline failed")
            self._add_error(
                error_type='exception',
                message=str(e),
                stage='pipeline',
                traceback=traceback.format_exc(),
                exception_type=type(e).__name__
            )
            self._update_log_status('failed')
            return self._build_response(start_time, success=False)
    
    def _create_log(self):
        """Create the ETL pipeline log entry."""
        # Compute file hash
        content = self.file.read()
        self.file_hash = hashlib.sha256(content).hexdigest()
        self.file.seek(0)
        
        self.log = ETLPipelineLog.objects.create(
            company_id=self.company_id,
            file_name=self.file_name,
            file_hash=self.file_hash,
            status='pending',
            is_preview=not self.commit,
        )
    
    def _json_serialize(self, obj):
        """Recursively convert datetime objects to ISO format strings for JSON serialization."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, date):
            return obj.isoformat()
        elif isinstance(obj, time_type):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._json_serialize(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._json_serialize(item) for item in obj]
        elif isinstance(obj, Decimal):
            return str(obj)
        else:
            return obj
    
    def _update_log_status(self, status: str):
        """Update log status."""
        if self.log:
            self.log.status = status
            self.log.sheets_found = self.sheets_found
            self.log.sheets_processed = self.sheets_processed
            self.log.sheets_skipped = self.sheets_skipped
            self.log.sheets_failed = self.sheets_failed
            # Convert datetime objects to strings for JSON serialization
            self.log.warnings = self._json_serialize(self.warnings)
            self.log.errors = self._json_serialize(self.errors)
            if status in ('completed', 'failed', 'partial'):
                self.log.completed_at = timezone.now()
            self.log.save()
    
    def _parse_excel(self) -> Dict[str, pd.DataFrame]:
        """Parse Excel file and return dict of sheet_name -> DataFrame."""
        try:
            xls = pd.read_excel(self.file, sheet_name=None)
            self.sheets_found = list(xls.keys())
            logger.info(f"ETL: Found {len(xls)} sheets: {self.sheets_found}")
            return xls
        except Exception as e:
            self._add_error(
                error_type='parse_error',
                message=f"Failed to parse Excel file: {str(e)}",
                stage='transformation'
            )
            return {}
    
    def _transform_sheet(self, sheet_name: str, df: pd.DataFrame):
        """
        Transform a single sheet using matching ImportTransformationRule.
        Case-insensitive sheet name matching.
        """
        # Find matching rule (case-insensitive)
        rule = ImportTransformationRule.objects.filter(
            company_id=self.company_id,
            is_active=True
        ).extra(
            where=["LOWER(source_sheet_name) = LOWER(%s)"],
            params=[sheet_name]
        ).first()
        
        if not rule:
            self.sheets_skipped.append(sheet_name)
            self._add_warning(
                warning_type='no_rule',
                message=f"No transformation rule found for sheet '{sheet_name}' - skipped",
                sheet=sheet_name
            )
            return
        
        logger.info(f"ETL: Transforming sheet '{sheet_name}' using rule '{rule.name}'")
        
        # Debug: Print transformation rule specs
        logger.info("=" * 80)
        logger.info(f"ETL TRANSFORMATION RULE DEBUG: Rule '{rule.name}' for sheet '{sheet_name}'")
        logger.info("=" * 80)
        logger.info(f"ETL TRANSFORMATION RULE DEBUG: target_model = {rule.target_model}")
        logger.info(f"ETL TRANSFORMATION RULE DEBUG: skip_rows = {rule.skip_rows}")
        logger.info(f"ETL TRANSFORMATION RULE DEBUG: header_row = {rule.header_row}")
        logger.info(f"ETL TRANSFORMATION RULE DEBUG: column_mappings = {rule.column_mappings}")
        logger.info(f"ETL TRANSFORMATION RULE DEBUG: extra_fields_for_trigger = {rule.extra_fields_for_trigger}")
        logger.info(f"ETL TRANSFORMATION RULE DEBUG: column_concatenations = {rule.column_concatenations}")
        logger.info(f"ETL TRANSFORMATION RULE DEBUG: computed_columns = {rule.computed_columns}")
        logger.info(f"ETL TRANSFORMATION RULE DEBUG: default_values = {rule.default_values}")
        logger.info(f"ETL TRANSFORMATION RULE DEBUG: row_filter = {rule.row_filter}")
        logger.info("=" * 80)
        
        try:
            # Apply skip_rows
            if rule.skip_rows > 0:
                logger.debug(f"ETL DEBUG: Applying skip_rows={rule.skip_rows}")
                df = df.iloc[rule.skip_rows:].reset_index(drop=True)
            
            # Handle header_row
            if rule.header_row > 0:
                logger.debug(f"ETL DEBUG: Applying header_row={rule.header_row}")
                df.columns = df.iloc[rule.header_row - 1]
                df = df.iloc[rule.header_row:].reset_index(drop=True)
            
            # Remove completely empty rows
            df = df.dropna(how='all')
            
            if df.empty:
                self._add_warning(
                    warning_type='empty_sheet',
                    message=f"Sheet '{sheet_name}' is empty after preprocessing",
                    sheet=sheet_name
                )
                self.sheets_skipped.append(sheet_name)
                return
            
            # Apply row limit if specified (0 means process all rows)
            original_row_count = len(df)
            if self.row_limit > 0 and original_row_count > self.row_limit:
                df = df.head(self.row_limit)
                logger.info(f"ETL: Limiting sheet '{sheet_name}' to first {self.row_limit} rows (out of {original_row_count} total)")
                self._add_warning(
                    warning_type='row_limit',
                    message=f"Processing only first {self.row_limit} rows of sheet '{sheet_name}' (total: {original_row_count})",
                    sheet=sheet_name,
                    total_rows=original_row_count,
                    limited_to=self.row_limit
                )
            
            # Debug: Show raw data from template (limited to requested rows)
            logger.info("=" * 80)
            logger.info(f"ETL RAW DATA DEBUG: Raw Excel data from sheet '{sheet_name}' (showing first {len(df)} rows)")
            logger.info("=" * 80)
            logger.info(f"ETL RAW DATA DEBUG: Available columns: {list(df.columns)}")
            for idx, (row_idx, row) in enumerate(df.iterrows()):
                if idx >= 10:  # Limit to first 10 rows for debug output
                    logger.info(f"ETL RAW DATA DEBUG: ... (showing first 10 rows only)")
                    break
                row_dict = row.to_dict()
                # Convert NaN to None for cleaner output
                clean_row = {k: (None if pd.isna(v) else v) for k, v in row_dict.items()}
                logger.info(f"ETL RAW DATA DEBUG: Row {row_idx + 1}: {clean_row}")
            logger.info("=" * 80)
            
            # Build case-insensitive column lookup
            available_columns = {str(col).lower().strip(): str(col) for col in df.columns}
            available_columns_list = list(df.columns)
            
            # Validate required columns from column_mappings
            # Note: Fields that are only in extra_fields_for_trigger (not actual model fields) 
            # should NOT be validated as required columns. They are passed to triggers but not saved to the model.
            extra_fields_target_keys = set((rule.extra_fields_for_trigger or {}).keys())
            missing_columns = []
            column_map = {}  # normalized_target -> actual_source
            
            for source_col, target_field in (rule.column_mappings or {}).items():
                # Skip validation and mapping if the target_field is only used for extra_fields_for_trigger
                # (i.e., if target_field is a key in extra_fields_for_trigger, meaning it's not a model field)
                # These fields should ONLY be in extra_fields_for_trigger, not column_mappings
                if target_field in extra_fields_target_keys:
                    # This target field is only for extra_fields, not a model field
                    # It should be extracted via extra_fields_for_trigger, not column_mappings
                    # Skip it here to avoid conflicts
                    logger.warning(f"ETL: Field '{target_field}' in column_mappings is also in extra_fields_for_trigger. "
                                 f"Remove it from column_mappings - it will be extracted via extra_fields_for_trigger.")
                    continue
                
                source_lower = str(source_col).lower().strip()
                if source_lower not in available_columns:
                    missing_columns.append(source_col)
                else:
                    column_map[target_field] = available_columns[source_lower]
            
            if missing_columns:
                self._add_error(
                    error_type='missing_columns',
                    message=f"Missing required columns in sheet '{sheet_name}': {missing_columns}",
                    stage='transformation',
                    sheet=sheet_name,
                    rule=rule.name,
                    missing_columns=missing_columns,
                    available_columns=available_columns_list,
                    suggestion=self._suggest_column_matches(missing_columns, available_columns_list)
                )
                self.sheets_failed.append(sheet_name)
                return
            
            # Validate columns for concatenations
            for target_field, concat_config in (rule.column_concatenations or {}).items():
                concat_cols = concat_config.get('columns', [])
                for col in concat_cols:
                    col_lower = str(col).lower().strip()
                    if col_lower not in available_columns:
                        self._add_error(
                            error_type='missing_concat_column',
                            message=f"Concatenation column '{col}' not found for field '{target_field}' in sheet '{sheet_name}'",
                            stage='transformation',
                            sheet=sheet_name,
                            rule=rule.name,
                            missing_column=col,
                            available_columns=available_columns_list
                        )
                        self.sheets_failed.append(sheet_name)
                        return
            
            # Transform rows
            transformed_rows = []
            total_rows = len(df)
            filtered_count = 0
            filtered_samples = []  # Store first few filtered rows for debugging
            
            for idx, row in df.iterrows():
                row_dict = row.to_dict()
                row_number = idx + rule.skip_rows + rule.header_row + 2  # Excel row number (1-indexed + header)
                
                try:
                    # Apply row filter
                    if rule.row_filter:
                        if not self._evaluate_expression(rule.row_filter, row_dict, 'row_filter'):
                            filtered_count += 1
                            # Capture first 3 filtered rows for debugging
                            if len(filtered_samples) < 3:
                                # Sanitize NaN values for JSON serialization
                                sample = {k: (None if pd.isna(v) else v) for k, v in row_dict.items()}
                                filtered_samples.append({
                                    'row_number': row_number,
                                    'data': sample
                                })
                            continue
                    
                    # Build transformed row
                    transformed = {}
                    
                    # 1. Apply column mappings
                    logger.debug(f"ETL TRANSFORM DEBUG: Row {row_number} - Applying column mappings from {len(column_map)} mapped columns")
                    for target_field, source_col in column_map.items():
                        value = row_dict.get(source_col)
                        logger.debug(f"ETL TRANSFORM DEBUG: Row {row_number} - Mapping '{source_col}' -> '{target_field}': raw_value={value} (type: {type(value).__name__})")
                        # Clean NaN values
                        if pd.isna(value):
                            value = None
                            logger.debug(f"ETL TRANSFORM DEBUG: Row {row_number} - '{source_col}' was NaN, set to None")
                        # Convert pandas Timestamp/datetime to date for date fields
                        if target_field == 'date' and value is not None:
                            logger.info(f"ETL DATE DEBUG: Row {row_number} - Processing Transaction date field from column '{source_col}': raw_value={value} (type: {type(value).__name__})")
                            if hasattr(value, 'date'):
                                # pandas Timestamp or datetime
                                original_value = value
                                value = value.date()
                                logger.info(f"ETL DATE DEBUG: Row {row_number} - Extracted date from {type(original_value).__name__}: {value}")
                            elif isinstance(value, str) and 'T' in value:
                                # ISO datetime string
                                from datetime import datetime as dt
                                try:
                                    value = dt.fromisoformat(value.replace('Z', '+00:00')).date()
                                    logger.info(f"ETL DATE DEBUG: Row {row_number} - Parsed ISO datetime string to date: {value}")
                                except (ValueError, TypeError) as e:
                                    logger.warning(f"ETL DATE DEBUG: Row {row_number} - Failed to parse ISO datetime string '{value}': {e}")
                            elif isinstance(value, str):
                                # Try parsing as date string
                                parsed_date = self._parse_date_value(value)
                                if parsed_date:
                                    value = parsed_date
                                    logger.info(f"ETL DATE DEBUG: Row {row_number} - Parsed date string '{value}' to date: {parsed_date}")
                                else:
                                    logger.warning(f"ETL DATE DEBUG: Row {row_number} - Failed to parse date string '{value}'")
                            elif isinstance(value, (int, float)):
                                # Try parsing as Excel serial number
                                parsed_date = self._parse_date_value(value)
                                if parsed_date:
                                    value = parsed_date
                                    logger.info(f"ETL DATE DEBUG: Row {row_number} - Parsed Excel serial number {value} to date: {parsed_date}")
                                else:
                                    logger.warning(f"ETL DATE DEBUG: Row {row_number} - Failed to parse Excel serial number '{value}'")
                        transformed[target_field] = value
                        logger.debug(f"ETL TRANSFORM DEBUG: Row {row_number} - Set '{target_field}' = {value} (final type: {type(value).__name__})")
                    
                    # 2. Apply column concatenations
                    for target_field, concat_config in (rule.column_concatenations or {}).items():
                        concat_cols = concat_config.get('columns', [])
                        separator = concat_config.get('separator', ' ')
                        template = concat_config.get('template')
                        
                        if template:
                            # Use template format
                            format_dict = {}
                            for col in concat_cols:
                                col_lower = str(col).lower().strip()
                                actual_col = available_columns.get(col_lower, col)
                                val = row_dict.get(actual_col, '')
                                format_dict[col] = '' if pd.isna(val) else str(val)
                            try:
                                transformed[target_field] = template.format(**format_dict)
                            except KeyError as ke:
                                transformed[target_field] = template  # Keep template if format fails
                        else:
                            # Use separator
                            values = []
                            for col in concat_cols:
                                col_lower = str(col).lower().strip()
                                actual_col = available_columns.get(col_lower, col)
                                val = row_dict.get(actual_col)
                                if not pd.isna(val) and str(val).strip():
                                    values.append(str(val).strip())
                            transformed[target_field] = separator.join(values)
                    
                    # 3. Apply computed columns
                    for target_field, expression in (rule.computed_columns or {}).items():
                        try:
                            # Build context with both original row and transformed data
                            context = {'row': row_dict, 'transformed': transformed}
                            transformed[target_field] = self._evaluate_expression(expression, context, 'computed')
                        except Exception as e:
                            self._add_error(
                                error_type='computed_column_error',
                                message=f"Error computing '{target_field}' at row {row_number}: {str(e)}",
                                stage='transformation',
                                sheet=sheet_name,
                                row_number=row_number,
                                expression=expression
                            )
                            self.sheets_failed.append(sheet_name)
                            return
                    
                    # 4. Apply default values
                    for field, default_value in (rule.default_values or {}).items():
                        if field not in transformed or transformed[field] is None:
                            transformed[field] = default_value
                    
                    # 5. Extract extra_fields_for_trigger (not saved to model, passed to triggers)
                    extra_fields = {}
                    logger.debug(f"ETL TRANSFORM DEBUG: Row {row_number} - Extracting extra_fields_for_trigger")
                    
                    # Check if extra_fields_for_trigger format is backwards (common mistake)
                    # Format should be: {"target_field": "Source Column"}
                    # But user might have: {"Source Column": "target_field"}
                    extra_fields_config = rule.extra_fields_for_trigger or {}
                    if extra_fields_config:
                        # Check if keys look like Excel column names (common in available columns)
                        # and values look like field names (je_bank_date, je_book_date, account_path, etc.)
                        first_key = list(extra_fields_config.keys())[0]
                        first_value = list(extra_fields_config.values())[0]
                        key_in_columns = str(first_key).lower().strip() in available_columns
                        value_is_field_name = first_value in ('je_bank_date', 'je_book_date', 'account_path', 'cost_center_path')
                        
                        if key_in_columns and value_is_field_name:
                            # Configuration is backwards! Swap it
                            logger.warning(f"ETL TRANSFORM DEBUG: Row {row_number} - ⚠️ WARNING: extra_fields_for_trigger appears to be backwards!")
                            logger.warning(f"ETL TRANSFORM DEBUG: Row {row_number} - Current: {extra_fields_config}")
                            logger.warning(f"ETL TRANSFORM DEBUG: Row {row_number} - Should be: {dict((v, k) for k, v in extra_fields_config.items())}")
                            logger.warning(f"ETL TRANSFORM DEBUG: Row {row_number} - Format should be: {{\"target_field\": \"Source Column\"}}, not {{\"Source Column\": \"target_field\"}}")
                            # Auto-fix by swapping
                            extra_fields_config = {v: k for k, v in extra_fields_config.items()}
                            logger.warning(f"ETL TRANSFORM DEBUG: Row {row_number} - Auto-corrected to: {extra_fields_config}")
                    
                    for target_field, source_col in extra_fields_config.items():
                        source_lower = str(source_col).lower().strip()
                        actual_col = available_columns.get(source_lower, source_col)
                        value = row_dict.get(actual_col)
                        logger.debug(f"ETL TRANSFORM DEBUG: Row {row_number} - extra_field '{target_field}' from column '{source_col}' (actual: '{actual_col}'): raw_value={value} (type: {type(value).__name__})")
                        if pd.isna(value):
                            value = None
                            logger.debug(f"ETL TRANSFORM DEBUG: Row {row_number} - '{source_col}' was NaN, set to None")
                        elif value is None:
                            logger.warning(f"ETL TRANSFORM DEBUG: Row {row_number} - ⚠️ Column '{source_col}' not found in row data for extra_field '{target_field}'")
                        
                        # Special handling for date fields in extra_fields
                        if target_field in ('je_bank_date', 'je_book_date') and value is not None:
                            logger.info(f"ETL DATE DEBUG: Row {row_number} - Processing {target_field} from column '{source_col}': raw_value={value} (type: {type(value).__name__})")
                            parsed_date = self._parse_date_value(value)
                            if parsed_date:
                                # Create a fresh date object to avoid shared references when two columns
                                # come from the same pandas Timestamp/value.
                                if isinstance(parsed_date, date):
                                    value = date(parsed_date.year, parsed_date.month, parsed_date.day)
                                else:
                                    value = parsed_date
                                logger.info(f"ETL DATE DEBUG: Row {row_number} - ✓ Successfully parsed {target_field}={parsed_date}")
                            else:
                                logger.warning(f"ETL DATE DEBUG: Row {row_number} - ✗ Failed to parse {target_field}='{value}', will be passed as-is")
                        
                        extra_fields[target_field] = value
                        logger.debug(f"ETL TRANSFORM DEBUG: Row {row_number} - Set extra_field '{target_field}' = {value} (final type: {type(value).__name__})")
                    
                    if extra_fields:
                        logger.info(f"ETL TRANSFORM DEBUG: Row {row_number} - Final extra_fields: {extra_fields}")
                    
                    # Store extra_fields in a special key (will be removed before import)
                    if extra_fields:
                        transformed['__extra_fields__'] = extra_fields
                    
                    # Debug: Show final transformed row (limited output)
                    logger.debug(f"ETL TRANSFORM DEBUG: Row {row_number} - Final transformed data (excluding metadata):")
                    transformed_debug = {k: v for k, v in transformed.items() if not k.startswith('__')}
                    for key, val in transformed_debug.items():
                        logger.debug(f"ETL TRANSFORM DEBUG: Row {row_number} -   {key} = {val} (type: {type(val).__name__})")
                    
                    # Additional post-transformation filter: Skip rows with null amount for Transaction model
                    if rule.target_model == 'Transaction':
                        amount = transformed.get('amount')
                        date_value = transformed.get('date')
                        logger.info(f"ETL DATE DEBUG: Row {row_number} - Transaction date after transformation: {date_value} (type: {type(date_value).__name__ if date_value is not None else 'None'})")
                        
                        # Warn if date is missing
                        if date_value is None:
                            logger.error(f"ETL DATE DEBUG: Row {row_number} - ⚠️ ERROR: Transaction date is NULL!")
                            logger.error(f"ETL DATE DEBUG: Row {row_number} - Available columns in Excel: {list(available_columns.keys())}")
                            logger.error(f"ETL DATE DEBUG: Row {row_number} - column_mappings: {rule.column_mappings}")
                            logger.error(f"ETL DATE DEBUG: Row {row_number} - Raw row data has 'Emissão': {row_dict.get('Emissão')}")
                            logger.error(f"ETL DATE DEBUG: Row {row_number} - Raw row data has 'Vencimento': {row_dict.get('Vencimento')}")
                            logger.error(f"ETL DATE DEBUG: Row {row_number} - Raw row data has 'Competência': {row_dict.get('Competência')}")
                            logger.error(f"ETL DATE DEBUG: Row {row_number} - 💡 SOLUTION: Add 'Emissão': 'date' to column_mappings")
                        
                        # Check if amount is null or empty after transformation
                        # Note: We allow 0 as a valid amount, only filter null/empty
                        is_null_amount = (
                            amount is None or 
                            (isinstance(amount, str) and amount.strip() == '')
                        )
                        if is_null_amount:
                            # Skip this row - it would fail validation anyway
                            filtered_count += 1
                            continue
                    
                    # Store Excel source row metadata for tracking and grouping
                    # Use __excel_row_* prefix to avoid conflicts with model fields
                    transformed['__excel_row_number'] = row_number
                    transformed['__excel_sheet_name'] = sheet_name
                    transformed['__excel_row_id'] = f"{sheet_name}:{row_number}"  # Unique identifier
                    
                    # Add row to results
                    transformed_rows.append(transformed)
                    
                except Exception as e:
                    self._add_error(
                        error_type='row_transform_error',
                        message=f"Error transforming row {row_number} in sheet '{sheet_name}': {str(e)}",
                        stage='transformation',
                        sheet=sheet_name,
                        row_number=row_number
                    )
                    self.sheets_failed.append(sheet_name)
                    return
            
            # Store transformed data by target model
            target_model = rule.target_model
            if target_model not in self.transformed_data:
                self.transformed_data[target_model] = []
            self.transformed_data[target_model].extend(transformed_rows)
            
            # Store the rule for post-processing (e.g., journal_entry_options)
            self.transformation_rules[target_model] = rule
            
            self.sheets_processed.append(sheet_name)
            
            if filtered_count > 0:
                self._add_warning(
                    warning_type='rows_filtered',
                    message=f"Filtered out {filtered_count} rows from sheet '{sheet_name}' based on row_filter",
                    sheet=sheet_name,
                    filtered_count=filtered_count,
                    total_rows=total_rows,
                    row_filter_expression=rule.row_filter,
                    sample_filtered_rows=filtered_samples
                )
            
            logger.info(f"ETL: Transformed {len(transformed_rows)} rows from sheet '{sheet_name}' to model '{target_model}'")
            
        except Exception as e:
            self._add_error(
                error_type='transformation_error',
                message=f"Unexpected error transforming sheet '{sheet_name}': {str(e)}",
                stage='transformation',
                sheet=sheet_name,
                rule=rule.name
            )
            self.sheets_failed.append(sheet_name)
    
    def _apply_substitutions(self):
        """Apply SubstitutionRules to transformed data."""
        from multitenancy.formula_engine import _passes_conditions
        
        for model_name, rows in self.transformed_data.items():
            # Get model class to identify FK fields
            app_label = MODEL_APP_MAP.get(model_name)
            model = None
            fk_field_mapping = {}
            
            if app_label:
                try:
                    model = apps.get_model(app_label, model_name)
                    # Build FK field mapping: {field_name: related_model_name}
                    for field in model._meta.fields:
                        if isinstance(field, dj_models.ForeignKey):
                            related_model = getattr(field, 'related_model', None)
                            if related_model:
                                fk_field_mapping[field.name] = related_model.__name__
                except LookupError:
                    pass
            
            # Phase 1: Apply FK-related substitutions (e.g., Entity.id for entity_id)
            if fk_field_mapping:
                logger.info(f"ETL SUBSTITUTION: Found {len(fk_field_mapping)} FK fields in {model_name}: {list(fk_field_mapping.keys())}")
                
                for row_idx, row in enumerate(rows):
                    for field_name, related_model_name in fk_field_mapping.items():
                        if field_name not in row or row[field_name] is None:
                            continue
                        
                        original_value = row[field_name]
                        logger.debug(f"ETL SUBSTITUTION: Row {row_idx + 1} - Before FK substitution - {field_name}: '{original_value}' (type: {type(original_value).__name__})")
                        
                        # Look for substitution rules: model_name=related_model_name, field_name="id"
                        fk_rules = SubstitutionRule.objects.filter(
                            company_id=self.company_id,
                            model_name__iexact=related_model_name,
                            field_name__iexact="id"
                        )
                        
                        if not fk_rules.exists():
                            logger.debug(f"ETL SUBSTITUTION: No FK substitution rules found for {field_name} -> {related_model_name}.id")
                            continue
                        
                        logger.debug(f"ETL SUBSTITUTION: Found {fk_rules.count()} FK substitution rules for {field_name} -> {related_model_name}.id")
                        
                        for rule in fk_rules:
                            # Check filter_conditions
                            filter_conditions = getattr(rule, 'filter_conditions', None)
                            if filter_conditions and not _passes_conditions(row, filter_conditions):
                                logger.debug(f"ETL SUBSTITUTION: FK rule {rule.id} ({rule.title or rule.id}) failed filter_conditions for {field_name}")
                                continue
                            
                            try:
                                new_value = self._apply_substitution_rule(rule, original_value, row)
                                if new_value != original_value:
                                    # Convert to int for _id fields
                                    if field_name.endswith('_id'):
                                        try:
                                            new_value = int(new_value)
                                            logger.debug(f"ETL SUBSTITUTION: Converted {field_name} substitution value to integer: {new_value}")
                                        except (ValueError, TypeError):
                                            # Keep as string if conversion fails
                                            logger.debug(f"ETL SUBSTITUTION: Could not convert {field_name} value '{new_value}' to int, keeping as string")
                                    
                                    row[field_name] = new_value
                                    logger.info(f"ETL SUBSTITUTION: FK substitution applied - Row {row_idx + 1} - {field_name}: '{original_value}' -> '{new_value}' (rule: {rule.title or rule.id}, target: {related_model_name}.id)")
                                    break  # First matching rule wins
                            except Exception as e:
                                import traceback
                                error_traceback = traceback.format_exc()
                                logger.error(f"ETL SUBSTITUTION: Error applying FK substitution rule '{rule}' to {field_name}: {str(e)}", exc_info=True)
                                self._add_error(
                                    error_type='substitution_error',
                                    message=f"Error applying FK substitution rule '{rule}' to {field_name}: {str(e)}",
                                    stage='substitution',
                                    model=model_name,
                                    field=field_name,
                                    value=str(original_value)[:100],
                                    traceback=error_traceback,
                                    exception_type=type(e).__name__
                                )
            
            # Phase 2: Apply normal model-level substitutions
            rules = SubstitutionRule.objects.filter(
                company_id=self.company_id,
                model_name__iexact=model_name
            )
            
            if not rules.exists():
                continue
            
            logger.info(f"ETL: Applying {rules.count()} model-level substitution rules to {len(rows)} rows of {model_name}")
            
            for rule in rules:
                field_name = rule.field_name
                
                for row in rows:
                    if field_name not in row:
                        continue
                    
                    original_value = row[field_name]
                    if original_value is None:
                        continue
                    
                    # Check filter_conditions
                    filter_conditions = getattr(rule, 'filter_conditions', None)
                    if filter_conditions and not _passes_conditions(row, filter_conditions):
                        continue
                    
                    try:
                        new_value = self._apply_substitution_rule(rule, original_value, row)
                        if new_value != original_value:
                            row[field_name] = new_value
                            logger.debug(f"ETL: Substitution applied - {field_name}: '{original_value}' -> '{new_value}' (rule: {rule.title or rule.id})")
                    except Exception as e:
                        import traceback
                        error_traceback = traceback.format_exc()
                        self._add_error(
                            error_type='substitution_error',
                            message=f"Error applying substitution rule '{rule}': {str(e)}",
                            stage='substitution',
                            model=model_name,
                            field=field_name,
                            value=str(original_value)[:100],
                            traceback=error_traceback,
                            exception_type=type(e).__name__
                        )
    
    def _apply_substitution_rule(self, rule: SubstitutionRule, value: Any, row: dict = None) -> Any:
        """Apply a single substitution rule to a value."""
        str_value = str(value)
        
        if rule.match_type == 'exact':
            if str_value == rule.match_value:
                return rule.substitution_value
        elif rule.match_type == 'regex':
            try:
                if re.search(rule.match_value, str_value):
                    return re.sub(rule.match_value, rule.substitution_value, str_value)
            except re.error as e:
                logger.warning(f"ETL: Invalid regex pattern in substitution rule {rule.id}: {rule.match_value} - {str(e)}")
                return value
        elif rule.match_type == 'caseless':
            # Case and accent insensitive
            import unicodedata
            def normalize(s):
                return unicodedata.normalize('NFD', str(s).lower()).encode('ascii', 'ignore').decode('utf-8')
            if normalize(str_value) == normalize(rule.match_value):
                return rule.substitution_value
        
        return value
    
    def _apply_substitutions_to_extra_fields(self, extra_fields: dict, auto_config: dict, substitution_rules_cache: Dict = None, apply_substitution_fast: callable = None) -> dict:
        """
        Apply substitutions to extra_fields based on target model and field.
        
        For example, if extra_fields contains 'account_path', we look for SubstitutionRules
        for model='Account' and field='path', and apply those substitutions.
        
        Field mapping:
        - account_path -> Account.path
        - account_code -> Account.code
        - account_id -> Account.id
        - bank_account_id -> BankAccount.id
        - cost_center_id -> CostCenter.id (if applicable)
        """
        from multitenancy.formula_engine import apply_substitutions
        
        if not extra_fields:
            return extra_fields
        
        subst_start = time.time()
        # Create a copy to avoid modifying original
        substituted = dict(extra_fields)
        
        # Map extra field names to (model_name, field_name) tuples
        field_mappings = {
            'account_path': ('Account', 'path'),
            'account_code': ('Account', 'code'),
            'account_id': ('Account', 'id'),
            'bank_account_id': ('BankAccount', 'id'),
            'cost_center_id': ('CostCenter', 'id'),
        }
        
        # Also check auto_config for field mappings
        bank_account_field = auto_config.get('bank_account_field', 'bank_account_id')
        opposing_account_field = auto_config.get('opposing_account_field', 'account_path')
        cost_center_field = auto_config.get('cost_center_field')
        opposing_account_lookup = auto_config.get('opposing_account_lookup', 'path')
        
        # Add mappings from auto_config
        if opposing_account_field and opposing_account_field not in field_mappings:
            # Determine target model and field based on lookup type
            if opposing_account_lookup == 'path':
                field_mappings[opposing_account_field] = ('Account', 'path')
            elif opposing_account_lookup == 'code':
                field_mappings[opposing_account_field] = ('Account', 'code')
            elif opposing_account_lookup == 'id':
                field_mappings[opposing_account_field] = ('Account', 'id')
        
        if cost_center_field and cost_center_field not in field_mappings:
            field_mappings[cost_center_field] = ('CostCenter', 'id')
        
        # Apply substitutions for each field with detailed profiling
        # Use fast substitution function that uses pre-loaded rules cache
        field_timings = {}
        if self.debug_account_substitution:
            logger.info(f"ETL OPPOSING JE: _apply_substitutions_to_extra_fields - Processing {len(field_mappings)} field mappings")
        for field_name, (target_model, target_field) in field_mappings.items():
            if field_name in substituted and substituted[field_name] is not None:
                value = substituted[field_name]
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: _apply_substitutions_to_extra_fields - Processing field '{field_name}' -> {target_model}.{target_field}, original value: '{value}'")
                
                # Apply substitutions using fast cached function
                field_subst_start = time.time()
                try:
                    # Use the fast substitution function (defined in _import_transactions_with_journal_entries)
                    # We need to access it from the outer scope
                    new_value = apply_substitution_fast(value, target_model, target_field, row_context=extra_fields)
                    field_subst_time = time.time() - field_subst_start
                    field_timings[field_name] = field_subst_time
                    if field_subst_time > 0.01:
                        logger.info(f"ETL DEBUG: Substitution for {field_name} ({target_model}.{target_field}) took {field_subst_time:.3f}s")
                    if new_value != value:
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: _apply_substitutions_to_extra_fields - SUBSTITUTION APPLIED to '{field_name}': '{value}' -> '{new_value}'")
                        logger.debug(f"ETL: Applied substitution to {field_name}: {value} -> {new_value}")
                        substituted[field_name] = new_value
                    else:
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: _apply_substitutions_to_extra_fields - No substitution applied to '{field_name}', value unchanged: '{value}'")
                except Exception as e:
                    field_subst_time = time.time() - field_subst_start
                    field_timings[field_name] = field_subst_time
                    if self.debug_account_substitution:
                        logger.error(f"ETL OPPOSING JE: _apply_substitutions_to_extra_fields - EXCEPTION applying substitution to '{field_name}': {e}", exc_info=True)
                    logger.warning(f"ETL: Error applying substitutions to {field_name}: {e}")
                    # Continue with original value
            else:
                if self.debug_account_substitution:
                    logger.debug(f"ETL OPPOSING JE: _apply_substitutions_to_extra_fields - Field '{field_name}' not in substituted or is None")
        
        # Log summary of field timings
        if field_timings:
            total_field_time = sum(field_timings.values())
            if total_field_time > 0.05:
                logger.info(f"ETL SUBSTITUTION PROFILE (extra_fields): Total {total_field_time:.3f}s across {len(field_timings)} fields")
                for field_name, timing in sorted(field_timings.items(), key=lambda x: x[1], reverse=True):
                    if timing > 0.01:
                        logger.info(f"ETL SUBSTITUTION PROFILE (extra_fields): {field_name}: {timing:.3f}s")
        
        subst_total_time = time.time() - subst_start
        if subst_total_time > 0.05:
            logger.debug(f"ETL DEBUG: Total extra field substitutions took {subst_total_time:.3f}s")
        
        return substituted
    
    def _post_process_data(self):
        """
        Post-process transformed data after substitution.
        
        This is a placeholder for any model-specific processing that needs
        to happen after substitution but before validation/import.
        
        For JournalEntry creation from Transactions, use IntegrationRules
        with the create_transaction_with_entries() helper function.
        """
        pass  # No special post-processing needed - use IntegrationRules instead
    
    def _lookup_account(self, value: Any, lookup_type: str, path_separator: str = ' > ') -> Optional[Any]:
        """
        Look up an Account by various methods using in-memory cache.
        
        Args:
            value: The lookup value
            lookup_type: One of 'path', 'code', 'id', 'name'
            path_separator: Separator for path-based lookup
            
        Returns:
            Account instance or None
        """
        if self.debug_account_substitution:
            logger.info(f"ETL OPPOSING JE: _lookup_account called - value='{value}', lookup_type='{lookup_type}', path_separator='{path_separator}'")
        
        if not value:
            if self.debug_account_substitution:
                logger.warning(f"ETL OPPOSING JE: _lookup_account - value is None/empty, returning None")
            return None
        
        lookup_start = time.time()
        try:
            result = None
            if lookup_type == 'id':
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: _lookup_account - Looking up by ID: {value}")
                result = self.lookup_cache.get_account_by_id(int(value))
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: _lookup_account - ID lookup result: {result.id if result else None} ({result.name if result else 'NOT FOUND'})")
            
            elif lookup_type == 'code':
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: _lookup_account - Looking up by code: {value}")
                result = self.lookup_cache.get_account_by_code(str(value))
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: _lookup_account - Code lookup result: {result.id if result else None} ({result.name if result else 'NOT FOUND'})")
            
            elif lookup_type == 'name':
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: _lookup_account - Looking up by name: {value}")
                result = self.lookup_cache.get_account_by_name(str(value))
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: _lookup_account - Name lookup result: {result.id if result else None} ({result.name if result else 'NOT FOUND'})")
            
            elif lookup_type == 'path':
                # Use lookup cache for path resolution
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: _lookup_account - Looking up by path: '{value}' with separator: '{path_separator}'")
                result = self.lookup_cache.get_account_by_path(str(value), path_separator)
                if result:
                    if self.debug_account_substitution:
                        logger.info(f"ETL OPPOSING JE: _lookup_account - Path lookup SUCCESS: ID={result.id}, Name={result.name}, Code={getattr(result, 'account_code', 'N/A')}")
                else:
                    if self.debug_account_substitution:
                        logger.warning(f"ETL OPPOSING JE: _lookup_account - Path lookup FAILED: No account found for path '{value}' with separator '{path_separator}'")
                        # Try to get more info about why it failed
                        path_parts = [p.strip() for p in str(value).split(path_separator) if p.strip()]
                        logger.info(f"ETL OPPOSING JE: _lookup_account - Path parts: {path_parts}")
            
            else:
                if self.debug_account_substitution:
                    logger.warning(f"ETL OPPOSING JE: _lookup_account - Unknown lookup type: {lookup_type}")
                logger.warning(f"Unknown account lookup type: {lookup_type}")
                return None
            
            lookup_time = time.time() - lookup_start
            if lookup_time > 0.01:
                logger.debug(f"ETL DEBUG: Account lookup ({lookup_type}={value}) took {lookup_time:.3f}s")
            
            return result
                
        except Exception as e:
            logger.error(f"ETL OPPOSING JE: _lookup_account - EXCEPTION: {e}", exc_info=True)
            logger.error(f"Error looking up account: {e}")
            return None
    
    def _parse_date_value(self, value: Any) -> Optional[date]:
        """
        Parse various date formats to Python date object.
        
        Supports:
        - date objects (returns as-is)
        - datetime objects (extracts date)
        - pandas Timestamp objects (extracts date)
        - Excel serial numbers (float/int representing days since 1900-01-01)
        - ISO format strings (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        - YYYY-MM-DD format strings
        
        Args:
            value: Date value in various formats
            
        Returns:
            date object or None if parsing fails
        """
        logger.debug(f"ETL DATE DEBUG: _parse_date_value called with value={value} (type: {type(value).__name__})")
        
        if isinstance(value, date):
            # Check date first, but exclude datetime and Timestamp which are subclasses
            if not isinstance(value, datetime):
                logger.debug(f"ETL DATE DEBUG: Value is already a date object: {value}")
                return value
        # Handle pandas Timestamp objects FIRST (before datetime check)
        # pd.Timestamp is a subclass of datetime, so we need to check it first
        # to avoid comparison issues when isinstance checks trigger internal comparisons
        try:
            if isinstance(value, pd.Timestamp):
                # pandas Timestamp - convert to Python date
                # Use to_pydatetime().date() to avoid comparison issues
                parsed = value.to_pydatetime().date()
                logger.debug(f"ETL DATE DEBUG: Extracted date from pandas Timestamp: {parsed}")
                return parsed
            elif hasattr(value, 'to_pydatetime'):
                # Other pandas-like timestamp objects
                parsed = value.to_pydatetime().date()
                logger.debug(f"ETL DATE DEBUG: Extracted date from pandas-like object: {parsed}")
                return parsed
            elif hasattr(value, 'date') and callable(getattr(value, 'date', None)):
                # Objects with .date() method (like pandas Timestamp)
                try:
                    # For Timestamp objects, use to_pydatetime().date() to avoid comparison issues
                    if hasattr(value, 'to_pydatetime'):
                        parsed = value.to_pydatetime().date()
                    else:
                        parsed = value.date()
                    if isinstance(parsed, date):
                        logger.debug(f"ETL DATE DEBUG: Extracted date using .date() method: {parsed}")
                        return parsed
                except (AttributeError, ValueError, TypeError) as e:
                    logger.debug(f"ETL DATE DEBUG: Failed to extract date from object with .date() method: {e}")
                    pass
        except (AttributeError, ValueError, TypeError) as e:
            logger.debug(f"ETL DATE DEBUG: Failed to parse as pandas Timestamp: {e}")
            pass
        # Handle datetime objects (check after Timestamp since Timestamp is a subclass)
        if isinstance(value, datetime):
            parsed = value.date()
            logger.debug(f"ETL DATE DEBUG: Extracted date from datetime: {parsed}")
            return parsed
        # Handle Excel serial numbers (days since 1900-01-01)
        # Excel dates are typically floats like 44927.0 for 2023-01-01
        if isinstance(value, (int, float)):
            try:
                # Excel epoch is 1899-12-30 (not 1900-01-01 due to Excel's 1900 leap year bug)
                excel_epoch = date(1899, 12, 30)
                days = int(value)
                parsed = excel_epoch + timedelta(days=days)
                # Validate it's a reasonable date (between 1900 and 2100)
                if parsed.year >= 1900 and parsed.year <= 2100:
                    logger.debug(f"ETL DATE DEBUG: Parsed Excel serial number {value} to date: {parsed}")
                    return parsed
                else:
                    logger.debug(f"ETL DATE DEBUG: Excel serial number {value} resulted in out-of-range date: {parsed}")
            except (ValueError, OverflowError, TypeError) as e:
                logger.debug(f"ETL DATE DEBUG: Failed to parse numeric value {value} as Excel date: {e}")
        if isinstance(value, str):
            value = value.strip()
            if not value:
                logger.debug(f"ETL DATE DEBUG: Empty string after strip, returning None")
                return None
            logger.debug(f"ETL DATE DEBUG: Attempting to parse string '{value}' as date...")
            # Try ISO format first (handles both date-only and datetime strings)
            try:
                if 'T' in value:
                    logger.debug(f"ETL DATE DEBUG: String contains 'T', parsing as ISO datetime format")
                    parsed = datetime.fromisoformat(value.replace('Z', '+00:00')).date()
                    logger.debug(f"ETL DATE DEBUG: Successfully parsed ISO datetime to date: {parsed}")
                    return parsed
                else:
                    logger.debug(f"ETL DATE DEBUG: Parsing as YYYY-MM-DD format")
                    parsed = datetime.strptime(value, '%Y-%m-%d').date()
                    logger.debug(f"ETL DATE DEBUG: Successfully parsed YYYY-MM-DD to date: {parsed}")
                    return parsed
            except (ValueError, TypeError) as e:
                logger.warning(f"ETL DATE DEBUG: Failed to parse date value '{value}' (error: {e}), expected YYYY-MM-DD format")
                return None
        logger.debug(f"ETL DATE DEBUG: Value type {type(value).__name__} not supported, returning None")
        return None
    
    def _validate_data(self):
        """Validate transformed data before import."""
        for model_name, rows in self.transformed_data.items():
            app_label = MODEL_APP_MAP.get(model_name)
            if not app_label:
                self._add_error(
                    error_type='unknown_model',
                    message=f"Unknown target model '{model_name}'. Valid models: {list(MODEL_APP_MAP.keys())}",
                    stage='validation',
                    model=model_name
                )
                continue
            
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                self._add_error(
                    error_type='model_not_found',
                    message=f"Model '{model_name}' not found in app '{app_label}'",
                    stage='validation',
                    model=model_name
                )
                continue
            
            # Validate required fields
            required_fields = []
            for field in model._meta.fields:
                if not field.blank and not field.null and not field.has_default() and field.name != 'id':
                    if field.name not in ('company', 'created_at', 'updated_at', 'created_by', 'updated_by'):
                        required_fields.append(field.name)
            
            for idx, row in enumerate(rows):
                # Try to get Excel row number from metadata if available
                excel_row_number = None
                excel_sheet_name = None
                if '__extra_fields__' in row:
                    extra_fields = row.get('__extra_fields__', {})
                    excel_row_number = extra_fields.get('__excel_row_number')
                    excel_sheet_name = extra_fields.get('__excel_sheet_name')
                
                row_number = excel_row_number if excel_row_number else (idx + 1)
                row_label = f"Row {row_number}" + (f" (Sheet: {excel_sheet_name})" if excel_sheet_name else "")
                
                for field in required_fields:
                    # Check both field name and field_id variant
                    field_id = f"{field}_id" if not field.endswith('_id') else field
                    field_fk = f"{field}_fk"
                    
                    if (field not in row or row[field] is None) and \
                       (field_id not in row or row[field_id] is None) and \
                       (field_fk not in row or row[field_fk] is None):
                        self._add_warning(
                            warning_type='missing_required_field',
                            message=f"{row_label} in {model_name} is missing required field '{field}'",
                            model=model_name,
                            row_number=row_number,
                            excel_sheet=excel_sheet_name,
                            field=field
                        )
    
    def _import_data(self) -> dict:
        """
        Import transformed data using existing bulk import logic.
        
        IMPORTANT: This entire method is wrapped in a single atomic transaction
        to ensure all-or-nothing behavior. If any step fails (import, auto-create
        journal entries, or integration rule triggers), the entire operation is
        rolled back, preventing partial data in the database.
        """
        # Wrap everything in a single atomic transaction
        with transaction.atomic():
            # Extract extra_fields and filter invalid model fields before import (same as preview)
            # This ensures fields like 'account_path' that aren't valid Transaction fields
            # are still available in extra_fields for opposing account lookup
            self.extra_fields_by_model = {}
            cleaned_data: Dict[str, List[dict]] = {}
            
            for model_name, rows in self.transformed_data.items():
                self.extra_fields_by_model[model_name] = []
                cleaned_data[model_name] = []
                
                # Get valid model fields
                app_label = MODEL_APP_MAP.get(model_name)
                valid_fields = set()
                if app_label:
                    try:
                        model = apps.get_model(app_label, model_name)
                        valid_fields = {f.name for f in model._meta.fields}
                        # Also include _id variants for ForeignKey
                        for f in model._meta.fields:
                            if hasattr(f, 'column'):
                                valid_fields.add(f.column)
                    except LookupError:
                        pass
                
                for row in rows:
                    # Extract __extra_fields__ first
                    extra_fields = row.pop('__extra_fields__', {})
                    
                    # Preserve Excel row metadata for tracking/grouping
                    # Note: We extract these but also keep them in row for execute_import_job
                    excel_row_number = row.pop('__excel_row_number', None)
                    excel_sheet_name = row.pop('__excel_sheet_name', None)
                    excel_row_id = row.pop('__excel_row_id', None)
                    
                    # Move invalid fields to extra_fields (same logic as preview)
                    cleaned_row = {}
                    invalid_fields = {}
                    for key, value in row.items():
                        # Check if this is a valid model field
                        field_name = key.replace('_id', '') if key.endswith('_id') else key
                        if key in valid_fields or field_name in valid_fields or not valid_fields:
                            cleaned_row[key] = value
                        else:
                            invalid_fields[key] = value
                    
                    # Merge invalid fields into extra_fields
                    extra_fields.update(invalid_fields)
                    
                    # Store Excel metadata in extra_fields so it's available for grouping
                    if excel_row_number is not None:
                        extra_fields['__excel_row_number'] = excel_row_number
                    if excel_sheet_name is not None:
                        extra_fields['__excel_sheet_name'] = excel_sheet_name
                    if excel_row_id is not None:
                        extra_fields['__excel_row_id'] = excel_row_id
                        # Also keep it in cleaned_row for execute_import_job to use
                        cleaned_row['__excel_row_id'] = excel_row_id
                    
                    self.extra_fields_by_model[model_name].append(extra_fields)
                    cleaned_data[model_name].append(cleaned_row)
            
            # Convert to sheets format expected by execute_import_job
            # Also track which transformation rule was used for each model to get sheet name
            # IMPORTANT: Set __row_id from __excel_row_id so outputs can be mapped back
            sheets = []
            for model_name, rows in cleaned_data.items():
                # Get sheet name from transformation rule if available
                sheet_name = None
                rule = self.transformation_rules.get(model_name)
                if rule:
                    sheet_name = rule.source_sheet_name
                
                # Ensure __row_id is set from __excel_row_id for mapping outputs back
                rows_with_row_id = []
                for row in rows:
                    row_copy = dict(row)
                    # Set __row_id from __excel_row_id if not already set
                    if '__row_id' not in row_copy and '__excel_row_id' in row_copy:
                        row_copy['__row_id'] = row_copy['__excel_row_id']
                    rows_with_row_id.append(row_copy)
                
                sheets.append({
                    'model': model_name,
                    'rows': rows_with_row_id,
                    'sheet_name': sheet_name  # Pass sheet name for metadata
                })
            
            if not sheets:
                return {'message': 'No data to import'}
            
            # Build import metadata for notes
            import_metadata = {
                'source': 'ETL',
                'function': 'ETLPipelineService._import_data',
                'filename': self.file_name,
                'log_id': self.log.id if self.log else None,
            }
            
            # Separate Transaction sheets from other sheets when auto_create_journal_entries is enabled
            # This ensures Transactions and JournalEntries are created together in the same transaction
            transaction_sheets = []
            other_sheets = []
            if self.auto_create_journal_entries and self.auto_create_journal_entries.get('enabled', False):
                transaction_sheets = [s for s in sheets if s.get('model') == 'Transaction']
                other_sheets = [s for s in sheets if s.get('model') != 'Transaction']
            else:
                other_sheets = sheets
            
            # Process Transactions with JournalEntries in the same transaction (if enabled)
            transaction_import_result = None
            if transaction_sheets and self.auto_create_journal_entries:
                logger.info(f"ETL: Processing {len(transaction_sheets)} Transaction sheet(s) with auto-created JournalEntries")
                transaction_import_result = self._import_transactions_with_journal_entries(
                    transaction_sheets, 
                    self.extra_fields_by_model.get('Transaction', []),
                    import_metadata=import_metadata
                )
            
            # Process other sheets normally
            other_import_result = None
            if other_sheets:
                logger.info(f"ETL: Processing {len(other_sheets)} non-Transaction sheet(s)")
                other_import_result = execute_import_job(
                    company_id=self.company_id,
                    sheets=other_sheets,
                    commit=True,  # This will commit the inner transaction, but outer transaction wraps everything
                    lookup_cache=self.lookup_cache,
                    import_metadata=import_metadata
                )
            
            # Merge results
            result = {'imports': []}
            if transaction_import_result:
                result['imports'].extend(transaction_import_result.get('imports', []))
            if other_import_result:
                result['imports'].extend(other_import_result.get('imports', []))
            
            # If no separate processing happened, process all sheets normally
            if not transaction_import_result and not other_import_result:
                result = execute_import_job(
                    company_id=self.company_id,
                    sheets=sheets,
                    commit=True,  # This will commit the inner transaction, but outer transaction wraps everything
                    lookup_cache=self.lookup_cache,
                    import_metadata=import_metadata
                )
            
            # Normalize result format: execute_import_job returns {'imports': [...]}
            # Convert to {'results': {model_name: [outputs]}} format
            normalized_result = {'results': {}}
            for import_item in result.get('imports', []):
                model_name = import_item.get('model')
                outputs = import_item.get('result', [])
                normalized_result['results'][model_name] = outputs
            
            # Validate that each row created exactly 1 Transaction and 2 Journal Entries
            # This validation only applies when auto_create_journal_entries is enabled
            if transaction_import_result and self.auto_create_journal_entries and self.auto_create_journal_entries.get('enabled', False):
                from multitenancy.tasks import _norm_row_key as _norm_row_key_validation
                transaction_outputs = normalized_result.get('results', {}).get('Transaction', [])
                journal_entry_outputs = normalized_result.get('results', {}).get('JournalEntry', []) or []
                
                # Build a map of transaction_id -> row_id from transaction outputs.
                # Use int(transaction_id) as key when possible so int/str mismatch (e.g. from JSON) does not break matching.
                transaction_id_to_row_id = {}
                for tx_output in transaction_outputs:
                    if tx_output.get('status') == 'success' and tx_output.get('action') == 'create':
                        row_id_raw = tx_output.get('__row_id') or tx_output.get('__excel_row_id')
                        tx_data = tx_output.get('data', {})
                        transaction_id = tx_data.get('id')
                        if transaction_id is not None and row_id_raw is not None:
                            row_id = _norm_row_key_validation(row_id_raw)
                            try:
                                tid_key = int(transaction_id)
                            except (TypeError, ValueError):
                                tid_key = transaction_id
                            transaction_id_to_row_id[tid_key] = row_id
                
                # Group by normalized row_id so keys match when counting JEs
                rows_by_id = {}
                for tx_output in transaction_outputs:
                    if tx_output.get('status') == 'success' and tx_output.get('action') == 'create':
                        row_id_raw = tx_output.get('__row_id') or tx_output.get('__excel_row_id')
                        if row_id_raw is not None:
                            row_id = _norm_row_key_validation(row_id_raw)
                            if row_id not in rows_by_id:
                                rows_by_id[row_id] = {'transactions': 0, 'journal_entries': 0, 'row_id': row_id}
                            rows_by_id[row_id]['transactions'] += 1
                
                # Count journal entries per row by matching transaction_id (try int and raw for lookup)
                for je_output in journal_entry_outputs:
                    if je_output.get('status') == 'success' and je_output.get('action') == 'create':
                        je_data = je_output.get('data', {})
                        transaction_id = je_data.get('transaction_id')
                        if transaction_id is None:
                            continue
                        try:
                            tid_key = int(transaction_id)
                        except (TypeError, ValueError):
                            tid_key = transaction_id
                        row_id = transaction_id_to_row_id.get(tid_key) or transaction_id_to_row_id.get(transaction_id)
                        if row_id is not None and row_id in rows_by_id:
                            rows_by_id[row_id]['journal_entries'] += 1
                
                # Validate each row
                validation_errors = []
                for row_id, counts in rows_by_id.items():
                    if counts['transactions'] != 1:
                        validation_errors.append(
                            f"Row {row_id}: Expected 1 Transaction, got {counts['transactions']}"
                        )
                    if counts['journal_entries'] != 2:
                        validation_errors.append(
                            f"Row {row_id}: Expected 2 Journal Entries, got {counts['journal_entries']}"
                        )
                
                # If validation fails, rollback by raising an exception
                if validation_errors:
                    error_message = f"ETL validation failed: Expected 1 Transaction and 2 Journal Entries per row, but found mismatches:\n" + "\n".join(validation_errors)
                    logger.error(error_message)
                    for error in validation_errors:
                        self._add_error(
                            error_type='validation_error',
                            message=error,
                            stage='import',
                            model='Transaction'
                        )
                    raise Exception(error_message)
            
            # Update log with import stats (log update happens inside transaction)
            records_created = {}
            if self.log:
                for model_name, outputs in normalized_result.get('results', {}).items():
                    created_count = sum(1 for o in outputs if o.get('status') == 'success' and o.get('action') == 'create')
                    if created_count > 0:
                        records_created[model_name] = created_count
                
                self.log.records_created = records_created
                self.log.total_rows_imported = sum(records_created.values())
                self.log.save()
            
            # Auto-create JournalEntries for Transactions (only if Transactions were NOT processed separately)
            # If Transactions were processed with _import_transactions_with_journal_entries, JournalEntries are already created
            if transaction_sheets and self.auto_create_journal_entries and self.auto_create_journal_entries.get('enabled', False):
                # Transactions were processed with _import_transactions_with_journal_entries, so JournalEntries are already created
                logger.info(f"ETL: Skipping _auto_create_journal_entries - JournalEntries already created in _import_transactions_with_journal_entries")
            else:
                # Transactions were processed normally, so create JournalEntries now
                self._auto_create_journal_entries(normalized_result, self.extra_fields_by_model)
            
            # Trigger IntegrationRule events for created records (backward compatible)
            # This also runs inside the same transaction - if any trigger fails, everything rolls back
            self._trigger_events_for_created_records(normalized_result, self.extra_fields_by_model)
        
        # Transaction commits here (or rolls back if any exception occurred)
        # For execute mode, we still return a structure compatible with v2 format
        # Build response structure (this is just data transformation, no DB operations)
        import_result_for_response = {
            'transformed_data': {},
            'would_create': {},
            'would_fail': {},
            'import_errors': [],
            'integration_rules_preview': [],
            'integration_rules_available': [],
            'transformation_rules_used': [],
            'total_rows': sum(len(rows) for rows in self.transformed_data.values()),
            'would_create_by_row': [],
            'substitutions_applied': []
        }
        
        # Build transformed_data structure (for reference)
        for model_name, rows in self.transformed_data.items():
            # Preserve a copy with metadata for building rows
            rows_copy = []
            for idx, row in enumerate(rows):
                row_copy = dict(row)
                # Add back Excel metadata from extra_fields
                if idx < len(self.extra_fields_by_model.get(model_name, [])):
                    extra_fields = self.extra_fields_by_model[model_name][idx]
                    row_copy['__excel_row_id'] = extra_fields.get('__excel_row_id')
                    row_copy['__excel_row_number'] = extra_fields.get('__excel_row_number')
                    row_copy['__excel_sheet_name'] = extra_fields.get('__excel_sheet_name')
                rows_copy.append(row_copy)
            
            import_result_for_response['transformed_data'][model_name] = {
                'row_count': len(rows_copy),
                'rows': rows_copy,
                'sample_columns': list(rows_copy[0].keys()) if rows_copy else []
            }
        
        # Build a map from __row_id to Excel metadata for efficient lookup
        # The __row_id in output matches the __row_id from input rows (normalized)
        # We need to normalize both the row_id from rows and from outputs for matching
        from multitenancy.tasks import _norm_row_key
        row_id_to_excel_metadata = {}
        for model_name, rows in self.transformed_data.items():
            extra_fields_list = self.extra_fields_by_model.get(model_name, [])
            for idx, row in enumerate(rows):
                # Try both __row_id and __excel_row_id, normalize for matching
                row_id = row.get('__row_id') or row.get('__excel_row_id')
                if row_id and idx < len(extra_fields_list):
                    extra_fields = extra_fields_list[idx]
                    # Normalize row_id for consistent matching
                    normalized_row_id = _norm_row_key(row_id)
                    row_id_to_excel_metadata[normalized_row_id] = {
                        '__excel_row_id': extra_fields.get('__excel_row_id'),
                        '__excel_row_number': extra_fields.get('__excel_row_number'),
                        '__excel_sheet_name': extra_fields.get('__excel_sheet_name')
                    }
        
        # Build transaction_id -> excel_row_id mapping for JournalEntry grouping (like preview mode)
        transaction_to_excel_row_map = {}
        for model_name, outputs in normalized_result.get('results', {}).items():
            if model_name == 'Transaction':
                for output in outputs:
                    if output.get('status') == 'success' and output.get('action') == 'create':
                        record_data = output.get('data', {})
                        transaction_id = record_data.get('id')
                        if transaction_id:
                            # Look up Excel row metadata using __row_id from output
                            row_id = output.get('__row_id')
                            if row_id:
                                normalized_row_id = _norm_row_key(row_id)
                                if normalized_row_id in row_id_to_excel_metadata:
                                    excel_metadata = row_id_to_excel_metadata[normalized_row_id]
                                    transaction_to_excel_row_map[transaction_id] = {
                                        'excel_row_id': excel_metadata.get('__excel_row_id'),
                                        'excel_row_number': excel_metadata.get('__excel_row_number'),
                                        'excel_sheet_name': excel_metadata.get('__excel_sheet_name', 'Unknown')
                                    }
        
        # Build would_create and created structures from normalized_result
        # 'would_create' is for backward compatibility (same as preview)
        # 'created' is the actual created records (for execute mode)
        for model_name, outputs in normalized_result.get('results', {}).items():
            created_records = []
            for idx, output in enumerate(outputs):
                if output.get('status') == 'success' and output.get('action') == 'create':
                    record_data = output.get('data', {})
                    if record_data:
                        # Look up Excel row metadata using __row_id from output (normalized)
                        row_id = output.get('__row_id')
                        excel_metadata = None
                        if row_id:
                            normalized_row_id = _norm_row_key(row_id)
                            if normalized_row_id in row_id_to_excel_metadata:
                                excel_metadata = row_id_to_excel_metadata[normalized_row_id]
                        
                        # For JournalEntries, try to get Excel row from parent Transaction (like preview mode)
                        if model_name == 'JournalEntry' and not excel_metadata:
                            transaction_id = record_data.get('transaction_id')
                            if transaction_id and transaction_id in transaction_to_excel_row_map:
                                tx_row_info = transaction_to_excel_row_map[transaction_id]
                                excel_metadata = {
                                    '__excel_row_id': tx_row_info['excel_row_id'],
                                    '__excel_row_number': tx_row_info['excel_row_number'],
                                    '__excel_sheet_name': tx_row_info['excel_sheet_name']
                                }
                        
                        # Fallback: use index-based lookup if __row_id lookup failed (like preview mode)
                        if not excel_metadata:
                            extra_fields_list = self.extra_fields_by_model.get(model_name, [])
                            if idx < len(extra_fields_list):
                                extra_fields = extra_fields_list[idx]
                                excel_metadata = {
                                    '__excel_row_id': extra_fields.get('__excel_row_id'),
                                    '__excel_row_number': extra_fields.get('__excel_row_number'),
                                    '__excel_sheet_name': extra_fields.get('__excel_sheet_name', 'Unknown')
                                }
                        
                        # Apply Excel metadata to record
                        if excel_metadata:
                            record_data['__excel_row_id'] = excel_metadata.get('__excel_row_id')
                            record_data['__excel_row_number'] = excel_metadata.get('__excel_row_number')
                            record_data['__excel_sheet_name'] = excel_metadata.get('__excel_sheet_name')
                        else:
                            # Default fallback (like preview mode)
                            excel_sheet_name = 'Unknown'
                            excel_row_number = idx + 1
                            record_data['__excel_row_id'] = f"{excel_sheet_name}:{excel_row_number}"
                            record_data['__excel_row_number'] = excel_row_number
                            record_data['__excel_sheet_name'] = excel_sheet_name
                        
                        created_records.append(record_data)
            
            if created_records:
                # Deduplicate records by ID to avoid showing the same record twice (like preview mode)
                seen_ids = set()
                unique_records = []
                for record in created_records:
                    record_id = record.get('id')
                    if record_id:
                        if record_id not in seen_ids:
                            seen_ids.add(record_id)
                            unique_records.append(record)
                    else:
                        # If no ID, include it (shouldn't happen for saved records)
                        unique_records.append(record)
                
                # For backward compatibility with preview mode
                # Preview mode doesn't attach Excel metadata to records in would_create
                # It only uses metadata for grouping in would_create_by_row
                would_create_records = []
                for record in unique_records:
                    # Create a copy without Excel metadata (like preview mode)
                    clean_record = {k: v for k, v in record.items() if not k.startswith('__excel_')}
                    would_create_records.append(clean_record)
                
                # Limit records based on preview_record_limit (0 = show all, None/50 = default limit)
                if self.preview_record_limit == 0:
                    limited_records = would_create_records
                else:
                    limited_records = would_create_records[:self.preview_record_limit]
                
                import_result_for_response['would_create'][model_name] = {
                    'count': len(unique_records),
                    'records': limited_records,  # Limited records for better preview (configurable via preview_record_limit)
                    'total': len(unique_records)  # Total count even if limited (like preview mode)
                }
                
                # For execute mode - actual created records (with Excel metadata)
                import_result_for_response['created'] = import_result_for_response.get('created', {})
                import_result_for_response['created'][model_name] = {
                    'count': len(unique_records),
                    'records': unique_records,  # All records with Excel metadata for execute mode
                    'total': len(unique_records)
                }
        
        # Build would_create_by_row by grouping records by Excel row (like preview mode)
        # Use records with Excel metadata from 'created' structure, not cleaned records from 'would_create'
        would_create_by_row_dict = {}
        for model_name, model_data in import_result_for_response.get('created', {}).items():
            records = model_data.get('records', [])
            for record in records:
                excel_row_id = record.get('__excel_row_id')
                if not excel_row_id:
                    continue
                
                if excel_row_id not in would_create_by_row_dict:
                    excel_sheet = record.get('__excel_sheet_name', 'Unknown')
                    excel_row_number = record.get('__excel_row_number')
                    would_create_by_row_dict[excel_row_id] = {
                        'excel_sheet': excel_sheet,
                        'excel_row_number': excel_row_number,
                        'excel_row_id': excel_row_id,
                        'created_records': {}
                    }
                
                if model_name not in would_create_by_row_dict[excel_row_id]['created_records']:
                    would_create_by_row_dict[excel_row_id]['created_records'][model_name] = []
                
                # Deduplicate by ID to avoid adding the same record twice (like preview mode)
                record_id = record.get('id')
                if record_id:
                    # Check if this record already exists in the group
                    existing_ids = {r.get('id') for r in would_create_by_row_dict[excel_row_id]['created_records'][model_name] if r.get('id')}
                    if record_id not in existing_ids:
                        # Remove internal metadata before adding to created_records (like preview mode)
                        clean_record = {k: v for k, v in record.items() if not k.startswith('__')}
                        would_create_by_row_dict[excel_row_id]['created_records'][model_name].append(clean_record)
                else:
                    # If no ID, just append (shouldn't happen for saved records)
                    clean_record = {k: v for k, v in record.items() if not k.startswith('__')}
                    would_create_by_row_dict[excel_row_id]['created_records'][model_name].append(clean_record)
        
        # Convert to list and sort
        import_result_for_response['would_create_by_row'] = sorted(
            would_create_by_row_dict.values(),
            key=lambda x: (x.get('excel_sheet', ''), x.get('excel_row_number', 999999))
        )
        
        # Add transformation rules used
        for model_name, rule in self.transformation_rules.items():
            import_result_for_response['transformation_rules_used'].append({
                'id': rule.id,
                'name': rule.name,
                'target_model': rule.target_model,
                'source_sheet_name': rule.source_sheet_name,
                'column_mappings': rule.column_mappings,
                'column_concatenations': rule.column_concatenations,
                'computed_columns': rule.computed_columns,
                'default_values': rule.default_values,
                'row_filter': rule.row_filter,
                'extra_fields_for_trigger': rule.extra_fields_for_trigger,
                'trigger_options': rule.trigger_options,
                'skip_rows': rule.skip_rows,
                'header_row': rule.header_row,
                'execution_order': rule.execution_order,
            })
        
        return import_result_for_response
    
    def _import_transactions_with_journal_entries(self, transaction_sheets: List[dict], extra_fields_list: List[dict], import_metadata: dict = None) -> dict:
        """
        Import Transactions and create JournalEntries immediately after each Transaction,
        all within the same transaction context. This ensures Transactions are accessible
        when creating JournalEntries.
        
        Similar strategy to import template - create related records together before rollback.
        This method manually processes Transactions and creates JournalEntries in the same loop,
        all within the outer transaction context from _preview_data.
        """
        from accounting.models import Account, BankAccount, Transaction, JournalEntry
        from accounting.serializers import TransactionSerializer, JournalEntrySerializer
        from multitenancy.tasks import apply_substitutions, _filter_unknown, _attach_company_context
        from multitenancy.tasks import _apply_path_inputs, _apply_fk_inputs, _coerce_boolean_fields, _quantize_decimal_fields
        from multitenancy.tasks import _safe_model_dict, _row_observations, _norm_row_key
        from django.apps import apps
        
        if self.debug_account_substitution:
            logger.info(f"ETL OPPOSING JE: _import_transactions_with_journal_entries CALLED - {len(transaction_sheets)} Transaction sheet(s), {len(extra_fields_list)} extra_fields entries")
        logger.info(f"ETL: Importing {len(transaction_sheets)} Transaction sheet(s) with auto-created JournalEntries")
        
        # Get auto-create configuration
        auto_config = self.auto_create_journal_entries or {}
        if self.debug_account_substitution:
            logger.info(f"ETL OPPOSING JE: auto_create_journal_entries config: {auto_config}")
            logger.info(f"ETL OPPOSING JE: auto_config.get('enabled'): {auto_config.get('enabled', False)}")
        
        if not auto_config.get('enabled', False):
            # If not enabled, just use normal import
            if self.debug_account_substitution:
                logger.warning(f"ETL OPPOSING JE: auto_create_journal_entries is NOT ENABLED - using normal import instead")
            from multitenancy.tasks import execute_import_job
            return execute_import_job(
                company_id=self.company_id,
                sheets=transaction_sheets,
                commit=True,
                lookup_cache=self.lookup_cache,
                import_metadata=import_metadata
            )
        
        if self.debug_account_substitution:
            logger.info(f"ETL OPPOSING JE: auto_create_journal_entries is ENABLED - proceeding with custom import logic")
        
        bank_account_field = auto_config.get('bank_account_field', 'bank_account_id')
        opposing_account_field = auto_config.get('opposing_account_field', 'account_path')
        opposing_account_lookup = auto_config.get('opposing_account_lookup', 'path')
        path_separator = auto_config.get('path_separator', ' > ')
        cost_center_field = auto_config.get('cost_center_field')
        
        # Process Transactions manually and create JournalEntries immediately
        import time
        transaction_outputs = []
        journal_entry_outputs = []
        token_to_id: Dict[str, int] = {}
        
        # Collect JournalEntries for bulk creation (performance optimization)
        journal_entries_to_create: List[JournalEntry] = []
        journal_entry_metadata: List[dict] = []  # Track metadata for output
        
        # Cache pending bank accounts by currency_id (major performance optimization)
        # ensure_pending_bank_structs is expensive, so we call it once per currency
        pending_bank_cache: Dict[int, tuple] = {}  # currency_id -> (pending_ba, pending_gl)
        
        # Pre-load substitution rules for Account.path to avoid DB queries per row
        # This is a major performance optimization - saves ~0.13s per row
        from multitenancy.models import SubstitutionRule
        from multitenancy.formula_engine import _passes_conditions, _normalize
        import re as regex_module
        
        substitution_rules_cache: Dict[tuple, List[SubstitutionRule]] = {}  # (model, field) -> [rules]
        
        # DUMP ALL SUBSTITUTION RULES FOR DEBUGGING (only if flag enabled)
        if self.debug_account_substitution:
            logger.info("=" * 80)
            logger.info("ETL SUBSTITUTION RULES DUMP - START")
            logger.info("=" * 80)
            all_rules = list(SubstitutionRule.objects.filter(company_id=self.company_id).order_by('model_name', 'field_name', 'id'))
            logger.info(f"ETL SUBSTITUTION RULES: Total rules for company {self.company_id}: {len(all_rules)}")
            
            # Group by (model_name, field_name) for easier reading
            rules_by_target = {}
            for rule in all_rules:
                key = (rule.model_name, rule.field_name)
                if key not in rules_by_target:
                    rules_by_target[key] = []
                rules_by_target[key].append(rule)
            
            for (model_name, field_name), rules in sorted(rules_by_target.items()):
                logger.info(f"ETL SUBSTITUTION RULES: {model_name}.{field_name} - {len(rules)} rule(s)")
                for idx, rule in enumerate(rules, 1):
                    rule_title = getattr(rule, 'title', f'Rule {rule.id}')
                    filter_conditions = getattr(rule, 'filter_conditions', None)
                    logger.info(f"  [{idx}] ID={rule.id}, title='{rule_title}', match_type='{rule.match_type}', "
                              f"match_value='{rule.match_value}', substitution_value='{rule.substitution_value}', "
                              f"filter_conditions={filter_conditions}")
            
            # Highlight Account.path rules specifically
            account_path_rules_list = [r for (m, f), rules in rules_by_target.items() 
                                       for r in rules if m == 'Account' and f == 'path']
            logger.info(f"ETL SUBSTITUTION RULES: Account.path rules: {len(account_path_rules_list)}")
            if account_path_rules_list:
                for idx, rule in enumerate(account_path_rules_list, 1):
                    rule_title = getattr(rule, 'title', f'Rule {rule.id}')
                    logger.info(f"  Account.path Rule [{idx}]: ID={rule.id}, title='{rule_title}', "
                              f"match='{rule.match_value}' -> '{rule.substitution_value}'")
            else:
                logger.warning("ETL SUBSTITUTION RULES: WARNING - No Account.path rules found! "
                              "Substitutions for account_path will not work.")
            
            # Check for common misconfigurations
            account_path_wrong = [r for (m, f), rules in rules_by_target.items() 
                                 for r in rules if m == 'Account' and f == 'account_path']
            if account_path_wrong:
                logger.warning(f"ETL SUBSTITUTION RULES: WARNING - Found {len(account_path_wrong)} rule(s) with "
                              f"model_name='Account' and field_name='account_path' (should be 'path' instead)")
                for rule in account_path_wrong:
                    rule_title = getattr(rule, 'title', f'Rule {rule.id}')
                    logger.warning(f"  Misconfigured Rule ID={rule.id}, title='{rule_title}'")
            
            logger.info("=" * 80)
            logger.info("ETL SUBSTITUTION RULES DUMP - END")
            logger.info("=" * 80)
        
        # Pre-load rules for Account.path (most common case)
        account_path_rules = list(SubstitutionRule.objects.filter(
            company_id=self.company_id,
            model_name='Account',
            field_name='path'
        ))
        substitution_rules_cache[('Account', 'path')] = account_path_rules
        if self.debug_account_substitution and account_path_rules:
            logger.info(f"ETL DEBUG: Pre-loaded {len(account_path_rules)} substitution rules for Account.path")
        
        def normalize_path_separators(path_str: str) -> str:
            """
            Normalize path separators to a consistent format.
            Converts backslashes and various arrow formats to ' > ' (space-greater-space).
            """
            if not path_str or not isinstance(path_str, str):
                return path_str
            
            # Replace backslashes with ' > '
            normalized = path_str.replace('\\', ' > ')
            
            # Replace standalone '>' (not part of ' > ') with ' > '
            # Use regex to match '>' that's not surrounded by spaces
            normalized = re.sub(r'(?<! )>(?! )', ' > ', normalized)
            
            # Clean up multiple spaces (this will also fix any ' >  > ' issues)
            normalized = ' '.join(normalized.split())
            
            # Strip leading/trailing spaces
            normalized = normalized.strip()
            
            return normalized
        
        def apply_substitution_fast(value: Any, model_name: str, field_name: str, row_context: dict = None) -> Any:
            """
            Fast substitution using pre-loaded rules cache.
            Returns the substituted value or original if no substitution applies.
            """
            if value is None:
                return value
            
            cache_key = (model_name, field_name)
            rules = substitution_rules_cache.get(cache_key)
            
            if self.debug_account_substitution:
                logger.info(f"ETL OPPOSING JE: apply_substitution_fast - value='{value}', model='{model_name}', field='{field_name}'")
                logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Found {len(rules) if rules else 0} rules in cache for {cache_key}")
            
            # If not cached, load it (shouldn't happen often)
            if rules is None:
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rules not cached, loading from DB")
                rules = list(SubstitutionRule.objects.filter(
                    company_id=self.company_id,
                    model_name=model_name,
                    field_name=field_name
                ))
                substitution_rules_cache[cache_key] = rules
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Loaded {len(rules)} rules from DB")
            
            # Apply rules in order (first match wins)
            row_context = row_context or {}
            if self.debug_account_substitution:
                logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Row context: {row_context}")
            
            # For account_path fields, normalize path separators before comparison
            is_account_path_field = (field_name == 'account_path' or field_name.endswith('_path'))
            if is_account_path_field and isinstance(value, str):
                value_normalized = normalize_path_separators(value)
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Normalized account_path value: '{value}' -> '{value_normalized}'")
            else:
                value_normalized = value
            
            for idx, rl in enumerate(rules):
                rule_title = getattr(rl, 'title', f'Rule {rl.id}')
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Checking rule {idx + 1}/{len(rules)}: ID={rl.id}, title='{rule_title}', match_type='{rl.match_type}', match_value='{rl.match_value}', substitution_value='{rl.substitution_value}'")
                
                # Check filter conditions
                filter_conditions = getattr(rl, "filter_conditions", None)
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} filter_conditions: {filter_conditions}")
                if not _passes_conditions(row_context, filter_conditions):
                    if self.debug_account_substitution:
                        logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} FAILED filter conditions, skipping")
                    continue
                
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} PASSED filter conditions, checking match")
                
                # Check match type
                mt = (rl.match_type or "exact").lower()
                mv = rl.match_value
                sv = rl.substitution_value
                
                # For account_path fields, normalize match_value as well
                if is_account_path_field and isinstance(mv, str):
                    mv_normalized = normalize_path_separators(mv)
                    if self.debug_account_substitution:
                        logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Normalized account_path match_value: '{mv}' -> '{mv_normalized}'")
                else:
                    mv_normalized = mv
                
                if mt == "exact":
                    # Use normalized values for account_path fields, original values otherwise
                    compare_value = value_normalized if is_account_path_field else value
                    compare_match = mv_normalized if is_account_path_field else mv
                    if self.debug_account_substitution:
                        logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} exact match: '{compare_value}' == '{compare_match}'? {compare_value == compare_match}")
                    if compare_value == compare_match:
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} MATCHED! Returning substitution: '{sv}'")
                        return sv
                elif mt == "regex":
                    try:
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} regex match: pattern='{mv}' against '{value}'")
                        if regex_module.search(str(mv), str(value or "")):
                            result = regex_module.sub(str(mv), str(sv), str(value or ""))
                            if self.debug_account_substitution:
                                logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} MATCHED! Returning substitution: '{result}'")
                            return result
                        else:
                            if self.debug_account_substitution:
                                logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} regex did not match")
                    except regex_module.error as regex_err:
                        if self.debug_account_substitution:
                            logger.warning(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} regex error: {regex_err}")
                        continue
                elif mt == "caseless":
                    normalized_value = _normalize(value)
                    normalized_match = _normalize(mv)
                    if self.debug_account_substitution:
                        logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} caseless match: '{normalized_value}' == '{normalized_match}'? {normalized_value == normalized_match}")
                    if normalized_value == normalized_match:
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: apply_substitution_fast - Rule {idx + 1} MATCHED! Returning substitution: '{sv}'")
                        return sv
            
            if self.debug_account_substitution:
                logger.info(f"ETL OPPOSING JE: apply_substitution_fast - No rules matched, returning original value: '{value}'")
            return value
        
        model = apps.get_model('accounting', 'Transaction')
        
        # Track processed rows for commit substitutions to avoid processing twice
        processed_substitution_rows = set()
        
        total_start = time.time()
        logger.info(f"ETL DEBUG: Starting transaction processing for {len(transaction_sheets)} sheet(s)")
        
        for sheet_idx, sheet in enumerate(transaction_sheets):
            sheet_start = time.time()
            raw_rows: List[Dict[str, Any]] = sheet.get("rows") or []
            logger.info(f"ETL DEBUG: Sheet {sheet_idx + 1}: Processing {len(raw_rows)} raw rows")
            
            # Log entity_id values before substitutions
            for idx, row in enumerate(raw_rows):
                if isinstance(row, dict) and 'entity_id' in row:
                    logger.info(f"ETL DEBUG: Row {idx + 1} BEFORE substitutions - entity_id: '{row.get('entity_id')}' (type: {type(row.get('entity_id')).__name__})")
            
            # Apply substitutions
            subst_start = time.time()
            rows, audit = apply_substitutions(
                raw_rows,
                company_id=self.company_id,
                model_name='Transaction',
                return_audit=True,
                commit=self.commit,
                processed_row_ids=processed_substitution_rows
            )
            subst_time = time.time() - subst_start
            logger.info(f"ETL DEBUG: Substitutions took {subst_time:.3f}s for {len(rows)} rows ({subst_time/len(rows)*1000:.2f}ms per row)")
            
            # Log entity_id values after substitutions
            for idx, row in enumerate(rows):
                if isinstance(row, dict) and 'entity_id' in row:
                    logger.info(f"ETL DEBUG: Row {idx + 1} AFTER substitutions - entity_id: '{row.get('entity_id')}' (type: {type(row.get('entity_id')).__name__})")
            audit_by_rowid: Dict[Any, List[dict]] = {}
            for ch in (audit or []):
                key_norm = _norm_row_key(ch.get("__row_id"))
                audit_by_rowid.setdefault(key_norm, []).append(ch)
            
            row_processing_start = time.time()
            logger.info(f"ETL DEBUG: Starting row-by-row processing for {len(rows)} rows")
            
            for row_idx, row in enumerate(rows):
                row_start = time.time()
                if row_idx % 10 == 0:
                    logger.info(f"ETL DEBUG: Processing row {row_idx + 1}/{len(rows)}")
                raw = dict(row or {})
                rid_raw = raw.pop("__row_id", None)
                rid = _norm_row_key(rid_raw)
                
                # Log entity_id in raw row
                if 'entity_id' in raw:
                    logger.debug(f"ETL DEBUG: Row {row_idx + 1} raw dict - entity_id: '{raw.get('entity_id')}' (type: {type(raw.get('entity_id')).__name__})")
                
                try:
                    filter_start = time.time()
                    # Filter unknowns
                    filtered, unknown = _filter_unknown(model, raw)
                    
                    # Company context
                    filtered = _attach_company_context(model, filtered, self.company_id)
                    
                    # Path resolution
                    path_start = time.time()
                    filtered = _apply_path_inputs(model, filtered, self.company_id, lookup_cache=self.lookup_cache)
                    path_time = time.time() - path_start
                    if path_time > 0.01:
                        logger.debug(f"ETL DEBUG: Row {row_idx + 1} path resolution took {path_time:.3f}s")
                    
                    # FK application
                    fk_start = time.time()
                    filtered = _apply_fk_inputs(model, filtered, raw, token_to_id)
                    fk_time = time.time() - fk_start
                    if fk_time > 0.01:
                        logger.debug(f"ETL DEBUG: Row {row_idx + 1} FK resolution took {fk_time:.3f}s")
                    
                    # Log entity_id in filtered dict before save
                    if 'entity_id' in filtered:
                        logger.info(f"ETL DEBUG: Row {row_idx + 1} BEFORE save - entity_id: '{filtered.get('entity_id')}' (type: {type(filtered.get('entity_id')).__name__})")
                    
                    # Coercions
                    filtered = _coerce_boolean_fields(model, filtered)
                    filtered = _quantize_decimal_fields(model, filtered)
                    filter_time = time.time() - filter_start
                    if filter_time > 0.1:
                        logger.debug(f"ETL DEBUG: Row {row_idx + 1} filtering/processing took {filter_time:.3f}s")
                    
                    # Create or update Transaction
                    action = "create"
                    if "id" in filtered and filtered["id"]:
                        pk = int(filtered["id"])
                        instance = model.objects.get(id=pk)
                        for k, v in filtered.items():
                            setattr(instance, k, v)
                        action = "update"
                    else:
                        instance = model(**filtered)
                    
                    # Add notes metadata if notes field exists and this is a new record
                    logger.info(f"ETL NOTES DEBUG: action={action}, hasattr(instance, 'notes')={hasattr(instance, 'notes')}, import_metadata={import_metadata}")
                    if action == "create" and hasattr(instance, 'notes'):
                        # Import here to avoid circular import issues
                        try:
                            from multitenancy.utils import build_notes_metadata
                            from crum import get_current_user
                        except ImportError:
                            # Fallback: if import fails, create a simple notes string
                            from crum import get_current_user
                            def build_notes_metadata(source, function=None, filename=None, user=None, user_id=None, **kwargs):
                                parts = [f"Source: {source}"]
                                if function:
                                    parts.append(f"Function: {function}")
                                if filename:
                                    parts.append(f"File: {filename}")
                                if user:
                                    parts.append(f"User: {user}")
                                return " | ".join(parts)
                        
                        # Get current user for notes
                        current_user = get_current_user()
                        user_name = current_user.username if current_user and current_user.is_authenticated else None
                        user_id = current_user.id if current_user and current_user.is_authenticated else None
                        
                        # Get Excel row metadata from extra_fields
                        extra_fields = extra_fields_list[row_idx] if row_idx < len(extra_fields_list) else {}
                        excel_row_id = extra_fields.get('__excel_row_id')
                        excel_row_number = extra_fields.get('__excel_row_number')
                        excel_sheet_name = extra_fields.get('__excel_sheet_name')
                        
                        # Build notes with metadata
                        notes_metadata = {
                            'source': import_metadata.get('source', 'ETL') if import_metadata else 'ETL',
                            'function': import_metadata.get('function', 'ETLPipelineService._import_transactions_with_journal_entries') if import_metadata else 'ETLPipelineService._import_transactions_with_journal_entries',
                            'user': user_name,
                            'user_id': user_id,
                        }
                        
                        # Add filename if available
                        if import_metadata and 'filename' in import_metadata:
                            notes_metadata['filename'] = import_metadata['filename']
                        
                        # Add log_id if available
                        if import_metadata and 'log_id' in import_metadata:
                            notes_metadata['log_id'] = import_metadata['log_id']
                        
                        # Add Excel row metadata if available
                        if excel_row_id:
                            notes_metadata['excel_row_id'] = excel_row_id
                        if excel_row_number:
                            notes_metadata['row_number'] = excel_row_number
                        if excel_sheet_name:
                            notes_metadata['sheet_name'] = excel_sheet_name
                        elif sheet.get('sheet_name'):
                            notes_metadata['sheet_name'] = sheet.get('sheet_name')
                        
                        instance.notes = build_notes_metadata(**notes_metadata)
                        logger.info(f"ETL NOTES DEBUG: Set notes to: {instance.notes[:100] if instance.notes else 'None'}...")
                    else:
                        logger.warning(f"ETL NOTES DEBUG: NOT setting notes - action={action}, hasattr notes={hasattr(instance, 'notes')}")
                    
                    # Validate & save
                    save_start = time.time()
                    # Skip full_clean for performance - we validate manually where needed
                    # full_clean() validates FK relationships which causes DB queries
                    # For ETL, we trust the data has been validated during transformation
                    # validate_start = time.time()
                    # if hasattr(instance, "full_clean"):
                    #     instance.full_clean()
                    # validate_time = time.time() - validate_start
                    # if validate_time > 0.1:
                    #     logger.info(f"ETL DEBUG: Row {row_idx + 1} Transaction full_clean took {validate_time:.3f}s")
                    
                    # Skip clean_fields() for performance - we already quantize decimals in _quantize_decimal_fields()
                    # and save() also quantizes amounts. For ETL, we trust the data has been validated during transformation.
                    # clean_fields_start = time.time()
                    # if hasattr(instance, "clean_fields"):
                    #     instance.clean_fields()
                    # clean_fields_time = time.time() - clean_fields_start
                    # if clean_fields_time > 0.1:
                    #     logger.info(f"ETL DEBUG: Row {row_idx + 1} Transaction clean_fields took {clean_fields_time:.3f}s")
                    
                    db_save_start = time.time()
                    instance.save()  # Transaction is now saved in the transaction context (save() quantizes amounts)
                    db_save_time = time.time() - db_save_start
                    logger.info(f"ETL DEBUG: Row {row_idx + 1} Transaction instance.save() took {db_save_time:.3f}s")
                    # Verify notes were saved
                    logger.info(f"ETL NOTES DEBUG: After save, instance.notes = {instance.notes[:100] if instance.notes else 'None'}...")
                    if db_save_time > 0.5:
                        logger.warning(f"ETL DEBUG: Row {row_idx + 1} Transaction save is VERY SLOW: {db_save_time:.3f}s")
                    save_time = time.time() - save_start
                    logger.info(f"ETL DEBUG: Row {row_idx + 1} total Transaction save took {save_time:.3f}s")
                    
                    # Register token->id
                    if rid:
                        token_to_id[rid] = int(instance.pk)
                    
                    # Success output for Transaction
                    msg = "ok"
                    if unknown:
                        msg += f" | Ignoring unknown columns: {', '.join(unknown)}"
                    
                    safe_dict_start = time.time()
                    transaction_data = _safe_model_dict(
                        instance,
                        exclude_fields=["created_by", "updated_by", "is_deleted", "is_active"]
                    )
                    safe_dict_time = time.time() - safe_dict_start
                    if safe_dict_time > 0.1:
                        logger.info(f"ETL DEBUG: Row {row_idx + 1} _safe_model_dict took {safe_dict_time:.3f}s")
                    
                    transaction_outputs.append({
                        "__row_id": rid,
                        "status": "success",
                        "action": action,
                        "data": transaction_data,
                        "message": msg,
                        "observations": _row_observations(audit_by_rowid, rid),
                        "external_id": None,
                    })
                    
                    # NOW create JournalEntries immediately after Transaction is saved
                    # We're in the same transaction context, so the Transaction is accessible
                    je_prep_start = time.time()
                    extra_fields = extra_fields_list[row_idx] if row_idx < len(extra_fields_list) else {}
                    
                    # Apply substitutions to extra_fields before using them
                    # For each field, check if there are substitutions for the target model
                    if self.debug_account_substitution:
                        logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Starting extra_fields substitution")
                        logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Original extra_fields: {extra_fields}")
                        logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Auto config: enabled={auto_config.get('enabled')}, opposing_account_field={auto_config.get('opposing_account_field')}, opposing_account_lookup={auto_config.get('opposing_account_lookup')}")
                    
                    subst_extra_start = time.time()
                    substituted_extra_fields = self._apply_substitutions_to_extra_fields(
                        extra_fields, 
                        auto_config,
                        substitution_rules_cache=substitution_rules_cache,
                        apply_substitution_fast=apply_substitution_fast
                    )
                    subst_extra_time = time.time() - subst_extra_start
                    if self.debug_account_substitution:
                        logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Substituted extra_fields: {substituted_extra_fields}")
                    logger.info(f"ETL DEBUG: Row {row_idx + 1} extra field substitutions took {subst_extra_time:.3f}s")
                    if subst_extra_time > 0.5:
                        logger.warning(f"ETL DEBUG: Row {row_idx + 1} extra field substitutions is VERY SLOW: {subst_extra_time:.3f}s")
                    
                    try:
                        # Create JournalEntries for this Transaction
                        amount = Decimal(str(instance.amount))
                        abs_amount = abs(amount)
                        
                        # Check if we should use pending bank account
                        use_pending_bank = auto_config.get('use_pending_bank_account', False)
                        
                        # For bank JournalEntry: Always use pending bank account if enabled
                        bank_ledger_account = None
                        bank_designation_pending = False
                        
                        if use_pending_bank:
                            # Use cached pending bank account (major performance optimization)
                            currency_id = instance.currency_id
                            if currency_id not in pending_bank_cache:
                                pending_start = time.time()
                                from accounting.services.bank_structs import ensure_pending_bank_structs
                                pending_ba, pending_gl = ensure_pending_bank_structs(
                                    company_id=self.company_id,
                                    currency_id=currency_id
                                )
                                pending_time = time.time() - pending_start
                                logger.info(f"ETL DEBUG: ensure_pending_bank_structs for currency {currency_id} took {pending_time:.3f}s (cached for future rows)")
                                if pending_time > 0.5:
                                    logger.warning(f"ETL DEBUG: ensure_pending_bank_structs is VERY SLOW: {pending_time:.3f}s")
                                pending_bank_cache[currency_id] = (pending_ba, pending_gl)
                            else:
                                pending_ba, pending_gl = pending_bank_cache[currency_id]
                                logger.debug(f"ETL DEBUG: Row {row_idx + 1} using cached pending bank account for currency {currency_id}")
                            
                            bank_ledger_account = pending_gl
                            bank_designation_pending = True
                            logger.debug(f"ETL: Using pending bank account for Transaction {instance.id}")
                        
                        # For opposing JournalEntry: Always use account_path from template
                        opposing_account = None
                        account_path_value = substituted_extra_fields.get('account_path')
                        
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Extracting account_path from substituted_extra_fields")
                            logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - account_path_value (raw): {account_path_value}")
                            logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - opposing_account_field from config: {opposing_account_field}")
                            logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - opposing_account_lookup from config: {opposing_account_lookup}")
                        
                        # Also check if the field name in extra_fields matches the configured field name
                        if not account_path_value and opposing_account_field != 'account_path':
                            account_path_value = substituted_extra_fields.get(opposing_account_field)
                            if self.debug_account_substitution:
                                logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Also checked {opposing_account_field}: {account_path_value}")
                        
                        # Detect path separator (could be \ or > )
                        detected_separator = path_separator
                        if account_path_value:
                            if self.debug_account_substitution:
                                logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Detecting path separator for: {account_path_value}")
                            if '\\' in account_path_value:
                                detected_separator = '\\'
                            elif ' > ' in account_path_value:
                                detected_separator = ' > '
                            elif '>' in account_path_value:
                                detected_separator = '>'
                            if self.debug_account_substitution:
                                logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Detected separator: '{detected_separator}' (config default: '{path_separator}')")
                        
                        if account_path_value:
                            # Look up account by path for opposing JournalEntry
                            if self.debug_account_substitution:
                                logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Looking up account with path='{account_path_value}', lookup_type='{opposing_account_lookup}', separator='{detected_separator}'")
                            lookup_start = time.time()
                            opposing_account = self._lookup_account(account_path_value, opposing_account_lookup, detected_separator)
                            lookup_time = time.time() - lookup_start
                            if lookup_time > 0.01:
                                logger.debug(f"ETL DEBUG: Row {row_idx + 1} account path lookup took {lookup_time:.3f}s")
                            if opposing_account:
                                if self.debug_account_substitution:
                                    logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - SUCCESS: Found opposing account - ID: {opposing_account.id}, Name: {opposing_account.name}, Code: {getattr(opposing_account, 'account_code', 'N/A')}")
                                logger.debug(f"ETL: Found opposing account using account_path: {account_path_value} -> {opposing_account.id} ({opposing_account.name})")
                            else:
                                if self.debug_account_substitution:
                                    logger.warning(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - FAILED: Account not found for path: '{account_path_value}' (separator: '{detected_separator}', lookup_type: '{opposing_account_lookup}')")
                                logger.warning(f"ETL: Account not found for path: {account_path_value} (separator: {detected_separator})")
                                self._add_error(
                                    error_type='substitution_not_found',
                                    message=f"Account not found for path: {account_path_value}",
                                    stage='import',
                                    model='Transaction',
                                    record_id=instance.id,
                                    account_path=account_path_value,
                                    field='account_path',
                                    value=account_path_value
                                )
                        else:
                            if self.debug_account_substitution:
                                logger.warning(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - SKIPPED: No account_path_value found in substituted_extra_fields. Keys available: {list(substituted_extra_fields.keys())}")
                        
                        # Calculate debit/credit based on transaction amount and account direction
                        # For bank account (pending): treat as asset (direction = 1)
                        # For opposing account: use its actual account_direction
                        if opposing_account:
                            opp_direction = opposing_account.account_direction if hasattr(opposing_account, 'account_direction') else 1
                        else:
                            opp_direction = 1  # Default if account not found
                        
                        # Bank accounts are typically assets (direction = 1)
                        # Positive amount in asset = debit, negative = credit
                        # Opposing entry must balance (opposite)
                        if amount >= 0:
                            # Positive transaction: bank gets debit, opposing gets credit
                            bank_debit, bank_credit = abs_amount, None
                            opp_debit, opp_credit = None, abs_amount
                        else:
                            # Negative transaction: bank gets credit, opposing gets debit
                            bank_debit, bank_credit = None, abs_amount
                            opp_debit, opp_credit = abs_amount, None
                        
                        # Look up cost center (optional)
                        cost_center_id = None
                        if cost_center_field:
                            cost_center_value = substituted_extra_fields.get(cost_center_field)
                            if cost_center_value:
                                try:
                                    cost_center_id = int(cost_center_value)
                                except (ValueError, TypeError):
                                    pass
                        
                        # Extract custom dates from extra_fields (if provided)
                        logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - Transaction date: {instance.date}")
                        logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - Checking for custom dates in extra_fields...")
                        logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - Available keys in substituted_extra_fields: {list(substituted_extra_fields.keys())}")
                        
                        je_bank_date = None
                        je_book_date = None
                        
                        je_bank_date_raw = substituted_extra_fields.get('je_bank_date')
                        logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - je_bank_date raw value: {je_bank_date_raw} (type: {type(je_bank_date_raw).__name__ if je_bank_date_raw is not None else 'None'})")
                        
                        if je_bank_date_raw:
                            logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - Parsing je_bank_date from '{je_bank_date_raw}'...")
                            try:
                                je_bank_date = self._parse_date_value(je_bank_date_raw)
                                if je_bank_date:
                                    # Import date type to avoid shadowing
                                    from datetime import date as date_type
                                    if isinstance(je_bank_date, date_type):
                                        je_bank_date = date_type(je_bank_date.year, je_bank_date.month, je_bank_date.day)
                                # Ensure it's a Python date object, not a Timestamp or datetime
                                # Check that it's a date but not a datetime (Timestamp is a subclass of datetime)
                                from datetime import date as date_type
                                if not isinstance(je_bank_date, date_type) or isinstance(je_bank_date, datetime):
                                    logger.warning(f"ETL DATE DEBUG: Transaction {instance.id} - je_bank_date is not a pure date object (type: {type(je_bank_date).__name__}), converting...")
                                    je_bank_date = self._parse_date_value(je_bank_date)  # Re-parse to ensure it's a date
                                    # Ensure conversion succeeded
                                    from datetime import date as date_type
                                    if je_bank_date and isinstance(je_bank_date, datetime):
                                        je_bank_date = je_bank_date.date() if hasattr(je_bank_date, 'date') else None
                                    if je_bank_date and isinstance(je_bank_date, date_type):
                                        je_bank_date = date_type(je_bank_date.year, je_bank_date.month, je_bank_date.day)
                                logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - ✓ Successfully parsed je_bank_date={je_bank_date} (type: {type(je_bank_date).__name__})")
                                logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - je_bank_date vs transaction.date: {je_bank_date} vs {instance.date}")
                                if je_bank_date < instance.date:
                                    self._add_warning(
                                        warning_type='journal_entry_date_earlier_than_transaction',
                                        message=f"Bank Journal Entry date {je_bank_date} cannot be earlier than Transaction date {instance.date} for Transaction {instance.id}. Using transaction date.",
                                        model='JournalEntry',
                                        transaction_id=instance.id,
                                        provided_date=str(je_bank_date),
                                        transaction_date=str(instance.date)
                                    )
                                    je_bank_date = None  # Fallback to transaction date
                                    logger.warning(f"ETL DATE DEBUG: Transaction {instance.id} - ✗ je_bank_date is earlier than transaction.date, falling back to transaction.date")
                                else:
                                    logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - ✓ je_bank_date is valid (>= transaction.date)")
                            except Exception as e:
                                logger.warning(f"ETL DATE DEBUG: Transaction {instance.id} - ✗ Failed to parse je_bank_date='{je_bank_date_raw}', will use transaction.date. Error: {e}")
                                je_bank_date = None
                        else:
                            logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - No je_bank_date provided in extra_fields - will use transaction.date={instance.date}")
                        
                        je_book_date_raw = substituted_extra_fields.get('je_book_date')
                        logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - je_book_date raw value: {je_book_date_raw} (type: {type(je_book_date_raw).__name__ if je_book_date_raw is not None else 'None'})")
                        
                        if je_book_date_raw:
                            logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - Parsing je_book_date from '{je_book_date_raw}'...")
                            je_book_date = self._parse_date_value(je_book_date_raw)
                            if je_book_date:
                                from datetime import date as date_type
                                if isinstance(je_book_date, date_type):
                                    je_book_date = date_type(je_book_date.year, je_book_date.month, je_book_date.day)
                                # Ensure it's a Python date object, not a Timestamp or datetime
                                # Check that it's a date but not a datetime (Timestamp is a subclass of datetime)
                                if not isinstance(je_book_date, date_type) or isinstance(je_book_date, datetime):
                                    logger.warning(f"ETL DATE DEBUG: Transaction {instance.id} - je_book_date is not a pure date object (type: {type(je_book_date).__name__}), converting...")
                                    je_book_date = self._parse_date_value(je_book_date)  # Re-parse to ensure it's a date
                                    # Ensure conversion succeeded
                                    if je_book_date and isinstance(je_book_date, datetime):
                                        je_book_date = je_book_date.date() if hasattr(je_book_date, 'date') else None
                                    if je_book_date and isinstance(je_book_date, date_type):
                                        je_book_date = date_type(je_book_date.year, je_book_date.month, je_book_date.day)
                                logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - ✓ Successfully parsed je_book_date={je_book_date} (type: {type(je_book_date).__name__})")
                                logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - je_book_date vs transaction.date: {je_book_date} vs {instance.date}")
                                if je_book_date < instance.date:
                                    self._add_warning(
                                        warning_type='journal_entry_date_earlier_than_transaction',
                                        message=f"Book Journal Entry date {je_book_date} cannot be earlier than Transaction date {instance.date} for Transaction {instance.id}. Using transaction date.",
                                        model='JournalEntry',
                                        transaction_id=instance.id,
                                        provided_date=str(je_book_date),
                                        transaction_date=str(instance.date)
                                    )
                                    je_book_date = None  # Fallback to transaction date
                                    logger.warning(f"ETL DATE DEBUG: Transaction {instance.id} - ✗ je_book_date is earlier than transaction.date, falling back to transaction.date")
                                else:
                                    logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - ✓ je_book_date is valid (>= transaction.date)")
                            else:
                                logger.warning(f"ETL DATE DEBUG: Transaction {instance.id} - ✗ Failed to parse je_book_date='{je_book_date_raw}', will use transaction.date")
                        else:
                            logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - No je_book_date provided in extra_fields - will use transaction.date={instance.date}")
                        
                        # Summary of date decisions
                        final_bank_date = je_bank_date if je_bank_date else instance.date
                        final_book_date = je_book_date if je_book_date else instance.date
                        logger.info(f"ETL DATE DEBUG: Transaction {instance.id} - FINAL DATE DECISION:")
                        logger.info(f"ETL DATE DEBUG: Transaction {instance.id} -   Bank JE will use: {final_bank_date} {'(CUSTOM: je_bank_date)' if je_bank_date else '(DEFAULT: transaction.date)'}")
                        logger.info(f"ETL DATE DEBUG: Transaction {instance.id} -   Book JE will use: {final_book_date} {'(CUSTOM: je_book_date)' if je_book_date else '(DEFAULT: transaction.date)'}")
                        
                        # Create bank account JournalEntry
                        # Always create bank JournalEntry if pending bank account is enabled
                        if use_pending_bank:
                            try:
                                bank_je_create_start = time.time()
                                # Get pending GL account from cache (already ensured by ensure_pending_bank_structs)
                                pending_ba, pending_gl = pending_bank_cache[instance.currency_id]
                                # Create JournalEntry instance directly (skip serializer for performance)
                                # Set account_id to pending_gl.id since bulk_create bypasses save() which would set it
                                bank_je = JournalEntry(
                                    company_id=self.company_id,
                                    transaction_id=instance.id,
                                    date=final_bank_date,
                                    description=instance.description or '',
                                    debit_amount=bank_debit,
                                    credit_amount=bank_credit,
                                    cost_center_id=cost_center_id,
                                    state='pending',
                                    bank_designation_pending=True,
                                    account_id=pending_gl.id  # Set to pending GL account (bulk_create bypasses save())
                                )
                                # Skip clean_fields() for performance - we already quantize decimals
                                # and bulk_create will handle validation at DB level
                                # bank_validate_start = time.time()
                                # if hasattr(bank_je, "clean_fields"):
                                #     bank_je.clean_fields()
                                # bank_validate_time = time.time() - bank_validate_start
                                # if bank_validate_time > 0.1:
                                #     logger.info(f"ETL DEBUG: Row {row_idx + 1} bank JE validation took {bank_validate_time:.3f}s")
                                journal_entries_to_create.append(bank_je)
                                # Store Excel row metadata for notes
                                excel_row_id = extra_fields.get('__excel_row_id')
                                excel_row_number = extra_fields.get('__excel_row_number')
                                excel_sheet_name = extra_fields.get('__excel_sheet_name')
                                journal_entry_metadata.append({
                                    'type': 'bank',
                                    'transaction_id': instance.id,
                                    'row_id': f"auto_je_bank_{instance.id}",
                                    'account_path': "Pending Bank Account",
                                    'debit_amount': bank_debit,
                                    'credit_amount': bank_credit,
                                    'excel_row_id': excel_row_id,
                                    'excel_row_number': excel_row_number,
                                    'excel_sheet_name': excel_sheet_name,
                                })
                                bank_je_time = time.time() - bank_je_create_start
                                if bank_je_time > 0.05:
                                    logger.info(f"ETL DEBUG: Row {row_idx + 1} bank JE creation took {bank_je_time:.3f}s")
                            except Exception as je_error:
                                # Include failed JournalEntry in output with error
                                error_msg = str(je_error)
                                if hasattr(je_error, 'detail'):
                                    error_msg = str(je_error.detail)
                                elif hasattr(je_error, 'message_dict'):
                                    error_msg = str(je_error.message_dict)
                                journal_entry_outputs.append({
                                    '__row_id': f"auto_je_bank_{instance.id}",
                                    'status': 'error',
                                    'action': 'create',
                                    'data': {
                                        'transaction_id': instance.id,
                                        'account_path': "Pending Bank Account",
                                    },
                                    'message': error_msg,
                                    'observations': [],
                                    'external_id': None,
                                })
                                logger.error(f"ETL: Error preparing bank JournalEntry for Transaction {instance.id}: {je_error}")
                                self._add_warning(
                                    warning_type='auto_journal_entry_error',
                                    message=f"Error preparing bank JournalEntry for Transaction {instance.id}: {error_msg}",
                                    model='Transaction',
                                    record_id=instance.id
                                )
                        
                        # Create opposing account JournalEntry
                        # Always try to create if account_path was provided
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Checking if opposing JE should be created")
                            logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - account_path_value present: {bool(account_path_value)}, opposing_account found: {bool(opposing_account)}")
                        
                        if account_path_value:
                            if not opposing_account:
                                # Account lookup failed, but we still want to show the error in output
                                if self.debug_account_substitution:
                                    logger.error(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - ERROR: Account lookup failed, cannot create opposing JE")
                                journal_entry_outputs.append({
                                    '__row_id': f"auto_je_opp_{instance.id}",
                                    'status': 'error',
                                    'action': 'create',
                                    'data': {
                                        'transaction_id': instance.id,
                                        'account_path': account_path_value,
                                    },
                                    'message': f"Account not found for path: {account_path_value}",
                                    'observations': [],
                                    'external_id': None,
                                })
                            else:
                                # Account found, create opposing JournalEntry
                                if self.debug_account_substitution:
                                    logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - Creating opposing JE with account_id={opposing_account.id}, debit={opp_debit}, credit={opp_credit}")
                                try:
                                    # Create JournalEntry instance directly (skip serializer for performance)
                                    opp_je_create_start = time.time()
                                    opposing_je = JournalEntry(
                                        company_id=self.company_id,
                                        transaction_id=instance.id,
                                        account_id=opposing_account.id,
                                        date=final_book_date,
                                        description=instance.description or '',
                                        debit_amount=opp_debit,
                                        credit_amount=opp_credit,
                                        cost_center_id=cost_center_id,
                                        state='pending',
                                        bank_designation_pending=False
                                    )
                                    logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - JournalEntry instance created successfully, adding to bulk_create list")
                                    # Skip clean_fields() for performance - we already quantize decimals
                                    # and bulk_create will handle validation at DB level
                                    # opp_validate_start = time.time()
                                    # if hasattr(opposing_je, "clean_fields"):
                                    #     opposing_je.clean_fields()
                                    # opp_validate_time = time.time() - opp_validate_start
                                    # if opp_validate_time > 0.1:
                                    #     logger.info(f"ETL DEBUG: Row {row_idx + 1} opposing JE validation took {opp_validate_time:.3f}s")
                                    journal_entries_to_create.append(opposing_je)
                                    opp_je_time = time.time() - opp_je_create_start
                                    if opp_je_time > 0.05:
                                        logger.debug(f"ETL DEBUG: Row {row_idx + 1} opposing JE creation took {opp_je_time:.3f}s")
                                    # Store Excel row metadata for notes
                                    excel_row_id = extra_fields.get('__excel_row_id')
                                    excel_row_number = extra_fields.get('__excel_row_number')
                                    excel_sheet_name = extra_fields.get('__excel_sheet_name')
                                    journal_entry_metadata.append({
                                        'type': 'opposing',
                                        'transaction_id': instance.id,
                                        'row_id': f"auto_je_opp_{instance.id}",
                                        'account_id': opposing_account.id,
                                        'account_path': account_path_value,
                                        'account_code': opposing_account.account_code if hasattr(opposing_account, 'account_code') else None,
                                        'debit_amount': opp_debit,
                                        'credit_amount': opp_credit,
                                        'excel_row_id': excel_row_id,
                                        'excel_row_number': excel_row_number,
                                        'excel_sheet_name': excel_sheet_name,
                                    })
                                    if self.debug_account_substitution:
                                        logger.info(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - SUCCESS: Opposing JE prepared for bulk_create. Total JEs in queue: {len(journal_entries_to_create)}")
                                    logger.debug(f"ETL: Prepared opposing JournalEntry for Transaction {instance.id} with account {opposing_account.id} ({opposing_account.name})")
                                except Exception as je_error:
                                    # Include failed JournalEntry in output with error
                                    error_msg = str(je_error)
                                    if hasattr(je_error, 'detail'):
                                        error_msg = str(je_error.detail)
                                    elif hasattr(je_error, 'message_dict'):
                                        error_msg = str(je_error.message_dict)
                                    logger.error(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - EXCEPTION creating opposing JE: {error_msg}", exc_info=True)
                                    journal_entry_outputs.append({
                                        '__row_id': f"auto_je_opp_{instance.id}",
                                        'status': 'error',
                                        'action': 'create',
                                        'data': {
                                            'transaction_id': instance.id,
                                            'account_path': account_path_value,
                                        },
                                        'message': error_msg,
                                        'observations': [],
                                        'external_id': None,
                                    })
                                    logger.error(f"ETL: Error creating opposing JournalEntry for Transaction {instance.id}: {je_error}")
                                    self._add_warning(
                                        warning_type='auto_journal_entry_error',
                                        message=f"Error creating opposing JournalEntry for Transaction {instance.id}: {error_msg}",
                                        model='Transaction',
                                        record_id=instance.id
                                    )
                        else:
                            logger.warning(f"ETL OPPOSING JE: Row {row_idx + 1} Transaction {instance.id} - SKIPPED: No account_path_value, opposing JE will not be created")
                                
                    except Exception as e:
                        import traceback
                        error_traceback = traceback.format_exc()
                        logger.error(f"ETL: Error creating JournalEntries for Transaction {instance.id}: {e}", exc_info=True)
                        self._add_error(
                            error_type='python_error',
                            message=f"Error auto-creating JournalEntries for Transaction {instance.id}: {str(e)}",
                            stage='import',
                            model='Transaction',
                            record_id=instance.id,
                            traceback=error_traceback,
                            exception_type=type(e).__name__
                        )
                    finally:
                        je_prep_time = time.time() - je_prep_start
                        if je_prep_time > 0.1:
                            logger.debug(f"ETL DEBUG: Row {row_idx + 1} total JE preparation took {je_prep_time:.3f}s")
                        row_time = time.time() - row_start
                        if row_time > 0.2:
                            logger.warning(f"ETL DEBUG: Row {row_idx + 1} total processing took {row_time:.3f}s (SLOW!)")
                
                except Exception as e:
                    logger.exception(f"ETL: Error processing Transaction row {rid}: {e}")
                    transaction_outputs.append({
                        "__row_id": rid,
                        "status": "error",
                        "action": None,
                        "data": raw,
                        "message": str(e),
                        "observations": _row_observations(audit_by_rowid, rid),
                        "external_id": None,
                    })
            
            row_processing_time = time.time() - row_processing_start
            logger.info(f"ETL DEBUG: Sheet {sheet_idx + 1} row processing took {row_processing_time:.3f}s for {len(rows)} rows ({row_processing_time/len(rows):.3f}s per row)")
            sheet_time = time.time() - sheet_start
            logger.info(f"ETL DEBUG: Sheet {sheet_idx + 1} total time: {sheet_time:.3f}s")
        
        # Bulk create all JournalEntries at once (major performance optimization)
        if journal_entries_to_create:
            bulk_start = time.time()
            if self.debug_account_substitution:
                logger.info(f"ETL OPPOSING JE: Bulk creating {len(journal_entries_to_create)} JournalEntries")
            # Count how many are bank vs opposing
            bank_count = sum(1 for m in journal_entry_metadata if m.get('type') == 'bank')
            opposing_count = sum(1 for m in journal_entry_metadata if m.get('type') == 'opposing')
            if self.debug_account_substitution:
                logger.info(f"ETL OPPOSING JE: Breakdown - Bank JEs: {bank_count}, Opposing JEs: {opposing_count}")
            
            # Log details about opposing entries
            if self.debug_account_substitution:
                for metadata in journal_entry_metadata:
                    if metadata.get('type') == 'opposing':
                        logger.info(f"ETL OPPOSING JE: About to create opposing JE for Transaction {metadata.get('transaction_id')} with account_id={metadata.get('account_id')}, path={metadata.get('account_path')}")
            
            try:
                created_jes = JournalEntry.objects.bulk_create(journal_entries_to_create, batch_size=500)
                bulk_time = time.time() - bulk_start
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: SUCCESS - Bulk created {len(created_jes)} JournalEntries in {bulk_time:.3f}s ({len(created_jes)/bulk_time:.1f} entries/sec)")
                logger.info(f"ETL: Successfully bulk created {len(created_jes)} JournalEntries in {bulk_time:.3f}s ({len(created_jes)/bulk_time:.1f} entries/sec)")
                
                # Add notes to all created Journal Entries
                notes_start = time.time()
                if created_jes and hasattr(created_jes[0], 'notes'):
                    from multitenancy.utils import build_notes_metadata
                    from crum import get_current_user
                    
                    current_user = get_current_user()
                    user_name = current_user.username if current_user and current_user.is_authenticated else None
                    user_id = current_user.id if current_user and current_user.is_authenticated else None
                    
                    # Build notes for each Journal Entry
                    for je, metadata in zip(created_jes, journal_entry_metadata):
                        notes_metadata = {
                            'source': import_metadata.get('source', 'ETL') if import_metadata else 'ETL',
                            'function': import_metadata.get('function', 'ETLPipelineService._import_transactions_with_journal_entries') if import_metadata else 'ETLPipelineService._import_transactions_with_journal_entries',
                            'user': user_name,
                            'user_id': user_id,
                        }
                        
                        # Add filename if available
                        if import_metadata and 'filename' in import_metadata:
                            notes_metadata['filename'] = import_metadata['filename']
                        
                        # Add log_id if available
                        if import_metadata and 'log_id' in import_metadata:
                            notes_metadata['log_id'] = import_metadata['log_id']
                        
                        # Add Excel row metadata if available
                        if metadata.get('excel_row_id'):
                            notes_metadata['excel_row_id'] = metadata['excel_row_id']
                        if metadata.get('excel_row_number'):
                            notes_metadata['row_number'] = metadata['excel_row_number']
                        if metadata.get('excel_sheet_name'):
                            notes_metadata['sheet_name'] = metadata['excel_sheet_name']
                        
                        je.notes = build_notes_metadata(**notes_metadata)
                        logger.info(f"ETL NOTES DEBUG: Set notes on JournalEntry {je.id}: {je.notes[:100] if je.notes else 'None'}...")
                    
                    # Bulk update notes efficiently
                    JournalEntry.objects.bulk_update(created_jes, ['notes'], batch_size=500)
                    notes_time = time.time() - notes_start
                    logger.info(f"ETL: Added notes to {len(created_jes)} JournalEntries in {notes_time:.3f}s")
                
                # Verify opposing entries were created
                created_opposing = sum(1 for m in journal_entry_metadata if m.get('type') == 'opposing')
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: Created {created_opposing} opposing JournalEntries out of {opposing_count} expected")
                
                # Map created JournalEntries to their metadata for output
                opposing_created_count = 0
                bank_created_count = 0
                for je, metadata in zip(created_jes, journal_entry_metadata):
                    output_data = {
                        'id': je.id,
                        'transaction_id': metadata['transaction_id'],
                        'account_path': metadata['account_path'],
                        'debit_amount': str(metadata['debit_amount']) if metadata['debit_amount'] else None,
                        'credit_amount': str(metadata['credit_amount']) if metadata['credit_amount'] else None,
                        'bank_designation_pending': metadata['type'] == 'bank',
                    }
                    
                    if metadata['type'] == 'opposing' and 'account_id' in metadata:
                        output_data['account_id'] = metadata['account_id']
                        output_data['account_code'] = metadata.get('account_code')
                        opposing_created_count += 1
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: Created opposing JE ID={je.id} for Transaction {metadata['transaction_id']} with account_id={metadata['account_id']}, path={metadata['account_path']}")
                    elif metadata['type'] == 'bank':
                        output_data['account_id'] = None
                        bank_created_count += 1
                    
                    journal_entry_outputs.append({
                        '__row_id': metadata['row_id'],
                        'status': 'success',
                        'action': 'create',
                        'data': output_data,
                        'message': 'ok',
                        'observations': [],
                        'external_id': None,
                    })
                
                if self.debug_account_substitution:
                    logger.info(f"ETL OPPOSING JE: Final count - Bank JEs created: {bank_created_count}, Opposing JEs created: {opposing_created_count}")
            except Exception as bulk_error:
                logger.error(f"ETL OPPOSING JE: ERROR - Bulk create failed: {bulk_error}", exc_info=True)
                logger.error(f"ETL: Error bulk creating JournalEntries: {bulk_error}", exc_info=True)
                # Add errors for all failed entries
                for metadata in journal_entry_metadata:
                    journal_entry_outputs.append({
                        '__row_id': metadata['row_id'],
                        'status': 'error',
                        'action': 'create',
                        'data': {
                            'transaction_id': metadata['transaction_id'],
                            'account_path': metadata.get('account_path', 'N/A'),
                        },
                        'message': f"Bulk create failed: {str(bulk_error)}",
                        'observations': [],
                        'external_id': None,
                    })
                self._add_warning(
                    warning_type='bulk_journal_entry_error',
                    message=f"Error bulk creating JournalEntries: {str(bulk_error)}",
                    model='JournalEntry'
                )
        
        # Build result structure
        result = {
            'imports': [
                {
                    'model': 'Transaction',
                    'result': transaction_outputs
                }
            ]
        }
        
        # Add JournalEntry outputs
        if journal_entry_outputs:
            result['imports'].append({
                'model': 'JournalEntry',
                'result': journal_entry_outputs
            })
        
        total_time = time.time() - total_start
        logger.info(f"ETL DEBUG: Total transaction processing time: {total_time:.3f}s")
        logger.info(f"ETL DEBUG: Processed {len(transaction_outputs)} transactions, created {len(journal_entries_to_create)} journal entries")
        if len(transaction_outputs) > 0:
            logger.info(f"ETL DEBUG: Average time per transaction: {total_time/len(transaction_outputs):.3f}s")
        
        # Return result (Transaction + JournalEntry). Previously the code built
        # transaction_import_result with only Transaction and returned that,
        # so JournalEntry outputs were never included and validation saw 0 JEs per row.
        return result
        
        bank_account_field = auto_config.get('bank_account_field', 'bank_account_id')
        opposing_account_field = auto_config.get('opposing_account_field', 'account_path')
        opposing_account_lookup = auto_config.get('opposing_account_lookup', 'path')
        path_separator = auto_config.get('path_separator', ' > ')
        cost_center_field = auto_config.get('cost_center_field')
        
        # Process each Transaction and create JournalEntries immediately
        for idx, output in enumerate(transaction_outputs):
            if output.get('status') != 'success' or output.get('action') != 'create':
                continue
            
            transaction_data = output.get('data', {})
            transaction_id = transaction_data.get('id')
            
            if not transaction_id:
                continue
            
            # Get the Transaction instance - it should be accessible in the same transaction
            try:
                transaction = Transaction.objects.get(id=transaction_id, company_id=self.company_id)
            except Transaction.DoesNotExist:
                logger.warning(f"ETL: Transaction {transaction_id} not found immediately after creation")
                self._add_warning(
                    warning_type='transaction_not_found',
                    message=f"Transaction {transaction_id} not found (company_id={self.company_id})",
                    model='Transaction',
                    record_id=transaction_id
                )
                continue
            
            # Get extra_fields for this Transaction
            extra_fields = extra_fields_list[idx] if idx < len(extra_fields_list) else {}
            
            try:
                # Create JournalEntries for this Transaction
                amount = Decimal(str(transaction.amount))
                abs_amount = abs(amount)
                
                # Check if we should use pending bank account
                use_pending_bank = auto_config.get('use_pending_bank_account', False)
                
                # Look up bank account
                bank_ledger_account = None
                bank_designation_pending = False
                
                if use_pending_bank:
                    from accounting.services.bank_structs import ensure_pending_bank_structs
                    pending_ba, pending_gl = ensure_pending_bank_structs(
                        company_id=self.company_id,
                        currency_id=transaction.currency_id
                    )
                    bank_ledger_account = pending_gl
                    bank_designation_pending = True
                else:
                    bank_account_id_str = extra_fields.get(bank_account_field)
                    if bank_account_id_str:
                        try:
                            bank_account_id = int(bank_account_id_str)
                            bank_account = BankAccount.objects.filter(
                                company_id=self.company_id,
                                id=bank_account_id
                            ).first()
                            if bank_account:
                                bank_ledger_account = Account.objects.filter(
                                    company_id=self.company_id,
                                    bank_account_id=bank_account.id
                                ).first()
                        except (ValueError, TypeError):
                            pass
                
                # Look up opposing account
                opposing_account = None
                opposing_account_value = extra_fields.get(opposing_account_field)
                
                if opposing_account_value:
                    if opposing_account_lookup == 'path':
                        opposing_account = self._lookup_account(opposing_account_value, 'path', path_separator)
                    elif opposing_account_lookup == 'code':
                        opposing_account = self._lookup_account(opposing_account_value, 'code')
                    elif opposing_account_lookup == 'id':
                        try:
                            account_id = int(opposing_account_value)
                            opposing_account = Account.objects.filter(
                                company_id=self.company_id,
                                id=account_id
                            ).first()
                        except (ValueError, TypeError):
                            pass
                
                # Calculate debit/credit
                if amount >= 0:
                    bank_debit, bank_credit = abs_amount, None
                    opp_debit, opp_credit = None, abs_amount
                else:
                    bank_debit, bank_credit = None, abs_amount
                    opp_debit, opp_credit = abs_amount, None
                
                # Look up cost center (optional)
                cost_center_id = None
                if cost_center_field:
                    cost_center_value = substituted_extra_fields.get(cost_center_field)
                    if cost_center_value:
                        try:
                            cost_center_id = int(cost_center_value)
                        except (ValueError, TypeError):
                            pass
                
                # Create bank account JournalEntry
                if bank_ledger_account or use_pending_bank:
                    bank_je_data = {
                        'company': self.company_id,
                        'transaction': transaction.id,
                        'date': transaction.date,
                        'description': transaction.description or '',
                        'debit_amount': bank_debit,
                        'credit_amount': bank_credit,
                        'cost_center': cost_center_id,
                        'state': 'pending',
                        'bank_designation_pending': bank_designation_pending,
                    }
                    
                    if bank_ledger_account and not bank_designation_pending:
                        bank_je_data['account'] = bank_ledger_account.id
                    
                    bank_je_serializer = JournalEntrySerializer(data=bank_je_data, context={'lookup_cache': self.lookup_cache})
                    if bank_je_serializer.is_valid(raise_exception=True):
                        bank_je = bank_je_serializer.save()
                        journal_entry_outputs.append({
                            '__row_id': f"auto_je_bank_{transaction_id}",
                            'status': 'success',
                            'action': 'create',
                            'data': {
                                'id': bank_je.id,
                                'account_id': bank_je.account_id,
                                'account_name': bank_ledger_account.name if bank_ledger_account else "Pending Bank Account",
                                'transaction_id': transaction.id,
                                'debit_amount': str(bank_debit) if bank_debit else None,
                                'credit_amount': str(bank_credit) if bank_credit else None,
                                'bank_designation_pending': bank_designation_pending,
                            },
                            'message': 'ok',
                            'observations': [],
                            'external_id': None,
                        })
                
                # Create opposing account JournalEntry
                if opposing_account:
                    opposing_je_data = {
                        'company': self.company_id,
                        'transaction': transaction.id,
                        'account': opposing_account.id,
                        'date': transaction.date,
                        'description': transaction.description or '',
                        'debit_amount': opp_debit,
                        'credit_amount': opp_credit,
                        'cost_center': cost_center_id,
                        'state': 'pending',
                    }
                    
                    opposing_je_serializer = JournalEntrySerializer(data=opposing_je_data, context={'lookup_cache': self.lookup_cache})
                    if opposing_je_serializer.is_valid(raise_exception=True):
                        opposing_je = opposing_je_serializer.save()
                        journal_entry_outputs.append({
                            '__row_id': f"auto_je_opp_{transaction_id}",
                            'status': 'success',
                            'action': 'create',
                            'data': {
                                'id': opposing_je.id,
                                'account_id': opposing_account.id,
                                'account_name': opposing_account.name,
                                'transaction_id': transaction.id,
                                'debit_amount': str(opp_debit) if opp_debit else None,
                                'credit_amount': str(opp_credit) if opp_credit else None,
                            },
                            'message': 'ok',
                            'observations': [],
                            'external_id': None,
                        })
                        
            except Exception as e:
                logger.error(f"ETL: Error creating JournalEntries for Transaction {transaction_id}: {e}", exc_info=True)
                self._add_warning(
                    warning_type='auto_journal_entry_error',
                    message=f"Error auto-creating JournalEntries for Transaction {transaction_id}: {str(e)}",
                    model='Transaction',
                    record_id=transaction_id
                )
        
        # Add JournalEntry outputs to result
        if journal_entry_outputs:
            transaction_import_result.setdefault('imports', []).append({
                'model': 'JournalEntry',
                'result': journal_entry_outputs
            })
        
        return transaction_import_result
    
    def _auto_create_journal_entries(self, import_result: dict, extra_fields_by_model: Dict[str, List[dict]]):
        """
        Automatically create JournalEntries for Transactions when auto_create_journal_entries is enabled.
        This happens directly without IntegrationRules, but IntegrationRules can still fire afterward.
        
        Configuration comes from request parameter, not from transformation rule.
        """
        from accounting.models import Account, BankAccount, Transaction, JournalEntry
        from accounting.serializers import JournalEntrySerializer
        
        if self.debug_account_substitution:
            logger.info(f"ETL OPPOSING JE: _auto_create_journal_entries CALLED")
        
        # Check if we have any Transaction outputs
        transaction_outputs = import_result.get('results', {}).get('Transaction', [])
        if self.debug_account_substitution:
            logger.info(f"ETL OPPOSING JE: Found {len(transaction_outputs)} Transaction outputs")
        if not transaction_outputs:
            if self.debug_account_substitution:
                logger.warning(f"ETL OPPOSING JE: No Transaction outputs found, returning early")
            return
        
        # Check if auto-create is enabled (from request parameter)
        auto_config = self.auto_create_journal_entries or {}
        if self.debug_account_substitution:
            logger.info(f"ETL OPPOSING JE: auto_create_journal_entries config: {auto_config}")
            logger.info(f"ETL OPPOSING JE: auto_config.get('enabled'): {auto_config.get('enabled', False)}")
        if not auto_config.get('enabled', False):
            if self.debug_account_substitution:
                logger.warning(f"ETL OPPOSING JE: auto_create_journal_entries is NOT ENABLED, returning early")
            return
        
        if self.debug_account_substitution:
            logger.info(f"ETL OPPOSING JE: auto_create_journal_entries is ENABLED - proceeding")
        logger.info(f"ETL: Auto-creating JournalEntries for {len(transaction_outputs)} Transactions")
        
        # Cache pending bank accounts by currency_id (prevents duplicate key violations)
        # ensure_pending_bank_structs is expensive, so we call it once per currency
        pending_bank_cache: Dict[int, tuple] = {}  # currency_id -> (pending_ba, pending_gl)
        
        # Get configuration
        bank_account_field = auto_config.get('bank_account_field', 'bank_account_id')
        opposing_account_field = auto_config.get('opposing_account_field', 'account_path')
        opposing_account_lookup = auto_config.get('opposing_account_lookup', 'path')
        path_separator = auto_config.get('path_separator', ' > ')
        cost_center_field = auto_config.get('cost_center_field')
        
        # Get extra_fields for Transactions
        extra_fields_list = extra_fields_by_model.get('Transaction', [])
        
        # Pre-load substitution rules cache for performance
        from multitenancy.models import SubstitutionRule
        substitution_rules_cache = {}
        substitution_rules = SubstitutionRule.objects.filter(company_id=self.company_id)
        for rule in substitution_rules:
            key = (rule.model_name, rule.field_name)
            if key not in substitution_rules_cache:
                substitution_rules_cache[key] = []
            substitution_rules_cache[key].append(rule)
        
        # Create fast substitution function (with filter_conditions support)
        from multitenancy.formula_engine import _passes_conditions
        def apply_substitution_fast(value, model_name, field_name, row_context=None):
            """Fast substitution using pre-loaded cache with filter_conditions support."""
            if not value or not model_name or not field_name:
                return value
            key = (model_name, field_name)
            rules = substitution_rules_cache.get(key, [])
            for rule in rules:
                try:
                    # Check filter_conditions if present
                    if hasattr(rule, 'filter_conditions') and rule.filter_conditions:
                        if not _passes_conditions(row_context or {}, rule.filter_conditions):
                            continue
                    
                    str_value = str(value)
                    if rule.match_type == 'exact':
                        if str_value == rule.match_value:
                            return rule.substitution_value
                    elif rule.match_type == 'regex':
                        import re
                        return re.sub(rule.match_value, rule.substitution_value, str_value)
                    elif rule.match_type == 'caseless':
                        import unicodedata
                        normalized_value = unicodedata.normalize('NFD', str_value.lower())
                        normalized_match = unicodedata.normalize('NFD', rule.match_value.lower())
                        if normalized_value == normalized_match:
                            return rule.substitution_value
                except Exception as e:
                    logger.warning(f"ETL: Error in substitution rule {rule.id}: {e}")
            return value
        
        # Track created JournalEntries for result
        journal_entries_created = []
        
        # Build transaction_id -> Excel row metadata mapping for JournalEntry grouping
        transaction_to_excel_row_map = {}
        for idx, output in enumerate(transaction_outputs):
            if output.get('status') != 'success' or output.get('action') != 'create':
                continue
            
            transaction_data = output.get('data', {})
            transaction_id = transaction_data.get('id')
            
            if transaction_id and idx < len(extra_fields_list):
                extra_fields = extra_fields_list[idx]
                transaction_to_excel_row_map[transaction_id] = {
                    'excel_row_id': extra_fields.get('__excel_row_id'),
                    'excel_row_number': extra_fields.get('__excel_row_number'),
                    'excel_sheet_name': extra_fields.get('__excel_sheet_name', 'Unknown')
                }
        
        # Collect all transaction IDs first, then bulk fetch them
        # This is more efficient and works better in transaction contexts
        transaction_ids = []
        transaction_id_to_index = {}
        
        for idx, output in enumerate(transaction_outputs):
            if output.get('status') != 'success' or output.get('action') != 'create':
                continue
            
            transaction_data = output.get('data', {})
            transaction_id = transaction_data.get('id')
            
            if not transaction_id:
                error_msg = f"Transaction output at index {idx} has no ID"
                logger.warning(f"ETL: {error_msg}, skipping JournalEntry creation")
                logger.debug(f"ETL: Transaction output data: {transaction_data}")
                self._add_warning(
                    warning_type='missing_transaction_id',
                    message=error_msg,
                    model='Transaction',
                    row_index=idx,
                    output_data=transaction_data
                )
                continue
            
            transaction_ids.append(transaction_id)
            transaction_id_to_index[transaction_id] = idx
        
        # Bulk fetch all Transactions at once (more efficient and works in transaction context)
        if not transaction_ids:
            logger.info("ETL: No valid Transaction IDs found for JournalEntry creation")
            return
        
        try:
            # Use filter().in_bulk() for efficient bulk lookup
            # This works within the transaction context even in preview mode
            # In preview mode, Transactions exist in the transaction context even if marked for rollback
            # We need to query them before the transaction is actually rolled back
            logger.debug(f"ETL: Looking up {len(transaction_ids)} Transactions: {transaction_ids[:5]}...")
            
            transactions_dict = Transaction.objects.filter(
                id__in=transaction_ids,
                company_id=self.company_id
            ).in_bulk()
            
            logger.debug(f"ETL: Found {len(transactions_dict)} Transactions out of {len(transaction_ids)} requested")
            
            # Debug: Check if any transactions exist at all for this company
            if len(transactions_dict) == 0:
                total_for_company = Transaction.objects.filter(company_id=self.company_id).count()
                logger.warning(f"ETL: No Transactions found. Total Transactions for company {self.company_id}: {total_for_company}")
                # Try querying without company filter to see if IDs exist
                any_transactions = Transaction.objects.filter(id__in=transaction_ids).count()
                logger.warning(f"ETL: Transactions with these IDs exist (any company): {any_transactions}")
            
            if len(transactions_dict) < len(transaction_ids):
                missing_ids = set(transaction_ids) - set(transactions_dict.keys())
                logger.warning(f"ETL: {len(missing_ids)} Transactions not found: {missing_ids}")
                for missing_id in missing_ids:
                    idx = transaction_id_to_index.get(missing_id)
                    if idx is not None:
                        output = transaction_outputs[idx]
                        transaction_data = output.get('data', {})
                        self._add_warning(
                            warning_type='transaction_not_found',
                            message=f"Transaction {missing_id} not found (company_id={self.company_id})",
                            model='Transaction',
                            transaction_id=missing_id,
                            company_id=self.company_id,
                            row_index=idx,
                            output_data=transaction_data
                        )
            
            # Process each Transaction
            for transaction_id, idx in transaction_id_to_index.items():
                transaction = transactions_dict.get(transaction_id)
                
                if not transaction:
                    error_msg = f"Transaction {transaction_id} not found (company_id={self.company_id})"
                    logger.warning(f"ETL: {error_msg}, skipping JournalEntry creation")
                    output = transaction_outputs[idx]
                    transaction_data = output.get('data', {})
                    logger.debug(f"ETL: Transaction data from output: {transaction_data}")
                    self._add_warning(
                        warning_type='transaction_not_found',
                        message=error_msg,
                        model='Transaction',
                        transaction_id=transaction_id,
                        company_id=self.company_id,
                        row_index=idx,
                        output_data=transaction_data
                    )
                    continue
                
                # Get extra_fields for this row
                extra_fields = extra_fields_list[idx] if idx < len(extra_fields_list) else {}
                logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} (idx={idx}) - Original extra_fields: {extra_fields}")
                
                # Apply substitutions to extra_fields before using them (like in _import_transactions_with_journal_entries)
                substituted_extra_fields = self._apply_substitutions_to_extra_fields(
                    extra_fields,
                    auto_config,
                    substitution_rules_cache=substitution_rules_cache,
                    apply_substitution_fast=apply_substitution_fast
                )
                logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} (idx={idx}) - Substituted extra_fields: {substituted_extra_fields}")
                
                # Extract custom dates from extra_fields (if provided)
                logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - Transaction date: {transaction.date}")
                logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - Checking for custom dates in extra_fields...")
                
                je_bank_date = None
                je_book_date = None
                
                je_bank_date_raw = substituted_extra_fields.get('je_bank_date')
                logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - je_bank_date raw value: {je_bank_date_raw} (type: {type(je_bank_date_raw).__name__})")
                
                if je_bank_date_raw:
                    logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - Parsing je_bank_date from '{je_bank_date_raw}'...")
                    je_bank_date = self._parse_date_value(je_bank_date_raw)
                    if je_bank_date:
                        if isinstance(je_bank_date, date):
                            je_bank_date = date(je_bank_date.year, je_bank_date.month, je_bank_date.day)
                        logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - ✓ Successfully parsed je_bank_date={je_bank_date} (type: {type(je_bank_date).__name__})")
                        logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - je_bank_date vs transaction.date: {je_bank_date} vs {transaction.date}")
                        if je_bank_date < transaction.date:
                            logger.warning(f"ETL DATE DEBUG: Transaction {transaction_id} - ⚠ WARNING: je_bank_date ({je_bank_date}) is earlier than transaction.date ({transaction.date}) - this will cause validation error!")
                        else:
                            logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - ✓ je_bank_date is valid (>= transaction.date)")
                    else:
                        logger.warning(f"ETL DATE DEBUG: Transaction {transaction_id} - ✗ Failed to parse je_bank_date='{je_bank_date_raw}' - will fallback to transaction.date={transaction.date}")
                else:
                    logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - No je_bank_date provided in extra_fields - will use transaction.date={transaction.date}")
                
                je_book_date_raw = substituted_extra_fields.get('je_book_date')
                logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - je_book_date raw value: {je_book_date_raw} (type: {type(je_book_date_raw).__name__})")
                
                if je_book_date_raw:
                    logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - Parsing je_book_date from '{je_book_date_raw}'...")
                    je_book_date = self._parse_date_value(je_book_date_raw)
                    if je_book_date:
                        from datetime import date as date_type
                        if isinstance(je_book_date, date_type):
                            je_book_date = date_type(je_book_date.year, je_book_date.month, je_book_date.day)
                        logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - ✓ Successfully parsed je_book_date={je_book_date} (type: {type(je_book_date).__name__})")
                        logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - je_book_date vs transaction.date: {je_book_date} vs {transaction.date}")
                        if je_book_date < transaction.date:
                            logger.warning(f"ETL DATE DEBUG: Transaction {transaction_id} - ⚠ WARNING: je_book_date ({je_book_date}) is earlier than transaction.date ({transaction.date}) - this will cause validation error!")
                        else:
                            logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - ✓ je_book_date is valid (>= transaction.date)")
                    else:
                        logger.warning(f"ETL DATE DEBUG: Transaction {transaction_id} - ✗ Failed to parse je_book_date='{je_book_date_raw}' - will fallback to transaction.date={transaction.date}")
                else:
                    logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - No je_book_date provided in extra_fields - will use transaction.date={transaction.date}")
                
                # Summary of date decisions
                final_bank_date = je_bank_date if je_bank_date else transaction.date
                final_book_date = je_book_date if je_book_date else transaction.date
                logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - FINAL DATE DECISION:")
                logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} -   Bank JE will use: {final_bank_date} {'(CUSTOM)' if je_bank_date else '(TRANSACTION DATE)'}")
                logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} -   Book JE will use: {final_book_date} {'(CUSTOM)' if je_book_date else '(TRANSACTION DATE)'}")
                
                try:
                    # Track JournalEntries created for this transaction
                    transaction_jes = []
                    
                    logger.debug(f"ETL: Processing Transaction {transaction_id} for JournalEntry creation")
                    
                    amount = Decimal(str(transaction.amount))
                    abs_amount = abs(amount)
                    
                    # Check if we should use pending bank account
                    use_pending_bank = auto_config.get('use_pending_bank_account', False)
                    
                    # Look up bank account
                    bank_ledger_account = None
                    bank_designation_pending = False
                    
                    if use_pending_bank:
                        # Use cached pending bank account (prevents duplicate key violations)
                        currency_id = transaction.currency_id
                        if currency_id not in pending_bank_cache:
                            from accounting.services.bank_structs import ensure_pending_bank_structs
                            pending_ba, pending_gl = ensure_pending_bank_structs(
                                company_id=self.company_id,
                                currency_id=currency_id
                            )
                            pending_bank_cache[currency_id] = (pending_ba, pending_gl)
                        else:
                            pending_ba, pending_gl = pending_bank_cache[currency_id]
                        bank_ledger_account = pending_gl
                        bank_designation_pending = True
                        logger.debug(f"ETL: Using pending bank account for Transaction {transaction_id}")
                    else:
                        # Look up specific bank account (use substituted extra_fields)
                        bank_account_id_str = substituted_extra_fields.get(bank_account_field)
                        if bank_account_id_str:
                            try:
                                bank_account_id = int(bank_account_id_str)
                                bank_account = BankAccount.objects.filter(
                                    company_id=self.company_id,
                                    id=bank_account_id
                                ).first()
                                if bank_account:
                                    bank_ledger_account = Account.objects.filter(
                                        company_id=self.company_id,
                                        bank_account_id=bank_account.id
                                    ).first()
                            except (ValueError, TypeError):
                                pass
                    
                    # Look up opposing account (use substituted extra_fields with substitutions applied)
                    opposing_account = None
                    opposing_account_value = substituted_extra_fields.get(opposing_account_field)
                    
                    if self.debug_account_substitution:
                        logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} - Extracting opposing account")
                        logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} - opposing_account_field: '{opposing_account_field}'")
                        logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} - opposing_account_value from substituted_extra_fields: '{opposing_account_value}'")
                        logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} - opposing_account_lookup: '{opposing_account_lookup}'")
                        logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} - path_separator: '{path_separator}'")
                    
                    if opposing_account_value:
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} - Looking up opposing account with value='{opposing_account_value}', lookup_type='{opposing_account_lookup}'")
                        if opposing_account_lookup == 'path':
                            opposing_account = self._lookup_account(opposing_account_value, 'path', path_separator)
                        elif opposing_account_lookup == 'code':
                            opposing_account = self._lookup_account(opposing_account_value, 'code')
                        elif opposing_account_lookup == 'id':
                            try:
                                account_id = int(opposing_account_value)
                                if self.debug_account_substitution:
                                    logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} - Looking up account by ID: {account_id}")
                                opposing_account = Account.objects.filter(
                                    company_id=self.company_id,
                                    id=account_id
                                ).first()
                                if self.debug_account_substitution:
                                    logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} - ID lookup result: {opposing_account.id if opposing_account else None} ({opposing_account.name if opposing_account else 'NOT FOUND'})")
                            except (ValueError, TypeError) as e:
                                if self.debug_account_substitution:
                                    logger.warning(f"ETL OPPOSING JE: Transaction {transaction_id} - Error converting opposing_account_value to int: {e}")
                                pass
                        
                        if opposing_account:
                            if self.debug_account_substitution:
                                logger.info(f"ETL OPPOSING JE: Transaction {transaction_id} - SUCCESS: Found opposing account - ID: {opposing_account.id}, Name: {opposing_account.name}, Code: {getattr(opposing_account, 'account_code', 'N/A')}")
                        else:
                            if self.debug_account_substitution:
                                logger.warning(f"ETL OPPOSING JE: Transaction {transaction_id} - FAILED: Account not found for value='{opposing_account_value}' (lookup_type='{opposing_account_lookup}')")
                    else:
                        if self.debug_account_substitution:
                            logger.warning(f"ETL OPPOSING JE: Transaction {transaction_id} - SKIPPED: No opposing_account_value found. Keys in substituted_extra_fields: {list(substituted_extra_fields.keys())}")
                    
                    # Calculate debit/credit
                    if amount >= 0:
                        # Positive = deposit/income
                        bank_debit, bank_credit = abs_amount, None
                        opp_debit, opp_credit = None, abs_amount
                    else:
                        # Negative = payment/expense
                        bank_debit, bank_credit = None, abs_amount
                        opp_debit, opp_credit = abs_amount, None
                    
                    # Look up cost center (optional, use substituted extra_fields)
                    cost_center_id = None
                    if cost_center_field:
                        cost_center_value = substituted_extra_fields.get(cost_center_field)
                        if cost_center_value:
                            # Could add cost center path lookup here if needed
                            try:
                                cost_center_id = int(cost_center_value)
                            except (ValueError, TypeError):
                                pass
                    
                    # Create bank account JournalEntry
                    # Create if we have a bank account OR if using pending bank account
                    if bank_ledger_account or use_pending_bank:
                        bank_je_final_date = je_bank_date if je_bank_date else transaction.date
                        logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - Creating Bank JE with date: {bank_je_final_date} {'(CUSTOM: je_bank_date)' if je_bank_date else '(DEFAULT: transaction.date)'}")
                        
                        bank_je_data = {
                            'company': self.company_id,
                            'transaction': transaction.id,  # Use transaction instance ID
                            'date': bank_je_final_date,
                            'description': transaction.description or '',
                            'debit_amount': bank_debit,
                            'credit_amount': bank_credit,
                            'cost_center': cost_center_id,
                            'state': 'pending',
                            'bank_designation_pending': bank_designation_pending,
                        }
                        
                        logger.debug(f"ETL: Creating bank JournalEntry for Transaction {transaction.id} (pending={bank_designation_pending}, date={bank_je_final_date})")
                        
                        # Only set account if not using pending bank account
                        if bank_ledger_account and not bank_designation_pending:
                            bank_je_data['account'] = bank_ledger_account.id
                        
                        bank_je_serializer = JournalEntrySerializer(data=bank_je_data, context={'lookup_cache': self.lookup_cache})
                        if bank_je_serializer.is_valid(raise_exception=True):
                            bank_je = bank_je_serializer.save()
                            
                            # Confirm the date that was actually saved
                            logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - ✓ Bank JE created successfully!")
                            logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - Bank JE ID: {bank_je.id}, Saved date: {bank_je.date}")
                            logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - Bank JE date verification: requested={bank_je_final_date}, saved={bank_je.date}, match={bank_je.date == bank_je_final_date}")
                            
                            # Add notes metadata for auto-created journal entry
                            if hasattr(bank_je, 'notes'):
                                from multitenancy.utils import build_notes_metadata
                                from crum import get_current_user
                                
                                current_user = get_current_user()
                                user_name = current_user.username if current_user and current_user.is_authenticated else None
                                user_id = current_user.id if current_user and current_user.is_authenticated else None
                                
                                # Get Excel row metadata from extra_fields
                                excel_row_id = extra_fields.get('__excel_row_id')
                                excel_row_number = extra_fields.get('__excel_row_number')
                                excel_sheet_name = extra_fields.get('__excel_sheet_name')
                                
                                notes_metadata = {
                                    'source': 'ETL',
                                    'function': 'ETLPipelineService._auto_create_journal_entries',
                                    'filename': self.file_name,
                                    'user': user_name,
                                    'user_id': user_id,
                                    'log_id': self.log.id if self.log else None,
                                    'transaction_id': transaction.id,
                                }
                                
                                if excel_row_id:
                                    notes_metadata['excel_row_id'] = excel_row_id
                                if excel_row_number:
                                    notes_metadata['row_number'] = excel_row_number
                                if excel_sheet_name:
                                    notes_metadata['sheet_name'] = excel_sheet_name
                                
                                bank_je.notes = build_notes_metadata(**notes_metadata)
                                bank_je.save(update_fields=['notes'])
                            account_id = bank_je.account_id if bank_je.account_id else None
                            account_name = bank_ledger_account.name if bank_ledger_account else "Pending Bank Account"
                            
                            # Verify transaction_id is set correctly
                            actual_transaction_id = bank_je.transaction_id if hasattr(bank_je, 'transaction_id') else None
                            if actual_transaction_id != transaction.id:
                                logger.warning(f"ETL: JournalEntry {bank_je.id} transaction_id mismatch: expected {transaction.id}, got {actual_transaction_id}")
                            
                            transaction_jes.append({
                                'id': bank_je.id,
                                'account_id': account_id,
                                'account_name': account_name,
                                'type': 'bank',
                                'transaction_id': actual_transaction_id or transaction.id,  # Use actual ID from saved object
                                'debit_amount': str(bank_debit) if bank_debit else None,
                                'credit_amount': str(bank_credit) if bank_credit else None,
                                'bank_designation_pending': bank_designation_pending,
                            })
                            logger.debug(f"ETL: Created bank JournalEntry {bank_je.id} for Transaction {transaction.id} (pending={bank_designation_pending}, transaction_id={actual_transaction_id})")
                    
                    # Create opposing account JournalEntry
                    if self.debug_account_substitution:
                        logger.info(f"ETL OPPOSING JE: Transaction {transaction.id} - Checking if opposing JE should be created")
                        logger.info(f"ETL OPPOSING JE: Transaction {transaction.id} - opposing_account found: {bool(opposing_account)}")
                    
                    if opposing_account:
                        opposing_je_final_date = je_book_date if je_book_date else transaction.date
                        logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - Creating Book/Opposing JE with date: {opposing_je_final_date} {'(CUSTOM: je_book_date)' if je_book_date else '(DEFAULT: transaction.date)'}")
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: Transaction {transaction.id} - Creating opposing JE with account_id={opposing_account.id}, debit={opp_debit}, credit={opp_credit}, date={opposing_je_final_date}")
                        
                        opposing_je_data = {
                            'company': self.company_id,
                            'transaction': transaction.id,  # Use transaction instance ID
                            'account': opposing_account.id,
                            'date': opposing_je_final_date,
                            'description': transaction.description or '',
                            'debit_amount': opp_debit,
                            'credit_amount': opp_credit,
                            'cost_center': cost_center_id,
                            'state': 'pending',
                        }
                        
                        if self.debug_account_substitution:
                            logger.info(f"ETL OPPOSING JE: Transaction {transaction.id} - Opposing JE data: {opposing_je_data}")
                        logger.debug(f"ETL: Creating opposing JournalEntry for Transaction {transaction.id} with account {opposing_account.id}, date={opposing_je_final_date}")
                        
                        opposing_je_serializer = JournalEntrySerializer(data=opposing_je_data, context={'lookup_cache': self.lookup_cache})
                        if opposing_je_serializer.is_valid(raise_exception=True):
                            if self.debug_account_substitution:
                                logger.info(f"ETL OPPOSING JE: Transaction {transaction.id} - Serializer is valid, saving opposing JE")
                            opposing_je = opposing_je_serializer.save()
                            
                            # Confirm the date that was actually saved
                            logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - ✓ Book/Opposing JE created successfully!")
                            logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - Book JE ID: {opposing_je.id}, Saved date: {opposing_je.date}")
                            logger.info(f"ETL DATE DEBUG: Transaction {transaction_id} - Book JE date verification: requested={opposing_je_final_date}, saved={opposing_je.date}, match={opposing_je.date == opposing_je_final_date}")
                            if self.debug_account_substitution:
                                logger.info(f"ETL OPPOSING JE: Transaction {transaction.id} - SUCCESS: Created opposing JE ID={opposing_je.id}")
                            
                            # Add notes metadata for auto-created journal entry
                            if hasattr(opposing_je, 'notes'):
                                from multitenancy.utils import build_notes_metadata
                                from crum import get_current_user

                                current_user = get_current_user()
                                user_name = current_user.username if current_user and current_user.is_authenticated else None
                                user_id = current_user.id if current_user and current_user.is_authenticated else None
                                
                                # Get Excel row metadata from extra_fields
                                excel_row_id = extra_fields.get('__excel_row_id')
                                excel_row_number = extra_fields.get('__excel_row_number')
                                excel_sheet_name = extra_fields.get('__excel_sheet_name')
                                
                                notes_metadata = {
                                    'source': 'ETL',
                                    'function': 'ETLPipelineService._auto_create_journal_entries',
                                    'filename': self.file_name,
                                    'user': user_name,
                                    'user_id': user_id,
                                    'log_id': self.log.id if self.log else None,
                                    'transaction_id': transaction.id,
                                }
                                
                                if excel_row_id:
                                    notes_metadata['excel_row_id'] = excel_row_id
                                if excel_row_number:
                                    notes_metadata['row_number'] = excel_row_number
                                if excel_sheet_name:
                                    notes_metadata['sheet_name'] = excel_sheet_name
                                
                                opposing_je.notes = build_notes_metadata(**notes_metadata)
                                opposing_je.save(update_fields=['notes'])
                            
                            # Verify transaction_id is set correctly
                            actual_transaction_id = opposing_je.transaction_id if hasattr(opposing_je, 'transaction_id') else None
                            if actual_transaction_id != transaction.id:
                                logger.warning(f"ETL: JournalEntry {opposing_je.id} transaction_id mismatch: expected {transaction.id}, got {actual_transaction_id}")
                            
                            transaction_jes.append({
                                'id': opposing_je.id,
                                'account_id': opposing_account.id,
                                'account_name': opposing_account.name,
                                'type': 'opposing',
                                'transaction_id': actual_transaction_id or transaction.id,  # Use actual ID from saved object
                                'debit_amount': str(opp_debit) if opp_debit else None,
                                'credit_amount': str(opp_credit) if opp_credit else None,
                            })
                            logger.debug(f"ETL: Created opposing JournalEntry {opposing_je.id} for Transaction {transaction.id} (transaction_id={actual_transaction_id})")
                        else:
                            logger.error(f"ETL OPPOSING JE: Transaction {transaction.id} - ERROR: Serializer validation failed: {opposing_je_serializer.errors}")
                    else:
                        logger.warning(f"ETL OPPOSING JE: Transaction {transaction.id} - SKIPPED: No opposing_account, opposing JE will not be created")
                    
                    # Add to main list
                    journal_entries_created.extend(transaction_jes)
                    
                except Exception as e:
                    self._add_warning(
                        warning_type='auto_journal_entry_error',
                        message=f"Error auto-creating JournalEntries for Transaction {transaction_id}: {str(e)}",
                        model='Transaction',
                        record_id=transaction_id
                    )
                    logger.error(f"ETL: Error auto-creating JournalEntries for Transaction {transaction_id}: {e}", exc_info=True)
        
        except Exception as e:
            # Handle errors during bulk fetch or processing
            error_msg = f"Error during bulk Transaction lookup or JournalEntry creation: {str(e)}"
            logger.error(f"ETL: {error_msg}", exc_info=True)
            self._add_warning(
                warning_type='bulk_journal_entry_error',
                message=error_msg,
                model='Transaction',
                transaction_count=len(transaction_ids),
                error=str(e)
            )
        
        # Update result with created JournalEntries
        if journal_entries_created:
            if 'JournalEntry' not in import_result.get('results', {}):
                import_result.setdefault('results', {})['JournalEntry'] = []
            
            for je_data in journal_entries_created:
                # Get Excel row metadata from the transaction that created this JournalEntry
                transaction_id = je_data.get('transaction_id')
                excel_metadata = None
                if transaction_id and transaction_id in transaction_to_excel_row_map:
                    tx_row_info = transaction_to_excel_row_map[transaction_id]
                    excel_metadata = {
                        '__excel_row_id': tx_row_info['excel_row_id'],
                        '__excel_row_number': tx_row_info['excel_row_number'],
                        '__excel_sheet_name': tx_row_info['excel_sheet_name']
                    }
                
                import_result['results']['JournalEntry'].append({
                    '__row_id': None,
                    'status': 'success',
                    'action': 'create',
                    'data': {
                        'id': je_data['id'],
                        'account_id': je_data['account_id'],
                        'account_name': je_data.get('account_name'),
                        'transaction_id': je_data['transaction_id'],
                        'debit_amount': je_data['debit_amount'],
                        'credit_amount': je_data['credit_amount'],
                        'bank_designation_pending': je_data.get('bank_designation_pending', False),
                    },
                    'message': f"Auto-created {je_data['type']} JournalEntry",
                })
                
                # Add Excel metadata to the JournalEntry data if available
                if excel_metadata:
                    import_result['results']['JournalEntry'][-1]['data']['__excel_row_id'] = excel_metadata.get('__excel_row_id')
                    import_result['results']['JournalEntry'][-1]['data']['__excel_row_number'] = excel_metadata.get('__excel_row_number')
                    import_result['results']['JournalEntry'][-1]['data']['__excel_sheet_name'] = excel_metadata.get('__excel_sheet_name')
            
            logger.info(f"ETL: Auto-created {len(journal_entries_created)} JournalEntries")
    
    def _trigger_events_for_created_records(self, import_result: dict, extra_fields_by_model: Dict[str, List[dict]]):
        """
        Trigger IntegrationRule events for each created record.
        
        For example, when a Transaction is created, trigger 'transaction_created' event
        with the transaction data and any extra_fields from the transformation.
        """
        from multitenancy.tasks import trigger_integration_event
        
        # Map model names to trigger events
        MODEL_EVENT_MAP = {
            'Transaction': 'transaction_created',
            'JournalEntry': 'journal_entry_created',
        }
        
        for model_name, outputs in import_result.get('results', {}).items():
            event_name = MODEL_EVENT_MAP.get(model_name)
            if not event_name:
                continue
            
            # Get the rule to check if triggers are enabled
            rule = self.transformation_rules.get(model_name)
            trigger_options = (rule.trigger_options or {}) if rule else {}
            
            if not trigger_options.get('enabled', True):
                logger.info(f"ETL: Triggers disabled for {model_name}")
                continue
            
            # Check if this specific event is enabled
            allowed_events = trigger_options.get('events', [event_name])
            if event_name not in allowed_events:
                continue
            
            use_celery = trigger_options.get('use_celery', True)
            extra_fields_list = extra_fields_by_model.get(model_name, [])
            
            # Trigger event for each created record
            for idx, output in enumerate(outputs):
                if output.get('status') != 'success' or output.get('action') != 'create':
                    continue
                
                record_data = output.get('data', {})
                record_id = record_data.get('id')
                
                if not record_id:
                    continue
                
                # Get extra_fields for this row
                extra_fields = extra_fields_list[idx] if idx < len(extra_fields_list) else {}
                
                # Build trigger payload
                payload = {
                    f'{model_name.lower()}_id': record_id,
                    model_name.lower(): record_data,
                    'extra_fields': extra_fields,
                    'source': 'etl_import',
                    'log_id': self.log.id if self.log else None,
                }
                
                logger.info(f"ETL: Triggering {event_name} for {model_name} id={record_id}")
                
                try:
                    if use_celery:
                        trigger_integration_event.delay(self.company_id, event_name, payload)
                    else:
                        trigger_integration_event(self.company_id, event_name, payload)
                except Exception as e:
                    self._add_warning(
                        warning_type='trigger_error',
                        message=f"Error triggering {event_name} for {model_name} id={record_id}: {str(e)}",
                        model=model_name,
                        record_id=record_id
                    )
    
    def _preview_data(self) -> dict:
        """
        Return full preview of the pipeline including IntegrationRule outputs.
        
        Runs the complete import + triggers in a transaction that gets rolled back,
        so no actual data is persisted but user sees what WOULD be created.
        """
        from django.db import transaction as db_transaction
        from django.apps import apps
        from multitenancy.models import IntegrationRule
        from multitenancy.formula_engine import execute_rule
        
        preview = {
            'transformed_data': {},
            'would_create': {},
            'would_fail': {},
            'import_errors': [],
            'integration_rules_preview': [],
            'integration_rules_available': [],
            'transformation_rules_used': [],  # Metadata about rules that were applied
            'total_rows': 0,
        }
        
        # Add transformation rule metadata for debugging
        for model_name, rule in self.transformation_rules.items():
            preview['transformation_rules_used'].append({
                'id': rule.id,
                'name': rule.name,
                'target_model': rule.target_model,
                'source_sheet_name': rule.source_sheet_name,
                'column_mappings': rule.column_mappings,
                'column_concatenations': rule.column_concatenations,
                'computed_columns': rule.computed_columns,
                'default_values': rule.default_values,
                'row_filter': rule.row_filter,
                'extra_fields_for_trigger': rule.extra_fields_for_trigger,
                'trigger_options': rule.trigger_options,
                'skip_rows': rule.skip_rows,
                'header_row': rule.header_row,
                'execution_order': rule.execution_order,
            })
        
        # Store transformed data preview
        for model_name, rows in self.transformed_data.items():
            # Make a deep copy to avoid modifying original
            rows_copy = [dict(row) for row in rows]
            preview['transformed_data'][model_name] = {
                'row_count': len(rows_copy),
                'rows': rows_copy,
                'sample_columns': list(rows_copy[0].keys()) if rows_copy else []
            }
            preview['total_rows'] += len(rows_copy)
        
        # Check for available IntegrationRules
        MODEL_EVENT_MAP = {
            'Transaction': 'transaction_created',
            'JournalEntry': 'journal_entry_created',
        }
        for model_name in self.transformed_data.keys():
            event_name = MODEL_EVENT_MAP.get(model_name)
            if event_name:
                rules = IntegrationRule.objects.filter(
                    company_id=self.company_id,
                    trigger_event=event_name,
                    is_active=True
                ).values('id', 'name', 'trigger_event')
                preview['integration_rules_available'].extend(list(rules))
        
        # Run full import + triggers in a transaction that will be rolled back
        # Initialize extra_fields_by_model and store as instance variable
        self.extra_fields_by_model = {}
        
        try:
            with db_transaction.atomic():
                # Create a savepoint we can rollback to
                sid = db_transaction.savepoint()
                
                try:
                    # Extract extra_fields and filter invalid model fields before import
                    extra_fields_by_model = {}
                    cleaned_data: Dict[str, List[dict]] = {}
                    
                    for model_name, rows in self.transformed_data.items():
                        extra_fields_by_model[model_name] = []
                        cleaned_data[model_name] = []
                        
                        # Get valid model fields
                        app_label = MODEL_APP_MAP.get(model_name)
                        valid_fields = set()
                        if app_label:
                            try:
                                model = apps.get_model(app_label, model_name)
                                valid_fields = {f.name for f in model._meta.fields}
                                # Also include _id variants for ForeignKey
                                for f in model._meta.fields:
                                    if hasattr(f, 'column'):
                                        valid_fields.add(f.column)
                            except LookupError:
                                pass
                        
                        for idx, row in enumerate(rows):
                            extra_fields = row.pop('__extra_fields__', {})
                            
                            # Preserve Excel row metadata for tracking/grouping
                            excel_row_number = row.pop('__excel_row_number', None)
                            excel_sheet_name = row.pop('__excel_sheet_name', None)
                            excel_row_id = row.pop('__excel_row_id', None)
                            
                            # Move invalid fields to extra_fields
                            cleaned_row = {}
                            invalid_fields = {}
                            for key, value in row.items():
                                # Check if this is a valid model field
                                field_name = key.replace('_id', '') if key.endswith('_id') else key
                                if key in valid_fields or field_name in valid_fields or not valid_fields:
                                    cleaned_row[key] = value
                                else:
                                    invalid_fields[key] = value
                            
                            # Merge invalid fields into extra_fields
                            extra_fields.update(invalid_fields)
                            
                            # Store Excel metadata in extra_fields so it's available for grouping
                            if excel_row_number is not None:
                                extra_fields['__excel_row_number'] = excel_row_number
                            if excel_sheet_name is not None:
                                extra_fields['__excel_sheet_name'] = excel_sheet_name
                            if excel_row_id is not None:
                                extra_fields['__excel_row_id'] = excel_row_id
                            
                            extra_fields_by_model[model_name].append(extra_fields)
                            cleaned_data[model_name].append(cleaned_row)
                            
                            if invalid_fields and idx == 0:
                                # Log once about moved fields
                                preview['import_errors'].append({
                                    'type': 'fields_moved_to_extra',
                                    'message': f"Fields not in {model_name} model moved to extra_fields: {list(invalid_fields.keys())}",
                                    'fields': list(invalid_fields.keys()),
                                    'hint': "Use extra_fields_for_trigger in your transformation rule to pass these to IntegrationRules"
                                })
                    
                    # Store extra_fields_by_model as instance variable for v2 response building
                    self.extra_fields_by_model = extra_fields_by_model
                    
                    # Coerce dates from ISO format to date objects
                    from datetime import datetime, date as date_type
                    for model_name, rows in cleaned_data.items():
                        for row in rows:
                            if 'date' in row and row['date']:
                                val = row['date']
                                if isinstance(val, str):
                                    # Parse ISO datetime string to date
                                    try:
                                        if 'T' in val:
                                            row['date'] = datetime.fromisoformat(val.replace('Z', '+00:00')).date()
                                        else:
                                            row['date'] = datetime.strptime(val, '%Y-%m-%d').date()
                                    except (ValueError, TypeError):
                                        pass  # Leave as is, let validation catch it
                                elif hasattr(val, 'date'):
                                    # pandas Timestamp
                                    row['date'] = val.date()
                    
                    # Filter out rows with null required fields (amount)
                    valid_rows_by_model: Dict[str, List[dict]] = {}
                    failed_rows_by_model: Dict[str, List[dict]] = {}
                    
                    for model_name, rows in cleaned_data.items():
                        valid_rows_by_model[model_name] = []
                        failed_rows_by_model[model_name] = []
                        valid_extra_fields = []
                        
                        for idx, row in enumerate(rows):
                            # Get Excel row metadata from extra_fields for better error reporting
                            extra_fields = extra_fields_by_model[model_name][idx]
                            excel_row_number = extra_fields.get('__excel_row_number', idx + 1)
                            excel_sheet_name = extra_fields.get('__excel_sheet_name', 'Unknown')
                            excel_row_id = extra_fields.get('__excel_row_id', f"{excel_sheet_name}:{excel_row_number}")
                            
                            # Check for null amount (required field for Transaction)
                            amount = row.get('amount')
                            is_null_amount = amount is None or (isinstance(amount, str) and amount.strip() == '')
                            
                            if model_name == 'Transaction' and is_null_amount:
                                failed_rows_by_model[model_name].append({
                                    'row_number': excel_row_number,
                                    'excel_sheet': excel_sheet_name,
                                    'excel_row_id': excel_row_id,
                                    'reason': 'amount is null/missing',
                                    'data': row
                                })
                            else:
                                valid_rows_by_model[model_name].append(row)
                                valid_extra_fields.append(extra_fields)
                        
                        # Update extra_fields to only include valid rows
                        extra_fields_by_model[model_name] = valid_extra_fields
                    
                    # Report failed rows
                    for model_name, failed in failed_rows_by_model.items():
                        if failed:
                            preview['would_fail'][model_name] = {
                                'count': len(failed),
                                'rows': failed[:10],  # First 10 failed rows
                                'total_failed': len(failed)
                            }
                    
                    # Run import with valid rows only
                    sheets = []
                    for model_name, rows in valid_rows_by_model.items():
                        if rows:  # Only include if there are valid rows
                            sheets.append({
                                'model': model_name,
                                'rows': rows
                            })
                    
                    if sheets:
                        # Separate Transaction sheets from other sheets
                        transaction_sheets = [s for s in sheets if s.get('model') == 'Transaction']
                        other_sheets = [s for s in sheets if s.get('model') != 'Transaction']
                        
                        # Process Transactions with JournalEntries in the same transaction
                        transaction_import_result = None
                        if transaction_sheets and self.auto_create_journal_entries:
                            # Custom import flow: create Transactions and JournalEntries together
                            transaction_import_result = self._import_transactions_with_journal_entries(
                                transaction_sheets, 
                                extra_fields_by_model.get('Transaction', [])
                            )
                        
                        # Process other sheets normally
                        other_import_result = None
                        if other_sheets:
                            other_import_result = execute_import_job(
                                company_id=self.company_id,
                                sheets=other_sheets,
                                commit=False,  # Preview mode - don't actually commit (transaction will rollback)
                                lookup_cache=self.lookup_cache
                            )
                        
                        # Merge results
                        import_result = {'imports': []}
                        if transaction_import_result:
                            import_result['imports'].extend(transaction_import_result.get('imports', []))
                        if other_import_result:
                            import_result['imports'].extend(other_import_result.get('imports', []))
                        
                        # If Transactions were processed separately, we don't need to call _auto_create_journal_entries
                        # because they were already created in _import_transactions_with_journal_entries
                        normalized_import_result = {'results': {}}
                        if not transaction_sheets or not self.auto_create_journal_entries:
                            # Process all sheets normally and create JournalEntries after
                            if not transaction_import_result and not other_import_result:
                                import_result = execute_import_job(
                                    company_id=self.company_id,
                                    sheets=sheets,
                                    commit=False,
                                    lookup_cache=self.lookup_cache
                                )
                            
                            # Normalize import_result format for auto-creation
                            for import_item in import_result.get('imports', []):
                                model_name = import_item.get('model')
                                outputs = import_item.get('result', [])
                                normalized_import_result['results'][model_name] = outputs
                            
                            # Auto-create JournalEntries for Transactions (if enabled)
                            self._auto_create_journal_entries(normalized_import_result, extra_fields_by_model)
                        else:
                            # Transactions were processed with JournalEntries, normalize the result
                            for import_item in import_result.get('imports', []):
                                model_name = import_item.get('model')
                                outputs = import_item.get('result', [])
                                normalized_import_result['results'][model_name] = outputs
                        
                        # JournalEntries are already in import_result from _import_transactions_with_journal_entries
                        # No need to add them again here
                        
                        # Capture what would be created, grouped by source Excel row
                        # execute_import_job returns {'imports': [{'model': '...', 'result': [...]}]}
                        
                        # Track Excel row to created records mapping
                        excel_row_groups: Dict[str, Dict[str, Any]] = {}
                        
                        # First pass: Build transaction_id -> excel_row_id mapping for JournalEntry grouping
                        transaction_to_excel_row_map = {}
                        for import_item in import_result.get('imports', []):
                            model_name = import_item.get('model')
                            if model_name == 'Transaction':
                                outputs = import_item.get('result', [])
                                model_extra_fields = extra_fields_by_model.get(model_name, [])
                                for idx, output in enumerate(outputs):
                                    if output.get('status') == 'success' and output.get('action') == 'create':
                                        record_data = output.get('data', {})
                                        transaction_id = record_data.get('id')
                                        if transaction_id:
                                            excel_row_info = model_extra_fields[idx] if idx < len(model_extra_fields) else {}
                                            excel_row_id = excel_row_info.get('__excel_row_id')
                                            excel_row_number = excel_row_info.get('__excel_row_number')
                                            excel_sheet_name = excel_row_info.get('__excel_sheet_name', 'Unknown')
                                            if not excel_row_id:
                                                excel_row_id = f"{excel_sheet_name}:{excel_row_number or (idx + 1)}"
                                            transaction_to_excel_row_map[transaction_id] = {
                                                'excel_row_id': excel_row_id,
                                                'excel_row_number': excel_row_number,
                                                'excel_sheet_name': excel_sheet_name
                                            }
                        
                        # Second pass: Process all models and group by Excel row
                        for import_item in import_result.get('imports', []):
                            model_name = import_item.get('model')
                            outputs = import_item.get('result', [])
                            
                            created_records = []
                            failed_records = []
                            
                            # Get the extra_fields for this model to track Excel row info
                            model_extra_fields = extra_fields_by_model.get(model_name, [])
                            
                            for idx, output in enumerate(outputs):
                                if output.get('status') == 'success' and output.get('action') == 'create':
                                    record_data = output.get('data', {})
                                    created_records.append(record_data)
                                    
                                    # Get Excel row metadata for this record
                                    excel_row_info = model_extra_fields[idx] if idx < len(model_extra_fields) else {}
                                    excel_row_id = excel_row_info.get('__excel_row_id')
                                    excel_row_number = excel_row_info.get('__excel_row_number')
                                    excel_sheet_name = excel_row_info.get('__excel_sheet_name', 'Unknown')
                                    
                                    # For JournalEntries, try to get Excel row from parent Transaction
                                    if model_name == 'JournalEntry' and not excel_row_id:
                                        transaction_id = record_data.get('transaction_id')
                                        if transaction_id and transaction_id in transaction_to_excel_row_map:
                                            tx_row_info = transaction_to_excel_row_map[transaction_id]
                                            excel_row_id = tx_row_info['excel_row_id']
                                            excel_row_number = tx_row_info['excel_row_number']
                                            excel_sheet_name = tx_row_info['excel_sheet_name']
                                    
                                    # Use a default ID if not available
                                    if not excel_row_id:
                                        excel_row_id = f"{excel_sheet_name}:{excel_row_number or (idx + 1)}"
                                    
                                    # Group by Excel row
                                    if excel_row_id not in excel_row_groups:
                                        excel_row_groups[excel_row_id] = {
                                            'excel_row_number': excel_row_number,
                                            'excel_sheet_name': excel_sheet_name,
                                            'excel_row_id': excel_row_id,
                                            'created_records': {}
                                        }
                                    
                                    if model_name not in excel_row_groups[excel_row_id]['created_records']:
                                        excel_row_groups[excel_row_id]['created_records'][model_name] = []
                                    
                                    # Deduplicate by ID to avoid adding the same record twice
                                    record_id = record_data.get('id')
                                    if record_id:
                                        # Check if this record already exists in the group
                                        existing_ids = {r.get('id') for r in excel_row_groups[excel_row_id]['created_records'][model_name] if r.get('id')}
                                        if record_id not in existing_ids:
                                            excel_row_groups[excel_row_id]['created_records'][model_name].append(record_data)
                                    else:
                                        # If no ID, just append (shouldn't happen for saved records)
                                        excel_row_groups[excel_row_id]['created_records'][model_name].append(record_data)
                                    
                                elif output.get('status') == 'error':
                                    failed_records.append({
                                        'error': output.get('message', 'Unknown error'),
                                        'data': output.get('data', {})
                                    })
                            
                            if created_records:
                                # Deduplicate records by ID to avoid showing the same record twice
                                seen_ids = set()
                                unique_records = []
                                for record in created_records:
                                    record_id = record.get('id')
                                    if record_id:
                                        if record_id not in seen_ids:
                                            seen_ids.add(record_id)
                                            unique_records.append(record)
                                    else:
                                        # If no ID, include it (shouldn't happen for saved records)
                                        unique_records.append(record)
                                
                                # Limit records based on preview_record_limit (0 = show all, None/50 = default limit)
                                if self.preview_record_limit == 0:
                                    limited_records = unique_records
                                else:
                                    limited_records = unique_records[:self.preview_record_limit]
                                
                                preview['would_create'][model_name] = {
                                    'count': len(unique_records),
                                    'records': limited_records,  # Limited records for better preview (configurable via preview_record_limit)
                                    'total': len(unique_records)
                                }
                            
                            if failed_records:
                                preview['import_errors'].extend([{
                                    'type': 'import_error',
                                    'model': model_name,
                                    'error': r.get('error', 'Unknown error'),
                                    'data': r.get('data', {})
                                } for r in failed_records[:5]])  # First 5 errors
                        
                        # JournalEntries are already processed in the main loop above (lines 2134-2192)
                        # No need to process them again here - that would cause duplicates
                        auto_created_jes = []
                        
                        # Simulate IntegrationRule triggers and capture results
                        # Skip IntegrationRules for Transactions if auto_create_journal_entries is enabled
                        # to avoid duplicate JournalEntry creation
                        if self.auto_create_journal_entries and self.auto_create_journal_entries.get('enabled', False):
                            # Filter out transaction_created events to prevent duplicate JournalEntry creation
                            preview['integration_rules_preview'] = []
                            logger.info("ETL: Skipping IntegrationRules for Transactions (auto_create_journal_entries is enabled)")
                        else:
                            preview['integration_rules_preview'] = self._simulate_integration_rules(
                                import_result, 
                                extra_fields_by_model
                            )
                        
                        # Collect all JournalEntries from IntegrationRules for both grouped and flat views
                        all_journal_entries = []
                        substitution_observations = []  # Collect substitution info for display
                        
                        for rule_preview in preview.get('integration_rules_preview', []):
                            source_record = rule_preview.get('source_record', {})
                            source_model = source_record.get('model')
                            source_id = source_record.get('id')
                            extra_fields = rule_preview.get('extra_fields', {})
                            
                            # Get Excel row info from extra_fields
                            excel_row_id = extra_fields.get('__excel_row_id')
                            if not excel_row_id:
                                excel_row_number = extra_fields.get('__excel_row_number')
                                excel_sheet_name = extra_fields.get('__excel_sheet_name', 'Unknown')
                                excel_row_id = f"{excel_sheet_name}:{excel_row_number}" if excel_row_number else None
                            
                            # Add JournalEntries to grouped view
                            if excel_row_id and excel_row_id in excel_row_groups:
                                for created_item in rule_preview.get('would_create', []):
                                    created_model = created_item.get('model')
                                    created_data = created_item.get('data', {})
                                    
                                    if created_model not in excel_row_groups[excel_row_id]['created_records']:
                                        excel_row_groups[excel_row_id]['created_records'][created_model] = []
                                    
                                    excel_row_groups[excel_row_id]['created_records'][created_model].append(created_data)
                            
                            # Also collect for flat view
                            for created_item in rule_preview.get('would_create', []):
                                created_model = created_item.get('model')
                                if created_model == 'JournalEntry':
                                    created_data = created_item.get('data', {})
                                    all_journal_entries.append(created_data)
                        
                        # JournalEntries are already in preview['would_create']['JournalEntry'] from the main loop
                        # Only add IntegrationRule-created JournalEntries if any exist (and auto_create is disabled)
                        # Since auto_created_jes is now empty (we removed duplicate processing), this should only
                        # contain IntegrationRule-created JournalEntries
                        if all_journal_entries:
                            # If JournalEntry already exists in would_create, merge the counts
                            if 'JournalEntry' in preview.get('would_create', {}):
                                existing_jes = preview['would_create']['JournalEntry'].get('records', [])
                                existing_count = preview['would_create']['JournalEntry'].get('count', 0)
                                # Deduplicate by ID to avoid showing the same JournalEntry twice
                                existing_ids = {je.get('id') for je in existing_jes if je.get('id')}
                                new_jes = [je for je in all_journal_entries if je.get('id') and je.get('id') not in existing_ids]
                                if new_jes:
                                    # Limit new records to fit within preview_record_limit
                                    if self.preview_record_limit == 0:
                                        limited_new_jes = new_jes
                                    else:
                                        remaining_slots = max(0, self.preview_record_limit - len(existing_jes))
                                        limited_new_jes = new_jes[:remaining_slots]
                                    preview['would_create']['JournalEntry']['records'].extend(limited_new_jes)
                                    preview['would_create']['JournalEntry']['count'] = existing_count + len(new_jes)
                                    preview['would_create']['JournalEntry']['total'] = existing_count + len(new_jes)
                            else:
                                # Limit records based on preview_record_limit (0 = show all, None/50 = default limit)
                                if self.preview_record_limit == 0:
                                    limited_jes = all_journal_entries
                                else:
                                    limited_jes = all_journal_entries[:self.preview_record_limit]
                                
                                preview['would_create']['JournalEntry'] = {
                                    'count': len(all_journal_entries),
                                    'records': limited_jes,  # Limited records (configurable via preview_record_limit)
                                    'total': len(all_journal_entries)
                                }
                        
                        # Collect substitution observations from all outputs
                        for import_item in import_result.get('imports', []):
                            outputs = import_item.get('result', [])
                            model_name = import_item.get('model')
                            
                            for idx, output in enumerate(outputs):
                                observations = output.get('observations', [])
                                if observations:
                                    # Get Excel row info
                                    model_extra_fields = extra_fields_by_model.get(model_name, [])
                                    excel_row_info = model_extra_fields[idx] if idx < len(model_extra_fields) else {}
                                    
                                    substitution_observations.append({
                                        'model': model_name,
                                        'row_number': excel_row_info.get('__excel_row_number', idx + 1),
                                        'sheet': excel_row_info.get('__excel_sheet_name', 'Unknown'),
                                        'observations': observations,
                                        'record_id': output.get('data', {}).get('id')
                                    })
                        
                        # Add substitutions to preview
                        if substitution_observations:
                            preview['substitutions_applied'] = substitution_observations
                        
                        # Create grouped view by Excel row (includes Transactions and JournalEntries)
                        if excel_row_groups:
                            # Sort by sheet name and row number
                            sorted_groups = sorted(
                                excel_row_groups.items(),
                                key=lambda x: (
                                    x[1].get('excel_sheet_name', ''),
                                    x[1].get('excel_row_number', 999999)
                                )
                            )
                            
                            preview['would_create_by_row'] = [
                                {
                                    'excel_sheet': group['excel_sheet_name'],
                                    'excel_row_number': group['excel_row_number'],
                                    'excel_row_id': group['excel_row_id'],
                                    'created_records': group['created_records']
                                }
                                for _, group in sorted_groups
                            ]
                    else:
                        preview['import_errors'].append({
                            'type': 'no_valid_rows',
                            'message': 'No valid rows to import after filtering null amounts and invalid fields'
                        })
                    
                finally:
                    # Always rollback - this is just a preview
                    db_transaction.savepoint_rollback(sid)
                    
        except Exception as e:
            logger.warning(f"ETL Preview: Error during full preview simulation: {e}")
            import traceback
            preview['import_errors'].append({
                'type': 'simulation_error',
                'message': str(e),
                'traceback': traceback.format_exc()
            })
        
        if self.log:
            self.log.total_rows_transformed = preview['total_rows']
            self.log.save()
        
        # Build structured output for raw JSON (legacy format, kept for backward compatibility)
        # Note: This is used by _build_v2_response_rows to extract row-level warnings/errors
        preview['structured_by_row'] = self._build_structured_output(preview, self.extra_fields_by_model)
        
        return preview
    
    def _build_structured_output(self, preview: dict, extra_fields_by_model: Dict[str, List[dict]]) -> List[dict]:
        """
        Build a structured output that shows, for each Excel row:
        - The transformed data (after substitutions)
        - Transactions that would be created
        - Journal Entries that would be created for each transaction
        - Any errors or warnings for that row
        
        Follows JSON API best practices for error handling.
        """
        structured_rows = []
        
        # Get the would_create_by_row structure
        would_create_by_row = preview.get('would_create_by_row', [])
        
        # Build a map of transaction_id -> journal_entries
        transaction_to_journal_entries = {}
        journal_entries = preview.get('would_create', {}).get('JournalEntry', {}).get('records', [])
        for je in journal_entries:
            tx_id = je.get('transaction_id')
            if tx_id:
                if tx_id not in transaction_to_journal_entries:
                    transaction_to_journal_entries[tx_id] = []
                transaction_to_journal_entries[tx_id].append(je)
        
        # Build a map of excel_row_id -> transformed data (after substitutions)
        transformed_by_row = {}
        for model_name, model_data in preview.get('transformed_data', {}).items():
            rows = model_data.get('rows', [])
            for row in rows:
                excel_row_id = row.get('__excel_row_id')
                if excel_row_id:
                    if excel_row_id not in transformed_by_row:
                        transformed_by_row[excel_row_id] = {}
                    if model_name not in transformed_by_row[excel_row_id]:
                        transformed_by_row[excel_row_id][model_name] = []
                    transformed_by_row[excel_row_id][model_name].append(row)
        
        # Build a map of excel_row_id -> substitutions applied
        substitutions_by_row = {}
        for sub in preview.get('substitutions_applied', []):
            excel_row_id = f"{sub.get('sheet', 'Unknown')}:{sub.get('row_number', 'N/A')}"
            if excel_row_id not in substitutions_by_row:
                substitutions_by_row[excel_row_id] = []
            # Parse observations to extract substitution details
            observations = sub.get('observations', [])
            for obs in observations:
                # Parse observation string like: "campo 'field_name' alterado de 'old' para 'new' (regra id=123)"
                if isinstance(obs, str):
                    import re
                    match = re.match(r"campo '([^']+)' alterado de '([^']*)' para '([^']*)' \(regra id=(\d+)\)", obs)
                    if match:
                        substitutions_by_row[excel_row_id].append({
                            'field': match.group(1),
                            'original_value': match.group(2),
                            'new_value': match.group(3),
                            'rule_id': int(match.group(4))
                        })
                    else:
                        # Fallback: include the raw observation
                        substitutions_by_row[excel_row_id].append({
                            'observation': obs
                        })
                elif isinstance(obs, dict):
                    substitutions_by_row[excel_row_id].append(obs)
        
        # Build a map of transaction_id -> excel_row_id for error mapping
        transaction_to_excel_row = {}
        for row_group in would_create_by_row:
            excel_row_id = row_group.get('excel_row_id')
            created_records = row_group.get('created_records', {})
            transactions = created_records.get('Transaction', [])
            for transaction in transactions:
                tx_id = transaction.get('id')
                if tx_id:
                    transaction_to_excel_row[tx_id] = excel_row_id
        
        # Build a map of transaction_id -> excel_row_id for error mapping
        transaction_to_excel_row_map = {}
        for row_group in would_create_by_row:
            excel_row_id = row_group.get('excel_row_id')
            created_records = row_group.get('created_records', {})
            transactions = created_records.get('Transaction', [])
            for transaction in transactions:
                tx_id = transaction.get('id')
                if tx_id:
                    transaction_to_excel_row_map[tx_id] = excel_row_id
        
        # Build a map of excel_row_id -> errors (JSON API format)
        errors_by_row = {}
        for error in preview.get('import_errors', []):
            # Try to extract row information from error
            error_data = error.get('data', {})
            excel_row_id = error_data.get('__excel_row_id')
            if not excel_row_id:
                # Try to get from extra_fields or other sources
                excel_row_id = error.get('excel_row_id') or error.get('row_id')
            
            # If still not found, try to map via transaction_id
            if not excel_row_id:
                transaction_id = error_data.get('transaction_id')
                if transaction_id:
                    excel_row_id = transaction_to_excel_row_map.get(transaction_id)
            
            if excel_row_id:
                if excel_row_id not in errors_by_row:
                    errors_by_row[excel_row_id] = []
                
                # Format error according to JSON API best practices
                error_obj = {
                    'id': f"error_{len(errors_by_row[excel_row_id])}",
                    'status': '400',  # Bad Request
                    'code': error.get('type', 'unknown_error'),
                    'title': self._get_error_title(error.get('type')),
                    'detail': error.get('message') or error.get('error', 'Unknown error'),
                    'source': {}
                }
                
                # Add source pointer if field is available
                if error.get('field'):
                    error_obj['source']['pointer'] = f"/data/attributes/{error.get('field')}"
                
                # Add meta information
                error_obj['meta'] = {
                    'model': error.get('model'),
                    'traceback': error.get('traceback') if error.get('traceback') else None
                }
                
                # Remove None values from meta
                error_obj['meta'] = {k: v for k, v in error_obj['meta'].items() if v is not None}
                
                errors_by_row[excel_row_id].append(error_obj)
        
        # Build a map of excel_row_id -> warnings (JSON API format)
        warnings_by_row = {}
        for warning in preview.get('warnings', []):
            excel_row_id = warning.get('excel_row_id') or warning.get('row_id')
            if not excel_row_id:
                # Try to extract from record_id (which is transaction_id for Transaction warnings)
                record_id = warning.get('record_id')
                if record_id:
                    # First try the transaction_to_excel_row_map we built above
                    excel_row_id = transaction_to_excel_row_map.get(record_id)
                    
                    # If still not found, search through row groups
                    if not excel_row_id:
                        for row_group in would_create_by_row:
                            created_records = row_group.get('created_records', {})
                            for model_name, records in created_records.items():
                                for record in records:
                                    if record.get('id') == record_id:
                                        excel_row_id = row_group.get('excel_row_id')
                                        break
                                if excel_row_id:
                                    break
                            if excel_row_id:
                                break
            
            if excel_row_id:
                if excel_row_id not in warnings_by_row:
                    warnings_by_row[excel_row_id] = []
                
                # Format warning according to JSON API best practices
                warning_obj = {
                    'id': f"warning_{len(warnings_by_row[excel_row_id])}",
                    'status': '200',  # OK but with warning
                    'code': warning.get('type', 'unknown_warning'),
                    'title': self._get_warning_title(warning.get('type')),
                    'detail': warning.get('message', 'Unknown warning'),
                    'meta': {
                        'model': warning.get('model'),
                        'record_id': warning.get('record_id'),
                        'account_path': warning.get('account_path')
                    }
                }
                
                # Remove None values from meta
                warning_obj['meta'] = {k: v for k, v in warning_obj['meta'].items() if v is not None}
                
                warnings_by_row[excel_row_id].append(warning_obj)
        
        # Process each row group
        for row_group in would_create_by_row:
            excel_row_id = row_group.get('excel_row_id')
            excel_row_number = row_group.get('excel_row_number')
            excel_sheet_name = row_group.get('excel_sheet', 'Unknown')
            created_records = row_group.get('created_records', {})
            
            # Get transformed data for this row (after substitutions)
            transformed_data = transformed_by_row.get(excel_row_id, {})
            
            # Get substitutions applied to this row
            substitutions = substitutions_by_row.get(excel_row_id, [])
            
            # Get transactions for this row
            transactions = created_records.get('Transaction', [])
            
            # For each transaction, get its journal entries
            transactions_with_entries = []
            for transaction in transactions:
                tx_id = transaction.get('id')
                journal_entries = transaction_to_journal_entries.get(tx_id, [])
                
                transactions_with_entries.append({
                    'transaction': transaction,
                    'journal_entries': journal_entries,
                    'journal_entry_count': len(journal_entries)
                })
            
            # Build structured row output
            structured_row = {
                'excel_row': {
                    'sheet_name': excel_sheet_name,
                    'row_number': excel_row_number,
                    'row_id': excel_row_id
                },
                'transformed_data': transformed_data,  # Data after substitutions
                'substitutions_applied': substitutions,
                'transactions': transactions_with_entries,
                'other_records': {k: v for k, v in created_records.items() if k != 'Transaction'},
                'errors': errors_by_row.get(excel_row_id, []),
                'warnings': warnings_by_row.get(excel_row_id, [])
            }
            
            structured_rows.append(structured_row)
        
        # Add rows that have errors but no created records
        for excel_row_id, errors in errors_by_row.items():
            # Check if this row is already in structured_rows
            if not any(row['excel_row']['row_id'] == excel_row_id for row in structured_rows):
                # Extract row info from transformed data or errors
                row_info = {}
                if excel_row_id in transformed_by_row:
                    # Try to get row info from transformed data
                    for model_data in transformed_by_row[excel_row_id].values():
                        if model_data:
                            first_row = model_data[0]
                            row_info = {
                                'sheet_name': first_row.get('__excel_sheet_name', 'Unknown'),
                                'row_number': first_row.get('__excel_row_number'),
                                'row_id': excel_row_id
                            }
                            break
                
                if not row_info:
                    # Fallback: parse from excel_row_id
                    if ':' in excel_row_id:
                        parts = excel_row_id.split(':', 1)
                        row_info = {
                            'sheet_name': parts[0],
                            'row_number': parts[1] if len(parts) > 1 else None,
                            'row_id': excel_row_id
                        }
                    else:
                        row_info = {
                            'sheet_name': 'Unknown',
                            'row_number': None,
                            'row_id': excel_row_id
                        }
                
                structured_rows.append({
                    'excel_row': row_info,
                    'transformed_data': transformed_by_row.get(excel_row_id, {}),
                    'substitutions_applied': substitutions_by_row.get(excel_row_id, []),
                    'transactions': [],
                    'other_records': {},
                    'errors': errors,
                    'warnings': warnings_by_row.get(excel_row_id, [])
                })
        
        return structured_rows
    
    def _get_error_title(self, error_type: str) -> str:
        """Get a human-readable title for an error type."""
        titles = {
            'validation_error': 'Validation Error',
            'import_error': 'Import Error',
            'simulation_error': 'Simulation Error',
            'fields_moved_to_extra': 'Fields Moved to Extra',
            'no_valid_rows': 'No Valid Rows',
            'unknown_error': 'Unknown Error'
        }
        return titles.get(error_type, 'Error')
    
    def _get_warning_title(self, warning_type: str) -> str:
        """Get a human-readable title for a warning type."""
        titles = {
            'no_rule': 'No Transformation Rule',
            'row_limit': 'Row Limit Applied',
            'account_not_found': 'Account Not Found',
            'auto_journal_entry_error': 'Journal Entry Creation Error',
            'unknown_warning': 'Warning'
        }
        return titles.get(warning_type, 'Warning')
    
    def _simulate_integration_rules(self, import_result: dict, extra_fields_by_model: Dict[str, List[dict]]) -> List[dict]:
        """
        Simulate IntegrationRule execution for preview.
        
        Returns a list of what each integration rule WOULD create.
        """
        from multitenancy.models import IntegrationRule
        from multitenancy.formula_engine import execute_rule
        from django.db import transaction as db_transaction
        
        results = []
        
        MODEL_EVENT_MAP = {
            'Transaction': 'transaction_created',
            'JournalEntry': 'journal_entry_created',
        }
        
        # execute_import_job returns {'imports': [{'model': '...', 'result': [...]}]}
        for import_item in import_result.get('imports', []):
            model_name = import_item.get('model')
            outputs = import_item.get('result', [])
            
            event_name = MODEL_EVENT_MAP.get(model_name)
            if not event_name:
                continue
            
            # Get the transformation rule to check trigger options
            rule = self.transformation_rules.get(model_name)
            trigger_options = (rule.trigger_options or {}) if rule else {}
            
            if not trigger_options.get('enabled', True):
                continue
            
            allowed_events = trigger_options.get('events', [event_name])
            if event_name not in allowed_events:
                continue
            
            # Skip IntegrationRules for transaction_created if auto_create_journal_entries is enabled
            # to avoid duplicate JournalEntry creation
            if event_name == 'transaction_created' and self.auto_create_journal_entries:
                auto_config = self.auto_create_journal_entries or {}
                if auto_config.get('enabled', False):
                    logger.debug(f"ETL: Skipping IntegrationRules for {event_name} (auto_create_journal_entries is enabled)")
                    continue
            
            extra_fields_list = extra_fields_by_model.get(model_name, [])
            
            # Find IntegrationRules for this event
            integration_rules = IntegrationRule.objects.filter(
                company_id=self.company_id,
                trigger_event=event_name,
                is_active=True
            ).order_by('execution_order')
            
            if not integration_rules.exists():
                continue
            
            for idx, output in enumerate(outputs):
                if output.get('status') != 'success' or output.get('action') != 'create':
                    continue
                
                record_data = output.get('data', {})
                record_id = record_data.get('id')
                extra_fields = extra_fields_list[idx] if idx < len(extra_fields_list) else {}
                
                # Build payload
                payload = {
                    f'{model_name.lower()}_id': record_id,
                    model_name.lower(): record_data,
                    'extra_fields': extra_fields,
                    'source': 'etl_preview',
                }
                
                # Execute each integration rule
                for int_rule in integration_rules:
                    rule_result = {
                        'rule_name': int_rule.name,
                        'rule_id': int_rule.id,
                        'trigger_event': event_name,
                        'source_record': {
                            'model': model_name,
                            'id': record_id,
                            'data': record_data
                        },
                        'extra_fields': extra_fields,
                        'would_create': [],
                        'errors': [],
                    }
                    
                    try:
                        # Run the rule in a nested savepoint
                        sid = db_transaction.savepoint()
                        try:
                            result = execute_rule(self.company_id, int_rule.rule, [payload])
                            
                            # Capture what would be created by checking the database
                            # Look for JournalEntries created for this transaction
                            if model_name == 'Transaction' and record_id:
                                from accounting.models import JournalEntry
                                created_jes = JournalEntry.objects.filter(
                                    transaction_id=record_id
                                ).values('id', 'account_id', 'account__name', 'debit_amount', 'credit_amount', 'description')
                                
                                for je in created_jes:
                                    rule_result['would_create'].append({
                                        'model': 'JournalEntry',
                                        'data': {
                                            'account_id': je['account_id'],
                                            'account_name': je['account__name'],
                                            'debit_amount': str(je['debit_amount']) if je['debit_amount'] else None,
                                            'credit_amount': str(je['credit_amount']) if je['credit_amount'] else None,
                                            'description': je['description'],
                                        }
                                    })
                            
                            rule_result['rule_output'] = result
                            
                        finally:
                            # Rollback this rule's changes
                            db_transaction.savepoint_rollback(sid)
                            
                    except Exception as e:
                        rule_result['errors'].append(str(e))
                    
                    results.append(rule_result)
        
        return results
    
    def _evaluate_expression(self, expression: str, context: dict, expr_type: str) -> Any:
        """Safely evaluate a Python expression."""
        # Build safe context
        safe_context = dict(self.SAFE_BUILTINS)
        
        if expr_type == 'row_filter':
            safe_context['row'] = context
        elif expr_type == 'computed':
            safe_context['row'] = context.get('row', {})
            safe_context['transformed'] = context.get('transformed', {})
        else:
            safe_context.update(context)
        
        try:
            return eval(expression, {"__builtins__": {}}, safe_context)
        except Exception as e:
            raise ValueError(f"Expression error: {str(e)}")
    
    def _suggest_column_matches(self, missing: List[str], available: List[str]) -> dict:
        """Suggest possible column matches for missing columns."""
        suggestions = {}
        available_lower = {str(c).lower(): c for c in available}
        
        for col in missing:
            col_lower = str(col).lower()
            # Simple substring matching
            matches = []
            for avail_lower, avail in available_lower.items():
                if col_lower in avail_lower or avail_lower in col_lower:
                    matches.append(avail)
                # Check word overlap
                col_words = set(col_lower.replace('_', ' ').replace('-', ' ').split())
                avail_words = set(avail_lower.replace('_', ' ').replace('-', ' ').split())
                if col_words & avail_words:
                    if avail not in matches:
                        matches.append(avail)
            
            if matches:
                suggestions[col] = matches[:3]  # Top 3 suggestions
        
        return suggestions
    
    def _add_error(self, error_type: str, message: str, stage: str, **kwargs):
        """Add an error to the error list."""
        error = {
            'type': error_type,
            'message': message,
            'stage': stage,
            'timestamp': timezone.now().isoformat(),
            **kwargs
        }
        self.errors.append(error)
        
        # Categorize errors
        if error_type in ('substitution_not_found', 'account_not_found', 'fk_substitution_failed'):
            self.substitution_errors.append(error)
        elif error_type in ('database_error', 'integrity_error', 'constraint_error'):
            self.database_errors.append(error)
        elif error_type in ('exception', 'python_error', 'type_error', 'value_error'):
            self.python_errors.append(error)
        
        logger.error(f"ETL Error [{stage}]: {message}")
    
    def _add_warning(self, warning_type: str, message: str, **kwargs):
        """Add a warning to the warnings list."""
        warning = {
            'type': warning_type,
            'message': message,
            **kwargs
        }
        self.warnings.append(warning)
        logger.warning(f"ETL Warning: {message}")
    
    def _build_v2_response_rows(self, import_result: dict, extra_fields_by_model: Dict[str, List[dict]]) -> List[dict]:
        """
        Build the canonical data.rows structure for v2 response format.
        
        Each row groups all relevant information: Excel metadata, transformed data,
        transformation metadata, created records, warnings, and errors.
        """
        rows = []
        
        # Get existing structures
        would_create_by_row = import_result.get('would_create_by_row', [])
        transformed_data = import_result.get('transformed_data', {})
        would_fail = import_result.get('would_fail', {})
        
        # Build maps for efficient lookup
        # Map: excel_row_id -> transformed data
        transformed_by_row = {}
        for model_name, model_data in transformed_data.items():
            model_rows = model_data.get('rows', [])
            for row in model_rows:
                excel_row_id = row.get('__excel_row_id')
                if excel_row_id:
                    if excel_row_id not in transformed_by_row:
                        transformed_by_row[excel_row_id] = {}
                    if model_name not in transformed_by_row[excel_row_id]:
                        transformed_by_row[excel_row_id][model_name] = []
                    # Remove internal metadata from transformed row
                    clean_row = {k: v for k, v in row.items() if not k.startswith('__')}
                    transformed_by_row[excel_row_id][model_name].append(clean_row)
        
        # Map: excel_row_id -> source row data (if available)
        source_rows_by_id = {}
        # Try to get source rows from transformed data
        for model_name, model_data in transformed_data.items():
            model_rows = model_data.get('rows', [])
            for row in model_rows:
                excel_row_id = row.get('__excel_row_id')
                if excel_row_id and '__source_row__' in row:
                    source_rows_by_id[excel_row_id] = row['__source_row__']
        
        # Map: excel_row_id -> rule applied
        rule_by_row = {}
        for model_name, rule in self.transformation_rules.items():
            # We need to map rows to rules - for now, use model_name match
            for excel_row_id in transformed_by_row.keys():
                if model_name in transformed_by_row.get(excel_row_id, {}):
                    rule_by_row[excel_row_id] = {
                        'id': rule.id,
                        'name': rule.name
                    }
        
        # Map: excel_row_id -> substitutions applied
        substitutions_by_row = {}
        for sub in import_result.get('substitutions_applied', []):
            excel_row_id = f"{sub.get('sheet', 'Unknown')}:{sub.get('row_number', 'N/A')}"
            if excel_row_id not in substitutions_by_row:
                substitutions_by_row[excel_row_id] = []
            
            observations = sub.get('observations', [])
            for obs in observations:
                if isinstance(obs, str):
                    import re
                    match = re.match(r"campo '([^']+)' alterado de '([^']*)' para '([^']*)' \(regra id=(\d+)\)", obs)
                    if match:
                        substitutions_by_row[excel_row_id].append({
                            'field': match.group(1),
                            'from': match.group(2),
                            'to': match.group(3),
                            'rule_id': int(match.group(4))
                        })
                elif isinstance(obs, dict):
                    substitutions_by_row[excel_row_id].append(obs)
        
        # Map: excel_row_id -> extra fields
        extra_fields_by_row = {}
        for model_name, extra_fields_list in extra_fields_by_model.items():
            for idx, extra_fields in enumerate(extra_fields_list):
                excel_row_id = extra_fields.get('__excel_row_id')
                if excel_row_id:
                    # Get extra fields (excluding internal metadata)
                    clean_extra = {k: v for k, v in extra_fields.items() if not k.startswith('__')}
                    if clean_extra:
                        if excel_row_id not in extra_fields_by_row:
                            extra_fields_by_row[excel_row_id] = []
                        extra_fields_by_row[excel_row_id].extend(list(clean_extra.keys()))
        
        # Map: excel_row_id -> errors and warnings
        # Extract from structured_by_row if available (from preview), otherwise build from import_errors
        errors_by_row = {}
        warnings_by_row = {}
        
        structured_by_row = import_result.get('structured_by_row', [])
        if structured_by_row:
            for structured_row in structured_by_row:
                excel_row_id = structured_row.get('excel_row', {}).get('row_id')
                if excel_row_id:
                    errors_by_row[excel_row_id] = structured_row.get('errors', [])
                    warnings_by_row[excel_row_id] = structured_row.get('warnings', [])
        else:
            # Fallback: try to extract from import_errors and warnings
            # This is a simplified extraction - full mapping would require transaction_id -> row mapping
            pass  # For now, leave empty - can be enhanced later if needed
        
        # Process successful rows (with created records)
        for row_group in would_create_by_row:
            excel_row_id = row_group.get('excel_row_id')
            excel_sheet = row_group.get('excel_sheet', 'Unknown')
            excel_row_number = row_group.get('excel_row_number')
            created_records = row_group.get('created_records', {})
            
            # Build transactions list
            transactions_list = []
            transactions = created_records.get('Transaction', [])
            
            # Map transaction_id -> journal_entries
            journal_entries_by_tx = {}
            journal_entries = created_records.get('JournalEntry', [])
            for je in journal_entries:
                tx_id = je.get('transaction_id')
                if tx_id:
                    if tx_id not in journal_entries_by_tx:
                        journal_entries_by_tx[tx_id] = []
                    journal_entries_by_tx[tx_id].append(je)
            
            for transaction in transactions:
                tx_id = transaction.get('id')
                transactions_list.append({
                    'transaction': transaction,
                    'journal_entries': journal_entries_by_tx.get(tx_id, []),
                    'journal_entry_count': len(journal_entries_by_tx.get(tx_id, []))
                })
            
            # Build other_records (non-Transaction records)
            other_records = {k: v for k, v in created_records.items() if k not in ['Transaction', 'JournalEntry']}
            # Add JournalEntries not linked to transactions
            unlinked_jes = [je for je in journal_entries if not je.get('transaction_id')]
            if unlinked_jes:
                other_records.setdefault('JournalEntry', []).extend(unlinked_jes)
            
            # Determine status
            status = 'ok' if transactions_list or other_records else 'failed'
            
            # Get rule info
            rule_info = rule_by_row.get(excel_row_id, {})
            
            # Build row result
            row_result = {
                'excel_row': {
                    'sheet_name': excel_sheet,
                    'row_number': excel_row_number,
                    'row_id': excel_row_id
                },
                'status': status,
                'source_row': source_rows_by_id.get(excel_row_id),
                'transformed': transformed_by_row.get(excel_row_id, {}),
                'transformation': {
                    'rule_id': rule_info.get('id'),
                    'rule_name': rule_info.get('name'),
                    'substitutions_applied': substitutions_by_row.get(excel_row_id, []),
                    'extra_fields': list(set(extra_fields_by_row.get(excel_row_id, [])))
                },
                'transactions': transactions_list,
                'other_records': other_records,
                'warnings': warnings_by_row.get(excel_row_id, []),
                'errors': errors_by_row.get(excel_row_id, [])
            }
            
            rows.append(row_result)
        
        # Process failed rows
        for model_name, failed_data in would_fail.items():
            failed_rows = failed_data.get('rows', [])
            for failed_row in failed_rows:
                excel_row_id = failed_row.get('excel_row_id')
                if not excel_row_id:
                    excel_sheet = failed_row.get('excel_sheet', 'Unknown')
                    excel_row_number = failed_row.get('row_number')
                    excel_row_id = f"{excel_sheet}:{excel_row_number}" if excel_row_number else None
                
                # Skip if already processed
                if excel_row_id and any(r['excel_row']['row_id'] == excel_row_id for r in rows):
                    continue
                
                # Build error
                error = {
                    'code': 'VALIDATION_ERROR',
                    'message': failed_row.get('reason', 'Validation failed'),
                    'field': failed_row.get('field')
                }
                
                row_result = {
                    'excel_row': {
                        'sheet_name': failed_row.get('excel_sheet', 'Unknown'),
                        'row_number': failed_row.get('row_number'),
                        'row_id': excel_row_id or f"{failed_row.get('excel_sheet', 'Unknown')}:{failed_row.get('row_number', 'N/A')}"
                    },
                    'status': 'failed',
                    'source_row': failed_row.get('data'),
                    'transformed': transformed_by_row.get(excel_row_id, {}),
                    'transformation': {
                        'rule_id': None,
                        'rule_name': None,
                        'substitutions_applied': [],
                        'extra_fields': []
                    },
                    'transactions': [],
                    'other_records': {},
                    'warnings': [],
                    'errors': [error]
                }
                
                rows.append(row_result)
        
        # Sort rows by sheet name and row number
        def sort_key(row):
            excel_row = row['excel_row']
            return (excel_row.get('sheet_name', ''), excel_row.get('row_number', 999999))
        
        rows.sort(key=sort_key)
        
        return rows
    
    def _build_v2_summary(self, rows: List[dict]) -> dict:
        """
        Build the v2 summary from rows data.
        
        Computes:
        - total_rows_transformed from rows count
        - rows.ok/failed/skipped counts
        - models.created/failed counts
        """
        summary = {
            'sheets_found': len(self.sheets_found),
            'sheets_processed': len(self.sheets_processed),
            'sheets_skipped': len(self.sheets_skipped),
            'sheets_failed': len(self.sheets_failed),
            'total_rows_transformed': len(rows),
            'rows': {
                'ok': 0,
                'failed': 0,
                'skipped': 0
            },
            'models': {}
        }
        
        # Count rows by status
        for row in rows:
            status = row.get('status', 'unknown')
            if status == 'ok':
                summary['rows']['ok'] += 1
            elif status == 'failed':
                summary['rows']['failed'] += 1
            elif status in ['skipped', 'ignored']:
                summary['rows']['skipped'] += 1
        
        # Count models
        transaction_count = 0
        journal_entry_count = 0
        
        for row in rows:
            transactions = row.get('transactions', [])
            transaction_count += len(transactions)
            
            for tx_bundle in transactions:
                journal_entry_count += len(tx_bundle.get('journal_entries', []))
            
            # Count other JournalEntries
            other_jes = row.get('other_records', {}).get('JournalEntry', [])
            journal_entry_count += len(other_jes)
        
        summary['models'] = {
            'Transaction': {
                'created': transaction_count,
                'failed': 0  # TODO: track failures per model if needed
            },
            'JournalEntry': {
                'created': journal_entry_count,
                'failed': 0
            }
        }
        
        return summary
    
    def _build_v2_data(self, import_result: dict, extra_fields_by_model: Dict[str, List[dict]]) -> dict:
        """
        Build the v2 data structure with rows and transformations.
        """
        # Build rows
        rows = self._build_v2_response_rows(import_result, extra_fields_by_model)
        
        # Build transformations block
        transformations = {
            'rules_used': import_result.get('transformation_rules_used', []),
            'import_errors': import_result.get('import_errors', []),
            'integration_rules_available': import_result.get('integration_rules_available', []),
            'integration_rules_preview': import_result.get('integration_rules_preview', [])
        }
        
        result = {
            'rows': rows,
            'transformations': transformations
        }
        
        # Add 'created' structure for execute mode (actual created records)
        if 'created' in import_result:
            result['created'] = import_result['created']
        
        return result
    
    def _build_response(self, start_time: float, success: bool, import_result: dict = None) -> dict:
        """
        Build the final response in v2 format.
        
        v2 Format:
        - schema_version: "2.0"
        - Single canonical data block (no import_result duplication)
        - data.rows: per-row canonical structure
        - data.transformations: global transformation metadata
        - summary computed from data.rows
        """
        duration = time.monotonic() - start_time
        
        if self.log:
            self.log.duration_seconds = duration
            self.log.total_rows_input = sum(len(rows) for rows in self.transformed_data.values())
            self.log.save()
        
        # Build base response
        response = {
            'success': success,
            'log_id': self.log.id if self.log else None,
            'file_name': self.file_name,
            'file_hash': self.file_hash,
            'is_preview': not self.commit,
            'duration_seconds': round(duration, 2),
            'schema_version': '2.0',
            
            'sheets': {
                'found': self.sheets_found,
                'processed': self.sheets_processed,
                'skipped': self.sheets_skipped,
                'failed': self.sheets_failed,
            },
            
            'errors': self.errors,
            'warnings': self.warnings,
        }
        
        # Build v2 data structure if we have import_result
        if import_result:
            # Build data.rows and data.transformations
            data = self._build_v2_data(import_result, self.extra_fields_by_model)
            response['data'] = data
            
            # Build summary from rows
            summary = self._build_v2_summary(data['rows'])
            response['summary'] = summary
        else:
            # No import result - build minimal summary
            response['summary'] = {
                'sheets_found': len(self.sheets_found),
                'sheets_processed': len(self.sheets_processed),
                'sheets_skipped': len(self.sheets_skipped),
                'sheets_failed': len(self.sheets_failed),
                'total_rows_transformed': 0,
                'rows': {
                    'ok': 0,
                    'failed': 0,
                    'skipped': 0
                },
                'models': {}
            }
            response['data'] = {
                'rows': [],
                'transformations': {
                    'rules_used': [],
                    'import_errors': [],
                    'integration_rules_available': [],
                    'integration_rules_preview': []
                }
            }
        
        return response
    
    def generate_error_report(self) -> str:
        """
        Generate a comprehensive error report as a text file.
        Includes all errors, warnings, substitution errors, database errors, and Python exceptions.
        """
        from io import StringIO
        
        report = StringIO()
        report.write("=" * 80 + "\n")
        report.write("ETL PIPELINE ERROR REPORT\n")
        report.write("=" * 80 + "\n\n")
        
        # File information
        report.write(f"File: {self.file_name}\n")
        report.write(f"Company ID: {self.company_id}\n")
        if self.log:
            report.write(f"Log ID: {self.log.id}\n")
            report.write(f"Status: {self.log.status}\n")
            report.write(f"Started: {self.log.created_at}\n")
            if self.log.completed_at:
                report.write(f"Completed: {self.log.completed_at}\n")
                if self.log.duration_seconds:
                    report.write(f"Duration: {self.log.duration_seconds:.2f} seconds\n")
        report.write("\n")
        
        # Summary
        report.write("=" * 80 + "\n")
        report.write("SUMMARY\n")
        report.write("=" * 80 + "\n")
        report.write(f"Total Errors: {len(self.errors)}\n")
        report.write(f"  - Python/Exception Errors: {len(self.python_errors)}\n")
        report.write(f"  - Database Errors: {len(self.database_errors)}\n")
        report.write(f"  - Substitution Errors: {len(self.substitution_errors)}\n")
        report.write(f"Total Warnings: {len(self.warnings)}\n")
        report.write(f"Sheets Found: {len(self.sheets_found)}\n")
        report.write(f"Sheets Processed: {len(self.sheets_processed)}\n")
        report.write(f"Sheets Skipped: {len(self.sheets_skipped)}\n")
        report.write(f"Sheets Failed: {len(self.sheets_failed)}\n")
        report.write("\n")
        
        # Python/Exception Errors
        if self.python_errors:
            report.write("=" * 80 + "\n")
            report.write("PYTHON/EXCEPTION ERRORS\n")
            report.write("=" * 80 + "\n")
            for idx, error in enumerate(self.python_errors, 1):
                report.write(f"\n[{idx}] {error.get('exception_type', 'Exception')}\n")
                report.write(f"Stage: {error.get('stage', 'unknown')}\n")
                report.write(f"Message: {error.get('message', 'No message')}\n")
                if error.get('model'):
                    report.write(f"Model: {error.get('model')}\n")
                if error.get('record_id'):
                    report.write(f"Record ID: {error.get('record_id')}\n")
                if error.get('traceback'):
                    report.write(f"Traceback:\n{error.get('traceback')}\n")
                report.write(f"Timestamp: {error.get('timestamp', 'N/A')}\n")
                report.write("-" * 80 + "\n")
            report.write("\n")
        
        # Database Errors
        if self.database_errors:
            report.write("=" * 80 + "\n")
            report.write("DATABASE ERRORS\n")
            report.write("=" * 80 + "\n")
            for idx, error in enumerate(self.database_errors, 1):
                report.write(f"\n[{idx}] {error.get('type', 'database_error')}\n")
                report.write(f"Stage: {error.get('stage', 'unknown')}\n")
                report.write(f"Message: {error.get('message', 'No message')}\n")
                if error.get('model'):
                    report.write(f"Model: {error.get('model')}\n")
                if error.get('record_id'):
                    report.write(f"Record ID: {error.get('record_id')}\n")
                report.write(f"Timestamp: {error.get('timestamp', 'N/A')}\n")
                report.write("-" * 80 + "\n")
            report.write("\n")
        
        # Substitution Errors
        if self.substitution_errors:
            report.write("=" * 80 + "\n")
            report.write("SUBSTITUTION ERRORS (Not Found)\n")
            report.write("=" * 80 + "\n")
            for idx, error in enumerate(self.substitution_errors, 1):
                report.write(f"\n[{idx}] {error.get('type', 'substitution_error')}\n")
                report.write(f"Stage: {error.get('stage', 'unknown')}\n")
                report.write(f"Message: {error.get('message', 'No message')}\n")
                if error.get('field'):
                    report.write(f"Field: {error.get('field')}\n")
                if error.get('value'):
                    report.write(f"Value: {error.get('value')}\n")
                if error.get('account_path'):
                    report.write(f"Account Path: {error.get('account_path')}\n")
                if error.get('model'):
                    report.write(f"Model: {error.get('model')}\n")
                if error.get('record_id'):
                    report.write(f"Record ID: {error.get('record_id')}\n")
                report.write(f"Timestamp: {error.get('timestamp', 'N/A')}\n")
                report.write("-" * 80 + "\n")
            report.write("\n")
        
        # All Other Errors
        other_errors = [e for e in self.errors if e not in self.python_errors and e not in self.database_errors and e not in self.substitution_errors]
        if other_errors:
            report.write("=" * 80 + "\n")
            report.write("OTHER ERRORS\n")
            report.write("=" * 80 + "\n")
            for idx, error in enumerate(other_errors, 1):
                report.write(f"\n[{idx}] {error.get('type', 'error')}\n")
                report.write(f"Stage: {error.get('stage', 'unknown')}\n")
                report.write(f"Message: {error.get('message', 'No message')}\n")
                for key, value in error.items():
                    if key not in ('type', 'stage', 'message', 'timestamp'):
                        report.write(f"{key}: {value}\n")
                report.write(f"Timestamp: {error.get('timestamp', 'N/A')}\n")
                report.write("-" * 80 + "\n")
            report.write("\n")
        
        # Warnings
        if self.warnings:
            report.write("=" * 80 + "\n")
            report.write("WARNINGS\n")
            report.write("=" * 80 + "\n")
            for idx, warning in enumerate(self.warnings, 1):
                report.write(f"\n[{idx}] {warning.get('type', 'warning')}\n")
                report.write(f"Message: {warning.get('message', 'No message')}\n")
                for key, value in warning.items():
                    if key not in ('type', 'message'):
                        report.write(f"{key}: {value}\n")
                report.write("-" * 80 + "\n")
            report.write("\n")
        
        # Sheets Information
        if self.sheets_found:
            report.write("=" * 80 + "\n")
            report.write("SHEETS INFORMATION\n")
            report.write("=" * 80 + "\n")
            report.write(f"Found: {', '.join(self.sheets_found)}\n")
            if self.sheets_processed:
                report.write(f"Processed: {', '.join(self.sheets_processed)}\n")
            if self.sheets_skipped:
                report.write(f"Skipped: {', '.join(self.sheets_skipped)}\n")
            if self.sheets_failed:
                report.write(f"Failed: {', '.join(self.sheets_failed)}\n")
            report.write("\n")
        
        report.write("=" * 80 + "\n")
        report.write("END OF REPORT\n")
        report.write("=" * 80 + "\n")
        
        return report.getvalue()


