import aiohttp
import os
from typing import List, Dict, Optional

class LLMChatClient:
    """
    Production-ready LLM chat client for context-aware, multi-turn chat. Default: Cerebras.
    Easily swappable for other providers (OpenAI, Anthropic, etc.).
    """
    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.3-70b", temperature: float = 0.7, max_tokens: int = 1000):
        self.api_key = api_key or os.environ.get("CEREBRAS_API_KEY")
        self.api_url = "https://api.cerebras.ai/v1/chat/completions"
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        if not self.api_key:
            raise ValueError("Cerebras API key not configured.")

    async def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        """
        Send a chat completion request with conversation history.
        Args:
            messages: List of dicts with 'role' and 'content'.
            model: Override model name.
            temperature: Override temperature.
            max_tokens: Override max tokens.
        Returns:
            Assistant's response as a string.
        Raises:
            Exception on API or network error.
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.api_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Cerebras API error: {response.status} - {error_text}")
                result = await response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise Exception("No content in LLM response.")
                return content 