#!/usr/bin/env python3
"""Repeated Research Drive chat smoke — quality heuristics for professor-facing replies."""

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
    "What TWSE data do we already have in the vault?",
    "Give me a short plain answer — no paths or registry IDs.",
    "Show 3 sample rows from daily trading if you can.",
]

EMPTY_FALLBACK_MARKERS = (
    "did not get a final answer back",
    "Composer could not complete that turn",
    "CURSOR_API_KEY",
)


def post_json(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def post_chat(message: str, session_id: str = "") -> dict:
    body: dict = {"message": message, "user_email": EMAIL}
    if session_id:
        body["session_id"] = session_id
    return post_json("/library/chat", body)


def warm_session(session_id: str = "") -> str:
    body: dict = {"user_email": EMAIL, "background": True}
    if session_id:
        body["session_id"] = session_id
    out = post_json("/library/desk/warm", body)
    sid = str(out.get("session_id") or session_id or "")
    deadline = time.monotonic() + 75
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


def score_reply(reply: str, action: str, brain: str | None) -> dict:
    text = reply or ""
    words = len(text.split())
    bad_patterns = [
        (r"research_\w+", "snake_tool"),
        (r"local_ready", "internal_flag"),
        (r"data_lake/", "raw_path"),
        (r"download\s*#\d", "numbered_command"),
        (r"for\s+drkong@", "email_opening"),
        (r"found\s+\d+\s+leads", "old_search_template"),
    ]
    flags = [name for pat, name in bad_patterns if re.search(pat, text, re.I)]
    if any(marker in text for marker in EMPTY_FALLBACK_MARKERS):
        flags.append("empty_fallback")
    good = (
        words >= 20
        and words <= 350
        and action in {"composer", "none"}
        and brain == "cursor_composer"
        and "empty_fallback" not in flags
    )
    natural = not flags and words <= 500
    return {
        "words": words,
        "action": action,
        "brain": brain,
        "flags": flags,
        "natural_heuristic": natural and good,
        "preview": text[:280].replace("\n", " "),
    }


def main() -> int:
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
        arts = out.get("artifacts") or {}
        brain = arts.get("brain")
        action = out.get("action") or arts.get("action")
        reply = out.get("reply") or ""
        sc = score_reply(reply, str(action), brain)
        sc["seconds"] = round(dt, 1)
        sc["session_id"] = session_id
        results.append({"question": msg, **sc})
        status = "PASS" if sc.get("natural_heuristic") else "FAIL"
        print(f"{status} time={sc['seconds']}s action={action} brain={brain} words={sc['words']} flags={sc['flags']}")
        print(f"reply: {sc['preview']}…\n")

    out_path = Path(__file__).resolve().parents[2] / "docs/status/generated/desk_chat_smoke_loop.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"session_id": session_id, "turns": results}, indent=2), encoding="utf-8")
    ok = sum(1 for r in results if r.get("natural_heuristic"))
    print(f"Summary: {ok}/{len(results)} passed natural heuristic → {out_path}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
