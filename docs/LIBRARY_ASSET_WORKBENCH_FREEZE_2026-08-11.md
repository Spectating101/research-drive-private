# Research Drive — Library asset workbench freeze

**Status:** FROZEN VISUAL / INTERACTION AUTHORITY  
**Date:** 2026-08-11  
**Scope:** Library evidence estate, selected-asset workspace, Detail / Ask rail, preview and local-preparation overlays.  
**Amends:** [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md). The July 15 Library freeze is withdrawn ([`superseded/README.md`](superseded/README.md)).  

This is a scoped freeze. It does **not** reopen Library collection semantics, the global seven-destination shell, Discover, Synthesis, Resources, or query-workspace composition.

---

## 1. Library thesis

Library is the evidence estate: the place where a researcher understands and uses evidence the lab owns or is actively preparing. It is not an external catalogue, generic cloud drive, or a standalone dataset-detail product.

```text
Library asset row
  → select within Library
  → understand meaning + usability + limitation
  → inspect or act without losing the estate
  → selected asset visibly changes state when a durable consequence occurs
```

The global shell remains mounted in every state:

```text
Navigation | Library centre | Detail / Ask rail
```

No Library asset action removes the sidebar or presents a new top-level product destination.

---

## 2. Centre and rail responsibilities

```text
CENTRE
  evidence estate when no asset is selected
  selected-asset workspace when an asset is selected

DETAIL
  what the asset is
  what it supports
  what it does not establish
  source, verification, and readiness truth
  the one valid next action

ASK
  a grounded conversation about the exact selected asset
  its declared coverage, fields, state, provenance, and limitation
```

Ask is not a generic chatbot. Its composer must identify the selected asset and retain that context until the asset is changed or the user clears it.

---

## 3. Canonical Library state language

Use the existing authoritative readiness vocabulary exactly:

```text
QUERY-READY
  A verified local query path is available.

REGISTERED
  A durable registry record exists, but local query use is not implied.

METADATA ONLY
  A catalogue/metadata record exists; no owned usable evidence is implied.

UNAVAILABLE / NOT VERIFIED
  The system cannot establish a usable local state.
```

`Preparing local copy` is an in-progress lifecycle treatment of a Registered asset, not a fifth readiness claim.

Hard truth rules:

```text
registered ≠ local bytes present
archive path ≠ archive verified
completed job ≠ registered
registered ≠ query-ready
```

The UI must not expose Preview rows, local query, sample analysis, or data-derived Ask claims for an asset until the corresponding local/query readiness is confirmed.

---

## 4. Frozen screen family

### 4.1 Estate — no asset selected

The centre contains, in this order:

```text
Library title + concise boundary statement
Library search
readiness filters
compact evidence ledger grouped or filtered by actual state
```

Normal row grammar remains:

```text
TITLE                     SOURCE       VERIFY       STATE
plain-language one-line description
```

The description is mandatory. Grain, rows, field counts, archive paths, or other metadata never substitute for a human explanation of what the evidence is about.

The empty rail explains the Library boundary and prompts selection; it is not a blank inspector.

### 4.2 Selected asset — query-ready

Selecting a row is a state change within Library. The evidence ledger remains recoverable through the same Library context; the sidebar remains visible.

The selected-asset centre composition is exactly:

```text
asset title + QUERY-READY state
plain-language description
one primary action: Open query
secondary inspection actions: Preview rows · View fields · source/provenance disclosure

WHAT YOU HAVE
  unit/grain · period · scope · meaningful keys · actual row scale when declared

WHAT IT SUPPORTS
  plain-language research uses

WHAT IT DOES NOT ESTABLISH
  meaningful limitation, when declared or inferable from coverage

DATA GLIMPSE
  a compact sample, with Preview 100 rows as an overlay trigger

FIELDS / OPERATIONS
  declared fields and capabilities; schema and provenance remain disclosures
```

The selected Detail rail answers `Can I use it now?`, then shows verified state and the material limitation. Ask occupies the same rail when selected.

### 4.3 Bounded inspection overlays

The following are overlays over the selected Library state, never pages or sidebar destinations:

```text
Preview rows
Schema / fields inspection
Provenance / source record
```

An overlay has one visible body at a time, an explicit close affordance, Escape and scrim-close behavior, and preserves selected asset plus rail context underneath.

`Open query` may replace the **centre canvas** with a query workspace while retaining the Library shell, selection, and right rail. Its detailed query-builder composition is intentionally not frozen by this document.

### 4.4 Registered asset — local copy absent

For a Registered asset without a confirmed local query path:

```text
primary action: Prepare local copy
allowed inspection: metadata, declared coverage, source and verification record
not available: sample rows, local query, analysis of local data
```

The centre must distinguish what is confirmed from what is still absent. The rail explains that registration does not imply local usability.

### 4.5 Prepare-local-copy confirmation

`Prepare local copy` opens a small confirmation modal. It must name:

```text
asset identity
destination in the Library vault (when known)
what preparation does
what is not promised until verification completes
the researcher’s approval boundary
```

It must never promise query readiness. The confirmation action uses preparation language, not `Add`, `Use now`, or `Query-ready`.

### 4.6 Preparing

After approval, the selected asset stays in Library and enters a visible `Preparing local copy` state. It may show progress only when the backend supplies it. It must state the remaining verification boundary before preview/query becomes available.

No separate Library page, pipeline page, or forced navigation follows confirmation.

---

## 5. Action hierarchy

| Asset state | Primary action | Secondary action |
|---|---|---|
| Query-ready | Open query | Preview rows; View fields; Ask |
| Registered, no local copy | Prepare local copy | Inspect metadata; Ask about access |
| Preparing | Refresh status | Cancel only if backend permits; Ask |
| Metadata only | Inspect metadata | Ask; find owned equivalent only when grounded |
| Unavailable / not verified | Ask about limitation | Inspect evidence record |

Do not give actions equal visual weight. A state has one dominant valid next move.

---

## 6. Explicit prohibitions

```text
No standalone /library/dataset/:id product page.
No loss of the persistent sidebar during Library inspection.
No generic empty Detail rail.
No source/provenance wall in ledger rows.
No generic Query-ready label for registered metadata.
No Preview rows before a verified local query path.
No “in lab”, “held”, and “Library evidence” vocabulary drift.
Use “Library” for owned/registered evidence and “Beyond your Library” only for external evidence.
```

---

## 7. Acceptance tests

The Library implementation is conformant only when rendered workflows demonstrate:

1. Estate → select a query-ready asset without losing shell context.
2. Query-ready asset → Preview modal → close returns to the same selected asset.
3. Selected-asset Ask gives an answer grounded in that asset’s actual fields/state or plainly states missing metadata.
4. Registered/no-local asset never offers local preview or query; it offers Prepare local copy.
5. Preparation confirmation makes no promise beyond preparation and verification.
6. Preparing state does not claim archive verification, registration, or query readiness before the corresponding backend truth.
7. All states remain usable with the persistent desktop sidebar and mobile rail treatment.

---

## 8. Change control

Any new permanent Library destination, replacement of the selected-asset workspace, or change to readiness language requires an explicit amendment to this document and `UI_PRODUCT_AUTHORITY.md` before implementation.
