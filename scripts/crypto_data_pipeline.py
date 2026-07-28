#!/usr/bin/env python3
"""
Workspace crypto data pipeline (free-first, optional CoinGecko).

What it does:
1) Runs free-source collection (CoinLore/CryptoCompare by default).
2) Optionally runs CoinGecko collection (public or Pro).
3) Audits field coverage for the target coin-profile fields:
   info, contract, website, whitepaper, explorers, wallets,
   community, search_on, api_id, chains, categories.
4) Writes run artifacts (logs + JSON/Markdown summary) under data_lake/crypto_pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
_MARKET_SCRIPTS_ROOT = Path(__file__).resolve().parent
_ENV_FILE = _WORKSPACE_ROOT / ".env.local"

DEFAULT_OUT_ROOT = _WORKSPACE_ROOT / "data_lake" / "crypto_pipeline"
FIELD_ORDER = [
    "info",
    "contract",
    "website",
    "whitepaper",
    "explorers",
    "wallets",
    "community",
    "search_on",
    "api_id",
    "chains",
    "categories",
]


@dataclass
class StageResult:
    name: str
    enabled: bool
    command: list[str]
    log_path: str
    db_path: str
    started_at: str
    completed_at: str
    exit_code: int
    note: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_env_value(name: str, env_path: Path | None = None) -> str:
    explicit_path = env_path is not None
    path = env_path or _ENV_FILE
    if not explicit_path:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    if not path.exists():
        return str(os.getenv(name, "") or "").strip() if explicit_path else ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line.startswith(f"{name}="):
            continue
        value = line.split("=", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value
    return str(os.getenv(name, "") or "").strip() if explicit_path else ""


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _has_value(value: Any) -> bool:
    if _has_text(value):
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, list):
        return any(_has_value(x) for x in value)
    if isinstance(value, dict):
        return any(_has_value(v) for v in value.values())
    return False


def _parse_json_maybe(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        parsed = json.loads(value)
    except Exception:
        return default
    if isinstance(default, dict) and isinstance(parsed, dict):
        return parsed
    if isinstance(default, list) and isinstance(parsed, list):
        return parsed
    return default


def _table_count(conn: sqlite3.Connection, table_name: str) -> int:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
    except sqlite3.Error:
        return 0


def _latest_ingest_run(conn: sqlite3.Connection) -> dict[str, Any] | None:
    try:
        row = conn.execute(
            """
            SELECT run_id, started_at, completed_at, status, note
            FROM ingest_runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return {
        "run_id": row[0],
        "started_at": row[1],
        "completed_at": row[2],
        "status": row[3],
        "note": row[4],
    }


def _iter_coin_detail_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(coin_details)").fetchall()
            if len(row) > 1
        }
    except sqlite3.Error:
        return []
    if not cols:
        return []

    wanted = ["coin_id", "links_json", "categories_json", "platforms_json", "raw_json"]
    selected = [c for c in wanted if c in cols]
    if not selected:
        return []
    q = f"SELECT {', '.join(selected)} FROM coin_details"
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(q).fetchall()
    except sqlite3.Error:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append({k: row[k] for k in selected})
    return out


def _description_exists(raw: dict[str, Any]) -> bool:
    description = raw.get("description")
    if isinstance(description, dict):
        return any(_has_text(v) for v in description.values())
    return _has_text(description)


def _coverage_from_db(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    try:
        counts = {
            "coins": _table_count(conn, "coins"),
            "coin_markets": _table_count(conn, "coin_markets"),
            "coin_details": _table_count(conn, "coin_details"),
            "coin_history": _table_count(conn, "coin_history"),
            "exchanges": _table_count(conn, "exchanges"),
            "exchange_details": _table_count(conn, "exchange_details"),
            "failures": _table_count(conn, "failures"),
        }
        ingest = _latest_ingest_run(conn)
        rows = _iter_coin_detail_rows(conn)
    finally:
        conn.close()

    stats = {k: 0 for k in FIELD_ORDER}
    total = len(rows)

    for row in rows:
        coin_id = str(row.get("coin_id") or "").strip()
        links = _parse_json_maybe(row.get("links_json"), {})
        categories = _parse_json_maybe(row.get("categories_json"), [])
        platforms = _parse_json_maybe(row.get("platforms_json"), {})
        raw = _parse_json_maybe(row.get("raw_json"), {})

        if _has_text(coin_id):
            stats["api_id"] += 1

        if _description_exists(raw):
            stats["info"] += 1

        platform_map = platforms if isinstance(platforms, dict) else {}
        if isinstance(raw.get("platforms"), dict):
            platform_map = {**platform_map, **raw.get("platforms", {})}
        contract_address = raw.get("contract_address")
        has_contract = any(_has_text(v) for v in platform_map.values()) or _has_text(contract_address)
        if has_contract:
            stats["contract"] += 1
            stats["chains"] += 1

        if _has_value(links.get("homepage")):
            stats["website"] += 1
        if _has_value(links.get("whitepaper")):
            stats["whitepaper"] += 1
        if _has_value(links.get("blockchain_site")):
            stats["explorers"] += 1

        has_wallet = False
        if isinstance(links, dict):
            for k, v in links.items():
                if "wallet" in str(k).lower() and _has_value(v):
                    has_wallet = True
                    break
        if has_wallet:
            stats["wallets"] += 1

        community_keys = [
            "twitter_screen_name",
            "facebook_username",
            "telegram_channel_identifier",
            "subreddit_url",
            "bitcointalk_thread_identifier",
        ]
        has_community = isinstance(links, dict) and any(_has_value(links.get(k)) for k in community_keys)
        if not has_community and isinstance(links, dict):
            for k, v in links.items():
                kl = str(k).lower()
                if any(token in kl for token in ["twitter", "reddit", "facebook", "telegram", "discord", "community"]):
                    if _has_value(v):
                        has_community = True
                        break
        if not has_community and isinstance(raw.get("community_data"), dict):
            has_community = any(v not in (None, 0, "", []) for v in raw["community_data"].values())
        if has_community:
            stats["community"] += 1

        has_search = False
        if isinstance(links, dict):
            has_search = any(
                _has_value(links.get(k))
                for k in ["subreddit_url", "repos_url", "snapshot_url", "announcement_url"]
            )
        if has_search:
            stats["search_on"] += 1

        if isinstance(categories, list) and any(_has_text(x) for x in categories):
            stats["categories"] += 1

    fill_rates = {
        key: {
            "filled": stats[key],
            "total": total,
            "fill_rate": round((stats[key] / total), 4) if total else 0.0,
        }
        for key in FIELD_ORDER
    }

    return {
        "db_path": str(db_path),
        "counts": counts,
        "latest_ingest_run": ingest,
        "coverage_sample_size": total,
        "field_fill": fill_rates,
    }


def _run_stage(
    *,
    stage_name: str,
    enabled: bool,
    command: list[str],
    log_path: Path,
    db_path: Path,
    dry_run: bool,
) -> StageResult:
    started = _utc_now_iso()
    if not enabled:
        return StageResult(
            name=stage_name,
            enabled=False,
            command=command,
            log_path=str(log_path),
            db_path=str(db_path),
            started_at=started,
            completed_at=_utc_now_iso(),
            exit_code=0,
            note="skipped",
        )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        log_path.write_text(f"[dry-run] {' '.join(command)}\n", encoding="utf-8")
        return StageResult(
            name=stage_name,
            enabled=True,
            command=command,
            log_path=str(log_path),
            db_path=str(db_path),
            started_at=started,
            completed_at=_utc_now_iso(),
            exit_code=0,
            note="dry-run",
        )

    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"$ {' '.join(command)}\n\n")
        f.flush()
        proc = subprocess.run(
            command,
            cwd=str(_WORKSPACE_ROOT),
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    note = "ok" if proc.returncode == 0 else f"failed(exit={proc.returncode})"
    return StageResult(
        name=stage_name,
        enabled=True,
        command=command,
        log_path=str(log_path),
        db_path=str(db_path),
        started_at=started,
        completed_at=_utc_now_iso(),
        exit_code=int(proc.returncode),
        note=note,
    )


def _build_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Crypto Data Pipeline Report - {report['run_id']}")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at']}`")
    lines.append(f"- Output directory: `{report['out_dir']}`")
    lines.append(f"- Profile: `{report['profile']}`")
    lines.append("")
    lines.append("## Stage Execution")
    lines.append("")
    lines.append("| Stage | Enabled | Exit | Note | DB | Log |")
    lines.append("|---|---:|---:|---|---|---|")
    for stage in report["stages"]:
        lines.append(
            f"| {stage['name']} | {str(stage['enabled']).lower()} | {stage['exit_code']} | {stage['note']} | "
            f"`{stage['db_path']}` | `{stage['log_path']}` |"
        )
    lines.append("")
    lines.append("## Coverage Summary")
    lines.append("")
    for source_name, source in report["sources"].items():
        lines.append(f"### {source_name}")
        lines.append("")
        lines.append(f"- Sample size (`coin_details` rows): **{source.get('coverage_sample_size', 0)}**")
        counts = source.get("counts", {})
        lines.append(
            f"- Counts: coins={counts.get('coins', 0)}, markets={counts.get('coin_markets', 0)}, "
            f"details={counts.get('coin_details', 0)}, history={counts.get('coin_history', 0)}, "
            f"exchanges={counts.get('exchanges', 0)}, exchange_details={counts.get('exchange_details', 0)}, "
            f"failures={counts.get('failures', 0)}"
        )
        lines.append("")
        lines.append("| Field | Filled | Total | Fill rate |")
        lines.append("|---|---:|---:|---:|")
        fill = source.get("field_fill", {})
        for field in FIELD_ORDER:
            row = fill.get(field, {"filled": 0, "total": 0, "fill_rate": 0.0})
            lines.append(
                f"| {field} | {row['filled']} | {row['total']} | {row['fill_rate'] * 100:.1f}% |"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _default_history_from(profile: str) -> str:
    if profile == "full":
        return "2020-01-01T00:00:00+00:00"
    return "2024-01-01T00:00:00+00:00"


def _default_limit(profile: str) -> int:
    if profile == "full":
        return 0
    return 500


def _default_exchange_limit(profile: str) -> int:
    if profile == "full":
        return 0
    return 150


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run workspace crypto collection pipeline.")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--run-id", default=f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}")
    ap.add_argument("--profile", choices=["quick", "full"], default="quick")
    ap.add_argument("--free-source", choices=["coinlore", "coinpaprika"], default="coinlore")
    ap.add_argument("--coingecko-mode", choices=["off", "public", "pro"], default="off")
    ap.add_argument("--coingecko-api-key", default="")
    ap.add_argument("--coins-limit", type=int, default=None)
    ap.add_argument("--exchange-limit", type=int, default=None)
    ap.add_argument("--history-from", default="")
    ap.add_argument("--history-to", default="now")
    ap.add_argument("--skip-coin-details", action="store_true")
    ap.add_argument("--skip-history", action="store_true")
    ap.add_argument("--skip-exchanges", action="store_true")
    ap.add_argument("--min-interval-seconds", type=float, default=0.2)
    ap.add_argument("--coingecko-min-interval-seconds", type=float, default=2.5)
    ap.add_argument("--coingecko-markets-max-pages", type=int, default=None, help="Override CoinGecko markets max pages (0=all).")
    ap.add_argument("--coingecko-exchanges-max-pages", type=int, default=None, help="Override CoinGecko exchanges max pages (0=all).")
    ap.add_argument("--timeout-seconds", type=int, default=30)
    ap.add_argument("--max-retries", type=int, default=4)
    ap.add_argument("--retry-backoff-seconds", type=float, default=2.0)
    ap.add_argument("--strict", action="store_true", help="Fail run if any enabled stage fails.")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main() -> int:
    args = _build_parser().parse_args()

    if args.coingecko_mode == "pro" and not args.coingecko_api_key:
        args.coingecko_api_key = _load_env_value("COINGECKO_API_KEY")
        if not args.coingecko_api_key:
            print("ERROR: --coingecko-mode pro requires --coingecko-api-key (or COINGECKO_API_KEY).", file=sys.stderr)
            return 2

    coins_limit = _default_limit(args.profile) if args.coins_limit is None else int(args.coins_limit)
    exchange_limit = _default_exchange_limit(args.profile) if args.exchange_limit is None else int(args.exchange_limit)
    history_from = args.history_from.strip() or _default_history_from(args.profile)
    if args.coingecko_markets_max_pages is None:
        cg_markets_max_pages = 1 if args.coingecko_mode == "public" else 0
    else:
        cg_markets_max_pages = int(args.coingecko_markets_max_pages)
    if args.coingecko_exchanges_max_pages is None:
        cg_exchanges_max_pages = 1 if args.coingecko_mode == "public" else 0
    else:
        cg_exchanges_max_pages = int(args.coingecko_exchanges_max_pages)

    run_dir = (args.out_root / args.run_id).resolve()
    logs_dir = run_dir / "logs"
    reports_dir = run_dir / "reports"
    run_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    free_script = (
        _MARKET_SCRIPTS_ROOT / "free_crypto_collect_coinlore.py"
        if args.free_source == "coinlore"
        else _MARKET_SCRIPTS_ROOT / "free_crypto_collect.py"
    )
    cg_script = _MARKET_SCRIPTS_ROOT / "coingecko_bulk_collect.py"
    if not free_script.exists():
        print(f"ERROR: collector not found: {free_script}", file=sys.stderr)
        return 2
    if not cg_script.exists():
        print(f"ERROR: collector not found: {cg_script}", file=sys.stderr)
        return 2

    free_db = run_dir / f"free_{args.free_source}.sqlite3"
    cg_db = run_dir / "coingecko.sqlite3"

    free_cmd = [
        sys.executable,
        str(free_script),
        "--db-path",
        str(free_db),
        "--coins-limit",
        str(coins_limit),
        "--exchange-limit",
        str(exchange_limit),
        "--history-from",
        history_from,
        "--history-to",
        args.history_to,
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--min-interval-seconds",
        str(args.min_interval_seconds),
        "--max-retries",
        str(args.max_retries),
        "--retry-backoff-seconds",
        str(args.retry_backoff_seconds),
    ]
    if args.skip_coin_details:
        free_cmd.append("--skip-coin-details")
    if args.skip_history:
        free_cmd.append("--skip-history")
    if args.skip_exchanges:
        free_cmd.append("--skip-exchanges")

    cg_cmd = [
        sys.executable,
        str(cg_script),
        "--db-path",
        str(cg_db),
        "--coins-limit",
        str(min(coins_limit, 50) if args.coingecko_mode == "public" and coins_limit == 0 else coins_limit),
        "--exchange-limit",
        str(min(exchange_limit, 50) if args.coingecko_mode == "public" and exchange_limit == 0 else exchange_limit),
        "--history-from",
        history_from,
        "--history-to",
        args.history_to,
        "--markets-max-pages",
        str(cg_markets_max_pages),
        "--exchanges-max-pages",
        str(cg_exchanges_max_pages),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--min-interval-seconds",
        str(args.coingecko_min_interval_seconds),
        "--max-retries",
        str(args.max_retries),
        "--retry-backoff-seconds",
        str(args.retry_backoff_seconds),
    ]
    if args.coingecko_mode == "public":
        cg_cmd.append("--use-public-api")
    elif args.coingecko_mode == "pro":
        cg_cmd.extend(["--api-key", args.coingecko_api_key])
    if args.skip_coin_details:
        cg_cmd.append("--skip-coin-details")
    if args.skip_history:
        cg_cmd.append("--skip-history")
    if args.skip_exchanges:
        cg_cmd.append("--skip-exchanges")

    print(f"[pipeline] run_id={args.run_id} profile={args.profile} out={run_dir}")
    print(f"[pipeline] free source={args.free_source} coingecko_mode={args.coingecko_mode}")

    stages: list[StageResult] = []
    stages.append(
        _run_stage(
            stage_name=f"free_{args.free_source}",
            enabled=True,
            command=free_cmd,
            log_path=logs_dir / f"free_{args.free_source}.log",
            db_path=free_db,
            dry_run=args.dry_run,
        )
    )
    stages.append(
        _run_stage(
            stage_name="coingecko",
            enabled=(args.coingecko_mode != "off"),
            command=cg_cmd,
            log_path=logs_dir / "coingecko.log",
            db_path=cg_db,
            dry_run=args.dry_run,
        )
    )

    sources: dict[str, Any] = {}
    if free_db.exists():
        sources[f"free_{args.free_source}"] = _coverage_from_db(free_db)
    if cg_db.exists():
        sources["coingecko"] = _coverage_from_db(cg_db)

    report = {
        "run_id": args.run_id,
        "generated_at": _utc_now_iso(),
        "out_dir": str(run_dir),
        "profile": args.profile,
        "params": {
            "free_source": args.free_source,
            "coingecko_mode": args.coingecko_mode,
            "coins_limit": coins_limit,
            "exchange_limit": exchange_limit,
            "history_from": history_from,
            "history_to": args.history_to,
            "skip_coin_details": bool(args.skip_coin_details),
            "skip_history": bool(args.skip_history),
            "skip_exchanges": bool(args.skip_exchanges),
            "timeout_seconds": int(args.timeout_seconds),
            "max_retries": int(args.max_retries),
            "retry_backoff_seconds": float(args.retry_backoff_seconds),
            "min_interval_seconds": float(args.min_interval_seconds),
            "coingecko_min_interval_seconds": float(args.coingecko_min_interval_seconds),
            "coingecko_markets_max_pages": int(cg_markets_max_pages),
            "coingecko_exchanges_max_pages": int(cg_exchanges_max_pages),
            "dry_run": bool(args.dry_run),
        },
        "stages": [asdict(s) for s in stages],
        "sources": sources,
    }

    report_json = reports_dir / "coverage_summary.json"
    report_md = reports_dir / "coverage_summary.md"
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_md.write_text(_build_markdown_report(report), encoding="utf-8")

    print(f"[pipeline] wrote {report_json}")
    print(f"[pipeline] wrote {report_md}")
    for s in stages:
        print(f"[pipeline] stage={s.name} enabled={s.enabled} exit={s.exit_code} note={s.note}")

    if args.strict and any(s.enabled and s.exit_code != 0 for s in stages):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
