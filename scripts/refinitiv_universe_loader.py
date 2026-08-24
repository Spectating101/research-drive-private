#!/usr/bin/env python3
"""Load layered Refinitiv universes from config/refinitiv_universes.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO / "config/refinitiv_universes.json"

NYSE_DOT_TICKERS = {
    "BRK.B": "BRK_b.N",
    "BF.B": "BF_b.N",
}


def yahoo_to_ric(ticker: str, *, mapping: dict[str, Any] | None = None) -> str:
    """Map a Yahoo-style symbol to an LSEG RIC."""
    t = ticker.strip().upper()
    if not t:
        return t

    special = NYSE_DOT_TICKERS
    if mapping:
        special = {**NYSE_DOT_TICKERS, **(mapping.get("nyse_dot_special") or {})}

    if t in special:
        return special[t]

    # Already-suffixed Asia / exchange RICs pass through.
    if t.endswith((".JK", ".TW", ".T", ".KS", ".SI", ".HK")):
        return t

    # FX / commodities / indices with dot or equals.
    if t.endswith("=") or (t.startswith(".") and len(t) > 1):
        return t

    # Yahoo index caret → Refinitiv dot index.
    if t.startswith("^"):
        return "." + t[1:]

    # Already dotted (e.g. BRK.B handled above; other dotted pass if not caret).
    if "." in t:
        return t

    # Hyphen tickers → underscore + default US suffix.
    default_suffix = ".O"
    if mapping:
        default_suffix = str(mapping.get("us_default_suffix", ".O"))
    if "-" in t:
        return t.replace("-", "_") + default_suffix
    return f"{t}{default_suffix}"


def _read_ticker_file(path: Path) -> list[str]:
    tickers: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split("#", 1)[0].strip()
        if line:
            tickers.append(line.split()[0].strip())
    return tickers


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        t = item.strip()
        if not t or t in seen:
            continue
        out.append(t)
        seen.add(t)
    return out


def _stride_sample(items: list[str], stride: int, limit: int | None) -> list[str]:
    sampled = items[:: max(1, stride)]
    if limit is not None:
        return sampled[:limit]
    return sampled


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG
    if not cfg_path.is_absolute():
        cfg_path = REPO / cfg_path
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _resolve_base_tickers(spec: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    mapping = cfg.get("ric_mapping") or {}
    tickers: list[str] = []

    if spec.get("rics"):
        tickers.extend(str(x) for x in spec["rics"])

    if spec.get("tickers_file"):
        tf = Path(str(spec["tickers_file"]))
        if not tf.is_absolute():
            tf = REPO / tf
        tickers.extend(_read_ticker_file(tf))

    if spec.get("source_config") and spec.get("universe_id"):
        src = Path(str(spec["source_config"]))
        if not src.is_absolute():
            src = REPO / src
        asia = json.loads(src.read_text(encoding="utf-8"))
        uid = str(spec["universe_id"])
        for uni in asia.get("universes", []):
            if str(uni.get("id")) == uid:
                tickers.extend(str(x) for x in uni.get("tickers", []))
                if uni.get("tickers_file"):
                    tf = Path(str(uni["tickers_file"]))
                    if not tf.is_absolute():
                        tf = REPO / tf
                    tickers.extend(_read_ticker_file(tf))
                break

    if spec.get("ric_from_yahoo"):
        tickers = [yahoo_to_ric(t, mapping=mapping) for t in tickers]

    return _dedupe(tickers)


def load_universe_rics(
    universe_id: str,
    *,
    config_path: Path | None = None,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Return deduped RIC list for *universe_id* (supports compose specs)."""
    cfg = config or load_config(config_path)
    universes = cfg.get("universes") or {}
    if universe_id not in universes:
        raise KeyError(f"Unknown universe {universe_id!r}; available: {sorted(universes)}")

    spec = universes[universe_id]
    if spec.get("compose"):
        merged: list[str] = []
        for part in spec["compose"]:
            child_id = str(part["from"])
            child_spec = universes[child_id]
            child_tickers = _resolve_base_tickers(child_spec, cfg)
            stride = int(part.get("stride", 1))
            limit = part.get("limit")
            limit_i = int(limit) if limit is not None else None
            merged.extend(_stride_sample(child_tickers, stride, limit_i))
        return _dedupe(merged)

    return _resolve_base_tickers(spec, cfg)


def list_universe_ids(*, config_path: Path | None = None) -> list[str]:
    cfg = load_config(config_path)
    return sorted((cfg.get("universes") or {}).keys())


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Print RICs for a Refinitiv universe.")
    ap.add_argument("universe", nargs="?", default="value_harvest_core")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = ap.parse_args()
    rics = load_universe_rics(args.universe, config_path=Path(args.config))
    print(f"{args.universe}: {len(rics)} RICs")
    for ric in rics:
        print(ric)
