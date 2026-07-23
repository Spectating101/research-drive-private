# Alpha ↔ Drive research flywheel

**Status:** Approved for implementation (user: take the lead)
**Date:** 2026-07-18
**Scope:** `alpha/` + `kernel/` only — do not edit Drive app/UI/MCP handlers

## Doctrine

Drive is the **data supply chain**. The alpha engine is the **research lab**. Loop until a candidate clears promotion gates (or the search space is honestly exhausted).

```text
Drive supply (registry / MCP / API / jobs)
  → kernel resolve (local panels)
  → engine research (features → walk-forward → DSR/PBO/α/costs)
  → promote OR beta_core fallback
  → scorecard / next supply asks
  → repeat
```

Live paper/trading must not depend on `:8765` or MCP uptime. Those surfaces are for inventory, sampling, and procurement requests.

## Capital policy

When `promotion_gate=block` fails: export **`beta_core`** weights (transparent multi-asset, no crypto sleeve), not the rejected prior alpha weights.

## Fuel set

Declared in `alpha/config/alpha_fuel_manifest.json`. Inventory via kernel; optional HTTP query for readiness checks. Gaps become supply asks for Drive MCP/API operators.

## Non-goals (this slice)

- Editing Drive source or Discover UX
- Auto-submitting YZU jobs from alpha without an explicit later flag
- Claiming alpha before gates pass
