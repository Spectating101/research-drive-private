#!/usr/bin/env python3
"""
Research Drive — CLI wireframe preview + industry steal rationale.

Authority: docs/RESEARCH_DRIVE_UI_CANON.md (this script is optional exploration only).

Cheap design review before React/CSS work. Stdlib only.

  python3 scripts/rd_desk_blueprint_preview.py
  python3 scripts/rd_desk_blueprint_preview.py --screen home
  python3 scripts/rd_desk_blueprint_preview.py --matrix
  python3 scripts/rd_desk_blueprint_preview.py --compare
  python3 scripts/rd_desk_blueprint_preview.py --flows
  python3 scripts/rd_desk_blueprint_preview.py --identity
  python3 scripts/rd_desk_blueprint_preview.py --screen home-pulse
  python3 scripts/rd_desk_blueprint_preview.py --screen lab-grouped
"""

from __future__ import annotations

import argparse
import shutil
import sys
import textwrap
from dataclasses import dataclass, field


@dataclass
class Steal:
    platform: str
    pattern: str
    why_us: str
    skip: str = ""


@dataclass
class Screen:
    id: str
    title: str
    wireframe: list[str]
    steals: list[Steal] = field(default_factory=list)
    flows: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)


def term_width() -> int:
    return min(100, max(72, shutil.get_terminal_size((100, 24)).columns))


def box(title: str, lines: list[str], width: int | None = None) -> str:
    w = width or term_width()
    inner = w - 4
    out = [f"┌─ {title}" + "─" * max(0, w - len(title) - 3) + "┐"]
    for line in lines:
        if len(line) <= inner:
            out.append(f"│ {line.ljust(inner)} │")
        else:
            for chunk in textwrap.wrap(line, width=inner):
                out.append(f"│ {chunk.ljust(inner)} │")
    out.append("└" + "─" * (w - 2) + "┘")
    return "\n".join(out)


SCREENS: dict[str, Screen] = {
    "home-pulse": Screen(
        id="home-pulse",
        title="HOME — Lab pulse (v2 target) — light catalog identity",
        wireframe=[
            "┌─ RD ── [Search library…] ─── 78 ds · 1 link · 11 jobs ─ [New] ─┐",
            "├ NAV ─┬─ MAIN (light #f7f9fc) ──────────────────┬─ INSPECTOR ────┤",
            "│ ●Home│ Home · 78 datasets in the lab library    │ [Details*]     │",
            "│ Drive│ ┌─ Continue ────────┬─ Pipeline ───────┐ │  (collapsed    │",
            "│ Disc │ │ TWSE daily panel  │ ● GDELT GKG  42% │ │   until pick)  │",
            "│ Src  │ │ [Open][Ask]       │ ● DataCite  RUN  │ │                │",
            "│ Pipe │ └───────────────────┴──────────────────┘ │                │",
            "│      │ Quick open: [Skynet] [USDT] [GDELT] …    │                │",
            "│      │ Recent (5 max)              [See all →]   │                │",
            "│      │ ┌────────────────────────────────────────┐ │                │",
            "│      │ │ Name + faculty summary    Kind   Pill  │ │                │",
            "│      │ └────────────────────────────────────────┘ │                │",
            "└──────┴────────────────────────────────────────────┴────────────────┘",
            "",
            "  NO: fake 5-step stepper · duplicate stat strip · Suggested table",
            "  NO: ghost Access/Schema tiles · dark teal ops console on Home",
        ],
        steals=[
            Steal("Google Drive", "Light browse canvas + 3-column shell",
                  "Faculty muscle memory; Home is digest not warehouse."),
            Steal("platform_status CLI", "OK/WARN/FAIL honesty in pipeline rows",
                  "Real % from /yzu/acquisitions — never decorative progress."),
            Steal("Notion DB", "Continue card + recent rows",
                  "Orient in <10s; one table not two."),
            Steal("Gemini in Drive", "Quick open chips → Chat when needed",
                  "Ambient sourcing, not thread on landing."),
            Steal("—", "NOT dark admin dashboard", "Dark only for Activity/ops."),
        ],
        flows=[
            "Orient: Continue + pipeline + 5 recent rows.",
            "Acquire: chip or header Chat → Sourcing (not sidebar thread).",
        ],
        acceptance=[
            "Light default on Home/Drive/Discover.",
            "Pipeline binds to live acquisitions API.",
            "Inspector idle is one line — no placeholder grid.",
            "Newsreader on page title only; Plex Sans on tables.",
        ],
    ),
    "home": Screen(
        id="home",
        title="HOME — Lab data library (default landing)",
        wireframe=[
            "┌─ RD ── [Search datasets in library…] ───────────── [New] [YZ] ─┐",
            "├ NAV ─┬─ MAIN (primary) ─────────────────────┬─ INSPECTOR ───────┤",
            "│ ●Home│ Lab data library                      │ [Details*][Source]│",
            "│  My  │ ┌─ Source with assistant ─────────────┐ │                   │",
            "│  Lab │ │ Describe a dataset to collect… [Src]│ │  Ask the assistant│",
            "│  Disc│ │ [Browse finance][Source new data]   │ │  [Browse …][Src…] │",
            "│  Act │ └───────────────────────────────────┘ │                   │",
            "│      │ 6 lab datasets · Browse Lab Drive     │  Dataset details  │",
            "│      │ Featured datasets          [View all] │  (select a row)   │",
            "│      │ ┌───────────────────────────────────┐ │                   │",
            "│      │ │ Name + summary    Kind      Status│ │  *Details default │",
            "│      │ └───────────────────────────────────┘ │                   │",
            "└──────┴───────────────────────────────────────┴───────────────────┘",
        ],
        steals=[
            Steal("Google Drive", "3-column shell + list browse",
                  "Faculty already navigate files; we keep muscle memory."),
            Steal("Gemini in Drive", "Compose bar + suggestion chips on browse",
                  "AI visible without chat-as-homepage; opens Source thread."),
            Steal("Snowflake / BigQuery", "Typed rows + status pills",
                  "Datasets are assets with backend state, not opaque files."),
            Steal("Notion DB list", "Title + rich subtitle column",
                  "FACULTY_SUMMARIES answer 'what is this for?' in the row."),
            Steal("—", "NO quick-access tiles", "Sidebar already navigates; tiles duplicated nav."),
            Steal("—", "NO full chat on landing", "Procurement thread only in Source tab."),
        ],
        flows=[
            "Orient: professor sees holdings + how to source more in <10s.",
            "Acquire (light): type in smart procure bar → Source tab → candidates.",
        ],
        acceptance=[
            "Details tab selected by default; Source panel not visible.",
            "Smart procure bar visible with contextual chips.",
            "Each row shows kind + one-line research summary.",
        ],
    ),
    "home-selected": Screen(
        id="home-selected",
        title="HOME — row selected (toolbar + Details)",
        wireframe=[
            "┌─ … same header / nav … ─────────────────────────────────────────┐",
            "├ NAV ─┬─ MAIN ─────────────────────────────┬─ INSPECTOR Details ─┤",
            "│      │ ┌─ CoinGecko crypto market archive ─ Open Preview Clear ┐│",
            "│      │ │ ● CoinGecko…  SQLite database   STORED  ←selected    ││",
            "│      │ │   GDELT Asia… Country-day panel STORED                ││",
            "│      │ └───────────────────────────────────────────────────────┘│",
            "│      │                                       │ KIND: SQLite DB   │",
            "│      │                                       │ Historical crypto │",
            "│      │                                       │ prices, caps…     │",
            "│      │                                       │ STORED · Verified │",
            "│      │                                       │ Access: local+GD  │",
            "│      │                                       │ [Open][Preview]   │",
            "│      │                                       │ [Source related]  │",
            "└──────┴───────────────────────────────────────┴───────────────────┘",
        ],
        steals=[
            Steal("Google Drive", "Inspector updates on selection",
                  "Metadata without opening full page for every glance."),
            Steal("Finder / Explorer", "Selection toolbar in content",
                  "Open is primary action; matches file mental model."),
            Steal("Databricks Unity", "Open → workspace for preview/schema",
                  "Deep use happens in Dataset view, not rail-only."),
        ],
        flows=["Use (light): select → read Details → Open if needed."],
        acceptance=[
            "Toolbar appears in main, not only rail.",
            "Details shows summary + pills + actions, not chat starters.",
        ],
    ),
    "lab": Screen(
        id="lab",
        title="LAB DRIVE — CURRENT (folder tree) — ✗ not recommended",
        wireframe=[
            "  WHY THIS FEELS WRONG AT LAB SCALE",
            "  • Sidebar nav (Lab) + folder rail + breadcrumbs + table = 3 navigators",
            "  • Google Drive does NOT put a folder tree beside the file list",
            "  • Explorer chrome for ~6 datasets — annoyance without scale payoff",
            "",
            "├ NAV ─┬─ MAIN ─────────────────────────────┬─ INSPECTOR ───────┤",
            "│ ●Lab │ ┌─ Source with assistant ───────────┐ │ [Details*]        │",
            "│      │ └───────────────────────────────────┘ │                   │",
            "│      │ ┌Folders─┐ ┌─────────────────────────┐ │                   │",
            "│      │ │Research│ │ breadcrumb / folder / … │ │  ← triple chrome  │",
            "│      │ │Import…│ │ Name + summary Kind Stat│ │                   │",
            "│      │ └────────┘ └─────────────────────────┘ │                   │",
            "│      │ [All][Available][Connected][Archived]   │                   │",
            "└──────┴───────────────────────────────────────┴───────────────────┘",
        ],
        steals=[
            Steal("Windows Explorer", "Tree + list split pane",
                  "Works at 10k files; we have ~6 curated panels."),
            Steal("—", "NOT Google Drive", "Drive uses flat list + breadcrumb only."),
            Steal("—", "REJECT for v1", "Keep folder IDs in data model; hide tree in UI."),
        ],
        flows=["This is what React ships today — replace with lab-grouped."],
        acceptance=["Do not ship more polish on this layout.", "Use lab-grouped wireframe instead."],
    ),
    "lab-grouped": Screen(
        id="lab-grouped",
        title="LAB DRIVE — PROPOSED (grouped list, no folder rail) — ✓ recommended",
        wireframe=[
            "├ NAV ─┬─ MAIN (full width list) ───────────────┬─ INSPECTOR ───────┤",
            "│  Home│ Lab Drive · 6 curated datasets         │ [Details*][Source]│",
            "│  My  │ ┌─ Source with assistant ──────────────┐ │                   │",
            "│ ●Lab │ │ Need data not listed? ………… [Source]  │ │  Details + chips  │",
            "│  Disc│ └──────────────────────────────────────┘ │                   │",
            "│  Act │ [All][Available][Connected][Archived]    │                   │",
            "│      │                                            │                   │",
            "│      │ ▼ Research panels (3)          [collapse]  │                   │",
            "│      │   CoinGecko crypto market archive           │                   │",
            "│      │   SQLite database · STORED                  │                   │",
            "│      │   Historical crypto prices, caps, volumes…  │                   │",
            "│      │                                            │                   │",
            "│      │   GDELT Asia daily country panel            │                   │",
            "│      │   Country-day panel · STORED                │                   │",
            "│      │   Macro, trade, governance news-risk…       │                   │",
            "│      │                                            │                   │",
            "│      │ ▼ Connections (1)                          │                   │",
            "│      │   Ethereum USDT transfer catalogue            │                   │",
            "│      │   Remote table · CONNECTED                  │                   │",
            "│      │                                            │                   │",
            "│      │ ▼ Collecting now (1)                       │                   │",
            "│      │   Taiwan equity panel campaign · PENDING    │                   │",
            "│      │   Procurement · approve in Source/Activity  │                   │",
            "└──────┴────────────────────────────────────────────┴───────────────────┘",
        ],
        steals=[
            Steal("Google Drive", "One primary list, full width",
                  "Drive: sidebar switches roots; main = flat files only."),
            Steal("Dropbox", "Grouped-by-date list rhythm",
                  "Section headers replace folder tree for small catalogs."),
            Steal("Notion grouped DB", "Group = folder semantics without tree UI",
                  "research_panels / procured / connections stay as labels."),
            Steal("Snowflake catalog", "Rich rows under group headers",
                  "Kind + summary + status — same grammar as Home."),
            Steal("Our pipeline", "Collecting now section",
                  "Campaigns visible without drilling folders."),
        ],
        flows=[
            "Scan: one scroll, groups teach structure in 5 seconds.",
            "Select row → Details; double-click → Dataset workspace.",
            "Smart bar → Source → promoted row appears under Imported.",
        ],
        acceptance=[
            "No left folder rail; no breadcrumb row for top-level Lab.",
            "Groups map to existing folder IDs (data unchanged).",
            "52px rows, summary line, filter chips only.",
            "Smart procure bar + Details default unchanged.",
        ],
    ),
    "my-tree": Screen(
        id="my-tree",
        title="MY DRIVE — CURRENT (folder tree) — ✗ not recommended",
        wireframe=[
            "  Same Explorer pattern as Lab — worse here:",
            "  • Personal uploads are usually flat (5–30 files)",
            "  • Folder tree + breadcrumbs for 'Uploads' is empty ceremony",
            "",
            "├ NAV ─┬─ MAIN ─────────────────────────────┬─ INSPECTOR ───────┤",
            "│  Lab │ My Drive · 4 files                   │ [Details*]        │",
            "│ ●My  │ ┌Folders─┐ ┌─────────────────────────┐ │                   │",
            "│      │ │ Uploads │ │ Name    Owner   Modified │ │                   │",
            "│      │ └────────┘ │ thesis.csv  You   Mar 12 │ │                   │",
            "│      │            └─────────────────────────┘ │                   │",
            "│      │ [Import]                                 │                   │",
            "└──────┴───────────────────────────────────────┴───────────────────┘",
        ],
        steals=[
            Steal("—", "NOT Google Drive My Drive", "Flat list + sort, no inner tree."),
            Steal("—", "REJECT", "Replace with my-flat."),
        ],
        flows=["Current React layout — do not polish further."],
        acceptance=["Replace with my-flat wireframe."],
    ),
    "my-flat": Screen(
        id="my-flat",
        title="MY DRIVE — PROPOSED (flat list + intake states) — ✓ recommended",
        wireframe=[
            "├ NAV ─┬─ MAIN (full width) ──────────────────┬─ INSPECTOR ───────┤",
            "│  Lab │ My Drive · 4 uploads                   │ [Details*][Source]│",
            "│ ●My  │ [Import]  [Recent ▾]  [Needs review]   │                   │",
            "│      │                                            │                   │",
            "│      │ ▼ Ready (2)                                │                   │",
            "│      │   thesis_panel_v2.csv                      │                   │",
            "│      │   Upload · Verified · Mar 12               │                   │",
            "│      │   Country-week panel you uploaded for fuse…  │                   │",
            "│      │                                            │                   │",
            "│      │ ▼ Needs review (1)                         │                   │",
            "│      │   scraped_urls_march.jsonl                 │                   │",
            "│      │   Upload · Unverified · Mar 18             │                   │",
            "│      │   Private until schema + provenance check  │                   │",
            "│      │                                            │                   │",
            "│      │ ▼ Draft (1)                                │                   │",
            "│      │   notes_raw.txt · scan pending             │                   │",
            "│      │                                            │                   │",
            "│      │ Drag files here or [Import]                │                   │",
            "└──────┴────────────────────────────────────────────┴───────────────────┘",
        ],
        steals=[
            Steal("Google Drive", "Flat My Drive list",
                  "One folder mentally; sort/filter instead of tree."),
            Steal("Gmail inbox", "State groups (Needs review / Draft)",
                  "Upload intake pipeline is status, not folder path."),
            Steal("Home table grammar", "Title + summary + pills",
                  "Consistent browse language across Lab and My."),
        ],
        flows=[
            "Import → lands in Draft → scan → Needs review → Ready.",
            "No folder navigation for personal files.",
        ],
        acceptance=[
            "No folder rail; no breadcrumbs on My Drive.",
            "Groups: Ready / Needs review / Draft (maps to trust status).",
            "Import CTA visible; same row density as Lab grouped.",
        ],
    ),
    "gdrive-ref": Screen(
        id="gdrive-ref",
        title="REFERENCE — what Google Drive actually does (why no inner folder tree)",
        wireframe=[
            "  GOOGLE DRIVE (simplified)",
            "",
            "  LEFT SIDEBAR          MAIN CANVAS (only navigation surface)",
            "  ─────────────         ─────────────────────────────────────",
            "  Home                  [My Drive ▾]  [sort] [view] [info]",
            "  My Drive              > Research  > 2026              ← breadcrumb ONLY when nested",
            "  Shared drives         ┌────────────────────────────────┐",
            "  Recent                │ Name          Owner    Modified │",
            "  Starred               │ Q1_notes.doc  me       Mar 1   │",
            "  …                     │ dataset.csv   me       Feb 28  │",
            "                        └────────────────────────────────┘",
            "",
            "  KEY: sidebar = switch CONTEXT (My / Shared / Recent)",
            "       main    = ONE list for current folder",
            "       NO second folder tree column inside main",
            "",
            "  OUR MISTAKE: Lab/My add Explorer tree INSIDE main while",
            "  sidebar already says Lab Drive / My Drive.",
        ],
        steals=[
            Steal("Google Drive", "Sidebar for roots, main for files",
                  "We already have sidebar — inner tree duplicates it."),
            Steal("Google Drive", "Breadcrumb only when drilled in",
                  "Top-level Lab/My should not show breadcrumb row."),
        ],
        flows=["Match this: Research Drive sidebar = Drive sidebar."],
        acceptance=["Inner folder rail removed from Lab and My."],
    ),
    "dataset": Screen(
        id="dataset",
        title="DATASET WORKSPACE — preview, schema, query",
        wireframe=[
            "├ NAV ─┬─ MAIN ─────────────────────────────┬─ INSPECTOR ───────┤",
            "│      │ Lab Drive / CoinGecko…    [Back]    │ Details (pinned)  │",
            "│      │ Historical crypto prices…             │ same dataset      │",
            "│      │ [Overview][Preview][Schema][Query]  │                   │",
            "│      │ ┌─ Preview (8 rows) ────────────────┐ │ [Source tab for   │",
            "│      │ │ date │ symbol │ price │ …        │ │  procure only]    │",
            "│      │ └───────────────────────────────────┘ │                   │",
            "│      │ Query: limit 100  [Run] [Ask in Src] │                   │",
            "└──────┴───────────────────────────────────────┴───────────────────┘",
        ],
        steals=[
            Steal("BigQuery / Snowflake", "Preview sample + schema tabs",
                  "Trust requires seeing columns before research use."),
            Steal("Databricks notebook adjacency", "Query tab",
                  "Registry-backed `/query/{id}` already exists."),
            Steal("—", "Main canvas owns depth",
                  "Rail stays summary; workspace is where work happens."),
        ],
        flows=["Use (deep): Open → Preview → Schema → Query."],
        acceptance=[
            "Overview shows recommended_use + limitations.",
            "Preview loads from live API.",
        ],
    ),
    "discover": Screen(
        id="discover",
        title="DISCOVER — external catalog (not in library yet)",
        wireframe=[
            "├ NAV ─┬─ MAIN ─────────────────────────────┬─ INSPECTOR ───────┤",
            "│  Home│ Discover                              │ [Source*]         │",
            "│ ●Disc│ [Search topic…………………] [Search]       │                   │",
            "│      │ [All][In library][Catalog][External]  │  Acquire helper   │",
            "│      │ 12 results                            │  (chat optional)  │",
            "│      │ ┌─────────────────────────────────────┐ │                   │",
            "│      │ │ Taiwan equity panel · Catalog ·2023 │ │                   │",
            "│      │ │                        [Add] [Ask]  │ │                   │",
            "│      │ └─────────────────────────────────────┘ │                   │",
            "│      │ No close match? [Ask to search web]     │                   │",
            "└──────┴───────────────────────────────────────┴───────────────────┘",
        ],
        steals=[
            Steal("Google Dataset Search", "Separate discover mode",
                  "External search ≠ browsing owned files."),
            Steal("E-commerce faceted search", "Source filter chips",
                  "Catalog vs external vs already in library."),
            Steal("Gemini in Drive", "Source rail on discover",
                  "Acquire context is appropriate here."),
        ],
        flows=["Find external: Discover → filter → Add / Source."],
        acceptance=["Clearly labeled outside library.", "Index miss shows web fallback."],
    ),
    "source": Screen(
        id="source",
        title="SOURCE TAB — procurement chat (opt-in only)",
        wireframe=[
            "├ NAV ─┬─ MAIN (unchanged behind) ────────────┬─ INSPECTOR ───────┤",
            "│      │                                       │ [Details][Source*]│",
            "│      │                                       │ Source data       │",
            "│      │                                       │ ───────────────── │",
            "│      │                                       │ User: Taiwan eq…  │",
            "│      │                                       │ Agent: 3 candidates│",
            "│      │                                       │ ┌─ #1 DataCite ─┐ │",
            "│      │                                       │ │ trust · Add    │ │",
            "│      │                                       │ └───────────────┘ │",
            "│      │                                       │ [composer………]   │",
            "│      │                                       │ [Send]            │",
            "└──────┴───────────────────────────────────────┴───────────────────┘",
        ],
        steals=[
            Steal("ChatGPT / Claude", "Thread + tool outcomes",
                  "ProcurementAgent already returns candidates/jobs."),
            Steal("Gemini side panel", "Contextual copilot",
                  "Panel opens on demand, not on every screen."),
            Steal("GitHub PR review", "Compare picks → table",
                  "Existing compare flow for candidates."),
        ],
        flows=["Acquire: Source → candidates → approve job → Activity."],
        acceptance=[
            "Never default on Home/Lab/My.",
            "Scope chip when dataset selected (@name).",
        ],
    ),
    "activity": Screen(
        id="activity",
        title="ACTIVITY — jobs & sync (async pipeline)",
        wireframe=[
            "├ NAV ─┬─ MAIN ─────────────────────────────┬─ (no inspector) ──┤",
            "│ ●Act │ Activity                              │                   │",
            "│      │ Background imports, updates, sync     │                   │",
            "│      │ Running now                           │                   │",
            "│      │ ┌─────────────────────────────────────┐ │                   │",
            "│      │ │ GDELT shard refresh      RUNNING 42%│ │                   │",
            "│      │ │ DataCite collect #8821   PENDING    │ │                   │",
            "│      │ └─────────────────────────────────────┘ │                   │",
            "│      │ Storage: Vault · Cache · Desk           │                   │",
            "└──────┴───────────────────────────────────────┴───────────────────┘",
        ],
        steals=[
            Steal("Linear / GitHub Actions", "Compact status list",
                  "Procurement is async; users need visibility not chat."),
            Steal("Drive sync indicator", "Storage tier strip",
                  "desk.storage_tiers in /health — ops truth."),
        ],
        flows=["Track: after collect, user checks Activity."],
        acceptance=["Pending approval count in nav badge.", "No chat rail."],
    ),
}

MATRIX_ROWS = [
    ("3-column shell", "Google Drive", "Nav / list / inspector", "Faculty file mental model"),
    ("Inspector on select", "Drive, macOS Finder", "Details tab default", "Metadata without page churn"),
    ("Smart procure bar", "Gemini in Drive", "Compose + chips on Home/Lab", "AI sourcing without chat-as-home"),
    ("Typed catalog rows", "Snowflake, BigQuery", "Kind + summary + status", "Registry has backend + availability"),
    ("Schema + preview tabs", "Databricks Unity", "Dataset workspace", "Research requires column trust"),
    ("Faceted discover", "Dataset Search, e-commerce", "Filter chips", "Catalog vs external vs owned"),
    ("Contextual AI panel", "Gemini in Drive", "Source tab only", "Procure is episodic (Option B)"),
    ("Async job feed", "Linear, GitHub Actions", "Activity view", "collect → promote pipeline"),
    ("List not cards", "Notion DB table view", "Featured table on Home", "Density; no faux marketing"),
    ("Light browse surfaces", "Drive, Notion, HF hub", "Professor default theme", "Dark = ops/Activity only"),
    ("—", "ChatGPT alone", "NOT default UI", "We have registry + jobs + promotion"),
    ("—", "Generic dark SaaS", "NOT goal", "Teal-on-black ops console"),
]

COMPARE_ROWS = [
    ("Primary job", "Store & share files", "Govern enterprise tables", "Browse lab registry + acquire"),
    ("Default screen", "My Drive folder", "Worksheets / catalog", "Library table"),
    ("AI placement", "Gemini optional", "Copilot in places", "Source tab opt-in"),
    ("Deep use", "Open in Docs/Sheets", "SQL + lineage", "Preview / Schema / Query"),
    ("Missing data", "Search Drive", "Request access workflow", "Discover + procure agent"),
    ("Async work", "Sync icon", "Tasks / pipelines", "Activity + job queue"),
    ("Our gap vs best", "Polish + sharing", "Scale + governance", "Catalog teaching density + inspector polish"),
]


def print_identity() -> None:
    w = term_width()
    print("\n" + box("VISUAL IDENTITY — Research Drive (CLI preview)", [
        "Product: faculty card catalog + procure flywheel (not chat app, not ops console)",
        "Canonical: light browse · dark ops · honest pipeline · Drive muscle memory",
        "Doc: docs/RESEARCH_DRIVE_UI_V2.md · tokens: src/drive-visual.css (to split → tokens.css)",
    ], w))
    print("""
  METAPHOR
    Reading room + card catalog + status board (platform_status OK/WARN/FAIL)

  TYPOGRAPHY
    ┌──────────────────┬─────────────────────────────────────────────┐
    │ Page titles      │ Newsreader (serif) — Home, Drive, Discover  │
    │ UI / tables      │ IBM Plex Sans — nav, rows, buttons          │
    │ Jobs / schema    │ JetBrains Mono — pills, %, query snippets   │
    └──────────────────┴─────────────────────────────────────────────┘

  COLOR SEMANTICS (one meaning per hue — do not mix accents on same row)
    █ copper  #d4a574  lab-held · pinned · vault paths · RD mark
    █ cyan    #3db8d4  queryable · live link · primary action
    █ green   #6ee7a8  STORED · verified · ready to analyze
    █ amber   #e8c468  jobs · pending · needs review
    █ red     #f4a4a4  failed · blocked

  THEME
    ┌─────────────────────┬──────────────────────────────────────────┐
    │ LIGHT (default)     │ Home · Drive · Discover · Dataset        │
    │ #f7f9fc bg          │ Steal: Google Drive, Notion, HF hub      │
    ├─────────────────────┼──────────────────────────────────────────┤
    │ DARK (ops)          │ Activity · admin · optional night mode   │
    │ #070a0e bg          │ Steal: Linear density, CLI honesty     │
    └─────────────────────┴──────────────────────────────────────────┘

  CURRENT GAP (why UI feels wrong)
    • styles.css = light Drive    vs    drive-visual.css = dark terminal
    • Favicon still Google blue #1f65d8 — conflicts with copper/cyan system
    • Discover looks designed; Home/Drive look like a different product

  COMPETITOR VISUAL STEALS
    Google Drive     3-column shell, light list, selection → inspector
    Hugging Face     Discover cards; dataset Overview/Files/Schema tabs
    Gemini in Drive  compose bar + chips on browse (not chat-as-home)
    Snowflake/BQ     status pills on typed rows
    platform_status  sparse OK/WARN/FAIL — no fake progress bars

  AVOID
    ✗ ChatGPT wall-of-text as primary chrome
    ✗ Teal glow + copper rail + green pills on same screen
    ✗ Internal / Procure / Tools nav labels (operator taxonomy)
    ✗ Fake pipeline steppers (hardcoded 15%)

  COMMANDS
    python3 scripts/rd_desk_blueprint_preview.py -s home-pulse
    python3 scripts/rd_desk_blueprint_preview.py --matrix
    python3 scripts/rd_desk_blueprint_preview.py --compare
    python3 scripts/rd_desk_blueprint_preview.py --flows
""")


def print_steals(screen: Screen) -> None:
    print("\n  STOLEN FROM (reasoned):\n")
    for s in screen.steals:
        print(f"  • {s.platform}: {s.pattern}")
        print(f"    → {s.why_us}")
        if s.skip:
            print(f"    ✗ skip: {s.skip}")
        print()


def print_screen(screen: Screen) -> None:
    w = term_width()
    print()
    print(box(screen.title, [], w))
    print()
    for line in screen.wireframe:
        print(line)
    if screen.flows:
        print("\n  USER FLOW:")
        for f in screen.flows:
            print(f"    • {f}")
    print_steals(screen)
    if screen.acceptance:
        print("  ACCEPTANCE:")
        for a in screen.acceptance:
            print(f"    ☐ {a}")
    print()


def print_matrix() -> None:
    print("\n" + box("INDUSTRY STEAL MATRIX", [], term_width()))
    print()
    for pat, plat, use, why in MATRIX_ROWS:
        print(f"  [{pat}]")
        print(f"    from:  {plat}")
        print(f"    use:   {use}")
        print(f"    why:   {why}")
        print()
    print("  Full doc: docs/RESEARCH_DRIVE_UI_BLUEPRINT.md\n")


def print_compare() -> None:
    print("\n" + box("VS INDUSTRY (honest positioning)", [], term_width()))
    print()
    for d, drive, snow, rd in COMPARE_ROWS:
        print(f"  {d}")
        print(f"    Google Drive:           {drive}")
        print(f"    Snowflake/Databricks:   {snow}")
        print(f"    Research Drive (target): {rd}")
        print()


def print_flows() -> None:
    flows = [
        ("1. ORIENT", "Home → smart procure bar + featured table → holdings + how to source"),
        ("2. USE (light)", "Select row → Details chips / toolbar → Open if needed"),
        ("3. USE (deep)", "Dataset workspace → Preview → Schema → Query"),
        ("4. ACQUIRE (ambient)", "Smart procure bar or Details chip → Source tab → candidates"),
        ("5. FIND EXTERNAL", "Discover → filter → Add or Source with query"),
        ("6. ACQUIRE (async)", "Approve job → Activity → promoted row in Lab"),
    ]
    print("\n" + box("CORE FLOWS (blueprint)", [f[1] for f in flows], term_width()))
    for name, desc in flows:
        print(f"\n  {name}\n    {desc}")
    print()


def print_browse_compare() -> None:
    w = term_width()
    print("\n" + box("BROWSE UI DECISION — folder tree vs grouped list", [
        "Review before any Lab/My React work.",
        "Recommended: lab-grouped + my-flat (see wireframes below).",
    ], w))
    print("""
  ┌────────────────────────────┬────────────────────────────┐
  │ CURRENT (tree)             │ PROPOSED (grouped / flat)  │
  ├────────────────────────────┼────────────────────────────┤
  │ Nav + folder rail + crumbs │ Nav + one full-width list  │
  │ Explorer split pane        │ Section headers = folders  │
  │ 3 ways to orient           │ 1 scroll to understand     │
  │ Feels cramped              │ Drive spacing (52px rows)  │
  │ GDrive does NOT do this    │ Matches GDrive main canvas │
  └────────────────────────────┴────────────────────────────┘

  DATA MODEL: unchanged — group headers = existing folder IDs
              (research_panels, procured, connections, …)

  COMMANDS:
    python3 scripts/rd_desk_blueprint_preview.py -s gdrive-ref
    python3 scripts/rd_desk_blueprint_preview.py -s lab        # current ✗
    python3 scripts/rd_desk_blueprint_preview.py -s lab-grouped # target ✓
    python3 scripts/rd_desk_blueprint_preview.py -s my-tree    # current ✗
    python3 scripts/rd_desk_blueprint_preview.py -s my-flat    # target ✓
""")
    for sid in ("gdrive-ref", "lab", "lab-grouped", "my-tree", "my-flat"):
        print_screen(SCREENS[sid])


def interactive() -> None:
    keys = list(SCREENS.keys())
    help_text = (
        "Screens: " + ", ".join(keys)
        + " | home-pulse | identity | browse | matrix | compare | flows | all | quit"
    )
    print(box("Research Drive — CLI blueprint preview", [
        "Design authority before more React/CSS.",
        "Doc: docs/RESEARCH_DRIVE_UI_BLUEPRINT.md",
        help_text,
    ], term_width()))

    while True:
        try:
            cmd = input("\nblueprint> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not cmd:
            continue
        if cmd in ("q", "quit", "exit"):
            break
        if cmd == "help":
            print(help_text)
            continue
        if cmd == "matrix":
            print_matrix()
            continue
        if cmd == "compare":
            print_compare()
            continue
        if cmd == "flows":
            print_flows()
            continue
        if cmd in ("browse", "browse-compare", "folders"):
            print_browse_compare()
            continue
        if cmd == "all":
            for sid in keys:
                print_screen(SCREENS[sid])
            continue
        if cmd in SCREENS:
            print_screen(SCREENS[cmd])
            continue
        # aliases
        aliases = {
            "h": "home",
            "sel": "home-selected",
            "selected": "home-selected",
            "l": "lab-grouped",
            "lab": "lab-grouped",
            "lab-new": "lab-grouped",
            "lab-old": "lab",
            "lab-tree": "lab",
            "my": "my-flat",
            "my-new": "my-flat",
            "my-old": "my-tree",
            "my-tree": "my-tree",
            "gdrive": "gdrive-ref",
            "d": "dataset",
            "disc": "discover",
            "src": "source",
            "a": "activity",
        }
        if cmd in aliases:
            print_screen(SCREENS[aliases[cmd]])
            continue
        print(f"Unknown: {cmd}. Try: {help_text}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Research Drive CLI blueprint preview")
    parser.add_argument("--screen", "-s", choices=list(SCREENS.keys()) + ["all"], help="Show one screen")
    parser.add_argument("--matrix", action="store_true", help="Industry steal matrix")
    parser.add_argument("--compare", action="store_true", help="Vs Drive / warehouse")
    parser.add_argument("--flows", action="store_true", help="Core user flows")
    parser.add_argument(
        "--browse-compare",
        action="store_true",
        help="Folder tree vs grouped list debate (Lab + My + GDrive ref)",
    )
    args = parser.parse_args()

    if args.matrix:
        print_matrix()
        return 0
    if args.compare:
        print_compare()
        return 0
    if args.flows:
        print_flows()
        return 0
    if args.browse_compare:
        print_browse_compare()
        return 0
    if args.screen:
        if args.screen == "all":
            for sid in SCREENS:
                print_screen(SCREENS[sid])
        else:
            print_screen(SCREENS[args.screen])
        return 0

    interactive()
    return 0


if __name__ == "__main__":
    sys.exit(main())
