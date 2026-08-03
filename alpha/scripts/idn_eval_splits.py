"""Panel-relative train/OOS splits for IDX research — no calendar-year hardcodes."""

from __future__ import annotations

from typing import Any

import pandas as pd

OOS_FRAC_DEFAULT = 0.25
ERA_FULL = "full"
ERA_TRAIN = "train"
ERA_OOS = "oos_holdout"
ERA_NAMES = (ERA_FULL, ERA_TRAIN, ERA_OOS)


def time_cutoff(
    times: pd.Series,
    *,
    oos_frac: float = OOS_FRAC_DEFAULT,
) -> pd.Timestamp:
    """First timestamp of the last ``oos_frac`` slice (discrete panel weeks/days)."""
    t = pd.to_datetime(times).dropna().sort_values().unique()
    if len(t) == 0:
        raise ValueError("empty timeline")
    n_holdout = max(1, int(round(len(t) * oos_frac)))
    if n_holdout >= len(t):
        n_holdout = max(1, len(t) // 4)
    return pd.Timestamp(t[-n_holdout]).normalize()


def build_eras(
    df: pd.DataFrame,
    *,
    time_col: str = "week_end",
    oos_frac: float = OOS_FRAC_DEFAULT,
) -> tuple[tuple[str, str | None, str | None], ...]:
    """(name, start_inclusive, end_exclusive) slices from actual panel extent."""
    cut = time_cutoff(df[time_col], oos_frac=oos_frac)
    cut_s = str(cut.date())
    return (
        (ERA_FULL, None, None),
        (ERA_TRAIN, None, cut_s),
        (ERA_OOS, cut_s, None),
    )


def era_bounds(
    df: pd.DataFrame,
    era: str,
    *,
    time_col: str = "week_end",
    oos_frac: float = OOS_FRAC_DEFAULT,
) -> tuple[str | None, str | None]:
    eras = {name: (a, b) for name, a, b in build_eras(df, time_col=time_col, oos_frac=oos_frac)}
    if era not in eras:
        raise KeyError(f"unknown era {era!r}; expected one of {list(eras)}")
    return eras[era]


def era_slice(
    df: pd.DataFrame,
    start: str | None,
    end: str | None,
    *,
    time_col: str = "week_end",
) -> pd.DataFrame:
    out = df
    if start:
        out = out[out[time_col] >= pd.Timestamp(start)]
    if end:
        out = out[out[time_col] < pd.Timestamp(end)]
    return out


def slice_era(
    df: pd.DataFrame,
    era: str,
    *,
    time_col: str = "week_end",
    oos_frac: float = OOS_FRAC_DEFAULT,
) -> pd.DataFrame:
    start, end = era_bounds(df, era, time_col=time_col, oos_frac=oos_frac)
    return era_slice(df, start, end, time_col=time_col)


def split_meta(
    df: pd.DataFrame,
    *,
    time_col: str = "week_end",
    oos_frac: float = OOS_FRAC_DEFAULT,
) -> dict[str, Any]:
    """Summary for reports: cut date, row counts, week counts."""
    cut = time_cutoff(df[time_col], oos_frac=oos_frac)
    t = pd.to_datetime(df[time_col])
    train = df[t < cut]
    oos = df[t >= cut]
    return {
        "oos_frac": oos_frac,
        "cutoff": str(cut.date()),
        "timeline_min": str(t.min().date()),
        "timeline_max": str(t.max().date()),
        "train_rows": int(len(train)),
        "oos_rows": int(len(oos)),
        "train_weeks": int(train[time_col].nunique()) if time_col in train.columns else None,
        "oos_weeks": int(oos[time_col].nunique()) if time_col in oos.columns else None,
    }


def min_weeks_for_era(era: str, *, default_train: int = 30, default_oos: int = 8) -> int:
    if era == ERA_OOS:
        return default_oos
    if era == ERA_TRAIN:
        return default_train
    return default_train
