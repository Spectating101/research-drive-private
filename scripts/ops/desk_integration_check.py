#!/usr/bin/env python3
"""Full-stack desk integration check — API, registry, profile, env (no secret values)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
API = os.environ.get("YZU_API_URL", "http://127.0.0.1:8765")
UI = os.environ.get("YZU_DESK_URL", "http://127.0.0.1:5178")
FACULTY_EMAIL = os.environ.get("DESK_TEST_EMAIL", "drkong@saturn.yzu.edu.tw")


def get_json(path: str, *, base: str = API, timeout: float = 15) -> dict:
    with urllib.request.urlopen(f"{base}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def _load_env_files() -> list[str]:
    candidates = [
        Path.home() / ".env.local",
        _REPO.parent / ".env.local",
        _REPO / ".env.local",
    ]
    loaded: list[str] = []
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        loaded.append(str(path))
    return loaded


def check_env() -> dict:
    paths = _load_env_files()
    cursor = bool(os.environ.get("CURSOR_API_KEY", "").strip())
    brain = os.environ.get("DESK_BRAIN", "")
    return {
        "name": "env_cursor_composer",
        "ok": cursor,
        "brain": brain or "(default)",
        "env_files": paths,
        "note": "CURSOR_API_KEY loaded" if cursor else "Set CURSOR_API_KEY in .env.local",
    }


def main() -> int:
    report: dict = {"checks": [], "api": API, "ui": UI}

    report["checks"].append(check_env())

    try:
        health = get_json("/health?live=1")
    except urllib.error.URLError as exc:
        report["checks"].append(
            {
                "name": "api_health",
                "ok": False,
                "error": str(exc),
                "hint": "bash drive/scripts/run_yzu_cluster.sh",
            }
        )
        print(json.dumps(report, indent=2))
        return 2

    desk = health.get("desk") or {}
    report["checks"].append(
        {
            "name": "api_health",
            "ok": health.get("status") == "ok",
            "status": health.get("status"),
            "datasets": health.get("datasets"),
            "brain": desk.get("brain"),
            "composer_configured": desk.get("composer_configured"),
        }
    )

    try:
        ds = get_json("/datasets")
        n = len(ds.get("datasets") or [])
        report["checks"].append({"name": "registry_datasets", "ok": n >= 1, "count": n})
    except urllib.error.URLError as exc:
        report["checks"].append({"name": "registry_datasets", "ok": False, "error": str(exc)})

    try:
        prof = get_json(f"/library/faculty/profile?email={urllib.parse.quote(FACULTY_EMAIL)}")
        report["checks"].append(
            {
                "name": "faculty_profile",
                "ok": bool(prof.get("found")),
                "email": FACULTY_EMAIL,
                "faculty_name": (prof.get("profile") or {}).get("name_en"),
            }
        )
    except urllib.error.URLError as exc:
        report["checks"].append({"name": "faculty_profile", "ok": False, "error": str(exc)})

    try:
        via_ui = get_json("/api/datasets", base=UI, timeout=20)
        ui_n = len(via_ui.get("datasets") or [])
        report["checks"].append(
            {"name": "ui_proxy_datasets", "ok": ui_n >= 1, "count": ui_n, "base": UI}
        )
    except (urllib.error.URLError, TimeoutError) as exc:
        report["checks"].append(
            {
                "name": "ui_proxy_datasets",
                "ok": False,
                "error": str(exc),
                "hint": "npm run dev on :5178 or run_yzu_cluster.sh",
            }
        )

    try:
        discover = get_json(f"/library/discover?q=TWSE&limit=3&email={urllib.parse.quote(FACULTY_EMAIL)}")
        report["checks"].append(
            {
                "name": "discover_search",
                "ok": discover.get("total", 0) >= 0,
                "total": discover.get("total"),
            }
        )
    except urllib.error.URLError as exc:
        report["checks"].append({"name": "discover_search", "ok": False, "error": str(exc)})

    out_path = _REPO / "docs/status/generated/desk_integration_check.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    core = [c for c in report["checks"] if c["name"] != "discover_search"]
    ok = all(c.get("ok") for c in core)
    passed = sum(1 for c in report["checks"] if c.get("ok"))
    print(json.dumps(report, indent=2))
    print(f"\nSummary: {passed}/{len(report['checks'])} passed → {out_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
