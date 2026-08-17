#!/usr/bin/env python3
"""A glob pattern is a query, never a directory name.

A registry row whose local_path ends in `/*` had its plan's local_path stripped of
the glob and its local_abs left holding it. execute_hydrate prefers local_abs, so it
mkdir'd a directory literally named `*`. Real rclone output then landed inside it, and
an empty one shadowed 163MB of TWSE data at query time because the engine resolves
against repo_root before the data roots.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp import registry_hydrate
from scripts.research_data_mcp.collection_hydrate import execute_hydrate

GLOB_CHARS = ("*", "?", "[")

REGISTRY = Path(__file__).resolve().parents[1] / "drive/config/research_query_registry.json"


def _glob_specs() -> list[dict]:
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return [
        row
        for row in doc.get("datasets") or []
        if any(ch in str(row.get("local_path") or "") for ch in GLOB_CHARS)
    ]


def test_the_registry_still_has_glob_rows_to_protect() -> None:
    assert _glob_specs(), "no glob local_path rows left; this guard would be vacuous"


@pytest.mark.parametrize("spec", _glob_specs(), ids=lambda s: str(s.get("dataset_id")))
def test_plan_targets_never_contain_a_glob(tmp_path: Path, spec: dict) -> None:
    """Parametrised over the real registry so a new glob row cannot skip this."""
    row = dict(spec)
    row["canonical_remote"] = "gdrive:canonical/example"
    plan = registry_hydrate.build_registry_hydrate_plan(tmp_path, row)
    assert plan is not None
    if plan.get("skip_reason"):
        return
    for key in ("local_path", "local_abs"):
        value = str(plan.get(key) or "")
        for ch in GLOB_CHARS:
            assert ch not in value, f"{key}={value!r} carries {ch!r}; mkdir would create it"


def test_local_abs_and_local_path_agree(tmp_path: Path) -> None:
    plan = registry_hydrate.build_registry_hydrate_plan(
        tmp_path,
        {
            "dataset_id": "twse_openapi_taiwan_market_layer",
            "local_path": "data_lake/official_disclosures/taiwan_twse/*",
            "canonical_remote": "gdrive:canonical/twse",
        },
    )
    assert plan is not None
    assert plan["local_path"] == "data_lake/official_disclosures/taiwan_twse"
    assert Path(plan["local_abs"]) == tmp_path / "data_lake/official_disclosures/taiwan_twse"


def test_execute_hydrate_refuses_a_glob_target(tmp_path: Path) -> None:
    """Defence in depth: even a bad plan must not create a `*` directory."""
    out = execute_hydrate(
        tmp_path,
        {
            "remote_path": "gdrive:canonical/twse",
            "local_path": "data_lake/official_disclosures/taiwan_twse",
            "local_abs": str(tmp_path / "data_lake/official_disclosures/taiwan_twse/*"),
            "scope": "full",
        },
    )
    assert out.get("ok") is False
    assert out.get("error") == "glob_in_hydrate_target"
    assert not (tmp_path / "data_lake/official_disclosures/taiwan_twse/*").exists()
