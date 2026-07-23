#!/usr/bin/env python3
"""Build IDX behavioral episode + reward dataset (short horizon, cross-ref panel)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_episode_reward_lib import (  # noqa: E402
    OUT_DIR,
    action_policy_summary,
    audit_data_lineage,
    build_episode_dataset,
    episode_reward_summary,
    fit_simple_behavioral_scores,
    fry_spike_lifecycle_table,
)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = build_episode_dataset()
    out_parquet = OUT_DIR / "daily_episodes.parquet"
    df.to_parquet(out_parquet, index=False)

    by_state = episode_reward_summary(df)
    by_action = action_policy_summary(df)
    model = fit_simple_behavioral_scores(df)
    lifecycle = fry_spike_lifecycle_table(df)
    lineage = audit_data_lineage(df)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": len(df),
        "symbols": int(df["yahoo_symbol"].nunique()),
        "date_min": str(df["date"].min().date()),
        "date_max": str(df["date"].max().date()),
        "name_type_counts": df["name_type"].value_counts().to_dict(),
        "episode_state_top": by_state.head(15).to_dict(orient="records"),
        "action_policy": by_action.to_dict(orient="records") if not by_action.empty else [],
        "behavioral_model": model,
        "fry_lifecycle": lifecycle.to_dict(orient="records"),
        "data_lineage": lineage,
        "parquet": str(out_parquet.relative_to(REPO)),
    }

    out_json = REPO / "backtests/outputs/idn_behavior_model/latest.json"
    out_md = REPO / "backtests/outputs/idn_behavior_model/latest.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# IDX behavioral episode + reward",
        "",
        f"- Rows: **{payload['rows']:,}** | symbols: {payload['symbols']}",
        f"- Range: {payload['date_min']} → {payload['date_max']}",
        "",
        "## Name types",
        "",
    ]
    for k, v in payload["name_type_counts"].items():
        lines.append(f"- {k}: {v:,}")
    lines.extend(["", "## Episode states (mean 20d reward %)", ""])
    for row in payload["episode_state_top"][:12]:
        lines.append(
            f"- **{row['episode_state']}**: n={row['n']:,} "
            f"5d={row['mean_5d']:.2f}% 20d={row['mean_20d']:.2f}% "
            f"win20={row['win_20d']*100:.0f}%"
        )
    lines.extend(["", "## Rule actions (fires only)", ""])
    for row in payload["action_policy"]:
        lines.append(
            f"- **{row['suggested_action']}**: n={row['n']:,} "
            f"20d={row['mean_20d']:.2f}% win20={row['win_20d']*100:.0f}%"
        )
    bm = payload["behavioral_model"]
    if "error" not in bm:
        lines.extend(
            [
                "",
                "## Simple behavioral model (train first 75%, OOS last 25%)",
                "",
                f"- Train through: {bm.get('train_end', 'n/a')} | OOS from: {bm.get('oos_start', 'n/a')}",
                f"- Train rows: {bm.get('train_rows', 'n/a'):,} | OOS rows: {bm.get('oos_rows', 'n/a'):,}",
                f"- OOS fires: {bm['oos_fires']:,}",
                f"- OOS mean 20d when fired: **{bm['oos_mean_20d_when_fired']}%**",
                f"- OOS win 20d when fired: **{bm['oos_win_20d_when_fired']}%**",
                f"- OOS bench mean 20d: {bm['oos_bench_mean_20d']}%",
            ]
        )
    lines.extend(["", "## Fry spike lifecycle (+10% / +25% day forward)", ""])
    for row in payload.get("fry_lifecycle", [])[:20]:
        lines.append(
            f"- **{row['event']}** {row['name_type']}: n={row['n']} "
            f"5d={row['mean_5d']}% 20d={row['mean_20d']}% win20={row['win_20d']}%"
        )
    lin = payload.get("data_lineage", {})
    lines.extend(["", "## Data coverage (honest)", ""])
    uni = lin.get("universe", {})
    lines.append(f"- Universe: {uni.get('episode_universe_n')} symbols (+{uni.get('added_vs_liquid')})")
    for row in lin.get("weekly_crossref_by_year", [])[-3:]:
        lines.append(
            f"- {row['year']}: entity_tone {row['entity_tone_pct']}% | "
            f"broadcast_news {row['broadcast_news_pct']}% | prior_return {row['prior_return_pct']}%"
        )
    for g in lin.get("known_gaps", [])[:6]:
        lines.append(f"- gap: {g}")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "rows": len(df), "json": str(out_json)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
