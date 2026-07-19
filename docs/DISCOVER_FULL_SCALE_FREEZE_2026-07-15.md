# Research Drive — Discover full-scale freeze

**Status:** FROZEN VISUAL / INTERACTION AUTHORITY  
**Date:** 2026-07-15  
**Authority:** Normative Discover appendix incorporated by [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md)  
**Scope:** `drive/src/v2/*`, Discover API projections, typed rail context, Discover tests, rendered-pixel review  

This appendix preserves the complete Discover composition approved during the 2026-07-15 convergence pass. It is intentionally visual-first. The CLI wireframes below are implementation authority, not illustrative sketches.

No current component, screenshot, fixture, test, Focused Evaluation workspace, Activity feed, or backend event kind overrides this appendix. A proposed Discover composition change must amend `UI_PRODUCT_AUTHORITY.md` and this appendix before implementation.

---

## 1. Frozen Discover thesis

```text
RESEARCH NEED

        ↓

EXPLORE

find and rank candidate evidence

        ↓

SELECT

centre preserves evidence landscape

        ↓

DETAIL

understand selected source
fit
local gap
knowns
unknowns
next decision

        ↓

ASK

investigate
probe
reason
operate platform

        ↓

DURABLE EVIDENCE REQUEST

        ↓

HISTORY

one persistent research object

        ↓

ROUTE INVESTIGATION

API?
HTTP manifest?
query route?
Spectator?
Playwright?
browser extraction?
custom connector?

        ↓

METHOD REVIEW
when researcher decision required

        ↓

EXECUTION

        ↓

EVIDENCE SHAPE / ARCHIVE / REGISTRY

        ↓

QUERY-READY LIBRARY ASSET

        ↓

SYNTHESIS
```

Discover is the evidence-procurement transformation surface:

```text
research evidence requirement
→ candidate evidence
→ bounded inspection
→ durable evidence request
→ acquisition-method engineering when required
→ execution
→ evidence promotion
```

It is not a generic dataset finder, chat page, worker dashboard, event feed, or pipeline builder.

Frozen Discover modes:

```text
Explore | History
```

Frozen application grammar:

```text
Navigation | Centre | Detail / Ask
```

Centre answers:

```text
What exists?
What state is it in?
```

Detail answers:

```text
What does that state mean?
What is known?
What is unknown?
What decision exists?
```

Ask answers:

```text
What can Research Drive investigate or operate on this exact selected object?
```

---

# 2. Discover · Explore — full-scale frozen authority

## 2.1 Full desktop / 1440 × 1024

```text
RESEARCH DRIVE — DISCOVER · EXPLORE
FULL-SCALE FROZEN CLI WIREFRAME

DESKTOP / 1440 × 1024


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   DISCOVER                                             │ DETAIL ●              ASK           │
│                        │                                                                             │ ETHEREUM / USDT HISTORY             │
│    Home                │ EXPLORE ●                                                    HISTORY 3      │                                     │
│    Library             │                                                                             │ BigQuery public datasets             │
│  ● Discover            │ WHAT EVIDENCE ARE YOU LOOKING FOR?                                          │ Transaction-level · Public           │
│    Synthesis           │                                                                             │                                     │
│    Resources           │ ┌─────────────────────────────────────────────────────────────────────────┐ │ BEST FIT                            │
│    Profile             │ │ I need transaction-level stablecoin evidence around market stress      │ │                                     │
│    Settings            │ │ events before 2020, preferably with entity identifiers.             ⌕ │ │ Strong match for the current       │
│                        │ └─────────────────────────────────────────────────────────────────────────┘ │ evidence need.                      │
│ ACTIVE RESEARCH        │                                                                             │                                     │
│                        │ INTERPRETING                                                                │ Why it fits                         │
│ Stablecoin Research   │                                                                             │                                     │
│                        │ Stablecoins · Transactions · Pre-2020 · +2                                │ • transaction-level transfers       │
│ Event studies          │                                                                             │ • historical Ethereum coverage      │
│                        │ Refine evidence need ▾                                                     │ • stablecoin records available      │
│ Market structure       │                                                                             │                                     │
│                        │ BEST FIT                                                                   │ In your lab                         │
│ ────────────────────── │                                                                             │                                     │
│                        │ ▌ ETHEREUM / USDT ON-CHAIN HISTORY                                         │ Partial                             │
│ RECENT                 │                                                                             │                                     │
│                        │   BigQuery public datasets · Transaction-level · Public                   │ Existing                            │
│ USDT transactions      │                                                                             │ USDT transaction dataset            │
│ Event study panel      │   Transactions · Stablecoins · Earlier history                             │ 2020–2024                           │
│                        │   Partial · local evidence begins in 2020                                  │                                     │
│                        │                                                                             │ Gap                                 │
│                        │   2017–present reported coverage · Preview available                       │ Earlier transaction history         │
│                        │                                                                             │                                     │
│                        │ OTHER MATCHES                                                               │ What is known                       │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │                                                                             │ • timestamps                        │
│                        │ ETHERSCAN API                                                              │ • transaction identifiers           │
│                        │                                                                             │ • counterparties                    │
│                        │ Etherscan · Transaction-level · Public API                                 │ • raw transfer values               │
│                        │                                                                             │                                     │
│                        │ Transactions · Stablecoins                                                  │ Unknowns                            │
│                        │ Related · equivalence not established                                     │                                     │
│                        │                                                                             │ ? complete historical coverage      │
│                        │ ─────────────────────────────────────────────────────────────────────────── │ ? entity mapping quality            │
│                        │                                                                             │ ? final query cost                  │
│                        │ HISTORICAL STABLECOIN DATASETS                                              │                                     │
│                        │                                                                             │ [ Preview source ]                  │
│                        │ Research catalogues · Tabular sources · Access unverified                  │                                     │
│                        │                                                                             │ Request this evidence               │
│                        │ Stablecoins · Historical coverage                                           │                                     │
│                        │ Comparison unknown                                                         │ Evidence and access ▸               │
│                        │                                                                             │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │                                                                             │                                     │
│                        │ GDELT EVENTS                                                               │                                     │
│                        │                                                                             │                                     │
│                        │ GDELT · Event-level · Public API                                           │                                     │
│                        │                                                                             │                                     │
│                        │ Event study · Market stress                                                │                                     │
│                        │ Related · event context, not transaction evidence                         │                                     │
│                        │                                                                             │                                     │
│                        │ 34 candidates                                                   Filters ▾   │                                     │
│                        │ Ranked using active research + interpreted evidence need                    │                                     │
│                        │                                                                             │                                     │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Selection stays in ranked results · Detail expands selected evidence          │ Source judgment                      │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

### Frozen Explore selection rule

```text
NO

select source
    ↓
centre becomes giant Focused Evaluation


YES

select source
    ↓
result remains selected in ranked list
    ↓
DETAIL expands its meaning
```

The `▌` marker is the selected-state authority. Do not use full-row cobalt fill, cards, checkboxes, radios, or a second centre workspace.

## 2.2 Frozen entry grammar

Long research need:

```text
WHAT EVIDENCE ARE YOU LOOKING FOR?

┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ I need transaction-level stablecoin evidence around market stress events before 2020, preferably   │
│ with entity identifiers.                                                                        ⌕ │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘

INTERPRETING

Stablecoins · Transactions · Pre-2020 · +2

Refine evidence need ▾
```

Short query:

```text
WHAT EVIDENCE ARE YOU LOOKING FOR?

┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ethereum transactions                                                                            ⌕ │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘

INTERPRETING

Ethereum · Transactions

Refine evidence need ▾
```

Analytical description:

```text
WHAT EVIDENCE ARE YOU LOOKING FOR?

┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ I want to compare transfer behaviour before and after major stablecoin stress events across         │
│ entities and markets.                                                                            ⌕ │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘

INTERPRETING

Stablecoins · Transfers · Event comparison · Entity analysis · +1

Refine evidence need ▾
```

Coverage gap:

```text
WHAT EVIDENCE ARE YOU LOOKING FOR?

┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ My local USDT panel starts in 2020. I need comparable transaction evidence before that period.      │
│                                                                                                  ⌕ │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘

INTERPRETING

USDT · Transactions · Before 2020 · Local coverage gap

Refine evidence need ▾
```

Same surface accepts keyword, question, research description, coverage gap, and evidence requirement. No Keyword Search, Semantic Search, AI Search, or Advanced Search tabs.

## 2.3 Interpretation authority

Default:

```text
INTERPRETING

Stablecoins · Transactions · Pre-2020 · +2

Refine evidence need ▾
```

Expanded:

```text
INTERPRETING

Stablecoins
Transactions
Event study
Pre-2020
Entity identifiers

┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ RESEARCH OBJECT       Stablecoins                                                                   │
│ EVIDENCE NEED         Transaction records                                                           │
│ ANALYTICAL USE        Event study                                                                   │
│ COVERAGE              Before 2020                                                                   │
│ PREFERRED FIELDS      Entity identifiers                                                            │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘

Collapse interpretation ▴
```

Interpretation is a readout, not navigation or a wizard. Default visible budget is three named signals, one additional signal when space permits, then `+N` overflow.

## 2.4 Result-row authority

```text
TITLE
provider · proven evidence shape · proven access
compact named match signals
local relationship
optional coverage / preview truth
```

Maximum normal row: five visible lines.

Missing fact means remove the claim:

```text
unknown grain
→ omit evidence-shape claim

unknown coverage
→ Coverage not reported

unknown access
→ Access not verified

unknown match signals
→ omit match line

unknown comparator result
→ Comparison unknown

completed comparator with no qualifying asset
→ No local alternative
```

Composer interprets the query and may explain a typed match. Composer does not create source facts.

## 2.5 Explore Ask — same selected source

```text
DISCOVER · EXPLORE
SAME SELECTED SOURCE — ASK ACTIVE


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   DISCOVER                                             │ DETAIL                ASK ●         │
│                        │                                                                             │ ETHEREUM / USDT HISTORY             │
│    Home                │ EXPLORE ●                                                    HISTORY 5      │                                     │
│    Library             │                                                                             │ Selected source context             │
│  ● Discover            │ WHAT EVIDENCE ARE YOU LOOKING FOR?                                          │ BigQuery public datasets             │
│    Synthesis           │                                                                             │ Transaction-level · Public           │
│    Resources           │ ┌─────────────────────────────────────────────────────────────────────────┐ │                                     │
│    Profile             │ │ I need transaction-level stablecoin evidence around market stress      │ │ You                                 │
│    Settings            │ │ events before 2020, preferably with entity identifiers.             ⌕ │ │                                     │
│                        │ └─────────────────────────────────────────────────────────────────────────┘ │ I need this before 2020. Can we     │
│ ACTIVE RESEARCH        │                                                                             │ actually acquire it?                │
│                        │ INTERPRETING                                                                │                                     │
│ Stablecoin Research   │                                                                             │ Research Drive                      │
│                        │ Stablecoins · Transactions · Pre-2020 · +2                                │                                     │
│ Event studies          │                                                                             │ Checking this source against the    │
│                        │ Refine evidence need ▾                                                     │ selected evidence need and current  │
│ Market structure       │                                                                             │ lab gap.                            │
│                        │ BEST FIT                                                                   │                                     │
│ ────────────────────── │                                                                             │ Agent activity                      │
│                        │ ▌ ETHEREUM / USDT ON-CHAIN HISTORY                                         │                                     │
│ RECENT                 │                                                                             │ ✓ candidate facts loaded            │
│                        │   BigQuery public datasets · Transaction-level · Public                   │ ✓ local coverage compared           │
│ USDT transactions      │                                                                             │ ✓ direct source route checked       │
│ Event study panel      │   Transactions · Stablecoins · Earlier history                             │ ● evaluating acquisition route      │
│                        │   Partial · local evidence begins in 2020                                  │                                     │
│                        │                                                                             │                                     │
│                        │   2017–present reported coverage · Preview available                       │                                     │
│                        │                                                                             │                                     │
│                        │ OTHER MATCHES                                                               │                                     │
│                        │ ...                                                                         │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │ 34 candidates                                                   Filters ▾   │ ┌─────────────────────────────────┐ │
│                        │                                                                             │ │ Ask about this source…          │ │
│                        │                                                                             │ │                           Send │ │
│                        │                                                                             │ └─────────────────────────────────┘ │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Ask operates the same selected source · centre selection never disappears    │ Acquisition investigation           │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

Ask must preserve the selected source context and operate supported platform equipment. Completed phase sequences collapse by default; the final message should show a small durable receipt when a mutation occurred.

---

# 3. Evidence-request entry — History begins before method resolution

The History item must exist before the procurement method exists.

```text
NOT

agent figures everything out
        ↓
done method appears in History


INSTEAD

researcher commits an evidence need
        ↓
durable History object created immediately
        ↓
route / method is investigated INSIDE that object
        ↓
method proposed
        ↓
review / execute
```

## 3.1 Explore source selected — no durable request yet

```text
DISCOVER · EXPLORE
SOURCE SELECTED / NO DURABLE REQUEST YET


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   DISCOVER                                             │ DETAIL ●              ASK           │
│                        │                                                                             │ TAIWAN GOVERNANCE ARCHIVE           │
│    Home                │ EXPLORE ●                                                    HISTORY 5      │ Government web records              │
│    Library             │                                                                             │ Public · Access observed             │
│  ● Discover            │ WHAT EVIDENCE ARE YOU LOOKING FOR?                                          │                                     │
│    Synthesis           │                                                                             │ RELEVANT                            │
│    Resources           │ ┌─────────────────────────────────────────────────────────────────────────┐ │                                     │
│    Profile             │ │ I need historical point-in-time governance records for Taiwan firms,    │ │ The archive appears relevant to    │
│    Settings            │ │ with entity, date, role, and source reference.                       ⌕ │ │ the requested governance evidence. │
│                        │ └─────────────────────────────────────────────────────────────────────────┘ │                                     │
│ ACTIVE RESEARCH        │                                                                             │ Why it fits                         │
│                        │ INTERPRETING                                                                │                                     │
│ Stablecoin Research   │                                                                             │ • historical records observed       │
│                        │ Taiwan firms · Governance · Point-in-time · Entity records · +1             │ • entity pages available            │
│ Event studies          │                                                                             │ • reporting periods visible         │
│                        │ Refine evidence need ▾                                                     │                                     │
│ Market structure       │                                                                             │ In your lab                         │
│                        │ BEST FIT                                                                   │                                     │
│ ────────────────────── │                                                                             │ No local alternative                │
│                        │ ▌ TAIWAN GOVERNANCE ARCHIVE                                                 │                                     │
│ RECENT                 │                                                                             │ What is known                       │
│                        │   Government web records · Public                                            │                                     │
│ USDT transactions      │                                                                             │ • public archive                    │
│ Event study panel      │   Governance · Historical records                                           │ • entity pages                      │
│                        │   No local alternative                                                     │ • reporting periods                 │
│                        │                                                                             │                                     │
│                        │   Historical archive observed · Preview available                           │ Unknowns                            │
│                        │                                                                             │                                     │
│                        │ OTHER MATCHES                                                               │ ? acquisition route                 │
│                        │ ...                                                                         │ ? pagination completeness           │
│                        │                                                                             │ ? required field shape              │
│                        │                                                                             │                                     │
│                        │                                                                             │ [ Preview source ]                  │
│                        │                                                                             │                                     │
│                        │                                                                             │ Request this evidence               │
│                        │                                                                             │                                     │
│                        │                                                                             │ Evidence and access ▸               │
│                        │                                                                             │                                     │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Source selected · no durable procurement request exists yet                   │ Source evidence                     │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

## 3.2 Request confirmation

`Request this evidence` opens contextual confirmation. No pipeline builder.

```text
REQUEST EVIDENCE

TAIWAN GOVERNANCE ARCHIVE
Government web records

Evidence need
Historical point-in-time governance records for Taiwan firms.

Required evidence
entity
date
role
source reference

Current evidence
✓ source identity confirmed
✓ bounded preview checked
? acquisition method not established

Nothing will be collected yet.
Research Drive will preserve this request
and investigate a procurement route.

[ Start evidence request ]

Cancel
```

Starting the request creates the durable lifecycle object immediately.

---

# 4. Discover · History — priority + compact lifecycle ledger

## 4.1 Frozen History model

History is not a chronological activity feed and not five stacked mini-inboxes.

```text
NEEDS YOU
────────────────────────────────────────
researcher-owned decisions


RESEARCH LIFECYCLE
────────────────────────────────────────
all remaining durable research objects
ordered by material durable lifecycle change
```

`Needs you` is a priority territory, not an ontological peer of lifecycle state.

Projection axes:

```text
LIFECYCLE STATE

active
ready
needs_recovery
scheduled


DECISION OWNERSHIP

researcher
system
none
```

Rules:

```text
decision_owner = researcher
        ↓
NEEDS YOU


everything else
        ↓
RESEARCH LIFECYCLE
```

Each durable object appears once in the centre. No duplication between `Needs you` and the ledger.

## 4.2 Full desktop / 1440 × 1024 — compact ledger + bounded rail

```text
RESEARCH DRIVE — DISCOVER · HISTORY
PRIORITY + COMPACT LIFECYCLE LEDGER
WITH MATERIAL PROCUREMENT METHOD CUE

DESKTOP / 1440 × 1024


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   DISCOVER                                             │ DETAIL ●              ASK           │
│                        │                                                                             │ HISTORICAL USDT TRANSACTIONS        │
│    Home                │ EXPLORE                                                     HISTORY ● 72   │ METHOD REVIEW                       │
│    Library             │                                                                             │                                     │
│  ● Discover            │ RESEARCH LIFECYCLE                                                          │ Browser extraction proposed         │
│    Synthesis           │                                                                             │                                     │
│    Resources           │ All ●    Needs you 4    Active 18    Ready 31    Recovery 7    Scheduled 12│                                     │
│    Profile             │                                                                             ├─────────────────────────────────────┤
│    Settings            │ NEEDS YOU · 4                                                               │                                     │
│                        │                                                                             │ WHY THIS METHOD                     │
│ ACTIVE RESEARCH        │ ▌ HISTORICAL USDT TRANSACTIONS                              METHOD REVIEW  │                                     │
│                        │   BigQuery · Historical transaction evidence                                 │ Direct collection did not establish │
│ Stablecoin Research   │   Browser extraction proposed · Updated now                                  │ the required historical records.    │
│                        │                                                                             │                                     │
│ Event studies          │   TAIWAN GOVERNANCE SOURCE                                  METHOD REVIEW  │ METHOD                              │
│                        │   Government records · Governance · Point-in-time                            │                                     │
│ Market structure       │   Browser extraction proposed · Updated 16:18                                │ Browser extraction                  │
│                        │                                                                             │ Spectator · Playwright              │
│ ────────────────────── │   CRYPTO ENTITY LABELS                                      SCOPE REVIEW    │                                     │
│                        │   Address attribution · Entity evidence                                      │ ROUTE                               │
│ RECENT                 │   12 proposed entity groups · Updated 15:31                                 │                                     │
│                        │                                                                             │ 1  Open historical archive          │
│ USDT transactions      │   REFINITIV NEWS ARCHIVE                                   ACCESS DECISION │ 2  Traverse periods                 │
│ Event study panel      │   Licensed article evidence · Historical news                               │ 3  Traverse stablecoin records      │
│                        │   Entitlement route identified · Updated 14:48                               │ 4  Extract required transfer fields │
│                        │                                                                             │                                     │
│                        │ RESEARCH LIFECYCLE · 68                                                       │ KNOWN                               │
│                        │                                                                             │                                     │
│                        │ STABLECOIN ATTENTION PANEL                                  COLLECTING       │ ✓ direct route checked              │
│                        │ GDELT · Event / news evidence · daily panel                                  │ ✓ browser route observed            │
│                        │ Latest verified range 2022-06-30 · Updated 16:04                             │ ✓ bounded route tested              │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ ETHEREUM TRANSFER ARCHIVE                                  ARCHIVE PENDING  │ UNKNOWNS                            │
│                        │ Ethereum provider · Transaction evidence                                     │                                     │
│                        │ 18.4 GB received · archive verification pending · 15:51                      │ ? traversal completeness            │
│                        │ ─────────────────────────────────────────────────────────────────────────── │ ? session stability                 │
│                        │ SEC COMPANY TICKERS                                         QUERY-READY      │ ? final extraction volume           │
│                        │ SEC EDGAR · Company identity evidence                                       │                                     │
│                        │ Registry confirmed · Library asset available · 15:42                         │ Technical record ▸                  │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ TAIWAN ENTITY MAPPING                                      RETRY PENDING    │                                     │
│                        │ Government identity sources · Entity evidence                               │                                     │
│                        │ Previous observation preserved · retry pending · 15:07                       │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ TWSE REFRESH                                               SCHEDULE RECORDED│                                     │
│                        │ TWSE · Every Monday at 10:00                                                │                                     │
│                        │ Request saved · automatic execution not active · 14:22                       │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ USDT ENTITY PANEL                                  REGISTRATION PENDING      │                                     │
│                        │ Local synthesis input · Entity evidence                                    │                                     │
│                        │ Archive confirmed · registry promotion pending · 13:54                       │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ MARKET STRESS EVENTS                                         QUERY-READY     │                                     │
│                        │ GDELT + registered event sources                                             │                                     │
│                        │ Library asset available · 13:21                                             │                                     │
│                        │                                                                             ├─────────────────────────────────────┤
│                        │ Showing 8 of 68 lifecycle items                              Load more ↓    │ [ Review method ]                   │
│                        │                                                                             │ Ask about method · Return to source │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Researcher decisions first · compact lifecycle ledger                         │ Procurement authority               │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

### Frozen History row grammar

```text
TITLE                                           CURRENT STATE
source · evidence identity · optional scope
one current-state evidence line · freshness
```

Normal row budget: three visible lines.

Examples:

```text
TAIWAN GOVERNANCE SOURCE                         METHOD REVIEW
Government records · Governance · Point-in-time
Browser extraction proposed · Updated 16:18
```

```text
STABLECOIN ATTENTION PANEL                       COLLECTING
GDELT · Event / news evidence · daily panel
Latest verified range 2022-06-30 · Updated 16:04
```

```text
SEC COMPANY TICKERS                              QUERY-READY
SEC EDGAR · Company identity evidence
Registry confirmed · Library asset available · 15:42
```

```text
TWSE REFRESH                                     SCHEDULE RECORDED
TWSE · Every Monday at 10:00
Request saved · automatic execution not active · 14:22
```

Method identity surfaces in the centre only when procurement method is materially part of the current lifecycle state or decision. Do not advertise worker configuration on routine rows.

## 4.3 Vertical scale authority

Default `All` view:

```text
NEEDS YOU
show all researcher-owned decisions
normally 0–8 rows

RESEARCH LIFECYCLE
initial viewport budget 8–12 rows

Showing 8 of 68 lifecycle items                     Load more ↓
```

Use explicit `Load more`, not a bottomless activity feed.

Default ledger ordering:

```text
1. MATERIAL STATE CHANGE

   method proposed
   collection started
   extraction finished
   archive verified
   registration changed
   readiness changed
   failure / retry state changed

2. LATEST DURABLE CHANGE

DO NOT PROMOTE FOR

heartbeat
poll
worker check
unchanged progress refresh
```

Filters remain:

```text
All · Needs you · Active · Ready · Recovery · Scheduled
```

When a state filter is active, the centre may show a single state heading such as `ACTIVE`. The default `All` view does not create five giant state sections.

---

# 5. Initial History state — route investigating

Starting an evidence request creates the History object before method resolution.

```text
DISCOVER · HISTORY
INITIAL DURABLE OBJECT


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   DISCOVER                                             │ DETAIL ●              ASK           │
│                        │                                                                             │ TAIWAN GOVERNANCE SOURCE            │
│    Home                │ EXPLORE                                                     HISTORY ● 6    │ ROUTE INVESTIGATING                 │
│    Library             │                                                                             │                                     │
│  ● Discover            │ RESEARCH LIFECYCLE                                                          │ The evidence request is preserved.  │
│    Synthesis           │                                                                             │                                     │
│    Resources           │ All ●    Needs you 0    Active 1    Ready 2    Recovery 1    Scheduled 2   │ CURRENT WORK                        │
│    Profile             │                                                                             │                                     │
│    Settings            │ RESEARCH LIFECYCLE                                                          │ Determining how the requested       │
│                        │                                                                             │ evidence can be acquired.           │
│ ACTIVE RESEARCH        │ ▌ TAIWAN GOVERNANCE SOURCE                                ROUTE INVESTIGATING│                                     │
│                        │   Government web records · Point-in-time governance evidence                │ EVIDENCE NEED                       │
│ Stablecoin Research   │   Acquisition method not established · Updated 16:12                         │                                     │
│                        │                                                                             │ Historical governance records       │
│ Event studies          │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ STABLECOIN ATTENTION PANEL                                  COLLECTING       │ Preferred                          │
│ Market structure       │   GDELT · Event / news evidence · daily panel                                │ entity · date · role                │
│                        │   Latest verified range 2022-06-30 · Updated 16:04                           │ source reference                    │
│ ────────────────────── │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ ETHEREUM TRANSFER ARCHIVE                                  ARCHIVE PENDING  │ KNOWN                               │
│ RECENT                 │   Ethereum provider · Transaction evidence                                   │                                     │
│                        │   18.4 GB received · archive verification pending · 15:51                    │ ✓ source identity confirmed         │
│ USDT transactions      │ ─────────────────────────────────────────────────────────────────────────── │ ✓ bounded preview retained          │
│ Event study panel      │ SEC COMPANY TICKERS                                         QUERY-READY      │                                     │
│                        │   SEC EDGAR · Company identity evidence                                     │ UNKNOWNS                            │
│                        │   Registry confirmed · Library asset available · 15:42                       │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │ ? acquisition method                │
│                        │ TWSE REFRESH                                               SCHEDULE RECORDED│ ? traversal completeness            │
│                        │   TWSE · Every Monday at 10:00                                              │ ? final output shape                │
│                        │   Request saved · automatic execution not active · 14:22                     │                                     │
│                        │                                                                             │ Technical record ▸                  │
│                        │                                                                             │                                     │
│                        │                                                                             ├─────────────────────────────────────┤
│                        │                                                                             │ [ Investigate route ]               │
│                        │                                                                             │ Return to source                    │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Request exists before route resolution · selection remains centre-owned       │ Procurement investigation           │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

Correct initial row:

```text
▌ TAIWAN GOVERNANCE SOURCE                         ROUTE INVESTIGATING
  Government web records · Governance · Point-in-time
  Acquisition method not established · Updated 16:12
```

Do not begin the row at `METHOD REVIEW`. That state only exists after a durable method proposal exists.

---

# 6. History Ask — operate the exact lifecycle object

```text
DISCOVER · HISTORY
ROUTE INVESTIGATION — ASK ACTIVE


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   DISCOVER                                             │ DETAIL                ASK ●         │
│                        │                                                                             │ HISTORICAL USDT TRANSACTIONS        │
│    Home                │ EXPLORE                                                     HISTORY ● 6    │ ROUTE INVESTIGATING                 │
│    Library             │                                                                             │                                     │
│  ● Discover            │ RESEARCH LIFECYCLE                                                          │ Selected lifecycle context          │
│    Synthesis           │                                                                             │                                     │
│    Resources           │ All ●    Needs you 1    Active 2    Ready 1    Recovery 1    Scheduled 1   │ You                                 │
│    Profile             │                                                                             │                                     │
│    Settings            │ NEEDS YOU · 1                                                               │ Try to find a real acquisition      │
│                        │                                                                             │ route. Use available procurement    │
│ ACTIVE RESEARCH        │   TAIWAN GOVERNANCE SOURCE                                  METHOD REVIEW  │ equipment if direct access fails.   │
│                        │   Government records · Governance · Point-in-time                            │                                     │
│ Stablecoin Research   │   Browser extraction proposed · Updated 16:18                                │ Research Drive                      │
│                        │                                                                             │                                     │
│ Event studies          │ RESEARCH LIFECYCLE · 5                                                       │ Investigating the selected evidence │
│                        │                                                                             │ request.                            │
│ Market structure       │ ▌ HISTORICAL USDT TRANSACTIONS                          ROUTE INVESTIGATING│                                     │
│                        │   BigQuery · Historical transaction evidence                                 │ Agent activity                      │
│ ────────────────────── │   Evaluating acquisition routes · Updated now                               │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │ ✓ evidence need loaded              │
│ RECENT                 │ STABLECOIN ATTENTION PANEL                                  COLLECTING       │ ✓ candidate source loaded           │
│                        │   GDELT · Event / news evidence · daily panel                                │ ✓ direct route checked              │
│ USDT transactions      │   Latest verified range 2022-06-30 · Updated 16:04                           │ ● testing bounded browser route     │
│ Event study panel      │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ ETHEREUM TRANSFER ARCHIVE                                  ARCHIVE PENDING  │                                     │
│                        │   Ethereum provider · Transaction evidence                                   │                                     │
│                        │   18.4 GB received · archive verification pending · 15:51                    │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ SEC COMPANY TICKERS                                         QUERY-READY      │                                     │
│                        │   SEC EDGAR · Company identity evidence                                     │                                     │
│                        │   Registry confirmed · Library asset available · 15:42                       │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ TWSE REFRESH                                               SCHEDULE RECORDED│                                     │
│                        │   TWSE · Every Monday at 10:00                                              │                                     │
│                        │   Request saved · automatic execution not active · 14:22                     │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │                                     │
│                        │                                                                             │ ┌─────────────────────────────────┐ │
│                        │                                                                             │ │ Ask about this request…         │ │
│                        │                                                                             │ │                           Send │ │
│                        │                                                                             │ └─────────────────────────────────┘ │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Ask operates the selected lifecycle item · centre reflects durable work       │ Route investigation                 │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

Ask may inspect source routes, evaluate available procurement equipment, run bounded probes/tests, propose or revise a method, schedule supported refresh behavior, and perform supported typed platform operations.

Ask may not silently approve an irreversible operation or promote an inferred fact into source authority.

A successful mutation produces a compact product receipt:

```text
✓ Evidence request recorded
✓ Procurement method prepared
✓ Schedule recorded
✓ Collection queued
✓ Method revised
```

No durable mutation:

```text
Nothing changed because the required authority or supported operation is not established.
```

---

# 7. Method review — durable procurement method is visible

When method engineering itself is material, the centre shows a compact method cue and Detail expands it.

```text
DISCOVER · HISTORY
METHOD PROPOSED — DETAIL ACTIVE


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   DISCOVER                                             │ DETAIL ●              ASK           │
│                        │                                                                             │ HISTORICAL USDT TRANSACTIONS        │
│    Home                │ EXPLORE                                                     HISTORY ● 6    │ METHOD REVIEW                       │
│    Library             │                                                                             │                                     │
│  ● Discover            │ RESEARCH LIFECYCLE                                                          │ Browser extraction proposed         │
│    Synthesis           │                                                                             │                                     │
│    Resources           │ All ●    Needs you 2    Active 1    Ready 1    Recovery 1    Scheduled 1   │                                     │
│    Profile             │                                                                             ├─────────────────────────────────────┤
│    Settings            │ NEEDS YOU · 2                                                               │                                     │
│                        │                                                                             │ WHY THIS METHOD                     │
│ ACTIVE RESEARCH        │ ▌ HISTORICAL USDT TRANSACTIONS                              METHOD REVIEW  │                                     │
│                        │   BigQuery · Historical transaction evidence                                 │ Direct collection did not establish │
│ Stablecoin Research   │   Browser extraction proposed · Updated now                                  │ the required historical records.    │
│                        │                                                                             │                                     │
│ Event studies          │   TAIWAN GOVERNANCE SOURCE                                  METHOD REVIEW  │ METHOD                              │
│                        │   Government records · Governance · Point-in-time                            │                                     │
│ Market structure       │   Browser extraction proposed · Updated 16:18                                │ Browser extraction                  │
│                        │                                                                             │ Spectator · Playwright              │
│ ────────────────────── │ RESEARCH LIFECYCLE · 4                                                       │                                     │
│                        │                                                                             │ ROUTE                               │
│ RECENT                 │ STABLECOIN ATTENTION PANEL                                  COLLECTING       │                                     │
│                        │   GDELT · Event / news evidence · daily panel                                │ 1  Open historical archive          │
│ USDT transactions      │   Latest verified range 2022-06-30 · Updated 16:04                           │ 2  Traverse periods                 │
│ Event study panel      │ ─────────────────────────────────────────────────────────────────────────── │ 3  Traverse stablecoin records      │
│                        │ ETHEREUM TRANSFER ARCHIVE                                  ARCHIVE PENDING  │ 4  Extract required transfer fields │
│                        │   Ethereum provider · Transaction evidence                                   │                                     │
│                        │   18.4 GB received · archive verification pending · 15:51                    │ KNOWN                               │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ SEC COMPANY TICKERS                                         QUERY-READY      │ ✓ direct route checked              │
│                        │   SEC EDGAR · Company identity evidence                                     │ ✓ browser route observed            │
│                        │   Registry confirmed · Library asset available · 15:42                       │ ✓ bounded route tested              │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ TWSE REFRESH                                               SCHEDULE RECORDED│ UNKNOWNS                            │
│                        │   TWSE · Every Monday at 10:00                                              │                                     │
│                        │   Request saved · automatic execution not active · 14:22                     │ ? traversal completeness            │
│                        │                                                                             │ ? session stability                 │
│                        │                                                                             │ ? final extraction volume           │
│                        │                                                                             │                                     │
│                        │                                                                             │ Technical record ▸                  │
│                        │                                                                             │                                     │
│                        │                                                                             ├─────────────────────────────────────┤
│                        │                                                                             │ [ Review method ]                   │
│                        │                                                                             │ Ask about method · Return to source │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Durable method state changes centre position and Detail judgment               │ Procurement authority               │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

Method can be:

```text
Direct API
HTTP manifest
BigQuery query
Browser extraction
Scraper run
Custom connector
```

Equipment/engine may be named only from durable method truth:

```text
Spectator
Playwright
Selenium
Node
...
```

Do not hard-code a capability that the current durable method record does not establish.

---

# 8. Active extraction state

```text
DISCOVER · HISTORY
BROWSER EXTRACTION ACTIVE


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   DISCOVER                                             │ DETAIL ●              ASK           │
│                        │                                                                             │ TAIWAN GOVERNANCE SOURCE            │
│    Home                │ EXPLORE                                                     HISTORY ● 8    │ EXTRACTING                          │
│    Library             │                                                                             │                                     │
│  ● Discover            │ RESEARCH LIFECYCLE                                                          │ Browser extraction active.          │
│    Synthesis           │                                                                             │                                     │
│    Resources           │ All ●    Needs you 2    Active 3    Ready 1    Recovery 1    Scheduled 1   │ METHOD                              │
│    Profile             │                                                                             │                                     │
│    Settings            │ NEEDS YOU · 2                                                               │ Spectator · Playwright              │
│                        │                                                                             │                                     │
│ ACTIVE RESEARCH        │   HISTORICAL USDT TRANSACTIONS                             APPROVAL REQUIRED│ OBSERVED                            │
│                        │   BigQuery · Historical transfers · 2018–present                            │                                     │
│ Stablecoin Research   │   Preview checked · request prepared · Updated 16:10                         │ 6 reporting periods                 │
│                        │                                                                             │ 312 entity pages                    │
│ Event studies          │   CRYPTO ENTITY LABELS                                      SCOPE REVIEW    │ 8,904 records                       │
│                        │   Address attribution · Entity evidence                                      │                                     │
│ Market structure       │   12 proposed entity groups · Updated 15:31                                 │ FIELDS                              │
│                        │                                                                             │                                     │
│ ────────────────────── │ RESEARCH LIFECYCLE · 6                                                       │ entity                              │
│                        │                                                                             │ date                                │
│ RECENT                 │ ▌ TAIWAN GOVERNANCE SOURCE                                      EXTRACTING  │ role                                │
│                        │   Government web records · Point-in-time governance evidence                │ source reference                    │
│ USDT transactions      │   Browser extraction · Spectator / Playwright                               │                                     │
│ Event study panel      │   6 periods · 312 entity pages · extraction active · 16:42                  │ UNKNOWNS                            │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ STABLECOIN ATTENTION PANEL                                  COLLECTING       │ ? remaining coverage                │
│                        │   GDELT · Event / news evidence · daily panel                                │ ? duplicate pages                   │
│                        │   Latest verified range 2022-06-30 · Updated 16:04                           │ ? role normalization                │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ ETHEREUM TRANSFER ARCHIVE                                  ARCHIVE PENDING  │ Technical record ▸                  │
│                        │   Ethereum provider · Transaction evidence                                   │                                     │
│                        │   18.4 GB received · archive verification pending · 15:51                    │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ SEC COMPANY TICKERS                                         QUERY-READY      │                                     │
│                        │   SEC EDGAR · Company identity evidence                                     │                                     │
│                        │   Registry confirmed · Library asset available · 15:42                       │                                     │
│                        │                                                                             ├─────────────────────────────────────┤
│                        │                                                                             │ [ View evidence ]                   │
│                        │                                                                             │ Ask about extraction               │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Method identity and observed execution remain attached to one lifecycle item  │ Extraction authority                │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

No fake percentage bar unless the execution contract supplies a real denominator.

---

# 9. Schema review state

```text
DISCOVER · HISTORY
EXTRACTION FINISHED / RESEARCHER DECISION RETURNS


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   DISCOVER                                             │ DETAIL ●              ASK           │
│                        │                                                                             │ TAIWAN GOVERNANCE SOURCE            │
│    Home                │ EXPLORE                                                     HISTORY ● 8    │ SCHEMA REVIEW                       │
│    Library             │                                                                             │                                     │
│  ● Discover            │ RESEARCH LIFECYCLE                                                          │ 18,420 records observed.            │
│    Synthesis           │                                                                             │                                     │
│    Resources           │ All ●    Needs you 3    Active 2    Ready 1    Recovery 1    Scheduled 1   │ CONFIRMED                           │
│    Profile             │                                                                             │                                     │
│    Settings            │ NEEDS YOU · 3                                                               │ ✓ entity                            │
│                        │                                                                             │ ✓ point-in-time date                │
│ ACTIVE RESEARCH        │ ▌ TAIWAN GOVERNANCE SOURCE                                  SCHEMA REVIEW  │ ✓ source reference                  │
│                        │   Government web records · Point-in-time governance evidence                │                                     │
│ Stablecoin Research   │   Browser extraction completed · 18,420 records observed                    │ NEEDS REVIEW                        │
│                        │   Role mapping requires review · Updated 17:08                              │                                     │
│ Event studies          │ ─────────────────────────────────────────────────────────────────────────── │ role_text                           │
│                        │ HISTORICAL USDT TRANSACTIONS                             APPROVAL REQUIRED  │ 17 observed values                  │
│ Market structure       │   BigQuery public datasets · Historical transfers                           │                                     │
│                        │   Preview checked · request prepared · Updated 16:10                         │ PROPOSED MAPPING                    │
│ ────────────────────── │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ CRYPTO ENTITY LABELS                                      SCOPE REVIEW      │ Director                            │
│ RECENT                 │   Address attribution catalogue · Entity evidence                            │ Supervisor                          │
│                        │   12 proposed entity groups · Updated 15:31                                 │ Manager                             │
│ USDT transactions      │                                                                             │ Representative                      │
│ Event study panel      │ RESEARCH LIFECYCLE · 5                                                       │ Other                               │
│                        │                                                                             │                                     │
│                        │ STABLECOIN ATTENTION PANEL                                  COLLECTING       │ Technical record ▸                  │
│                        │   GDELT · Event / news evidence · daily panel                                │                                     │
│                        │   Latest verified range 2022-06-30 · Updated 16:04                           │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ ETHEREUM TRANSFER ARCHIVE                                  ARCHIVE PENDING  │                                     │
│                        │   Ethereum provider · Transaction evidence                                   │                                     │
│                        │   18.4 GB received · archive verification pending · 15:51                    │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │ SEC COMPANY TICKERS                                         QUERY-READY      │                                     │
│                        │   SEC EDGAR · Company identity evidence                                     │                                     │
│                        │   Registry confirmed · Library asset available · 15:42                       │                                     │
│                        │                                                                             ├─────────────────────────────────────┤
│                        │                                                                             │ [ Review mapping ]                  │
│                        │                                                                             │ View evidence · Ask about mapping   │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Completed extraction returns to Needs You only for a researcher-owned decision │ Evidence-shape authority           │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

---

# 10. Ready and scheduled rail states

## 10.1 Ready

```text
SEC COMPANY TICKERS
QUERY-READY

Registered evidence is available
for research reuse.


EVIDENCE

Company identity records

REGISTRY

Confirmed

READINESS

Query-ready

AVAILABLE IN

Library
Compatible Synthesis inputs

Technical record ▸

─────────────────────────────
[ Open in Library ]

View Synthesis
```

`completed`, `archived`, `registered`, and `query-ready` are not synonyms.

```text
collection completed
≠ archive verified

archive verified
≠ registry promoted

registry promoted
≠ registry read-back confirmed

registered
≠ query-ready
```

## 10.2 Scheduled — honest non-executing state

```text
TWSE REFRESH
SCHEDULE RECORDED

Every Monday at 10:00


STATUS

The refresh request is saved in
Research Drive.

Automatic execution is not active yet.


SOURCE

TWSE market source

EXECUTION

Not active

Technical record ▸

─────────────────────────────
[ Edit schedule request ]

Ask about schedule
```

Required centre row:

```text
TWSE REFRESH                                     SCHEDULE RECORDED
TWSE · Every Monday at 10:00
Request saved · automatic execution not active · 14:22
```

Do not show `Next run` unless scheduler authority supplies an actual `next_run_at` and execution mode is scheduled/armed.

---

# 11. Frozen Detail / Ask rail composition

The rail earns permanent desktop width only if it compounds the selected Discover object.

```text
CENTRE

object + current durable state

        ↓

DETAIL

current judgment + current decision

        ↓

ASK

intelligence + operation

        ↓

DURABLE BACKEND

preserve consequence

        ↓

CENTRE

consequence becomes visible
```

## 11.1 Viewport contract

```text
RAIL HEIGHT = APP VIEWPORT

┌───────────────────────────────┐
│ FIXED IDENTITY / STATE        │
├───────────────────────────────┤
│                               │
│ BOUNDED SCROLL BODY           │
│                               │
│                               │
├───────────────────────────────┤
│ STICKY DECISION / ACTION      │
└───────────────────────────────┘

THE PAGE NEVER GROWS BECAUSE OF THE RAIL.
```

Implementation layout rule:

```text
header:
fixed

body:
min-height: 0
overflow-y: auto

footer:
sticky / fixed within rail
```

## 11.2 Default Detail budget

```text
IDENTITY / STATE
────────────────────────────
2–3 lines

PRIMARY JUDGMENT
────────────────────────────
max 3–4 lines

ACTIVE DECISION MODULE
────────────────────────────
state-specific
roughly 12–18 visible lines

KNOWN
────────────────────────────
max 3–5

UNKNOWNS
────────────────────────────
max 3

ONE DISCLOSURE
────────────────────────────
Technical record ▸

STICKY ACTION AREA
────────────────────────────
1 primary
max 2 secondary
```

Maximum default modules: five.

The rail is a decision instrument, not a report. Do not repeat semantic information under `Current decision`, `Execution`, `Evidence`, and `What happens next` when state, judgment, and the primary action already communicate the same truth.

Expanded `Technical record` remains inside the bounded scroll body; the sticky action footer remains visible.

## 11.3 Explore active object

```text
kind = external_candidate
```

Detail owns fit, local relationship, source facts, unknowns, and the current valid action.

Ask receives the same exact candidate identity, source/provider identity, candidate key, evidence scope, comparator state, and supported operations.

## 11.4 History active object

```text
kind = discover_lifecycle
```

Selecting a History row must make that lifecycle object the first-class rail context.

Required context shape, naming adaptable to backend implementation:

```text
object

kind = discover_lifecycle
id = intent_...
title = Taiwan Governance Source


lifecycle

state = active
reason = route_investigating
decision_owner = system


evidence_need

entity
date
role
source_reference


source

source_id
connector_id
candidate_key


procurement_method

state = investigating
method_id = null
equipment = []


available_operations

investigate_route
probe_source
test_browser_route
propose_method
schedule_refresh
return_to_source
```

Method review example:

```text
lifecycle

state = needs_you
reason = method_review
decision_owner = researcher


procurement_method

state = review_required
kind = browser_extract
equipment = spectator
engine = playwright
method_id = method_...


available_operations

explain_method
review_method
revise_method
return_to_source
```

The frontend must not infer available operations from free-form status regexes once backend lifecycle projection exists.

## 11.5 Context separation

```text
DISCOVER ACTIVE OBJECT IS ALWAYS EXACTLY ONE OF:

EXPLORE
external_candidate

HISTORY
discover_lifecycle

PREVIEW
preview_target
scoped to selected candidate / lifecycle item

NEVER
stale previous Explore source
while History row is selected
```

Explore selection and History selection are separate preserved states.

```text
Explore selection state
≠
History selection state
```

Switching to History clears active Explore rail context and binds the selected History object. Switching back to Explore restores the preserved Explore selection separately.

---

# 12. History lifecycle projector authority

Durable machinery may remain decomposed internally:

```text
intent
proposal
selected route
job
archive / manifest
promotion
registry read-back
subscription
```

History projects those records into one researcher-facing lifecycle object.

```text
CURRENT DURABLE STORES

intents
subscriptions
Discover-linked jobs
registry / archive evidence

                ↓

     HISTORY LIFECYCLE PROJECTOR

                ↓

{
  id
  lifecycle_kind
  lifecycle_state
  lifecycle_reason
  status_label
  reason
  title
  summary

  decision_owner
  decision_reason

  intent_id
  subscription_id
  job_id
  candidate_key
  registered_dataset_id

  procurement_method
  evidence_state
  next_action

  created_at
  updated_at
  material_changed_at
}

                ↓

             HISTORY UI
```

Backend-owned lifecycle state must not be derived by frontend regex once normalized projection exists.

Required semantic states:

```text
active
ready
needs_recovery
scheduled
```

`Needs you` is projected from researcher decision ownership.

Typed reasons may include:

```text
approval_required
review_required
route_investigating
method_review
collection_queued
collection_running
browser_extracting
schema_review
archive_pending
registration_pending
query_readiness_unconfirmed
collection_failed
archive_failed
retry_pending
schedule_recorded
schedule_paused
```

A single evidence request progresses as one object:

```text
HISTORICAL USDT TRANSACTIONS

ROUTE INVESTIGATING
        ↓
METHOD REVIEW
        ↓
COLLECTION QUEUED
        ↓
COLLECTING / EXTRACTING
        ↓
SCHEMA REVIEW when required
        ↓
ARCHIVE PENDING
        ↓
REGISTRATION PENDING
        ↓
READINESS UNCONFIRMED
        ↓
QUERY-READY
```

Do not render linked intent and collection job as separate primary History rows for the same evidence request.

---

# 13. Procurement method authority

History must represent the difficult middle:

```text
How do we actually acquire this evidence?
```

The method is a durable state attached to the evidence request, not a separate page and not private Ask prose.

Conceptual method envelope:

```text
PROCUREMENT METHOD

method_state
────────────────────────
investigating
proposed
review_required
approved
queued
executing
revision_required
completed

method_kind
────────────────────────
api_query
http_manifest
browser_extract
scraper_run
custom_connector

 equipment
────────────────────────
direct_http
bigquery
spectator
...

engine
────────────────────────
playwright
selenium
node
...

authority
────────────────────────
proposed
observed
approved
executed

route_summary
────────────────────────
bounded human-readable stages

observed_constraints
────────────────────────
direct route insufficient
pagination observed
session required
...

method_id / proposal_id
intent_id
connector_id
job_id
```

Exact field names may adapt to backend conventions. The semantic separation is binding.

Centre method cue:

```text
Browser extraction proposed
```

Detail method expansion:

```text
Browser extraction
Spectator · Playwright
why direct route failed
bounded route stages
knowns
unknowns
review / revise action
```

Method is hidden from ordinary rows when it is no longer material to the current decision.

---

# 14. Preview relationship

Preview remains a centre-scoped evidence overlay. It does not become a Discover route or replace the selected object.

```text
Navigation | active preview evidence | active Detail / Ask interpretation
```

The selected candidate or lifecycle object remains the parent context. Preview may contribute bounded observed evidence to candidate facts or method investigation, with observation time and authority.

No collection starts because Preview opened.

---

# 15. Truth and authority rules

Every visible claim requires authority and freshness.

```text
Coverage
→ provider metadata or observed response
→ fallback: Not reported

Preview evidence
→ bounded observed response
→ fallback: Preview unavailable

Local relationship
→ completed comparator
→ fallback: Comparison unknown

Readiness
→ registry read-back
→ fallback: Registered — readiness not confirmed

Access
→ entitlement/provider state
→ fallback: Access not verified

Lifecycle
→ durable projected state
→ fallback: Status unavailable

Archive
→ archive/manifest verification
→ fallback: Archive verification pending

Registration
→ promotion/read-back
→ fallback: Registration pending

Ranking
→ named ranking signals
→ fallback: Why ranked unavailable

AI evidence
→ source/time/verification envelope
→ fallback: Assistant interpretation — verify source
```

No fixture, stale cache, UI estimate, free-form status regex, or model prose may render as live authoritative fact.

Composer:

```text
interprets query
explains typed match
reasons over typed rail context
operates supported equipment

DOES NOT
create candidate facts
invent legal clearance
invent query readiness
invent equivalence
approve irreversible operations silently
```

---

# 16. Exact cross-page handoffs

```text
Discover Exact
→ exact Library asset

Discover registered result
→ exact Library asset

Discover registered result
→ compatible Synthesis blueprint

Library evidence gap
→ Discover prefilled gap query

Synthesis input gap
→ Discover requirement + existing inputs

Resources capability
→ Discover provider/access constraint

Profile explanation
→ Discover named ranking signals
```

Every handoff opens an exact object or a prefilled evidence requirement, not a generic landing page.

---

# 17. Responsive authority

Desktop 1440:

```text
Navigation | Centre | Detail / Ask
all visible
full-height shell
bounded rail
```

Laptop 1280:

```text
narrow navigation and rail
three-line History rows remain authoritative
rail content budget does not expand
```

Tablet 900:

```text
navigation collapses
centre primary
Detail / Ask opens as a selected-object slide-over
centre state is preserved
```

Mobile 390:

```text
single-column Discover
selection opens a Detail sheet
Ask remains scoped to exact selected object
History rows may wrap but must preserve title/state/source/current-state/freshness order
```

Mobile does not drive desktop composition. It must preserve semantics without forcing the desktop desk into mobile-sized modules.

---

# 18. Frozen Discover acceptance

The following are hard acceptance rules:

```text
EXPLORE

Explore | History only
natural-language / short-query evidence input
visible interpretation readout
ranked result list stays visible after selection
selected mark = ▌
Detail owns selected-source meaning and decision
Ask operates same selected candidate
Focused Evaluation centre takeover is not authority


HISTORY

History begins when evidence need becomes durable
not when procurement method is already solved

Needs You = researcher-owned decision territory
Research Lifecycle = all remaining durable objects

three-line compact rows
right edge = current state only
material procurement method cue may appear in centre
no event-kind taxonomy
no worker-dashboard chronology as primary view
explicit Load more for scale

one evidence request = one primary lifecycle object
linked intent/job/archive/registry states are projected into it

selected History row = discover_lifecycle active rail object


DETAIL

bounded to app viewport
fixed identity/state
bounded internal scroll body
sticky action footer
max five default modules
one judgment
max 3–5 known facts
max 3 unknowns
one disclosure
one primary action
max two secondary actions


ASK

typed exact selected-object context
selected source / lifecycle identity remains explicit
active tool activity may be compact
completed activity collapses by default
successful mutations produce durable receipts
no stale Explore context while History object is selected


PROCUREMENT METHOD

method may be investigated, proposed, reviewed, approved, executed, revised
method belongs to the lifecycle object
method is not a page
method is not private Ask prose
centre shows material method cue
Detail expands current method decision


TRUTH

completed ≠ ready
archived ≠ registered
registered ≠ query-ready
schedule recorded ≠ automatic execution active
unknown fact = conservative fallback or omitted claim
```

---

# 19. Do not reintroduce

```text
Search | Activity
Activity workspace
Focused Evaluation centre takeover
Semantic Search tab
AI Search tab
Advanced Search tab
Evidence Builder
Research Query mode
Browse mode
Source Finder mode
worker dashboard History
event-kind filters: Search / Probe / Procure
five giant lifecycle sections in All view
five-line-plus default History rows
infinite activity feed
full-height Detail document that stretches the page
per-row Ask / collect controls
MCP debugger copy
hard-coded Spectator / Playwright / Selenium claims without durable method authority
```

---

# 20. Freeze statement

The Discover composition frozen on 2026-07-15 is:

```text
DISCOVER

EXPLORE | HISTORY


EXPLORE

research need
→ visible interpretation
→ ranked evidence landscape
→ selected row remains in place
→ bounded Detail judgment
→ Ask operates exact selected candidate


HISTORY

researcher-owned decisions first
+
compact durable lifecycle ledger

one evidence request
→ route investigating
→ method review when needed
→ execution
→ evidence-shape review when needed
→ archive
→ registration
→ readiness

material procurement method is visible as state,
not hidden inside Ask and not promoted into a page


DETAIL / ASK

Centre = object + state
Detail = meaning + decision
Ask = intelligence + operation
Backend = durable consequence
Centre = consequence becomes visible
```

This is the Discover visual and interaction baseline. Future implementation must converge to it. Existing code is evidence of current implementation state only; it does not override this freeze.