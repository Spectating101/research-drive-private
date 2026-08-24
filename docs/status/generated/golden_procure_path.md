# Golden procure path — automated evidence

Captured: 2026-07-08T15:54:51.468971Z
Faculty: drkong@saturn.yzu.edu.tw
Dataset: `sec_company_tickers` · execute=False

## Flow

```text
Discover search → probe public source → yzu_submit_job (queue task)
  → worker completes → registry promote → GDrive finalize → query_dataset
  → Discover finds in-lab holding
```

## Steps

### PASS — `health`
- **composer_configured:** True
- **registry_count:** 159
- **jobs:** {"pending_approval": 7, "queued": 0, "running": 0, "completed": 308, "failed": 85, "cancelled": 100}
- **gdrive:** {"rclone_installed": true, "remotes": ["gdrive"], "gdrive_remote": true, "drive_root": "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data", "ready": true, "drive_list_ok": true, "drive_list_error": ""}

### PASS — `faculty_profile`
- **name_en:** Kong, De-Rong

### PASS — `discover_search`
- **query:** SEC EDGAR company tickers CIK mapping
- **total:** 12
- **rows:** 12

### PASS — `discover_probe`
- **url:** https://www.sec.gov/files/company_tickers.json
- **connector_id:** src_ace4a0fb8e9e
- **summary:** direct_file source; 0 downloadable links detected; recommendation: download_sample_then_archive

### PASS — `submit_collect_job`
- **skipped:** True
- **reason:** dry-run

### PASS — `job_completed`
- **skipped:** True

### PASS — `registry_query`
- **skipped:** True

### PASS — `gdrive_verify`
- **skipped:** True

### PASS — `discover_in_lab`
- **skipped:** True

**Overall:** PASS
