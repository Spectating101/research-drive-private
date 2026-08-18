#!/usr/bin/env python3
"""A fingerprint the reader cannot check is worse than none.

The exported script's header says "verify these fingerprints before trusting a
reproduction". For a single-file input it emitted sha256(filename + bytes) labelled
`sha256:`, while the run manifest recorded the plain sha256 of the same bytes. Running
`sha256sum` on the file returned neither the manifest's value nor the script's, which
reads as tampering when nothing is wrong.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.research_data_mcp.synthesis.spec_export import fingerprint_path


def test_a_single_file_fingerprint_matches_sha256sum(tmp_path: Path) -> None:
    target = tmp_path / "panel.csv"
    payload = b"a,b\n1,2\n"
    target.write_bytes(payload)
    out = fingerprint_path(target)
    assert out["files"] == 1
    assert out["fingerprint"] == f"sha256:{hashlib.sha256(payload).hexdigest()}"


def test_the_single_file_value_equals_what_the_manifest_records(tmp_path: Path) -> None:
    """The manifest hashes the bytes; the script must agree or neither can be trusted."""
    target = tmp_path / "panel.parquet"
    payload = b"PAR1-not-really"
    target.write_bytes(payload)
    manifest_style = hashlib.sha256(target.read_bytes()).hexdigest()
    assert fingerprint_path(target)["fingerprint"] == f"sha256:{manifest_style}"


def test_a_multi_file_input_is_labelled_so_nobody_runs_sha256sum(tmp_path: Path) -> None:
    """Chaining names is right for many files, but must not claim to be a file hash."""
    root = tmp_path / "dir"
    root.mkdir()
    (root / "a.csv").write_bytes(b"x")
    (root / "b.csv").write_bytes(b"y")
    out = fingerprint_path(root)
    assert out["files"] == 2
    assert out["fingerprint"].startswith("sha256-manifest:"), out["fingerprint"]
    assert "2 file" in str(out.get("note") or "")


def test_an_absent_path_still_refuses_to_invent_a_fingerprint(tmp_path: Path) -> None:
    out = fingerprint_path(tmp_path / "nope.csv")
    assert out["fingerprint"] is None
    assert out["note"]
