from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from quant_ai.config import REPO, AnalystConfig

BRIEF_JSON_SCHEMA = {
    "stance": "explore | watch | deploy_small | avoid",
    "conviction_1_to_5": "integer",
    "size_guidance": "string — e.g. 0-2% sleeve, paper only, full allocation",
    "primary_expression": "string — what to actually do",
    "best_quant_signal": "string — strategy name from evidence",
    "kill_conditions": ["list of strings"],
    "keep_conditions": ["list of strings"],
    "falsifiers": ["list of strings — what would prove thesis wrong"],
    "explain_vs_trade": "explain_only | trade_small | trade_core",
    "gate_verdict": "string — gates are inputs not veto; your judgment",
    "summary": "string — 2-3 sentences",
}


def load_env() -> None:
    for p in [REPO / ".env.local", REPO / ".env", REPO.parent / ".env.local", REPO.parent / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)


def pack_for_llm(pack: dict, brief: bool = False) -> dict:
    slim = {
        "country": pack.get("country"),
        "country_label": pack.get("country_label"),
        "date_range": pack.get("date_range"),
        "strategies": pack.get("strategies"),
        "promotion": pack.get("promotion"),
        "shock_correlations": pack.get("shock_correlations", [])[:6],
        "sample_articles": pack.get("sample_articles", [])[:6],
        "stock_universe_size": pack.get("stock_universe_size"),
    }
    if pack.get("portfolio_context"):
        slim["portfolio_context"] = pack["portfolio_context"]
    if pack.get("recent_week_explains"):
        slim["recent_week_explains"] = [
            {
                "week_end": x.get("week_end"),
                "return_1w": x.get("return_1w"),
                "move": x.get("move"),
                "narrative": x.get("narrative"),
                "macro_shocks": x.get("macro_shocks", [])[:3],
            }
            for x in pack["recent_week_explains"]
        ]
    if brief:
        slim["brief_schema"] = BRIEF_JSON_SCHEMA
    return slim


def ask_deepseek(system: str, user: str, model: str, max_tokens: int = 1600) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    body = json.dumps(
        {
            "model": model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        base_url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def _call_backend(
    system: str,
    user: str,
    backend: str,
    model: str,
    out_dir: Path | None,
    max_tokens: int,
    pack: dict | None = None,
) -> dict:
    load_env()
    errors: list[str] = []
    prompt = f"{system}\n\n{user}"

    if backend in {"auto", "deepseek"} and os.getenv("DEEPSEEK_API_KEY"):
        try:
            ds_model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            text = ask_deepseek(system, user, ds_model, max_tokens=max_tokens)
            return {"backend": "deepseek", "model": ds_model, "text": text, "errors": errors}
        except Exception as exc:
            errors.append(f"deepseek: {exc}")

    if backend in {"auto", "openai"} and os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI

            client = OpenAI()
            resp = client.chat.completions.create(
                model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.3,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ""
            return {"backend": "openai", "model": model, "text": text, "errors": errors}
        except Exception as exc:
            errors.append(f"openai: {exc}")

    if backend in {"auto", "codex"}:
        prompt_path = (out_dir or REPO / "backtests/outputs/quant_ai") / "llm_prompt.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["codex", "exec", "-"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(REPO),
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return {"backend": "codex", "model": "codex-exec", "text": proc.stdout.strip(), "errors": errors}
            errors.append(f"codex rc={proc.returncode} stderr={proc.stderr[:800]}")
        except Exception as exc:
            errors.append(f"codex: {exc}")

    p = pack or {}
    fallback = (
        f"## Executive summary\nLLM backends unavailable ({errors}).\n\n"
        f"Promotion passed: {p.get('promotion', {}).get('n_passed', 0)}/"
        f"{p.get('promotion', {}).get('n_strategies', 0)}.\n"
        "See evidence_pack.json for full metrics."
    )
    return {"backend": "fallback", "model": None, "text": fallback, "errors": errors}


def _system_prompt(cfg: AnalystConfig, brief: bool) -> str:
    base = (
        f"You are a {cfg.analyst_persona} advising a quant desk. "
        "Use ONLY the evidence JSON. Separate facts from narrative. "
        "Promotion gates (DSR, PBO, alpha t-stat) are INPUTS — not automatic vetoes. "
        "A strategy can fail gates yet warrant a small exploratory sleeve if economics and falsifiers are clear. "
        "Conversely, passing gates does not mean full size. Be direct; no hype."
    )
    if brief:
        base += (
            " You MUST output a fenced ```json block with the decision brief matching brief_schema, "
            "then markdown sections for reasoning."
        )
    return base


def _user_prompt(pack: dict, cfg: AnalystConfig, brief: bool) -> str:
    slim = pack_for_llm(pack, brief=brief)
    if brief:
        sections = (
            "## Decision brief (JSON block first)\n"
            "## Executive summary\n"
            "## What the data shows\n"
            "## Best signal & sizing\n"
            "## Gates vs judgment\n"
            "## Recent weeks (explain layer)\n"
            "## Falsifiers & kill switches\n"
            "## Tradable vs explain-only"
        )
    else:
        sections = (
            "## Executive summary\n## What the data actually shows\n"
            "## Best usable signal (if any)\n## Why gates passed/failed\n"
            "## Country-specific story\n## Next 3 pre-registered tests\n"
            "## Tradable vs explain-only verdict"
        )
    return (
        f"Analyze {cfg.country_label} ({cfg.country}) news-to-market evidence.\n\n"
        f"EVIDENCE_JSON:\n{json.dumps(slim, indent=2, default=str)}\n\n"
        f"Structure your reply:\n{sections}"
    )


def synthesize_analysis(
    pack: dict,
    cfg: AnalystConfig,
    backend: str = "auto",
    model: str = "",
    out_dir: Path | None = None,
    max_tokens: int = 1600,
) -> dict:
    system = _system_prompt(cfg, brief=False)
    user = _user_prompt(pack, cfg, brief=False)
    return _call_backend(system, user, backend, model, out_dir, max_tokens, pack=pack)


def synthesize_brief(
    pack: dict,
    cfg: AnalystConfig,
    backend: str = "auto",
    model: str = "",
    out_dir: Path | None = None,
    max_tokens: int = 2000,
) -> dict:
    system = _system_prompt(cfg, brief=True)
    user = _user_prompt(pack, cfg, brief=True)
    result = _call_backend(system, user, backend, model, out_dir, max_tokens, pack=pack)
    result["decision_brief"] = extract_brief_json(result.get("text", ""))
    return result


def extract_brief_json(text: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
