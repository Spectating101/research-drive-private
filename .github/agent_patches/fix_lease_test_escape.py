from pathlib import Path

path = Path("tests/test_completion_lease_scope.py")
text = path.read_text(encoding="utf-8")

broken = '""".strip() + "\n",'
fixed = '""".strip() + "\\n",'
if text.count(broken) != 1:
    raise SystemExit(f"expected one broken generated newline, found {text.count(broken)}")
text = text.replace(broken, fixed, 1)

marker = "timestamp," + "value"
start = text.find(marker)
stop = text.find("')", start)
if start < 0 or stop < 0:
    raise SystemExit("embedded fixture segment not found")
fragment = text[start:stop]
if fragment.count(chr(10)) != 2:
    raise SystemExit(f"expected two embedded line breaks, found {fragment.count(chr(10))}")
text = text[:start] + fragment.replace(chr(10), "\\\\n") + text[stop:]

path.write_text(text, encoding="utf-8")
