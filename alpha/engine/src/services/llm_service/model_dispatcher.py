# src/services/llm_service/model_dispatcher.py

import json
import os
import logging
import asyncio
import random
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .usage_tracker import UsageTracker
from .api_clients.mistral_client import MistralClient
from .api_clients.cerebras_client import CerebrasClient
from .api_clients.cohere_client import CohereClient

logger = logging.getLogger(__name__)

class ModelDispatcher:
    """
    Routes documents to appropriate LLM service with enhanced error handling, security, and observability.
    
    Features:
    - Multi-provider LLM routing with intelligent fallback
    - Usage tracking and quota management
    - Comprehensive error handling and retry logic
    - Input validation and sanitization
    - Structured logging and monitoring
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize with enhanced security and error handling.
        
        Args:
            config_path: Optional custom config path
            
        Raises:
            ValueError: If configuration is invalid
            FileNotFoundError: If config file cannot be found
        """
        try:
            # Load configuration with error handling
            self.config = self._load_config(config_path)
            
            # Initialize usage tracker
            self.usage_tracker = UsageTracker()
            
            # Initialize clients with error handling
            self.clients = {}
            self._initialize_clients()
            
            # Track service priorities
            self.service_priorities = self._get_service_priorities()
            
            logger.info(f"ModelDispatcher initialized with {len(self.clients)} clients")
            
        except Exception as e:
            logger.error(f"Failed to initialize ModelDispatcher: {str(e)}")
            raise
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """
        Set configuration for the dispatcher with validation.
        
        Args:
            config: Configuration dictionary
            
        Raises:
            ValueError: If configuration is invalid
        """
        try:
            if not isinstance(config, dict):
                raise ValueError("Config must be a dictionary")
            
            self.config = config
            
            # Update model names from config with validation
            models = config.get("models", {})
            if not isinstance(models, dict):
                raise ValueError("Models config must be a dictionary")
            
            self.default_model = models.get("default", "llama-3.3-70b")
            self.synthesis_model = models.get("synthesis", "llama-3.3-70b")
            
            logger.info("Configuration updated successfully")
            
        except Exception as e:
            logger.error(f"Error setting configuration: {str(e)}")
            raise
        
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """
        Load API configuration from file with enhanced error handling.
        
        Args:
            config_path: Optional custom config path
            
        Returns:
            Configuration dictionary
            
        Raises:
            FileNotFoundError: If no valid config file can be found
            json.JSONDecodeError: If config file is invalid JSON
        """
        # Try multiple possible locations
        possible_paths = [
            config_path,
            os.path.join(os.path.dirname(__file__), "../../config/api_config.json"),
            "src/config/api_config.json",
            "config/api_config.json"
        ]
        
        # Filter None values and keep only paths that exist
        valid_paths = [p for p in possible_paths if p and os.path.exists(p)]
        
        if not valid_paths:
            error_msg = "No valid config paths found. Searched in:"
            for p in possible_paths:
                if p:
                    error_msg += f"\n- {os.path.abspath(p)} (exists: {os.path.exists(p)})"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        path = valid_paths[0]
        logger.info(f"Loading config from: {os.path.abspath(path)}")
        
        try:
            with open(path, 'r') as f:
                config = json.load(f)
                
            # Validate config structure
            if not isinstance(config, dict):
                raise ValueError("Config file must contain a JSON object")
            
            # Debug output
            services = config.get("llm_services", {})
            if not isinstance(services, dict):
                raise ValueError("llm_services must be a dictionary")
            
            enabled = [name for name, conf in services.items() 
                      if isinstance(conf, dict) and conf.get("enabled", False)]
            logger.info(f"Config loaded with enabled services: {enabled}")
            
            return config
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file {path}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error loading config from {path}: {str(e)}")
            raise
    
    def _initialize_clients(self) -> None:
        """
        Initialize API clients with enhanced error handling and security.
        
        Raises:
            ValueError: If client initialization fails
        """
        try:
            services = self.config.get("llm_services", {})
            
            if not isinstance(services, dict):
                raise ValueError("llm_services configuration must be a dictionary")
            
            # Initialize Mistral client if enabled
            if services.get("mistral", {}).get("enabled", False):
                try:
                    api_key = services.get("mistral", {}).get("api_key")
                    if not api_key:
                        logger.warning("Mistral enabled but no API key provided")
                    else:
                        self.clients["mistral"] = MistralClient(api_key)
                        logger.info("Mistral client initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize Mistral client: {str(e)}")
            
            # Initialize Cerebras client if enabled
            if services.get("cerebras", {}).get("enabled", False):
                try:
                    api_key = services.get("cerebras", {}).get("api_key")
                    if not api_key:
                        logger.warning("Cerebras enabled but no API key provided")
                    else:
                        self.clients["cerebras"] = CerebrasClient(api_key)
                        logger.info("Cerebras client initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize Cerebras client: {str(e)}")
            
            # Initialize Cohere client if enabled
            if services.get("cohere", {}).get("enabled", False):
                try:
                    api_key = services.get("cohere", {}).get("api_key")
                    if not api_key:
                        logger.warning("Cohere enabled but no API key provided")
                    else:
                        self.clients["cohere"] = CohereClient(api_key)
                        logger.info("Cohere client initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize Cohere client: {str(e)}")
            
            if not self.clients:
                logger.warning("No LLM clients enabled. Check your configuration.")
                
        except Exception as e:
            logger.error(f"Error initializing clients: {str(e)}")
            raise
    
    def _get_service_priorities(self) -> List[str]:
        """
        Get ordered list of services by priority with validation.
        
        Returns:
            List of service names in priority order
        """
        try:
            services = self.config.get("llm_services", {})
            service_list = []
            
            for service, config in services.items():
                if isinstance(config, dict) and config.get("enabled", False):
                    priority = config.get("priority", 99)  # Default to low priority
                    if not isinstance(priority, (int, float)):
                        logger.warning(f"Invalid priority for {service}: {priority}, using default")
                        priority = 99
                    service_list.append((service, priority))
            
            # Sort by priority (lower number = higher priority)
            service_list.sort(key=lambda x: x[1])
            return [s[0] for s in service_list]
            
        except Exception as e:
            logger.error(f"Error getting service priorities: {str(e)}")
            return []
    
    def _validate_document(self, document: Dict[str, Any]) -> None:
        """
        Validate document structure and content.
        
        Args:
            document: Document to validate
            
        Raises:
            ValueError: If document is invalid
        """
        if not isinstance(document, dict):
            raise ValueError("Document must be a dictionary")
        
        required_fields = ['id', 'title', 'content']
        for field in required_fields:
            if field not in document:
                raise ValueError(f"Document missing required field: {field}")
        
        if not isinstance(document['content'], str):
            raise ValueError("Document content must be a string")
        
        if len(document['content']) > 50000:  # Reasonable limit
            raise ValueError("Document content too long (max 50,000 characters)")
    
    def _sanitize_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize document content to prevent injection attacks.
        
        Args:
            document: Document to sanitize
            
        Returns:
            Sanitized document
        """
        sanitized = document.copy()
        
        # Sanitize content
        if 'content' in sanitized:
            sanitized['content'] = self._sanitize_text(sanitized['content'])
        
        # Sanitize title
        if 'title' in sanitized:
            sanitized['title'] = self._sanitize_text(sanitized['title'], max_length=500)
        
        return sanitized
    
    def _sanitize_text(self, text: str, max_length: int = 50000) -> str:
        """
        Sanitize text input to prevent injection attacks.
        
        Args:
            text: Text to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Sanitized text
        """
        if not isinstance(text, str):
            raise ValueError("Text must be a string")
        
        if len(text) > max_length:
            raise ValueError(f"Text too long (max {max_length} characters)")
        
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
    
    async def dispatch_document(self, document: Dict[str, Any], is_critical: bool = False) -> Dict[str, Any]:
        """
        Route document to appropriate service with enhanced error handling and security.
        
        Args:
            document: The document to process
            is_critical: Whether this is a critical document deserving higher quality processing
            
        Returns:
            Processed document with extracted information
            
        Raises:
            ValueError: If document is invalid
            ConnectionError: If all services fail
        """
        try:
            # Input validation and sanitization
            self._validate_document(document)
            sanitized_doc = self._sanitize_document(document)
            
            logger.info(f"Dispatching document {sanitized_doc['id']} (critical: {is_critical})")
            
            # Create service order based on document priority
            service_order = self._get_service_order(is_critical)
            
            if not service_order:
                raise ConnectionError("No available services configured")
            
            # Try each service in order until one succeeds
            errors = []
            for service in service_order:
                if service not in self.clients:
                    logger.warning(f"Service {service} not available")
                    continue
                    
                if not self.usage_tracker.can_use(service):
                    logger.info(f"Service {service} has reached usage limits. Trying next option.")
                    continue
                
                try:
                    client = self.clients[service]
                    result = await client.process_document(sanitized_doc)
                    
                    # Validate result
                    if not isinstance(result, dict):
                        raise ValueError(f"{service} returned invalid result format")
                    
                    # If processing succeeded, record usage and return result
                    if result.get("success", False):
                        self.usage_tracker.record_usage(service)
                        logger.info(f"Document {sanitized_doc['id']} processed by {service}")
                        return result
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        errors.append(f"{service}: {error_msg}")
                        logger.warning(f"{service} processing failed: {error_msg}")
                        
                except Exception as e:
                    errors.append(f"{service}: {str(e)}")
                    logger.error(f"Error using {service} for document processing: {str(e)}")
            
            # If all services failed, raise exception with all errors
            error_summary = '; '.join(errors)
            logger.error(f"All LLM services failed for document {sanitized_doc['id']}: {error_summary}")
            raise ConnectionError(f"All LLM services failed: {error_summary}")
            
        except ValueError as e:
            logger.error(f"Invalid document input: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error dispatching document {document.get('id', 'unknown')}: {str(e)}")
            raise
    
    def _get_service_order(self, is_critical: bool) -> List[str]:
        """
        Determine the order of services to try based on criticality.
        
        Args:
            is_critical: Whether this is a critical document
            
        Returns:
            List of service names in priority order
        """
        try:
            if not is_critical:
                # For regular documents, use the configured priority order
                return self.service_priorities
            
            # For critical documents, prioritize more capable services
            critical_priority = {"cerebras": 1, "mistral": 2, "cohere": 3}
            
            # Filter to only enabled services
            available_services = [s for s in self.service_priorities if s in self.clients]
            
            # Sort by critical priority
            return sorted(available_services, key=lambda s: critical_priority.get(s, 99))
            
        except Exception as e:
            logger.error(f"Error determining service order: {str(e)}")
            return self.service_priorities
    
    async def generate_synthesis(self, papers: List[Dict[str, Any]], initial_consensus: str) -> Dict[str, Any]:
        """
        Generate a synthesis of multiple papers with enhanced error handling and security.
        
        Args:
            papers: List of processed papers
            initial_consensus: Initial understanding or context
            
        Returns:
            Synthesis of the papers
            
        Raises:
            ValueError: If papers list is invalid
            ConnectionError: If all services fail
        """
        try:
            # Input validation
            if not isinstance(papers, list):
                raise ValueError("Papers must be a list")
            
            if not papers:
                raise ValueError("Papers list cannot be empty")
            
            # Sanitize initial consensus
            if initial_consensus:
                initial_consensus = self._sanitize_text(initial_consensus, max_length=2000)
            
            logger.info(f"Generating synthesis for {len(papers)} papers")
            
            # Synthesis priority is different - prefer services better at reasoning
            synthesis_priority = {"cohere": 1, "cerebras": 2, "mistral": 3}
            
            # Sort available services by synthesis capability
            available_services = [s for s in self.service_priorities if s in self.clients]
            synthesis_order = sorted(available_services, key=lambda s: synthesis_priority.get(s, 99))
            
            if not synthesis_order:
                raise ConnectionError("No available services for synthesis")
            
            # Try each service in order
            errors = []
            for service in synthesis_order:
                if not self.usage_tracker.can_use(service):
                    logger.info(f"Service {service} has reached usage limits for synthesis. Trying next option.")
                    continue
                
                try:
                    client = self.clients[service]
                    result = await client.generate_synthesis(papers, initial_consensus)
                    
                    # Validate result
                    if not isinstance(result, dict):
                        raise ValueError(f"{service} synthesis returned invalid result format")
                    
                    # If synthesis succeeded, record usage and return result
                    if result.get("success", False):
                        self.usage_tracker.record_usage(service)
                        logger.info(f"Synthesis generated by {service}")
                        return result
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        errors.append(f"{service}: {error_msg}")
                        logger.warning(f"{service} synthesis failed: {error_msg}")
                        
                except Exception as e:
                    errors.append(f"{service}: {str(e)}")
                    logger.error(f"Error using {service} for synthesis: {str(e)}")
            
            # If all services failed, raise exception with all errors
            error_summary = '; '.join(errors)
            logger.error(f"All synthesis services failed: {error_summary}")
            raise ConnectionError(f"All synthesis services failed: {error_summary}")
            
        except ValueError as e:
            logger.error(f"Invalid synthesis input: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error generating synthesis: {str(e)}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check of all components.
        
        Returns:
            Health status for all components
        """
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "components": {}
            }
            
            # Check clients
            client_status = {}
            for service, client in self.clients.items():
                try:
                    # Simple health check - try to access client attributes
                    if hasattr(client, 'api_key'):
                        client_status[service] = {"status": "healthy", "configured": True}
                    else:
                        client_status[service] = {"status": "error", "error": "Invalid client structure"}
                        health_status["status"] = "degraded"
                except Exception as e:
                    client_status[service] = {"status": "error", "error": str(e)}
                    health_status["status"] = "degraded"
            
            health_status["components"]["clients"] = client_status
            
            # Check usage tracker
            try:
                self.usage_tracker.get_usage_summary()
                health_status["components"]["usage_tracker"] = {"status": "healthy"}
            except Exception as e:
                health_status["components"]["usage_tracker"] = {"status": "error", "error": str(e)}
                health_status["status"] = "degraded"
            
            # Check configuration
            try:
                config_valid = isinstance(self.config, dict) and "llm_services" in self.config
                health_status["components"]["configuration"] = {
                    "status": "healthy" if config_valid else "error",
                    "valid": config_valid
                }
                if not config_valid:
                    health_status["status"] = "degraded"
            except Exception as e:
                health_status["components"]["configuration"] = {"status": "error", "error": str(e)}
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