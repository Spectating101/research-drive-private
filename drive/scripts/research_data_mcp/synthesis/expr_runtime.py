"""One definition of the derive expression operators, for both consumers.

The engine had these as Python and the exported script embedded a second copy as
text. The copies drifted: 21 of 23 were missing from the script, and ntile
bucketed a rank there and the raw series on the desk, so the same spec on the
same bytes produced different buckets.

Here they exist once, as source text. The engine execs it to get callables; the
renderer embeds the identical text in the script it hands the researcher. They
cannot disagree, because there is only one of them.

The text needs `np` and `pd` in scope and nothing else — that is what lets the
exported script stay standalone.
"""

from __future__ import annotations

from typing import Any

RUNTIME_SOURCE = '''
def _expr_functions():
    """The callable surface a derive expression may reach.

    Adding an entry here widens what can be expressed on the desk and in the
    exported script at the same time; nothing else in the grammar changes.
    """
    periods = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}

    def dt(series):
        return pd.to_datetime(series, errors="coerce")

    def date_trunc(series, unit):
        key = str(unit).lower()
        if key not in periods:
            raise ValueError("date_trunc unit must be one of " + str(sorted(periods)))
        return dt(series).dt.to_period(periods[key]).astype(str)

    def substr(series, start, length=None):
        start = int(start)
        stop = start + int(length) if length is not None else None
        return series.astype(str).str[start:stop]

    def concat(*parts):
        out = None
        for part in parts:
            piece = part.astype(str) if hasattr(part, "astype") else str(part)
            out = piece if out is None else out + piece
        return out

    def if_else(cond, when_true, when_false):
        return pd.Series(np.where(cond, when_true, when_false), index=cond.index)

    def ntile(series, buckets):
        return pd.qcut(series, int(buckets), labels=False, duplicates="drop") + 1

    return {
        "date_trunc": date_trunc,
        "year": lambda s: dt(s).dt.year,
        "month": lambda s: dt(s).dt.month,
        "quarter": lambda s: dt(s).dt.quarter,
        "day_of_week": lambda s: dt(s).dt.dayofweek,
        "lower": lambda s: s.astype(str).str.lower(),
        "upper": lambda s: s.astype(str).str.upper(),
        "strip": lambda s: s.astype(str).str.strip(),
        "substr": substr,
        "replace": lambda s, old, new: s.astype(str).str.replace(str(old), str(new), regex=False),
        "contains": lambda s, pat: s.astype(str).str.contains(str(pat), na=False),
        "concat": concat,
        "length": lambda s: s.astype(str).str.len(),
        "abs": lambda s: s.abs(),
        "round": lambda s, digits=0: s.round(int(digits)),
        "clip": lambda s, low, high: s.clip(low, high),
        "log": lambda s: np.log(s.where(s > 0)),
        "sqrt": lambda s: np.sqrt(s.where(s >= 0)),
        "if_else": if_else,
        "coalesce": lambda a, b: a.fillna(b),
        "is_null": lambda s: s.isna(),
        "rank_pct": lambda s: s.rank(pct=True),
        "ntile": ntile,
    }
'''


def functions() -> dict[str, Any]:
    """Callables from RUNTIME_SOURCE — the same text the exported script carries."""
    import numpy as np
    import pandas as pd

    namespace: dict[str, Any] = {"np": np, "pd": pd}
    exec(RUNTIME_SOURCE, namespace)  # noqa: S102 - this module's own text, not input
    return namespace["_expr_functions"]()
