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

`main` is **not** what runs. As of 2026-08-25 it is 43 commits behind the
deployed backend.

| Branch | What it is |
|---|---|
| `live/deployed-backend-20260825` | The backend actually serving `:8765` (`687529d7`). Base new work here. |
| `work/discover-relevance-20260825` | The above plus in-flight search-relevance fixes, tested but **not deployed**. |
| `main` | 43 commits stale. Do not assume it reflects production. |
| `snapshot/live-20260825` | **Mislabelled.** Its message says "current live Research Drive" but it does not contain the deployed SHA; it is a diverged lineage. Do not treat it as live. |

The UI is a *different* repository: `Spectating101/yzu-cluster`, branches
`live/deployed-ui-20260825` and `work/discover-web-context-20260825`. Do not
look for the desk frontend in this repo.

## Setup and tests (verified from a bare container)

```bash
python3 -m venv .venv && .venv/bin/pip install pytest pandas pyarrow
PYTHONPATH=drive .venv/bin/python -m pytest drive/tests -q
```

Expect **173 passed, 1 skipped** in ~2s. The skip (`test_invariant_inventory`)
is correct off-host: it needs a deployed `build.json`.

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

1. **Never push to `main`** and never force-push any branch. Open a PR.
2. **Never** attempt to deploy, promote a release, or restart a service. The
   front door has a startup guard that compares the checkout SHA against the
   built release; moving `HEAD` in a serving tree takes the desk down. This has
   already caused one outage.
3. Commit only files you changed. Check `git status` before staging; other
   agents and machine processes leave unrelated files dirty.
4. If a change cannot be verified offline, state the verification the human
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
