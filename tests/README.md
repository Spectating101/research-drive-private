# Test suite guardrails

Full suite target: **≤200 tests**, **<30s** on a normal laptop.

```bash
.venv/bin/pytest tests/ -q
```

## Rules (non-negotiable)

1. **One contract per behavior** — e.g. search ranking lives in `test_procurement_search.py`, not `test_procurement_search_v2.py`.
2. **No new file per layer** — do not add `test_procurement_chat_actions.py`, `test_procurement_mcp_http.py`, etc. unless deleting an equivalent.
3. **No full-stack procurement tests** — no live Composer/Cursor API, no live cluster, no 3-hour integration grids in default `pytest tests/`.
4. **No competitor benchmark tests** — do not add vanilla-vs-equipped grids to CI.
5. **Mock external I/O** — network, Cursor API, SQLite job queues: mock or use `tmp_path` fixtures.

## What belongs here

| Area | Files |
|------|-------|
| Alpha paper pipeline | `test_alpha_*.py`, `test_paper_*.py`, `test_scorecard*.py` |
| Research integrity | `test_fingerprint.py`, `test_deflated_sharpe.py`, … |
| Desk contracts | `test_procurement_search.py`, `test_procurement_equipment_bridge.py` |
| Query engine | `test_research_query_engine_panels.py` |
| API / data scripts | `test_api_*.py`, `test_sec_*.py`, `test_coingecko_*.py` |

## Before adding tests

- Can an existing file gain one focused `def test_...` instead?
- Will `pytest tests/ -q` stay under 30s?
- If it needs live API keys, it does **not** belong in default suite.

## Hygiene check

```bash
.venv/bin/pytest tests/ --collect-only -q | tail -1   # should show ~150 tests
```

If collection exceeds 200, stop and delete or merge — do not mark everything `@pytest.mark.slow`.
