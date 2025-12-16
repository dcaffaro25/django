# Knowledge Base API - cURL Examples

## Prerequisites

Set your authentication token and tenant:
```bash
export TOKEN="your-auth-token-here"
export TENANT="your-tenant-subdomain"
export BASE_URL="http://localhost:8000"
```

## Knowledge Base Management

### Create Knowledge Base
```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Knowledge Base"}' \
  $BASE_URL/$TENANT/api/knowledge-bases/
```

**Response:**
```json
{
  "id": 1,
  "name": "My Knowledge Base",
  "gemini_store_name": "corpora/123456789",
  "company": 1,
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-01T12:00:00Z",
  "documents_count": 0
}
```

### List Knowledge Bases
```bash
curl -X GET \
  -H "Authorization: Token $TOKEN" \
  $BASE_URL/$TENANT/api/knowledge-bases/
```

### Get Knowledge Base Details
```bash
curl -X GET \
  -H "Authorization: Token $TOKEN" \
  $BASE_URL/$TENANT/api/knowledge-bases/1/
```

## Document Management

### Upload Document (File Upload)
```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -F "file=@/path/to/document.pdf" \
  -F "filename=My Document" \
  $BASE_URL/$TENANT/api/knowledge-bases/1/documents/
```

**Response:**
```json
{
  "id": 1,
  "knowledge_base": 1,
  "source_document": null,
  "filename": "My Document",
  "status": "queued",
  "error": null,
  "gemini_doc_name": null,
  "metadata": {
    "file_size": 1024000,
    "mime_type": "application/pdf"
  },
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-01T12:00:00Z"
}
```

### Import Existing Document
```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_document_id": 123}' \
  $BASE_URL/$TENANT/api/knowledge-bases/1/documents/
```

### List Documents
```bash
curl -X GET \
  -H "Authorization: Token $TOKEN" \
  "$BASE_URL/$TENANT/api/documents/?knowledge_base=1"
```

**Response:**
```json
[
  {
    "id": 1,
    "knowledge_base": 1,
    "filename": "document.pdf",
    "status": "ready",
    "error": null,
    "gemini_doc_name": "files/987654321",
    "metadata": {...},
    "created_at": "2024-01-01T12:00:00Z"
  }
]
```

## Q&A

### Ask a Question
```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main topic of the documents?"}' \
  $BASE_URL/$TENANT/api/knowledge-bases/1/ask/
```

**Response:**
```json
{
  "answer_id": 1,
  "answer_text": "The main topic of the documents is...",
  "citations": [
    {
      "document_name": "document.pdf",
      "uri_or_store_ref": "files/987654321",
      "start_index": 0,
      "end_index": 100,
      "page": 1,
      "excerpt": "Relevant text excerpt from the document..."
    }
  ],
  "grounding_metadata": {
    "grounding_chunks": [...],
    "retrieval_queries": [...]
  }
}
```

### Ask Question (Not in Documents)
```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the weather today?"}' \
  $BASE_URL/$TENANT/api/knowledge-bases/1/ask/
```

**Response:**
```json
{
  "error": "The information requested is not available in the provided documents."
}
```

## Feedback

### Submit Positive Feedback
```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "answer": 1,
    "rating": "up",
    "comment": "Very helpful answer!",
    "missing_info": false
  }' \
  $BASE_URL/$TENANT/api/answers/1/feedback/
```

### Submit Negative Feedback
```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "answer": 1,
    "rating": "down",
    "comment": "Missing important details",
    "missing_info": true
  }' \
  $BASE_URL/$TENANT/api/answers/1/feedback/
```

**Response:**
```json
{
  "id": 1,
  "answer": 1,
  "rating": "down",
  "comment": "Missing important details",
  "missing_info": true,
  "created_at": "2024-01-01T12:00:00Z"
}
```

## Error Examples

### File Too Large
```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -F "file=@/path/to/large-file.pdf" \
  $BASE_URL/$TENANT/api/knowledge-bases/1/documents/
```

**Response (400):**
```json
{
  "error": "File size (25.5 MB) exceeds maximum allowed size (20 MB)"
}
```

### Missing API Key
If `GEMINI_API_KEY` is not set, the service will fail at startup with:
```
ValueError: Gemini API key not found. Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable.
```

### Empty Knowledge Base
```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Test question"}' \
  $BASE_URL/$TENANT/api/knowledge-bases/1/ask/
```

**Response (400):**
```json
{
  "error": "Knowledge base has no documents indexed yet."
}
```

## Complete Workflow Example

```bash
# 1. Create knowledge base
KB_ID=$(curl -s -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test KB"}' \
  $BASE_URL/$TENANT/api/knowledge-bases/ | jq -r '.id')

# 2. Upload document
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -F "file=@document1.pdf" \
  $BASE_URL/$TENANT/api/knowledge-bases/$KB_ID/documents/

# 3. Wait for indexing (check status)
sleep 10
curl -X GET \
  -H "Authorization: Token $TOKEN" \
  "$BASE_URL/$TENANT/api/documents/?knowledge_base=$KB_ID"

# 4. Ask question
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is this document about?"}' \
  $BASE_URL/$TENANT/api/knowledge-bases/$KB_ID/ask/

# 5. Submit feedback
ANSWER_ID=1  # From previous response
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"answer": '$ANSWER_ID', "rating": "up", "missing_info": false}' \
  $BASE_URL/$TENANT/api/answers/$ANSWER_ID/feedback/
```

