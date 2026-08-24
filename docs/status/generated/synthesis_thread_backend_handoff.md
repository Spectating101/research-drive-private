# Synthesis thread backend handoff

**Date:** 2026-07-13  
**Scope:** Narrow durable Synthesis Thread State vertical slice (private control-plane only).  
**Public UI:** unchanged (`yzu-cluster` / public frontend files not modified).

## Purpose

Persist researcher-accepted Synthesis construction state. Composer remains the reasoning agent; this backend does **not** invent heuristic plans or claim materialised outputs without execution.

## Persistence

| Item | Location |
|------|----------|
| SQLite store | `data_lake/procurement_memory/synthesis_threads.sqlite3` |
| Module | `drive/scripts/research_data_mcp/synthesis_thread_store.py` |
| Gateway | `ResearchDataGateway.synthesis_thread_*` |
| HTTP | `drive/scripts/research_data_mcp/http_router.py` under `/library/synthesis/threads*` |

Tables:

- `synthesis_threads` — stable id, objective, title, `session_id`, `conversation_id`, `materialisation`, `state_json`, timestamps
- `synthesis_thread_patches` — accepted/rejected decision audit log

Construction `state_json` is frontend-compatible (nodes / edges / proposal / spec / activity / `required_grain` / honest `materialisation`).

## Routes

Registered **before** `/library/synthesis/{id}` so `threads` is not captured as a profile id.

| Method | Path | Role |
|--------|------|------|
| `GET` | `/library/synthesis/threads` | List (`limit`, optional `session_id`) |
| `POST` | `/library/synthesis/threads` | Create (`objective` required; optional title, session/conversation linkage, `required_grain`, initial `state`) |
| `GET` | `/library/synthesis/threads/{thread_id}` | Load full thread + state |
| `POST` | `/library/synthesis/threads/{thread_id}/proposal` | Store pending agent proposal (not yet accepted) |
| `POST` | `/library/synthesis/threads/{thread_id}/patches` | Researcher decision: `decision=accept\|reject\|apply` |
| `GET` | `/library/synthesis/threads/{thread_id}/discover-handoff` | Conservative Discover handoff payload |
| `GET` | `/library/synthesis/threads/{thread_id}/materialisation` | Honest materialisation view |

### Patch semantics

Compatible with the construction-workbench ops:

`update_node`, `add_node`, `remove_node`, `update_edge`, `add_edge`, `update_spec`, `append_activity`

- **accept** — apply pending (or provided) proposal operations; clear proposal; reload retains accepted state
- **reject** — if `nodeId` present, remove that node and connected edges (frontend-compatible); clear proposal
- **apply** — apply an explicit accepted `operations` list

Dishonest materialisation labels (`registered`, `generated`, `produced`, …) are rejected. Patches cannot claim an output was generated without an execution record.

### Discover handoff shape

```json
{
  "thread_id": "...",
  "objective": "...",
  "required_grain": "asset-week",
  "held_evidence": [{"id": "...", "dataset_id": "...", "status": "held", "...": "..."}],
  "missing_evidence": [{"id": "...", "candidate_key": "...", "source_identity": "...", "status": "missing"}],
  "collection": null,
  "fake_collection": false
}
```

Held statuses: `held`, `queryable`. Missing statuses: `missing`, `needs_access`, `sourceable`. No invented collection jobs or plans.

### Materialisation honesty

Default and current slice behaviour:

- `materialisation`: `not_materialised` or `planned` only via this API
- `executed`: false unless an execution record exists (not written by this slice)
- `output_registered`: false

## Tests

`tests/test_synthesis_thread_state.py`

- create / list / get persistence + reload
- accept proposal retained on reload
- reject proposal removes candidate node/edges
- dishonest materialisation rejected; honest materialisation endpoint
- Discover handoff preserves held/missing identities only
- HTTP round-trip on `/library/synthesis/threads*` with isolated sqlite

Closest existing backend coverage also exercised: `tests/test_synthesis.py`, `tests/test_http_router_contract.py`.

## Intentionally unimplemented

- Running / materialising synthesis profiles from a thread (no silent `research_synthesis_run`)
- Recording execution / promoting outputs to the registry from thread state
- Auto-opening Discover collect jobs from missing evidence
- MCP tool wrappers for thread CRUD
- Public yzu-cluster UI binding to these routes
- Heuristic planners or Composer replacement logic
- Graph layout / ELK / React Flow (frontend concern)
- Resources spend attribution for synthesis threads

## Related authority

- `/tmp/yzu-discover-routes/docs/PRODUCT_ARCHITECTURE_HANDOFF_2026-07-13.md` — Synthesis vs Discover, agent→patch→approve model
- `docs/DATASET_SYNTHESIS.md` — existing profile run/pair equipment (separate from thread state)
- `docs/UI_PRODUCT_AUTHORITY.md` / `docs/RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md` — product surfaces; this slice is backend persistence only
