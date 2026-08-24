# Storage Inventory

**Measured:** 2026-08-03. All figures are observed, not hinted — sizes come from
`rclone size` / `du` at that date, not from `drive_size_hint` fields.

Three storages hold research data. They are not peers.

| storage | role | capacity | authority |
|---|---|---|---|
| `gdrive:` | **canonical vault** | 5 TiB, 769 GiB used, 4.24 TiB free | owned by us |
| local `/mnt/research-data` | working set / staging | 1.9 TiB, 727 GiB free | ephemeral per `legacy_local_path_role` |
| `dropbox:` | **delivery surface only** | 2 GiB Basic, 160 MiB free | **her folder — we are `editor`, not owner** |

Dropbox is not storage. `Chris/` is a shared folder owned by the professor
(`access_type: editor`, `shared_folder_id: 14111655027`), it counts against our
2 GiB Basic quota, and she can unshare it at any time. Nothing may exist there
as its only copy.

---

## 1. Vault — `collection/` partitions

Canonical root: `gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data`

Verifier: `python3 scripts/ops/verify_gdrive_vault.py` — reports layout ready,
all 9 core domains present, **1 legacy root still to migrate (`sec`)**.

Reconciled local vs vault, 25 partitions:

| partition | local | vault | note |
|---|---|---|---|
| `news.gdelt-asia` | 478 GiB | 157 GiB | **large unexplained delta** |
| `news.gdelt-expanded` | 221 GiB | 221 GiB | matched |
| `markets.crypto-landscape` | 12 GiB | 7.4 GiB | local ahead |
| `derived.research-panels` | 2 GiB | 1.5 GiB | local ahead |
| `markets.nft-opensea` | 538 KiB | 538 KiB | matched (metadata only) |
| `reference.sec-edgar` | 173 MiB | 247 MiB | **vault ahead** — local pruned |

Present locally, **absent from vault** — all licensed vendor data, likely
deliberately:

| partition | local size |
|---|---|
| `reference.crsp-moveit` | 14 GiB |
| `reference.refinitiv-backfill` | 55 MiB |
| `reference.compustat-capitaliq` | 212 B (empty) |

Do not sync these without a licensing decision. CRSP/MOVEit, LSEG/Refinitiv and
Compustat/Capital IQ terms generally prohibit redistribution, and the vault is
share-linked to the professor.

## 2. Vault — deliverables, **outside the partition scheme**

80.17 GiB across 61,750 files, in four unrelated roots. None registered in
`collection_partitions.json`.

| root | contents |
|---|---|
| `molina_workbench/Sharpe-Renaissance-deliverables/` | **80.17 GiB / 61,750 files** — the real archive |
| `molina_workbench/Sharpe-Renaissance-trash-rescue-20260521/…-deliverables/` | 11 large zips, incl. the sole copy of Part 2 |
| `molina_deliverables/Sharpe-Renaissance-deliverables/` | 2 small files |
| `molina_workbench/…-raw_archives/deliverables/_manifests_only_20260513/` | `.sha256` stubs only |

Largest members of the 80 GiB tree:

| folder | size | files |
|---|---|---|
| `deliverables-opensea` | 51.94 GiB | 959 |
| `professor_zip_folder_supducks_split_50` | 10.55 GiB | 204 |
| `professor_zip_folder_supducks_250` | 10.55 GiB | 44 |
| `professor_zip_folder_mayc_250` | 5.15 GiB | 82 |
| `professor_zip_folder_clone_x_tail_split_18751_19764` | 0.85 GiB | 24 |
| `opensea_metadata_sidecars_20260518_full` | 0.30 GiB | 59,527 |

`supducks_250` and `supducks_split_50` are identical totals at different chunk
granularity — almost certainly the same payload twice, 10.55 GiB recoverable.

The canonical copy of `professor_crypto_bundle_continuation.zip` lives in a
folder named **trash-rescue**. That is the accident to fix first.

## 3. Dropbox — `Chris/RA`, 1,134 files, 847.7 MiB

| item | size | copies elsewhere |
|---|---|---|
| `professor_crypto_bundle_continuation.zip` | 493.04 MiB | vault (byte-exact) |
| `professor_crypto_bundle/per_coin/*` (1,063) | 168.63 MiB | vault (2026-08-03) |
| `professor_crypto_bundle.zip` | 106.12 MiB | vault (2026-08-03) — **was sole-copy** |
| `professor_crypto_bundle/professor_crypto_panel.csv` | 74.30 MiB | vault — **damaged, see §5** |
| `Investing.com/2024/*.csv` (13) | 3.83 MiB | local + vault |
| `Cryptocurrencies 2025.xlsx` | 1.69 MiB | local + vault |
| `OpenSea/CryptoPunks/*` (51) | 0.06 MiB | vault zip |
| `OpenSea/List of NFT Collections.xlsx` | 0.02 MiB | vault (2026-08-03) — **was sole-copy** |

The remaining ~1 GiB of the 1.843 GiB used sits in her non-RA folders
(`Anchoring bias`, `Draft`, `Invisible Ledger`, `References`, `Stata`,
`Thesis Topics`). Out of scope.

## 4. Health checks run 2026-08-03

| check | result |
|---|---|
| CoinGecko archive `PRAGMA quick_check` | **ok** — no corruption, 486,186 pages |
| CoinGecko archive `foreign_key_check` | no violations |
| Excel row-cap sweep, 343 CSV/TSV > 1 MB, all local roots | **0 affected** |
| `professor_crypto_bundle.zip` `unzip -t` | no errors, 1,066 entries |
| Vault layout verifier | pass, 1 legacy root |

## 5. Known defect — Excel truncation

`professor_crypto_bundle/professor_crypto_panel.csv` **in Dropbox** was opened in
Excel and saved back:

```
zip (authoritative) : 2,244,846 rows   1,062 coins   ends zmine 2026-04-15
Dropbox extracted   : 1,048,576 rows     497 coins   ends iotex 2025-02-18
```

1,048,576 = 2^20, Excel's hard row limit. **53% of coins lost.** The other 1,065
files in that folder are byte-identical to the zip.

If the professor has analysed from that path rather than the zip, her results
cover 497 of 1,062 coins. This is a research-integrity issue, not housekeeping.

The sweep in §4 confirms no other file in any storage shows this signature.

## 6. Copy count — what is sole-copy

| dataset | copies | where |
|---|---|---|
| CoinGecko archive DB (11.4M rows) | 2 | local + vault |
| `professor_crypto_bundle.zip` (Part 1) | 2 | vault + Dropbox (as of 2026-08-03) |
| `professor_crypto_bundle_continuation.zip` (Part 2) | 2 | vault + Dropbox |
| OpenSea BAYC | 2 | `OpenSea_RA` + rescue zip |
| OpenSea MAYC | 2 | `OpenSea_RA` + `professor_zip_folder_mayc_250` |
| OpenSea CryptoPunks | 3 | local images + 2 rescue zips |
| Her source files | 3 | Dropbox + local + vault |
| GDELT delta (~320 GiB) | **1** | local only, unresolved |

## 7. Open items

1. `rclone check` verification of the 2026-08-03 upload — **pending**.
2. sha256 verification of 7 vault archives that ship digests but were never
   checked — **in progress**.
3. GDELT 478 vs 157 GiB — needs `rclone check`, not a size comparison.
4. Deliverables tree unregistered; canonical Part 2 in `trash-rescue`.
5. `partition_sync.json` is `mode: backfill_only`, `scheduled: false` — nothing
   periodically reconciles local against vault. Root cause of the drift above.
6. Legacy `sec` root still present at vault top level.
