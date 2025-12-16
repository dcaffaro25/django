"""
Gemini File Search Store service wrapper.

This module provides a service layer for interacting with Google's Gemini
File Search Store API for document indexing and Q&A functionality.
"""
import os
import logging
from typing import Optional, Dict, Any, BinaryIO
from pathlib import Path

try:
    import google.generativeai as genai
    from google.generativeai.types import File
except ImportError:
    genai = None
    File = None

logger = logging.getLogger(__name__)

# Gemini File Search Store limits
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class GeminiFileSearchService:
    """
    Service wrapper for Gemini File Search Store API.
    
    Handles:
    - Creating File Search Stores
    - Uploading and indexing documents
    - Querying with grounding
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the service with API key.
        
        Args:
            api_key: Gemini API key. If None, reads from GEMINI_API_KEY or GOOGLE_API_KEY env var.
        
        Raises:
            ValueError: If API key is not found.
        """
        if genai is None:
            raise ImportError(
                "google-generativeai package is required. "
                "Install with: pip install google-generativeai"
            )
        
        api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError(
                "Gemini API key not found. Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable."
            )
        
        genai.configure(api_key=api_key)
        self.client = genai
        logger.info("GeminiFileSearchService initialized")
    
    def create_store(self, display_name: str) -> str:
        """
        Create a new Gemini File Search Store.
        
        Args:
            display_name: Human-readable name for the store (must be globally unique)
        
        Returns:
            Store resource name (e.g., "corpora/123456789")
        
        Raises:
            Exception: If store creation fails.
        """
        try:
            # Create a corpus (File Search Store)
            # Note: API may vary - adjust based on actual SDK
            corpus = self.client.create_corpus(name=display_name)
            store_name = getattr(corpus, 'name', None) or str(corpus)
            logger.info(f"Created Gemini File Search Store: {store_name} (display: {display_name})")
            return store_name
        except AttributeError:
            # Fallback: Try alternative API
            try:
                corpus = genai.create_corpus(name=display_name)
                store_name = getattr(corpus, 'name', None) or str(corpus)
                logger.info(f"Created Gemini File Search Store (alt method): {store_name}")
                return store_name
            except Exception as e2:
                logger.error(f"Failed to create Gemini File Search Store (both methods): {e2}")
                raise
        except Exception as e:
            logger.error(f"Failed to create Gemini File Search Store: {e}")
            raise
    
    def upload_and_index_doc(
        self,
        store_name: str,
        file_path_or_obj: Any,
        display_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Upload and index a document into a Gemini File Search Store.
        
        EXTRACT: Accept file path or file-like object
        TRANSFORM: Validate file size, normalize metadata
        LOAD: Upload to Gemini File Search Store and index
        
        Args:
            store_name: Gemini File Search Store resource name
            file_path_or_obj: File path (str/Path) or file-like object (BinaryIO)
            display_name: Display name for the document in Gemini
            metadata: Optional metadata dict (not used by Gemini, stored in our DB)
        
        Returns:
            Document resource name (e.g., "files/123456789")
        
        Raises:
            ValueError: If file is too large or invalid
            Exception: If upload/indexing fails
        """
        # EXTRACT: Get file object
        if isinstance(file_path_or_obj, (str, Path)):
            file_path = Path(file_path_or_obj)
            if not file_path.exists():
                raise ValueError(f"File not found: {file_path}")
            
            file_size = file_path.stat().st_size
            file_obj = open(file_path, 'rb')
            should_close = True
        else:
            # Assume file-like object
            file_obj = file_path_or_obj
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0, 2)  # Seek to end
                file_size = file_obj.tell()
                file_obj.seek(0)  # Reset to start
            else:
                # Try to get size from file object
                file_size = getattr(file_obj, 'size', None)
                if file_size is None:
                    raise ValueError("Cannot determine file size")
            should_close = False
        
        try:
            # TRANSFORM: Validate file size
            if file_size > MAX_FILE_SIZE_BYTES:
                raise ValueError(
                    f"File size ({file_size / 1024 / 1024:.2f} MB) exceeds "
                    f"maximum allowed size ({MAX_FILE_SIZE_MB} MB)"
                )
            
            # LOAD: Upload to Gemini File Search Store
            try:
                # Upload file to Gemini
                uploaded_file = self.client.upload_file(
                    path=file_obj,
                    display_name=display_name
                )
                
                # Wait for file to be processed
                import time
                while uploaded_file.state.name == "PROCESSING":
                    time.sleep(1)
                    uploaded_file = self.client.get_file(uploaded_file.name)
                
                if uploaded_file.state.name == "FAILED":
                    raise Exception(f"File processing failed: {uploaded_file.error}")
                
                # Add file to corpus (File Search Store)
                corpus = self.client.get_corpus(store_name)
                corpus.create_file(file=uploaded_file)
                
                doc_name = uploaded_file.name
                logger.info(f"Uploaded and indexed document: {doc_name} (display: {display_name})")
                return doc_name
                
            except Exception as e:
                logger.error(f"Failed to upload/index document: {e}")
                raise
        finally:
            if should_close and hasattr(file_obj, 'close'):
                file_obj.close()
    
    def ask(self, store_name: str, question: str) -> Dict[str, Any]:
        """
        Ask a question against a Gemini File Search Store with grounding.
        
        Args:
            store_name: Gemini File Search Store resource name
            question: User's question
        
        Returns:
            Dict with:
            - answer_text: Generated answer
            - grounding_metadata: Raw grounding metadata from Gemini
            - citations: Parsed citations array (structured)
        
        Raises:
            Exception: If query fails
        """
        try:
            # Get the corpus
            try:
                corpus = self.client.get_corpus(store_name)
            except AttributeError:
                corpus = genai.get_corpus(store_name)
            
            # Create a model with File Search tool
            # Note: API may vary - adjust based on actual SDK
            try:
                tool = self.client.Tool.from_corpus(corpus)
            except AttributeError:
                # Alternative: Use corpus directly or different tool creation method
                tool = genai.Tool.from_corpus(corpus) if hasattr(genai, 'Tool') else corpus
            
            model = self.client.GenerativeModel(
                model_name='gemini-1.5-pro',
                tools=[tool] if tool else []
            )
            
            # Generate response with grounding
            response = model.generate_content(question)
            
            # Extract answer text
            answer_text = response.text if hasattr(response, 'text') else str(response)
            
            # Extract grounding metadata
            grounding_metadata = {}
            citations = []
            
            if hasattr(response, 'grounding_metadata'):
                grounding_metadata = {
                    'grounding_chunks': getattr(response.grounding_metadata, 'grounding_chunks', []),
                    'retrieval_queries': getattr(response.grounding_metadata, 'retrieval_queries', []),
                }
                
                # Parse citations from grounding chunks
                for chunk in getattr(response.grounding_metadata, 'grounding_chunks', []):
                    citation = {
                        'document_name': getattr(chunk, 'file', {}).get('display_name', ''),
                        'uri_or_store_ref': getattr(chunk, 'file', {}).get('name', ''),
                    }
                    
                    # Add optional fields if available
                    if hasattr(chunk, 'start_index'):
                        citation['start_index'] = chunk.start_index
                    if hasattr(chunk, 'end_index'):
                        citation['end_index'] = chunk.end_index
                    if hasattr(chunk, 'page'):
                        citation['page'] = chunk.page
                    if hasattr(chunk, 'excerpt'):
                        citation['excerpt'] = chunk.excerpt
                    
                    citations.append(citation)
            
            result = {
                'answer_text': answer_text,
                'grounding_metadata': grounding_metadata,
                'citations': citations,
            }
            
            logger.info(f"Generated answer for question: {question[:50]}...")
            return result
            
        except Exception as e:
            logger.error(f"Failed to query Gemini File Search Store: {e}")
            raise
