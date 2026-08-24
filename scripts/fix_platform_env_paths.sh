#!/usr/bin/env bash
# One-shot: symlink lib into drive/alpha scripts + normalize platform_env source lines.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CANON="${ROOT}/scripts/lib/platform_env.sh"
[[ -f "${CANON}" ]] || { echo "missing ${CANON}" >&2; exit 1; }

for sub in drive/scripts alpha/scripts; do
  target="${ROOT}/${sub}/lib"
  if [[ ! -e "${target}" ]]; then
    ln -sfn "../../scripts/lib" "${target}"
    echo "symlink ${target} -> ../../scripts/lib"
  fi
done

export ROOT
python3 - <<'PY'
import os
from pathlib import Path

root = Path(os.environ["ROOT"])
old = 'source "${_script_dir}/lib/platform_env.sh"'
new = 'source "${_script_dir}/lib/platform_env.sh"'
old_comment = "# shellcheck source=lib/platform_env.sh"
new_comment = "# shellcheck source=lib/platform_env.sh"
count = 0
for base in [root / "scripts", root / "drive" / "scripts", root / "alpha" / "scripts"]:
    if not base.is_dir():
        continue
    for path in sorted(base.rglob("*.sh")):
        text = path.read_text(encoding="utf-8")
        if old not in text and old_comment not in text:
            continue
        text = text.replace(old_comment, new_comment).replace(old, new)
        path.write_text(text, encoding="utf-8")
        print("fixed", path.relative_to(root))
        count += 1
py_path = root / "scripts" / "fix_repo_root_paths.py"
if py_path.is_file():
    t = py_path.read_text(encoding="utf-8")
    t2 = t.replace(
        "# shellcheck source=lib/platform_env.sh\nsource \"${_script_dir}/../../scripts/lib/platform_env.sh\"",
        "# shellcheck source=lib/platform_env.sh\nsource \"${_script_dir}/lib/platform_env.sh\"",
    )
    if t2 != t:
        py_path.write_text(t2, encoding="utf-8")
        print("fixed fix_repo_root_paths.py")
print(f"shell_scripts_fixed={count}")
PY
