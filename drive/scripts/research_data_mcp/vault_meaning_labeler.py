#!/usr/bin/env python3
"""Background vault meaning labelling — Copilot/Gemini brain, Python hands.

Hands measure a facts packet from the registry row (+ optional synthesis node
hints), call a light model for plain-language meaning, then write show+store
fields. dataset_id never changes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.vault_meaning import (
    apply_meaning_to_row,
    is_ops_face,
    normalize_meaning_payload,
)


def _atomic_update_json(path: Path, mutate) -> dict[str, Any]:
    from scripts.research_data_mcp.registry_transaction import atomic_update_json

    return atomic_update_json(path, mutate)


def measure_meaning_facts(row: dict[str, Any], *, extras: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bundle measured facts for the label brain — no invented science."""
    extras = extras if isinstance(extras, dict) else {}
    lineage = row.get("lineage") if isinstance(row.get("lineage"), dict) else {}
    exec_spec = row.get("execution_spec") if isinstance(row.get("execution_spec"), dict) else {}
    if not exec_spec and isinstance(extras.get("execution_spec"), dict):
        exec_spec = extras["execution_spec"]
    node_hints = extras.get("node_titles") or []
    if not isinstance(node_hints, list):
        node_hints = []
    return {
        "dataset_id": str(row.get("dataset_id") or ""),
        "current_name": str(row.get("name") or row.get("title") or "")[:240],
        "ops_title": str(row.get("ops_title") or "")[:240],
        "grain": str(row.get("grain") or ""),
        "coverage": str(row.get("coverage") or row.get("date_range") or ""),
        "partition_id": str(row.get("partition_id") or lineage.get("partition_id") or ""),
        "domain": str(row.get("domain") or ""),
        "source_system": str(row.get("source_system") or ""),
        "source_dataset_id": str(row.get("source_dataset_id") or ""),
        "upstream_dataset_ids": list(lineage.get("upstream_dataset_ids") or []),
        "derived_via": str(lineage.get("derived_via") or ""),
        "url_hint": _url_from_row(row),
        "file_hint": _file_hint(row),
        "columns_hint": _columns_hint(row),
        "objective_hint": str(extras.get("objective") or "")[:500],
        "transform_hint": _transform_hint(exec_spec),
        "node_titles": [str(t)[:80] for t in node_hints if str(t).strip()][:6],
        "analysis_readiness": str(row.get("analysis_readiness") or ""),
    }


def _url_from_row(row: dict[str, Any]) -> str:
    for blob in (row.get("description"), row.get("recommended_use"), row.get("ops_title")):
        m = re.search(r"https?://\S+", str(blob or ""))
        if m:
            return m.group(0).rstrip(".,)")
    return ""


def _file_hint(row: dict[str, Any]) -> str:
    path = str(row.get("local_path") or row.get("local_file") or "")
    if not path:
        return ""
    return Path(path.split("*")[0]).name


def _columns_hint(row: dict[str, Any]) -> list[str]:
    smoke = row.get("query_smoke") if isinstance(row.get("query_smoke"), dict) else {}
    cols = smoke.get("columns") or []
    if isinstance(cols, list):
        return [str(c) for c in cols[:16]]
    mat = row.get("materialization") if isinstance(row.get("materialization"), dict) else {}
    qs = mat.get("query_smoke") if isinstance(mat.get("query_smoke"), dict) else {}
    cols = qs.get("columns") or []
    return [str(c) for c in cols[:16]] if isinstance(cols, list) else []


def _transform_hint(exec_spec: dict[str, Any]) -> str:
    transforms = exec_spec.get("transforms") or []
    if not isinstance(transforms, list):
        return ""
    bits = []
    for step in transforms:
        if not isinstance(step, dict):
            continue
        op = str(step.get("op") or "")
        if op == "diff":
            bits.append(f"diff({step.get('column')}, periods={step.get('periods')})→{step.get('as')}")
        elif op:
            bits.append(op)
    return "; ".join(bits)[:240]


def build_meaning_prompt(facts: dict[str, Any]) -> str:
    return (
        "You label a research Library dataset for faculty and LLMs.\n"
        "Write plain language about WHAT IT IS — not industry codes, not craft_ ids, "
        "not 'Custom collect', not 'Route prove', not pasted objectives.\n"
        "Benchmark tone for a CO2 series: "
        "'Monthly carbon dioxide measurements from the Mauna Loa observatory since 1958 "
        "— the classic Keeling Curve record of rising atmospheric CO₂.'\n"
        "Return ONLY one JSON object with keys:\n"
        "  title (short, ≤80 chars),\n"
        "  description (2–3 plain sentences, what it is),\n"
        "  recommended_use (one short line, what you'd use it for),\n"
        "  aliases (array of alternate names people/LLMs might say),\n"
        "  keywords (array of lowercase topical tokens for search),\n"
        "  meaning_about (optional longer note for models; may include other names).\n"
        "Do not change or invent dataset_id. Do not output markdown fences.\n\n"
        f"FACTS:\n{json.dumps(facts, ensure_ascii=False, indent=2)}\n"
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty model reply")
    try:
        out = json.loads(raw)
        if isinstance(out, dict):
            return out
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        out = json.loads(raw[start : end + 1])
        if isinstance(out, dict):
            return out
    raise ValueError("model reply was not a JSON object")


def _cursor_label(prompt: str, gateway: Any) -> dict[str, Any]:
    """Label via the desk's own Composer — the same brain Discover and Ask use."""
    from scripts.research_data_mcp.desk_brain import (
        cursor_composer_available,
        run_cursor_composer_turn,
    )

    if not cursor_composer_available():
        raise RuntimeError("composer not configured")
    turn = run_cursor_composer_turn(
        gateway,
        prompt,
        {"vault_meaning_label": True},
        session_id=f"vault-label-{abs(hash(prompt)) % 10_000_000}",
    )
    payload = _parse_json_object(str(getattr(turn, "reply", "") or ""))
    normalize_meaning_payload(payload)
    return payload


def call_label_brain(
    prompt: str, *, timeout: int = 90, gateway: Any = None
) -> tuple[dict[str, Any], str, str]:
    """Cursor Composer first, then Copilot wrappers, then optional Gemini.

    Composer is the desk's own brain — the one Discover and Ask already run on —
    so labelling no longer depends on separate CLI wrappers that can be down
    while the desk itself is healthy.
    """
    errors: list[str] = []
    if gateway is not None:
        try:
            payload = _cursor_label(prompt, gateway)
            return payload, "cursor_composer", "cursor_composer"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"cursor_composer:{str(exc)[:80]}")

    providers = [
        ("copilot-ly", ["copilot-ly", "-p", prompt]),
        ("copilot-ly2", ["copilot-ly2", "-p", prompt]),
        ("copilot-spectator", ["copilot-spectator", "-p", prompt]),
    ]
    gemini = shutil.which("gemini")
    if gemini and os.getenv("VAULT_MEANING_ALLOW_GEMINI", "").strip().lower() in {"1", "true", "yes"}:
        providers.append(("gemini", [gemini, "-p", prompt, "-o", "text", "--yolo"]))

    for name, argv in providers:
        bin_path = shutil.which(argv[0])
        if not bin_path and name != "gemini":
            # wrappers are often in ~/.local/bin without which in restricted PATH
            cand = Path.home() / ".local/bin" / argv[0]
            if cand.is_file():
                argv = [str(cand), *argv[1:]]
            else:
                continue
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{name}:{exc}")
            continue
        blob = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        if proc.returncode != 0 and not blob:
            errors.append(f"{name}:rc={proc.returncode}")
            continue
        try:
            payload = _parse_json_object(blob)
            normalize_meaning_payload(payload)  # validate early
            return payload, name, name
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}:parse:{exc}")
            continue
    raise RuntimeError("vault meaning label brain failed: " + "; ".join(errors[:6]))


def propose_meaning_for_row(
    row: dict[str, Any],
    *,
    extras: dict[str, Any] | None = None,
    gateway: Any = None,
) -> dict[str, Any]:
    facts = measure_meaning_facts(row, extras=extras)
    prompt = build_meaning_prompt(facts)
    payload, provider, model = call_label_brain(prompt, gateway=gateway)
    clean = normalize_meaning_payload(payload)
    return {
        "ok": True,
        "dataset_id": row.get("dataset_id"),
        "meaning": clean,
        "provider": provider,
        "model": model,
        "facts": facts,
    }


def apply_meaning_to_registry(
    registry_path: Path,
    dataset_id: str,
    meaning: dict[str, Any],
    *,
    labeled_by: str,
    model: str = "",
) -> dict[str, Any]:
    did = str(dataset_id or "").strip()
    if not did:
        raise ValueError("dataset_id required")

    def mutate(registry: dict[str, Any]) -> dict[str, Any]:
        datasets = list(registry.get("datasets") or [])
        for index, row in enumerate(datasets):
            if str(row.get("dataset_id") or "") != did:
                continue
            updated = apply_meaning_to_row(row, meaning, labeled_by=labeled_by, model=model)
            datasets[index] = updated
            registry["datasets"] = datasets
            registry["updated_at"] = updated.get("meaning", {}).get("labeled_at")
            return {"dataset_id": did, "title": updated.get("title"), "aliases": updated.get("aliases")}
        raise KeyError(f"unknown dataset_id: {did}")

    return _atomic_update_json(Path(registry_path), mutate)


def resolve_registry_path(repo_root: Path, gateway: Any = None) -> Path:
    """Registry location for this checkout.

    The private repo carries a root-level config/ of symlinks; the runtime
    checkout only has drive/config/. Hardcoding the former made relabel fail on
    the root the service actually runs from. The gateway already knows, so ask
    it first and fall back to the layouts that exist.
    """
    declared = getattr(gateway, "registry_path", None)
    if declared:
        candidate = Path(declared)
        if candidate.is_file():
            return candidate
    root = Path(repo_root).resolve()
    for rel in ("config/research_query_registry.json", "drive/config/research_query_registry.json"):
        candidate = root / rel
        if candidate.is_file():
            return candidate
    return root / "config/research_query_registry.json"


def relabel_dataset(
    repo_root: Path,
    dataset_id: str,
    *,
    registry_path: Path | None = None,
    extras: dict[str, Any] | None = None,
    dry_run: bool = False,
    gateway: Any = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    reg_path = Path(registry_path) if registry_path else resolve_registry_path(root, gateway)
    doc = json.loads(reg_path.read_text(encoding="utf-8"))
    row = next((r for r in (doc.get("datasets") or []) if r.get("dataset_id") == dataset_id), None)
    if not row:
        raise KeyError(f"unknown dataset_id: {dataset_id}")
    proposal = propose_meaning_for_row(row, extras=extras, gateway=gateway)
    if dry_run:
        return {**proposal, "applied": False, "dry_run": True}
    applied = apply_meaning_to_registry(
        reg_path,
        dataset_id,
        proposal["meaning"],
        labeled_by=str(proposal.get("provider") or "label_brain"),
        model=str(proposal.get("model") or ""),
    )
    return {**proposal, "applied": True, "registry": applied, "dry_run": False}


def needs_meaning_relabel(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    title = str(row.get("title") or row.get("display_name") or row.get("name") or "")
    if is_ops_face(title):
        return True
    if not (row.get("aliases") or row.get("keywords")):
        return True
    desc = str(row.get("description") or "").strip()
    # Descriptions are allowed to be long; only reject ops-jargon faces.
    if not desc or is_ops_face(desc, allow_long=True):
        return True
    return False


def list_relabel_queue(
    repo_root: Path,
    *,
    registry_path: Path | None = None,
    limit: int = 40,
    include_scrape_noise: bool = False,
    gateway: Any = None,
) -> list[dict[str, Any]]:
    """Prioritize query-ready / instant holdings that still lack meaning store."""
    root = Path(repo_root).resolve()
    reg_path = Path(registry_path) if registry_path else resolve_registry_path(root, gateway)
    doc = json.loads(reg_path.read_text(encoding="utf-8"))
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in doc.get("datasets") or []:
        if not needs_meaning_relabel(row):
            continue
        did = str(row.get("dataset_id") or "")
        if not did:
            continue
        if not include_scrape_noise and (
            did.startswith("scrape_")
            or did in {"test_sec", "procured_sec_tickers_test", "collection_queue_status", "datacite_local_harvest_status"}
        ):
            continue
        ar = str(row.get("analysis_readiness") or "")
        mat = row.get("materialization") if isinstance(row.get("materialization"), dict) else {}
        qr = bool(mat.get("query_ready")) or ar in {"query_ready", "instant"}
        title = str(row.get("display_name") or row.get("title") or row.get("name") or "")
        # Prefer: query_ready craft/synthesis, then instant research panels, then rest.
        priority = 0
        if ar == "query_ready" or mat.get("query_ready"):
            priority += 100
        if ar == "instant":
            priority += 40
        if did.startswith(("craft_", "synthesis_")) or is_ops_face(title):
            priority += 50
        if row.get("partition_id") or (row.get("lineage") or {}).get("partition_id"):
            priority += 10
        # Operator dashboards / audit artifacts — lower than research panels.
        if did.startswith("investment_") and did.endswith("_latest"):
            priority -= 60
        if "operator_dashboard" in did or "repo_inventory" in did:
            priority -= 60
        if did.startswith("scrape_"):
            priority -= 80
        scored.append(
            (
                priority,
                {
                    "dataset_id": did,
                    "title": title[:80],
                    "analysis_readiness": ar,
                    "priority": priority,
                    "query_ready": qr,
                },
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]["dataset_id"]))
    return [item[1] for item in scored[: max(1, min(int(limit or 40), 200))]]


def batch_relabel_datasets(
    repo_root: Path,
    *,
    dataset_ids: list[str] | None = None,
    limit: int = 20,
    dry_run: bool = False,
    include_scrape_noise: bool = False,
    gateway: Any = None,
) -> dict[str, Any]:
    """Sequential meaning pass over a prioritized queue (hands apply).

    Pass ``gateway`` to label via the desk's own Composer rather than the
    Copilot CLI wrappers.
    """
    root = Path(repo_root).resolve()
    if dataset_ids:
        queue = [{"dataset_id": str(d).strip()} for d in dataset_ids if str(d).strip()]
    else:
        queue = list_relabel_queue(
            root, limit=limit, include_scrape_noise=include_scrape_noise, gateway=gateway
        )
    results: list[dict[str, Any]] = []
    for item in queue[: max(1, min(int(limit or 20), 100))]:
        did = str(item.get("dataset_id") or "")
        if not did:
            continue
        try:
            out = relabel_dataset(root, did, dry_run=dry_run, gateway=gateway)
            row_out = {
                "dataset_id": did,
                "ok": True,
                "title": (out.get("meaning") or {}).get("title") or (out.get("registry") or {}).get("title"),
                "provider": out.get("provider"),
                "applied": out.get("applied"),
            }
            results.append(row_out)
            print(f"vault_meaning OK {did} -> {row_out.get('title')}", flush=True)
        except Exception as exc:  # noqa: BLE001 — keep batch moving
            results.append({"dataset_id": did, "ok": False, "error": str(exc)[:240]})
            print(f"vault_meaning FAIL {did}: {exc}", flush=True)
    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "ok": ok_n == len(results) and bool(results),
        "attempted": len(results),
        "succeeded": ok_n,
        "failed": len(results) - ok_n,
        "results": results,
        "dry_run": dry_run,
    }


def schedule_relabel_after_promote(
    repo_root: Path,
    dataset_id: str,
    *,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fire-and-forget background relabel (worker / promote hook)."""
    if os.getenv("VAULT_MEANING_AUTOLABEL", "1").strip().lower() in {"0", "false", "no"}:
        return {"ok": False, "skipped": True, "reason": "disabled"}

    root = Path(repo_root).resolve()
    did = str(dataset_id or "").strip()
    if not did:
        return {"ok": False, "skipped": True, "reason": "no_dataset_id"}

    def _run() -> None:
        try:
            relabel_dataset(root, did, extras=extras, dry_run=False)
        except Exception:  # noqa: BLE001 — background must not crash promote
            return

    threading.Thread(target=_run, name=f"vault-meaning-{did[:12]}", daemon=True).start()
    return {"ok": True, "scheduled": True, "dataset_id": did}
