# Discover Evaluation Surface — visual notes

Design-review evidence for the combined D2+D3 Evaluation Surface pass.
Before references are D1 main screenshots (`before-d1-*`). After shots are `01`–`09`.

## Before / after intent

| Before (D1) | After (Evaluation Surface) |
|---|---|
| Metadata rail: Possession / Readiness / Source / License field grid | Decision workspace: identity → Can I use this? → Useful for → Coverage → Verified / Still unknown → actions |
| Probe dumps connector fields in primary scroll | Verified / Inferred summaries; Technical evidence collapsed |
| Pale selected row | Stronger left border + marker + shared title with Detail |
| Add to lab often primary for every external | Primary action follows taxonomy |

---

## 01 — `01-desktop-external-before-probe.png` (1440×900)

- **User decision:** Can I inspect this unprobed external source, and what should I do first?
- **Primary visual focus:** Selected row ↔ Detail identity; “Can I use this? · Available to inspect”; primary **Probe source**
- **Deliberately demoted:** Connector IDs, raw probe JSON, equal-weight metadata fields
- **Known responsive limitation:** Dual-pane desktop composition; mobile still uses rail overlay (not final responsive pass)

## 02 — `02-desktop-external-after-probe.png` (1440×900)

- **User decision:** What did the probe actually prove vs leave unknown?
- **Primary visual focus:** Verified checklist + Still unknown; Inferred marked separately; Technical evidence collapsed
- **Deliberately demoted:** Connector ID, ETag, raw summary (under Technical evidence / Model interpretation)
- **Known responsive limitation:** Long unknown lists may scroll inside rail; tablet/mobile not redesigned here

## 03 — `03-desktop-acquisition-available.png` (1440×900)

- **User decision:** A collection route exists — add to lab or probe first?
- **Primary visual focus:** “External · Acquisition available” decision block; primary **Add to lab**; Probe secondary when not yet probed
- **Deliberately demoted:** Lifecycle/approval states (D4 not started); backend job vocabulary
- **Known responsive limitation:** Same as desktop dual-pane

## 04 — `04-desktop-licensed-manual.png` (1440×900)

- **User decision:** This is not an immediate Add-to-lab path — what access work remains?
- **Primary visual focus:** Licensed / manual decision; primary **Review access requirements** (not Add to lab)
- **Deliberately demoted:** Fake acquisition CTAs; legal-clearance claims
- **Known responsive limitation:** Ask chips wrap; fine on desktop, denser on tablet

## 05 — `05-desktop-local-query-ready.png` (1440×900)

- **User decision:** Already in lab and queryable — open it?
- **Primary visual focus:** “In lab · Query ready”; primary **Open in Library**
- **Deliberately demoted:** Probe/acquisition language for local holdings
- **Known responsive limitation:** None specific beyond existing Library handoff

## 06 — `06-tablet-external-after-probe.png` (900×1200)

- **User decision:** Same probe-truth evaluation on a narrower desktop/tablet width
- **Primary visual focus:** Decision + Verified / Unknown still readable; list remains scannable
- **Deliberately demoted:** Full technical dump
- **Known responsive limitation:** Not the final tablet redesign — rail may feel tall; composition not reflowed to single-column evaluation mode

## 07 — `07-mobile-selected-row.png` (390×1200)

- **User decision:** Which candidate am I evaluating?
- **Primary visual focus:** Selected row marker/border in the list
- **Deliberately demoted:** Full Detail until opened
- **Known responsive limitation:** Mobile still list-first; Detail is a separate overlay/sheet — final responsive pass deferred

## 08 — `08-mobile-detail-after-probe.png` (390×1200)

- **User decision:** After opening Detail, can I still read usability + uncertainty?
- **Primary visual focus:** Decision headline + Verified / Still unknown on a narrow rail
- **Deliberately demoted:** Technical evidence (collapsed)
- **Known responsive limitation:** Sticky footer actions compete with scroll; not final mobile layout

## 09 — `09-mobile-detail-ask-context.png` (390×1200)

- **User decision:** Ask while retaining the selected candidate
- **Primary visual focus:** Ask header “Evaluating · …” with selected title
- **Deliberately demoted:** Ask as primary Discover interface (Detail remains the evaluation surface)
- **Known responsive limitation:** Chip prompts truncate; full Ask redesign not in scope

---

## Backend contract gaps

None blocked honest presentation in this pass.

If later needed for richer Verified bullets:

| Field needed | Current evidence | Why frontend inference would be dishonest |
|---|---|---|
| Explicit `http_status` on all probe successes | Sometimes only connector/spec present | Inventing 200 from “probe returned” overclaims |
| `robots` / auth challenge flags | Not consistently returned | Claiming “open” or “auth required” without response evidence |
| Schema sample / column names | Only discovered_files occasionally | Inventing schema from content-type alone |

## Scope confirmations

- Acquisition lifecycle (approval / running / completed / archive): **not started**
- Local sufficiency / equivalence: **not started**
- Final tablet/mobile responsive redesign: **not started**
