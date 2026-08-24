#!/usr/bin/env python3
"""Composer + MCP synthesis smoke — real POST /library/chat with CURSOR_API_KEY."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8765"
EMAIL = "drkong@saturn.yzu.edu.tw"

TURNS = [
    (
        "Synthesize our stablecoin trust and engagement data — community growth, "
        "security history, GDELT news, DeFiLlama adoption. Give a short professor answer."
    ),
    "Which entities have the strongest community growth and code security scores?",
    "How many weekly panel rows and sources does the trust engagement cluster cover?",
]

SYNTHESIS_TOOL_MARKERS = (
    "research_synthesis_run",
    "research_synthesis_list_profiles",
    "stablecoin_trust_engagement",
)
EMPTY_FALLBACK_MARKERS = (
    "did not get a final answer back",
    "Composer could not complete that turn",
    "missing CURSOR_API_KEY",
    "composer_unavailable",
)


def post_json(path: str, body: dict, *, timeout: float = 360) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def warm_session(session_id: str = "") -> str:
    body: dict = {"user_email": EMAIL, "background": True}
    if session_id:
        body["session_id"] = session_id
    out = post_json("/library/desk/warm", body)
    sid = str(out.get("session_id") or session_id or "")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if out.get("primed"):
            return sid
        time.sleep(1)
        try:
            sess = json.loads(
                urllib.request.urlopen(f"{API}/library/chat/{sid}", timeout=10).read()
            )
            state = sess.get("state") or {}
            if state.get("desk_primed") and state.get("cursor_agent_id"):
                return sid
            if not state.get("desk_priming") and not state.get("desk_primed"):
                break
        except urllib.error.URLError:
            break
    return sid


def post_chat(message: str, session_id: str = "") -> dict:
    body: dict = {"message": message, "user_email": EMAIL}
    if session_id:
        body["session_id"] = session_id
    return post_json("/library/chat", body)


def _tool_calls(payload: dict) -> list[str]:
    names: list[str] = []
    for block in payload.get("tool_calls") or []:
        if isinstance(block, dict):
            name = block.get("name") or block.get("tool")
            if name:
                names.append(str(name))
    arts = payload.get("artifacts") or {}
    for step in arts.get("steps") or []:
        if isinstance(step, dict) and step.get("tool"):
            names.append(str(step["tool"]))
    synth = arts.get("synthesis")
    if isinstance(synth, dict) and synth.get("profile_id"):
        names.append("research_synthesis_run")
    return names


def score_turn(turn_idx: int, out: dict) -> dict:
    reply = out.get("reply") or ""
    arts = out.get("artifacts") or {}
    brain = arts.get("brain")
    action = str(out.get("action") or arts.get("action") or "")
    tools = _tool_calls(out)
    words = len(reply.split())

    flags: list[str] = []
    if any(m in reply for m in EMPTY_FALLBACK_MARKERS):
        flags.append("empty_fallback")
    if brain != "cursor_composer":
        flags.append("wrong_brain")
    if action not in {"composer", "none"}:
        flags.append(f"action_{action}")

    synthesis_called = any(
        t.startswith("research_synthesis") for t in tools
    ) or any(m in json.dumps(out, default=str) for m in SYNTHESIS_TOOL_MARKERS)

    substance = any(
        token in reply.lower()
        for token in (
            "community",
            "security",
            "gdelt",
            "defillama",
            "entity",
            "panel",
            "stablecoin",
            "weekly",
            "source",
        )
    )

    if turn_idx == 1 and not synthesis_called and not substance:
        flags.append("no_synthesis_tool")
    if turn_idx >= 2 and words < 15:
        flags.append("too_short")

    if turn_idx == 1 and not substance:
        flags.append("no_substance")

    ok = not flags and words >= 20 and brain == "cursor_composer"
    return {
        "words": words,
        "action": action,
        "brain": brain,
        "tools": tools,
        "synthesis_called": synthesis_called,
        "flags": flags,
        "pass": ok,
        "preview": reply[:320].replace("\n", " "),
        "synthesis_artifact": arts.get("synthesis"),
    }


def main() -> int:
    try:
        health = urllib.request.urlopen(f"{API}/health", timeout=5).read()
        if b"ok" not in health.lower() and b"healthy" not in health.lower():
            print(f"WARN: unexpected health: {health[:120]!r}")
    except urllib.error.URLError as exc:
        print(f"FAIL: API not reachable at {API}: {exc}")
        print("Start with: bash drive/scripts/run_research_query_engine.sh")
        return 2

    session_id = warm_session()
    results: list[dict] = []
    print(f"API={API} email={EMAIL} session={session_id}\n")

    for i, msg in enumerate(TURNS, 1):
        print(f"--- turn {i} ---")
        print(f"Q: {msg}")
        t0 = time.time()
        try:
            out = post_chat(msg, session_id)
        except urllib.error.URLError as exc:
            print(f"FAIL: {exc}")
            return 1
        dt = time.time() - t0
        session_id = out.get("session_id") or session_id
        sc = score_turn(i, out)
        sc["seconds"] = round(dt, 1)
        sc["session_id"] = session_id
        results.append({"question": msg, **sc})
        status = "PASS" if sc["pass"] else "FAIL"
        print(
            f"{status} time={sc['seconds']}s brain={sc['brain']} "
            f"tools={sc['tools']} synthesis={sc['synthesis_called']} flags={sc['flags']}"
        )
        if sc.get("synthesis_artifact"):
            print(f"synthesis artifact: {json.dumps(sc['synthesis_artifact'], default=str)[:200]}…")
        print(f"reply: {sc['preview']}…\n")

    out_path = (
        Path(__file__).resolve().parents[2]
        / "docs/status/generated/desk_synthesis_chat_smoke.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"session_id": session_id, "turns": results}, indent=2),
        encoding="utf-8",
    )
    ok = sum(1 for r in results if r.get("pass"))
    print(f"Summary: {ok}/{len(results)} passed → {out_path}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
