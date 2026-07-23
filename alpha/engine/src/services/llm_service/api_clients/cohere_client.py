# src/services/llm_service/api_clients/cohere_client.py

import aiohttp
import json
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class CohereClient:
    """Client for Cohere API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Cohere client with API key"""
        self.api_key = api_key or os.environ.get("COHERE_API_KEY")
        self.api_url_chat = "https://api.cohere.ai/v1/chat"
        self.api_url_generate = "https://api.cohere.ai/v1/generate"
        
        if not self.api_key:
            logger.warning("Cohere API key not set. Set COHERE_API_KEY env var or pass as argument")
    
    async def process_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a document with Cohere API
        
        Args:
            document: Dictionary containing document info (id, title, content)
            
        Returns:
            Dictionary with extracted information
        """
        if not self.api_key:
            raise ValueError("Cohere API key not configured")
        
        # Extract document content (handle both text and binary)
        content = document.get("content", "")
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        
        # Prepare prompt - truncate if needed
        max_chars = 12000  # Cohere has smaller context than some others
        if len(content) > max_chars:
            # Keep beginning and end if document is too long
            half = max_chars // 2
            content = content[:half] + "\n\n[content truncated]\n\n" + content[-half:]
        
        # Create extraction message
        message = self._create_extraction_message(
            document.get("title", "Untitled"), 
            content
        )
        
        # Call Cohere chat API
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": "command-light",  # Use lighter model to conserve tokens
                    "message": message,
                    "temperature": 0.1,
                    "max_tokens": 2000
                }
                
                async with session.post(
                    self.api_url_chat, 
                    headers=headers, 
                    json=payload,
                    timeout=60
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Cohere API error: {response.status} - {error_text}")
                        raise Exception(f"Cohere API error: {response.status}")
                    
                    result = await response.json()
                    return self._process_response(document.get("id", "unknown"), result)
                    
        except Exception as e:
            logger.error(f"Error in Cohere API call: {str(e)}")
            return {
                "doc_id": document.get("id", "unknown"),
                "error": str(e),
                "success": False
            }
    
    def _create_extraction_message(self, title: str, content: str) -> str:
        """Create an extraction message for the document"""
        return f"""
        Extract key information from this research paper.
        
        Paper Title: {title}
        
        Paper Content:
        {content}
        
        Extract the following information in JSON format:
        1. main_findings: A list of the key findings or conclusions
        2. methodology: The research methodology used
        3. results: The primary results or outcomes
        4. limitations: Any limitations or constraints mentioned
        5. future_work: Suggestions for future research
        
        Format your response as a clean JSON object with these fields.
        Do not include any text before or after the JSON object.
        """
    
    def _process_response(self, doc_id: str, api_response: Dict[str, Any]) -> Dict[str, Any]:
        """Process and structure the API response"""
        try:
            # Extract content from Cohere response
            content = api_response.get("text", "").strip()
            
            # Try to parse JSON from content
            try:
                # Find JSON in the text (in case model adds extra commentary)
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    data = json.loads(json_str)
                else:
                    # If no JSON found, use raw text
                    data = {"raw_text": content}
            except json.JSONDecodeError:
                data = {"raw_text": content}
            
            # Add document ID and success flag
            data["doc_id"] = doc_id
            data["success"] = True
            return data
            
        except Exception as e:
            logger.error(f"Error processing Cohere response: {str(e)}")
            return {
                "doc_id": doc_id,
                "error": str(e),
                "raw_text": api_response.get("text", ""),
                "success": False
            }
    
    async def generate_synthesis(self, papers: List[Dict[str, Any]], initial_consensus: str) -> Dict[str, Any]:
        """
        Generate a synthesis of multiple papers
        
        Args:
            papers: List of processed papers with extracted information
            initial_consensus: Initial understanding or context
            
        Returns:
            Dictionary with synthesis information
        """
        if not self.api_key:
            raise ValueError("Cohere API key not configured")
        
        # Prepare paper summaries for the prompt
        paper_summaries = []
        for paper in papers:
            paper_id = paper.get("doc_id", "unknown")
            title = paper.get("title", "Untitled")
            
            summary = f"PAPER ID: {paper_id}\nTITLE: {title}\n"
            
            # Add findings if available
            if "main_findings" in paper and isinstance(paper["main_findings"], list):
                summary += "FINDINGS:\n"
                for i, finding in enumerate(paper["main_findings"], 1):
                    summary += f"  {i}. {finding}\n"
            elif "raw_text" in paper:
                summary += f"CONTENT: {paper['raw_text'][:500]}...\n"
            
            paper_summaries.append(summary)
        
        # Join summaries with limit to avoid exceeding token context
        all_summaries = "\n\n".join(paper_summaries)
        if len(all_summaries) > 12000:  # Conservative limit for Cohere
            # Truncate in the middle if too long
            all_summaries = all_summaries[:6000] + "\n...[additional papers omitted]...\n" + all_summaries[-6000:]
        
        # Create synthesis prompt
        prompt = f"""
        You are a research synthesis expert creating a comprehensive literature review.
        
        INITIAL UNDERSTANDING:
        {initial_consensus[:2000]}
        
        PAPERS ANALYZED:
        {all_summaries}
        
        Based on these papers, provide a comprehensive research synthesis that:
        1. Summarizes the current state of knowledge
        2. Identifies consensus findings across papers
        3. Highlights contradictions or disagreements
        4. Analyzes limitations in current research
        5. Suggests directions for future research
        
        Format your response as a structured literature review.
        """
        
        # For synthesis, use the full `command` model (not light) for better quality
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": "command",  # Use full model for synthesis
                    "prompt": prompt,
                    "temperature": 0.3,
                    "max_tokens": 2500
                }
                
                async with session.post(
                    self.api_url_generate, 
                    headers=headers, 
                    json=payload,
                    timeout=120  # Longer timeout for synthesis
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Cohere API error: {response.status} - {error_text}")
                        raise Exception(f"Cohere API error: {response.status}")
                    
                    result = await response.json()
                    synthesis = result.get("generations", [{"text": ""}])[0]["text"]
                    
                    return {
                        "synthesis": synthesis,
                        "paper_count": len(papers),
                        "generated_at": datetime.now().isoformat()
                    }
                    
        except Exception as e:
            logger.error(f"Error in Cohere synthesis: {str(e)}")
            return {
                "error": str(e),
                "success": False
            }