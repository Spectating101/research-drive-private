#!/usr/bin/env python3
"""One dataset must not mean two different files.

The query engine expands a wildcard anywhere in local_path; the synthesis resolver only
stripped a trailing one, so a declaration like
`.../taiwan_twse/*/derived/twse_security_master.csv` served real rows through the desk and
was unreadable to synthesis. Pinning a default_run_id would have fixed synthesis while
leaving the engine on the newest landing — the same dataset resolving to two files, which
is the drift this project keeps paying for.

Ambiguity is still refused: several distinct filenames under one glob is not one table.
"""

from __future__ import annotations

import pytest

from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.delenv("RESEARCH_DATA_ROOTS", raising=False)


def _landing(root, stamp, name="twse_security_master.csv", body="a,b\n1,2\n"):
    d = root / "data_lake/twse" / stamp / "derived"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")
    return d / name


def test_a_midpath_glob_resolves_to_the_newest_matching_file(tmp_path):
    old = _landing(tmp_path, "20260101")
    new = _landing(tmp_path, "20260718")
    os_utime_newer(new, old)
    row = {
        "dataset_id": "twse",
        "local_path": "data_lake/twse/*/derived/twse_security_master.csv",
        "local_file": "twse_security_master.csv",
    }
    path, err = resolve_dataset_file(tmp_path, row)
    assert err is None, err
    assert path is not None
    assert path.name == "twse_security_master.csv"
    assert "20260718" in str(path), f"expected the newest landing, got {path}"


def test_several_distinct_filenames_under_one_glob_are_refused(tmp_path):
    _landing(tmp_path, "20260101", name="one.csv")
    _landing(tmp_path, "20260102", name="two.csv")
    row = {"dataset_id": "mixed", "local_path": "data_lake/twse/*/derived/*.csv"}
    path, err = resolve_dataset_file(tmp_path, row)
    assert path is None
    assert err and "refusing to guess" in err


def test_a_concrete_path_is_unaffected(tmp_path):
    target = _landing(tmp_path, "only")
    row = {"dataset_id": "x", "local_path": "data_lake/twse/only/derived/twse_security_master.csv"}
    path, err = resolve_dataset_file(tmp_path, row)
    assert err is None and path == target


def os_utime_newer(newer, older):
    import os, time
    now = time.time()
    os.utime(older, (now - 500, now - 500))
    os.utime(newer, (now, now))
