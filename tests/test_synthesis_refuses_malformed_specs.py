#!/usr/bin/env python3
"""The refusals, as a committed set rather than a session result.

"20 of 20 malformed specs refused" was measured once in a session and cited repeatedly.
Review was right that no committed adversarial set backed it. This is that set: every case
must be refused, and the sandbox-escape cases are the ones that matter — a derive expression
is eval-backed, so an accepted escape is arbitrary execution against the data lake.
"""

from __future__ import annotations

import pytest

from scripts.research_data_mcp.synthesis_executor import validate_execution_spec

SPINE = "cross_asset_fused_primary_panel"


def _spec(**kw):
    base = {
        "input_dataset_id": SPINE,
        "output_dataset_id": "synthesis_adversarial_probe_001",
        "metrics": [{"function": "count", "as": "n"}],
        "transforms": [],
        "group_by": [],
    }
    base.update(kw)
    return base


def _derive(expr):
    return [{"op": "derive", "as": "z", "expr": expr}]


ACCEPTED = (
    ("minimal count", _spec()),
    ("dispersion", _spec(metrics=[{"function": "std", "as": "sd", "column": "x"}])),
    ("quantile", _spec(metrics=[{"function": "quantile", "as": "p90", "column": "x", "q": 0.9}])),
    ("whitelisted expression", _spec(transforms=_derive("round(abs(x), 2)"))),
)

REFUSED = (
    ("no metrics", _spec(metrics=[])),
    ("output id not prefixed", _spec(output_dataset_id="not_prefixed")),
    ("output equals input", _spec(output_dataset_id=SPINE)),
    ("unknown metric function", _spec(metrics=[{"function": "kurtosis", "as": "k", "column": "x"}])),
    ("duplicate metric alias", _spec(metrics=[{"function": "count", "as": "n"},
                                              {"function": "sum", "as": "n", "column": "x"}])),
    ("alias collides with group key", _spec(group_by=["g"], metrics=[{"function": "count", "as": "g"}])),
    ("non-count metric without column", _spec(metrics=[{"function": "mean", "as": "m"}])),
    ("quantile without q", _spec(metrics=[{"function": "quantile", "as": "q", "column": "x"}])),
    ("quantile q out of range", _spec(metrics=[{"function": "quantile", "as": "q", "column": "x", "q": 1.7}])),
    ("unknown transform op", _spec(transforms=[{"op": "pivot", "by": "x"}])),
    ("transform cap exceeded", _spec(transforms=[{"op": "head", "n": 5}] * 17)),
    ("filter with bad comparator", _spec(transforms=[{"op": "filter", "column": "x", "cmp": "~=", "value": 1}])),
    # sandbox escapes — an accepted one of these is arbitrary execution
    ("escape: import", _spec(transforms=_derive("__import__('os').system('id')"))),
    ("escape: attribute walk", _spec(transforms=_derive("x.__class__.__mro__"))),
    ("escape: lambda", _spec(transforms=_derive("(lambda: 1)()"))),
    ("escape: comprehension", _spec(transforms=_derive("[i for i in range(9)]"))),
    ("escape: f-string", _spec(transforms=_derive("f'{x}'"))),
    ("escape: subscript", _spec(transforms=_derive("x[0]"))),
    ("escape: builtins via globals", _spec(transforms=_derive("globals()"))),
    ("unsupported: ternary", _spec(transforms=_derive("1 if x else 2"))),
    ("unsupported: chained compare", _spec(transforms=_derive("1 < x < 3"))),
)


@pytest.mark.parametrize("label,spec", REFUSED, ids=[c[0] for c in REFUSED])
def test_every_malformed_spec_is_refused(label, spec):
    with pytest.raises(ValueError):
        validate_execution_spec(dict(spec))


@pytest.mark.parametrize("label,spec", ACCEPTED, ids=[c[0] for c in ACCEPTED])
def test_valid_specs_still_pass(label, spec):
    validate_execution_spec(dict(spec))


def test_the_escape_cases_are_actually_covered():
    """A guard that only counts is not evidence; name what must stay blocked."""
    escapes = [label for label, _ in REFUSED if label.startswith("escape:")]
    assert len(escapes) >= 7, escapes
