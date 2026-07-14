# Discover E2E clean audit report — 2026-07-14

Identity: see `discover_e2e_clean_audit_identity_2026-07-14.md`

```text
git_sha:     534a78a4d334f3e9157fc76d1d464b5c0a6061fd
vite_url:    http://127.0.0.1:5180
vite_cwd:    .../Sharpe-Renaissance-discover-converge
data_mode:   fixture/mock
workers:     1
result:      4 passed · 5 failed
```

## Classification

| Test | Result | Class | Notes |
|---|---|---|---|
| Explore and History as stable modes | PASS | CURRENT | Critical contract green |
| LEGACY: Activity workspace is not a Discover mode | PASS | LEGACY guard | Activity absent — good |
| empty state shows suggestions | PASS | CURRENT | |
| Probe source shows verified facts | PASS | CURRENT | |
| header pending opens Explore queue | FAIL | CURRENT AUTHORITY FAILURE | Pending selection entered Focus without queue strip |
| suggestion chip → demo results | FAIL | SELECTOR DRIFT | Expected 1 `.rd-v2-catalog` candidate; UI renders 3 grouped candidates |
| selecting row → evaluation surface title | FAIL | SELECTOR DRIFT | Fixture title `Taiwan MOPS / governance procured` ≠ hard-coded `MOPS financial statements` |
| mobile Focus geometry | FAIL | SELECTOR DRIFT | `actionsBottom` 1101 vs ≥1107 (6px) |
| Ask actions carry candidate context | FAIL | SELECTOR DRIFT | Same title hard-code mismatch |

Environment: **not** contaminated (Vite cwd matches converge worktree).

## Post-fix verification (same identity, :5180)

After CURRENT fix (queue strip visible in Focus chrome) and SELECTOR DRIFT e2e alignment:

```text
9 passed · 0 failed
YZU_DESK_URL=http://127.0.0.1:5180
workers=1
```

LEGACY Activity workspace remains absent (guard test green). No Activity-positive tests remained on main to retire.
