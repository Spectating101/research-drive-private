import logging
import re
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime
import hashlib
import os

import numpy as np
from langchain.embeddings import OpenAIEmbeddings
import faiss
import pickle
from pathlib import Path

# Configure structured logging
logger = logging.getLogger(__name__)

class EmbeddingManager:
    """
    Enhanced embedding manager with comprehensive error handling, security, and observability.
    
    Features:
    - Secure embedding creation and storage
    - Input validation and sanitization
    - Comprehensive error handling and retry logic
    - Structured logging and monitoring
    - Protection against injection attacks
    - Vector similarity search with FAISS
    """
    
    def __init__(self, cache_dir: Optional[str] = None, max_text_length: int = 8000):
        """
        Initialize embedding manager with enhanced security and error handling.
        
        Args:
            cache_dir: Directory for caching embeddings and indices
            max_text_length: Maximum allowed text length for embeddings
            
        Raises:
            ValueError: If parameters are invalid
            ConnectionError: If embedding service initialization fails
        """
        try:
            if max_text_length <= 0:
                raise ValueError("max_text_length must be positive")
            
            logger.info("Initializing EmbeddingManager with enhanced security")
            
            # Initialize embeddings service with error handling
            try:
                self.embeddings = OpenAIEmbeddings()
                logger.info("Embeddings service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize embeddings service: {str(e)}")
                raise ConnectionError(f"Embeddings service initialization failed: {str(e)}")
            
            # Set up cache directory
            if cache_dir:
                self.cache_dir = Path(cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Cache directory set to: {self.cache_dir}")
            else:
                self.cache_dir = None
                logger.info("No cache directory specified")
            
            # Initialize index and document map
            self.index = None
            self.document_map = {}
            self.max_text_length = max_text_length
            
            logger.info("EmbeddingManager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize EmbeddingManager: {str(e)}")
            raise
    
    def _validate_text(self, text: str) -> None:
        """
        Validate text input for security and safety.
        
        Args:
            text: Text to validate
            
        Raises:
            ValueError: If text is invalid
        """
        if not isinstance(text, str):
            raise ValueError("Text must be a string")
        
        if not text.strip():
            raise ValueError("Text cannot be empty")
        
        if len(text) > self.max_text_length:
            raise ValueError(f"Text too long (max {self.max_text_length} characters)")
        
        # Check for potentially dangerous content
        dangerous_patterns = [
            r'<script.*?>.*?</script>',  # Script tags
            r'javascript:',              # JavaScript protocol
            r'data:text/html',           # Data URLs
            r'vbscript:',                # VBScript
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                raise ValueError(f"Text contains potentially dangerous patterns: {pattern}")
    
    def _sanitize_text(self, text: str) -> str:
        """
        Sanitize text to prevent injection attacks.
        
        Args:
            text: Text to sanitize
            
        Returns:
            Sanitized text
        """
        # Basic XSS protection
        sanitized = text.replace('<', '&lt;').replace('>', '&gt;')
        
        # Remove null bytes and other control characters
        sanitized = ''.join(char for char in sanitized if ord(char) >= 32 or char in '\n\r\t')
        
        return sanitized.strip()
    
    def _validate_texts_list(self, texts: List[str]) -> None:
        """
        Validate list of texts.
        
        Args:
            texts: List of texts to validate
            
        Raises:
            ValueError: If texts list is invalid
        """
        if not isinstance(texts, list):
            raise ValueError("Texts must be a list")
        
        if not texts:
            raise ValueError("Texts list cannot be empty")
        
        if len(texts) > 1000:  # Reasonable limit
            raise ValueError("Too many texts (max 1000)")
        
        for i, text in enumerate(texts):
            try:
                self._validate_text(text)
            except ValueError as e:
                raise ValueError(f"Invalid text at index {i}: {str(e)}")
    
    async def create_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Create embeddings for a list of texts with enhanced error handling and security.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            Numpy array of embeddings
            
        Raises:
            ValueError: If texts are invalid
            ConnectionError: If embedding creation fails
        """
        try:
            # Input validation and sanitization
            self._validate_texts_list(texts)
            sanitized_texts = [self._sanitize_text(text) for text in texts]
            
            logger.info(f"Creating embeddings for {len(sanitized_texts)} texts")
            
            # Create embeddings with retry logic
            embeddings = await self._create_embeddings_with_retry(sanitized_texts)
            
            # Validate embeddings
            if not isinstance(embeddings, np.ndarray):
                raise ValueError("Embeddings service returned invalid format")
            
            if embeddings.shape[0] != len(sanitized_texts):
                raise ValueError("Number of embeddings doesn't match number of texts")
            
            logger.info(f"Successfully created embeddings with shape {embeddings.shape}")
            return embeddings
            
        except ValueError as e:
            logger.error(f"Invalid input for embedding creation: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating embeddings: {str(e)}")
            raise
    
    async def _create_embeddings_with_retry(self, texts: List[str], max_retries: int = 3) -> np.ndarray:
        """
        Create embeddings with retry logic.
        
        Args:
            texts: List of sanitized texts
            max_retries: Maximum retry attempts
            
        Returns:
            Numpy array of embeddings
            
        Raises:
            ConnectionError: If all retries fail
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Create embeddings with timeout
                embeddings = await asyncio.wait_for(
                    self.embeddings.aembed_documents(texts),
                    timeout=60.0  # 60 second timeout
                )
                return np.array(embeddings)
                
            except asyncio.TimeoutError:
                last_error = ConnectionError("Embedding creation timed out")
                logger.warning(f"Embedding creation attempt {attempt + 1} timed out")
            except Exception as e:
                last_error = e
                logger.warning(f"Embedding creation attempt {attempt + 1} failed: {str(e)}")
            
            if attempt < max_retries - 1:
                # Exponential backoff
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
        
        # All retries failed
        logger.error(f"All embedding creation attempts failed")
        raise ConnectionError(f"Failed to create embeddings after {max_retries} attempts: {str(last_error)}")
    
    async def add_to_index(self, doc_id: str, texts: List[str]) -> bool:
        """
        Add document embeddings to the search index with enhanced error handling and security.
        
        Args:
            doc_id: Document identifier
            texts: List of texts to add
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            ValueError: If inputs are invalid
        """
        try:
            # Input validation
            if not isinstance(doc_id, str) or not doc_id.strip():
                raise ValueError("Document ID must be a non-empty string")
            
            self._validate_texts_list(texts)
            
            logger.info(f"Adding document {doc_id} to search index ({len(texts)} texts)")
            
            # Create embeddings
            embeddings = await self.create_embeddings(texts)
            
            # Initialize index if needed
            if self.index is None:
                try:
                    dimension = embeddings.shape[1]
                    self.index = faiss.IndexFlatL2(dimension)
                    logger.info(f"Initialized FAISS index with dimension {dimension}")
                except Exception as e:
                    logger.error(f"Failed to initialize FAISS index: {str(e)}")
                    return False
            
            # Add to index with error handling
            try:
                self.index.add(embeddings)
            except Exception as e:
                logger.error(f"Failed to add embeddings to FAISS index: {str(e)}")
                return False
            
            # Update document map
            try:
                start_idx = self.index.ntotal - len(texts)
                for i, text in enumerate(texts):
                    self.document_map[start_idx + i] = {
                        "doc_id": doc_id,
                        "chunk_index": i,
                        "text": text,
                        "added_at": datetime.utcnow().isoformat()
                    }
            except Exception as e:
                logger.error(f"Failed to update document map: {str(e)}")
                return False
            
            logger.info(f"Successfully added document {doc_id} to index")
            return True
            
        except ValueError as e:
            logger.error(f"Invalid input for index addition: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error adding document to index: {str(e)}")
            return False
    
    async def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar texts with enhanced error handling and security.
        
        Args:
            query: Search query
            k: Number of results to return
            
        Returns:
            List of search results with scores
            
        Raises:
            ValueError: If query is invalid
        """
        try:
            # Input validation
            self._validate_text(query)
            if not isinstance(k, int) or k <= 0 or k > 100:
                raise ValueError("k must be a positive integer <= 100")
            
            if not self.is_initialized:
                logger.warning("Search index not initialized")
                return []
            
            logger.info(f"Searching for: {query[:50]}... (k={k})")
            
            # Create query embedding with retry logic
            query_embedding = await self._create_query_embedding_with_retry(query)
            
            # Perform search with error handling
            try:
                distances, indices = self.index.search(
                    np.array([query_embedding]), k
                )
            except Exception as e:
                logger.error(f"FAISS search failed: {str(e)}")
                return []
            
            # Prepare results with validation
            results = []
            for distance, idx in zip(distances[0], indices[0]):
                if idx != -1 and idx in self.document_map:  # Valid index
                    doc_info = self.document_map[idx]
                    results.append({
                        "doc_id": doc_info["doc_id"],
                        "chunk_index": doc_info["chunk_index"],
                        "text": doc_info["text"],
                        "score": float(1.0 / (1.0 + distance)),
                        "distance": float(distance),
                        "searched_at": datetime.utcnow().isoformat()
                    })
            
            logger.info(f"Found {len(results)} similar documents")
            return results
            
        except ValueError as e:
            logger.error(f"Invalid search query: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error during search: {str(e)}")
            return []
    
    async def _create_query_embedding_with_retry(self, query: str, max_retries: int = 3) -> List[float]:
        """
        Create query embedding with retry logic.
        
        Args:
            query: Search query
            max_retries: Maximum retry attempts
            
        Returns:
            Query embedding vector
            
        Raises:
            ConnectionError: If all retries fail
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Create query embedding with timeout
                embedding = await asyncio.wait_for(
                    self.embeddings.aembed_query(query),
                    timeout=30.0  # 30 second timeout
                )
                return embedding
                
            except asyncio.TimeoutError:
                last_error = ConnectionError("Query embedding creation timed out")
                logger.warning(f"Query embedding attempt {attempt + 1} timed out")
            except Exception as e:
                last_error = e
                logger.warning(f"Query embedding attempt {attempt + 1} failed: {str(e)}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # Short delay between retries
        
        # All retries failed
        logger.error(f"All query embedding attempts failed")
        raise ConnectionError(f"Failed to create query embedding after {max_retries} attempts: {str(last_error)}")
    
    async def save_index(self, path: Optional[str] = None) -> bool:
        """
        Save the search index to disk with enhanced error handling and security.
        
        Args:
            path: Optional custom save path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not path and not self.cache_dir:
                logger.warning("No save path specified and no cache directory configured")
                return False
            
            if not self.is_initialized:
                logger.warning("No index to save")
                return False
            
            # Determine save path
            if path:
                save_path = Path(path)
                save_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                save_path = self.cache_dir / "embeddings_index"
            
            logger.info(f"Saving index to {save_path}")
            
            # Save FAISS index with error handling
            try:
                faiss.write_index(self.index, str(save_path) + ".faiss")
                logger.info("FAISS index saved successfully")
            except Exception as e:
                logger.error(f"Failed to save FAISS index: {str(e)}")
                return False
            
            # Save document map with error handling
            try:
                with open(str(save_path) + ".docmap", 'wb') as f:
                    pickle.dump(self.document_map, f)
                logger.info("Document map saved successfully")
            except Exception as e:
                logger.error(f"Failed to save document map: {str(e)}")
                # Try to clean up the FAISS file
                try:
                    os.remove(str(save_path) + ".faiss")
                except OSError:
                    pass
                return False
            
            logger.info("Index saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error saving index: {str(e)}")
            return False
    
    async def load_index(self, path: Optional[str] = None) -> bool:
        """
        Load the search index from disk with enhanced error handling and security.
        
        Args:
            path: Optional custom load path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not path and not self.cache_dir:
                logger.warning("No load path specified and no cache directory configured")
                return False
            
            # Determine load path
            if path:
                load_path = Path(path)
            else:
                load_path = self.cache_dir / "embeddings_index"
            
            # Check if files exist
            faiss_path = str(load_path) + ".faiss"
            docmap_path = str(load_path) + ".docmap"
            
            if not os.path.exists(faiss_path) or not os.path.exists(docmap_path):
                logger.warning(f"Index files not found at {load_path}")
                return False
            
            logger.info(f"Loading index from {load_path}")
            
            # Load FAISS index with error handling
            try:
                self.index = faiss.read_index(faiss_path)
                logger.info("FAISS index loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load FAISS index: {str(e)}")
                return False
            
            # Load document map with error handling
            try:
                with open(docmap_path, 'rb') as f:
                    self.document_map = pickle.load(f)
                logger.info("Document map loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load document map: {str(e)}")
                self.index = None  # Reset index
                return False
            
            logger.info(f"Index loaded successfully with {len(self.document_map)} documents")
            return True
            
        except Exception as e:
            logger.error(f"Error loading index: {str(e)}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check of the embedding manager.
        
        Returns:
            Health status
        """
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "components": {}
            }
            
            # Check embeddings service
            try:
                # Simple test embedding
                test_embedding = await asyncio.wait_for(
                    self.embeddings.aembed_query("test"),
                    timeout=10.0
                )
                health_status["components"]["embeddings_service"] = {
                    "status": "healthy",
                    "dimension": len(test_embedding)
                }
            except Exception as e:
                health_status["components"]["embeddings_service"] = {
                    "status": "error",
                    "error": str(e)
                }
                health_status["status"] = "degraded"
            
            # Check index
            if self.is_initialized:
                health_status["components"]["search_index"] = {
                    "status": "healthy",
                    "document_count": len(self.document_map),
                    "index_size": self.index.ntotal
                }
            else:
                health_status["components"]["search_index"] = {
                    "status": "not_initialized"
                }
            
            # Check cache directory
            if self.cache_dir:
                try:
                    cache_writable = os.access(self.cache_dir, os.W_OK)
                    health_status["components"]["cache_directory"] = {
                        "status": "healthy" if cache_writable else "not_writable",
                        "path": str(self.cache_dir),
                        "writable": cache_writable
                    }
                    if not cache_writable:
                        health_status["status"] = "degraded"
                except Exception as e:
                    health_status["components"]["cache_directory"] = {
                        "status": "error",
                        "error": str(e)
                    }
                    health_status["status"] = "degraded"
            
            logger.info(f"Health check completed: {health_status['status']}")
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @property
    def is_initialized(self) -> bool:
        """
        Check if index is initialized.
        
        Returns:
            True if index is initialized, False otherwise
        """
        return self.index is not None and hasattr(self.index, 'ntotal')
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the embedding manager.
        
        Returns:
            Statistics dictionary
        """
        try:
            stats = {
                "index_initialized": self.is_initialized,
                "document_count": len(self.document_map) if self.document_map else 0,
                "cache_directory": str(self.cache_dir) if self.cache_dir else None,
                "max_text_length": self.max_text_length
            }
            
            if self.is_initialized:
                stats.update({
                    "index_size": self.index.ntotal,
                    "index_dimension": self.index.d
                })
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return {"error": str(e)}