#!/usr/bin/env python3
"""CLI sketch preview — renders docs/design/WIREFRAME_V2_FROZEN.md wireframes.

  python3 scripts/rd_layout_preview.py all --pager
  python3 scripts/rd_layout_preview.py library
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "docs/design/WIREFRAME_V2_FROZEN.md"

PAGES = (
    "new_menu", "detail", "ask",
    "home", "library", "cluster", "browse",
    "resources", "profile", "settings", "preview", "flows",
)
ALIASES = {"analyze": "preview", "new": "new_menu", "detail_panel": "detail", "ask_rail": "ask"}
HEADINGS = {
    "new_menu": "## NEW MENU",
    "detail": "## DETAIL PANEL",
    "ask": "## ASK RAIL",
    "home": "## HOME",
    "library": "## LIBRARY",
    "cluster": "## CLUSTER",
    "browse": "## BROWSE",
    "resources": "## RESOURCES",
    "profile": "## PROFILE",
    "settings": "## SETTINGS",
    "preview": "## PREVIEW",
    "flows": "## FLOWS",
}


def load_wireframes() -> dict[str, str]:
    text = FROZEN.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for key, heading in HEADINGS.items():
        start = text.index(heading)
        rest = text[start + len(heading) :]
        m = re.search(r"\n## ", rest)
        block = rest[: m.start()] if m else rest
        m2 = re.search(r"```text\n(.*?)```", block, re.DOTALL)
        if not m2:
            raise SystemExit(f"no wireframe block for {key} in {FROZEN}")
        out[key] = m2.group(1).rstrip() + "\n"
    return out


def render(page: str, frames: dict[str, str]) -> str:
    page = ALIASES.get(page.lower(), page.lower())
    if page not in frames:
        raise SystemExit(f"unknown page: {page}")
    return frames[page]


def main() -> None:
    p = argparse.ArgumentParser(description="Frozen v2 wireframes (see WIREFRAME_V2_FROZEN.md)")
    p.add_argument("page", nargs="?", default="library", choices=[*PAGES, "all", "list"])
    p.add_argument("--pager", action="store_true")
    args = p.parse_args()

    frames = load_wireframes()

    if args.page == "list":
        print(f"Source: {FROZEN.relative_to(ROOT)}")
        for i, n in enumerate(PAGES, 1):
            print(f"  {i}. {n}")
        return

    if args.page == "all":
        sep = "\n" + "═" * 78 + "\n\n"
        text = sep.join(render(n, frames) for n in PAGES)
        if args.pager and sys.stdout.isatty():
            subprocess.run(["less", "-R"], input=text, text=True, check=False)
        else:
            print(text, end="")
    else:
        print(render(args.page, frames), end="")


if __name__ == "__main__":
    main()
