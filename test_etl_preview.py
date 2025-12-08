"""
ETL Preview Endpoint Test Script

This script tests the ETL preview endpoint with the specified Excel file.
"""

import requests
import json
from pathlib import Path
from datetime import datetime

# ============================================
# CONFIGURATION - Update these values
# ============================================

# Server URL (default: localhost:8000)
BASE_URL = "http://localhost:8000"

# Excel file path
FILE_PATH = r"C:\Users\DCaff\Nord Ventures\Nord Ventures - Documentos\Clientes\DatBaby\Financeiro\Base de Dados\2025.01.xlsx"

# Company ID (check your database if unsure)
COMPANY_ID = 4

# ============================================
# END CONFIGURATION
# ============================================

def format_duration(seconds):
    """Format duration in a readable way."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"

def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def print_success(message):
    """Print a success message."""
    print(f"✓ {message}")

def print_error(message):
    """Print an error message."""
    print(f"❌ {message}")

def print_warning(message):
    """Print a warning message."""
    print(f"⚠ {message}")

def test_etl_preview():
    """Test the ETL preview endpoint."""
    
    url = f"{BASE_URL}/api/core/etl/preview/"
    
    print_section("ETL Preview Endpoint Test")
    print(f"Server: {BASE_URL}")
    print(f"File: {FILE_PATH}")
    print(f"Company ID: {COMPANY_ID}")
    
    # Check if file exists
    file_path_obj = Path(FILE_PATH)
    if not file_path_obj.exists():
        print_error(f"File not found: {FILE_PATH}")
        return
    
    file_size = file_path_obj.stat().st_size / (1024 * 1024)  # Size in MB
    print(f"File Size: {file_size:.2f} MB")
    
    print_section("Sending Request")
    
    try:
        # Prepare auto_create_journal_entries configuration
        auto_config = {
            "enabled": True,
            "use_pending_bank_account": True,
            "opposing_account_field": "account_path",
            "opposing_account_lookup": "path",
            "path_separator": " > "
        }
        
        print_section("Auto-Create Journal Entries Configuration")
        print(json.dumps(auto_config, indent=2))
        
        # Prepare the request
        with open(FILE_PATH, 'rb') as f:
            files = {
                'file': (
                    file_path_obj.name, 
                    f, 
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
            }
            data = {
                'company_id': COMPANY_ID,
                'auto_create_journal_entries': json.dumps(auto_config),
                'row_limit': 10  # Process only first 10 rows for testing (0 = all rows)
            }
            
            print("Uploading file and processing...")
            start_time = datetime.now()
            
            response = requests.post(url, files=files, data=data, timeout=300)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            print(f"Request completed in {format_duration(elapsed)}")
            
            # Check response status
            response.raise_for_status()
            
            result = response.json()
            
            print_section("Response Summary")
            
            # Basic info
            print_success(f"Preview completed successfully!")
            print(f"  Log ID: {result.get('log_id')}")
            print(f"  Duration: {format_duration(result.get('duration_seconds', 0))}")
            print(f"  File: {result.get('file_name')}")
            
            # Summary
            summary = result.get('summary', {})
            print(f"\n  Sheets:")
            print(f"    - Found: {summary.get('sheets_found', 0)}")
            print(f"    - Processed: {summary.get('sheets_processed', 0)}")
            print(f"    - Skipped: {summary.get('sheets_skipped', 0)}")
            print(f"    - Failed: {summary.get('sheets_failed', 0)}")
            print(f"    - Rows Transformed: {summary.get('total_rows_transformed', 0)}")
            
            # Data section
            data_section = result.get('data', {})
            
            # Would create (flat)
            would_create = data_section.get('would_create', {})
            if would_create:
                print_section("Records That Would Be Created (Flat)")
                for model_name, model_data in would_create.items():
                    count = model_data.get('count', 0)
                    print(f"  {model_name}: {count} record(s)")
                    
                    # Special handling for JournalEntry to check for pending bank account
                    if model_name == 'JournalEntry':
                        records = model_data.get('records', [])
                        pending_count = sum(1 for r in records if r.get('bank_designation_pending'))
                        if pending_count > 0:
                            print_success(f"    ✓ {pending_count} JournalEntry(ies) with bank_designation_pending=True")
                        
                        # Show sample records
                        if records:
                            print(f"\n    Sample JournalEntries (first 3):")
                            for idx, record in enumerate(records[:3]):
                                print(f"      {idx+1}. ID: {record.get('id')}, Account: {record.get('account_id')}, "
                                      f"Debit: {record.get('debit_amount')}, Credit: {record.get('credit_amount')}, "
                                      f"Pending: {record.get('bank_designation_pending', False)}")
            
            # Would create by row (grouped) - NEW FEATURE
            would_create_by_row = data_section.get('would_create_by_row', [])
            if would_create_by_row:
                print_section(f"Records Grouped by Excel Row ({len(would_create_by_row)} rows)")
                
                # Show first 5 rows as sample
                for idx, row_group in enumerate(would_create_by_row[:5]):
                    row_num = row_group.get('excel_row_number')
                    sheet_name = row_group.get('excel_sheet')
                    created_records = row_group.get('created_records', {})
                    
                    print(f"\n  Row {row_num} ({sheet_name}):")
                    total_records = 0
                    for model, records in created_records.items():
                        count = len(records) if isinstance(records, list) else 1
                        total_records += count
                        print(f"    - {model}: {count} record(s)")
                    print(f"    Total: {total_records} record(s) created from this Excel row")
                
                if len(would_create_by_row) > 5:
                    print(f"\n  ... and {len(would_create_by_row) - 5} more rows")
            
            # Would fail
            would_fail = data_section.get('would_fail', {})
            if would_fail:
                print_section("Records That Would Fail")
                for model_name, fail_data in would_fail.items():
                    count = fail_data.get('count', 0)
                    print(f"  {model_name}: {count} row(s) would fail")
                    # Show first few failures
                    failed_rows = fail_data.get('rows', [])[:3]
                    for failed_row in failed_rows:
                        row_num = failed_row.get('row_number')
                        reason = failed_row.get('reason', 'Unknown reason')
                        print(f"    - Row {row_num}: {reason}")
            
            # Warnings
            warnings = result.get('warnings', [])
            if warnings:
                print_section(f"Warnings ({len(warnings)})")
                for warning in warnings[:5]:
                    warning_type = warning.get('type', 'unknown')
                    message = warning.get('message', 'No message')
                    print(f"  [{warning_type}] {message}")
                if len(warnings) > 5:
                    print(f"  ... and {len(warnings) - 5} more warnings")
            
            # Errors
            errors = result.get('errors', [])
            if errors:
                print_section(f"Errors ({len(errors)})")
                for error in errors[:5]:
                    error_type = error.get('type', 'unknown')
                    message = error.get('message', 'No message')
                    print(f"  [{error_type}] {message}")
                if len(errors) > 5:
                    print(f"  ... and {len(errors) - 5} more errors")
            
            # Save full response
            output_file = f"etl_preview_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w', encoding='utf-8') as outfile:
                json.dump(result, outfile, indent=2, ensure_ascii=False, default=str)
            
            print_section("Response Saved")
            print_success(f"Full response saved to: {output_file}")
            
            return result
            
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to server. Is it running?")
        print(f"  Try: python manage.py runserver")
        return None
        
    except requests.exceptions.Timeout:
        print_error("Request timed out. The file might be too large or server is slow.")
        return None
        
    except requests.exceptions.HTTPError as e:
        print_error(f"HTTP Error: {e}")
        if hasattr(e.response, 'text'):
            print(f"Response: {e.response.text[:500]}")
        return None
        
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_etl_preview()

