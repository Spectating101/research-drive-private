#!/usr/bin/env python3
"""Durable Synthesis research-thread state — researcher-accepted construction only.

Composer remains the reasoning agent. This module persists thread identity,
controlled accepted/rejected patches (compatible with the frontend construction
workspace ops), Discover handoff identities, and honest materialisation status.
It does not invent collection jobs or claim outputs were generated without
execution evidence.
"""

from __future__ import annotations

from contextlib import contextmanager

import copy
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Any


ALLOWED_PATCH_OPS = frozenset(
    {
        "update_node",
        "add_node",
        "remove_node",
        "update_edge",
        "add_edge",
        "update_spec",
        "append_activity",
    }
)

# Patches may only keep planned / not-yet-run language. Produced/registered
# claims require an execution record (intentionally not auto-applied here).
HONEST_MATERIALISATION = frozenset({"not_materialised", "planned"})
DISHONEST_MATERIALISATION = frozenset(
    {
        "materialised",
        "materialized",
        "produced",
        "registered",
        "complete",
        "completed",
        "done",
        "generated",
    }
)

HELD_STATUSES = frozenset({"held", "queryable"})
MISSING_STATUSES = frozenset({"missing", "needs_access", "sourceable"})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_synthesis_thread_db(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/procurement_memory/synthesis_threads.sqlite3"


def empty_construction_state(
    *,
    objective: str = "",
    title: str = "",
    required_grain: str = "",
) -> dict[str, Any]:
    return {
        "title": title,
        "objective": objective,
        "required_grain": required_grain,
        "maturity": "exploring",
        "maturityLabel": "Exploring",
        "lastActivity": "Thread created.",
        "materialisation": "not_materialised",
        "nodes": [],
        "edges": [],
        "proposal": None,
        "decisions": [],
        "activity": [{"time": "Now", "kind": "create", "message": "Synthesis thread created."}],
        "spec": {
            "purpose": objective,
            "grain": required_grain,
            "coreEvidence": [],
            "validation": [],
            "unavailable": [],
            "construction": [],
            "limitations": [],
        },
        "plannedColumns": [],
        "chartIdeas": [],
    }


def _clone_state(state: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(state or {})


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def apply_synthesis_patch(state: dict[str, Any], operations: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Apply controlled construction ops (frontend-compatible semantics)."""
    next_state = _clone_state(state)
    next_state.setdefault("nodes", [])
    next_state.setdefault("edges", [])
    next_state.setdefault("activity", [])
    next_state.setdefault("spec", {})

    for operation in operations or []:
        if not isinstance(operation, dict):
            raise ValueError("Unsupported synthesis patch operation: unknown")
        op = str(operation.get("op") or "")
        if op not in ALLOWED_PATCH_OPS:
            raise ValueError(f"Unsupported synthesis patch operation: {op or 'unknown'}")

        if op == "update_node":
            node_id = str(operation.get("id") or "")
            index = next((i for i, n in enumerate(next_state["nodes"]) if n.get("id") == node_id), -1)
            if index < 0:
                raise ValueError(f"Unknown synthesis node: {node_id}")
            patch = dict(operation.get("patch") or {})
            _reject_dishonest_materialisation_fields(patch)
            next_state["nodes"][index] = {**next_state["nodes"][index], **patch}
        elif op == "add_node":
            node = dict(operation.get("node") or {})
            node_id = str(node.get("id") or "")
            if not node_id or any(n.get("id") == node_id for n in next_state["nodes"]):
                raise ValueError("Synthesis node additions require a unique id.")
            _reject_dishonest_materialisation_fields(node)
            next_state["nodes"].append(node)
        elif op == "remove_node":
            node_id = str(operation.get("id") or "")
            next_state["nodes"] = [n for n in next_state["nodes"] if n.get("id") != node_id]
            next_state["edges"] = [
                e
                for e in next_state["edges"]
                if e.get("source") != node_id and e.get("target") != node_id
            ]
        elif op == "update_edge":
            edge_id = str(operation.get("id") or "")
            index = next((i for i, e in enumerate(next_state["edges"]) if e.get("id") == edge_id), -1)
            if index < 0:
                raise ValueError(f"Unknown synthesis edge: {edge_id}")
            patch = dict(operation.get("patch") or {})
            next_state["edges"][index] = {**next_state["edges"][index], **patch}
        elif op == "add_edge":
            edge = dict(operation.get("edge") or {})
            edge_id = str(edge.get("id") or "")
            if not edge_id or any(e.get("id") == edge_id for e in next_state["edges"]):
                raise ValueError("Synthesis edge additions require a unique id.")
            ids = {n.get("id") for n in next_state["nodes"]}
            if edge.get("source") not in ids or edge.get("target") not in ids:
                raise ValueError("Synthesis edge endpoints must exist.")
            next_state["edges"].append(edge)
        elif op == "update_spec":
            patch = dict(operation.get("patch") or {})
            next_state["spec"] = {**(next_state.get("spec") or {}), **patch}
        elif op == "append_activity":
            next_state["activity"].append(
                {
                    "time": "Now",
                    "kind": "change",
                    "message": str(operation.get("message") or "Synthesis state updated."),
                }
            )

    _reject_dishonest_materialisation_fields(next_state)
    return next_state


def _reject_dishonest_materialisation_fields(payload: dict[str, Any]) -> None:
    raw = payload.get("materialisation", payload.get("materialization"))
    if raw is None:
        return
    value = str(raw).strip().lower()
    if value in DISHONEST_MATERIALISATION:
        raise ValueError(
            "Dishonest materialisation claim rejected: "
            "outputs cannot be marked generated without execution evidence."
        )
    if value and value not in HONEST_MATERIALISATION:
        payload["materialisation"] = "not_materialised"
        payload.pop("materialization", None)


def accept_proposal(state: dict[str, Any], proposal: dict[str, Any] | None = None) -> dict[str, Any]:
    current = _clone_state(state)
    prop = proposal if proposal is not None else current.get("proposal")
    if not prop:
        raise ValueError("No synthesis proposal to accept.")
    if not prop.get("proposal_hash"):
        raise ValueError("Synthesis proposal has no validated revision.")
    operations = list(prop.get("operations") or [])
    next_state = apply_synthesis_patch(current, operations)
    # A runnable plan is persisted only after the researcher accepts its proposal.
    # The worker validates it again before touching any source bytes.
    if prop.get("execution_spec") is not None:
        next_state["execution_spec"] = _clone_state(prop["execution_spec"])
        next_state["accepted_spec_hash"] = hashlib.sha256(
            json.dumps(next_state["execution_spec"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        # A new accepted spec starts a new execution revision; it must never inherit
        # the registered/pending state of an earlier output.
        next_state["execution"] = {
            "status": "spec_accepted",
            "spec_hash": next_state["accepted_spec_hash"],
            "output_dataset_id": next_state["execution_spec"]["output_dataset_id"],
        }
    next_state["proposal"] = None
    next_state["lastActivity"] = str(prop.get("title") or "Proposal accepted")
    next_state["activity"] = _as_list(next_state.get("activity"))
    next_state["activity"].append(
        {
            "time": "Now",
            "kind": "decision",
            "message": f"Accepted proposal: {prop.get('title') or prop.get('id') or 'untitled'}.",
        }
    )
    return next_state


def validate_synthesis_proposal(
    state: dict[str, Any], proposal: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Validate a Composer proposal without changing the construction state."""
    if proposal is None:
        return None
    if not isinstance(proposal, dict):
        raise ValueError("synthesis proposal must be an object")
    normalized = _clone_state(proposal)
    proposal_id = str(normalized.get("id") or "").strip()
    title = str(normalized.get("title") or "").strip()
    summary = str(normalized.get("summary") or "").strip()
    operations = normalized.get("operations")
    if not proposal_id or not title or not summary:
        raise ValueError("synthesis proposal requires id, title, and summary")
    if not isinstance(operations, list) or not operations:
        raise ValueError("synthesis proposal requires one or more operations")
    if len(operations) > 32:
        raise ValueError("synthesis proposal has too many operations")
    normalized["id"] = proposal_id[:120]
    normalized["title"] = title[:240]
    normalized["summary"] = summary[:2000]
    if normalized.get("reason") is not None:
        normalized["reason"] = str(normalized["reason"])[:3000]
    if normalized.get("impact") is not None:
        if not isinstance(normalized["impact"], list):
            raise ValueError("synthesis proposal impact must be a list")
        normalized["impact"] = [str(item)[:400] for item in normalized["impact"][:12]]
    if normalized.get("execution_spec") is not None:
        from scripts.research_data_mcp.synthesis_executor import validate_execution_spec

        normalized["execution_spec"] = validate_execution_spec(
            normalized["execution_spec"]
        )
    revision_payload = {
        "id": normalized["id"],
        "title": normalized["title"],
        "summary": normalized["summary"],
        "operations": operations,
        "execution_spec": normalized.get("execution_spec"),
    }
    normalized["proposal_hash"] = hashlib.sha256(
        json.dumps(revision_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    # Validation-only dry run: impossible graph edits and dishonest output
    # claims fail before a proposal ever reaches the researcher.
    apply_synthesis_patch(state, operations)
    return normalized


def reject_proposal(state: dict[str, Any], proposal: dict[str, Any] | None = None) -> dict[str, Any]:
    current = _clone_state(state)
    prop = proposal if proposal is not None else current.get("proposal")
    if not prop:
        raise ValueError("No synthesis proposal to reject.")
    node_id = str(prop.get("nodeId") or "").strip()
    title = str(prop.get("title") or prop.get("id") or "proposal")
    if node_id:
        operations: list[dict[str, Any]] = [
            {"op": "remove_node", "id": node_id},
            {"op": "append_activity", "message": f"{title} rejected."},
        ]
    else:
        operations = [{"op": "append_activity", "message": f"{title} rejected."}]
    next_state = apply_synthesis_patch(current, operations)
    next_state["proposal"] = None
    next_state["lastActivity"] = f"{title} rejected"
    return next_state


def _evidence_identity(node: dict[str, Any]) -> dict[str, Any]:
    """Conservative identity fields only — no fabricated collection payload."""
    identity: dict[str, Any] = {
        "id": node.get("id"),
        "label": node.get("label") or node.get("title") or node.get("id"),
        "status": node.get("status"),
        "type": node.get("type"),
        "role": node.get("role"),
    }
    for key in (
        "dataset_id",
        "registered_dataset_id",
        "candidate_key",
        "source_identity",
        "connector_id",
        "probe_id",
        "source",
        "grain",
        "coverage",
    ):
        val = node.get(key)
        if val not in (None, ""):
            identity[key] = val
    return identity


def _is_evidence_node(node: dict[str, Any]) -> bool:
    ntype = str(node.get("type") or "")
    layer = str(node.get("layer") or "")
    if ntype in {"source", "construct"}:
        return True
    if layer == "evidence":
        return True
    return False


def build_discover_handoff(thread: dict[str, Any]) -> dict[str, Any]:
    state = thread.get("state") or {}
    required_grain = (
        str(state.get("required_grain") or "").strip()
        or str((state.get("spec") or {}).get("grain") or "").strip()
        or ""
    )
    held: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for node in _as_list(state.get("nodes")):
        if not isinstance(node, dict) or not _is_evidence_node(node):
            continue
        status = str(node.get("status") or "")
        if status in HELD_STATUSES:
            held.append(_evidence_identity(node))
        elif status in MISSING_STATUSES:
            missing.append(_evidence_identity(node))

    collect_intents: list[dict[str, Any]] = []
    for row in missing:
        connectors = [
            str(row.get(k) or "").strip()
            for k in ("connector_id", "source_id", "candidate_key", "source_identity")
        ]
        has_hook = bool(connectors[0] or connectors[1] or connectors[2])
        intent: dict[str, Any] = {
            "evidence_id": row.get("id"),
            "label": row.get("label"),
            "connector_id": row.get("connector_id") or "",
            "source_id": row.get("source_id") or "",
            "candidate_key": row.get("candidate_key") or "",
            "source_identity": row.get("source_identity") or "",
            "resolvable_hint": has_hook,
            "status": "intent_only",
        }
        if not has_hook:
            intent["reason"] = "missing_source_hooks"
        collect_intents.append(intent)

    return {
        "thread_id": thread.get("id"),
        "objective": thread.get("objective") or state.get("objective") or "",
        "required_grain": required_grain,
        "held_evidence": held,
        "missing_evidence": missing,
        "collect_intents": collect_intents,
        "collection": None,
        "fake_collection": False,
        "note": (
            "Conservative Discover handoff: identities + collect_intents from "
            "missing evidence hooks. No acquisition jobs invented until "
            "researcher calls collect-missing."
        ),
    }


def build_materialisation_view(thread: dict[str, Any]) -> dict[str, Any]:
    state = thread.get("state") or {}
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    execution_status = str(execution.get("status") or "")
    output_registered = execution_status == "registered"
    materialisation = str(
        thread.get("materialisation")
        or state.get("materialisation")
        or "not_materialised"
    ).strip() or "not_materialised"
    if output_registered:
        materialisation = "registered"
    elif materialisation.lower() in DISHONEST_MATERIALISATION:
        materialisation = "not_materialised"
    if materialisation not in HONEST_MATERIALISATION | {"registered"}:
        materialisation = "not_materialised"
    return {
        "thread_id": thread.get("id"),
        "materialisation": materialisation,
        "executed": execution_status in {"completed", "registered"},
        "output_registered": output_registered,
        "execution_recorded": bool(execution.get("job_id")),
        "job_id": execution.get("job_id") or "",
        "output_dataset_id": execution.get("output_dataset_id") or "",
        "note": (
            "Honest materialisation only: no output is claimed generated without "
            "an execution record on this thread."
        ),
    }


class SynthesisThreadStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS synthesis_threads (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    title TEXT,
                    objective TEXT NOT NULL,
                    session_id TEXT,
                    conversation_id TEXT,
                    materialisation TEXT NOT NULL,
                    state_json TEXT NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS synthesis_thread_patches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_synth_threads_updated "
                "ON synthesis_threads(updated_at DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_synth_patches_thread "
                "ON synthesis_thread_patches(thread_id, id)"
            )

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        """Open a short-lived connection that always closes.

        Python 3.12+ ``Connection.__exit__`` commits/rollbacks but no longer
        closes the handle, so ``with sqlite3.connect(...)`` leaks FDs under
        desk polling (/health, job list, workers).
        """
        db = sqlite3.connect(self.path, timeout=30)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create(
        self,
        *,
        objective: str,
        title: str = "",
        session_id: str = "",
        conversation_id: str = "",
        required_grain: str = "",
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        objective = str(objective or "").strip()
        if not objective:
            raise ValueError("objective is required")
        tid = uuid.uuid4().hex[:16]
        stamp = _now()
        title = str(title or "").strip() or objective[:120]
        body = empty_construction_state(
            objective=objective,
            title=title,
            required_grain=str(required_grain or "").strip(),
        )
        if state:
            merged = _clone_state(state)
            merged.setdefault("objective", objective)
            merged.setdefault("title", title)
            if required_grain and not merged.get("required_grain"):
                merged["required_grain"] = required_grain
            _reject_dishonest_materialisation_fields(merged)
            if str(merged.get("materialisation") or "") not in HONEST_MATERIALISATION:
                merged["materialisation"] = "not_materialised"
            if merged.get("proposal") is not None:
                # Existing locally persisted workspaces predate proposal summaries.
                # Preserve them as reviewable proposals rather than silently applying them.
                if isinstance(merged["proposal"], dict) and not merged["proposal"].get("summary"):
                    merged["proposal"]["summary"] = str(merged["proposal"].get("title") or "Legacy synthesis proposal")
                merged["proposal"] = validate_synthesis_proposal(merged, merged["proposal"])
            body = merged
        materialisation = str(body.get("materialisation") or "not_materialised")
        if materialisation not in HONEST_MATERIALISATION:
            materialisation = "not_materialised"
            body["materialisation"] = materialisation
        with self._db() as db:
            db.execute(
                "INSERT INTO synthesis_threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tid,
                    stamp,
                    stamp,
                    title[:200],
                    objective[:4000],
                    str(session_id or "")[:64],
                    str(conversation_id or "")[:64],
                    materialisation,
                    json.dumps(body),
                ),
            )
        return self.get(tid)

    def get(self, thread_id: str) -> dict[str, Any]:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM synthesis_threads WHERE id = ?",
                (thread_id,),
            ).fetchone()
        if not row:
            raise KeyError(thread_id)
        item = dict(row)
        item["state"] = json.loads(item.pop("state_json") or "{}")
        item["execution_recorded"] = bool((item["state"].get("execution") or {}).get("job_id"))
        return item

    def list(self, *, limit: int = 30, session_id: str = "") -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 30), 200))
        with self._db() as db:
            if session_id:
                ids = [
                    r[0]
                    for r in db.execute(
                        "SELECT id FROM synthesis_threads WHERE session_id = ? "
                        "ORDER BY updated_at DESC LIMIT ?",
                        (session_id, limit),
                    )
                ]
            else:
                ids = [
                    r[0]
                    for r in db.execute(
                        "SELECT id FROM synthesis_threads ORDER BY updated_at DESC LIMIT ?",
                        (limit,),
                    )
                ]
        return [self.get(tid) for tid in ids]

    def _save_state(
        self,
        thread_id: str,
        state: dict[str, Any],
        *,
        objective: str | None = None,
        title: str | None = None,
        trusted_execution: bool = False,
    ) -> dict[str, Any]:
        current = self.get(thread_id)
        body = _clone_state(state)
        if not trusted_execution:
            _reject_dishonest_materialisation_fields(body)
        materialisation = str(body.get("materialisation") or current.get("materialisation") or "not_materialised")
        allowed_materialisation = HONEST_MATERIALISATION | ({"registered"} if trusted_execution else set())
        if materialisation not in allowed_materialisation:
            materialisation = "not_materialised"
            body["materialisation"] = materialisation
        new_objective = objective if objective is not None else current.get("objective") or body.get("objective") or ""
        new_title = title if title is not None else current.get("title") or body.get("title") or ""
        body["objective"] = new_objective
        body["title"] = new_title
        with self._db() as db:
            db.execute(
                "UPDATE synthesis_threads SET updated_at=?, title=?, objective=?, "
                "materialisation=?, state_json=? WHERE id=?",
                (
                    _now(),
                    str(new_title)[:200],
                    str(new_objective)[:4000],
                    materialisation,
                    json.dumps(body),
                    thread_id,
                ),
            )
        return self.get(thread_id)

    def _log_patch(self, thread_id: str, decision: str, payload: dict[str, Any]) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO synthesis_thread_patches(thread_id, created_at, decision, payload_json) "
                "VALUES (?, ?, ?, ?)",
                (thread_id, _now(), decision, json.dumps(payload)),
            )

    def apply_patch_decision(
        self,
        thread_id: str,
        *,
        decision: str,
        operations: list[dict[str, Any]] | None = None,
        proposal_id: str = "",
        proposal_hash: str = "",
    ) -> dict[str, Any]:
        """Persist researcher accept / reject / apply decisions."""
        decision_norm = str(decision or "").strip().lower()
        thread = self.get(thread_id)
        state = _clone_state(thread.get("state") or {})

        if decision_norm in {"accept", "accepted", "apply_proposal"}:
            current = state.get("proposal") or {}
            if not proposal_id or not proposal_hash:
                raise ValueError("proposal_id and proposal_hash are required for acceptance")
            if proposal_id != current.get("id") or proposal_hash != current.get("proposal_hash"):
                raise ValueError("Synthesis proposal changed; refresh before accepting")
            next_state = accept_proposal(state, proposal=state.get("proposal"))
            logged = {"decision": "accepted", "proposal": current}
            out = self._save_state(thread_id, next_state)
            self._log_patch(thread_id, "accepted", logged)
            return out

        if decision_norm in {"reject", "rejected"}:
            current = state.get("proposal") or {}
            if not proposal_id or not proposal_hash:
                raise ValueError("proposal_id and proposal_hash are required for rejection")
            if proposal_id != current.get("id") or proposal_hash != current.get("proposal_hash"):
                raise ValueError("Synthesis proposal changed; refresh before rejecting")
            next_state = reject_proposal(state, proposal=state.get("proposal"))
            logged = {"decision": "rejected", "proposal": current}
            out = self._save_state(thread_id, next_state)
            self._log_patch(thread_id, "rejected", logged)
            return out

        if decision_norm in {"apply", "apply_operations", "patch"}:
            if not operations:
                raise ValueError("operations are required for apply decisions")
            next_state = apply_synthesis_patch(state, operations)
            next_state["lastActivity"] = "Accepted synthesis patch applied."
            out = self._save_state(thread_id, next_state)
            self._log_patch(thread_id, "accepted", {"decision": "apply", "operations": operations})
            return out

        raise ValueError(
            "decision must be accept, reject, or apply "
            f"(got {decision_norm or 'empty'})"
        )

    def set_proposal(self, thread_id: str, proposal: dict[str, Any] | None) -> dict[str, Any]:
        thread = self.get(thread_id)
        state = _clone_state(thread.get("state") or {})
        state["proposal"] = validate_synthesis_proposal(state, proposal)
        out = self._save_state(thread_id, state)
        if proposal is not None:
            self._log_patch(thread_id, "proposed", {"proposal": state["proposal"]})
        return out

    def link_conversation(
        self,
        thread_id: str,
        *,
        session_id: str,
        conversation_id: str = "",
    ) -> dict[str, Any]:
        """Bind a Composer/procurement chat session to an existing synthesis thread."""
        self.get(thread_id)  # ensure exists
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id is required")
        cid_raw = conversation_id
        cid = str(cid_raw or "").strip()
        if cid_raw not in (None, "") and not cid:
            raise ValueError("conversation_id must be a non-empty stable id when provided")
        stamp = _now()
        with self._db() as db:
            if cid:
                db.execute(
                    "UPDATE synthesis_threads SET session_id=?, conversation_id=?, updated_at=? "
                    "WHERE id=?",
                    (sid[:64], cid[:64], stamp, thread_id),
                )
            else:
                db.execute(
                    "UPDATE synthesis_threads SET session_id=?, updated_at=? WHERE id=?",
                    (sid[:64], stamp, thread_id),
                )
        return self.get(thread_id)

    def discover_handoff(self, thread_id: str) -> dict[str, Any]:
        return build_discover_handoff(self.get(thread_id))

    def materialisation(self, thread_id: str) -> dict[str, Any]:
        return build_materialisation_view(self.get(thread_id))

    def record_execution(self, thread_id: str, job: dict[str, Any], *, verified: bool = False) -> dict[str, Any]:
        """Record worker evidence after completion; this is not a researcher patch."""
        if not verified:
            raise ValueError("trusted execution record requires completion verification")
        thread = self.get(thread_id)
        state = _clone_state(thread.get("state") or {})
        result = job.get("result") or {}
        materialized = result.get("materialized") or {}
        registered = True
        state["execution"] = {
            "status": "registered" if registered else "completed",
            "job_id": str(job.get("id") or ""),
            "output_dataset_id": str(materialized.get("dataset_id") or ""),
            "rows": result.get("rows"),
            "drive_verified": bool((result.get("drive_finalize") or {}).get("ok")),
            "manifest_id": str(result.get("output_manifest_id") or ""),
        }
        state["lastActivity"] = (
            "Registered synthesis output is available in Library."
            if registered
            else "Synthesis execution completed; registry promotion is not confirmed."
        )
        state["maturity"] = "registered" if registered else "executed"
        state["maturityLabel"] = "Registered output" if registered else "Execution completed"
        state["activity"] = _as_list(state.get("activity"))
        state["activity"].append({"time": "Now", "kind": "execution", "message": state["lastActivity"]})
        state["materialisation"] = "registered" if registered else "planned"
        return self._save_state(
            thread_id,
            state,
            trusted_execution=True,
        )

    def record_execution_failure(self, thread_id: str, job_id: str, error: str) -> dict[str, Any]:
        thread = self.get(thread_id)
        state = _clone_state(thread.get("state") or {})
        execution = state.get("execution") or {}
        if execution.get("job_id") != job_id:
            raise ValueError("failed execution does not match the active synthesis job")
        state["execution"] = {
            **execution,
            "status": "failed",
            "error": str(error)[:1200],
        }
        state["lastActivity"] = "Synthesis execution failed; inspect the error and retry the accepted spec."
        state["activity"] = _as_list(state.get("activity"))
        state["activity"].append({"time": "Now", "kind": "execution", "message": state["lastActivity"]})
        return self._save_state(thread_id, state)

    def patch_log(self, thread_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        self.get(thread_id)  # ensure exists
        with self._db() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT id, created_at, decision, payload_json FROM synthesis_thread_patches "
                "WHERE thread_id = ? ORDER BY id DESC LIMIT ?",
                (thread_id, max(1, min(limit, 200))),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            out.append(item)
        return out
