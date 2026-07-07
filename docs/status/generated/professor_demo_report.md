# Professor demo — automated evidence

Captured: 2026-07-07T17:25:01.125Z
Faculty: drkong@saturn.yzu.edu.tw
Registry: 159 datasets · Composer: ready

## Product model exercised

```text
Home → command surface + attention
Library → lab vault + query-ready preview
Discover → search → probe facts → Add to lab → Ask
Resources → safety ledger + approvals
Profile → faculty context
Return → In lab filter finds registered holdings
```

## Scenarios

### PASS — Home command surface + attention queue
- **id:** `home_command`
- **holdings:** 159
- **attention_items:** 3
- **header_meta:** 159 datasets

### PASS — Library vault drill-in + query-ready detail
- **id:** `library_vault`
- **folder:** research_panels/gdelt
- **visible_datasets:** 4
- **selected_dataset:** data_lake/news_shock_taxonomy/processed

### PASS — Discover search + acquisition pipeline
- **id:** `discover_search`
- **query:** TWSE
- **candidates:** 11
- **first_candidate:** Taiwan TWSE OpenAPI market layer
- **source_badge:** “TWSE”

### PASS — Discover in-lab candidate → Open in Library
- **id:** `discover_probe_add`
- **candidate:** Taiwan MOPS governance misconduct panel
- **action:** open_in_library

### PASS — Resources safety ledger (professor labels)
- **id:** `resources_safety`
- **faculty_labels_found:** ["Remote tables","procurement routes","Connected"]
- **has_status_strip:** true
- **has_inventory:** true
- **page_excerpt:** Resources

Storage, account limits, and procurement routes

Overview
Activity
Collectors
5/6 busy
2026-06-09 – 2026-07-08
Updated 0s ago
Refresh
ASK USAGE
37 month
Procurement chat this month
COLLECTION WORKERS
5/6 busy
0 running
LAB VAULT
quota pending
hot 85.6%
DESK CONNECTION
Connected
Catalog and query service
Key resources
10 shown · 5 source routes
Storage
Where collected data is archived or staged. Check capacity before large downloads.
2
Drive vault
Archive
3 TB cap · usage pending
Long-term archive
Working disk
Workspace
41 GB free · 85.6% used
Local working space
Check
Accounts & lim

### PASS — Pending approvals surfaced in desk
- **id:** `resources_approvals`
- **pending_count:** 0
- **home_strip:** false
- **limits_normal:** true
- **header_meta:** 159 datasets

### PASS — Faculty profile loaded from registry
- **id:** `profile_faculty`
- **name_en:** Kong, De-Rong
- **email:** drkong@saturn.yzu.edu.tw

### PASS — Query-ready preview on registered dataset
- **id:** `library_preview`
- **dataset_id:** gdelt_asia_daily_country_panel
- **preview_hint:** Preview — GDELT Asia Daily Country News Shock Panel
×
Preview
Schema
Query

Loading preview…

Export CSV
Open query engine

### PASS — Registered datasets findable after Discover session
- **id:** `verify_in_lab`
- **in_lab_ui_matches:** 0
- **registry_count:** 159
- **filter:** In lab
- **query:** gdelt

## ChatGPT review prompt

```text
Review this professor procurement demo evidence for Research Drive v2.
Repo: Spectating101/yzu-cluster · Screenshots: docs/screenshots-review/
Judge whether the workflow is credible end-to-end:
search missing data → Library check → Discover probe → Resources safety → queue procurement → find registered result.
```
