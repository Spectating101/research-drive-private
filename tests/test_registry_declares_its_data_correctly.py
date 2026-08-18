#!/usr/bin/env python3
"""The catalogue must be right, not merely compensated for.

The engine descends when a declared path yields no files, which recovered 33 datasets and
made 31 wrong declarations invisible. Those are now corrected at the source, and this
pins them: a declaration that needs descending is a defect, and adding one fails here
rather than being absorbed silently and forever.

Skips where the bytes are not reachable, since a checkout without RESEARCH_DATA_ROOTS
cannot tell a wrong declaration from absent data.
"""

from __future__ import annotations

import pytest

from scripts.research_query_engine.registry_drift import scan


@pytest.fixture(scope="module")
def report() -> dict:
    result = scan(".")
    reachable = result["glob_datasets"] - len(result["no_files_at_any_depth"])
    if reachable <= 0:
        pytest.skip("no glob dataset has reachable bytes here; set RESEARCH_DATA_ROOTS")
    return result


def test_no_declaration_needs_the_engine_to_descend(report: dict) -> None:
    drifted = [
        f"{row['dataset_id']}: {row['declared']} -> {row['suggested_local_path']}"
        for row in report["drifted"]
    ]
    assert not drifted, (
        "registry declarations that only work because the engine descends:\n  "
        + "\n  ".join(drifted)
        + "\n\nrun: python -m scripts.research_query_engine.registry_drift"
    )


def test_most_glob_declarations_resolve_at_the_depth_they_state(report: dict) -> None:
    """A floor, so silently emptying the catalogue cannot pass this file."""
    assert report["declared_correctly"] >= 30, report
