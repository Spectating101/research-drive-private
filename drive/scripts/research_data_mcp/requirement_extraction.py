#!/usr/bin/env python3
"""Requirement extraction via a local model. No pattern tables, no external API.

Why local rather than a hosted provider:

The desk serves a Taiwanese institution, and routing research questions through
a mainland-China-hosted API is not acceptable here regardless of model quality.
The sanctioned remote path (Cursor Composer) is an agentic call with a 150s
timeout, which cannot sit in an assessment request.  A local model resolves both
constraints at once: the question never leaves the machine, and inference is
fast enough to run inline.

Determinism is preserved by construction: ``temperature=0``, a fixed JSON schema,
and an explicit instruction to emit ``null`` rather than guess.  Every value it
produces is recorded as ``drafted`` provenance, so the researcher's editable
brief remains the correcting authority -- an extraction error is visible and
fixable, never a silent constraint.

If the model is unavailable the extractor raises, and the caller is expected to
leave dimensions ``unspecified``.  It must not substitute invented values: an
undrafted dimension is honestly unchecked, whereas a wrong one is checked wrongly.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any

DIMENSIONS = ("unit", "universe/geography", "time_range", "frequency", "fields", "event_type")

_SYSTEM = """You extract structured research-data requirements from a researcher's question.

Return ONLY a JSON object with exactly these keys:
  unit               observation unit, e.g. "firm_day", "country_week", "issuer_quarter", "transaction"
  universe_geography list of ISO 3166-1 alpha-3 country codes, e.g. ["TWN","JPN"]. Expand regions
                     ("Asia" -> its member codes). null if no place is named.
  time_range         {"start":"YYYY","end":"YYYY"}; use null for an open end. null if no period.
  frequency          one of daily, weekly, monthly, quarterly, annual, intraday
  fields             list of measured variables, e.g. ["return","volume","bid_ask_spread"]
  event_type         list of events/topics, e.g. ["earnings","stablecoin_depeg","governance_disclosure"]

Rules:
- Use null when the question does not state or unambiguously imply a dimension.
- Never guess. A missing value is correct; an invented value is a defect.
- Capture EVERY named place and event, not just the first.
- Output raw JSON only. No prose, no markdown fences."""


class ExtractionUnavailable(RuntimeError):
    """The local model could not be reached or returned unusable output."""


def run_cursor_prompt(prompt: str, model: str, timeout: float) -> str:
    """Run one bounded desk-model turn for declared-source selection.

    The model may propose source identifiers; the caller must validate every
    one against its declared source map. This helper deliberately performs no
    matching, ranking, or fallback inference itself.
    """
    binary = shutil.which("cursor-agent")
    if not binary:
        raise ExtractionUnavailable("cursor-agent not installed")
    key = os.getenv("CURSOR_API_KEY", "").strip()
    if not key:
        raise ExtractionUnavailable("CURSOR_API_KEY is empty")
    try:
        done = subprocess.run(
            [binary, "-p", str(prompt or ""), "--model", str(model or "composer-2.5"),
             "--output-format", "text", "--trust"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CURSOR_API_KEY": key},
            cwd="/tmp",
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionUnavailable(f"cursor-agent timed out after {timeout}s") from exc
    if done.returncode != 0:
        raise ExtractionUnavailable(f"cursor-agent failed: {done.stderr[:200]}")
    return done.stdout


def _endpoint() -> str:
    return os.getenv("RD_LOCAL_LLM_URL", "http://127.0.0.1:11434/api/chat")


def model_name() -> str:
    return os.getenv("RD_LOCAL_LLM_MODEL", "llama3.2:3b")


def enabled() -> bool:
    """Off by default.

    Measured on this host (CPU-only, llama3.2:3b): 9.5-16s per call, and it
    fabricated a `time_range` of 2020-2022 from "Korean chaebol firm daily
    returns" -- a question containing no years -- reproducibly across 3 runs at
    temperature 0.  A fabricated requirement dimension silently becomes a filter,
    so the engine would exclude evidence against a period the researcher never
    asked for and then report a confident negative.  The corpus-derived drafter
    is instant and cannot invent, so it stays primary until a model is shown not
    to fabricate on this hardware.  Set RD_LOCAL_LLM_DRAFTING=1 to re-evaluate.
    """
    return os.getenv("RD_LOCAL_LLM_DRAFTING", "").strip().lower() in {"1", "true", "yes", "on"}


def available(timeout: float = 2.0) -> bool:
    """Cheap liveness probe so callers can degrade instead of stalling."""
    tags = _endpoint().replace("/api/chat", "/api/tags")
    try:
        with urllib.request.urlopen(tags, timeout=timeout) as resp:
            models = json.loads(resp.read().decode()).get("models") or []
        return any(str(m.get("name", "")).startswith(model_name().split(":")[0]) for m in models)
    except Exception:
        return False


def _normalize(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map the model's flat JSON onto requirement dimensions, dropping empties."""
    mapped = {
        "unit": raw.get("unit"),
        "universe/geography": raw.get("universe_geography") or raw.get("universe/geography"),
        "time_range": raw.get("time_range"),
        "frequency": raw.get("frequency"),
        "fields": raw.get("fields"),
        "event_type": raw.get("event_type"),
    }
    draft: dict[str, dict[str, Any]] = {}
    for dimension in DIMENSIONS:
        value = mapped.get(dimension)
        if isinstance(value, str) and not value.strip():
            value = None
        if isinstance(value, dict):
            value = {k: v for k, v in value.items() if v not in (None, "")} or None
        if isinstance(value, list):
            value = [v for v in value if v not in (None, "")] or None
        if value is not None:
            draft[dimension] = {"value": value, "provenance": "drafted"}
    return draft


def extract_requirement(question: str, *, timeout: float = 45.0) -> dict[str, dict[str, Any]]:
    """Extract requirement dimensions from a question using the local model."""
    text = str(question or "").strip()
    if not text:
        return {}
    body = json.dumps({
        "model": model_name(),
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},
        "messages": [{"role": "system", "content": _SYSTEM},
                     {"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(_endpoint(), data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ExtractionUnavailable(f"local model unreachable: {exc}") from exc

    content = (payload.get("message") or {}).get("content") or ""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ExtractionUnavailable(f"local model returned non-JSON: {content[:160]}") from exc
    if not isinstance(parsed, dict):
        raise ExtractionUnavailable("local model returned a non-object payload")
    return _normalize(parsed)
