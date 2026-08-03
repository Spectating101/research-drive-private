# src/services/llm_service/api_clients/cerebras_client.py

import aiohttp
import json
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class CerebrasClient:
    """Client for Cerebras AI API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Cerebras client with API key"""
        self.api_key = api_key or os.environ.get("CEREBRAS_API_KEY")
        self.api_url = "https://api.cerebras.ai/v1/chat/completions"
        
        if not self.api_key:
            logger.warning("Cerebras API key not set. Set CEREBRAS_API_KEY env var or pass as argument")
    
    async def process_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a document with Cerebras AI
        
        Args:
            document: Dictionary containing document info (id, title, content)
            
        Returns:
            Dictionary with extracted information
        """
        
        if not self.api_key:
            raise ValueError("Cerebras API key not configured")
        
        # Extract document content (handle both text and binary)
        content = document.get("content", "")
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        
        # Prepare prompt - truncate if needed
        max_chars = 18000  # Cerebras has 8k token context window
        if len(content) > max_chars:
            # Keep beginning and end if document is too long
            half = max_chars // 2
            content = content[:half] + "\n\n[content truncated]\n\n" + content[-half:]
        
        # Create extraction prompt
        prompt = self._create_extraction_prompt(
            document.get("title", "Untitled"), 
            content
        )
        
        # Determine which model to use based on criticality
        # Use 70B for critical papers if available, otherwise 8B
        model = "llama-3.3-70b" # Default to larger model
        
        # Call Cerebras API
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a research assistant analyzing scholarly papers."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4000
                }
                
                async with session.post(
                    self.api_url, 
                    headers=headers, 
                    json=payload,
                    timeout=90  # Longer timeout for larger model
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Cerebras API error: {response.status} - {error_text}")
                        raise Exception(f"Cerebras API error: {response.status}")
                    
                    result = await response.json()
                    return self._process_response(document.get("id", "unknown"), result)
                    
        except Exception as e:
            logger.error(f"Error in Cerebras API call: {str(e)}")
            return {
                "doc_id": document.get("id", "unknown"),
                "error": str(e),
                "success": False
            }
    
    def _create_extraction_prompt(self, title: str, content: str) -> str:
        """Create an extraction prompt for the document"""
        # Cerebras uses a different prompt format than Mistral
        return f"""
        You are a research assistant analyzing a scholarly paper.
        
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
    
    def set_config(self, config):
        """Set configuration for the client"""
        self.config = config
        
        # Update model names from config
        models = config.get("models", {})
        self.default_model = models.get("default", "llama-3.3-70b")  # Or mistral-medium for Mistral
        self.synthesis_model = models.get("synthesis", "llama-3.3-70b")  # Or mistral-medium for Mistral
        
    def _process_response(self, doc_id: str, api_response: Dict[str, Any]) -> Dict[str, Any]:
        """Process and structure the API response"""
        try:
            # Extract content from response (format differs from Mistral)
            content = api_response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
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
            logger.error(f"Error processing Cerebras response: {str(e)}")
            return {
                "doc_id": doc_id,
                "error": str(e),
                "raw_text": api_response.get("output", {}).get("choices", [{}])[0].get("text", ""),
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
            raise ValueError("Cerebras API key not configured")
        
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
        if len(all_summaries) > 18000:  # Conservative limit for 8k tokens
            # Truncate in the middle if too long
            all_summaries = all_summaries[:9000] + "\n...[additional papers omitted]...\n" + all_summaries[-9000:]
        
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
        
        # Call Cerebras API with 70B model for synthesis (if available)
        model = "llama-3.3-70b" # Use largest model for synthesis
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a research assistant analyzing scholarly papers."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4000
                }
                
                async with session.post(
                    self.api_url, 
                    headers=headers, 
                    json=payload,
                    timeout=120  # Longer timeout for synthesis with large model
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Cerebras API error: {response.status} - {error_text}")
                        raise Exception(f"Cerebras API error: {response.status}")
                    
                    result = await response.json()
                    synthesis = result["choices"][0]["message"]["content"]
                    return {
                        "synthesis": synthesis,
                        "paper_count": len(papers),
                        "generated_at": datetime.now().isoformat()
                    }
                    
        except Exception as e:
            logger.error(f"Error in Cerebras synthesis: {str(e)}")
            return {
                "error": str(e),
                "success": False
            }