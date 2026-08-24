#!/usr/bin/env python3
"""Fix repo-root resolution in drive/ and alpha/ shell scripts after layout split."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNIPPET = '''
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
'''.strip()

PAT = re.compile(
    r'^(?:repo_root|ROOT_DIR|ROOT|SR_DIR)="\$\(cd "\$\(dirname "\$\{BASH_SOURCE\[0\]\}"\)/\.\." && pwd\)"\n(?:cd "\$\{(?:repo_root|ROOT_DIR|ROOT|SR_DIR)\}"\n)?',
    re.MULTILINE,
)


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "platform_env.sh" in text.split("\n")[:8]:
        return False
    new, n = PAT.subn(SNIPPET + "\nrepo_root=\"${SR_DIR}\"\n", text, count=1)
    if n == 0:
        # SR_DIR only line
        new2, n2 = re.subn(
            r'^SR_DIR="\$\(cd "\$\(dirname "\$\{BASH_SOURCE\[0\]\}"\)/\.\." && pwd\)"\n',
            SNIPPET + "\n",
            text,
            count=1,
        )
        if n2:
            new = new2
            n = n2
    if n == 0:
        return False
    path.write_text(new, encoding="utf-8")
    print(f"patched {path.relative_to(ROOT)}")
    return True


def main() -> int:
    count = 0
    for base in (ROOT / "drive" / "scripts", ROOT / "alpha" / "scripts"):
        for path in sorted(base.rglob("*.sh")):
            if patch_file(path):
                count += 1
    print(f"patched_files={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
