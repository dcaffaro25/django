#!/usr/bin/env python3
"""Quick test of auto-create journal entries feature"""
import requests
import json
from pathlib import Path

FILE_PATH = r"C:\Users\DCaff\Nord Ventures\Nord Ventures - Documentos\Clientes\DatBaby\Financeiro\Base de Dados\2025.01.xlsx"
URL = "http://localhost:8000/api/core/etl/preview/"
COMPANY_ID = 4

auto_config = {
    "enabled": True,
    "use_pending_bank_account": True,
    "opposing_account_field": "account_path",
    "opposing_account_lookup": "path",
    "path_separator": " > "
}

print("="*60)
print("Testing Auto-Create Journal Entries Feature")
print("="*60)
print(f"\nConfiguration:")
print(json.dumps(auto_config, indent=2))
print(f"\nFile: {Path(FILE_PATH).name}")
print(f"Company ID: {COMPANY_ID}")
print(f"\nSending request...")

try:
    with open(FILE_PATH, 'rb') as f:
        files = {'file': (Path(FILE_PATH).name, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        data = {
            'company_id': COMPANY_ID,
            'auto_create_journal_entries': json.dumps(auto_config),
            'row_limit': 10  # Process only first 10 rows for testing (0 = all rows)
        }
        
        response = requests.post(URL, files=files, data=data, timeout=300)
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('success'):
                print("\n✓ Request successful!")
                
                data_section = result.get('data', {})
                would_create = data_section.get('would_create', {})
                
                # Check Transactions
                transactions = would_create.get('Transaction', {})
                tx_count = transactions.get('count', 0)
                print(f"\nTransactions: {tx_count}")
                
                # Check JournalEntries
                journal_entries = would_create.get('JournalEntry', {})
                je_count = journal_entries.get('count', 0)
                print(f"JournalEntries: {je_count}")
                
                if je_count > 0:
                    je_records = journal_entries.get('records', [])
                    pending_count = sum(1 for je in je_records if je.get('bank_designation_pending'))
                    
                    print(f"\n✓ JournalEntries with bank_designation_pending=True: {pending_count}")
                    
                    # Show first few JournalEntries
                    print(f"\nFirst 3 JournalEntries:")
                    for idx, je in enumerate(je_records[:3]):
                        print(f"  {idx+1}. ID: {je.get('id')}, "
                              f"Account: {je.get('account_id')}, "
                              f"Transaction: {je.get('transaction_id')}, "
                              f"Pending: {je.get('bank_designation_pending', False)}, "
                              f"Debit: {je.get('debit_amount')}, "
                              f"Credit: {je.get('credit_amount')}")
                    
                    # Expected: 2 JournalEntries per Transaction
                    expected_min = tx_count * 2
                    if je_count >= expected_min:
                        print(f"\n✅ SUCCESS: Found {je_count} JournalEntries (expected at least {expected_min})")
                    else:
                        print(f"\n⚠ Found {je_count} JournalEntries but expected at least {expected_min}")
                else:
                    print("\n❌ No JournalEntries found in preview")
                    print("This indicates the auto-create feature is not working")
                
                # Check for errors/warnings
                errors = result.get('errors', [])
                warnings = result.get('warnings', [])
                
                if errors:
                    print(f"\n⚠ Errors ({len(errors)}):")
                    for error in errors[:3]:
                        print(f"  - {error.get('message', 'Unknown error')}")
                
                if warnings:
                    print(f"\n⚠ Warnings ({len(warnings)}):")
                    for warning in warnings[:3]:
                        print(f"  - {warning.get('message', 'Unknown warning')}")
            else:
                print("\n❌ Request returned success=False")
                errors = result.get('errors', [])
                for error in errors[:5]:
                    print(f"  Error: {error.get('message', 'Unknown')}")
        else:
            print(f"\n❌ HTTP Error: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

