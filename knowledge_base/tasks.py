"""
Celery tasks for knowledge base document indexing.
"""
import logging
import tempfile
import os
from celery import shared_task
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .models import KnowledgeBase, KnowledgeDocument
from .services.gemini_service import GeminiFileSearchService, MAX_FILE_SIZE_BYTES

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def index_document_task(self, knowledge_document_id: int):
    """
    Async task to index a document into Gemini File Search Store.
    
    EXTRACT: Get file from source_document or temp upload
    TRANSFORM: Validate, normalize metadata
    LOAD: Upload to Gemini and index
    
    Args:
        knowledge_document_id: ID of KnowledgeDocument to index
    """
    try:
        doc = KnowledgeDocument.objects.get(id=knowledge_document_id)
        doc.status = 'indexing'
        doc.save(update_fields=['status'])
        
        # Get knowledge base and Gemini service
        kb = doc.knowledge_base
        service = GeminiFileSearchService()
        
        # EXTRACT: Get file
        file_obj = None
        temp_file_path = None
        should_delete_temp = False
        
        try:
            # Option 1: Use source_document if available
            if doc.source_document and doc.source_document.file:
                file_obj = doc.source_document.file
                file_obj.open('rb')
            else:
                # Option 2: File should have been uploaded directly
                # For now, we'll need the file to be available via a temp path
                # In a real implementation, you might store the file temporarily
                raise ValueError("No file available for indexing. Upload file first.")
            
            # TRANSFORM: Prepare metadata
            file_size = getattr(file_obj, 'size', None)
            if file_size is None:
                if hasattr(file_obj, 'seek'):
                    file_obj.seek(0, 2)
                    file_size = file_obj.tell()
                    file_obj.seek(0)
                else:
                    file_size = 0
            
            # Validate file size
            if file_size > MAX_FILE_SIZE_BYTES:
                raise ValueError(
                    f"File size ({file_size / 1024 / 1024:.2f} MB) exceeds "
                    f"maximum allowed size (20 MB)"
                )
            
            # Update metadata
            doc.metadata.update({
                'file_size': file_size,
                'mime_type': getattr(file_obj, 'content_type', 'application/pdf'),
            })
            
            # LOAD: Upload and index to Gemini
            display_name = f"{kb.name}_{doc.filename}"
            gemini_doc_name = service.upload_and_index_doc(
                store_name=kb.gemini_store_name,
                file_path_or_obj=file_obj,
                display_name=display_name,
                metadata=doc.metadata
            )
            
            # Update document status
            doc.gemini_doc_name = gemini_doc_name
            doc.status = 'ready'
            doc.error = None
            doc.save(update_fields=['status', 'gemini_doc_name', 'error', 'metadata'])
            
            logger.info(f"Successfully indexed document {doc.id}: {doc.filename}")
            
        except Exception as e:
            error_msg = str(e)
            doc.status = 'failed'
            doc.error = error_msg
            doc.save(update_fields=['status', 'error'])
            logger.error(f"Failed to index document {doc.id}: {error_msg}")
            raise
        
        finally:
            # Clean up file handles
            if file_obj and hasattr(file_obj, 'close'):
                try:
                    file_obj.close()
                except Exception:
                    pass
            if temp_file_path and should_delete_temp and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
                    
    except KnowledgeDocument.DoesNotExist:
        logger.error(f"KnowledgeDocument {knowledge_document_id} not found")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in index_document_task: {e}")
        raise


@shared_task
def import_existing_documents_task(knowledge_base_id: int, document_ids: list):
    """
    Batch import existing npl.Document records into a knowledge base.
    
    Args:
        knowledge_base_id: ID of KnowledgeBase
        document_ids: List of npl.Document IDs to import
    """
    try:
        kb = KnowledgeBase.objects.get(id=knowledge_base_id)
        from npl.models import Document as NPLDocument
        
        imported_count = 0
        for doc_id in document_ids:
            try:
                npl_doc = NPLDocument.objects.get(id=doc_id)
                
                # Create KnowledgeDocument
                kb_doc = KnowledgeDocument.objects.create(
                    knowledge_base=kb,
                    source_document=npl_doc,
                    filename=npl_doc.file_name or f"document_{doc_id}",
                    company=kb.company,
                    metadata={
                        'mime_type': npl_doc.mime_type,
                        'num_pages': npl_doc.num_pages,
                        'doc_type': npl_doc.doc_type,
                    }
                )
                
                # Queue indexing task
                index_document_task.delay(kb_doc.id)
                imported_count += 1
                
            except NPLDocument.DoesNotExist:
                logger.warning(f"NPL Document {doc_id} not found, skipping")
            except Exception as e:
                logger.error(f"Failed to import document {doc_id}: {e}")
        
        logger.info(f"Imported {imported_count} documents into knowledge base {kb.id}")
        return {'imported': imported_count, 'total': len(document_ids)}
        
    except KnowledgeBase.DoesNotExist:
        logger.error(f"KnowledgeBase {knowledge_base_id} not found")
        raise
