# Research Drive — Library full-scale freeze

**Status:** FROZEN VISUAL / INTERACTION AUTHORITY  
**Date:** 2026-07-15  
**Authority:** Normative Library appendix to be incorporated by [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md)  
**Scope:** `drive/src/v2/*`, Library API projections, typed rail context, Library search/intake/collection contracts, rendered-pixel review  

This appendix preserves the complete Library composition approved during the 2026-07-15 convergence pass. It is intentionally visual-first. The CLI wireframes below are implementation authority, not illustrative sketches.

No current component, screenshot, backend directory shape, generic Drive convention, model prose, fixture, or historical Library implementation overrides this appendix. Library is a research evidence estate, not a generic cloud file manager and not a data catalogue with an AI sidebar.

---

# 1. Frozen Library thesis

```text
GOOGLE DRIVE

LOCATION
   ↓
FILES
   ↓
SELECT
   ↓
OPEN / SHARE / MOVE


RESEARCH DRIVE LIBRARY

RESEARCH LOCATION
   ↓
EVIDENCE ESTATE
   ↓
SELECT LIBRARY OBJECT
   ↓
UNDERSTAND

what evidence exists
what it is about
where it came from
what source relationship is established
whether it is query-ready
what it can support
what is missing

   ↓

ACT

preview
reuse
compare source relationship
organise into research collections
find the exact evidence gap
```

Frozen application grammar:

```text
Navigation | Centre | Detail / Ask
```

For Library:

```text
CENTRE

where am I?
what evidence exists here?
what Library object is selected?


DETAIL

what does this collection or asset mean?
what source / verification authority exists?
what is usable?
what is missing?
what decision or action exists?


ASK

what can Composer / Cite-Agent investigate,
compare, organise, or operate on this exact
selected Library object?
```

The compounding loop is binding:

```text
CENTRE
object + state

        ↓

DETAIL
meaning + current decision

        ↓

ASK
Composer / Cite-Agent
investigate / reason / operate exact object

        ↓

DURABLE CONSEQUENCE

collection suggestions recorded
collection context refined
verification relationship updated
gap recorded
Discover handoff created

        ↓

CENTRE / DETAIL
same object visibly changes
```

---

# 2. Library object model

Library has two first-class centre objects and one scoped search object:

```text
library_collection

research organisational context


library_asset

durable evidence identity


library_search_match

search explanation scoped to a library_asset
```

Collections are not storage directories.

```text
COLLECTION
=
RESEARCH ORGANISATIONAL CONTEXT


NOT
=
PHYSICAL ARCHIVE DIRECTORY
```

One durable asset may belong to multiple collections:

```text
USDT TRANSACTION DATASET

one asset identity
one registry identity
one archive authority
one readiness state

        │
        ├── Raw evidence
        ├── Historical transaction evidence
        └── Event-study inputs
```

Adding an asset to a collection does not duplicate the asset, archive, registry record, or source authority.

The physical storage/archive path belongs in provenance or Technical record. Backend directory structure must not dictate faculty-facing collection hierarchy.

---

# 3. Canonical Library state language

Readiness and verification are independent axes.

## 3.1 Readiness

Canonical readiness labels are exactly:

```text
QUERY-READY
REGISTERED
METADATA ONLY
UNAVAILABLE / NOT VERIFIED
```

Do not replace `QUERY-READY` with generic `Ready`.

```text
exists
≠
registered

registered
≠
query-ready
```

## 3.2 Source

`SOURCE` answers:

```text
WHERE DID THIS OWNED ASSET COME FROM?
```

Source display grammar:

```text
DIRECT EXTERNAL SOURCE

BIGQUERY
GDELT
MOPS
SEC EDGAR
DATACITE


SELF-PROVIDED

SELF-PROVIDED


PLURAL / DERIVED LINEAGE

2 SOURCES
3 SOURCES
8 SOURCES


SOURCE AUTHORITY ABSENT

NOT RECORDED
```

A self-provided source is not a failure state. It means the researcher supplied the evidence and the original upload/intake record is preserved.

## 3.3 Verification

`VERIFICATION` answers:

```text
WHAT RELATIONSHIP HAS RESEARCH DRIVE ESTABLISHED
BETWEEN THE OWNED ASSET AND AUTHORITATIVE /
SOURCABLE EVIDENCE?
```

Canonical semantic states:

```text
VERIFIED
MATCHED
PARTIAL
UNVERIFIED
NOT CHECKED
```

Meanings:

```text
VERIFIED
source identity and the owned asset's relationship
with that source are established


MATCHED
independent / self-provided asset has strong
correspondence with a known sourcable dataset
or record


PARTIAL
a source relationship exists but equivalence,
coverage, fields, or transformations differ


UNVERIFIED
no corresponding authoritative external source
relationship has been established


NOT CHECKED
verification has not completed or has not been attempted
```

Hard honesty rules:

```text
VERIFIED
≠
THE DATA IS TRUE


MATCHED
≠
THE DATASETS ARE IDENTICAL


QUERY-READY
≠
EXTERNALLY VERIFIED
```

The rail must explain exactly what matched, differed, or remains unestablished.

---

# 4. Normal Library row grammar

The centre remains evidence-first.

Frozen normal row anatomy:

```text
TITLE                     SOURCE       VERIFY       STATE
plain-language one-line description
```

Examples:

```text
PRIVATE USDT TRANSACTIONS SELF-PROVIDED MATCHED      QUERY-READY
Historical USDT transfer records supplied by the researcher.
```

```text
USDT TRANSACTION DATASET  BIGQUERY      VERIFIED     QUERY-READY
Public USDT transfer evidence for event and entity analysis.
```

```text
TAIWAN GOVERNANCE PANEL   MOPS          PARTIAL      REGISTERED
Point-in-time corporate role records for Taiwan firms.
```

```text
PRIVATE ENTITY LABELS     SELF-PROVIDED UNVERIFIED   QUERY-READY
Researcher-maintained labels for known stablecoin entities.
```

```text
STABLECOIN EVENT STUDY PANEL 2 SOURCES  VERIFIED     QUERY-READY
Event-window panel for measuring on-chain response around stress events.
```

Rules:

```text
NORMAL ROW

line 1 = identity + authority scan
line 2 = plain-language meaning


NO

metadata soup pretending to be description
three-line mini cards
per-row action buttons
source citation strings expanded in the ledger
full provenance chains in rows
```

The one-line description must explain what the evidence is about without requiring the researcher to decode the asset name.

---

# 5. Full desktop authority — collection selected

```text
RESEARCH DRIVE — LIBRARY
FULL-SCALE FROZEN CLI WIREFRAME

COLLECTION SELECTED
DESKTOP / 1440 × 1024


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   LIBRARY                             + ADD EVIDENCE ▾│ DETAIL ●              ASK           │
│                        │                                                                             │ RAW EVIDENCE                        │
│    Home                │ STABLECOIN RESEARCH  /  RAW EVIDENCE                                        │ COLLECTION                          │
│  ● Library             │                                                                             │                                     │
│    Discover            │ RAW EVIDENCE                                            128 ASSETS          │ Primary evidence retained for       │
│    Synthesis           │                                                                             │ stablecoin market and event-study   │
│    Resources           │ [ Search assets, entities, fields, sources, provenance…                 ⌕ ] │ research.                           │
│    Profile             │                                                                             │                                     │
│    Settings            │ All 128 ●    Query-ready 91    Registered 24    Metadata only 13            │ EVIDENCE                            │
│                        │                                                                             │                                     │
│ ACTIVE RESEARCH        │ ┌────────────────────┬─────────────────────────────────────────────────────┐ │ 128 assets                          │
│                        │ │ COLLECTIONS        │ EVIDENCE                SOURCE      VERIFY      STATE│ │ 91 query-ready                     │
│ Stablecoin Research   │ │                    ├─────────────────────────────────────────────────────┤ │                                     │
│                        │ │ ▾ Stablecoin       │   PRIVATE USDT          SELF-       MATCHED      QUERY│ │ CONTEXT                             │
│ Event studies          │ │   Research         │   TRANSACTIONS          PROVIDED                  -READY│                                     │
│                        │ │                    │   Historical USDT transfer records supplied by user. │ │ Stablecoins                         │
│ Market structure       │ │                    │                                                     │ │ Transactions                        │
│                        │ │ ▌ Raw evidence 128 │   USDT TRANSACTION       BIGQUERY    VERIFIED     QUERY│ │ Market events                       │
│ ────────────────────── │ │                    │   DATASET                                        -READY│ │                                     │
│                        │ │   Research panels  │   Public USDT transfer evidence for event analysis.  │ │ RELATED EVIDENCE                    │
│ RECENT                 │ │                41  │                                                     │ │                                     │
│                        │ │                    │   STABLECOIN            GDELT       VERIFIED     QUERY│ │ 3 owned assets may belong here.     │
│ USDT transactions      │ │   Outputs      12  │   ATTENTION PANEL                                -READY│ │                                     │
│ Event study panel      │ │                    │   Daily news and event attention around stablecoins. │ │ Review suggestions                  │
│                        │ │                    │                                                     │ │                                     │
│                        │ │ + New collection   │   TAIWAN GOVERNANCE      MOPS        PARTIAL      REGIS│ │ KNOWN GAPS                          │
│                        │ │                    │   PANEL                                           TERED│ │                                     │
│                        │ │                    │   Point-in-time corporate role records for Taiwan.   │ │ 4 recorded evidence gaps            │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │   PRIVATE ENTITY         SELF-       UNVERIFIED   QUERY│ │ Review gaps                         │
│                        │ │                    │   LABELS                 PROVIDED                  -READY│                                     │
│                        │ │                    │   Researcher-maintained stablecoin entity labels.    │ │                                     │
│                        │ │                    │                                                     │ │ Technical record ▸                  │
│                        │ │                    │   MARKET STRESS          GDELT       VERIFIED     QUERY│ │                                     │
│                        │ │                    │   EVENTS                                         -READY│ │                                     │
│                        │ │                    │   Dated market-stress events used in event windows.  │ │                                     │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │   HISTORICAL             DATACITE    VERIFIED     META│ │                                     │
│                        │ │                    │   STABLECOIN CATALOG                              DATA│ │                                     │
│                        │ │                    │   Historical references to documented datasets.     │ │                                     │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │                                      ↕              │ │                                     │
│                        │ └────────────────────┴─────────────────────────────────────────────────────┘ │                                     │
│                        │                                                                             ├─────────────────────────────────────┤
│                        │ 128 evidence assets                                                          │ [ Review suggestions ]              │
│                        │                                                                             │ Edit context · Find external evidence│
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Current collection owns location · evidence estate remains immediately visible│ Collection intelligence              │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

Frozen collection-selection rule:

```text
SELECT COLLECTION

        ↓

current location changes
breadcrumb changes
contents change

        ↓

DETAIL
collection meaning
accepted context
estate summary
related owned evidence suggestions
known gaps
```

Collection selection is navigation plus interpretation.

The centre does not add permanent dashboard modules for suggestions or gaps. Collection intelligence belongs in the selected collection's Detail rail.

---

# 6. Full desktop authority — asset selected

```text
RESEARCH DRIVE — LIBRARY
FULL-SCALE FROZEN CLI WIREFRAME

ASSET SELECTED
DESKTOP / 1440 × 1024


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   LIBRARY                             + ADD EVIDENCE ▾│ DETAIL ●              ASK           │
│                        │                                                                             │ PRIVATE USDT TRANSACTIONS           │
│    Home                │ STABLECOIN RESEARCH  /  RAW EVIDENCE                                        │ QUERY-READY                         │
│  ● Library             │                                                                             │                                     │
│    Discover            │ RAW EVIDENCE                                            128 ASSETS          │ Historical USDT transfer records    │
│    Synthesis           │                                                                             │ supplied by the researcher.         │
│    Resources           │ [ Search assets, entities, fields, sources, provenance…                 ⌕ ] │                                     │
│    Profile             │                                                                             │ EVIDENCE                            │
│    Settings            │ All 128 ●    Query-ready 91    Registered 24    Metadata only 13            │                                     │
│                        │                                                                             │ Transactions · 47 entities          │
│ ACTIVE RESEARCH        │ ┌────────────────────┬─────────────────────────────────────────────────────┐ │ 8 registered fields                 │
│                        │ │ COLLECTIONS        │ EVIDENCE                SOURCE      VERIFY      STATE│ │ Coverage · 2020–2024                │
│ Stablecoin Research   │ │                    ├─────────────────────────────────────────────────────┤ │                                     │
│                        │ │ ▾ Stablecoin       │ ▌ PRIVATE USDT          SELF-       MATCHED      QUERY│ │ SOURCE                              │
│ Event studies          │ │   Research         │   TRANSACTIONS          PROVIDED                  -READY│                                     │
│                        │ │                    │   Historical USDT transfer records supplied by user. │ │ Self-provided                       │
│ Market structure       │ │                    │                                                     │ │ Original upload preserved           │
│                        │ │ ● Raw evidence 128 │   USDT TRANSACTION       BIGQUERY    VERIFIED     QUERY│ │                                     │
│ ────────────────────── │ │                    │   DATASET                                        -READY│ │ VERIFICATION                        │
│                        │ │   Research panels  │   Public USDT transfer evidence for event analysis.  │ │                                     │
│ RECENT                 │ │                41  │                                                     │ │ MATCHED                             │
│                        │ │                    │   STABLECOIN            GDELT       VERIFIED     QUERY│ │                                     │
│ USDT transactions      │ │   Outputs      12  │   ATTENTION PANEL                                -READY│ │ Strong correspondence with          │
│ Event study panel      │ │                    │   Daily news and event attention around stablecoins. │ │ BigQuery public USDT records.       │
│                        │ │                    │                                                     │ │                                     │
│                        │ │ + New collection   │   TAIWAN GOVERNANCE      MOPS        PARTIAL      REGIS│ │ ✓ transaction identifiers           │
│                        │ │                    │   PANEL                                           TERED│ │ ✓ timestamps                        │
│                        │ │                    │   Point-in-time corporate role records for Taiwan.   │ │ ✓ transfer values                   │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │   PRIVATE ENTITY         SELF-       UNVERIFIED   QUERY│ │ ? complete row equivalence          │
│                        │ │                    │   LABELS                 PROVIDED                  -READY│ ? private transformations           │
│                        │ │                    │   Researcher-maintained stablecoin entity labels.    │ │                                     │
│                        │ │                    │                                                     │ │ COLLECTIONS                         │
│                        │ │                    │   MARKET STRESS          GDELT       VERIFIED     QUERY│ │                                     │
│                        │ │                    │   EVENTS                                         -READY│ │ Raw evidence                        │
│                        │ │                    │   Dated market-stress events used in event windows.  │ │ Historical transaction evidence    │
│                        │ │                    │                                                     │ │ Event-study inputs                  │
│                        │ │                    │   HISTORICAL             DATACITE    VERIFIED     META│ │                                     │
│                        │ │                    │   STABLECOIN CATALOG                              DATA│ │ Manage collections                  │
│                        │ │                    │   Historical references to documented datasets.     │ │                                     │
│                        │ │                    │                                                     │ │ Verification record ▸               │
│                        │ │                    │                                      ↕              │ │ Source record ▸                     │
│                        │ └────────────────────┴─────────────────────────────────────────────────────┘ │                                     │
│                        │                                                                             ├─────────────────────────────────────┤
│                        │ 128 evidence assets                                                          │ [ Preview ]                         │
│                        │                                                                             │ Compare source match · Use in Synthesis│
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Asset selection stays in current collection · Detail changes object           │ Evidence authority                   │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

Frozen asset-selection rule:

```text
SELECT ASSET

        ↓

current collection remains selected
row remains visible with ▌ marker

        ↓

DETAIL
asset research meaning
readiness
evidence shape / coverage
source
verification relationship
collection memberships
limitation
next action
```

The centre does not become a full-page asset evaluation workspace.

---

# 7. Full desktop authority — collection Ask / Composer active

```text
RESEARCH DRIVE — LIBRARY
FULL-SCALE FROZEN CLI WIREFRAME

COLLECTION SELECTED · ASK ACTIVE
DESKTOP / 1440 × 1024


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   LIBRARY                             + ADD EVIDENCE ▾│ DETAIL                ASK ●         │
│                        │                                                                             │ RAW EVIDENCE                        │
│    Home                │ STABLECOIN RESEARCH  /  RAW EVIDENCE                                        │ COLLECTION                          │
│  ● Library             │                                                                             │                                     │
│    Discover            │ RAW EVIDENCE                                            128 ASSETS          │ Composer · selected collection      │
│    Synthesis           │                                                                             │                                     │
│    Resources           │ [ Search assets, entities, fields, sources, provenance…                 ⌕ ] │ Context                             │
│    Profile             │                                                                             │                                     │
│    Settings            │ All 128 ●    Query-ready 91    Registered 24    Metadata only 13            │ Stablecoins                         │
│                        │                                                                             │ Transactions                        │
│ ACTIVE RESEARCH        │ ┌────────────────────┬─────────────────────────────────────────────────────┐ │ Market events                       │
│                        │ │ COLLECTIONS        │ EVIDENCE                SOURCE      VERIFY      STATE│ │ 128 owned assets                    │
│ Stablecoin Research   │ │                    ├─────────────────────────────────────────────────────┤ │                                     │
│                        │ │ ▾ Stablecoin       │   PRIVATE USDT          SELF-       MATCHED      QUERY│ │ You                                 │
│ Event studies          │ │   Research         │   TRANSACTIONS          PROVIDED                  -READY│                                     │
│                        │ │                    │   Historical USDT transfer records supplied by user. │ │ Check whether other owned evidence  │
│ Market structure       │ │                    │                                                     │ │ belongs in this collection.         │
│                        │ │ ▌ Raw evidence 128 │   USDT TRANSACTION       BIGQUERY    VERIFIED     QUERY│ │                                     │
│ ────────────────────── │ │                    │   DATASET                                        -READY│ │ Composer                            │
│                        │ │   Research panels  │   Public USDT transfer evidence for event analysis.  │ │                                     │
│ RECENT                 │ │                41  │                                                     │ │ Comparing the Library estate with  │
│                        │ │                    │   STABLECOIN            GDELT       VERIFIED     QUERY│ │ accepted collection context.       │
│ USDT transactions      │ │   Outputs      12  │   ATTENTION PANEL                                -READY│ │                                     │
│ Event study panel      │ │                    │   Daily news and event attention around stablecoins. │ │ Activity                            │
│                        │ │                    │                                                     │ │                                     │
│                        │ │ + New collection   │   TAIWAN GOVERNANCE      MOPS        PARTIAL      REGIS│ │ ✓ collection context loaded         │
│                        │ │                    │   PANEL                                           TERED│ │ ✓ evidence estate compared          │
│                        │ │                    │   Point-in-time corporate role records for Taiwan.   │ │ ✓ source relationships checked      │
│                        │ │                    │                                                     │ │ ✓ evidence shapes compared          │
│                        │ │                    │   PRIVATE ENTITY         SELF-       UNVERIFIED   QUERY│ │                                     │
│                        │ │                    │   LABELS                 PROVIDED                  -READY│ 3 related evidence suggestions      │
│                        │ │                    │   Researcher-maintained stablecoin entity labels.    │ │ prepared.                           │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │                                      ↕              │ │ ✓ Suggestions recorded             │
│                        │ └────────────────────┴─────────────────────────────────────────────────────┘ │                                     │
│                        │                                                                             │ Review suggestions                  │
│                        │ 128 evidence assets                                                          │                                     │
│                        │                                                                             │ ┌─────────────────────────────────┐ │
│                        │                                                                             │ │ Ask Composer about this         │ │
│                        │                                                                             │ │ collection…                  Send│ │
│                        │                                                                             │ └─────────────────────────────────┘ │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Composer operates the selected collection · durable Library state changes     │ Collection organisation             │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

The tab remains `ASK` for stable application grammar.

Visible active intelligence identity may say:

```text
Composer · selected collection
Composer · selected evidence
```

Where Cite-Agent is the actual active research reasoning surface, the implementation may truthfully identify it as:

```text
Cite-Agent · selected evidence
```

Do not present the rail as a generic assistant sidecar.

---

# 8. Collection organisation model

Manual authority is binding.

```text
CREATE / EDIT COLLECTION

        ↓

RESEARCHER NAMES COLLECTION
OPTIONAL DESCRIPTION

        ↓

RESEARCHER MANUALLY ADDS EVIDENCE

        ↓

COLLECTION CONTEXT ACCUMULATES

collection description
accepted evidence
evidence shape / grain
entities / markets
coverage
source relationships
active research context

        ↓

LIBRARY MAY SUGGEST

3 owned assets may belong here

        ↓

RESEARCHER REVIEWS

Add selected
Not related
Dismiss

        ↓

COLLECTION CONTEXT MAY IMPROVE
```

Hard prohibition:

```text
NEVER

Research Drive reorganised 47 datasets for you


NEVER

AI created 12 folders automatically


NEVER

asset silently moved because semantic similarity = 0.89
```

Composer / Cite-Agent may propose organisation changes. It may not silently change collection membership.

---

# 9. Full collection-suggestion review state

Suggestion review remains inside Library centre. It is a temporary review state, not a new page.

```text
RESEARCH DRIVE — LIBRARY
COLLECTION ORGANISATION REVIEW

RAW EVIDENCE

3 OWNED ASSETS MAY BE RELATED TO THIS COLLECTION


┌────────────────────┬─────────────────────────────────────────────────────────────────────────────────┐
│ COLLECTIONS        │ RELATED EVIDENCE                                                     3 SUGGESTIONS│
│                    │                                                                                 │
│ ▾ Stablecoin       │ Suggested using Raw evidence collection context.                                │
│   Research         │ Nothing changes until you approve it.                                           │
│                    │                                                                                 │
│ ● Raw evidence     │ □ ETHEREUM TRANSFER ARCHIVE                 BIGQUERY     VERIFIED     QUERY-READY│
│   · 128            │   Historical Ethereum transfers containing stablecoin activity.                 │
│                    │                                                                                 │
│   Research panels  │   WHY RELATED                                                                   │
│   · 41             │   Transactions · Stablecoins · Historical evidence                              │
│                    │                                                                                 │
│   Outputs          │ ─────────────────────────────────────────────────────────────────────────────── │
│   · 12             │                                                                                 │
│                    │ □ STABLECOIN ISSUER RECORDS                 DATACITE     VERIFIED     REGISTERED │
│ + New collection   │   Published issuer-level stablecoin evidence and source references.             │
│                    │                                                                                 │
│                    │   WHY RELATED                                                                   │
│                    │   Stablecoins · Primary evidence · Source records                               │
│                    │                                                                                 │
│                    │ ─────────────────────────────────────────────────────────────────────────────── │
│                    │                                                                                 │
│                    │ □ ERC-20 TRANSFER SAMPLE                    BIGQUERY     VERIFIED     QUERY-READY│
│                    │   Bounded token-transfer evidence retained from route testing.                  │
│                    │                                                                                 │
│                    │   WHY RELATED                                                                   │
│                    │   Transactions · Token evidence                                                  │
│                    │                                                                                 │
│                    │                                        Select all                               │
│                    │                                                                                 │
│                    │                        [ Add selected to Raw evidence ]                           │
│                    │                                                                                 │
│                    │                        Not related                                               │
└────────────────────┴─────────────────────────────────────────────────────────────────────────────────┘


DETAIL

RAW EVIDENCE
COLLECTION

Organisation suggestions

3 owned evidence assets appear related
to this collection.

SIGNALS

Stablecoins
Transactions
Primary evidence

Suggestions use recorded Library
metadata and accepted collection context.

No evidence will be added automatically.

─────────────────────────────

[ Add selected ]

Cancel review
```

Suggestion authority must be explainable through named context signals. Free-form model intuition does not create collection membership authority.

After approval:

```text
✓ 2 assets added to Raw evidence
```

The same assets remain one durable identity and may still belong to other collections.

---

# 10. Collection creation and context establishment

```text
+ NEW COLLECTION

Name

[ Historical transaction evidence ]


Optional description

[ Raw transaction and transfer evidence
  used for historical stablecoin research. ]


[ Create collection ]
```

Immediately after creation:

```text
HISTORICAL TRANSACTION EVIDENCE
0 ASSETS

No organisation suggestions yet.
```

Do not infer rich collection context from the title alone.

After manual additions:

```text
HISTORICAL TRANSACTION EVIDENCE
3 ASSETS

USDT transaction dataset
Ethereum transfer archive
Token transfer sample
```

Then collection Detail may show:

```text
HISTORICAL TRANSACTION EVIDENCE
COLLECTION

3 evidence assets


CONTEXT

Transactions
Historical coverage
Stablecoins
Ethereum


BASED ON

collection description
3 accepted evidence assets
active research context


RELATED EVIDENCE

7 owned assets may be related.

Review suggestions
```

The system earns the right to suggest only after sufficient accepted context exists.

---

# 11. Asset verification — matched self-provided evidence

Full semantic Detail authority:

```text
PRIVATE USDT TRANSACTIONS
QUERY-READY

Historical USDT transfer records
supplied by the researcher.


EVIDENCE

Transactions · 47 entities
8 registered fields
Coverage · 2020–2024


SOURCE

Self-provided
Original upload preserved


VERIFICATION

MATCHED

Strong correspondence with
BigQuery public USDT records.

✓ transaction identifiers
✓ timestamps
✓ transfer values

? complete row equivalence
? private transformations

Verification record ▸
Source record ▸

─────────────────────────────

[ Preview ]

Compare source match
Use in Synthesis
```

The centre scan state is:

```text
PRIVATE USDT TRANSACTIONS  SELF-PROVIDED  MATCHED  QUERY-READY
Historical USDT transfer records supplied by the researcher.
```

This is a valid state:

```text
SOURCE
Self-provided

VERIFICATION
Matched

READINESS
Query-ready
```

---

# 12. Asset verification — partial after Composer comparison

Ask may reason over the selected asset's schema, coverage, source relationship, provenance, and matched sourcable evidence.

Example Ask state:

```text
PRIVATE USDT TRANSACTIONS
QUERY-READY

Composer · selected evidence


You

How reliable is this match?
Could this dataset have been
transformed after download?


Composer

The current verification establishes
correspondence on transaction IDs,
timestamps, and transfer values.

It does not establish full row
equivalence or absence of private
transformations.

I can compare observed schema,
coverage, and sampled row identity
against the matched public source.


[ Compare source match ]
```

After supported comparison, the durable asset may change to:

```text
PRIVATE USDT TRANSACTIONS  SELF-PROVIDED  PARTIAL  QUERY-READY
Historical USDT transfer records supplied by the researcher.
```

Detail:

```text
VERIFICATION

PARTIAL

The owned asset corresponds strongly
to BigQuery public USDT evidence.

Observed differences were found in
coverage and derived fields.


MATCHED

✓ transaction identifiers
✓ timestamps
✓ raw transfer values


DIFFERS

! 3 derived fields
! 14-day coverage extension


NOT ESTABLISHED

? transformation methodology


Verification record ▸
```

Composer / Cite-Agent may not silently upgrade verification state from model prose. A durable comparison/verification record must establish the relationship.

---

# 13. Asset verification — self-provided with no established external source

Centre:

```text
PRIVATE ENTITY LABELS  SELF-PROVIDED  UNVERIFIED  QUERY-READY
Researcher-maintained labels for known stablecoin entities.
```

Detail:

```text
PRIVATE ENTITY LABELS
QUERY-READY

Researcher-maintained address labels
for known stablecoin entities.


SOURCE

Self-provided


VERIFICATION

UNVERIFIED

No corresponding authoritative
external dataset has been established.


KNOWN

✓ 1,204 labelled addresses
✓ 83 entity groups
✓ original upload preserved


UNKNOWN

? external equivalence
? independent attribution authority


Verification record ▸

─────────────────────────────

[ Preview ]

Find comparable evidence
Use in Synthesis
```

Query readiness and external verification remain independent.

---

# 14. Unavailable or failed source authority

The centre may render:

```text
HISTORICAL OWNERSHIP PANEL  NOT RECORDED  NOT CHECKED  REGISTERED
Point-in-time ownership evidence retained from a legacy research import.
```

Or:

```text
MARKET VENUE SNAPSHOT  REFINTIV  UNVERIFIED  UNAVAILABLE / NOT VERIFIED
Historical venue snapshot whose source entitlement can no longer be confirmed.
```

Selected Detail:

```text
MARKET VENUE SNAPSHOT
UNAVAILABLE / NOT VERIFIED

Historical venue evidence retained
from an earlier research archive.


SOURCE

Refinitiv

Source identity recorded
Current entitlement unavailable


VERIFICATION

UNVERIFIED

The current source relationship cannot
be re-checked with available access.


KNOWN

✓ archive object preserved
✓ recorded source identity retained


UNKNOWN

? current source equivalence
? entitlement validity
? query readiness


Technical record ▸

─────────────────────────────

[ View preserved evidence ]

Review source access
Find comparable evidence
```

Do not convert source unavailability into false provenance confidence.

---

# 15. Search authority

Library searches the evidence estate, not only filenames.

Search field:

```text
[ Search assets, entities, fields, sources, provenance…                 ⌕ ]
```

Supported authority-backed match families include:

```text
asset identity / description
entity
registered field / schema
source identity
citation / DOI / source record
provenance record
coverage
```

A semantic evidence match may be supported only when grounded in typed Library metadata / context authority.

Normal rows remain two lines.

Search result rows may use a temporary third match line:

```text
TITLE                     SOURCE       VERIFY       STATE
plain-language description
MATCH · FIELD / SOURCE / PROVENANCE / COVERAGE · exact reason
```

Full search state:

```text
RESEARCH DRIVE — LIBRARY
SEARCH RESULT STATE

SEARCH QUERY: counterparty address


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   LIBRARY                             + ADD EVIDENCE ▾│ DETAIL ●              ASK           │
│                        │                                                                             │ USDT TRANSACTION DATASET            │
│    Home                │ STABLECOIN RESEARCH  /  RAW EVIDENCE                                        │ QUERY-READY                         │
│  ● Library             │                                                                             │                                     │
│    Discover            │ RAW EVIDENCE                                            3 RESULTS           │ Public USDT transfer evidence       │
│    Synthesis           │                                                                             │ for event and entity analysis.      │
│    Resources           │ [ counterparty address                                                    × ] │                                     │
│    Profile             │                                                                             │ MATCH                               │
│    Settings            │ 3 matches in fields and evidence descriptions                              │                                     │
│                        │                                                                             │ FIELD                               │
│ ACTIVE RESEARCH        │ ┌────────────────────┬─────────────────────────────────────────────────────┐ │                                     │
│                        │ │ COLLECTIONS        │ EVIDENCE                 SOURCE     VERIFY      STATE│ │ to_address                          │
│ Stablecoin Research   │ │                    ├─────────────────────────────────────────────────────┤ │ from_address                        │
│                        │ │ ▾ Stablecoin       │ ▌ USDT TRANSACTION       BIGQUERY   VERIFIED    QUERY│ │                                     │
│ Event studies          │ │   Research         │   DATASET                                      -READY│ │ Registered fields                  │
│                        │ │                    │   Public USDT transfer evidence for event analysis.  │ │                                     │
│ Market structure       │ │   ● Raw evidence  │   MATCH · FIELD · to_address · from_address          │ │ ✓ from_address                     │
│                        │ │                    │                                                     │ │ ✓ to_address                       │
│ ────────────────────── │ │     Research      │   ERC-20 TRANSFER         BIGQUERY   VERIFIED    QUERY│ │ ✓ tx_hash                          │
│                        │ │     panels         │   HISTORY                                      -READY│ │ ✓ block_time                       │
│ RECENT                 │ │                    │   Historical ERC-20 transfer evidence by token.      │ │                                     │
│                        │ │     Outputs       │   MATCH · FIELD · from_address · to_address           │ │ SOURCE                              │
│ USDT transactions      │ │                    │                                                     │ │                                     │
│ Event study panel      │ │                    │   PRIVATE WALLET FLOWS      SELF-       PARTIAL   REGIS│ │ BigQuery public datasets           │
│                        │ │                    │   Researcher-maintained wallet flows.  PROVIDED       TERED│                                     │
│                        │ │                    │   MATCH · DESCRIPTION · counterparty address         │ │ Source record ▸                     │
│                        │ │                    │                                                     │ │ Copy citation                       │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │                                                     │ │ VERIFICATION                        │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │                                                     │ │ VERIFIED                            │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │                                                     │ │ Source and owned asset relationship │
│                        │ │                    │                                                     │ │ established.                        │
│                        │ └────────────────────┴─────────────────────────────────────────────────────┘ │                                     │
│                        │                                                                             ├─────────────────────────────────────┤
│                        │ 3 results                                                                    │ [ Preview ]                         │
│                        │                                                                             │ Use in Synthesis                    │
│                        │                                                                             │ Find related evidence               │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Search explains why an asset matched without replacing its description        │ Field match                          │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

The selected search match is scoped to the underlying asset. Detail must expose both match reason and canonical asset truth.

No model prose may invent a field, source, coverage, citation, or provenance match.

---

# 16. Plural / derived lineage

A derived dataset does not explode the source column.

Centre:

```text
STABLECOIN EVENT STUDY PANEL  2 SOURCES  VERIFIED  QUERY-READY
Event-window panel for measuring on-chain response around stress events.
```

Plural lineage grammar:

```text
2 SOURCES
3 SOURCES
8 SOURCES
```

Do not squeeze:

```text
BigQuery + GDELT + DataCite + MOPS
```

into the ledger.

Full derived state:

```text
RESEARCH DRIVE — LIBRARY
DERIVED DATASET / PLURAL LINEAGE

DESKTOP / 1440 × 1024


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   LIBRARY                             + ADD EVIDENCE ▾│ DETAIL ●              ASK           │
│                        │                                                                             │ STABLECOIN EVENT STUDY PANEL        │
│    Home                │ STABLECOIN RESEARCH  /  RESEARCH PANELS                                     │ QUERY-READY                         │
│  ● Library             │                                                                             │                                     │
│    Discover            │ RESEARCH PANELS                                          41 ASSETS          │ Event-window panel for measuring    │
│    Synthesis           │                                                                             │ on-chain response around stablecoin │
│    Resources           │ [ Search assets, entities, fields, sources, provenance…                 ⌕ ] │ stress events.                      │
│    Profile             │                                                                             │                                     │
│    Settings            │ All 41 ●     Query-ready 32     Registered 7     Metadata only 2            │ EVIDENCE                            │
│                        │                                                                             │                                     │
│ ACTIVE RESEARCH        │ ┌────────────────────┬─────────────────────────────────────────────────────┐ │ Event × entity × day                │
│                        │ │ COLLECTIONS        │ EVIDENCE                 SOURCE     VERIFY      STATE│ │ 47 entities                         │
│ Stablecoin Research   │ │                    ├─────────────────────────────────────────────────────┤ │ 26 stress events                    │
│                        │ │ ▾ Stablecoin       │ ▌ STABLECOIN EVENT       2 SOURCES  VERIFIED    QUERY│ │ Coverage · 2020–2024                │
│ Event studies          │ │   Research         │   STUDY PANEL                                  -READY│ │                                     │
│                        │ │                    │   Event-window panel for on-chain stress response.   │ │ SOURCES                             │
│ Market structure       │ │     Raw evidence  │                                                     │ │                                     │
│                        │ │                    │   STABLECOIN NEWS        3 SOURCES  VERIFIED    QUERY│ │ USDT transaction dataset            │
│ ────────────────────── │ │   ● Research      │   SHOCK PANEL                                  -READY│ │ Market stress events                │
│                        │ │     panels         │   Event evidence joined to market attention data.    │ │                                     │
│ RECENT                 │ │                    │                                                     │ │ 2 registered source assets          │
│                        │ │     Outputs       │   GOVERNANCE RESPONSE    4 SOURCES  PARTIAL     REGIS│ │                                     │
│ USDT transactions      │ │                    │   PANEL                                           TERED│ │ Source chain ▸                      │
│ Event study panel      │ │                    │   Governance evidence aligned to event windows.      │ │ Copy citations                     │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │   STABLECOIN LIQUIDITY   8 SOURCES  VERIFIED    QUERY│ │ VERIFICATION                        │
│                        │ │                    │   PANEL                                         -READY│ │                                     │
│                        │ │                    │   Market-liquidity panel across stablecoin venues.   │ │ VERIFIED                            │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │   ENTITY RESPONSE        3 SOURCES  UNVERIFIED  REGIS│ │ Source lineage established from     │
│                        │ │                    │   SAMPLE                                           TERED│ │ registered Library assets.          │
│                        │ │                    │   Exploratory entity-response panel for review.      │ │                                     │
│                        │ │                    │                                                     │ │ ✓ input identities                  │
│                        │ │                    │                                                     │ │ ✓ registered asset references       │
│                        │ │                    │                                                     │ │ ✓ build provenance                  │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │                                                     │ │ LIMITATION                          │
│                        │ │                    │                                                     │ │                                     │
│                        │ │                    │                                                     │ │ Earlier transfer history not        │
│                        │ │                    │                                                     │ │ represented.                        │
│                        │ └────────────────────┴─────────────────────────────────────────────────────┘ │                                     │
│                        │                                                                             ├─────────────────────────────────────┤
│                        │ 41 evidence assets                                                           │ [ Preview ]                         │
│                        │                                                                             │ Open source chain                   │
│                        │                                                                             │ Find earlier transaction history    │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Research panels · plural lineage remains visible without exploding rows       │ Evidence lineage                     │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

The source chain and citation actions are first-class research information. They are not buried only in Technical record.

---

# 17. Citation and source actions

For a direct externally sourced asset, Detail may show:

```text
SOURCE

BigQuery public datasets
Ethereum / token transfers

Source record ▸
Copy citation
```

For a multi-record source:

```text
SOURCE

MOPS

3 source records

2021 annual report
2022 annual report
2023 annual report

Source chain ▸
Copy citations
```

For DataCite:

```text
SOURCE

DataCite

12 DOI records

Source records ▸
Copy citations
```

For self-provided evidence:

```text
SOURCE

Self-provided

Original upload preserved
No external source claimed
```

Citation/source identity is core research use. It must not be relegated exclusively to developer diagnostics or Technical record.

---

# 18. Add evidence / intake authority

Frozen top action:

```text
+ ADD EVIDENCE ▾
```

Menu:

```text
Upload files

Add URL or DOI

────────────────────

Find external evidence
```

Ownership:

```text
UPLOAD FILES
=
actual local intake


ADD URL OR DOI
=
known-object / source-record intake


FIND EXTERNAL EVIDENCE
=
Discover
```

Do not add a Library-local `Procure`, `Magic import`, `AI collect`, or `Agent acquisition` workflow. External evidence procurement remains Discover ownership.

## 18.1 Upload / intake state family

Initial upload:

```text
stablecoins_final_final.csv

        ↓

LIBRARY INTAKE

PRIVATE USDT TRANSACTIONS

SOURCE
Self-provided

VERIFICATION
NOT CHECKED

READINESS
Registration pending
```

During supported verification:

```text
PRIVATE USDT TRANSACTIONS  SELF-PROVIDED  NOT CHECKED  REGISTERED
Historical USDT transfer records supplied by the researcher.


DETAIL

VERIFICATION

CHECKING SOURCE RELATIONSHIP

Comparing the owned asset with
available sourcable evidence.

Current checks

✓ schema observed
✓ candidate source identified
● bounded source comparison

No verification claim is established yet.
```

Possible durable outcomes:

```text
MATCHED
PARTIAL
UNVERIFIED
```

No model response alone may promote the row into one of these states.

---

# 19. Empty collection

```text
RESEARCH DRIVE — LIBRARY
EMPTY COLLECTION


STABLECOIN RESEARCH  /  HISTORICAL TRANSACTION EVIDENCE

HISTORICAL TRANSACTION EVIDENCE                         0 ASSETS

[ Search assets, entities, fields, sources, provenance…         ⌕ ]


┌────────────────────┬──────────────────────────────────────────────────────────────┐
│ COLLECTIONS        │                                                              │
│                    │                NO EVIDENCE HERE YET                            │
│ ▾ Stablecoin       │                                                              │
│   Research         │     Add owned evidence to establish this collection's         │
│                    │     research context.                                          │
│   Raw evidence 128 │                                                              │
│   Research panels  │     [ Add owned evidence ]                                    │
│               41   │                                                              │
│   Outputs      12  │     Find external evidence                                    │
│                    │                                                              │
│ ▌ Historical      │                                                              │
│   transaction      │                                                              │
│   evidence      0  │                                                              │
│                    │                                                              │
│ + New collection   │                                                              │
└────────────────────┴──────────────────────────────────────────────────────────────┘


DETAIL

HISTORICAL TRANSACTION EVIDENCE
COLLECTION

0 evidence assets

CONTEXT

Not established

Based on

collection description only

RELATED EVIDENCE

Not enough accepted context yet.

─────────────────────────────

[ Add owned evidence ]

Edit collection
Find external evidence
```

Do not show fake completeness or generic celebratory empty-state copy.

---

# 20. Collection tree authority and navigation depth

Normal collection tree:

```text
COLLECTIONS

▾ Stablecoin Research
  Raw evidence             128
  Research panels           41
  Outputs                   12

▸ Taiwan governance         36

▸ Market stress             24

+ New collection
```

Nested research context is allowed when it remains legible:

```text
▾ Stablecoin Research
  ▾ Event studies
    Raw event evidence       24
    Event-study inputs       18
    Outputs                   9

  ▸ Market structure         31

▸ Taiwan governance          36
```

Desktop normal depth budget:

```text
root research context
  collection
    nested collection
```

Three visible hierarchy levels are the normal design budget. Deeper backend/storage nesting must not automatically become faculty-facing tree depth.

Navigation behavior:

```text
CLICK COLLECTION

current location changes
breadcrumb changes
contents change
collection becomes active rail object


CLICK ASSET

current location stays
asset row becomes selected
asset becomes active rail object


BACK / BREADCRUMB

changes collection location
restores collection active object
```

Explore/Discover concepts such as procurement route, approval, or lifecycle job must never appear as Library tree nodes.

---

# 21. Collection and asset menus

Collection contextual menu:

```text
Raw evidence                                  ···

Open

Rename
Edit collection context

────────────────

Review related evidence

────────────────

Move collection
Delete collection
```

Asset contextual menu:

```text
USDT TRANSACTION DATASET                      ···

Preview

────────────────

Add to collection
Manage collections

────────────────

Use in Synthesis
Find related evidence

────────────────

Technical record
```

Because one asset may belong to multiple collections, the primary organisation language is:

```text
ADD TO COLLECTION
MANAGE COLLECTIONS
REMOVE FROM COLLECTION
```

`Delete asset` is a separate destructive action and must never be implied by removing an asset from one collection.

---

# 22. Known gaps

Known gaps are typed estate knowledge, not generic AI recommendations.

Collection Detail may show:

```text
KNOWN GAPS

4 recorded evidence gaps

Review gaps
```

Asset Detail may show a specific limitation and exact action:

```text
LIMITATION

Earlier transaction history not present.

─────────────────────────────

[ Preview ]

Use in Synthesis
Find earlier transaction history
```

Exact Library → Discover handoff:

```text
CLICK
Find earlier transaction history

        ↓

DISCOVER

WHAT EVIDENCE ARE YOU LOOKING FOR?

Historical USDT transaction evidence before 2020,
compatible with the existing USDT transaction dataset.

INTERPRETING

USDT · Transactions · Pre-2020 · Existing asset compatibility

LOCAL RELATIONSHIP

Partial
Existing coverage begins in 2020
```

Gap visibility rules:

```text
0 KNOWN GAPS
show nothing


1 KNOWN GAP
1 known evidence gap
Review gap


2+ KNOWN GAPS
4 known evidence gaps
Review gaps
```

Only render a known-gap claim when typed gap/comparison authority exists.

---

# 23. Library right-rail integration authority

The rail is not merely an asset inspector.

It interprets the exact selected Library object.

## 23.1 Collection active object

```text
kind = library_collection
```

Detail owns:

```text
collection identity
collection meaning
accepted context
estate summary
related-evidence suggestion state
known gaps
current organisation decision
```

Ask / Composer / Cite-Agent may:

```text
explain collection context
compare owned evidence against accepted context
propose related owned evidence
explain suggestion signals
inspect known gaps
refine collection context when explicitly accepted
create exact Discover handoff for a recorded gap
```

Ask may not:

```text
silently add or remove collection membership
autonomously create collection hierarchies
silently rewrite accepted context
upgrade source / verification authority from prose
```

## 23.2 Asset active object

```text
kind = library_asset
```

Detail owns:

```text
asset identity
research use
readiness
evidence shape / coverage
source
verification relationship
collection memberships
limitations
citation / source-chain actions
```

Ask / Composer / Cite-Agent may:

```text
explain evidence semantics
inspect source relationship
compare owned evidence with matched sourcable evidence
reason over schema / coverage / provenance
find related owned evidence
assess research use
prepare exact Discover handoff for a limitation / gap
```

Supported durable operations may include:

```text
run bounded source comparison
record verification result
record comparison differences
record collection suggestions
prepare collection membership review
record typed gap
open exact Discover requirement
```

## 23.3 Search match active object

```text
kind = library_search_match
parent = library_asset
```

Detail owns:

```text
why the asset matched
exact match authority
underlying canonical asset truth
```

Ask remains scoped to the exact underlying asset plus the current search match reason.

---

# 24. Bounded rail authority

Library uses the same global bounded rail grammar:

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

Collection Detail default budget:

```text
IDENTITY / TYPE

one collection judgment

EVIDENCE SUMMARY

CONTEXT

RELATED EVIDENCE or KNOWN GAPS
only when material

one disclosure

sticky actions
```

Asset Detail default budget:

```text
IDENTITY / READINESS

one plain research-use judgment

EVIDENCE / COVERAGE

SOURCE

VERIFICATION or LIMITATION
whichever is current material decision

one disclosure

sticky actions
```

Source record, Verification record, and Source chain are first-class research disclosures/actions. Technical record remains the developer/operational disclosure.

The rail must not become a vertical provenance report.

---

# 25. Inventory-scale authority

At 128+ assets:

```text
TABLE HEADER
fixed within evidence pane

EVIDENCE PANE
min-height: 0
overflow-y: auto

NORMAL ROW
2 lines

SOURCE
one scan line

VERIFY
one scan line

STATE
one canonical readiness label
```

Do not add secondary source text to every normal row.

The lower centre may show:

```text
128 evidence assets
```

or a bounded list position when useful:

```text
128 evidence assets · list position 1–10
```

The evidence pane scrolls independently inside the full-height desk.

---

# 26. Add / organise / verify durable consequences

Successful mutations return compact product receipts.

Examples:

```text
✓ 2 assets added to Raw evidence

✓ Collection context updated

✓ 3 related evidence suggestions recorded

✓ Verification comparison completed

✓ Verification relationship updated to Partial

✓ Evidence gap recorded

✓ Discover requirement prepared
```

Receipts do not replace visible state change.

The selected collection or asset remains visible and its centre/Detail state updates.

---

# 27. Truth and authority table

| Visible claim | Required authority | Honest fallback |
|---|---|---|
| Asset description | registered metadata / accepted asset description | Description not recorded |
| Readiness | registry read-back / readiness contract | Registered — readiness not confirmed |
| Source | provenance / intake / provider record | Not recorded |
| Self-provided | durable intake ownership record | Source not recorded |
| Verification | completed typed source-comparison record | Not checked / Unverified |
| Matched fields | observed schema/row comparison | Match details unavailable |
| Coverage | provider metadata / observed asset authority | Not reported |
| Citation / DOI | source/provenance record | Citation not recorded |
| Source chain | registered lineage / build provenance | Source lineage not established |
| Collection membership | durable membership record | Not in collection |
| Collection context | explicit description + accepted evidence + named context inputs | Context not established |
| Related evidence suggestion | typed Library comparator over accepted context | No suggestion claim |
| Known gap | typed gap / sufficiency / comparison authority | Gap not established |
| Search match | exact typed field/source/provenance/coverage or grounded semantic metadata match | Match reason unavailable |
| AI interpretation | source/time/verification envelope | Assistant interpretation — verify source |

No fixture, model prose, filename guess, backend folder name, UI estimate, or lexical-title similarity may render as authoritative Library evidence truth.

---

# 28. Responsive authority

## 28.1 Desktop / 1440

The full three-surface desk and all full-scale CLI wireframes in this appendix are authoritative.

```text
Navigation | Centre | Detail / Ask
```

Collections tree and evidence pane remain simultaneously visible.

## 28.2 Laptop / 1280

```text
Navigation narrows
Collections tree narrows modestly
Evidence remains dominant
Rail narrows but keeps full semantic labels
```

At 1280:

```text
EVIDENCE
SOURCE
VERIFY
STATE
```

may reduce column padding, but do not remove plain-language asset descriptions or merge source and verification.

## 28.3 Tablet / 900

Navigation may collapse.

Centre remains primary:

```text
COLLECTIONS | EVIDENCE
```

Selected collection/asset Detail becomes a slide-over.

Collection tree may collapse into a location selector if simultaneous tree + evidence width is no longer readable. Current location and breadcrumb must remain explicit.

## 28.4 Mobile / 390

Mobile does not drive desktop composition.

Sequence:

```text
LIBRARY

current location
search
state filters

COLLECTIONS ▾

EVIDENCE LIST

TITLE
plain-language description
SOURCE · VERIFY · STATE

        ↓ select

DETAIL SHEET
```

Do not compress the desktop four-column ledger into unreadable micro-columns.

---

# 29. Accessibility and keyboard authority

Keyboard users can:

```text
focus collection tree
move through collections
change current location
focus search
move through evidence rows
inspect selected asset
open Preview
open source / verification / source-chain disclosure
invoke sticky primary action
switch Detail / Ask
```

Selected state cannot rely on cobalt alone; the narrow `▌` marker and accessible selected semantics must be present.

Collection suggestion review checkboxes must have explicit asset labels and preserve keyboard multi-select.

The rail's internal scroll body and sticky footer must preserve visible focus and not trap keyboard navigation.

---

# 30. Explicitly rejected Library directions

Do not add:

```text
AI organiser page
Smart folders mode
Auto-organise toggle that silently moves assets
folder recommendation feed
Library procurement workflow
Library job dashboard
Library lifecycle timeline
full-page asset evaluation workspace
per-row Preview / Ask / Use buttons
file-system archive path as faculty hierarchy
one-folder-only asset identity
verification inferred from model prose
citation hidden only in Technical record
metadata-only descriptions
source + verification collapsed into one state
readiness + verification collapsed into one state
Google Drive clone with more badges
```

Do not turn collection suggestions into a recommendation homepage.

Do not turn Composer / Cite-Agent into generic folder chat.

---

# 31. Frozen Library visual / interaction baseline

```text
LIBRARY

RESEARCH LOCATION

breadcrumb
current collection
asset count

        ↓

SEARCH

assets
entities
fields
sources
provenance

        ↓

READINESS FILTERS

All
Query-ready
Registered
Metadata only

        ↓

COLLECTIONS | EVIDENCE ESTATE

collection tree
+
compact evidence ledger


NORMAL ASSET ROW

TITLE                     SOURCE       VERIFY       STATE
plain-language one-line description


COLLECTION SELECTION

centre location changes
collection becomes active rail object
Detail shows collection context,
related owned evidence suggestions,
and known gaps


ASSET SELECTION

current location remains
selected row remains visible
asset becomes active rail object
Detail shows research use,
source,
verification,
readiness,
coverage,
collection memberships,
and limitation


ASK

Composer / Cite-Agent operates the exact selected
collection or evidence asset

        ↓

DURABLE CONSEQUENCE

suggestions recorded
verification relationship updated
gap recorded
Discover handoff prepared
collection context refined when explicitly accepted

        ↓

SAME LIBRARY OBJECT VISIBLY CHANGES
```

Core distinction:

```text
GOOGLE DRIVE

where are my files?


RESEARCH DRIVE LIBRARY

what evidence do I own?
what is it about?
where did it come from?
what source relationship is established?
can I use it?
what research context does it belong to?
what evidence is missing?
```

This is the Library visual and interaction baseline frozen on 2026-07-15. Future implementation must converge to it. Existing code, backend folder structure, generic Drive conventions, and detached assistant behavior are evidence of current implementation state only; they do not override this freeze.
