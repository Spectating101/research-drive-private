# Research Drive — frontend ↔ backend integration

**Status:** FROZEN companion to [`V2_FORWARD_FROZEN.md`](V2_FORWARD_FROZEN.md) and [`../RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](../RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md)  
**Audience:** Implementers wiring v2 UI to `:8765`

---

## Two processes, one desk

```text
┌─────────────────────────────┐         ┌──────────────────────────────────┐
│  Vite UI (:5178)            │  HTTP   │  Query engine (:8765)            │
│  src/v2/ or src/main.jsx    │ ──────► │  scripts/research_query_engine/  │
│  React + driveTree.js       │  proxy  │  server.py → http_router.py      │
└─────────────────────────────┘         │       → ResearchDataGateway      │
         │                              │       → ResearchQueryEngine      │
         │  dev: /api/* → :8765         │       → config registry JSON     │
         └──────────────────────────────┴──────────────────────────────────┘
```

**Start both:** `bash scripts/run_yzu_cluster.sh` (API + Vite legacy)  
**v2 UI only:** API must be up; then `npm run dev:v2` → http://127.0.0.1:5178/index-v2.html

---

## Dev proxy (vite.config.js)

| Browser request | Proxied to |
|-----------------|------------|
| `/api/datasets` | `http://127.0.0.1:8765/datasets` |
| `/api/query/{id}` | `http://127.0.0.1:8765/query/{id}` |
| `/api/library/chat/stream` | same path on :8765 |
| `/datasets`, `/query`, `/library`, `/health` | also proxied (legacy `main.jsx`) |

v2 client uses `const API = import.meta.env.DEV ? "/api" : ""` (`src/v2/api.js`).

Production: UI is static `dist/`; same-origin or CORS to API (query server can `serve_ui`).

---

## Registry is the spine

1. **Registry JSON** (`config/research_query_registry.json` or path from `create_stack()`) lists datasets with `dataset_id`, `backend`, `grain`, paths, readiness.
2. **`ResearchQueryEngine`** loads registry → `list_datasets()`, `describe(id)`, `query(id, params)`.
3. **`ResearchDataGateway`** wraps search + procurement + library endpoints.
4. **`http_router.py`** maps REST paths to gateway methods (table-driven `ROUTE_CATALOG`).

Frontend never reads the registry file directly — always HTTP.

## Right rail is the UI integration boundary

The app should pass one selected-object envelope through `InspectorRail`, `DetailPanel`, and `AskRail`. See [`../RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](../RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md) for the canonical `rail_context` shape.

Current bridge: `src/v2/useAskChat.js` prefixes the message with `[context: ...]`. Target integration: `src/v2/api.js::sendChatMessage()` sends `rail_context` in the JSON body, and `/library/chat` stores it in the chat session state before Composer runs.

Do not add a second procurement path in the frontend. The rail uses `/library/chat/stream`; Composer chooses MCP tools.

---

## Phase 1 API calls (v2 Library slice)

| UI action | HTTP | Backend handler | Returns |
|-----------|------|-----------------|---------|
| Load library list | `GET /datasets` | `datasets` → `list_datasets()` | `{ datasets: [...] }` |
| Select row → Detail | `GET /datasets/{id}` | `dataset_describe` | Full registry row |
| Preview modal | `GET /query/{id}?limit=50` | `dataset_query` → `engine.query()` | `{ rows: [...], ... }` |
| Header health | `GET /health` | `desk_health` | status counts |

**Folder tree** is **frontend-only**: `src/driveTree.js` maps each dataset’s `local_root` / `domain` into `Lab › research_panels › …` — same as legacy Drive, no `/library/browse` required for Phase 1.

---

## Phase 2+ API calls (not wired in v2 yet)

| Tab / feature | HTTP |
|---------------|------|
| Browse discover | `GET /library/discover?q=` or `/library/search` |
| Ask rail | `POST /library/chat/stream` with `rail_context` target |
| Add to lab | `POST /library/jobs` + approve |
| Resources ledger | `GET /library/ops`, `/yzu/status`, `/yzu/jobs` |
| Home brief | `GET /library/desk/brief` |
| Profile | `GET /library/faculty/profile` |

---

## Preview modal data flow

```text
User [Preview rows] or double-click
  → PreviewModal open (React state + optional ?preview=1)
  → GET /query/{dataset_id}?limit=50
  → engine picks backend (csv, parquet, jsonl, …)
  → rows[] → table in Preview tab
  → Schema tab: registry fields + infer types from rows[0]
  → Query tab: display SQL hint; Run = same GET (Phase 1)
```

Preview does **not** navigate. Closing modal returns to Library with same `?dataset=`.

---

## v2 code map

| Path | Role |
|------|------|
| `index-v2.html` | v2 entry |
| `src/v2/main.jsx` | bootstrap |
| `src/v2/App.jsx` | shell, URL state, data fetch |
| `src/v2/LibraryPage.jsx` | breadcrumb + catalog |
| `src/v2/DetailPanel.jsx` | rail metadata |
| `src/v2/PreviewModal.jsx` | Quick Look overlay |
| `src/v2/api.js` | fetch helpers |
| `src/driveTree.js` | folder layout (shared with legacy) |

Legacy monolith: `src/main.jsx` (full features, old IA).

Legacy names in `src/main.jsx` (`Source`, `Pipeline`, `Details | Assistant`) are not v2 product names. They remain only until cutover.

---

## Run / verify

```bash
# Terminal 1 — API
bash scripts/run_yzu_cluster.sh    # or python3 -m scripts.research_query_engine.server --port 8765

# Terminal 2 — v2 UI
npm run dev:v2

# Smoke
curl -s http://127.0.0.1:8765/health | head
curl -s 'http://127.0.0.1:8765/datasets' | head -c 200
```

Open Library → click dataset → Detail rail → Preview rows.
