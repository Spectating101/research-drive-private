# Research Drive right rail integration contract

**Status:** Active backend/context contract; product composition superseded 2026-07-11  
**Authority:** Subordinate to [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md). Entity/context and backend mappings remain binding. Product composition, navigation, idle-rail, Preview, responsive, and lifecycle ownership rules are defined only by the authority and its 2026-07-14 amendment.  
**Scope:** v2 interface and integration: `src/v2/InspectorRail.jsx`, `src/v2/DetailPanel.jsx`, `src/v2/RailPanels.jsx`, `src/v2/AskRail.jsx`, `src/v2/api.js`.

The right rail is the product spine. The main tabs are lenses over the same research desk; the rail is where the selected object becomes usable, explainable, and actionable.

This contract exists to stop the repo from drifting back into separate products: Drive clone, chat app, ops dashboard, and procurement wizard.

---

## 1. Product rule

Every professor-facing feature must answer one question first:

> What object is selected, and what should the rail show about it?

If a feature cannot produce a rail object, it is not ready for the main desk UI.

| Stable concept | Rule |
|----------------|------|
| Rail width | Desktop target is **440px** at 1440px. The rail is not a skinny helper drawer. |
| Rail modes | Exactly **Detail** and **Ask**. One visible pane; both mounted. |
| Detail | API-backed truth: metadata, provenance, readiness, vault path, job status, actions. |
| Ask | Composer + MCP conversation scoped to the same selected object. |
| Navigation | Defined exclusively by [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md). This contract does not restate faculty navigation. |
| Not tabs | Ask, Pipeline, Vault tree, Source. These are rail modes, resources rows, or detail fields. |

Legacy `src/main.jsx` still contains `Source`, `Pipeline`, and `Details | Assistant`. Treat that as cutover debt only. New work uses `src/v2/*` and `Detail | Ask`.

---

## 2. Rail context envelope

The UI should maintain one explicit rail context object. Today v2 partially encodes this through React props and text prefixes; the next integration pass should send the structured envelope to chat as `rail_context`.

```json
{
  "tab": "library",
  "mode": "detail",
  "entity": {
    "kind": "dataset",
    "id": "gdelt_asia_daily_country_panel",
    "title": "GDELT Asia daily country panel"
  },
  "dataset_id": "gdelt_asia_daily_country_panel",
  "source_url": "",
  "job_id": "",
  "resource_key": "",
  "folder_id": "research_panels/gdelt",
  "vault_path": "gdrive:Machine_Archive/.../collection/research_panels/gdelt",
  "search_query": "",
  "profile_email": "drkong@saturn.yzu.edu.tw",
  "readiness": "Query-ready",
  "actions": ["preview_rows", "ask_about", "see_on_cluster"]
}
```

Rules:

- `Detail` renders from structured fields, not assistant prose.
- `Ask` receives the same context and may use it to choose MCP tools.
- The UI must not expose MCP tool names to the professor except in developer/admin diagnostics.
- If the rail context changes because the user selects a row, switch to `Detail`.
- If an action needs Composer (`Ask about this`, `Add to lab`, search Enter), switch to `Ask` and prefill or submit from the same context.

---

## 3. Entity contracts

| Entity kind | Produced by | Detail must show | Primary actions |
|-------------|-------------|------------------|-----------------|
| `dataset` | Home, Library | title, `dataset_id`, readiness, source, coverage, grain, join keys, vault path, limitations | Preview rows, Ask about this, See on Cluster |
| `external_candidate` | Discover | title, publisher/source, access class, format/size if known, in-lab/queued state, provenance URL/DOI | Add to lab, Preview ext, Ask |
| `cluster_compare` | Operational compatibility context only; not faculty navigation | datasets compared, shared keys/date coverage, only-A/only-B gaps, honesty note when unknown | Ask about overlap, open dataset |
| `resource_row` | Resources | measured value, status, source endpoint, last refresh, related job if any | Explain, view activity, supported operational action; acquisition approval routes to Discover |
| `profile_scope` | Profile | affiliation, tracks, holdings/gaps, pinned corpora | Ask with this scope, edit profile |
| `settings_account` | Settings | email, credentials summary, notification prefs | Save, test connection, ask setup |
| `empty_page` | no selection | page summary and next useful selection | Toggle Ask |

Do not build new page-local detail panels. They create a second truth source and weaken the rail.

---

## 4. Backend mapping

Use `/library/*` for new integrations. `/yzu/*` remains a compatibility surface when no `/library/*` route exists yet.

| UI need | HTTP route | Notes |
|---------|------------|-------|
| Library list | `GET /datasets` | Registry-backed list. Frontend never reads registry JSON directly. |
| Dataset detail | `GET /datasets/{id}` | Drives `DetailPanel`. |
| Preview rows | `GET /query/{id}?limit=50` | Opens modal; does not navigate away. |
| Discover/search | `GET /library/search?q=` or `GET /library/discover?q=` | Produces `external_candidate` rows. |
| Ask rail | `POST /library/chat/stream` | Composer + MCP. Add `rail_context` in the next protocol pass. |
| Fallback chat | `POST /library/chat` | Same brain, non-streaming fallback. |
| Jobs | `GET /library/jobs`, `POST /library/jobs/{id}/approve` | Resources monitors; acquisition approval opens the candidate/job Focus in Discover. |
| Resources | `GET /library/desk/resources`, `GET /library/ops` | Countable status ledger. |
| Acquisitions | `GET /yzu/acquisitions` | Compatibility until folded into `/library/*`. |
| Profile | `GET /library/faculty/profile?email=` | Ranking and Ask context. |
| Warm session | `POST /library/desk/warm` | Prime Composer and vault brief. |

Current bridge: `src/v2/useAskChat.js` prefixes messages with `[context: ...]`. Keep that only as a temporary compatibility bridge. The target is structured context on the request body and in the chat session state.

---

## 5. Composer procurement path

The rail does not implement a Python planner. Composer is the brain; MCP tools are passive equipment.

When `Ask` needs procurement, the expected path is:

```text
local index
  -> research_describe_dataset / research_query_dataset on hit
  -> research_web_discover on miss
  -> procurement_probe_public_source(url)
  -> yzu_submit_job(plan_json) or datacite_collect_doi
  -> yzu_archive_to_gdrive
  -> research_open_dataset / registry write-back verification
```

Professor-facing copy should say "Ask", "Add to lab", "Discover", "Resources", and "Library". It should not say "DeepSeek", "magic", "workflow", `planner.py`, `yzu_submit_job`, or MCP protocol names.

---

## 6. Tab grounding

| Tab | Main canvas owns | Rail Detail owns | Ask owns |
|-----|------------------|------------------|----------|
| Home | continue, recent, running highlights | selected recent dataset or desk summary | resume scoped question |
| Library | vault folders + catalog table | selected dataset truth | questions about selected dataset, queryability, related data |
| Operational compatibility | coverage/overlap visualization | selected compare or dataset gap | explanation of overlap/gap |
| Discover | external search results | selected candidate truth | Add to lab, source comparison, collection plan |
| Resources | capacity, cost, jobs, activity | selected metric/job/account row | explain resource row and supported operational action; acquisition decisions route to Discover |
| Profile | faculty research context | selected track/scope | ranking/procurement with that profile |
| Settings | preferences and credential summaries | selected account setting | setup help only |

`Pipeline` becomes Resources rows. `Source` becomes Ask mode. `Vault` becomes Library organization plus vault path/provenance in Detail.

---

## 7. Visual direction

Keep the good part of the earlier right-rail iterations:

- A dense, stable rail that always explains the selected object.
- Visible provenance: source, vault path, readiness, coverage, and job state.
- Quick action buttons at the rail edge, not scattered through every page.
- A rail that can feel more instrumental than the main canvas without turning the whole app into a dark ops console.

Useful historical references in this repo:

- `docs/design/references/ui-snapshots/research-drive-terminal-tree-rail.png`
- `docs/design/references/ui-snapshots/qa-folder-tree-final-desktop.png`
- `docs/design/references/ui-snapshots/research-drive-interactive-examples.png`
- `docs/design/references/ui-snapshots/research-drive-right-rail-folder-tree.png`

What to preserve from those: the sense that the right side is the command/evidence anchor. What to drop: full-screen terminal styling, generic assistant cards, and duplicate navigation trees competing with the main Library.

---

## 8. Upgrade rule

New capabilities attach to the rail before they become navigation:

| Capability growth | Where it appears first |
|-------------------|------------------------|
| New data source | Discover row + `external_candidate` Detail |
| New collected dataset | Library row + `dataset` Detail |
| New worker/job type | Resources row + `resource_row` Detail |
| New profile signal | Profile scope + Ask context |
| New storage tier | Resources storage row + dataset vault path |
| New query backend | Dataset readiness + Preview modal |

If the feature needs its own full page, prove why the rail object is not enough.

---

## 9. Acceptance checklist

- [ ] Every tab renders the same `InspectorRail`.
- [ ] Selecting a dataset/candidate/job switches rail to `Detail`.
- [ ] Search Enter, `Ask about this`, and `Add to lab` switch rail to `Ask`.
- [ ] `Ask` persists its session across tab switches.
- [ ] `Detail` does not rely on Composer prose for canonical fields.
- [ ] Desktop grid uses a 440px rail target at 1440px.
- [ ] No new UI mentions DeepSeek, magic procure, Python planner, `/library/magic`, `/library/assist`, or `/library/workflow`.
- [ ] Legacy `Source`/`Pipeline` names are not used in v2 nav.


### Current v2 entity additions

The rail contract must also support `synthesis_recipe` and `synthesis_output`. Detail receives the selected blueprint/output identity, input readiness, gap identities, output authority, and allowed UI intents. Ask receives the same typed context plus evidence scope; it must not fall back to a generic “Synthesis studio” prefix.

The rail is visually intense only for an active evidence object or Ask. It must not be used to impose a permanent empty inspector on an idle page.
