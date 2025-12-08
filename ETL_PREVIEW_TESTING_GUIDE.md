# ETL Preview Endpoint - Testing Guide

## Endpoint Information

- **URL**: `http://localhost:8000/api/core/etl/preview/`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Authentication**: Not required (AUTH_OFF = True in local settings)

## Required Parameters

1. **file** (required): Excel file to upload
2. **company_id** (required): Company ID (can be passed as form data or in URL)

## Test File Path

```
C:\Users\DCaff\Nord Ventures\Nord Ventures - Documentos\Clientes\DatBaby\Financeiro\Base de Dados\2025.01.xlsx
```

---

## Testing Methods

### Method 1: Using cURL (Command Line)

Open PowerShell or Command Prompt and run:

```bash
curl -X POST "http://localhost:8000/api/core/etl/preview/" ^
  -F "file=@\"C:\Users\DCaff\Nord Ventures\Nord Ventures - Documentos\Clientes\DatBaby\Financeiro\Base de Dados\2025.01.xlsx\"" ^
  -F "company_id=10" ^
  -o response.json
```

**Note for PowerShell**: Use backticks for line continuation:
```powershell
curl -X POST "http://localhost:8000/api/core/etl/preview/" `
  -F "file=@`"C:\Users\DCaff\Nord Ventures\Nord Ventures - Documentos\Clientes\DatBaby\Financeiro\Base de Dados\2025.01.xlsx`"" `
  -F "company_id=10" `
  -o response.json
```

To view the response in a readable format:
```bash
type response.json | python -m json.tool
```

---

### Method 2: Using PowerShell (Invoke-RestMethod)

```powershell
$filePath = "C:\Users\DCaff\Nord Ventures\Nord Ventures - Documentos\Clientes\DatBaby\Financeiro\Base de Dados\2025.01.xlsx"
$url = "http://localhost:8000/api/core/etl/preview/"

$form = @{
    file = Get-Item -Path $filePath
    company_id = 10
}

try {
    $response = Invoke-RestMethod -Uri $url -Method Post -Form $form -ContentType "multipart/form-data"
    $response | ConvertTo-Json -Depth 10 | Out-File -FilePath "response.json" -Encoding UTF8
    Write-Host "Response saved to response.json"
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error: $_"
    $_.Exception.Response
}
```

---

### Method 3: Using Python (requests library)

Create a file `test_etl_preview.py`:

```python
import requests
import json
from pathlib import Path

# Configuration
url = "http://localhost:8000/api/core/etl/preview/"
file_path = r"C:\Users\DCaff\Nord Ventures\Nord Ventures - Documentos\Clientes\DatBaby\Financeiro\Base de Dados\2025.01.xlsx"
company_id = 10

# Prepare the request
with open(file_path, 'rb') as f:
    files = {
        'file': (Path(file_path).name, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    data = {
        'company_id': company_id
    }
    
    try:
        response = requests.post(url, files=files, data=data)
        response.raise_for_status()
        
        # Save response to file
        result = response.json()
        with open('etl_preview_response.json', 'w', encoding='utf-8') as outfile:
            json.dump(result, outfile, indent=2, ensure_ascii=False, default=str)
        
        print("✓ Request successful!")
        print(f"✓ Response saved to etl_preview_response.json")
        print(f"\nSummary:")
        print(f"  - Success: {result.get('success', False)}")
        print(f"  - Duration: {result.get('duration_seconds', 0)}s")
        print(f"  - Log ID: {result.get('log_id')}")
        print(f"\nSheets:")
        summary = result.get('summary', {})
        print(f"  - Found: {summary.get('sheets_found', 0)}")
        print(f"  - Processed: {summary.get('sheets_processed', 0)}")
        print(f"  - Skipped: {summary.get('sheets_skipped', 0)}")
        print(f"  - Failed: {summary.get('sheets_failed', 0)}")
        print(f"  - Rows Transformed: {summary.get('total_rows_transformed', 0)}")
        
        # Show would_create_by_row count
        data_section = result.get('data', {})
        would_create_by_row = data_section.get('would_create_by_row', [])
        if would_create_by_row:
            print(f"\n✓ Records grouped by Excel row: {len(would_create_by_row)} rows")
            print(f"\nFirst few rows:")
            for idx, row_group in enumerate(would_create_by_row[:3]):
                print(f"\n  Row {row_group.get('excel_row_number')} ({row_group.get('excel_sheet')}):")
                created = row_group.get('created_records', {})
                for model, records in created.items():
                    print(f"    - {model}: {len(records)} record(s)")
        
        # Show warnings/errors
        warnings = result.get('warnings', [])
        errors = result.get('errors', [])
        if warnings:
            print(f"\n⚠ Warnings: {len(warnings)}")
        if errors:
            print(f"\n❌ Errors: {len(errors)}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        if hasattr(e.response, 'text'):
            print(f"Response: {e.response.text}")
```

Run it:
```bash
python test_etl_preview.py
```

---

### Method 4: Using Postman

1. **Open Postman**
2. **Create a new request**:
   - Method: `POST`
   - URL: `http://localhost:8000/api/core/etl/preview/`

3. **Go to Body tab**:
   - Select `form-data`
   - Add key `file`, change type to `File`, browse and select your Excel file
   - Add key `company_id`, type `Text`, value `10`

4. **Click Send**

5. **View Response**: The response will show:
   - `success`: Whether the preview was successful
   - `data.would_create_by_row`: Records grouped by Excel row
   - `data.would_create`: Flat list of all records
   - `warnings`: Any warnings
   - `errors`: Any errors

---

### Method 5: Using HTTPie (if installed)

```bash
http --form POST http://localhost:8000/api/core/etl/preview/ \
  file@"C:\Users\DCaff\Nord Ventures\Nord Ventures - Documentos\Clientes\DatBaby\Financeiro\Base de Dados\2025.01.xlsx" \
  company_id=10
```

---

## Expected Response Structure

```json
{
  "success": true,
  "log_id": 10,
  "file_name": "2025.01.xlsx",
  "is_preview": true,
  "duration_seconds": 3.27,
  "summary": {
    "sheets_found": 8,
    "sheets_processed": 1,
    "total_rows_transformed": 203
  },
  "data": {
    "transformed_data": { ... },
    "would_create": { ... },
    "would_create_by_row": [
      {
        "excel_sheet": "Base Ajustada",
        "excel_row_number": 115,
        "excel_row_id": "Base Ajustada:115",
        "created_records": {
          "Transaction": [ ... ],
          "JournalEntry": [ ... ]
        }
      }
    ],
    "would_fail": { ... }
  },
  "warnings": [ ... ],
  "errors": [ ... ]
}
```

---

## Troubleshooting

### Server Not Running

Make sure your Django server is running:
```bash
python manage.py runserver
```

### Port Different from 8000

If your server runs on a different port, update the URL:
```
http://localhost:YOUR_PORT/api/core/etl/preview/
```

### File Path with Spaces

If using curl, make sure to properly escape the path or use quotes:
- Windows CMD: Use `"path with spaces"`
- PowerShell: Use backticks or double quotes

### Company ID

If you're not sure about the company_id:
1. Check your database: `SELECT id, name FROM multitenancy_company;`
2. Or check existing ETL logs in the database

### Large Response

If the response is very large, you can:
1. Save it to a file (as shown in examples above)
2. Use `jq` (JSON processor) to filter: `cat response.json | jq '.data.would_create_by_row'`
3. Limit preview in Python script

---

## Quick Test Script

Save this as `quick_test.ps1`:

```powershell
$filePath = "C:\Users\DCaff\Nord Ventures\Nord Ventures - Documentos\Clientes\DatBaby\Financeiro\Base de Dados\2025.01.xlsx"
$url = "http://localhost:8000/api/core/etl/preview/"
$companyId = 10

Write-Host "Testing ETL Preview Endpoint..." -ForegroundColor Cyan
Write-Host "File: $filePath" -ForegroundColor Gray
Write-Host "URL: $url" -ForegroundColor Gray
Write-Host "Company ID: $companyId" -ForegroundColor Gray
Write-Host ""

$form = @{
    file = Get-Item -Path $filePath
    company_id = $companyId
}

try {
    Write-Host "Sending request..." -ForegroundColor Yellow
    $response = Invoke-RestMethod -Uri $url -Method Post -Form $form
    
    Write-Host "✓ Success!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Summary:" -ForegroundColor Cyan
    Write-Host "  Duration: $($response.duration_seconds)s"
    Write-Host "  Sheets Processed: $($response.summary.sheets_processed)"
    Write-Host "  Rows Transformed: $($response.summary.total_rows_transformed)"
    
    if ($response.data.would_create_by_row) {
        Write-Host ""
        Write-Host "Excel Rows with Created Records: $($response.data.would_create_by_row.Count)" -ForegroundColor Cyan
    }
    
    $response | ConvertTo-Json -Depth 10 | Out-File -FilePath "etl_response.json" -Encoding UTF8
    Write-Host ""
    Write-Host "Full response saved to: etl_response.json" -ForegroundColor Green
    
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host "Response: $responseBody" -ForegroundColor Red
    }
}
```

Run it:
```powershell
.\quick_test.ps1
```

---

## Checking the Response

The key sections to check:

1. **`data.would_create_by_row`**: Shows records grouped by source Excel row
   - Each item contains the Excel sheet name, row number, and all records created from that row
   - Includes both Transaction and JournalEntry records

2. **`data.would_create`**: Flat list of all records that would be created

3. **`data.would_fail`**: Records that would fail validation (with reasons)

4. **`warnings`**: Non-blocking issues (like missing rules for sheets)

5. **`errors`**: Blocking errors that prevent processing

