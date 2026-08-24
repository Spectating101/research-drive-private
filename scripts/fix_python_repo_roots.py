#!/usr/bin/env python3
"""Replace Path(__file__).parents[2] repo-root hacks in drive/ and alpha/."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAT = re.compile(r"Path\(__file__\)\.resolve\(\)\.parents\[2\]")
REPL = "repo_root_from_file(__file__)"
IMPORT = "from sharpe_kernel.paths import repo_root_from_file"


def patch(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "repo_root_from_file" in text and PAT.search(text) is None:
        return False
    if not PAT.search(text):
        return False
    new = PAT.sub(REPL, text)
    if IMPORT not in new:
        lines = new.splitlines()
        insert_at = 0
        if lines and lines[0].startswith("#!"):
            insert_at = 1
        if insert_at < len(lines) and "from __future__" in lines[insert_at]:
            insert_at += 2
        lines.insert(insert_at, IMPORT)
        new = "\n".join(lines) + ("\n" if new.endswith("\n") else "")
    path.write_text(new, encoding="utf-8")
    print(f"patched {path.relative_to(ROOT)}")
    return True


def main() -> int:
    n = 0
    for base in (ROOT / "drive", ROOT / "alpha"):
        for path in sorted(base.rglob("*.py")):
            if patch(path):
                n += 1
    print(f"patched_py={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
