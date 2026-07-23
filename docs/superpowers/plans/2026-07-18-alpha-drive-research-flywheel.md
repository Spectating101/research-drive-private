# Alpha–Drive Research Flywheel Implementation Plan

> **For agentic workers:** implement task-by-task. Drive tree is read-only.

**Goal:** Wire Drive data supply into the alpha research loop with beta fallback when gates fail.

**Architecture:** Fuel manifest + inventory (kernel) → research cycle report → live cycle uses beta_core on block.

**Tech Stack:** Python 3.11+, sharpe_kernel, existing promote_signal gates

---

### Task 1: Fuel manifest + drive_fuel + beta_core
### Task 2: Live cycle on-block → beta_core
### Task 3: Research cycle CLI + platform config
### Task 4: Tests
