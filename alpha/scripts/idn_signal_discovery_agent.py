"""LLM agent for reverse-engineering IDX price-movement signals via tool calls."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from idn_signal_discovery_tools import (
    DiscoveryContext,
    deterministic_discovery_scan,
    discovery_tools_prompt,
    execute_discovery_tool,
)

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)

TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL | re.IGNORECASE)

DISCOVERY_SCHEMA = {
    "mission": "reverse_engineer_price_movement",
    "best_signals": [
        {
            "signal": "feature name",
            "direction": "long_top | fade",
            "target": "fwd_return_1w | fwd_return_4w",
            "evidence": "cite tool results: IC t, spread t, OOS stability",
            "verdict": "reliable | conditional | unreliable",
            "detection_rule": "plain English rule to implement",
        }
    ],
    "failed_signals": [{"signal": "name", "why": "string"}],
    "retail_rules_validated": [{"strategy_id": "id", "verdict": "string"}],
    "recommended_detector_stack": ["ordered list of rules/signals for live pipeline"],
    "falsifiers": ["what would invalidate findings"],
    "next_experiments": ["data or tests to run next"],
    "summary": "2-4 sentences",
}


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


def _extract_discovery_report(text: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "best_signals" not in data:
        return None
    return data


def _system_prompt() -> str:
    return (
        "You are a quant researcher REVERSE-ENGINEERING what predicts Indonesian stock price moves.\n"
        "You do NOT pick stocks for next week — you discover DETECTION RULES with statistical evidence.\n\n"
        "Method:\n"
        "  1) list_features → scan_candidates (full, train, oos_holdout)\n"
        "  2) horse_race promising signals on fwd_return_1w and fwd_return_4w\n"
        "  3) oos_stability on top candidates — reject IS-only fits\n"
        "  4) list_retail_strategies + test_retail_strategy on TA rules\n"
        "  5) Synthesize detection rules that WORK OOS (2024+)\n\n"
        "Call tools via:\n"
        '<tool_call>{"tool": "scan_candidates", "args": {"era": "oos_holdout"}}</tool_call>\n'
        "Minimum 5 tool calls before final report. Every claim needs a tool result.\n\n"
        f"Tools:\n{discovery_tools_prompt()}\n\n"
        "Final output: fenced ```json matching:\n"
        f"{json.dumps(DISCOVERY_SCHEMA, indent=2)}"
    )


def run_discovery_agent(
    *,
    liquid: list[str] | None = None,
    backend: str = "auto",
    model: str = "",
    max_turns: int = 12,
    max_tokens: int = 3000,
) -> dict[str, Any]:
    from quant_ai.llm import _call_backend

    ctx = DiscoveryContext(liquid=liquid)
    trace: list[dict[str, Any]] = []
    messages = [
        {"role": "system", "content": _system_prompt()},
        {
            "role": "user",
            "content": (
                "Reverse-engineer the best price-movement detectors for liquid IDX. "
                "Prioritize signals that survive 2024+ OOS. Output detection rules, not stock picks."
            ),
        },
    ]
    tool_calls_total = 0
    final_text = ""

    for turn in range(max_turns):
        system = messages[0]["content"]
        user = "\n\n".join(m["content"] for m in messages[1:])
        result = _call_backend(system, user, backend, model, None, max_tokens, pack=None)
        text = result.get("text", "") or ""
        final_text = text
        trace.append({"turn": turn, "type": "assistant", "text": text[:10000]})

        report = _extract_discovery_report(text)
        calls = _parse_tool_calls(text)
        if report and tool_calls_total >= 5:
            trace.append({"type": "report", "report": report})
            return {
                "mode": "llm_discovery",
                "backend": result.get("backend"),
                "tool_calls": tool_calls_total,
                "turns": turn + 1,
                "discovery_report": report,
                "text": text,
                "trace": trace,
            }

        if not calls:
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {"role": "user", "content": "Use <tool_call> to run tests, or output final ```json discovery report."}
            )
            continue

        tool_results = []
        for call in calls[:8]:
            tool_calls_total += 1
            out = execute_discovery_tool(ctx, call["tool"], call["args"])
            tool_results.append({"tool": call["tool"], "args": call["args"], "result": out})
            trace.append({"turn": turn, "type": "tool", **tool_results[-1]})

        messages.append({"role": "assistant", "content": text})
        messages.append(
            {
                "role": "user",
                "content": "TOOL_RESULTS:\n"
                + json.dumps(tool_results, indent=2, default=str)
                + "\nContinue reverse-engineering or output final ```json discovery report.",
            }
        )

    det = deterministic_discovery_scan(ctx)
    trace.append({"type": "fallback", "deterministic": det})
    return {
        "mode": "llm_discovery_fallback",
        "tool_calls": tool_calls_total,
        "turns": max_turns,
        "discovery_report": _report_from_deterministic(det),
        "deterministic_scan": det,
        "text": final_text,
        "trace": trace,
        "errors": ["max_turns_exceeded"],
    }


def _report_from_deterministic(det: dict[str, Any]) -> dict[str, Any]:
    best = det.get("best_candidates") or {}
    signals = []
    for c in best.get("oos_top", [])[:3]:
        signals.append(
            {
                "signal": c.get("signal"),
                "direction": c.get("direction"),
                "target": "fwd_return_1w",
                "evidence": f"spread_t={c.get('spread_t')} ic_t={c.get('ic_t')} era=oos_holdout",
                "verdict": c.get("verdict"),
                "detection_rule": f"{'Long' if c.get('direction')=='long_top' else 'Fade'} top quintile on {c.get('signal')}",
            }
        )
    return {
        "mission": "reverse_engineer_price_movement",
        "best_signals": signals,
        "failed_signals": [{"signal": "mom_4w", "why": "typically unreliable OOS unless combined"}],
        "retail_rules_validated": [{"strategy_id": s, "verdict": "reliable"} for s in best.get("retail_reliable", [])],
        "recommended_detector_stack": best.get("retail_reliable", []) + best.get("oos_stable_signals", []),
        "falsifiers": ["2024+ entity weeks thin", "momentum crowding"],
        "next_experiments": ["accumulate trending history", "test composite score live"],
        "summary": "Deterministic scan fallback — run LLM agent for deeper synthesis.",
    }
