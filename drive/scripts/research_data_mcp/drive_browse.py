#!/usr/bin/env python3
"""Consumer drive browse tree — My Drive / Lab Drive (Google Drive style)."""

from __future__ import annotations

import re
from typing import Any

GLOB_RE = re.compile(r"[*?{\[]")

DRIVE_MY = "my"
DRIVE_LAB = "lab"

DRIVE_ROOT_NAMES = {
    DRIVE_MY: "My Drive",
    DRIVE_LAB: "Lab Drive",
}


def _clean_segment(part: str) -> str:
    part = str(part or "").strip()
    if GLOB_RE.search(part):
        part = part.split("*", 1)[0].rstrip("_")
    return part or "files"


def dataset_drive_scope(row: dict[str, Any]) -> str:
    if str(row.get("domain") or "") == "web_scrape":
        return DRIVE_MY
    return DRIVE_LAB


def _folder_label(segment: str) -> str:
    labels = {
        "uploads": "Uploads",
        "news_shock": "News shock",
        "research_panels": "Research panels",
        "procured": "Procured",
        "catalogues": "Catalogues",
        "reference": "Reference",
        "connections": "Apps & connections",
        "campaigns": "Campaigns",
        "processed": "Processed",
        "sec": "SEC filings",
        "entity_mapping": "Entity mapping",
        "spk_v1": "SPK v1",
        "other": "Other",
    }
    return labels.get(segment, segment.replace("_", " "))


def _lab_path_from_data_lake(parts: list[str]) -> list[str]:
    if not parts:
        return ["other"]
    head = _clean_segment(parts[0])
    tail = [_clean_segment(p) for p in parts[1:] if p]
    if head == "news_shock_taxonomy":
        return ["lab_pipelines", "news_shock", *tail]
    if head == "research_panels":
        return ["research_panels", *tail]
    if head == "dataset_catalog":
        return ["lab_pipelines", "catalogues", *tail]
    if head == "procured":
        return ["procured", *tail]
    if head == "sec":
        return ["reference", "sec", *tail]
    if head == "entity_mapping":
        return ["reference", "entity_mapping", *tail]
    if head == "spk_v1":
        return ["reference", "spk_v1", *tail]
    if head == "spectator_engine":
        return ["lab_pipelines", "scrapes", *tail]
    return ["other", head, *tail]


def consumer_dataset_path(row: dict[str, Any], scope: str | None = None) -> list[str]:
    scope = scope or dataset_drive_scope(row)
    domain = str(row.get("domain") or "")
    raw = str(row.get("local_root") or row.get("local_path") or "").strip()

    if scope == DRIVE_MY:
        scrape_id = str(row.get("dataset_id") or "").removeprefix("scrape_")
        if domain == "web_scrape" or "spectator_engine" in raw:
            return ["uploads", scrape_id or "draft"]
        return ["uploads", str(row.get("dataset_id") or "file")]

    if raw.startswith("data_lake/"):
        parts = [_clean_segment(p) for p in raw.removeprefix("data_lake/").split("/") if p]
        return _lab_path_from_data_lake(parts)

    if domain == "procured":
        if raw and "procured" in raw:
            tail = raw.split("procured/", 1)[-1]
            if tail:
                return ["procured", *[_clean_segment(p) for p in tail.split("/") if p]]
        return ["procured", str(row.get("dataset_id") or "item")]

    if not raw:
        readiness = str(row.get("analysis_readiness") or "")
        backend = str(row.get("backend") or "")
        if readiness == "metadata_search" or "catalog" in backend or "jsonl" in backend:
            return ["lab_pipelines", "catalogues", str(row.get("dataset_id") or "catalog")]
        return ["connections", str(row.get("dataset_id") or "remote")]

    return ["other", _clean_segment(raw)]


def dataset_storage_path(row: dict[str, Any]) -> list[str]:
    """Backward-compatible alias — lab drive path."""
    return consumer_dataset_path(row, DRIVE_LAB)


def _insert_path(root: dict[str, Any], segments: list[str], *, leaf: dict[str, Any]) -> None:
    node = root
    path_so_far: list[str] = []
    for i, seg in enumerate(segments):
        path_so_far.append(seg)
        folder_id = "/".join(path_so_far)
        is_leaf = i == len(segments) - 1
        if is_leaf:
            node.setdefault("children", {})
            node["children"][leaf["id"]] = leaf
            return
        children = node.setdefault("children", {})
        if folder_id not in children:
            children[folder_id] = {
                "id": folder_id,
                "kind": "folder",
                "name": _folder_label(seg),
                "segment": seg,
                "path": list(path_so_far),
                "children": {},
            }
        node = children[folder_id]


def build_browse_tree(
    datasets: list[dict[str, Any]],
    *,
    scope: str = DRIVE_LAB,
    campaigns: list[dict[str, Any]] | None = None,
    pins: list[dict[str, Any]] | None = None,
    showcase_ids: list[str] | None = None,
) -> dict[str, Any]:
    _ = showcase_ids
    root_name = DRIVE_ROOT_NAMES.get(scope, "Drive")
    root: dict[str, Any] = {
        "id": "",
        "kind": "folder",
        "name": root_name,
        "path": [],
        "children": {},
    }

    scoped = [r for r in datasets if dataset_drive_scope(r) == scope]

    for row in scoped:
        did = str(row.get("dataset_id") or "")
        if not did:
            continue
        segments = consumer_dataset_path(row, scope)
        _insert_path(root, segments, leaf=_dataset_leaf(row, scope))

    campaigns = campaigns or []
    if scope == DRIVE_LAB and campaigns:
        camp_root: dict[str, Any] = {
            "id": "campaigns",
            "kind": "folder",
            "name": _folder_label("campaigns"),
            "path": ["campaigns"],
            "children": {},
        }
        for c in campaigns:
            cid = str(c.get("id") or "")
            if not cid:
                continue
            camp_root["children"][f"campaign:{cid}"] = {
                "id": f"campaign:{cid}",
                "kind": "campaign",
                "name": str(c.get("goal") or cid)[:72],
                "campaign_id": cid,
                "phase": c.get("phase"),
                "status": c.get("status"),
                "path": ["campaigns", cid],
            }
        root["children"]["campaigns"] = camp_root

    pins = pins or []
    if scope == DRIVE_LAB:
        for pin in pins:
            fp = str(pin.get("file_path") or "")
            if not fp.startswith("data_lake/"):
                continue
            parts = [_clean_segment(p) for p in fp.removeprefix("data_lake/").split("/") if p]
            segments = _lab_path_from_data_lake(parts)
            _insert_path(
                root,
                segments,
                leaf={
                    "id": f"pin:{pin.get('handle')}",
                    "kind": "pin",
                    "name": str((pin.get("metadata") or {}).get("title") or pin.get("handle") or "Pinned file"),
                    "handle": pin.get("handle"),
                    "campaign_id": pin.get("campaign_id"),
                    "file_path": fp,
                    "path": segments,
                },
            )

    flat = _flatten_tree(root)
    return {
        "scope": scope,
        "root": root,
        "flat_folders": [n for n in flat if n.get("kind") == "folder"],
        "dataset_count": sum(1 for n in flat if n.get("kind") == "dataset"),
        "folder_count": sum(1 for n in flat if n.get("kind") == "folder"),
    }


def _dataset_leaf(row: dict[str, Any], scope: str) -> dict[str, Any]:
    did = str(row.get("dataset_id") or "")
    return {
        "id": did,
        "kind": "dataset",
        "name": row.get("name") or did,
        "dataset_id": did,
        "domain": row.get("domain"),
        "backend": row.get("backend"),
        "analysis_readiness": row.get("analysis_readiness"),
        "local_root": row.get("local_root"),
        "local_path": row.get("local_path"),
        "path": consumer_dataset_path(row, scope),
    }


def _flatten_tree(node: dict[str, Any], out: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    out = out or []
    out.append({k: v for k, v in node.items() if k != "children"})
    for child in (node.get("children") or {}).values():
        if child.get("kind") == "folder":
            _flatten_tree(child, out)
    return out


def _find_folder(root: dict[str, Any], folder_id: str) -> dict[str, Any] | None:
    if folder_id in ("", root.get("id", "")):
        return root
    node = root
    acc: list[str] = []
    for part in folder_id.split("/"):
        if not part:
            continue
        acc.append(part)
        current_id = "/".join(acc)
        children = node.get("children") or {}
        nxt = children.get(current_id)
        if nxt is None:
            nxt = next((c for c in children.values() if c.get("id") == current_id and c.get("kind") == "folder"), None)
        if nxt is None:
            return None
        node = nxt
    return node


def list_folder_children(tree: dict[str, Any], folder_id: str = "") -> list[dict[str, Any]]:
    root = tree.get("root") or tree
    node = _find_folder(root, folder_id)
    if node is None:
        return []
    children = list((node.get("children") or {}).values())
    folders = sorted([c for c in children if c.get("kind") == "folder"], key=lambda x: x.get("name", "").lower())
    files = sorted(
        [c for c in children if c.get("kind") != "folder"],
        key=lambda x: x.get("name", "").lower(),
    )
    return folders + files
