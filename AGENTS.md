# Agent notes — research-drive-private

Read this before `CLAUDE.md`. `CLAUDE.md` describes the Sharpe-Renaissance
quant platform; the Research Drive desk lives under `drive/` and is what most
current work touches.

## You are probably in a cloud container

If you are Codex (or any hosted agent), you have the repo and nothing else.
You do **not** have:

- the running desk (`:8765`) or any of its HTTP endpoints
- the bulk research drive (`/mnt/research-data/...`) or the 17GB `data_lake/`
- the dataset registry contents, procured files, or the semantic index cache
- the Copilot/composer runtime, `systemd`, or any deploy tooling

Work that cannot be verified without those is work you cannot verify. Say so
plainly rather than reporting it as done. A passing unit test is not evidence
that a desk endpoint changed behaviour — that distinction has burned this
project repeatedly.

## Which branch is real

As of 2026-08-27, canonical `main` has been reconciled to the deployed backend
baseline. The deployed service itself remains pinned to commit
`687529d7a9c7963e65b7d0e306467187417ac8c7`; canonicalization does **not** imply
a deployment or service restart.

| Branch | What it is |
|---|---|
| `main` | Canonical repository history. Its product code includes the `687529d7` deployed baseline plus documentation-only canonicalization history. |
| `live/deployed-backend-20260825` | Exact backend commit serving `:8765` (`687529d7`). Preserve this ref as deployment provenance. |
| `work/discover-relevance-20260825` | Deployed baseline plus in-flight search-relevance fixes; tested but **not deployed**. |
| `snapshot/live-20260825` | **Mislabelled.** Its message says "current live Research Drive" but it does not contain the deployed SHA; it is a diverged lineage. Do not treat it as live. |
| `yzu/main` | Detached/imported public YZU Cluster UI history with no common ancestor to backend `main`; do not merge it into the backend lineage. |

For ordinary repository work, start from current `main` unless a specific active
release/hardening branch documents a stronger base requirement. For work that
must reproduce the currently serving backend exactly, use
`live/deployed-backend-20260825` and do not mutate that ref.

The current UI is a *different* repository: `Spectating101/yzu-cluster`, with
its own deployed and hardening branches. Do not treat `yzu/main` in this repo as
the frontend authority.

## Setup and tests (verified from a bare container)

```bash
python3 -m venv .venv && .venv/bin/pip install pytest pandas pyarrow
PYTHONPATH=drive .venv/bin/python -m pytest drive/tests -q
```

Expect **173 passed, 1 skipped** in ~2s on the documented baseline. The skip
(`test_invariant_inventory`) is correct off-host: it needs a deployed
`build.json`.

`sentence_transformers`, `httpx`, `mcp`, `jwt` and friends are imported lazily
and are not needed for this suite. Do not install them to "be safe" — a slow
container helps nobody.

## Where the desk code is

- `drive/scripts/research_data_mcp/` — gateway, semantic index, procurement
  search, discovery adapters. Most relevance and retrieval logic.
- `drive/scripts/research_query_engine/` — the HTTP server and its front door.
- `drive/tests/` — the suite above.
- `drive/config/research_query_registry.json` — the dataset registry. It is
  frequently dirty in working trees with machine-generated drift. **Never
  commit it as a side effect** of unrelated work.

## Rules

1. **Never push directly to `main`** and never force-push any branch. Open a PR.
2. **Never** attempt to deploy, promote a release, or restart a service unless
   that is the explicit task and the host-side release procedure is available.
   The front door has a startup guard that compares the checkout SHA against
   the built release; moving `HEAD` in a serving tree can take the desk down.
3. Do not mutate `live/deployed-backend-20260825`; it is retained as exact
   deployment provenance.
4. Commit only files you changed. Check `git status` before staging; other
   agents and machine processes leave unrelated files dirty.
5. If a change cannot be verified offline, state the verification the human
   must run, and do not claim the change works.

## Traps this codebase has actually hit

- **Parity drift is the dominant defect class.** The same concept is often
  implemented twice and the copies disagree. There are several separate
  stopword/tokenizer lists (`semantic_index.STOPWORDS`,
  `procurement_search.PROCUREMENT_QUERY_STOPWORDS`, others). A word filtered on
  one path but not another means the layers disagree about the query. When you
  touch one, bind or test the others.
- **A capability route is not evidence.** The discovery layer can return
  generic acquisition routes (GDELT, DataCite, BigQuery) that answer any query.
  Counting them as matches makes an empty result look full.
- **Changing tokenisation invalidates the index cache.** Bump
  `INDEX_SCHEMA_VERSION` in `semantic_index.py` or stale vectors are served.
- **Verify at the endpoint, not the function.** Several past fixes passed their
  unit tests and changed nothing in the running product.
