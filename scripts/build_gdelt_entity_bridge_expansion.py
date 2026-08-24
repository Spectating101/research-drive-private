#!/usr/bin/env python3
"""Expand Refinitiv entity spine GDELT bridge — global master + exchange rules + aliases."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
SPINE_IN = ROOT / "data_lake/research_panels/refinitiv/2026-07-06-complete/entity_market_spine.parquet"
OUT_DIR = ROOT / "data_lake/research_panels/refinitiv/2026-07-06-complete"
OUT_PANEL = OUT_DIR / "entity_market_spine_expanded.parquet"
ALIASES = ROOT / "config/ticker_entity_aliases_v2.json"
GLOBAL_MASTER = ROOT / "data_lake/entity_mapping/global/latest/entity_master.csv"

SUFFIX_MAP = {
    ".TW": ("TWSE", "TWN"),
    ".TWO": ("TPEX", "TWN"),
    ".KS": ("KRX", "KOR"),
    ".KQ": ("KOSDAQ", "KOR"),
    ".T": ("TSE", "JPN"),
    ".JK": ("IDX", "IDN"),
    ".HK": ("HKEX", "HKG"),
    ".SS": ("SSE", "CHN"),
    ".SZ": ("SZSE", "CHN"),
    ".SI": ("SGX", "SGP"),
    ".KL": ("BURSA", "MYS"),
    ".BK": ("SET", "THA"),
    ".NS": ("NSE", "IND"),
    ".BO": ("BSE", "IND"),
    ".AX": ("ASX", "AUS"),
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _cell_str(row: pd.Series, col: str | None) -> str:
    if not col:
        return ""
    val = row.get(col)
    if val is None or (isinstance(val, float) and pd.isna(val)) or pd.isna(val):
        return ""
    return str(val).strip()


def _synthesize_entity_id(yahoo_symbol: str) -> str | None:
    sym = str(yahoo_symbol or "").strip()
    if not sym:
        return None
    for suffix, (exchange, _country) in SUFFIX_MAP.items():
        if sym.endswith(suffix):
            code = sym[: -len(suffix)]
            return f"{exchange}:{code}"
    if "." not in sym and "^" not in sym:
        return f"US_OR_GLOBAL:{sym.upper()}"
    return None


def _load_global_master() -> dict[str, dict[str, str]]:
    import csv

    path = GLOBAL_MASTER
    if not path.is_file():
        alt = sorted((ROOT / "data_lake/entity_mapping/global").glob("*/entity_master.csv"), reverse=True)
        path = alt[0] if alt else path
    out: dict[str, dict[str, str]] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            sym = str(row.get("yahoo_symbol") or "").strip()
            if sym:
                out[sym] = row
    return out


def expand_spine(spine_in: Path = SPINE_IN, out_panel: Path = OUT_PANEL) -> dict[str, Any]:
    if not spine_in.is_file():
        raise FileNotFoundError(spine_in)

    spine = pd.read_parquet(spine_in)
    global_map = _load_global_master()
    alias_rows: list[dict] = []
    if ALIASES.is_file():
        alias_rows = list(json.loads(ALIASES.read_text(encoding="utf-8")).get("entries") or [])

    sym_col = "yahoo_symbol"
    name_col = next((c for c in ("company_name", "constituent_name", "name") if c in spine.columns), None)
    ric_col = "ric" if "ric" in spine.columns else None

    before = int(spine["gdelt_entity_id"].notna().sum()) if "gdelt_entity_id" in spine.columns else 0
    expanded = spine.copy()
    if "bridge_method" not in expanded.columns:
        expanded["bridge_method"] = None

    methods: dict[str, int] = {}

    def _set(idx: Any, gid: Any, method: str, name: str = "") -> None:
        expanded.at[idx, "gdelt_entity_id"] = gid
        expanded.at[idx, "bridge_method"] = method
        if name and "entity_name_gdelt" in expanded.columns:
            expanded.at[idx, "entity_name_gdelt"] = name
        methods[method] = methods.get(method, 0) + 1

    for idx, row in expanded.iterrows():
        if pd.notna(row.get("gdelt_entity_id")):
            continue
        sym = _cell_str(row, sym_col)
        hit = global_map.get(sym)
        if hit and hit.get("entity_id"):
            _set(idx, hit["entity_id"], "global_master", str(hit.get("name") or ""))

    for idx, row in expanded.iterrows():
        if pd.notna(row.get("gdelt_entity_id")):
            continue
        sym = _cell_str(row, sym_col)
        gid = _synthesize_entity_id(sym)
        if gid:
            _set(idx, gid, "exchange_synth")

    sym_to_gid = {
        str(r[sym_col]).strip(): r["gdelt_entity_id"]
        for _, r in expanded.iterrows()
        if pd.notna(r.get("gdelt_entity_id")) and _cell_str(r, sym_col)
    }

    for entry in alias_rows:
        target = str(entry.get("yahoo_symbol") or "").strip()
        peer_gid = sym_to_gid.get(target)
        if not peer_gid:
            continue
        for idx, row in expanded.iterrows():
            if pd.notna(row.get("gdelt_entity_id")):
                continue
            sym = _cell_str(row, sym_col)
            if sym == target and entry.get("notes") == "ADR":
                _set(idx, peer_gid, "adr_peer")
                sym_to_gid[sym] = peer_gid
                continue
            if name_col:
                nm = _norm(_cell_str(row, name_col))
                for alias in entry.get("aliases") or []:
                    if alias and _norm(alias) in nm:
                        _set(idx, peer_gid, "alias_name_peer")
                        if sym:
                            sym_to_gid[sym] = peer_gid
                        break

    for idx, row in expanded.iterrows():
        if pd.notna(row.get("gdelt_entity_id")):
            continue
        sym = _cell_str(row, sym_col)
        ric = _cell_str(row, ric_col)
        for candidate in (sym, ric):
            if candidate in sym_to_gid:
                _set(idx, sym_to_gid[candidate], "symbol_peer_map")
                if sym:
                    sym_to_gid[sym] = sym_to_gid[candidate]
                break

    if name_col and "country_code" in expanded.columns:
        name_index: dict[tuple[str, str], Any] = {}
        for _, row in expanded.iterrows():
            if pd.isna(row.get("gdelt_entity_id")):
                continue
            nm = _norm(_cell_str(row, name_col))
            cc = str(row.get("country_code") or "").strip()
            if nm and cc:
                name_index.setdefault((cc, nm), row["gdelt_entity_id"])
        for idx, row in expanded.iterrows():
            if pd.notna(row.get("gdelt_entity_id")):
                continue
            nm = _norm(_cell_str(row, name_col))
            cc = str(row.get("country_code") or "").strip()
            gid = name_index.get((cc, nm))
            if gid:
                _set(idx, gid, "name_country_peer")

    after = int(expanded["gdelt_entity_id"].notna().sum())
    out_panel.parent.mkdir(parents=True, exist_ok=True)
    expanded.to_parquet(out_panel, index=False)

    spx = expanded[expanded["in_spx"] == 1] if "in_spx" in expanded.columns else expanded.iloc[:0]
    spx_bridged = int(spx["gdelt_entity_id"].notna().sum()) if len(spx) else 0

    stats = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "input_spine": str(spine_in.relative_to(ROOT)),
        "output_panel": str(out_panel.relative_to(ROOT)),
        "global_master_symbols": len(global_map),
        "rics": len(expanded),
        "bridged_before": before,
        "bridged_after": after,
        "added": after - before,
        "bridge_pct": round(100.0 * after / max(len(expanded), 1), 1),
        "spx_bridged": spx_bridged,
        "spx_total": int(len(spx)),
        "bridge_methods": methods,
    }
    (out_panel.parent / "entity_bridge_expansion_stats.json").write_text(
        json.dumps(stats, indent=2) + "\n", encoding="utf-8"
    )
    return stats


def main() -> int:
    stats = expand_spine()
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
