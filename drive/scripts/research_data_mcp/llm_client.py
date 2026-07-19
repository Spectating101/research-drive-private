#!/usr/bin/env python3
"""Legacy OpenAI-compatible chat client for non-desk procurement helpers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class LLMClientError(RuntimeError):
    pass


def llm_configured() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY") or "localhost" in os.getenv("DEEPSEEK_BASE_URL", ""))


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] = "auto",
    temperature: float = 0.15,
    response_format: dict[str, str] | None = None,
    timeout: int = 90,
) -> dict[str, Any]:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
    body: dict[str, Any] = {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "temperature": temperature,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice
    if response_format:
        body["response_format"] = response_format
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        base_url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise LLMClientError(f"LLM HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMClientError(f"LLM unreachable: {exc}") from exc


def message_content(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return ""


def parse_json_content(message: dict[str, Any]) -> dict[str, Any]:
    raw = message_content(message).strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise
