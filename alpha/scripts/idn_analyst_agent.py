"""Multi-turn IDX analyst agent — LLM calls tools to compute and reason, then picks."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from idn_analyst_tools import (
    AnalystDataContext,
    TOOL_SPECS,
    deterministic_analyst_picks,
    execute_tool,
    tools_prompt_block,
)
from idn_operator_llm import OPERATOR_DECISION_SCHEMA, extract_operator_decision

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)

TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)


def _system_prompt(*, liquid: list[str], as_of: str | None) -> str:
    return (
        "You are an Indonesia equity analyst with LIVE TOOLS — not a summarizer.\n"
        "You MUST call tools to obtain every number you cite. Do not invent metrics.\n"
        "Workflow:\n"
        "  1) get_regime + factor_summary\n"
        "  2) screen_universe (momentum and/or mentions)\n"
        "  3) analyze_ticker / compare_tickers / check_retail_signals on finalists\n"
        "  4) get_sentiment on live names when relevant\n"
        "  5) Output final decision JSON when ready\n\n"
        "To call a tool, emit EXACTLY:\n"
        "<tool_call>{\"tool\": \"analyze_ticker\", \"args\": {\"ticker\": \"BBCA.JK\"}}</tool_call>\n"
        "You may emit multiple tool_call blocks in one turn.\n"
        "After tool results arrive, continue analysis. Minimum 3 tool calls before final picks.\n"
        f"Allowed tickers: {sorted(liquid)}\n"
        f"Analysis as_of: {as_of or 'live'}\n\n"
        f"Available tools:\n{tools_prompt_block()}\n\n"
        "Final output MUST include fenced ```json matching this schema:\n"
        f"{json.dumps(OPERATOR_DECISION_SCHEMA, indent=2)}\n"
        "In final picks, reference computed fields from tool results in reason strings."
    )


def _parse_tool_calls(text: str) -> list[dict[str, Any]]:
    calls = []
    for m in TOOL_CALL_RE.finditer(text):
        try:
            payload = json.loads(m.group(1))
            if "tool" in payload:
                calls.append({"tool": payload["tool"], "args": payload.get("args") or {}})
        except json.JSONDecodeError:
            continue
    return calls


def _ask_llm(messages: list[dict[str, str]], backend: str, model: str, max_tokens: int) -> dict[str, Any]:
    from quant_ai.llm import _call_backend

    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_parts = [m["content"] for m in messages if m["role"] != "system"]
    user = "\n\n".join(user_parts)
    return _call_backend(system, user, backend, model, None, max_tokens, pack=None)


def run_analyst_agent(
    *,
    liquid: list[str],
    as_of: str | None = None,
    seed_tickers: list[str] | None = None,
    rules_context: dict[str, Any] | None = None,
    backend: str = "auto",
    model: str = "",
    max_turns: int = 10,
    max_tokens: int = 2500,
) -> dict[str, Any]:
    ctx = AnalystDataContext(liquid=liquid, as_of=pd.Timestamp(as_of) if as_of else None)
    trace: list[dict[str, Any]] = []
    as_of_str = str(ctx.last_week.date()) if ctx.last_week is not None else as_of

    seed_note = ""
    if seed_tickers:
        seed_note = f"Rules engine seeds to investigate: {seed_tickers}\n"
    if rules_context:
        seed_note += f"Rules context: {json.dumps(rules_context, default=str)[:2000]}\n"

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _system_prompt(liquid=liquid, as_of=as_of_str)},
        {
            "role": "user",
            "content": (
                f"{seed_note}"
                "Perform thorough ticker analysis using tools, then pick 3-5 names for an aggressive weekly book."
            ),
        },
    ]

    final_text = ""
    tool_calls_total = 0
    for turn in range(max_turns):
        result = _ask_llm(messages, backend, model, max_tokens)
        text = result.get("text", "") or ""
        final_text = text
        trace.append({"turn": turn, "type": "assistant", "backend": result.get("backend"), "text": text[:8000]})

        decision = extract_operator_decision(text)
        calls = _parse_tool_calls(text)
        if decision and tool_calls_total >= 3:
            trace.append({"turn": turn, "type": "decision", "decision": decision})
            return {
                "mode": "llm_agent",
                "backend": result.get("backend"),
                "model": result.get("model"),
                "as_of": as_of_str,
                "tool_calls": tool_calls_total,
                "turns": turn + 1,
                "operator_decision": decision,
                "text": text,
                "trace": trace,
                "errors": result.get("errors", []),
            }

        if not calls:
            if decision and tool_calls_total < 3:
                messages.append(
                    {
                        "role": "user",
                        "content": "You must call at least 3 tools before finalizing. Continue analysis.",
                    }
                )
                continue
            messages.append(
                {
                    "role": "user",
                    "content": "Call tools using <tool_call>{...}</tool_call> or output final ```json decision.",
                }
            )
            continue

        tool_results = []
        for call in calls[:6]:
            tool_calls_total += 1
            out = execute_tool(ctx, call["tool"], call["args"])
            tool_results.append({"tool": call["tool"], "args": call["args"], "result": out})
            trace.append({"turn": turn, "type": "tool", **tool_results[-1]})

        messages.append({"role": "assistant", "content": text})
        messages.append(
            {
                "role": "user",
                "content": "TOOL_RESULTS:\n"
                + json.dumps(tool_results, indent=2, default=str)
                + "\nContinue analysis or output final ```json decision.",
            }
        )

    # Fallback: deterministic tool pipeline
    det = deterministic_analyst_picks(ctx, seed_tickers=seed_tickers, max_picks=5)
    fallback_decision = _decision_from_deterministic(det)
    trace.append({"type": "fallback", "deterministic": det})
    return {
        "mode": "llm_agent_fallback",
        "backend": None,
        "as_of": as_of_str,
        "tool_calls": tool_calls_total,
        "turns": max_turns,
        "operator_decision": fallback_decision,
        "text": final_text,
        "trace": trace,
        "errors": ["max_turns_exceeded"],
    }


def _decision_from_deterministic(det: dict[str, Any]) -> dict[str, Any]:
    picks = []
    for p in det.get("picks", [])[:5]:
        picks.append(
            {
                "ticker": p["ticker"],
                "weight_hint": max(p.get("score", 0.1), 0.1),
                "primary_driver": "tool_score",
                "reason": "; ".join(p.get("reasons", [])),
            }
        )
    return {
        "stance": "aggressive",
        "conviction_1_to_5": 3,
        "final_picks": picks,
        "avoid": [],
        "watch": [],
        "evidence_used": ["tool_pipeline"],
        "evidence_missing": [],
        "summary": "Deterministic tool-score fallback",
    }


def synthesize_analyst_agent(
    manifest: dict[str, Any],
    *,
    liquid: list[str],
    backend: str = "auto",
    model: str = "",
    out_dir: Path | None = None,
    max_turns: int = 10,
    max_tokens: int = 2800,
) -> dict[str, Any]:
    """Run tool-calling analyst agent (computes via tools, not pre-baked evidence dump)."""
    seed = [p.get("ticker") for p in manifest.get("pick", []) if p.get("ticker")]
    result = run_analyst_agent(
        liquid=liquid,
        as_of=None,
        seed_tickers=seed,
        rules_context={
            "pick": manifest.get("pick", []),
            "avoid": manifest.get("avoid", []),
            "watch": manifest.get("watch", []),
        },
        backend=backend,
        model=model,
        max_turns=max_turns,
        max_tokens=max_tokens,
    )
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "analysis_trace.json").write_text(json.dumps(result.get("trace", []), indent=2, default=str) + "\n", encoding="utf-8")
        (out_dir / "agent_result.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    return result
