#!/usr/bin/env python3
"""Requirement extraction via a model backend, with a deterministic grounding floor.

Replaces the previous hand-maintained pattern tables (six geographies, four
units, four field terms) which drafted nothing for six of ten realistic
questions -- including this faculty's own declared domains -- and kept only the
first match, so "Taiwan and Japan" silently dropped Japan.

Backends, measured on the same five-question fabrication sweep:

    backend            latency        invented dimensions
    copilot council    14.4s (all 5)  none
    composer-2.5       40.6s (all 5)  none
    cursor-grok-4.5    63.9s (all 5)  none
    local qwen2.5:7b   49.8s each     3 of 5 (frequency)
    local llama3.2:3b  9.5-16s each   reproducible (time_range)

Capable models decline to invent; small local models do not, and no amount of
prompt instruction suppressed it.  So the backend is configurable and defaults
to a capable one -- but the grounding check below is applied regardless, because
"we used a good model" is not evidence about a specific answer.

Grounding is deliberately narrow.  It rejects only the two failure modes that
were actually observed, rather than speculating about others:

  * ``time_range`` -- every year asserted must literally appear in the question.
    A 3B model produced 2020-2022 for "Korean chaebol firm daily returns", which
    states no years at all.
  * ``frequency`` -- the cadence must have a textual root in the question.  A 7B
    model produced "daily" for "Hong Kong and Singapore exchange turnover".

Both matter more than they look: a requirement dimension is a *filter*.  An
invented time range makes the engine exclude evidence for a period nobody asked
about, then report a confident negative.  Dimensions whose failure mode was not
observed are left to the model plus the researcher's editable brief, which is
the correcting authority for everything marked ``drafted``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any

DIMENSIONS = ("unit", "universe/geography", "time_range", "frequency", "fields", "event_type")

DEFAULT_BACKEND = "cursor"
DEFAULT_CURSOR_MODEL = "composer-2.5"
DEFAULT_COPILOT_MODEL = "copilot-ly"
DEFAULT_LOCAL_MODEL = "qwen2.5:7b-instruct"

_PROMPT = """Extract research-data requirements from the question below.

Output ONLY a JSON object, no prose and no code fences:
  unit               observation unit, e.g. "firm_day", "country_week", "issuer_quarter"
  universe_geography list of ISO 3166-1 alpha-3 codes, e.g. ["TWN","JPN"]; expand regions
  time_range         {"start":"YYYY","end":"YYYY"} or null
  frequency          daily | weekly | monthly | quarterly | annual | intraday
  fields             list of measured variables
  event_type         list of events or topics

Use null for any dimension the question does not explicitly state or
unambiguously imply. Never infer a default: if no observation cadence is
stated, frequency MUST be null. Capture EVERY named place and event, not just
the first. A missing value is correct; an invented one is a defect.

Question: {question}"""

# Cadence -> textual roots that would justify asserting it.
_CADENCE_ROOTS = {
    "daily": ("dai", "day"),
    "weekly": ("week",),
    "monthly": ("month",),
    "quarterly": ("quarter",),
    "annual": ("annual", "year", "yearly"),
    "intraday": ("intraday", "tick", "minute"),
}


def _render_prompt(question: str) -> str:
    """Substitute literally.

    ``str.format`` cannot be used here: the template shows the model an example
    JSON object, and those braces would be read as format fields (``{"start"``
    raised ``KeyError``).  Escaping every brace would make the template harder to
    read and easy to break on the next edit.
    """
    return _PROMPT.replace("{question}", str(question or ""))


class ExtractionUnavailable(RuntimeError):
    """The configured backend could not be reached or returned unusable output."""


def backend_name() -> str:
    return os.getenv("RD_EXTRACTION_BACKEND", DEFAULT_BACKEND).strip().lower()


def enabled() -> bool:
    """Model-backed drafting is opt-in.

    Callers that leave it off fall back to corpus-derived resolution, which is
    instant and cannot invent.  Enabling it trades latency for vocabulary reach.
    """
    return os.getenv("RD_MODEL_DRAFTING", "").strip().lower() in {"1", "true", "yes", "on"}


def _key_file_candidates() -> list[str]:
    """Places the front-door env file may live, most explicit first.

    ``$HOME`` is deliberately not the only source: agent and sandbox shells
    override it, so ``~`` can resolve somewhere the config does not exist while
    the account's real home has it.  ``pwd`` reports the account home regardless
    of what ``HOME`` was set to.
    """
    paths: list[str] = []
    override = os.getenv("RD_FRONT_DOOR_ENV", "").strip()
    if override:
        paths.append(override)
    homes = [os.getenv("HOME", "").strip()]
    try:
        import pwd

        homes.append(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError):
        pass
    for home in homes:
        if home:
            paths.append(os.path.join(home, ".config/research-drive/front-door.env"))
    return list(dict.fromkeys(p for p in paths if p))


def _cursor_key() -> str:
    """Resolve the Cursor credential.

    The environment is authoritative -- the systemd unit supplies it via
    ``EnvironmentFile`` -- and the file scan is only a fallback for interactive
    runs.  Empty assignments are skipped rather than returned: ``.env.local``
    carries a blank ``CURSOR_API_KEY=`` which would otherwise authenticate as
    nobody and surface as a confusing auth error instead of a missing key.
    """
    key = os.getenv("CURSOR_API_KEY", "").strip()
    if key:
        return key
    for env_path in _key_file_candidates():
        try:
            with open(env_path, encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if stripped.startswith("export "):
                        stripped = stripped[len("export "):].lstrip()
                    if stripped.startswith("CURSOR_API_KEY="):
                        value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                        if value:
                            return value
        except OSError:
            continue
    return ""


def _run_cursor(question: str, model: str, timeout: float) -> str:
    binary = shutil.which("cursor-agent") or os.path.expanduser("~/.local/bin/cursor-agent")
    if not os.path.exists(binary):
        raise ExtractionUnavailable("cursor-agent not installed")
    key = _cursor_key()
    if not key:
        raise ExtractionUnavailable("CURSOR_API_KEY is empty")
    env = {**os.environ, "CURSOR_API_KEY": key}
    try:
        done = subprocess.run(
            [binary, "-p", _render_prompt(question), "--model", model,
             "--output-format", "text", "--trust"],
            capture_output=True, text=True, timeout=timeout, env=env, cwd="/tmp",
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionUnavailable(f"cursor-agent timed out after {timeout}s") from exc
    if done.returncode != 0:
        raise ExtractionUnavailable(f"cursor-agent failed: {done.stderr[:200]}")
    return done.stdout


def _run_local(question: str, model: str, timeout: float) -> str:
    url = os.getenv("RD_LOCAL_LLM_URL", "http://127.0.0.1:11434/api/chat")
    body = json.dumps({
        "model": model, "format": "json", "stream": False,
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": _render_prompt(question)}],
    }).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ExtractionUnavailable(f"local model unreachable: {exc}") from exc
    return (payload.get("message") or {}).get("content") or ""


def _parse_json_object(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a response that may carry stray prose."""
    stripped = re.sub(r"^```(?:json)?|```$", "", str(text or "").strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise ExtractionUnavailable(f"backend returned non-JSON: {stripped[:160]}")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ExtractionUnavailable(f"backend returned malformed JSON: {stripped[:160]}") from exc
    if isinstance(parsed, list):
        parsed = next((item for item in parsed if isinstance(item, dict)), {})
    if not isinstance(parsed, dict):
        raise ExtractionUnavailable("backend returned a non-object payload")
    return parsed


def ground_check(question: str, draft: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Drop asserted values the question does not textually support.

    Applied to every backend, including capable ones: a model being generally
    reliable is not evidence about this particular answer, and an unsupported
    dimension silently becomes a filter.
    """
    text = str(question or "").lower()
    checked: dict[str, dict[str, Any]] = {}
    for dimension, entry in (draft or {}).items():
        value = entry.get("value")

        if dimension == "time_range" and isinstance(value, dict):
            years = [str(v) for v in (value.get("start"), value.get("end")) if v]
            if years and not all(re.search(rf"\b{re.escape(y)}\b", text) for y in years):
                continue  # a year nobody wrote cannot constrain the search
        if dimension == "frequency" and isinstance(value, str):
            roots = _CADENCE_ROOTS.get(value.strip().lower(), ())
            if roots and not any(root in text for root in roots):
                continue  # cadence asserted with no textual basis

        checked[dimension] = entry
    return checked


def _normalize(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
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
        if isinstance(value, str):
            value = value.strip() or None
        if isinstance(value, dict):
            value = {k: v for k, v in value.items() if v not in (None, "")} or None
        if isinstance(value, list):
            value = [v for v in value if v not in (None, "")] or None
        if value is not None:
            draft[dimension] = {"value": value, "provenance": "drafted"}
    return draft


def extract_requirement(
    question: str, *, backend: str | None = None, model: str | None = None,
    timeout: float = 120.0,
) -> dict[str, dict[str, Any]]:
    """Extract requirement dimensions, then strip anything ungrounded."""
    text = str(question or "").strip()
    if not text:
        return {}
    chosen = (backend or backend_name()).lower()
    if chosen == "cursor":
        raw = _run_cursor(text, model or os.getenv("RD_CURSOR_MODEL", DEFAULT_CURSOR_MODEL), timeout)
    elif chosen in {"local", "ollama"}:
        raw = _run_local(text, model or os.getenv("RD_LOCAL_LLM_MODEL", DEFAULT_LOCAL_MODEL), timeout)
    else:
        raise ExtractionUnavailable(f"unknown extraction backend: {chosen}")
    return ground_check(text, _normalize(_parse_json_object(raw)))
