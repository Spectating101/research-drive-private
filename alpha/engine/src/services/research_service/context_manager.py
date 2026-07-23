import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
import redis.asyncio as redis
from src.storage.db.operations import DatabaseOperations
from src.services.llm_service.llm_manager import LLMManager

logger = logging.getLogger(__name__)

class ContentContextManager:
    """
    Generic content context manager for managing research sessions and content processing.
    
    Features:
    - Session management for content analysis
    - Content processing and storage
    - Citation tracking
    - Session state management
    """
    
    def __init__(self, db_ops: DatabaseOperations, llm_manager: LLMManager, redis_url: str):
        """
        Initialize content context manager.
        
        Args:
            db_ops: Database operations instance
            llm_manager: LLM manager instance
            redis_url: Redis connection URL
        """
        self.db = db_ops
        self.llm = llm_manager
        self.redis_client = redis.from_url(redis_url)
        self.active_sessions = {}
        
    async def create_session(self, session_id: str, content_type: str = "general") -> Dict[str, Any]:
        """
        Create a new content analysis session.
        
        Args:
            session_id: Unique session identifier
            content_type: Type of content being analyzed
            
        Returns:
            Session information
        """
        session = {
            "session_id": session_id,
            "content_type": content_type,
            "created_at": datetime.utcnow().isoformat(),
            "status": "active",
            "content_items": [],
            "citations": [],
            "analysis_results": {}
        }
        
        await self.redis_client.setex(
            f"session:{session_id}",
            3600,  # 1 hour
            json.dumps(session)
        )
        
        self.active_sessions[session_id] = session
        logger.info(f"Created session {session_id} for {content_type} analysis")
        return session
    
    async def add_content_to_session(self, session_id: str, content_item: Dict[str, Any]) -> bool:
        """
        Add content item to an active session.
        
        Args:
            session_id: Session identifier
            content_item: Content item to add
            
        Returns:
            Success status
        """
        try:
            session = await self.get_session(session_id)
            if not session:
                logger.error(f"Session {session_id} not found")
                return False
            
            # Process and store content
            processed_content = await self._process_content(content_item)
            content_id = await self.db.store_processed_content(processed_content)
            
            # Add to session
            session["content_items"].append({
                "content_id": content_id,
                "title": content_item.get("title", "Unknown"),
                "source": content_item.get("source", "Unknown"),
                "date": content_item.get("date", datetime.utcnow().isoformat()),
                "added_at": datetime.utcnow().isoformat()
            })
            
            # Update session
            await self._update_session(session_id, session)
            logger.info(f"Added content to session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding content to session {session_id}: {str(e)}")
            return False
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session information.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session information or None
        """
        try:
            # Check active sessions first
            if session_id in self.active_sessions:
                return self.active_sessions[session_id]
            
            # Check Redis
            session_data = await self.redis_client.get(f"session:{session_id}")
            if session_data:
                session = json.loads(session_data)
                self.active_sessions[session_id] = session
                return session
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving session {session_id}: {str(e)}")
            return None
    
    async def _process_content(self, content_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process content item for storage and analysis.
        
        Args:
            content_item: Raw content item
            
        Returns:
            Processed content item
        """
        processed = {
            "title": content_item.get("title", ""),
            "content": content_item.get("content", ""),
            "source": content_item.get("source", ""),
            "url": content_item.get("url", ""),
            "date": content_item.get("date", datetime.utcnow().isoformat()),
            "content_type": content_item.get("content_type", "general"),
            "metadata": content_item.get("metadata", {}),
            "processed_at": datetime.utcnow().isoformat()
        }
        
        # Extract key information using LLM if available
        if self.llm and processed["content"]:
            try:
                summary = await self._extract_summary(processed["content"])
                processed["summary"] = summary
            except Exception as e:
                logger.warning(f"Failed to extract summary: {str(e)}")
                processed["summary"] = ""
        
        return processed
    
    async def _extract_summary(self, content: str) -> str:
        """
        Extract summary from content using LLM.
        
        Args:
            content: Content text
            
        Returns:
            Extracted summary
        """
        prompt = f"""Extract a concise summary (2-3 sentences) from the following content:

{content[:2000]}...

Summary:"""
        
        try:
            result = await self.llm.model_dispatcher.dispatch_document({
                'id': 'summary-extract',
                'title': 'Summary Extraction',
                'content': prompt
            }, is_critical=False)
            
            return result.get('content', '')[:500]
        except Exception as e:
            logger.error(f"Error extracting summary: {str(e)}")
            return ""
    
    async def _update_session(self, session_id: str, session: Dict[str, Any]) -> None:
        """
        Update session in storage.
        
        Args:
            session_id: Session identifier
            session: Updated session data
        """
        try:
            session["updated_at"] = datetime.utcnow().isoformat()
            await self.redis_client.setex(
                f"session:{session_id}",
                3600,  # 1 hour
                json.dumps(session)
            )
            self.active_sessions[session_id] = session
        except Exception as e:
            logger.error(f"Error updating session {session_id}: {str(e)}")
    
    async def close_session(self, session_id: str) -> bool:
        """
        Close a session and store final results.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Success status
        """
        try:
            session = await self.get_session(session_id)
            if not session:
                logger.error(f"Session {session_id} not found")
                return False
            
            session["status"] = "closed"
            session["closed_at"] = datetime.utcnow().isoformat()
            
            # Store final session data
            await self.db.store_session_data(session)
            
            # Clean up
            await self.redis_client.delete(f"session:{session_id}")
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            logger.info(f"Closed session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error closing session {session_id}: {str(e)}")
            return False
    
    async def get_session_content(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all content items for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of content items
        """
        try:
            session = await self.get_session(session_id)
            if not session:
                return []
            
            content_items = []
            for item in session.get("content_items", []):
                content = await self.db.get_processed_content(item["content_id"])
                if content:
                    content_items.append(content)
            
            return content_items
            
        except Exception as e:
            logger.error(f"Error retrieving session content {session_id}: {str(e)}")
            return []
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        try:
            cleaned = 0
            current_time = datetime.utcnow()
            
            for session_id, session in list(self.active_sessions.items()):
                created_at = datetime.fromisoformat(session["created_at"])
                if current_time - created_at > timedelta(hours=1):
                    await self.close_session(session_id)
                    cleaned += 1
            
            logger.info(f"Cleaned up {cleaned} expired sessions")
            return cleaned
            
        except Exception as e:
            logger.error(f"Error cleaning up sessions: {str(e)}")
            return 0 