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
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from django.apps import apps
from django.db import transaction
from django.utils import timezone

from .models import ImportTransformationRule, ETLPipelineLog, SubstitutionRule
from .tasks import execute_import_job, MODEL_APP_MAP

logger = logging.getLogger(__name__)


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
    
    def __init__(self, company_id: int, file, commit: bool = False):
        self.company_id = company_id
        self.file = file
        self.commit = commit
        
        # State
        self.log: Optional[ETLPipelineLog] = None
        self.errors: List[dict] = []
        self.warnings: List[dict] = []
        self.file_hash: Optional[str] = None
        self.file_name: str = getattr(file, 'name', 'unknown')
        
        # Results
        self.sheets_found: List[str] = []
        self.sheets_processed: List[str] = []
        self.sheets_skipped: List[str] = []
        self.sheets_failed: List[str] = []
        self.transformed_data: Dict[str, List[dict]] = {}  # model_name -> rows
        self.transformation_rules: Dict[str, ImportTransformationRule] = {}  # model_name -> rule
        
    def execute(self) -> dict:
        """Main entry point - runs the full pipeline."""
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
            
            # 4. Post-process (e.g., JournalEntry debit/credit calculation)
            self._post_process_data()
            
            # 5. Validate
            self._update_log_status('validating')
            self._validate_data()
            
            # 6. Import or Preview
            if self.commit and self.transformed_data:
                self._update_log_status('importing')
                result = self._import_data()
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
            logger.exception("ETL Pipeline failed")
            self._add_error(
                error_type='exception',
                message=str(e),
                stage='pipeline'
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
    
    def _update_log_status(self, status: str):
        """Update log status."""
        if self.log:
            self.log.status = status
            self.log.sheets_found = self.sheets_found
            self.log.sheets_processed = self.sheets_processed
            self.log.sheets_skipped = self.sheets_skipped
            self.log.sheets_failed = self.sheets_failed
            self.log.warnings = self.warnings
            self.log.errors = self.errors
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
        
        try:
            # Apply skip_rows
            if rule.skip_rows > 0:
                df = df.iloc[rule.skip_rows:].reset_index(drop=True)
            
            # Handle header_row
            if rule.header_row > 0:
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
            
            # Build case-insensitive column lookup
            available_columns = {str(col).lower().strip(): str(col) for col in df.columns}
            available_columns_list = list(df.columns)
            
            # Validate required columns from column_mappings
            missing_columns = []
            column_map = {}  # normalized_target -> actual_source
            
            for source_col, target_field in (rule.column_mappings or {}).items():
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
            
            for idx, row in df.iterrows():
                row_dict = row.to_dict()
                row_number = idx + rule.skip_rows + rule.header_row + 2  # Excel row number (1-indexed + header)
                
                try:
                    # Apply row filter
                    if rule.row_filter:
                        if not self._evaluate_expression(rule.row_filter, row_dict, 'row_filter'):
                            filtered_count += 1
                            continue
                    
                    # Build transformed row
                    transformed = {}
                    
                    # 1. Apply column mappings
                    for target_field, source_col in column_map.items():
                        value = row_dict.get(source_col)
                        # Clean NaN values
                        if pd.isna(value):
                            value = None
                        transformed[target_field] = value
                    
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
                    for target_field, source_col in (rule.extra_fields_for_trigger or {}).items():
                        source_lower = str(source_col).lower().strip()
                        actual_col = available_columns.get(source_lower, source_col)
                        value = row_dict.get(actual_col)
                        if pd.isna(value):
                            value = None
                        extra_fields[target_field] = value
                    
                    # Store extra_fields in a special key (will be removed before import)
                    if extra_fields:
                        transformed['__extra_fields__'] = extra_fields
                    
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
                    total_rows=total_rows
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
        for model_name, rows in self.transformed_data.items():
            # Get all substitution rules for this model
            rules = SubstitutionRule.objects.filter(
                company_id=self.company_id,
                model_name__iexact=model_name
            )
            
            if not rules.exists():
                continue
            
            logger.info(f"ETL: Applying {rules.count()} substitution rules to {len(rows)} rows of {model_name}")
            
            for rule in rules:
                field_name = rule.field_name
                
                for row in rows:
                    if field_name not in row:
                        continue
                    
                    original_value = row[field_name]
                    if original_value is None:
                        continue
                    
                    try:
                        new_value = self._apply_substitution_rule(rule, original_value)
                        if new_value != original_value:
                            row[field_name] = new_value
                    except Exception as e:
                        self._add_warning(
                            warning_type='substitution_error',
                            message=f"Error applying substitution rule '{rule}': {str(e)}",
                            model=model_name,
                            field=field_name,
                            value=str(original_value)[:100]
                        )
    
    def _apply_substitution_rule(self, rule: SubstitutionRule, value: Any) -> Any:
        """Apply a single substitution rule to a value."""
        str_value = str(value)
        
        if rule.match_type == 'exact':
            if str_value == rule.match_value:
                return rule.substitution_value
        elif rule.match_type == 'regex':
            return re.sub(rule.match_value, rule.substitution_value, str_value)
        elif rule.match_type == 'caseless':
            # Case and accent insensitive
            import unicodedata
            def normalize(s):
                return unicodedata.normalize('NFD', s.lower()).encode('ascii', 'ignore').decode('utf-8')
            if normalize(str_value) == normalize(rule.match_value):
                return rule.substitution_value
        
        return value
    
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
        Look up an Account by various methods.
        
        Args:
            value: The lookup value
            lookup_type: One of 'path', 'code', 'id', 'name'
            path_separator: Separator for path-based lookup
            
        Returns:
            Account instance or None
        """
        from accounting.models import Account
        
        if not value:
            return None
        
        try:
            if lookup_type == 'id':
                return Account.objects.filter(
                    company_id=self.company_id,
                    id=int(value)
                ).first()
            
            elif lookup_type == 'code':
                return Account.objects.filter(
                    company_id=self.company_id,
                    account_code__iexact=str(value).strip()
                ).first()
            
            elif lookup_type == 'name':
                # Simple name lookup (may return first match if duplicates exist)
                return Account.objects.filter(
                    company_id=self.company_id,
                    name__iexact=str(value).strip()
                ).first()
            
            elif lookup_type == 'path':
                # Parse path and traverse the tree
                path_str = str(value).strip()
                path_parts = [p.strip() for p in path_str.split(path_separator) if p.strip()]
                
                if not path_parts:
                    return None
                
                # Traverse the account tree
                parent = None
                account = None
                
                for part_name in path_parts:
                    account = Account.objects.filter(
                        company_id=self.company_id,
                        name__iexact=part_name,
                        parent=parent
                    ).first()
                    
                    if not account:
                        # Try without parent constraint for more flexibility
                        # (in case path has gaps or different structure)
                        logger.debug(f"Account not found with parent constraint: {part_name}, trying without parent")
                        return None
                    
                    parent = account
                
                return account
            
            else:
                logger.warning(f"Unknown account lookup type: {lookup_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error looking up account: {e}")
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
                row_number = idx + 1
                for field in required_fields:
                    # Check both field name and field_id variant
                    field_id = f"{field}_id" if not field.endswith('_id') else field
                    field_fk = f"{field}_fk"
                    
                    if (field not in row or row[field] is None) and \
                       (field_id not in row or row[field_id] is None) and \
                       (field_fk not in row or row[field_fk] is None):
                        self._add_warning(
                            warning_type='missing_required_field',
                            message=f"Row {row_number} in {model_name} is missing required field '{field}'",
                            model=model_name,
                            row_number=row_number,
                            field=field
                        )
    
    def _import_data(self) -> dict:
        """Import transformed data using existing bulk import logic."""
        # Extract __extra_fields__ from rows before import (they're not model fields)
        extra_fields_by_model: Dict[str, List[dict]] = {}
        
        for model_name, rows in self.transformed_data.items():
            extra_fields_by_model[model_name] = []
            for row in rows:
                extra_fields = row.pop('__extra_fields__', {})
                extra_fields_by_model[model_name].append(extra_fields)
        
        # Convert to sheets format expected by execute_import_job
        sheets = []
        for model_name, rows in self.transformed_data.items():
            sheets.append({
                'model': model_name,
                'rows': rows
            })
        
        if not sheets:
            return {'message': 'No data to import'}
        
        # Use existing import logic
        result = execute_import_job(
            company_id=self.company_id,
            sheets=sheets,
            commit=True
        )
        
        # Update log with import stats
        records_created = {}
        if self.log:
            for model_name, outputs in result.get('results', {}).items():
                created_count = sum(1 for o in outputs if o.get('status') == 'success' and o.get('action') == 'create')
                if created_count > 0:
                    records_created[model_name] = created_count
            
            self.log.records_created = records_created
            self.log.total_rows_imported = sum(records_created.values())
            self.log.save()
        
        # Trigger IntegrationRule events for created records
        self._trigger_events_for_created_records(result, extra_fields_by_model)
        
        return result
    
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
            'total_rows': 0,
        }
        
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
        try:
            with db_transaction.atomic():
                # Create a savepoint we can rollback to
                sid = db_transaction.savepoint()
                
                try:
                    # Extract extra_fields and filter invalid model fields before import
                    extra_fields_by_model: Dict[str, List[dict]] = {}
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
                    
                    # Filter out rows with null required fields (amount)
                    valid_rows_by_model: Dict[str, List[dict]] = {}
                    failed_rows_by_model: Dict[str, List[dict]] = {}
                    
                    for model_name, rows in cleaned_data.items():
                        valid_rows_by_model[model_name] = []
                        failed_rows_by_model[model_name] = []
                        valid_extra_fields = []
                        
                        for idx, row in enumerate(rows):
                            # Check for null amount (required field for Transaction)
                            if model_name == 'Transaction' and (row.get('amount') is None):
                                failed_rows_by_model[model_name].append({
                                    'row_number': idx + 1,
                                    'reason': 'amount is null/missing',
                                    'data': row
                                })
                            else:
                                valid_rows_by_model[model_name].append(row)
                                valid_extra_fields.append(extra_fields_by_model[model_name][idx])
                        
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
                        import_result = execute_import_job(
                            company_id=self.company_id,
                            sheets=sheets,
                            commit=True  # Commit within this transaction (will be rolled back)
                        )
                        
                        # Capture what would be created
                        for model_name, outputs in import_result.get('results', {}).items():
                            created_records = []
                            failed_records = []
                            
                            for output in outputs:
                                if output.get('status') == 'success' and output.get('action') == 'create':
                                    created_records.append(output.get('data', {}))
                                elif output.get('status') == 'error':
                                    failed_records.append({
                                        'error': output.get('error'),
                                        'data': output.get('data', {})
                                    })
                            
                            if created_records:
                                preview['would_create'][model_name] = {
                                    'count': len(created_records),
                                    'records': created_records[:20],  # First 20 records
                                    'total': len(created_records)
                                }
                            
                            if failed_records:
                                preview['import_errors'].extend([{
                                    'type': 'import_error',
                                    'model': model_name,
                                    'error': r['error'],
                                    'data': r['data']
                                } for r in failed_records[:5]])  # First 5 errors
                        
                        # Simulate IntegrationRule triggers and capture results
                        preview['integration_rules_preview'] = self._simulate_integration_rules(
                            import_result, 
                            extra_fields_by_model
                        )
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
        
        return preview
    
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
        
        for model_name, outputs in import_result.get('results', {}).items():
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
            **kwargs
        }
        self.errors.append(error)
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
    
    def _build_response(self, start_time: float, success: bool, import_result: dict = None) -> dict:
        """Build the final response."""
        duration = time.monotonic() - start_time
        
        if self.log:
            self.log.duration_seconds = duration
            self.log.total_rows_input = sum(len(rows) for rows in self.transformed_data.values())
            self.log.save()
        
        response = {
            'success': success,
            'log_id': self.log.id if self.log else None,
            'file_name': self.file_name,
            'file_hash': self.file_hash,
            'is_preview': not self.commit,
            'duration_seconds': round(duration, 2),
            
            'summary': {
                'sheets_found': len(self.sheets_found),
                'sheets_processed': len(self.sheets_processed),
                'sheets_skipped': len(self.sheets_skipped),
                'sheets_failed': len(self.sheets_failed),
                'total_rows_transformed': sum(len(rows) for rows in self.transformed_data.values()),
            },
            
            'sheets': {
                'found': self.sheets_found,
                'processed': self.sheets_processed,
                'skipped': self.sheets_skipped,
                'failed': self.sheets_failed,
            },
            
            'errors': self.errors,
            'warnings': self.warnings,
        }
        
        if import_result:
            response['import_result'] = import_result
        
        # Include preview data if not committing
        if not self.commit:
            response['data'] = self._preview_data()
        
        return response

