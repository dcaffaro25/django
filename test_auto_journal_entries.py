#!/usr/bin/env python3
"""
Quick test script for auto-create journal entries feature.
Tests the ETL preview endpoint with a minimal request.
"""
import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8000"
COMPANY_ID = 4
FILE_PATH = r"C:\Users\DCaff\Nord Ventures\Nord Ventures - Documentos\Clientes\DatBaby\Financeiro\Base de Dados\2025.01.xlsx"

def wait_for_server(max_retries=3, wait_seconds=10):
    """Wait for Django server to be ready."""
    for i in range(max_retries):
        try:
            response = requests.get(f"{BASE_URL}/api/core/etl/transformation-rules/", timeout=5)
            if response.status_code in [200, 401, 403]:
                print("✓ Server is ready")
                return True
        except requests.exceptions.ConnectionError:
            if i < max_retries - 1:
                print(f"Server not ready, waiting {wait_seconds}s... (attempt {i+1}/{max_retries})")
                time.sleep(wait_seconds)
    
    print("✗ Server not responding")
    return False

def test_auto_create_journal_entries():
    """Test ETL preview with auto-create journal entries."""
    
    print("\n" + "="*60)
    print("Testing Auto-Create Journal Entries Feature")
    print("="*60)
    
    # Wait for server
    if not wait_for_server():
        print("Cannot proceed - server not ready")
        return False
    
    # Check if file exists
    file_path_obj = Path(FILE_PATH)
    if not file_path_obj.exists():
        print(f"✗ File not found: {FILE_PATH}")
        return False
    
    url = f"{BASE_URL}/api/core/etl/preview/"
    
    # Auto-create journal entries configuration
    auto_config = {
        "enabled": True,
        "use_pending_bank_account": True,
        "opposing_account_field": "account_path",
        "opposing_account_lookup": "path",
        "path_separator": " > "
    }
    
    print(f"\nConfiguration:")
    print(json.dumps(auto_config, indent=2))
    print(f"\nFile: {file_path_obj.name}")
    print(f"Company ID: {COMPANY_ID}")
    print(f"\nSending request...")
    
    try:
        with open(FILE_PATH, 'rb') as f:
            files = {'file': (file_path_obj.name, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
            data = {
                'company_id': COMPANY_ID,
                'auto_create_journal_entries': json.dumps(auto_config)
            }
            
            start_time = time.time()
            response = requests.post(url, files=files, data=data, timeout=300)
            elapsed = time.time() - start_time
            
            print(f"Request completed in {elapsed:.2f}s")
            print(f"Status Code: {response.status_code}")
            
            if response.status_code != 200:
                print(f"✗ Error: {response.status_code}")
                print(f"Response: {response.text[:500]}")
                return False
            
            result = response.json()
            
            # Check success
            if not result.get('success'):
                print("\n✗ Request failed")
                errors = result.get('errors', [])
                for error in errors[:5]:
                    print(f"  Error: {error.get('message', 'Unknown')}")
                return False
            
            print("\n✓ Request successful!")
            
            # Check for Transactions
            data_section = result.get('data', {})
            would_create = data_section.get('would_create', {})
            
            transactions = would_create.get('Transaction', {})
            transaction_count = transactions.get('count', 0)
            print(f"\nTransactions: {transaction_count}")
            
            # Check for JournalEntries
            journal_entries = would_create.get('JournalEntry', {})
            je_count = journal_entries.get('count', 0)
            print(f"JournalEntries: {je_count}")
            
            if je_count == 0:
                print("\n⚠ No JournalEntries found in preview")
                print("This might indicate an issue with auto-creation")
                return False
            
            # Check for pending bank account entries
            je_records = journal_entries.get('records', [])
            pending_count = sum(1 for je in je_records if je.get('bank_designation_pending'))
            
            print(f"\n✓ JournalEntries with bank_designation_pending=True: {pending_count}")
            
            # Show sample JournalEntries
            if je_records:
                print(f"\nSample JournalEntries (first 3):")
                for idx, je in enumerate(je_records[:3]):
                    print(f"  {idx+1}. ID: {je.get('id')}, "
                          f"Account: {je.get('account_id')}, "
                          f"Transaction: {je.get('transaction_id')}, "
                          f"Pending: {je.get('bank_designation_pending', False)}")
            
            # Expected: 2 JournalEntries per Transaction
            expected_je_count = transaction_count * 2
            if je_count >= expected_je_count:
                print(f"\n✓ SUCCESS: Found {je_count} JournalEntries (expected at least {expected_je_count})")
                return True
            else:
                print(f"\n⚠ Found {je_count} JournalEntries but expected at least {expected_je_count} (2 per Transaction)")
                return False
                
    except requests.exceptions.Timeout:
        print("\n✗ Request timed out")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_auto_create_journal_entries()
    if success:
        print("\n" + "="*60)
        print("✅ TEST PASSED")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("❌ TEST FAILED")
        print("="*60)

