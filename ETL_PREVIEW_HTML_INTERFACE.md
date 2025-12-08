# ETL Preview HTML Interface

A user-friendly web interface for testing the ETL preview endpoint directly in your browser.

## Access URL

**Local Server:**
```
http://localhost:8000/etl/preview/
```

**Production/Staging:**
```
http://your-server-url/etl/preview/
```

## Features

✅ **File Upload Form** - Easy drag-and-drop or browse to select Excel files  
✅ **Company Selection** - Dropdown with all available companies  
✅ **AJAX Processing** - No page reload, smooth user experience  
✅ **Tabbed Results View** - Organized display of results:
   - **Summary** - Overview of processing results
   - **Grouped by Row** - Records organized by source Excel row (NEW!)
   - **All Records** - Flat list of all records
   - **Failed Rows** - Rows that would fail validation
   - **Raw JSON** - Full JSON response for debugging

✅ **Beautiful UI** - Modern, clean interface  
✅ **Error Handling** - Clear error messages and warnings  
✅ **Loading Indicators** - Visual feedback during processing

## How to Use

1. **Start your Django server:**
   ```bash
   python manage.py runserver
   ```

2. **Open your browser and navigate to:**
   ```
   http://localhost:8000/etl/preview/
   ```

3. **Select a Company** from the dropdown

4. **Choose an Excel file** to upload

5. **Click "Preview Transformation"**

6. **View Results** in the organized tabs:
   - See summary statistics
   - Browse records grouped by Excel row
   - Check for warnings and errors
   - Review the full JSON response if needed

## What You'll See

### Summary Tab
- Processing duration
- File name
- Sheets found/processed/skipped
- Total rows transformed
- Warnings and errors (if any)

### Grouped by Row Tab (NEW!)
- Each Excel row shows:
  - Row number and sheet name
  - All Transaction records created from that row
  - All JournalEntry records created from that row (via IntegrationRules)
  - Complete data for each record

### All Records Tab
- Flat table view of all records that would be created
- Organized by model type (Transaction, JournalEntry, etc.)

### Failed Rows Tab
- List of rows that would fail validation
- Reason for failure
- Row data for debugging

### Raw JSON Tab
- Complete JSON response
- Useful for debugging or API integration

## Example

After uploading your file, you'll see something like:

```
Row 115 (Base Ajustada):
  - Transaction: 1 record(s)
  - JournalEntry: 2 record(s)
  Total: 3 record(s) created from this Excel row
```

This shows that Excel row 115 created:
- 1 Transaction record
- 2 JournalEntry records (from IntegrationRules)

## Technical Details

- **Endpoint:** `/etl/preview/`
- **Method:** GET (form) / POST (process)
- **View Class:** `ETLPreviewHTMLView`
- **Template:** `multitenancy/templates/multitenancy/etl_preview.html`
- **No Authentication Required** (when AUTH_OFF=True in settings)

## Notes

- The preview does NOT commit any data to the database
- All operations run in a transaction that gets rolled back
- Large files may take some time to process
- Results are displayed in your browser - no download required

## Troubleshooting

**404 Error:**
- Make sure the server is running
- Check the URL is correct: `/etl/preview/`

**No Companies in Dropdown:**
- Make sure you have companies in the database
- Companies marked as `is_deleted=True` won't appear

**File Upload Fails:**
- Check file size limits
- Ensure file is a valid Excel file (.xlsx, .xls)
- Check server logs for detailed errors

**Processing Takes Too Long:**
- Large files take time
- Check browser console for errors
- Check server logs for processing details

