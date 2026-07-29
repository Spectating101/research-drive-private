#!/usr/bin/env python3
"""Adversarial first-turn acceptance battery for the Synthesis agent.

The battery is read/reason-only. It creates chat sessions but never authorizes
collection, execution, materialisation, archive promotion, or registration.
Provider/runtime failures are reported separately from reasoning-contract
failures so an outage cannot be mistaken for a weak answer.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from sharpe_kernel.paths import repo_root_from_file

REPO = repo_root_from_file(__file__)
DEFAULT_CASES = REPO / "drive/config/synthesis_acceptance_cases.json"

_PROVIDER_ACTIONS = frozenset(
    {"composer_error", "composer_unavailable", "composer_pending"}
)
_FORBIDDEN_EXECUTION_CLAIMS = (
    re.compile(r"\b(?:i|we|the system)\s+(?:have\s+)?(?:collected|executed|materialised|materialized|registered)\b", re.I),
    re.compile(r"\b(?:is|are|now)\s+query[- ]ready\b", re.I),
    re.compile(r"\b(?:collection|execution|materialisation|materialization)\s+(?:is\s+)?complete\b", re.I),
)


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"no Synthesis acceptance cases in {path}")
    return [dict(row) for row in cases if isinstance(row, dict)]


def _group_hits(text: str, groups: list[list[str]]) -> list[dict[str, Any]]:
    lowered = text.lower()
    out: list[dict[str, Any]] = []
    for group in groups:
        terms = [str(term).strip().lower() for term in group if str(term).strip()]
        hits = [term for term in terms if term in lowered]
        out.append({"terms": terms, "hits": hits, "ok": bool(hits)})
    return out


def evaluate_response(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Deterministically validate the Synthesis first-turn contract."""
    reply = str(result.get("reply") or "").strip()
    artifacts = result.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    action = str(result.get("action") or artifacts.get("action") or "").strip()

    if action in _PROVIDER_ACTIONS:
        return {
            "id": case.get("id"),
            "title": case.get("title"),
            "outcome": "provider_failed",
            "action": action,
            "provider_error": str(artifacts.get("error") or artifacts.get("reason") or ""),
            "reply": reply,
            "checks": [],
        }

    asset_checks = _group_hits(
        reply,
        [list(group) for group in case.get("expected_asset_groups") or []],
    )
    risk_checks = _group_hits(
        reply,
        [list(group) for group in case.get("required_risk_groups") or []],
    )
    question_count = reply.count("?")
    forbidden = [
        pattern.pattern
        for pattern in _FORBIDDEN_EXECUTION_CLAIMS
        if pattern.search(reply)
    ]
    checks = [
        {"name": "usable_reply", "ok": len(reply) >= 120, "observed": len(reply)},
        {
            "name": "named_held_evidence",
            "ok": bool(asset_checks) and all(row["ok"] for row in asset_checks),
            "groups": asset_checks,
        },
        {
            "name": "explicit_validity_risks",
            "ok": bool(risk_checks) and all(row["ok"] for row in risk_checks),
            "groups": risk_checks,
        },
        {
            "name": "one_clarification_question",
            "ok": question_count == 1,
            "observed": question_count,
        },
        {
            "name": "no_execution_claim",
            "ok": not forbidden,
            "matched_patterns": forbidden,
        },
        {
            "name": "provisional_language",
            "ok": any(
                marker in reply.lower()
                for marker in (
                    "provisional",
                    "propose",
                    "candidate",
                    "proxy",
                    "could",
                    "would",
                )
            ),
        },
    ]
    passed = all(bool(check.get("ok")) for check in checks)
    return {
        "id": case.get("id"),
        "title": case.get("title"),
        "outcome": "passed" if passed else "contract_failed",
        "action": action,
        "reply": reply,
        "checks": checks,
    }


class SynthesisAcceptanceClient:
    def __init__(self, base_url: str, *, timeout: float = 150.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar)
        )
        self.origin = self.base_url

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": self.origin,
            },
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def open_session(self) -> None:
        self._post("/library/desk/session", {})

    def run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            "/library/chat",
            {
                "message": str(case.get("request") or ""),
                "rail_context": {
                    "tab": "synthesis",
                    "mode": "define",
                    "entity": {
                        "kind": "synthesis_project",
                        "id": f"acceptance:{case.get('id')}",
                        "title": str(case.get("title") or case.get("id") or ""),
                    },
                    "actions": [
                        "clarify_construct",
                        "inspect_library",
                        "propose_proxy",
                    ],
                },
            },
        )


def run_battery(
    base_url: str,
    *,
    cases_path: Path = DEFAULT_CASES,
    case_ids: set[str] | None = None,
    timeout: float = 150.0,
) -> dict[str, Any]:
    cases = load_cases(cases_path)
    if case_ids:
        cases = [case for case in cases if str(case.get("id")) in case_ids]
    if not cases:
        raise ValueError("no selected Synthesis acceptance cases")

    client = SynthesisAcceptanceClient(base_url, timeout=timeout)
    started = time.time()
    rows: list[dict[str, Any]] = []
    try:
        client.open_session()
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {
            "contract": "synthesis_first_turn",
            "base_url": base_url,
            "outcome": "transport_failed",
            "error": str(exc),
            "cases": [],
        }

    for case in cases:
        case_started = time.time()
        try:
            raw = client.run_case(case)
            evaluated = evaluate_response(case, raw)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            evaluated = {
                "id": case.get("id"),
                "title": case.get("title"),
                "outcome": "transport_failed",
                "error": str(exc),
                "checks": [],
            }
        evaluated["elapsed_ms"] = int((time.time() - case_started) * 1000)
        rows.append(evaluated)

    outcomes = {
        name: sum(1 for row in rows if row.get("outcome") == name)
        for name in ("passed", "contract_failed", "provider_failed", "transport_failed")
    }
    return {
        "contract": "synthesis_first_turn",
        "base_url": base_url,
        "elapsed_ms": int((time.time() - started) * 1000),
        "selected_cases": len(rows),
        "outcomes": outcomes,
        "outcome": "passed" if outcomes["passed"] == len(rows) else "failed",
        "cases": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the read/reason-only Synthesis acceptance battery"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=150.0)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = run_battery(
        args.base_url,
        cases_path=args.cases,
        case_ids=set(args.case) or None,
        timeout=args.timeout,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if report.get("outcome") == "passed":
        return 0
    if (report.get("outcomes") or {}).get("provider_failed"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
