# Cursor Agent Prompt: ETL Service Testing & Debugging

## Mission
Test and debug the ETL auto-create journal entries feature. Make iterative improvements until it works correctly.

## CRITICAL CONSTRAINTS

### Files You CAN Modify:
- ✅ `multitenancy/etl_service.py`
- ✅ `multitenancy/views.py` (ETL-related views only)
- ✅ `multitenancy/views_etl_html.py`
- ✅ `multitenancy/templates/multitenancy/etl_preview.html`
- ✅ `multitenancy/urls.py` (if needed for ETL endpoints)

### Files You CANNOT Modify:
- ❌ **ANY model files** (`multitenancy/models.py`, `accounting/models.py`, etc.)
- ❌ Database migrations
- ❌ Serializers (unless absolutely necessary for ETL)
- ❌ Other service files outside ETL

**If you need to change models, STOP and ask the user first.**

## Testing Configuration

### Test Parameters (ALWAYS USE THESE):
```json
{
  "auto_create_journal_entries": {
    "enabled": true,
    "use_pending_bank_account": true,
    "opposing_account_field": "account_path",
    "opposing_account_lookup": "path",
    "path_separator": " > "
  },
  "commit": false  // Preview mode - don't commit to database
}
```

### Test Endpoint:
- **URL**: `POST /api/{tenant_id}/etl/preview/` or `POST /etl/preview/`
- **Method**: POST (multipart/form-data)
- **Required Fields**:
  - `file`: Excel file
  - `company_id`: Company ID
  - `auto_create_journal_entries`: JSON string with config above

## Workflow

### Step 1: Wait for Server
After making ANY code changes:
1. **Wait at least 30 seconds** for Django auto-reload
2. **Ping the server** to verify it's ready:
   ```bash
   curl http://localhost:8000/health/  # or similar health check
   # OR
   curl http://localhost:8000/api/1/etl/transformation-rules/  # test endpoint
   ```
3. If server not ready, wait additional 10s and retry (max 3 retries)

### Step 2: Check Backend Logs
**IMPORTANT**: Monitor the "Django Server" command window/terminal for:
- Error messages
- Stack traces
- Warning messages
- ETL processing logs (look for "ETL:" prefixed messages)

### Step 3: Test the Feature
1. Create or use an existing Excel file with:
   - Transaction data (date, description, amount)
   - Account path in a column (e.g., "Despesas > Serviços")
   - Map to `extra_fields_for_trigger` in transformation rule

2. Send request with:
   ```python
   import requests
   
   url = "http://localhost:8000/api/1/etl/preview/"
   files = {'file': open('test.xlsx', 'rb')}
   data = {
       'company_id': 1,
       'auto_create_journal_entries': '{"enabled": true, "use_pending_bank_account": true, "opposing_account_field": "account_path", "opposing_account_lookup": "path", "path_separator": " > "}'
   }
   
   response = requests.post(url, files=files, data=data)
   print(response.json())
   ```

### Step 4: Analyze Results
Check the response for:
- ✅ `success: true`
- ✅ `data.would_create.Transaction` - should have Transaction records
- ✅ `data.would_create.JournalEntry` - should have 2 JournalEntries per Transaction
- ✅ JournalEntries should have `bank_designation_pending: true` for bank entry
- ❌ Any errors in `errors` array
- ❌ Any warnings in `warnings` array

### Step 5: Debug & Fix
If errors occur:

1. **Read the error message carefully** from:
   - API response `errors` field
   - Backend logs in "Django Server" window
   - Stack traces

2. **Identify the root cause**:
   - Is it a Transaction lookup issue?
   - Is it a JournalEntry creation issue?
   - Is it a pending bank account setup issue?
   - Is it a field mapping issue?

3. **Fix the code** (only in allowed files):
   - Add error handling
   - Fix logic errors
   - Add logging for debugging
   - Ensure transaction linking works correctly

4. **Add defensive checks**:
   - Verify transaction exists before creating JournalEntries
   - Handle missing accounts gracefully
   - Validate configuration parameters
   - Check for None/null values

### Step 6: Iterate
1. After each fix, **wait 30s** for server reload
2. **Ping server** to verify ready
3. **Re-run test**
4. **Check logs** again
5. **Repeat** until working

## Common Issues to Watch For

### Issue 1: "Transaction matching query does not exist"
**Fix**: Ensure we're using `Transaction.objects.filter().first()` and checking if transaction exists before proceeding.

### Issue 2: "JournalEntry validation error"
**Fix**: Check that:
- `bank_designation_pending=True` when using pending bank account
- `account` is set when `bank_designation_pending=False`
- Transaction ID is correctly linked

### Issue 3: "Account not found"
**Fix**: Verify account lookup logic:
- Path resolution works correctly
- Code resolution works correctly
- ID resolution works correctly

### Issue 4: "Server not responding"
**Fix**: 
- Wait longer (60s instead of 30s)
- Check if Django server is actually running
- Verify port is correct (8000)

## Logging Strategy

Add detailed logging to help debug:
```python
import logging
logger = logging.getLogger(__name__)

# Log key steps
logger.info(f"ETL: Starting auto-create for {len(transaction_outputs)} Transactions")
logger.debug(f"ETL: Transaction {transaction_id} found: {transaction is not None}")
logger.debug(f"ETL: Using pending bank: {use_pending_bank}")
logger.debug(f"ETL: Bank ledger account: {bank_ledger_account}")
logger.debug(f"ETL: Opposing account: {opposing_account}")
logger.error(f"ETL: Error creating JournalEntry: {e}", exc_info=True)
```

## Success Criteria

The feature is working when:
1. ✅ Request returns `success: true`
2. ✅ Transactions are created from Excel
3. ✅ 2 JournalEntries are created per Transaction:
   - 1 bank entry with `bank_designation_pending: true`
   - 1 opposing account entry with proper account
4. ✅ No errors in response
5. ✅ JournalEntries are correctly linked to Transactions
6. ✅ Debit/credit amounts are calculated correctly based on amount sign

## Testing Script Template

```python
#!/usr/bin/env python3
"""
ETL Auto-Create Journal Entries Test Script
"""
import requests
import time
import json

BASE_URL = "http://localhost:8000"
COMPANY_ID = 1

def wait_for_server(max_retries=3, wait_seconds=30):
    """Wait for Django server to be ready."""
    print(f"Waiting {wait_seconds}s for server to reload...")
    time.sleep(wait_seconds)
    
    for i in range(max_retries):
        try:
            response = requests.get(f"{BASE_URL}/api/{COMPANY_ID}/etl/transformation-rules/", timeout=5)
            if response.status_code in [200, 401, 403]:  # Any response means server is up
                print("✓ Server is ready")
                return True
        except requests.exceptions.ConnectionError:
            print(f"Server not ready, waiting 10s more... (attempt {i+1}/{max_retries})")
            time.sleep(10)
    
    print("✗ Server not responding")
    return False

def test_etl_preview(excel_file_path):
    """Test ETL preview with auto-create journal entries."""
    url = f"{BASE_URL}/api/{COMPANY_ID}/etl/preview/"
    
    config = {
        "enabled": True,
        "use_pending_bank_account": True,
        "opposing_account_field": "account_path",
        "opposing_account_lookup": "path",
        "path_separator": " > "
    }
    
    files = {'file': open(excel_file_path, 'rb')}
    data = {
        'company_id': COMPANY_ID,
        'auto_create_journal_entries': json.dumps(config)
    }
    
    print(f"\nTesting ETL preview with config: {json.dumps(config, indent=2)}")
    print(f"Excel file: {excel_file_path}")
    
    try:
        response = requests.post(url, files=files, data=data, timeout=60)
        result = response.json()
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Success: {result.get('success', False)}")
        
        if result.get('success'):
            transactions = result.get('data', {}).get('would_create', {}).get('Transaction', {})
            journal_entries = result.get('data', {}).get('would_create', {}).get('JournalEntry', {})
            
            print(f"\n✓ Transactions would be created: {transactions.get('count', 0)}")
            print(f"✓ JournalEntries would be created: {journal_entries.get('count', 0)}")
            
            # Check for pending bank account
            if journal_entries.get('records'):
                for je in journal_entries['records'][:2]:  # Check first 2
                    if je.get('bank_designation_pending'):
                        print(f"✓ Found pending bank account JournalEntry: {je.get('id')}")
        else:
            print(f"\n✗ Errors:")
            for error in result.get('errors', []):
                print(f"  - {error.get('message', 'Unknown error')}")
            
            print(f"\n✗ Warnings:")
            for warning in result.get('warnings', []):
                print(f"  - {warning.get('message', 'Unknown warning')}")
        
        return result
        
    except Exception as e:
        print(f"\n✗ Request failed: {e}")
        return None
    finally:
        files['file'].close()

if __name__ == "__main__":
    # Wait for server
    if not wait_for_server():
        print("Cannot proceed - server not ready")
        exit(1)
    
    # Run test
    excel_file = "test_transactions.xlsx"  # Update with your test file
    result = test_etl_preview(excel_file)
    
    if result and result.get('success'):
        print("\n✅ Test PASSED")
    else:
        print("\n❌ Test FAILED - check logs and fix issues")
```

## Instructions for Agent

1. **Read this entire prompt carefully**
2. **Identify the issue** from error messages and logs
3. **Make targeted fixes** in allowed files only
4. **Wait 30s + ping server** after each change
5. **Re-test** and verify fix
6. **Iterate** until working
7. **Report** what was fixed and why

## Remember

- ⏱️ **Always wait 30s** after code changes
- 🔍 **Always check backend logs** in "Django Server" window
- 🚫 **Never modify models** without asking
- ✅ **Test with commit=false** first (preview mode)
- 🔄 **Loop until it works**

Good luck! 🚀

