# multitenancy/etl_tasks.py
"""
Celery tasks for ETL Pipeline and Import Template processing.

Features:
- Support for multiple files in a single batch
- Real-time progress tracking and statistics
- Comprehensive error handling and logging
- Status updates via ETLPipelineLog model
"""

import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from io import BytesIO

from celery import shared_task
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.db import transaction
from django.utils import timezone

from .etl_service import ETLPipelineService
from .models import ETLPipelineLog

logger = logging.getLogger(__name__)


# ============================================================================
# ETL Pipeline Tasks
# ============================================================================

@shared_task(bind=True, name='etl.process_etl_file')
def process_etl_file_task(
    self,
    company_id: int,
    file_data: bytes,
    file_name: str,
    file_hash: str,
    commit: bool = False,
    auto_create_journal_entries: Optional[Dict[str, Any]] = None,
    row_limit: Optional[int] = None,
    log_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Process a single ETL file asynchronously.
    
    Args:
        company_id: Company ID for the import
        file_data: File content as bytes
        file_name: Original filename
        file_hash: SHA256 hash of the file
        commit: Whether to commit changes (False = preview mode)
        auto_create_journal_entries: Configuration for auto-creating journal entries
        row_limit: Limit number of rows to process (None = default, 0 = all)
        log_id: Optional ETLPipelineLog ID to update
        
    Returns:
        Dict with processing results and statistics
    """
    start_time = time.monotonic()
    stats = {
        'file_name': file_name,
        'file_hash': file_hash,
        'status': 'processing',
        'started_at': timezone.now().isoformat(),
        'stages': {},
        'errors': [],
        'warnings': [],
    }
    
    try:
        # Create file-like object from bytes
        file_obj = BytesIO(file_data)
        file_obj.name = file_name
        
        # Update log if provided
        log = None
        if log_id:
            try:
                log = ETLPipelineLog.objects.get(id=log_id, company_id=company_id)
                log.status = 'transforming'
                log.save(update_fields=['status'])
            except ETLPipelineLog.DoesNotExist:
                logger.warning(f"ETLPipelineLog {log_id} not found, continuing without log updates")
        
        # Initialize ETL service
        stage_start = time.monotonic()
        service = ETLPipelineService(
            company_id=company_id,
            file=file_obj,
            commit=commit,
            auto_create_journal_entries=auto_create_journal_entries or {},
            row_limit=row_limit
        )
        
        # If log exists, attach it to service
        if log:
            service.log = log
        
        # Execute pipeline
        result = service.execute()
        
        # Collect statistics
        stage_time = time.monotonic() - stage_start
        total_time = time.monotonic() - start_time
        
        stats.update({
            'status': 'completed' if result.get('success') else 'failed',
            'completed_at': timezone.now().isoformat(),
            'duration_seconds': total_time,
            'stages': {
                'transformation': {
                    'duration': stage_time,
                    'sheets_found': result.get('summary', {}).get('sheets_found', []),
                    'sheets_processed': result.get('summary', {}).get('sheets_processed', []),
                }
            },
            'summary': result.get('summary', {}),
            'errors': result.get('errors', []),
            'warnings': result.get('warnings', []),
            'records_created': result.get('summary', {}).get('records_created', {}),
            'total_rows_processed': result.get('summary', {}).get('total_rows_transformed', 0),
        })
        
        # Update log with final status
        if log:
            log.status = 'completed' if result.get('success') else 'failed'
            log.completed_at = timezone.now()
            log.duration_seconds = total_time
            log.save(update_fields=['status', 'completed_at', 'duration_seconds'])
        
        logger.info(
            f"ETL task completed: {file_name} | "
            f"Status: {stats['status']} | "
            f"Duration: {total_time:.2f}s | "
            f"Rows: {stats['total_rows_processed']}"
        )
        
        return stats
        
    except Exception as e:
        error_msg = str(e)
        logger.exception(f"ETL task failed: {file_name} | Error: {error_msg}")
        
        stats.update({
            'status': 'failed',
            'completed_at': timezone.now().isoformat(),
            'duration_seconds': time.monotonic() - start_time,
            'errors': [{
                'type': 'task_error',
                'message': error_msg,
                'stage': 'execution',
            }],
        })
        
        # Update log with error
        if log_id:
            try:
                log = ETLPipelineLog.objects.get(id=log_id, company_id=company_id)
                log.status = 'failed'
                log.completed_at = timezone.now()
                log.duration_seconds = time.monotonic() - start_time
                log.save(update_fields=['status', 'completed_at', 'duration_seconds'])
            except ETLPipelineLog.DoesNotExist:
                pass
        
        # Re-raise to trigger Celery retry mechanism if configured
        raise
    
    finally:
        # Cleanup
        if 'file_obj' in locals():
            file_obj.close()


@shared_task(bind=True, name='etl.process_etl_batch')
def process_etl_batch_task(
    self,
    company_id: int,
    files: List[Dict[str, Any]],
    commit: bool = False,
    auto_create_journal_entries: Optional[Dict[str, Any]] = None,
    row_limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Process multiple ETL files in a batch.
    
    Args:
        company_id: Company ID for the import
        files: List of file dicts with keys: 'data' (bytes), 'name' (str), 'hash' (str)
        commit: Whether to commit changes
        auto_create_journal_entries: Configuration for auto-creating journal entries
        row_limit: Limit number of rows to process per file
        
    Returns:
        Dict with batch results and per-file statistics
    """
    batch_start = time.monotonic()
    batch_stats = {
        'batch_id': self.request.id,
        'company_id': company_id,
        'total_files': len(files),
        'started_at': timezone.now().isoformat(),
        'files': [],
        'summary': {
            'completed': 0,
            'failed': 0,
            'total_rows_processed': 0,
            'total_records_created': {},
        },
    }
    
    logger.info(f"Starting ETL batch: {len(files)} files | Company: {company_id}")
    
    # Process each file
    for idx, file_info in enumerate(files, 1):
        file_name = file_info.get('name', f'file_{idx}')
        file_data = file_info.get('data')
        file_hash = file_info.get('hash', '')
        
        if not file_data:
            logger.warning(f"Skipping file {idx}: No data provided")
            batch_stats['files'].append({
                'file_name': file_name,
                'status': 'skipped',
                'error': 'No file data provided',
            })
            batch_stats['summary']['failed'] += 1
            continue
        
        logger.info(f"Processing file {idx}/{len(files)}: {file_name}")
        
        # Process file (synchronously in batch, or could be parallelized)
        try:
            file_result = process_etl_file_task(
                company_id=company_id,
                file_data=file_data,
                file_name=file_name,
                file_hash=file_hash,
                commit=commit,
                auto_create_journal_entries=auto_create_journal_entries,
                row_limit=row_limit,
                log_id=None  # Could create individual logs per file
            )
            
            batch_stats['files'].append(file_result)
            
            if file_result['status'] == 'completed':
                batch_stats['summary']['completed'] += 1
                batch_stats['summary']['total_rows_processed'] += file_result.get('total_rows_processed', 0)
                
                # Merge records_created
                records = file_result.get('records_created', {})
                for model, count in records.items():
                    batch_stats['summary']['total_records_created'][model] = \
                        batch_stats['summary']['total_records_created'].get(model, 0) + count
            else:
                batch_stats['summary']['failed'] += 1
                
        except Exception as e:
            logger.exception(f"Error processing file {file_name}: {e}")
            batch_stats['files'].append({
                'file_name': file_name,
                'status': 'failed',
                'error': str(e),
            })
            batch_stats['summary']['failed'] += 1
    
    # Finalize batch stats
    batch_duration = time.monotonic() - batch_start
    batch_stats.update({
        'completed_at': timezone.now().isoformat(),
        'duration_seconds': batch_duration,
        'status': 'completed' if batch_stats['summary']['failed'] == 0 else 'partial',
    })
    
    logger.info(
        f"ETL batch completed: {batch_stats['summary']['completed']}/{len(files)} files | "
        f"Duration: {batch_duration:.2f}s | "
        f"Total rows: {batch_stats['summary']['total_rows_processed']}"
    )
    
    return batch_stats


# ============================================================================
# Import Template Tasks
# ============================================================================

@shared_task(bind=True, name='import.process_import_template')
def process_import_template_task(
    self,
    company_id: int,
    sheets: List[Dict[str, Any]],
    commit: bool = False,
    file_meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Process import template (bulk import) asynchronously.
    
    Args:
        company_id: Company ID for the import
        sheets: List of sheet dicts with 'model' and 'rows' keys
        commit: Whether to commit changes
        file_meta: Optional metadata about the source file
        
    Returns:
        Dict with import results and statistics
    """
    from .tasks import execute_import_job
    
    start_time = time.monotonic()
    stats = {
        'task_id': self.request.id,
        'company_id': company_id,
        'status': 'processing',
        'started_at': timezone.now().isoformat(),
        'file_meta': file_meta or {},
        'sheets_count': len(sheets),
        'stages': {},
    }
    
    try:
        logger.info(
            f"Import template task started: {len(sheets)} sheets | "
            f"Company: {company_id} | Commit: {commit}"
        )
        
        # Build import_metadata with filename for notes
        import_metadata = {
            'source': 'Import',
            'function': 'process_import_template_task',
            'filename': file_meta.get('filename') if file_meta else None,
        }
        
        # Execute import job
        stage_start = time.monotonic()
        result = execute_import_job(company_id, sheets, commit, import_metadata=import_metadata)
        stage_time = time.monotonic() - stage_start
        
        # Collect statistics
        total_time = time.monotonic() - start_time
        
        # Extract stats from result
        outputs_by_model = result.get('outputs_by_model', {})
        total_created = sum(
            len([r for r in rows if r.get('status') == 'created'])
            for rows in outputs_by_model.values()
        )
        total_errors = sum(
            len([r for r in rows if r.get('status') == 'error'])
            for rows in outputs_by_model.values()
        )
        
        stats.update({
            'status': 'completed',
            'completed_at': timezone.now().isoformat(),
            'duration_seconds': total_time,
            'stages': {
                'import': {
                    'duration': stage_time,
                    'sheets_processed': len(sheets),
                }
            },
            'summary': {
                'total_records_created': total_created,
                'total_errors': total_errors,
                'models_processed': list(outputs_by_model.keys()),
                'records_by_model': {
                    model: len([r for r in rows if r.get('status') == 'created'])
                    for model, rows in outputs_by_model.items()
                },
            },
            'outputs_by_model': outputs_by_model,
        })
        
        logger.info(
            f"Import template task completed: {total_created} records created | "
            f"Duration: {total_time:.2f}s | "
            f"Errors: {total_errors}"
        )
        
        return stats
        
    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Import template task failed: {error_msg}")
        
        stats.update({
            'status': 'failed',
            'completed_at': timezone.now().isoformat(),
            'duration_seconds': time.monotonic() - start_time,
            'error': error_msg,
        })
        
        raise


@shared_task(bind=True, name='import.process_import_batch')
def process_import_batch_task(
    self,
    company_id: int,
    files: List[Dict[str, Any]],
    commit: bool = False
) -> Dict[str, Any]:
    """
    Process multiple import template files in a batch.
    
    Args:
        company_id: Company ID for the import
        files: List of file dicts with 'sheets' (List[Dict]) and optional 'meta' (Dict)
        commit: Whether to commit changes
        
    Returns:
        Dict with batch results and per-file statistics
    """
    batch_start = time.monotonic()
    batch_stats = {
        'batch_id': self.request.id,
        'company_id': company_id,
        'total_files': len(files),
        'started_at': timezone.now().isoformat(),
        'files': [],
        'summary': {
            'completed': 0,
            'failed': 0,
            'total_records_created': 0,
            'total_errors': 0,
            'records_by_model': {},
        },
    }
    
    logger.info(f"Starting import batch: {len(files)} files | Company: {company_id}")
    
    # Process each file
    for idx, file_info in enumerate(files, 1):
        sheets = file_info.get('sheets', [])
        file_meta = file_info.get('meta', {})
        file_name = file_meta.get('filename', f'file_{idx}')
        
        if not sheets:
            logger.warning(f"Skipping file {idx}: No sheets provided")
            batch_stats['files'].append({
                'file_name': file_name,
                'status': 'skipped',
                'error': 'No sheets provided',
            })
            batch_stats['summary']['failed'] += 1
            continue
        
        logger.info(f"Processing file {idx}/{len(files)}: {file_name} ({len(sheets)} sheets)")
        
        # Process file
        try:
            file_result = process_import_template_task(
                company_id=company_id,
                sheets=sheets,
                commit=commit,
                file_meta=file_meta
            )
            
            batch_stats['files'].append(file_result)
            
            if file_result['status'] == 'completed':
                batch_stats['summary']['completed'] += 1
                batch_stats['summary']['total_records_created'] += \
                    file_result.get('summary', {}).get('total_records_created', 0)
                batch_stats['summary']['total_errors'] += \
                    file_result.get('summary', {}).get('total_errors', 0)
                
                # Merge records_by_model
                records_by_model = file_result.get('summary', {}).get('records_by_model', {})
                for model, count in records_by_model.items():
                    batch_stats['summary']['records_by_model'][model] = \
                        batch_stats['summary']['records_by_model'].get(model, 0) + count
            else:
                batch_stats['summary']['failed'] += 1
                
        except Exception as e:
            logger.exception(f"Error processing file {file_name}: {e}")
            batch_stats['files'].append({
                'file_name': file_name,
                'status': 'failed',
                'error': str(e),
            })
            batch_stats['summary']['failed'] += 1
    
    # Finalize batch stats
    batch_duration = time.monotonic() - batch_start
    batch_stats.update({
        'completed_at': timezone.now().isoformat(),
        'duration_seconds': batch_duration,
        'status': 'completed' if batch_stats['summary']['failed'] == 0 else 'partial',
    })
    
    logger.info(
        f"Import batch completed: {batch_stats['summary']['completed']}/{len(files)} files | "
        f"Duration: {batch_duration:.2f}s | "
        f"Total records: {batch_stats['summary']['total_records_created']}"
    )
    
    return batch_stats

