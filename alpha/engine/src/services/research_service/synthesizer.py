#synthesizer.py

import logging
import re
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime
import json
import redis.asyncio as redis
import hashlib

from src.storage.db.operations import DatabaseOperations
from src.services.llm_service.llm_manager import LLMManager

# Configure structured logging
logger = logging.getLogger(__name__)

class ContentSynthesizer:
    """
    Generic content synthesizer for forming consensus from multiple sources.
    
    Features:
    - Secure content synthesis and analysis
    - Input validation and sanitization
    - Comprehensive error handling and retry logic
    - Structured logging and monitoring
    - Protection against injection attacks
    - Caching and task management
    """
    
    def __init__(self, db_ops: DatabaseOperations, llm_manager: LLMManager, redis_url: str):
        """
        Initialize content synthesizer with enhanced security and error handling.
        
        Args:
            db_ops: Database operations instance
            llm_manager: LLM manager instance
            redis_url: Redis connection URL
            
        Raises:
            ValueError: If parameters are invalid
            ConnectionError: If Redis connection fails
        """
        try:
            if not db_ops:
                raise ValueError("Database operations instance is required")
            if not llm_manager:
                raise ValueError("LLM manager instance is required")
            if not redis_url:
                raise ValueError("Redis URL is required")
            
            logger.info("Initializing ContentSynthesizer with enhanced security")
            
            self.db = db_ops
            self.llm = llm_manager
            
            # Initialize Redis with error handling
            try:
                self.redis_client = redis.from_url(redis_url)
                logger.info("Redis client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Redis client: {str(e)}")
                raise ConnectionError(f"Redis connection failed: {str(e)}")
            
            self.synthesis_cache = {}
            self.synthesis_tasks = {}
            
            logger.info("ContentSynthesizer initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ContentSynthesizer: {str(e)}")
            raise
    
    def _validate_content_ids(self, content_ids: List[str]) -> None:
        """
        Validate content IDs for security and safety.
        
        Args:
            content_ids: List of content IDs to validate
            
        Raises:
            ValueError: If content IDs are invalid
        """
        if not isinstance(content_ids, list):
            raise ValueError("Content IDs must be a list")
        
        if not content_ids:
            raise ValueError("Content IDs list cannot be empty")
        
        if len(content_ids) > 100:  # Reasonable limit
            raise ValueError("Too many content IDs (max 100)")
        
        for i, content_id in enumerate(content_ids):
            if not isinstance(content_id, str) or not content_id.strip():
                raise ValueError(f"Invalid content ID at index {i}: must be non-empty string")
            
            # Check for potentially dangerous patterns
            if re.search(r'[<>"\']', content_id):
                raise ValueError(f"Content ID at index {i} contains invalid characters")
    
    def _sanitize_text(self, text: str, max_length: int = 10000) -> str:
        """
        Sanitize text to prevent injection attacks.
        
        Args:
            text: Text to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Sanitized text
        """
        if not isinstance(text, str):
            raise ValueError("Text must be a string")
        
        if len(text) > max_length:
            text = text[:max_length]
        
        # Basic XSS protection
        sanitized = text.replace('<', '&lt;').replace('>', '&gt;')
        
        # Remove null bytes and other control characters
        sanitized = ''.join(char for char in sanitized if ord(char) >= 32 or char in '\n\r\t')
        
        return sanitized.strip()
    
    async def synthesize_content(self, content_ids: List[str], content_type: str = "general", force_refresh: bool = False) -> Dict[str, Any]:
        """
        Synthesize findings across multiple content sources with enhanced error handling and security.
        
        Args:
            content_ids: List of content IDs to synthesize
            content_type: Type of content (e.g., "news", "articles", "papers", "general")
            force_refresh: Whether to force refresh cached results
            
        Returns:
            Synthesis results
            
        Raises:
            ValueError: If content IDs are invalid
            ConnectionError: If synthesis fails
        """
        try:
            # Input validation and sanitization
            self._validate_content_ids(content_ids)
            
            # Create cache key
            cache_key = f"synthesis:{content_type}:{hashlib.md5('_'.join(sorted(content_ids)).encode()).hexdigest()}"
            
            logger.info(f"Synthesizing {len(content_ids)} {content_type} items (force_refresh: {force_refresh})")
            
            # Check cache if not forcing refresh
            if not force_refresh:
                try:
                    if cached := await self._get_cached_synthesis(cache_key):
                        logger.info("Using cached synthesis")
                        return cached
                except Exception as e:
                    logger.warning(f"Failed to retrieve cached synthesis: {str(e)}")
            
            # Create synthesis task if not already running
            if cache_key not in self.synthesis_tasks:
                self.synthesis_tasks[cache_key] = asyncio.create_task(
                    self._generate_synthesis(content_ids, content_type, cache_key)
                )
            
            try:
                return await self.synthesis_tasks[cache_key]
            finally:
                if cache_key in self.synthesis_tasks:
                    del self.synthesis_tasks[cache_key]
            
        except ValueError as e:
            logger.error(f"Invalid input for content synthesis: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error synthesizing content: {str(e)}")
            raise
    
    async def _generate_synthesis(self, content_ids: List[str], content_type: str, cache_key: str) -> Dict[str, Any]:
        """
        Generate comprehensive synthesis of content with enhanced error handling.
        
        Args:
            content_ids: List of content IDs
            content_type: Type of content
            cache_key: Cache key for storing results
            
        Returns:
            Synthesis results
            
        Raises:
            ConnectionError: If synthesis generation fails
        """
        try:
            # Gather content with error handling
            content_items = []
            for cid in content_ids:
                try:
                    if content := await self.db.get_processed_content(cid):
                        content_items.append(content)
                    else:
                        logger.warning(f"Content {cid} not found in database")
                except Exception as e:
                    logger.error(f"Error retrieving content {cid}: {str(e)}")
            
            if not content_items:
                logger.warning("No valid content found for synthesis")
                return {
                    "error": "No valid content found",
                    "content_count": 0,
                    "generated_at": datetime.utcnow().isoformat()
                }
            
            logger.info(f"Retrieved {len(content_items)} content items for synthesis")
            
            # Generate all aspects concurrently with error handling
            synthesis_tasks = {
                "common_findings": self._extract_common_findings(content_items, content_type),
                "contradictions": self._find_contradictions(content_items, content_type),
                "gaps": self._identify_gaps(content_items, content_type),
                "timeline": self._create_timeline(content_items, content_type),
                "connections": self._map_connections(content_items, content_type),
                "future_directions": self._suggest_future_directions(content_items, content_type)
            }
            
            synthesis = {}
            for aspect, task in synthesis_tasks.items():
                try:
                    synthesis[aspect] = await task
                except Exception as e:
                    logger.error(f"Error generating {aspect}: {str(e)}")
                    synthesis[aspect] = {"error": str(e)}
            
            # Add metadata
            synthesis.update({
                "content_count": len(content_items),
                "content_type": content_type,
                "generated_at": datetime.utcnow().isoformat(),
                "cache_key": cache_key
            })
            
            # Cache the result
            try:
                await self._cache_synthesis(cache_key, synthesis)
            except Exception as e:
                logger.warning(f"Failed to cache synthesis: {str(e)}")
            
            logger.info(f"Successfully generated synthesis for {len(content_items)} {content_type} items")
            return synthesis
            
        except Exception as e:
            logger.error(f"Error in synthesis generation: {str(e)}")
            raise ConnectionError(f"Synthesis generation failed: {str(e)}")
    
    async def _extract_common_findings(self, content_items: List[Dict[str, Any]], content_type: str) -> List[Dict[str, Any]]:
        """Extract common findings across content items."""
        try:
            # Prepare content summaries for LLM
            summaries = []
            for item in content_items:
                summary = f"Title: {item.get('title', 'Unknown')}\n"
                summary += f"Content: {item.get('content', '')[:1000]}...\n"
                summary += f"Date: {item.get('date', 'Unknown')}\n"
                summaries.append(summary)
            
            prompt = f"""Analyze the following {content_type} items and identify the most important common findings, themes, or insights.

Content Items:
{chr(10).join(summaries)}

Identify 5-10 key common findings that appear across multiple sources. For each finding:
1. State the finding clearly
2. Mention which sources support it
3. Note the strength of consensus

Format as a list of findings with clear descriptions."""
            
            response = await self.llm.generate_synthesis(summaries, prompt)
            return self._parse_findings(response)
            
        except Exception as e:
            logger.error(f"Error extracting common findings: {str(e)}")
            return [{"error": str(e)}]
    
    async def _find_contradictions(self, content_items: List[Dict[str, Any]], content_type: str) -> List[Dict[str, Any]]:
        """Find contradictions or disagreements across content items."""
        try:
            summaries = []
            for item in content_items:
                summary = f"Title: {item.get('title', 'Unknown')}\n"
                summary += f"Content: {item.get('content', '')[:1000]}...\n"
                summary += f"Date: {item.get('date', 'Unknown')}\n"
                summaries.append(summary)
            
            prompt = f"""Analyze the following {content_type} items and identify any contradictions, disagreements, or conflicting information.

Content Items:
{chr(10).join(summaries)}

Identify any contradictions or disagreements between sources. For each contradiction:
1. Describe the conflicting information
2. List which sources support each side
3. Note the potential reasons for disagreement

Format as a list of contradictions with clear descriptions."""
            
            response = await self.llm.generate_synthesis(summaries, prompt)
            return self._parse_contradictions(response)
            
        except Exception as e:
            logger.error(f"Error finding contradictions: {str(e)}")
            return [{"error": str(e)}]
    
    async def _identify_gaps(self, content_items: List[Dict[str, Any]], content_type: str) -> List[Dict[str, Any]]:
        """Identify gaps or missing information in the content."""
        try:
            summaries = []
            for item in content_items:
                summary = f"Title: {item.get('title', 'Unknown')}\n"
                summary += f"Content: {item.get('content', '')[:1000]}...\n"
                summary += f"Date: {item.get('date', 'Unknown')}\n"
                summaries.append(summary)
            
            prompt = f"""Analyze the following {content_type} items and identify gaps, missing information, or areas that need more coverage.

Content Items:
{chr(10).join(summaries)}

Identify 3-5 key gaps or missing information. For each gap:
1. Describe what information is missing
2. Explain why it's important
3. Suggest what additional sources might help

Format as a list of gaps with clear descriptions."""
            
            response = await self.llm.generate_synthesis(summaries, prompt)
            return self._parse_gaps(response)
            
        except Exception as e:
            logger.error(f"Error identifying gaps: {str(e)}")
            return [{"error": str(e)}]
    
    async def _create_timeline(self, content_items: List[Dict[str, Any]], content_type: str) -> Dict[str, Any]:
        """Create a timeline of events or developments."""
        try:
            # Sort by date if available
            dated_items = [item for item in content_items if item.get('date')]
            dated_items.sort(key=lambda x: x.get('date', ''))
            
            summaries = []
            for item in dated_items:
                summary = f"Date: {item.get('date', 'Unknown')}\n"
                summary += f"Title: {item.get('title', 'Unknown')}\n"
                summary += f"Content: {item.get('content', '')[:500]}...\n"
                summaries.append(summary)
            
            prompt = f"""Create a timeline of key events or developments from the following {content_type} items.

Content Items (chronological):
{chr(10).join(summaries)}

Create a clear timeline showing the progression of events or developments. Include:
1. Key dates and events
2. Important developments
3. Any patterns or trends over time

Format as a structured timeline."""
            
            response = await self.llm.generate_synthesis(summaries, prompt)
            return {"timeline": response, "item_count": len(dated_items)}
            
        except Exception as e:
            logger.error(f"Error creating timeline: {str(e)}")
            return {"error": str(e)}
    
    async def _map_connections(self, content_items: List[Dict[str, Any]], content_type: str) -> Dict[str, Any]:
        """Map connections and relationships between content items."""
        try:
            summaries = []
            for item in content_items:
                summary = f"Title: {item.get('title', 'Unknown')}\n"
                summary += f"Content: {item.get('content', '')[:1000]}...\n"
                summary += f"Date: {item.get('date', 'Unknown')}\n"
                summaries.append(summary)
            
            prompt = f"""Analyze the following {content_type} items and identify connections, relationships, or themes that link them together.

Content Items:
{chr(10).join(summaries)}

Identify:
1. Common themes or topics
2. Relationships between different pieces of content
3. How the content items relate to each other
4. Any patterns or clusters of related information

Format as a structured analysis of connections."""
            
            response = await self.llm.generate_synthesis(summaries, prompt)
            return {"connections": response, "item_count": len(content_items)}
            
        except Exception as e:
            logger.error(f"Error mapping connections: {str(e)}")
            return {"error": str(e)}
    
    async def _suggest_future_directions(self, content_items: List[Dict[str, Any]], content_type: str) -> List[Dict[str, Any]]:
        """Suggest future directions or next steps based on content analysis."""
        try:
            summaries = []
            for item in content_items:
                summary = f"Title: {item.get('title', 'Unknown')}\n"
                summary += f"Content: {item.get('content', '')[:1000]}...\n"
                summary += f"Date: {item.get('date', 'Unknown')}\n"
                summaries.append(summary)
            
            prompt = f"""Based on the following {content_type} items, suggest future directions, next steps, or areas for further investigation.

Content Items:
{chr(10).join(summaries)}

Suggest 3-5 future directions or next steps. For each suggestion:
1. Describe the direction or step
2. Explain why it's important or relevant
3. Note what additional information might be needed

Format as a list of future directions with clear descriptions."""
            
            response = await self.llm.generate_synthesis(summaries, prompt)
            return self._parse_future_directions(response)
            
        except Exception as e:
            logger.error(f"Error suggesting future directions: {str(e)}")
            return [{"error": str(e)}]
    
    async def _get_cached_synthesis(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached synthesis result."""
        try:
            cached = await self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            logger.warning(f"Error retrieving cached synthesis: {str(e)}")
            return None
    
    async def _cache_synthesis(self, cache_key: str, synthesis: Dict[str, Any]) -> None:
        """Cache synthesis result."""
        try:
            await self.redis_client.setex(
                cache_key,
                3600,  # 1 hour cache
                json.dumps(synthesis)
            )
        except Exception as e:
            logger.warning(f"Error caching synthesis: {str(e)}")
    
    def _parse_findings(self, llm_response: str) -> List[Dict[str, Any]]:
        """Parse LLM response into structured findings."""
        try:
            # Simple parsing - can be enhanced
            findings = []
            lines = llm_response.split('\n')
            current_finding = {}
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    if current_finding:
                        findings.append(current_finding)
                    current_finding = {"description": line}
            
            if current_finding:
                findings.append(current_finding)
            
            return findings
        except Exception as e:
            logger.error(f"Error parsing findings: {str(e)}")
            return [{"description": llm_response}]
    
    def _parse_contradictions(self, llm_response: str) -> List[Dict[str, Any]]:
        """Parse LLM response into structured contradictions."""
        try:
            # Simple parsing - can be enhanced
            contradictions = []
            lines = llm_response.split('\n')
            current_contradiction = {}
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    if current_contradiction:
                        contradictions.append(current_contradiction)
                    current_contradiction = {"description": line}
            
            if current_contradiction:
                contradictions.append(current_contradiction)
            
            return contradictions
        except Exception as e:
            logger.error(f"Error parsing contradictions: {str(e)}")
            return [{"description": llm_response}]
    
    def _parse_gaps(self, llm_response: str) -> List[Dict[str, Any]]:
        """Parse LLM response into structured gaps."""
        try:
            # Simple parsing - can be enhanced
            gaps = []
            lines = llm_response.split('\n')
            current_gap = {}
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    if current_gap:
                        gaps.append(current_gap)
                    current_gap = {"description": line}
            
            if current_gap:
                gaps.append(current_gap)
            
            return gaps
        except Exception as e:
            logger.error(f"Error parsing gaps: {str(e)}")
            return [{"description": llm_response}]
    
    def _parse_future_directions(self, llm_response: str) -> List[Dict[str, Any]]:
        """Parse LLM response into structured future directions."""
        try:
            # Simple parsing - can be enhanced
            directions = []
            lines = llm_response.split('\n')
            current_direction = {}
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    if current_direction:
                        directions.append(current_direction)
                    current_direction = {"description": line}
            
            if current_direction:
                directions.append(current_direction)
            
            return directions
        except Exception as e:
            logger.error(f"Error parsing future directions: {str(e)}")
            return [{"description": llm_response}]
    
    async def cleanup(self):
        """Clean up resources."""
        try:
            if hasattr(self, 'redis_client'):
                await self.redis_client.close()
            logger.info("ContentSynthesizer cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check."""
        try:
            redis_health = await self.redis_client.ping()
            return {
                "status": "healthy" if redis_health else "unhealthy",
                "redis": "connected" if redis_health else "disconnected",
                "llm": "available" if self.llm else "unavailable",
                "cache_size": len(self.synthesis_cache),
                "active_tasks": len(self.synthesis_tasks)
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            } 