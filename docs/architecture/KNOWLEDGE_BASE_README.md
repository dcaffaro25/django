# Knowledge Base (NotebookLM-like) Feature

A complete ETL + document Q&A application using Google's Gemini File Search Store API.

## Features

- **Knowledge Bases**: Create and manage multiple knowledge bases per tenant
- **Document Ingestion**: Upload files or import existing documents from the `npl` app
- **Indexing**: Automatic indexing into Gemini File Search Store with status tracking
- **Q&A**: Ask questions against knowledge bases with citations and grounding
- **Feedback**: Capture user feedback on answers (thumbs up/down, comments, missing info flag)

## Setup

### Prerequisites

- Django 5.0+
- Python 3.8+
- Google Gemini API key

### Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   # OR
   export GOOGLE_API_KEY="your-api-key-here"
   ```

3. **Run migrations:**
   ```bash
   python manage.py makemigrations knowledge_base
   python manage.py migrate
   ```

### Configuration

The app is already added to `INSTALLED_APPS` in `nord_backend/settings.py`.

## API Endpoints

All endpoints are tenant-scoped and require authentication (Token or Session).

### Knowledge Bases

- `POST /{tenant}/api/knowledge-bases/` - Create a new knowledge base
  ```json
  {
    "name": "My Knowledge Base"
  }
  ```

- `GET /{tenant}/api/knowledge-bases/` - List all knowledge bases

- `GET /{tenant}/api/knowledge-bases/{id}/` - Get knowledge base details

- `PUT/PATCH /{tenant}/api/knowledge-bases/{id}/` - Update knowledge base

- `DELETE /{tenant}/api/knowledge-bases/{id}/` - Delete knowledge base

### Documents

- `POST /{tenant}/api/knowledge-bases/{id}/documents/` - Upload/import documents
  ```bash
  # Upload file
  curl -X POST \
    -H "Authorization: Token YOUR_TOKEN" \
    -F "file=@document.pdf" \
    http://localhost:8000/{tenant}/api/knowledge-bases/1/documents/
  
  # Import existing npl.Document
  curl -X POST \
    -H "Authorization: Token YOUR_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"source_document_id": 123}' \
    http://localhost:8000/{tenant}/api/knowledge-bases/1/documents/
  ```

- `GET /{tenant}/api/documents/?knowledge_base={id}` - List documents with status

### Q&A

- `POST /{tenant}/api/knowledge-bases/{id}/ask/` - Ask a question
  ```bash
  curl -X POST \
    -H "Authorization: Token YOUR_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"question": "What is the main topic?"}' \
    http://localhost:8000/{tenant}/api/knowledge-bases/1/ask/
  ```
  
  Response:
  ```json
  {
    "answer_id": 1,
    "answer_text": "The main topic is...",
    "citations": [
      {
        "document_name": "document.pdf",
        "uri_or_store_ref": "files/123456",
        "page": 1,
        "excerpt": "Relevant excerpt..."
      }
    ],
    "grounding_metadata": {...}
  }
  ```

### Feedback

- `POST /{tenant}/api/answers/{id}/feedback/` - Submit feedback
  ```json
  {
    "rating": "up",
    "comment": "Very helpful!",
    "missing_info": false
  }
  ```

## UI

Access the web interface at:
```
http://localhost:8000/{tenant}/knowledge-base/
```

The UI provides:
- Knowledge base selection/creation
- File upload
- Document list with status
- Question input
- Answer display with citations
- Feedback buttons

## Background Jobs

Document indexing runs asynchronously via Celery:

```bash
# Start Celery worker (if Redis is configured)
celery -A nord_backend worker --loglevel=info

# If Redis is not configured, tasks run synchronously
```

## ETL Semantics

The implementation follows explicit ETL patterns:

- **EXTRACT**: Accept file uploads or reference existing `npl.Document` records
- **TRANSFORM**: Validate file size (max 20MB), normalize metadata
- **LOAD**: Upload to Gemini File Search Store and index

See `knowledge_base/services/gemini_service.py` for implementation details.

## File Size Limits

- Maximum file size: **20 MB** (Gemini File Search Store limit)
- Files exceeding this limit are rejected with a clear error message

## Error Handling

- **Missing API Key**: Application startup will fail with clear error message
- **Oversized Files**: Returns 400 error with descriptive message
- **Gemini API Failures**: Document status set to 'failed' with error stored in `error` field

## Deployment

### Railway

1. **Set environment variable:**
   ```
   GEMINI_API_KEY=your-api-key
   ```

2. **Deploy:**
   - Push to Railway-connected repository
   - Railway will automatically detect Django and run migrations

3. **Verify:**
   - Check logs for any startup errors
   - Test API endpoints

### Alternative: Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "nord_backend.wsgi:application", "--bind", "0.0.0.0:8000"]
```

## Testing

### Manual QA Checklist

1. **Upload Documents:**
   - [ ] Upload 2+ PDF documents
   - [ ] Verify documents show as "queued" then "indexing" then "ready"
   - [ ] Check document list shows correct status

2. **Ask Questions:**
   - [ ] Ask a question whose answer is in the documents
   - [ ] Verify response includes `answer_text`, `citations`, and `grounding_metadata`
   - [ ] Ask a question not in the documents
   - [ ] Verify response indicates information not found

3. **Feedback:**
   - [ ] Submit thumbs up feedback
   - [ ] Submit thumbs down with comment
   - [ ] Verify feedback is stored and linked to answer

4. **Error Cases:**
   - [ ] Upload file > 20MB → should get 400 error
   - [ ] Ask question on empty KB → should get appropriate error
   - [ ] Missing API key → should fail at startup

## Architecture

- **Models**: `KnowledgeBase`, `KnowledgeDocument`, `Answer`, `AnswerFeedback`
- **Service**: `GeminiFileSearchService` - Wrapper for Gemini File Search Store API
- **Tasks**: Celery tasks for async document indexing
- **Views**: DRF ViewSets with custom actions
- **UI**: Single Django template page

## Integration with Existing Apps

- **Multitenancy**: All models extend `TenantAwareBaseModel` for automatic tenant scoping
- **Documents**: Can import existing `npl.Document` records
- **Feedback**: Extends feedback patterns from `feedback` app

## Troubleshooting

### Documents stuck in "indexing" status

- Check Celery worker logs
- Verify Gemini API key is valid
- Check file size and format

### API returns 401 Unauthorized

- Ensure you're using the correct tenant subdomain in URL
- Verify authentication token is valid

### Gemini API errors

- Check API key is set correctly
- Verify API quota/limits
- Check network connectivity

## References

- [Google Gemini API Documentation](https://ai.google.dev/docs)
- [Gemini File Search Store](https://ai.google.dev/docs/file_search)
- Reference implementation: https://drlee.io/build-your-own-notebooklm-clone-in-30-minutes-using-googles-gemini-api-and-deploy-it-for-free-fa0d68ee0a86

