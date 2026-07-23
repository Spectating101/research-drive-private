import aiohttp
import os
import json
from typing import Dict, Any, List, Optional

class LLMDcClient:
    """
    Production-ready LLM document client for analysis and synthesis. Default: Cerebras.
    Easily swappable for other providers (OpenAI, Anthropic, etc.).
    """
    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.3-70b", temperature: float = 0.1, max_tokens: int = 4000):
        self.api_key = api_key or os.environ.get("CEREBRAS_API_KEY")
        self.api_url = "https://api.cerebras.ai/v1/chat/completions"
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        if not self.api_key:
            raise ValueError("Cerebras API key not configured.")

    async def process_document(self, title: str, content: str, model: Optional[str] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """
        Analyze a document and extract findings using the LLM.
        Args:
            title: Title of the document.
            content: Content of the document.
            model: Override model name.
            temperature: Override temperature.
            max_tokens: Override max tokens.
        Returns:
            Dict with extracted fields (main_findings, methodology, results, etc.).
        Raises:
            Exception on API or network error.
        """
        prompt = self._build_extraction_prompt(title, content)
        payload = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": "You are a research assistant analyzing scholarly papers."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.api_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=90)) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Cerebras API error: {response.status} - {error_text}")
                result = await response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                try:
                    json_start = content.find('{')
                    json_end = content.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = content[json_start:json_end]
                        data = json.loads(json_str)
                    else:
                        data = {"raw_text": content}
                except json.JSONDecodeError:
                    data = {"raw_text": content}
                return data

    def _build_extraction_prompt(self, title: str, content: str) -> str:
        return f"""
        You are a research assistant analyzing a scholarly paper.\n\nPaper Title: {title}\n\nPaper Content:\n{content}\n\nExtract the following information in JSON format:\n1. main_findings: A list of the key findings or conclusions\n2. methodology: The research methodology used\n3. results: The primary results or outcomes\n4. limitations: Any limitations or constraints mentioned\n5. future_work: Suggestions for future research\n\nFormat your response as a clean JSON object with these fields.\nDo not include any text before or after the JSON object.\n        """ 