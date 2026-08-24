#!/usr/bin/env python3
"""Build Constraint Market Collateral Capacity Study v1 (internal licensed asset).

CRSP STOCK_25i SI ASCII (sfz_*) is the price/volume/shares/delist spine.
Refinitiv S&P 500 PIT + ESG snapshot supply membership and optional overlays.

Outputs (under data/datasets/constraint_market_capacity_v1/):
  constraint_market_capacity_v1.parquet
  constraint_market_capacity_v1_schema.json
  constraint_market_capacity_v1_manifest.json
  constraint_market_capacity_v1_methods.md

Heavy I/O lands on Transcend work cache; deliverables land in the repo dataset tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
WORK = Path(
    "/media/phyrexian/Transcend/sharpe-renaissance/data_lake/crsp/constraint_v1_work"
)
RAW_WORK = WORK / "raw"
ZIP_DEFAULT = (
    REPO
    / "data_lake/crsp/raw/stock_25i_si_ascii_annual/siz202412_ascii.zip"
)
SPX_PIT_DEFAULT = Path(
    "/media/phyrexian/Transcend/sharpe-renaissance/data_lake/refinitiv_backfill/"
    "2026-07-06-complete/processed/index_membership_pit.parquet"
)
ESG_DEFAULT = Path(
    "/media/phyrexian/Transcend/sharpe-renaissance/data_lake/refinitiv_backfill/"
    "2026-07-06-complete/processed/esg_snapshot.parquet"
)
OUT_DEFAULT = REPO / "data/datasets/constraint_market_capacity_v1"

START = pd.Timestamp("2018-01-01")
TARGET_UNIVERSE_MIN = 100
TARGET_UNIVERSE_MAX = 500
TARGET_UNIVERSE_PREF = 350
MIN_COVERAGE = 0.95
SQRT_252 = math.sqrt(252.0)

# CRSP Flat File Format 1.0 (SIZ) field maps — frozen for methods/schema.
HDR_COLS = [
    "permno",
    "cusip",
    "cusip9",
    "htick",
    "permco",
    "compno",
    "issuno",
    "hexcd",
    "hsiccd",
    "begdt",
    "enddt",
    "hdlstcd",
    "hcomnam",
    "htsymbol",
    "hsnaics",
    "hshrcd",
    "hprimexch",
    "htrdstat",
    "hsecstat",
]
NAM_COLS = [
    "permno",
    "namedt",
    "nameenddt",
    "ncusip",
    "ncusip9",
    "ticker",
    "comnam",
    "shrcls",
    "shrcd",
    "exchcd",
    "siccd",
    "tsymbol",
    "snaics",
    "primexch",
    "trdstat",
    "secstat",
]
DEL_COLS = [
    "permno",
    "dlstdt",
    "dlstcd",
    "nwperm",
    "nwcomp",
    "nextdt",
    "dlprc",
    "dlpdt",
    "dlamt",
    "dlret",
    "dlretx",
]
SHR_COLS = ["permno", "shrsdt", "shrsenddt", "shrout", "shrflg"]
DP_COLS = ["permno", "caldt", "prc", "ret", "retx", "tcap", "vol"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _to_float(x: str) -> float:
    x = (x or "").strip()
    if not x:
        return np.nan
    try:
        return float(x)
    except ValueError:
        return np.nan


def _to_int(x: str) -> int | None:
    x = (x or "").strip()
    if not x:
        return None
    try:
        return int(float(x))
    except ValueError:
        return None


def _parse_pipe_file(
    path: Path,
    colnames: list[str],
    *,
    dtypes: dict | None = None,
) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        sep="|",
        header=None,
        names=colnames,
        dtype=str,
        engine="c",
        low_memory=False,
    )
    return df


def load_master_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    hdr = _parse_pipe_file(raw_dir / "sfz_hdr.dat", HDR_COLS)
    for c in ("permno", "hexcd", "hsiccd", "hdlstcd", "hshrcd", "permco"):
        hdr[c] = pd.to_numeric(hdr[c], errors="coerce")
    hdr["begdt"] = pd.to_datetime(hdr["begdt"], errors="coerce")
    hdr["enddt"] = pd.to_datetime(hdr["enddt"], errors="coerce")
    hdr["htsymbol"] = hdr["htsymbol"].fillna("").astype(str).str.strip().str.upper()
    hdr["hcomnam"] = hdr["hcomnam"].fillna("").astype(str).str.strip()

    nam = _parse_pipe_file(raw_dir / "sfz_nam.dat", NAM_COLS)
    nam["permno"] = pd.to_numeric(nam["permno"], errors="coerce")
    nam["namedt"] = pd.to_datetime(nam["namedt"], errors="coerce")
    nam["nameenddt"] = pd.to_datetime(nam["nameenddt"], errors="coerce")
    nam["shrcd"] = pd.to_numeric(nam["shrcd"], errors="coerce")
    nam["exchcd"] = pd.to_numeric(nam["exchcd"], errors="coerce")
    nam["siccd"] = pd.to_numeric(nam["siccd"], errors="coerce")
    nam["ticker"] = nam["ticker"].fillna("").astype(str).str.strip().str.upper()
    nam["tsymbol"] = nam["tsymbol"].fillna("").astype(str).str.strip().str.upper()

    dele = _parse_pipe_file(raw_dir / "sfz_del.dat", DEL_COLS)
    dele["permno"] = pd.to_numeric(dele["permno"], errors="coerce")
    dele["dlstdt"] = pd.to_datetime(dele["dlstdt"], errors="coerce")
    dele["dlstcd"] = pd.to_numeric(dele["dlstcd"], errors="coerce")
    dele["dlret"] = pd.to_numeric(dele["dlret"], errors="coerce")

    shr = _parse_pipe_file(raw_dir / "sfz_shr.dat", SHR_COLS)
    shr["permno"] = pd.to_numeric(shr["permno"], errors="coerce")
    shr["shrsdt"] = pd.to_datetime(shr["shrsdt"], errors="coerce")
    shr["shrsenddt"] = pd.to_datetime(shr["shrsenddt"], errors="coerce")
    shr["shrout"] = pd.to_numeric(shr["shrout"], errors="coerce")  # thousands

    return {"hdr": hdr, "nam": nam, "del": dele, "shr": shr}


def ric_to_ticker(ric: str) -> str:
    ric = (ric or "").strip().upper()
    if not ric:
        return ""
    # Strip exchange suffix: AAPL.OQ, BRK.B.N, BF.B.N → keep last-but-exchange token carefully
    # Common pattern: SYMBOL.EXCH where EXCH in N, O, OQ, K, A, P, etc.
    m = re.match(r"^([A-Z0-9.\-]+)\.([A-Z]{1,3})$", ric)
    if m:
        return m.group(1)
    return ric.split(".")[0]


def cusip9_to_isin(cusip9: str, country: str = "US") -> str | None:
    """Build ISIN from 9-char CUSIP + ISIN check digit (mod-10 double-add-double)."""
    c = (cusip9 or "").strip().upper()
    if len(c) != 9 or not country:
        return None
    body = f"{country}{c}"
    # Convert letters to numbers (A=10 ... Z=35), then double-add-double from right
    digits: list[int] = []
    for ch in body:
        if ch.isdigit():
            digits.append(int(ch))
        elif "A" <= ch <= "Z":
            n = ord(ch) - 55  # A=10
            digits.extend(divmod(n, 10) if n >= 10 else (n,))
            if n >= 10:
                # divmod returns (1,0) for 10 — need both digits
                pass
        else:
            return None
    # Rebuild properly
    expanded: list[int] = []
    for ch in body:
        if ch.isdigit():
            expanded.append(int(ch))
        else:
            n = ord(ch) - 55
            expanded.extend([n // 10, n % 10] if n >= 10 else [n])
    total = 0
    for i, d in enumerate(reversed(expanded)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check = (10 - (total % 10)) % 10
    return f"{body}{check}"


def build_spx_permno_map(
    nam: pd.DataFrame,
    hdr: pd.DataFrame,
    spx_pit: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Map Refinitiv .SPX PIT RICs to CRSP PERMNOs via ticker history overlap."""
    pit = spx_pit.copy()
    pit["as_of_date"] = pd.to_datetime(pit["as_of_date"], errors="coerce")
    pit = pit[(pit["index_ric"] == ".SPX") & (pit["as_of_date"] >= START)].dropna(
        subset=["as_of_date", "constituent_ric"]
    )
    pit["ticker"] = pit["constituent_ric"].map(ric_to_ticker)
    pit = pit[pit["ticker"] != ""].copy()

    nam2 = nam.dropna(subset=["permno", "namedt", "nameenddt"]).copy()
    nam2["match_sym"] = nam2["tsymbol"].where(nam2["tsymbol"] != "", nam2["ticker"])
    nam2 = nam2[nam2["match_sym"] != ""].copy()
    nam_common = nam2[nam2["shrcd"].isin([10, 11])].copy()
    if nam_common.empty:
        nam_common = nam2

    pairs = (
        pit[["ticker", "as_of_date", "constituent_ric"]]
        .drop_duplicates()
        .dropna(subset=["as_of_date", "ticker"])
        .copy()
    )
    pairs["as_of_date"] = pd.to_datetime(pairs["as_of_date"]).dt.tz_localize(None)
    pairs["ticker"] = pairs["ticker"].astype(str)

    right = nam_common[["match_sym", "namedt", "nameenddt", "permno"]].dropna(
        subset=["namedt", "match_sym"]
    ).copy()
    right["namedt"] = pd.to_datetime(right["namedt"]).dt.tz_localize(None)
    right["nameenddt"] = pd.to_datetime(right["nameenddt"]).dt.tz_localize(None)
    right["match_sym"] = right["match_sym"].astype(str)

    right_by = {sym: g.sort_values("namedt") for sym, g in right.groupby("match_sym", sort=False)}
    pieces: list[pd.DataFrame] = []
    unmatched_tickers = 0
    for ticker, left_g in pairs.groupby("ticker", sort=False):
        rg = right_by.get(ticker)
        if rg is None or rg.empty:
            unmatched_tickers += 1
            tmp = left_g.copy()
            tmp["permno"] = np.nan
            tmp["namedt"] = pd.NaT
            tmp["nameenddt"] = pd.NaT
            tmp["matched"] = False
            pieces.append(tmp)
            continue
        lg = left_g.sort_values("as_of_date")
        m = pd.merge_asof(
            lg,
            rg.drop(columns=["match_sym"], errors="ignore"),
            left_on="as_of_date",
            right_on="namedt",
            direction="backward",
        )
        in_window = m["nameenddt"].isna() | (m["as_of_date"] <= m["nameenddt"])
        m["matched"] = m["permno"].notna() & in_window
        m.loc[m["permno"].notna() & ~m["matched"], "matched"] = True
        pieces.append(m)
    merged = pd.concat(pieces, ignore_index=True)

    matched = merged[merged["matched"]].copy()
    def _mode_or_first(s: pd.Series):
        s = s.dropna()
        if s.empty:
            return None
        vc = s.value_counts()
        return vc.index[0] if len(vc) else s.iloc[0]

    ric_by_permno = matched.groupby("permno")["constituent_ric"].agg(_mode_or_first).to_dict()
    ticker_by_permno = matched.groupby("permno")["ticker"].agg(_mode_or_first).to_dict()
    candidate_permnos = sorted({int(p) for p in matched["permno"].dropna().unique()})

    hdr_idx = hdr.drop_duplicates("permno").set_index("permno")
    nam_common_permnos = set(
        int(x) for x in nam.loc[nam["shrcd"].isin([10, 11]), "permno"].dropna().unique()
    )
    common_permnos = []
    for p in candidate_permnos:
        if p not in hdr_idx.index:
            common_permnos.append(p)
            continue
        shrcd = hdr_idx.loc[p, "hshrcd"]
        if pd.isna(shrcd) or int(shrcd) in (10, 11) or p in nam_common_permnos:
            common_permnos.append(p)

    stats = {
        "spx_pit_rows_2018plus": int(len(pit)),
        "spx_unique_rics": int(pit["constituent_ric"].nunique()),
        "map_pair_rows": int(len(merged)),
        "map_matched_pairs": int(merged["matched"].sum()),
        "map_unmatched_pairs": int((~merged["matched"]).sum()),
        "unmatched_tickers": int(unmatched_tickers),
        "candidate_permnos": len(candidate_permnos),
        "common_share_permnos": len(common_permnos),
        "ric_match_rate_unique": float(
            matched["constituent_ric"].nunique() / max(pit["constituent_ric"].nunique(), 1)
        ),
    }
    return (
        pd.DataFrame(
            {
                "permno": common_permnos,
                "ric": [ric_by_permno.get(p) for p in common_permnos],
                "ticker": [ticker_by_permno.get(p) for p in common_permnos],
            }
        ),
        stats,
    )


def stream_daily_for_permnos(
    zip_path: Path,
    permnos: set[int],
    start: pd.Timestamp,
    out_parquet: Path,
) -> dict:
    """Stream sfz_dp_dly from zip; keep date>=start and permno in set."""
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    member = None
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.filename.endswith("sfz_dp_dly.dat"):
                member = info.filename
                break
        if member is None:
            raise FileNotFoundError("sfz_dp_dly.dat not in zip")

        chunks: list[pd.DataFrame] = []
        chunk_rows: list[list] = []
        n_kept = 0
        n_seen = 0
        start_s = start.strftime("%Y-%m-%d")
        writer_parts: list[Path] = []
        part_i = 0

        def flush():
            nonlocal chunk_rows, part_i, chunks
            if not chunk_rows:
                return
            df = pd.DataFrame(chunk_rows, columns=DP_COLS)
            df["permno"] = df["permno"].astype("int64")
            df["caldt"] = pd.to_datetime(df["caldt"], errors="coerce")
            for c in ("prc", "ret", "retx", "tcap", "vol"):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            part = out_parquet.parent / f"_dp_part_{part_i:03d}.parquet"
            df.to_parquet(part, index=False)
            writer_parts.append(part)
            part_i += 1
            chunk_rows = []

        with zf.open(member) as fh:
            for raw in fh:
                n_seen += 1
                line = raw.decode("latin-1", errors="replace").rstrip("\n")
                if not line:
                    continue
                parts = line.split("|")
                if len(parts) < 7:
                    continue
                caldt = parts[1]
                if caldt < start_s:
                    continue
                try:
                    permno = int(parts[0])
                except ValueError:
                    continue
                if permno not in permnos:
                    continue
                chunk_rows.append(
                    [
                        permno,
                        caldt,
                        parts[2],
                        parts[3],
                        parts[4],
                        parts[5],
                        parts[6],
                    ]
                )
                n_kept += 1
                if len(chunk_rows) >= 250_000:
                    flush()
                    if n_kept % 1_000_000 < 250_000:
                        print(f"  streamed kept={n_kept:,} scanned={n_seen:,}", flush=True)
        flush()

    if not writer_parts:
        raise RuntimeError("No daily rows kept for universe")

    frames = [pd.read_parquet(p) for p in writer_parts]
    daily = pd.concat(frames, ignore_index=True)
    daily = daily.sort_values(["permno", "caldt"]).drop_duplicates(
        ["permno", "caldt"], keep="last"
    )
    daily.to_parquet(out_parquet, index=False)
    for p in writer_parts:
        p.unlink(missing_ok=True)
    return {
        "rows": int(len(daily)),
        "permnos": int(daily["permno"].nunique()),
        "date_min": str(daily["caldt"].min().date()),
        "date_max": str(daily["caldt"].max().date()),
        "lines_scanned": n_seen,
        "rows_kept": n_kept,
    }


def attach_shares_and_delist(
    daily: pd.DataFrame,
    shr: pd.DataFrame,
    dele: pd.DataFrame,
    universe: pd.DataFrame,
    hdr: pd.DataFrame,
) -> pd.DataFrame:
    """Join shares (interval), delist info, and static sector/ticker."""
    # Shares: per-PERMNO merge_asof (global by= is brittle on mixed dtypes)
    daily = daily.copy()
    daily["permno"] = daily["permno"].astype("int64")
    daily["caldt"] = pd.to_datetime(daily["caldt"])
    daily = daily.sort_values(["permno", "caldt"], kind="mergesort")
    shr_u = shr[shr["permno"].isin(set(int(x) for x in universe["permno"]))].copy()
    shr_u["permno"] = shr_u["permno"].astype("int64")
    shr_u["shrsdt"] = pd.to_datetime(shr_u["shrsdt"])
    shr_u = shr_u.rename(columns={"shrout": "shrout_thousands"})
    pieces = []
    shr_by = {p: g.sort_values("shrsdt", kind="mergesort") for p, g in shr_u.groupby("permno", sort=False)}
    for permno, g in daily.groupby("permno", sort=False):
        g = g.sort_values("caldt", kind="mergesort")
        s = shr_by.get(int(permno))
        if s is None or s.empty:
            g = g.copy()
            g["shrout_thousands"] = np.nan
            pieces.append(g)
            continue
        merged = pd.merge_asof(
            g,
            s[["shrsdt", "shrout_thousands"]],
            left_on="caldt",
            right_on="shrsdt",
            direction="backward",
        )
        pieces.append(merged.drop(columns=["shrsdt"], errors="ignore"))
    out = pd.concat(pieces, ignore_index=True)

    # Price abs; market cap from TCAP ($ thousands) preferred
    out["close_price"] = out["prc"].abs()
    out["daily_return"] = out["ret"]
    out["trading_volume"] = out["vol"]
    # TCAP is abs(PRC)*SHROUT (SHROUT in thousands) → thousands of USD
    out["market_cap"] = out["tcap"] * 1000.0
    # Fallback if tcap missing: price * shrout*1000
    miss = out["market_cap"].isna() & out["close_price"].notna() & out["shrout_thousands"].notna()
    out.loc[miss, "market_cap"] = (
        out.loc[miss, "close_price"] * out.loc[miss, "shrout_thousands"] * 1000.0
    )
    out["shares_outstanding"] = out["shrout_thousands"] * 1000.0
    # If shrout missing but tcap+price present
    miss_s = out["shares_outstanding"].isna() & out["close_price"].gt(0) & out["tcap"].notna()
    out.loc[miss_s, "shares_outstanding"] = (
        out.loc[miss_s, "tcap"] * 1000.0 / out.loc[miss_s, "close_price"]
    )

    # Delist
    dmap = dele.drop_duplicates("permno", keep="last")[
        ["permno", "dlstdt", "dlstcd", "dlret"]
    ].rename(
        columns={"dlstdt": "delist_date", "dlstcd": "delist_code", "dlret": "delisting_return"}
    )
    out = out.merge(dmap, on="permno", how="left")
    out["delist_date"] = pd.to_datetime(out["delist_date"], errors="coerce")
    # CRSP DLSTCD 100 = still trading at file end; not a true delist event
    out["delisting_flag"] = (
        out["delist_date"].notna()
        & (out["delist_code"].fillna(100).astype(int) != 100)
        & (out["caldt"] >= out["delist_date"])
    )
    # Clear delist metadata for still-active (code 100) names
    active = out["delist_code"].fillna(100).astype(int) == 100
    out.loc[active, "delist_date"] = pd.NaT
    out.loc[active, "delisting_return"] = np.nan

    # Static fields
    u2 = universe.drop_duplicates("permno")[["permno", "ric", "ticker"]]
    out = out.drop(columns=[c for c in ("ric", "ticker") if c in out.columns], errors="ignore")
    out = out.merge(u2, on="permno", how="left")
    h2 = hdr.drop_duplicates("permno")[["permno", "hsiccd", "hcomnam", "cusip9"]].rename(
        columns={"hsiccd": "siccd", "hcomnam": "company_name"}
    )
    out = out.drop(
        columns=[c for c in ("siccd", "company_name", "cusip9", "isin") if c in out.columns],
        errors="ignore",
    )
    out = out.merge(h2, on="permno", how="left")
    cusip9 = out["cusip9"].fillna("").astype(str).str.strip()
    out["isin"] = cusip9.map(cusip9_to_isin)
    out = out.drop(columns=["cusip9"], errors="ignore")
    out["sector"] = out["siccd"].map(
        lambda x: f"SIC{int(x) // 100:02d}" if pd.notna(x) and float(x) != 0 else None
    )
    return out


def select_universe_by_coverage(
    daily: pd.DataFrame,
    candidates: pd.DataFrame,
    dele: pd.DataFrame,
    last_date: pd.Timestamp,
) -> tuple[pd.DataFrame, dict]:
    """Keep PERMNOs with >=95% trading-day coverage; cap to preference size by median ADV."""
    # Trading calendar = union of dates in sample
    all_dates = pd.Index(sorted(daily["caldt"].dropna().unique()))
    n_cal = len(all_dates)
    dmap = dele.drop_duplicates("permno", keep="last").set_index("permno")

    stats_rows = []
    for permno, g in daily.groupby("permno"):
        g = g.sort_values("caldt")
        first = g["caldt"].iloc[0]
        last = g["caldt"].iloc[-1]
        dlstdt = dmap.loc[permno, "dlstdt"] if permno in dmap.index else pd.NaT
        dlstcd = dmap.loc[permno, "dlstcd"] if permno in dmap.index else np.nan
        truly_delisted = bool(pd.notna(dlstdt) and pd.notna(dlstcd) and int(dlstcd) != 100)
        end = last_date
        if truly_delisted:
            end = min(last_date, dlstdt)
        start = max(START, first)
        expected = all_dates[(all_dates >= start) & (all_dates <= end)]
        n_exp = len(expected)
        n_obs = g["caldt"].nunique()
        cov = n_obs / n_exp if n_exp else 0.0
        dollar_vol = (g["prc"].abs() * g["vol"]).replace(0, np.nan)
        med_adv = float(dollar_vol.median()) if dollar_vol.notna().any() else 0.0
        stats_rows.append(
            {
                "permno": int(permno),
                "n_obs": int(n_obs),
                "n_expected": int(n_exp),
                "coverage": cov,
                "median_dollar_adv": med_adv,
                "first_date": str(first.date()),
                "last_date": str(last.date()),
                "delisted": truly_delisted,
                "dlstcd": float(dlstcd) if pd.notna(dlstcd) else np.nan,
            }
        )
    cov_df = pd.DataFrame(stats_rows)
    eligible = cov_df[cov_df["coverage"] >= MIN_COVERAGE].copy()
    eligible = eligible.sort_values("median_dollar_adv", ascending=False)

    if len(eligible) > TARGET_UNIVERSE_MAX:
        eligible = eligible.head(TARGET_UNIVERSE_PREF)
    elif len(eligible) < TARGET_UNIVERSE_MIN:
        # fallback: relax coverage to 0.85 then top ADV
        eligible = cov_df[cov_df["coverage"] >= 0.85].sort_values(
            "median_dollar_adv", ascending=False
        )
        eligible = eligible.head(min(TARGET_UNIVERSE_PREF, TARGET_UNIVERSE_MAX))

    selected = candidates[candidates["permno"].isin(set(eligible["permno"]))].copy()
    # If still short (candidates filtered), use eligible permnos with map from candidates
    if len(selected) < TARGET_UNIVERSE_MIN:
        # attach ticker/ric from candidates where possible; else null
        selected = eligible[["permno"]].merge(candidates, on="permno", how="left")

    meta = {
        "calendar_days": n_cal,
        "candidates_with_daily": int(cov_df["permno"].nunique()),
        "eligible_coverage_ge_95": int((cov_df["coverage"] >= MIN_COVERAGE).sum()),
        "selected_permnos": int(selected["permno"].nunique()),
        "selected_delisted": int(
            eligible[eligible["permno"].isin(selected["permno"])]["delisted"].sum()
        ),
        "coverage_threshold_used": MIN_COVERAGE
        if (cov_df["coverage"] >= MIN_COVERAGE).sum() >= TARGET_UNIVERSE_MIN
        else 0.85,
    }
    return selected, {**meta, "coverage_table": cov_df}


def add_derived_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["permno", "caldt"]).copy()
    df["market_value"] = df["market_cap"]
    df["return_1d"] = df["daily_return"]

    # Dollar volume for ADV
    df["dollar_volume"] = df["close_price"] * df["trading_volume"]

    parts = []
    for permno, g in df.groupby("permno", sort=False):
        g = g.sort_values("caldt").copy()
        r = g["return_1d"]
        g["volatility_20d"] = r.rolling(20, min_periods=15).std() * SQRT_252
        g["volatility_60d"] = r.rolling(60, min_periods=40).std() * SQRT_252
        g["adv_20d"] = g["dollar_volume"].rolling(20, min_periods=10).mean()

        # Forward drawdowns: min cumulative wealth over next H days minus 1
        rets = r.to_numpy(dtype=float)
        n = len(rets)

        def forward_drawdown(horizon: int) -> np.ndarray:
            out_arr = np.full(n, np.nan)
            # Replace nan returns with 0 for path continuity within horizon only when
            # the entire forward window exists; require finite market path length.
            for i in range(0, n - horizon):
                window = rets[i + 1 : i + 1 + horizon]
                if window.size < horizon:
                    continue
                w = np.nan_to_num(window, nan=0.0)
                wealth = np.cumprod(1.0 + w)
                out_arr[i] = float(wealth.min() - 1.0)
            return out_arr

        g["drawdown_20d_forward"] = forward_drawdown(20)
        g["drawdown_60d_forward"] = forward_drawdown(60)
        g["realized_capacity_20d"] = g["market_value"] * (1.0 + g["drawdown_20d_forward"])
        g["realized_capacity_60d"] = g["market_value"] * (1.0 + g["drawdown_60d_forward"])
        parts.append(g)

    return pd.concat(parts, ignore_index=True)


def join_esg(df: pd.DataFrame, esg_path: Path) -> tuple[pd.DataFrame, dict]:
    if not esg_path.is_file():
        df["esg_score"] = np.nan
        df["esg_environmental_pillar"] = np.nan
        return df, {"esg_joined": False, "reason": "missing_file"}
    esg = pd.read_parquet(esg_path)
    # normalize columns
    colmap = {}
    for c in esg.columns:
        cl = str(c).lower()
        if cl == "ric":
            colmap[c] = "ric"
        elif "environmental" in cl and "pillar" in cl:
            colmap[c] = "esg_environmental_pillar"
        elif cl in ("esg score", "lseg esg score") or cl == "esg_score":
            if "esg_score" not in colmap.values():
                colmap[c] = "esg_score"
    esg2 = esg.rename(columns=colmap)
    keep = [c for c in ("ric", "esg_score", "esg_environmental_pillar") if c in esg2.columns]
    esg2 = esg2[keep].drop_duplicates("ric", keep="last")
    # Prefer LSEG ESG if both — already handled by first esg_score
    before = df["ric"].notna().sum()
    out = df.merge(esg2, on="ric", how="left")
    matched = out["esg_score"].notna().sum() if "esg_score" in out.columns else 0
    if "esg_score" not in out.columns:
        out["esg_score"] = np.nan
    if "esg_environmental_pillar" not in out.columns:
        out["esg_environmental_pillar"] = np.nan
    return out, {
        "esg_joined": True,
        "rows_with_ric": int(before),
        "rows_with_esg_score": int(out["esg_score"].notna().sum()),
        "unique_rics_with_esg": int(
            out.loc[out["esg_score"].notna(), "ric"].nunique()
        ),
    }


def finalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["security_id"] = df["permno"].astype(int).astype(str)
    df["date"] = pd.to_datetime(df["caldt"]).dt.strftime("%Y-%m-%d")
    df["permno"] = df["permno"].astype(int)
    if "isin" not in df.columns:
        df["isin"] = pd.NA

    ordered = [
        "security_id",
        "date",
        "permno",
        "ric",
        "isin",
        "ticker",
        "company_name",
        "sector",
        "siccd",
        "close_price",
        "daily_return",
        "return_1d",
        "shares_outstanding",
        "market_cap",
        "market_value",
        "trading_volume",
        "dollar_volume",
        "volatility_20d",
        "volatility_60d",
        "adv_20d",
        "drawdown_20d_forward",
        "drawdown_60d_forward",
        "realized_capacity_20d",
        "realized_capacity_60d",
        "delisting_flag",
        "delisting_return",
        "delist_date",
        "delist_code",
        "esg_score",
        "esg_environmental_pillar",
    ]
    for c in ordered:
        if c not in df.columns:
            df[c] = np.nan
    out = df[ordered].sort_values(["permno", "date"]).reset_index(drop=True)
    # stringify delist_date
    out["delist_date"] = pd.to_datetime(out["delist_date"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    return out


def write_schema(path: Path) -> None:
    schema = {
        "dataset_id": "constraint_market_capacity_v1",
        "format": "parquet",
        "grain": "security-day",
        "license": "internal_yzu_licensed_no_redistribution",
        "columns": [
            {"name": "security_id", "type": "string", "source": "CRSP PERMNO", "nullable": False},
            {"name": "date", "type": "string(YYYY-MM-DD)", "source": "CRSP CALDT", "nullable": False},
            {"name": "permno", "type": "int64", "source": "CRSP KYPERMNO", "nullable": False},
            {"name": "ric", "type": "string", "source": "Refinitiv SPX PIT map", "nullable": True},
            {"name": "isin", "type": "string", "source": "US + CRSP CUSIP9 + ISIN check digit", "nullable": True},
            {"name": "ticker", "type": "string", "source": "CRSP/Refinitiv map", "nullable": True},
            {"name": "company_name", "type": "string", "source": "CRSP HCOMNAM", "nullable": True},
            {"name": "sector", "type": "string", "source": "SIC2 from HSICCD", "nullable": True},
            {"name": "siccd", "type": "float", "source": "CRSP HSICCD", "nullable": True},
            {"name": "close_price", "type": "float", "unit": "USD", "source": "abs(CRSP PRC)", "nullable": True},
            {"name": "daily_return", "type": "float", "unit": "ratio", "source": "CRSP RET", "nullable": True},
            {"name": "return_1d", "type": "float", "unit": "ratio", "source": "alias of daily_return", "nullable": True},
            {"name": "shares_outstanding", "type": "float", "unit": "shares", "source": "CRSP SHROUT*1000", "nullable": True},
            {"name": "market_cap", "type": "float", "unit": "USD", "source": "CRSP TCAP*1000", "nullable": True},
            {"name": "market_value", "type": "float", "unit": "USD", "source": "alias of market_cap", "nullable": True},
            {"name": "trading_volume", "type": "float", "unit": "shares", "source": "CRSP VOL", "nullable": True},
            {"name": "dollar_volume", "type": "float", "unit": "USD", "source": "close_price*trading_volume", "nullable": True},
            {"name": "volatility_20d", "type": "float", "unit": "annualized_stdev", "source": "derived", "nullable": True},
            {"name": "volatility_60d", "type": "float", "unit": "annualized_stdev", "source": "derived", "nullable": True},
            {"name": "adv_20d", "type": "float", "unit": "USD", "source": "20d mean dollar_volume", "nullable": True},
            {"name": "drawdown_20d_forward", "type": "float", "unit": "ratio", "source": "derived min cumret next 20d", "nullable": True},
            {"name": "drawdown_60d_forward", "type": "float", "unit": "ratio", "source": "derived min cumret next 60d", "nullable": True},
            {"name": "realized_capacity_20d", "type": "float", "unit": "USD", "source": "market_value*(1+drawdown_20d_forward)", "nullable": True},
            {"name": "realized_capacity_60d", "type": "float", "unit": "USD", "source": "market_value*(1+drawdown_60d_forward)", "nullable": True},
            {"name": "delisting_flag", "type": "bool", "source": "date>=DLSTDT", "nullable": False},
            {"name": "delisting_return", "type": "float", "source": "CRSP DLRET", "nullable": True},
            {"name": "delist_date", "type": "string(YYYY-MM-DD)", "source": "CRSP DLSTDT", "nullable": True},
            {"name": "delist_code", "type": "float", "source": "CRSP DLSTCD", "nullable": True},
            {"name": "esg_score", "type": "float", "source": "Refinitiv ESG snapshot", "nullable": True},
            {"name": "esg_environmental_pillar", "type": "float", "source": "Refinitiv ESG snapshot", "nullable": True},
        ],
        "crsp_field_map": {
            "sfz_dp_dly": DP_COLS,
            "sfz_hdr": HDR_COLS,
            "sfz_nam": NAM_COLS,
            "sfz_del": DEL_COLS,
            "sfz_shr": SHR_COLS,
            "reference": "CRSP US Stock & Indexes Database Guide Flat File Format 1.0 (SIZ)",
        },
    }
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def write_methods(path: Path, manifest: dict) -> None:
    text = f"""# Constraint Market Collateral Capacity Study v1 — Methods

**License:** `internal_yzu_licensed_no_redistribution`  
**Product boundary:** YZU Research Drive = upstream data foundry; Constraint = downstream claim-analysis instrument.  
Licensed CRSP / Refinitiv **raw rows must not be publicly redistributed**.

Generated: `{manifest.get("generated_at")}`

## Purpose

Empirical panel for collateral-capacity claims of the form:

> At date t, market evidence and policy P permit financing capacity Q.  
> After the market moves, was that bounded claim actually covered?

Policy haircuts (fixed %, volatility, liquidity, concentration) live in Constraint Policy Studio.  
This panel supplies **observed market value** and **realized MTM capacity floors** only.

## Sources

| Source | Role | Path / product |
|--------|------|----------------|
| CRSP STOCK_25i SI ASCII (SIZ) | Price, return, volume, TCAP, shares, delist, names | `{manifest.get("sources", {}).get("crsp_zip")}` |
| Refinitiv `.SPX` PIT | Universe membership | `{manifest.get("sources", {}).get("spx_pit")}` |
| Refinitiv ESG snapshot | Optional ESG overlay (point-in-time caveat) | `{manifest.get("sources", {}).get("esg_snapshot")}` |

## CRSP field map (SIZ flat file 1.0)

Pipe-delimited, no header row:

- `sfz_dp_dly`: permno, caldt, prc, ret, retx, tcap, vol
- `sfz_hdr`: permno, cusip, cusip9, htick, permco, compno, issuno, hexcd, hsiccd, begdt, enddt, hdlstcd, hcomnam, htsymbol, hsnaics, hshrcd, hprimexch, htrdstat, hsecstat
- `sfz_nam`: permno, namedt, nameenddt, ncusip, ncusip9, ticker, comnam, shrcls, shrcd, exchcd, siccd, tsymbol, snaics, primexch, trdstat, secstat
- `sfz_del`: permno, dlstdt, dlstcd, nwperm, nwcomp, nextdt, dlprc, dlpdt, dlamt, dlret, dlretx
- `sfz_shr`: permno, shrsdt, shrsenddt, shrout, shrflg

Conventions:

- Negative `PRC` → bid/ask average; panel stores `close_price = abs(PRC)`.
- `SHROUT` is in **thousands**; `shares_outstanding = SHROUT * 1000`.
- `TCAP` is capitalization in **thousands of USD**; `market_cap = TCAP * 1000`.

## Universe

1. Take Refinitiv `.SPX` point-in-time constituents with `as_of_date >= 2018-01-01`.
2. Map `constituent_ric` → ticker (strip exchange suffix) → CRSP `sfz_nam` overlap on `tsymbol`/`ticker` with share codes 10/11 preferred.
3. Stream CRSP daily primary rows for candidate PERMNOs with `caldt >= 2018-01-01`.
4. Keep names with trading-day coverage ≥ {MIN_COVERAGE:.0%} vs the sample calendar through delist/last date; prefer continuity over breadth.
5. Cap to ~{TARGET_UNIVERSE_PREF} by median dollar ADV if eligible set exceeds {TARGET_UNIVERSE_MAX}.

Manifest counts: selected PERMNOs = **{manifest.get("universe", {}).get("n_permnos")}**;  
RIC match rate (unique) ≈ **{manifest.get("universe", {}).get("ric_match_rate_unique")}**.

## Derived fields

| Field | Definition |
|-------|------------|
| `volatility_20d` / `volatility_60d` | Trailing stdev of daily `RET` × √252 (min periods 15 / 40) |
| `adv_20d` | 20-day mean of `close_price * trading_volume` |
| `drawdown_Hd_forward` | min CumulativeProd(1+r)−1 over the next H trading days |
| `realized_capacity_Hd` | `market_value_t * (1 + drawdown_Hd_forward)` — MTM collateral floor |

Forward fields are null for the final H sessions of each security path.

## Refinitiv ESG caveat

ESG columns come from a **snapshot**, not a full score-history panel. Treat as optional static overlay keyed by RIC. MarketPsych / news sentiment fields are **not** included (not entitled on the YZU EDP).

## Period

`{manifest.get("period", {}).get("start")}` → `{manifest.get("period", {}).get("end")}` (latest complete date in filtered CRSP daily extract).

## Out of scope (this package)

GDELT shock overlay, DataCite lineage pack, BigQuery run manifests, Constraint policy engine implementation.
"""
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", type=Path, default=ZIP_DEFAULT)
    ap.add_argument("--spx-pit", type=Path, default=SPX_PIT_DEFAULT)
    ap.add_argument("--esg", type=Path, default=ESG_DEFAULT)
    ap.add_argument("--out-dir", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--work-dir", type=Path, default=WORK)
    ap.add_argument(
        "--reuse-daily",
        action="store_true",
        help="Reuse existing crsp_daily_candidates.parquet if present",
    )
    args = ap.parse_args()

    work: Path = args.work_dir
    raw = work / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("== load master tables ==")
    masters = load_master_tables(raw)
    for k, df in masters.items():
        p = work / f"{k}.parquet"
        df.to_parquet(p, index=False)
        print(f"  {k}: {len(df):,} -> {p}")

    print("== SPX PIT -> PERMNO map ==")
    spx = pd.read_parquet(args.spx_pit)
    candidates, map_stats = build_spx_permno_map(masters["nam"], masters["hdr"], spx)
    candidates_path = work / "universe_candidates.parquet"
    candidates.to_parquet(candidates_path, index=False)
    print(json.dumps(map_stats, indent=2))
    print(f"  candidates: {len(candidates)}")

    daily_path = work / "crsp_daily_candidates.parquet"
    if args.reuse_daily and daily_path.is_file():
        print(f"== reuse daily {daily_path} ==")
        daily_stats = {"reused": True, "rows": int(len(pd.read_parquet(daily_path, columns=["permno"])))}
    else:
        print("== stream sfz_dp_dly (2018+, candidate PERMNOs) ==")
        permnos = set(int(p) for p in candidates["permno"])
        daily_stats = stream_daily_for_permnos(args.zip, permnos, START, daily_path)
        print(json.dumps(daily_stats, indent=2))

    daily = pd.read_parquet(daily_path)
    last_date = pd.to_datetime(daily["caldt"]).max()

    print("== coverage filter / freeze universe ==")
    selected, cov_meta = select_universe_by_coverage(
        daily, candidates, masters["del"], last_date
    )
    cov_table: pd.DataFrame = cov_meta.pop("coverage_table")
    cov_table.to_parquet(work / "coverage_table.parquet", index=False)
    selected_path = work / "universe_selected.parquet"
    selected.to_parquet(selected_path, index=False)
    print(json.dumps(cov_meta, indent=2))
    print(f"  selected permnos: {len(selected)}")

    daily_u = daily[daily["permno"].isin(set(selected["permno"]))].copy()
    print("== attach shares / delist / static ==")
    panel = attach_shares_and_delist(
        daily_u, masters["shr"], masters["del"], selected, masters["hdr"]
    )
    print("== derived fields ==")
    panel = add_derived_fields(panel)
    print("== ESG join ==")
    panel, esg_stats = join_esg(panel, args.esg)
    print(json.dumps(esg_stats, indent=2))
    panel = finalize_columns(panel)

    parquet_path = out_dir / "constraint_market_capacity_v1.parquet"
    panel.to_parquet(parquet_path, index=False)
    print(f"wrote {parquet_path} rows={len(panel):,} cols={len(panel.columns)}")

    sha = _sha256_file(parquet_path)
    manifest = {
        "dataset_id": "constraint_market_capacity_v1",
        "generated_at": _utc_now(),
        "license": "internal_yzu_licensed_no_redistribution",
        "redistribution": "forbidden_for_licensed_raw_and_derived_crsp_refinitiv_rows",
        "product_boundary": {
            "upstream": "YZU Research Drive (data foundry)",
            "downstream": "Constraint (claim-analysis instrument)",
        },
        "period": {
            "start": str(pd.to_datetime(panel["date"]).min().date()),
            "end": str(pd.to_datetime(panel["date"]).max().date()),
        },
        "universe": {
            "n_permnos": int(panel["permno"].nunique()),
            "n_rics": int(panel["ric"].dropna().nunique()),
            "permnos": sorted(int(x) for x in panel["permno"].unique()),
            "rics": sorted(str(x) for x in panel["ric"].dropna().unique()),
            "ric_match_rate_unique": map_stats.get("ric_match_rate_unique"),
            "map_stats": map_stats,
            "coverage_meta": cov_meta,
        },
        "rows": int(len(panel)),
        "columns": list(panel.columns),
        "sha256": sha,
        "sources": {
            "crsp_zip": str(args.zip),
            "spx_pit": str(args.spx_pit),
            "esg_snapshot": str(args.esg),
            "work_dir": str(work),
        },
        "daily_extract": daily_stats,
        "esg": esg_stats,
        "definitions": {
            "realized_capacity_Hd": "market_value_t * (1 + min_cumret over next H trading days)",
            "drawdown_Hd_forward": "min wealth path over next H days minus 1",
            "policy_haircuts": "not applied in this panel — Constraint Policy Studio owns them",
        },
    }
    (out_dir / "constraint_market_capacity_v1_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    write_schema(out_dir / "constraint_market_capacity_v1_schema.json")
    write_methods(out_dir / "constraint_market_capacity_v1_methods.md", manifest)

    # Slim manifest copy without giant permno list for console
    slim = {k: v for k, v in manifest.items() if k != "universe"}
    slim["universe"] = {
        k: v
        for k, v in manifest["universe"].items()
        if k not in ("permnos", "rics")
    }
    print(json.dumps(slim, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
