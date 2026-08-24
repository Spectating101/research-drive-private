"""CRSP MOVEit sync + ingest pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_moveit_file_item_id():
    from scripts.crsp_moveit_lib import MoveitFile

    f = MoveitFile.from_html("107798083", "test.pdf", 1000)
    assert f.item_id == "file107798083"


def test_folder_tree_parse():
    from scripts.crsp_moveit_lib import folder_tree_from_html

    html = '<option title="/Product_Downloads/Stock_Index_1925_ANNSUB" value="899531180">x</option>'
    tree = folder_tree_from_html(html)
    assert "/Product_Downloads/Stock_Index_1925_ANNSUB" in tree
    assert tree["/Product_Downloads/Stock_Index_1925_ANNSUB"].folder_id == "899531180"


def test_resolve_product_folder():
    from scripts.crsp_moveit_lib import MoveitFolder, resolve_product_folder

    tree = {
        "/Product_Downloads/STOCK_25i_SI_ASCII_Annual": MoveitFolder(
            folder_id="122819538", name="STOCK_25i_SI_ASCII_Annual", path="/Product_Downloads/STOCK_25i_SI_ASCII_Annual"
        )
    }
    got = resolve_product_folder(tree, "STOCK_25i_SI_ASCII_Annual")
    assert got is not None
    assert got.folder_id == "122819538"


def test_sync_script_importable():
    import scripts.crsp_moveit_sync as sync

    assert sync.TIER_PRODUCTS["index"] == ["stock_index_1925_annsub"]


def test_queue_has_crsp_sync_and_ingest_tasks():
    q = json.loads((REPO / "config/data_collection_queue.json").read_text(encoding="utf-8"))
    ids = {t["id"] for t in q["tasks"]}
    for tid in ("crsp_moveit_sync_priority", "crsp_moveit_ingest", "compustat_export_ingest", "crsp_compustat_ccm_link"):
        assert tid in ids
    sync_task = next(t for t in q["tasks"] if t["id"] == "crsp_moveit_sync_priority")
    assert sync_task["enabled"] is True
    assert "crsp_moveit_sync.py" in " ".join(sync_task["command"])


def test_compustat_schema_config():
    doc = json.loads((REPO / "config/compustat_export_schema.json").read_text(encoding="utf-8"))
    assert "gvkey" in doc["column_aliases"]


def test_ccm_link_blocked_without_file():
    import subprocess

    proc = subprocess.run(
        ["python3", "scripts/build_crsp_compustat_ccm_link.py", "--json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": f"{REPO}:{REPO}/kernel"},
    )
    assert proc.returncode == 1
    assert "blocked" in proc.stdout.lower() or "blocked" in proc.stderr.lower()
