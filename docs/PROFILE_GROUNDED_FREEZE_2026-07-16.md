# Research Drive — Profile Grounded Freeze

**Status:** GROUNDED COMPOSITION FREEZE / BACKUP AUTHORITY  
**Date:** 2026-07-16  
**Scope:** `Profile` centre composition and the data contract it is allowed to present  
**Implementation posture:** polish in place; do not redesign the product model unless the faculty-profile backend is materially expanded first

This document preserves the Profile convergence reached after visual review against the actual faculty-profile view model and current profile-building method.

The core correction is simple:

```text
PROFILE IS NOT

social profile
CV / résumé builder
academic identity graph
settings form
opaque AI-memory inspector

PROFILE IS

RESEARCH MEMORY
DERIVED FROM THE FACULTY PROFILE / REGISTRY CONTRACT
```

The current organic information architecture remains:

```text
MEMORY
↓
WORKS
↓
LAB

LINKED | SUGGESTED
```

The current implementation and view model already understand this shape. Thin faculty profiles must yield fewer blocks rather than invented substitute content.

---

## 1. Actual supported faculty-profile surface

Profile presentation may be built from the faculty profile / registry fields currently available to the product.

```text
IDENTITY
─────────────────────────────
name_en / name
title
discipline
email


MEMORY
─────────────────────────────
specialties

research_tracks
  title
  phase
  weight

method_tags


WORKS
─────────────────────────────
publication_highlights
paper_count / paper_count_parsed


LAB
─────────────────────────────
lab_fintech_stack

procurement_recommendations
```

Current profile-aware prompts may additionally use:

```text
starter_prompts
procurement_recommendations[].prompt
default_search_query
```

These may shape Ask or Home suggestions, but they do not automatically create new Profile ontology.

---

## 2. Hard honesty constraint

Do not present unsupported profile objects merely because they would make a visually richer page.

The following concepts are **not current Profile authority by default**:

```text
MARKETS & ENTITIES
EVIDENCE PREFERENCES
INFERRED SIGNALS
ACCEPTED CONTEXT
PRODUCT EFFECT
RANKING EFFECT LEDGER
PROFILE BELIEF PROVENANCE TABLE
```

They require a real backing model and durable authority before they can appear as canonical Profile truth.

In particular:

```text
MODEL INFERENCE
≠
PROFILE FACT

RECENT DATASET USE
≠
ACCEPTED RESEARCH PREFERENCE

MODEL PROSE
≠
RANKING-AUTHORITY RECORD
```

---

## 3. Rejected visual directions

### Rejected: context ledger

```text
CONTEXT                 ORIGIN          AFFECTS

STABLECOINS             EXPLICIT        DISCOVER
UNITED STATES           INFERRED        ASK
TRANSACTION DATA        EXPLICIT        LIBRARY
...
```

Reason:

```text
TOO SIMILAR TO LIBRARY / RESOURCES LEDGER GRAMMAR
+
REQUIRES CONTEXT ORIGIN / PRODUCT EFFECT AUTHORITY
THE CURRENT PROFILE BACKEND DOES NOT SUPPLY
```

### Rejected: research CV / dossier

```text
CHRISTOPHER ONGKO
王新福

FINANCE · DATA RESEARCH · APPLIED AI

I study digital markets through...

CURRENT RESEARCH
RESEARCH LENSES
EVIDENCE I WORK WITH
CONTEXT RECORD
```

Reason:

```text
OVER-INDEXES ON A PERSONAL RÉSUMÉ / CV
DOES NOT SCALE ORGANICALLY TO PROFESSOR PROFILES
REQUIRES GENERATED BIOGRAPHICAL / RESEARCH-IDENTITY COPY
BEYOND THE CURRENT PROFILE-BUILDING METHOD
```

### Rejected: synthetic research-context sheet

```text
RESEARCH FOCUS
MARKETS & ENTITIES
EVIDENCE PREFERENCES
ACTIVE WORK
CONTEXT REVIEW
```

Reason:

```text
CLOSER VISUALLY
BUT STILL DESIGNS PAST THE ACTUAL PROFILE JSON / VIEW MODEL
```

---

## 4. Current full-scale grounded composition

The following CLI wireframe is the current grounded visual direction. It keeps the existing product model and makes Memory visually dominant without inventing a new faculty ontology.

```text
RESEARCH DRIVE — PROFILE
GROUNDED VISUAL FREEZE

ACTUAL FACULTY PROFILE DATA ONLY

DESKTOP / 1440 × 1024


┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ RESEARCH DRIVE         │ STABLECOIN RESEARCH ▾   PROFILE                                             │ DETAIL ●              ASK           │
│                        │                                                                             │ SCHOLAR                             │
│    Home                │ RESEARCH MEMORY                                                             │                                     │
│    Library             │                                                                             │ Finance faculty · present focus on  │
│    Discover            │ KONG, DE-RONG                                                               │ fintech and digital transformation. │
│    Synthesis           │ Professor · Finance                                                         │                                     │
│    Resources           │ drkong@saturn.yzu.edu.tw                                                    │ STRENGTHS                           │
│  ● Profile             │                                                                             │                                     │
│    Settings            │ 23 INDEXED WORKS                                      4 SAVED CONTEXTS      │ FinTech through-line                │
│                        │                                                                             │ Market + on-chain panels            │
│ ACTIVE RESEARCH        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │                                                                             │ DESK                                │
│ Stablecoin Research   │ MEMORY                                                                      │                                     │
│                        │                                                                             │ FinTech panels linked.              │
│ Event studies          │ ┌───────────────────────────────────────┐  ┌──────────────────────────────┐ │ Taiwan equity / misconduct open    │
│                        │ │ RESEARCH FOCUS                        │  │ CURRENT RESEARCH DIRECTION   ● │ │ to link.                            │
│ Market structure       │ │                                       │  │                              │ │                                     │
│                        │ │ Asset Pricing, Corporate Finance,      │  │ FinTech and digital          │ │                                     │
│ ────────────────────── │ │ and Financial Technology              │  │ transformation               │ │                                     │
│                        │ └───────────────────────────────────────┘  │                              │ │                                     │
│ RECENT                 │                                            │ Used when finding and        │ │                                     │
│                        │ ┌───────────────────────────────────────┐  │ evaluating evidence.         │ │                                     │
│ USDT transactions      │ │ RESEARCH CONTEXT                      │  └──────────────────────────────┘ │                                     │
│ Event study panel      │ │                                       │                                   │                                     │
│                        │ │ Also: Corporate misconduct ·           │                                   │                                     │
│                        │ │ Token markets                          │                                   │                                     │
│                        │ └───────────────────────────────────────┘                                   │                                     │
│                        │                                                                             │                                     │
│                        │ ┌───────────────────────────────────────┐                                   │                                     │
│                        │ │ METHODS                               │                                   │                                     │
│                        │ │                                       │                                   │                                     │
│                        │ │ panel data · machine learning ·        │                                   │                                     │
│                        │ │ on-chain analysis                      │                                   │                                     │
│                        │ └───────────────────────────────────────┘                                   │                                     │
│                        │                                                                             │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │                                                                             │                                     │
│                        │ WORKS                                                    23 INDEXED          │                                     │
│                        │                                                                             │                                     │
│                        │ 01   FINTECH AND DIGITAL TRANSFORMATION                                  → │                                     │
│                        │                                                                             │                                     │
│                        │ 02   CORPORATE MISCONDUCT AND MARKET RESPONSE                             → │                                     │
│                        │                                                                             │                                     │
│                        │ ─────────────────────────────────────────────────────────────────────────── │                                     │
│                        │                                                                             │                                     │
│                        │ LAB                                                                         │                                     │
│                        │                                                                             │                                     │
│                        │ LINKED TO YOU                            SUGGESTED                            │                                     │
│                        │                                                                             │                                     │
│                        │ Crypto / NFT panel       Vaulted · Open → Taiwan equity      in lab · Link →│                                     │
│                        │ Stablecoin activity      BigQuery · Open → Misconduct data  not in lab · Search →│                                  │
│                        │                                                                             │                                     │
│                        │                                                                             ├─────────────────────────────────────┤
│                        │                                                                             │ Ask about this research memory      │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
│ Stablecoin Research    │ Memory → Works → Lab                                                         │ Faculty research memory              │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘
```

---

## 5. Visual priorities

Profile should remain quiet and editorial.

The strongest visual distinction comes from the asymmetric Memory composition:

```text
SAVED MEMORY CARDS

RESEARCH FOCUS
RESEARCH CONTEXT
METHODS

        +

CURRENT RESEARCH DIRECTION
visually dominant anchor
```

Do not turn Memory into chips, tabs, a ledger, or a ranking-effect table.

Works remains a compact grounding layer:

```text
WORKS

01  publication highlight
02  publication highlight

N INDEXED
```

Lab remains a compact relationship layer:

```text
LAB

LINKED TO YOU              SUGGESTED
owned / linked holdings    procurement recommendations
```

---

## 6. Detail / Ask

Profile Detail remains evidence-gated and grounded in the current view model:

```text
SCHOLAR
STRENGTHS
DESK
```

It may derive concise statements from:

```text
discipline
primary research track
track phase
method tags
publication count
lab_fintech_stack
procurement_recommendations
```

It must not invent a richer research identity than the backing fields support.

The `Ask` tab remains part of the application-wide `DETAIL | ASK` grammar.

For Profile, Ask stays quiet and profile-scoped. It may use the bound faculty profile and active research context as context for a question. It must not silently write inferred profile attributes back as accepted profile truth.

---

## 7. Thin / unbound profiles

Thin faculty profiles are not errors.

```text
RICH PROFILE
Memory + Works + Lab

THIN PROFILE
Memory only
or
Memory + Lab
or
identity + one grounded block
```

Do not synthesize missing biography, methods, markets, or publication themes to fill visual space.

For an unbound desk, an example / pilot profile must be visibly labelled as example or pilot context.

---

## 8. Freeze rule

Profile is not currently a major product-design problem.

```text
PRODUCT MODEL        KEEP
IA                   KEEP
DATA CONTRACT        RESPECT
MAJOR REDESIGN       NO
VISUAL POLISH        YES
```

Permitted next work:

```text
Memory hierarchy
Current research direction emphasis
Works density
Lab Linked / Suggested balance
Detail rail typography / spacing
thin-profile rendering
pilot / unbound labelling
responsive convergence
```

A future redesign that introduces markets/entities, evidence preferences, inferred signals, accepted context, or product-effect ledgers must first expand the durable faculty-profile model and authority contract. The frontend must not lead the backend into fabricated profile truth.
