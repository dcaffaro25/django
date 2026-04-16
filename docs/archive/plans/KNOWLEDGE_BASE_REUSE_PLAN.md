# Knowledge Base (NotebookLM-like) Feature - Reuse Plan

## Architecture Decision
**Create a new Django app: `knowledge_base`**
- Standalone app for NotebookLM-like Q&A functionality
- Integrates with existing multitenancy, feedback, and document infrastructure
- Uses Gemini File Search Store API for document indexing and retrieval

## Reuse Plan

### 1. Document Handling
**Reuse:**
- `npl.models.Document` - Existing document model with file storage
- `npl.utils.extract_text_from_pdf_fileobj()` - PDF text extraction utility
- File upload patterns from `npl.views.DocumentUploadView`

**Extend:**
- Create `knowledge_base.models.KnowledgeDocument` that references `npl.models.Document` (optional FK)
- Support importing existing `npl.Document` records OR direct file uploads
- Reuse file validation and text extraction logic

### 2. Multitenancy
**Reuse:**
- `multitenancy.models.TenantAwareBaseModel` - Base class for tenant-scoped models
- `multitenancy.middleware.TenantMiddleware` - Tenant extraction from URL
- `multitenancy.mixins.ScopedQuerysetMixin` - Automatic queryset filtering

**Apply:**
- All Knowledge Base models inherit from `TenantAwareBaseModel`
- Use `company` FK for tenant isolation
- URL routing: `/{tenant_subdomain}/api/knowledge-bases/...`

### 3. Feedback System
**Reuse:**
- `feedback.models.JudgmentSession` - Session tracking
- `feedback.models.UserJudgment` - User feedback records

**Extend:**
- Create `knowledge_base.models.AnswerFeedback` model
  - Links to `knowledge_base.models.Answer`
  - Fields: `rating` (thumbs up/down), `comment`, `missing_info` (boolean)
  - Reuse session pattern from existing feedback app

### 4. Background Tasks
**Reuse:**
- `celery` configuration from `nord_backend.celery`
- Task patterns from `npl.tasks` (async document processing)

**Create:**
- `knowledge_base.tasks.index_document_task` - Async Gemini File Search indexing
- `knowledge_base.tasks.import_existing_documents_task` - Batch import from npl.Document

### 5. API Structure
**Reuse:**
- DRF patterns from existing apps (`accounting`, `npl`, `feedback`)
- Serializer patterns and ViewSet conventions
- URL routing with tenant prefix

**Create:**
- `knowledge_base.views.KnowledgeBaseViewSet`
- `knowledge_base.views.KnowledgeDocumentViewSet`
- `knowledge_base.views.AskView` (custom action)
- `knowledge_base.views.AnswerFeedbackView`

### 6. File Storage
**Reuse:**
- Django's default file storage (already configured)
- File cleanup patterns (temporary files deleted after processing)

**Note:**
- Gemini File Search stores files in Google's infrastructure
- We only need to upload files temporarily, then delete after indexing
- Store file metadata, not the files themselves (unless `store_file=True`)

## New Components to Create

### Models (`knowledge_base/models.py`)
1. `KnowledgeBase` - Tenant-scoped knowledge base (maps to one Gemini File Search Store)
2. `KnowledgeDocument` - Document in a knowledge base (tracks indexing status)
3. `Answer` - Q&A response record (stores question, answer, citations, grounding metadata)

### Services (`knowledge_base/services/gemini_service.py`)
1. `GeminiFileSearchService` - Wrapper for Gemini File Search Store API
   - `create_store(display_name)` - Create a new File Search Store
   - `upload_and_index_doc(store_name, file_path, display_name)` - Upload and index document
   - `ask(store_name, question)` - Query with grounding

### Tasks (`knowledge_base/tasks.py`)
1. `index_document_task` - Async document indexing
2. `import_existing_documents_task` - Batch import from npl.Document

### Views (`knowledge_base/views.py`)
1. DRF ViewSets for CRUD operations
2. Custom action: `ask` on KnowledgeBaseViewSet
3. Feedback endpoint for answers

### Serializers (`knowledge_base/serializers.py`)
1. `KnowledgeBaseSerializer`
2. `KnowledgeDocumentSerializer`
3. `AskSerializer` (request/response)
4. `AnswerFeedbackSerializer`

### UI (`knowledge_base/templates/knowledge_base/index.html`)
- Single Django template page with:
  - File upload form
  - Document list with status
  - Question input
  - Answer display with citations
  - Feedback buttons

## Dependencies to Add
- `google-generativeai` - Official Gemini SDK

## File Structure
```
knowledge_base/
├── __init__.py
├── apps.py
├── admin.py
├── models.py
├── serializers.py
├── views.py
├── urls.py
├── tasks.py
├── services/
│   └── gemini_service.py
├── templates/
│   └── knowledge_base/
│       └── index.html
└── migrations/
    └── 0001_initial.py
```

