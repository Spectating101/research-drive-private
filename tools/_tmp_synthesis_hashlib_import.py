from pathlib import Path

path = Path("drive/scripts/research_data_mcp/gateway.py")
text = path.read_text(encoding="utf-8")
old = "import os\nimport json\nimport re\n"
new = "import hashlib\nimport os\nimport json\nimport re\n"
if text.count(old) != 1:
    raise SystemExit(f"expected one gateway import anchor, got {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
