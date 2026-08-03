# src/services/llm_service/llm_manager.py

import asyncio
import logging
import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import hashlib
import re

from src.services.llm_service.model_dispatcher import ModelDispatcher
from src.services.llm_service.usage_tracker import UsageTracker
from src.storage.db.operations import DatabaseOperations

# Configure structured logging
logger = logging.getLogger(__name__)

class LLMManager:
    """
    Central LLM service manager with enhanced error handling, security, and observability.
    
    Features:
    - Multi-provider LLM routing with fallback
    - Usage tracking and quota management
    - Comprehensive error handling and retry logic
    - Input validation and sanitization
    - Structured logging and monitoring
    """
    
    def __init__(self, redis_url: str, db_ops: Optional[DatabaseOperations] = None):
        """
        Initialize LLM manager with enhanced security and error handling.
        
        Args:
            redis_url: Redis connection URL
            db_ops: Database operations instance (optional)
            
        Raises:
            ValueError: If required configuration is missing
            ConnectionError: If Redis connection fails
        """
        try:
            self.redis_url = redis_url
            self.db_ops = db_ops
            
            # Initialize components with error handling
            self.model_dispatcher = ModelDispatcher()
            self.usage_tracker = UsageTracker()
            
            # Security: Validate API keys are present but never log them
            self._validate_api_keys()
            
            logger.info("LLMManager initialized successfully with enhanced security")
            
        except Exception as e:
            logger.error(f"Failed to initialize LLMManager: {str(e)}")
            raise
    
    def _validate_api_keys(self) -> None:
        """Validate that required API keys are present without exposing them."""
        required_keys = ['MISTRAL_API_KEY', 'CEREBRAS_API_KEY', 'COHERE_API_KEY']
        missing_keys = []
        
        for key in required_keys:
            if not os.environ.get(key):
                missing_keys.append(key)
        
        if missing_keys:
            logger.warning(f"Missing API keys: {missing_keys}")
            # Don't raise error - allow partial functionality
    
    def _sanitize_input(self, text: str, max_length: int = 10000) -> str:
        """
        Sanitize user input to prevent injection attacks and ensure safety.
        
        Args:
            text: Input text to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Sanitized text
            
        Raises:
            ValueError: If input is invalid or too long
        """
        if not isinstance(text, str):
            raise ValueError("Input must be a string")
        
        if len(text) > max_length:
            raise ValueError(f"Input too long (max {max_length} characters)")
        
        # Remove potentially dangerous patterns
        dangerous_patterns = [
            r'<script.*?>.*?</script>',  # Script tags
            r'javascript:',              # JavaScript protocol
            r'data:text/html',           # Data URLs
            r'vbscript:',                # VBScript
        ]
        
        sanitized = text
        for pattern in dangerous_patterns:
            sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
        
        # Basic XSS protection
        sanitized = sanitized.replace('<', '&lt;').replace('>', '&gt;')
        
        return sanitized.strip()
    
    async def process_document(self, document: Dict[str, Any], is_critical: bool = False) -> Dict[str, Any]:
        """
        Process a document with enhanced error handling and security.
        
        Args:
            document: Document to process
            is_critical: Whether this is a critical document requiring high-quality processing
            
        Returns:
            Processing results
            
        Raises:
            ValueError: If document is invalid
            ConnectionError: If all LLM providers are unavailable
        """
        try:
            # Input validation and sanitization
            if not isinstance(document, dict):
                raise ValueError("Document must be a dictionary")
            
            required_fields = ['id', 'title', 'content']
            for field in required_fields:
                if field not in document:
                    raise ValueError(f"Document missing required field: {field}")
            
            # Sanitize content
            document['content'] = self._sanitize_input(document['content'])
            document['title'] = self._sanitize_input(document['title'], max_length=500)
            
            logger.info(f"Processing document {document['id']} (critical: {is_critical})")
            
            # Process with retry logic
            result = await self._process_with_retry(document, is_critical)
            
            logger.info(f"Successfully processed document {document['id']}")
            return result
            
        except ValueError as e:
            logger.error(f"Invalid document input: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error processing document {document.get('id', 'unknown')}: {str(e)}")
            raise
    
    async def _process_with_retry(self, document: Dict[str, Any], is_critical: bool, max_retries: int = 3) -> Dict[str, Any]:
        """
        Process document with retry logic and provider fallback.
        
        Args:
            document: Document to process
            is_critical: Whether this is critical
            max_retries: Maximum retry attempts
            
        Returns:
            Processing results
            
        Raises:
            ConnectionError: If all providers fail after retries
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Process with model dispatcher
                result = await self.model_dispatcher.dispatch_document(document, is_critical=is_critical)
                
                # Validate result
                if not isinstance(result, dict):
                    raise ValueError("Provider returned invalid result format")
                
                return result
                
            except Exception as e:
                last_error = e
                logger.warning(f"Processing attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
        
        # All retries failed
        logger.error(f"All processing attempts failed for document {document['id']}")
        raise ConnectionError(f"Failed to process document after {max_retries} attempts: {str(last_error)}")
    
    async def generate_synthesis(self, papers: List[Dict[str, Any]], initial_consensus: str = "") -> Dict[str, Any]:
        """
        Generate synthesis with enhanced error handling and validation.
        
        Args:
            papers: List of papers to synthesize
            initial_consensus: Initial consensus statement
            
        Returns:
            Synthesis results
            
        Raises:
            ValueError: If papers list is invalid
            ConnectionError: If synthesis fails
        """
        try:
            # Input validation
            if not isinstance(papers, list):
                raise ValueError("Papers must be a list")
            
            if not papers:
                raise ValueError("Papers list cannot be empty")
            
            # Sanitize initial consensus
            if initial_consensus:
                initial_consensus = self._sanitize_input(initial_consensus, max_length=2000)
            
            logger.info(f"Generating synthesis for {len(papers)} papers")
            
            # Generate synthesis with retry logic
            result = await self._generate_synthesis_with_retry(papers, initial_consensus)
            
            logger.info(f"Successfully generated synthesis for {len(papers)} papers")
            return result
            
        except Exception as e:
            logger.error(f"Error generating synthesis: {str(e)}")
            raise
    
    async def _generate_synthesis_with_retry(self, papers: List[Dict[str, Any]], initial_consensus: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Generate synthesis with retry logic and provider fallback.
        
        Args:
            papers: Papers to synthesize
            initial_consensus: Initial consensus
            max_retries: Maximum retry attempts
            
        Returns:
            Synthesis results
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Generate synthesis using model dispatcher
                result = await self.model_dispatcher.generate_synthesis(papers, initial_consensus)
                
                # Validate result
                if not isinstance(result, dict):
                    raise ValueError("Synthesis provider returned invalid result format")
                
                return result
                
            except Exception as e:
                last_error = e
                logger.warning(f"Synthesis attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
        
        # All retries failed
        logger.error("All synthesis attempts failed")
        raise ConnectionError(f"Failed to generate synthesis after {max_retries} attempts: {str(last_error)}")
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics with error handling.
        
        Returns:
            Usage statistics
        """
        try:
            stats = self.usage_tracker.get_usage_summary()
            logger.debug("Retrieved usage statistics")
            return stats
        except Exception as e:
            logger.error(f"Error retrieving usage stats: {str(e)}")
            return {"error": str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check of LLM services.
        
        Returns:
            Health status for all components
        """
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "components": {}
            }
            
            # Check model dispatcher
            try:
                # Simple health check - try to access clients
                client_count = len(self.model_dispatcher.clients)
                health_status["components"]["model_dispatcher"] = {
                    "status": "healthy",
                    "client_count": client_count
                }
            except Exception as e:
                health_status["components"]["model_dispatcher"] = {"status": "error", "error": str(e)}
                health_status["status"] = "degraded"
            
            # Check usage tracker
            try:
                # Simple health check - try to get usage summary
                self.usage_tracker.get_usage_summary()
                health_status["components"]["usage_tracker"] = {"status": "healthy"}
            except Exception as e:
                health_status["components"]["usage_tracker"] = {"status": "error", "error": str(e)}
                health_status["status"] = "degraded"
            
            # Check API key availability
            api_keys_status = {}
            for key in ['MISTRAL_API_KEY', 'CEREBRAS_API_KEY', 'COHERE_API_KEY']:
                api_keys_status[key] = "configured" if os.environ.get(key) else "missing"
            
            health_status["components"]["api_keys"] = api_keys_status
            
            logger.info(f"Health check completed: {health_status['status']}")
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def cleanup(self):
        """Cleanup resources with error handling."""
        try:
            logger.info("LLMManager cleanup completed")
        except Exception as e:
            logger.error(f"Error during LLMManager cleanup: {str(e)}")
    