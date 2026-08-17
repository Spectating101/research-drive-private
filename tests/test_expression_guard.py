"""A derive expression operates on whole columns, so anything asking for the
truth of one has to be refused before the job runs.

and/or was already refused with "use & and |". A ternary and a chained
comparison fail identically — "the truth value of a Series is ambiguous" — and
both passed preflight clean and died in the approved job.

Also pins the sandbox: the expression namespace is evaluated with eval, and the
AST whitelist is what makes that safe.
"""

from __future__ import annotations

import pytest

from scripts.research_data_mcp.synthesis_executor import expression_functions, validate_expression


@pytest.mark.parametrize("expr", ["0 < v < 10", "1 <= v < 5", "a < b < c"])
def test_a_chained_comparison_is_refused(expr):
    with pytest.raises(ValueError, match="chain comparisons with &"):
        validate_expression(expr)


@pytest.mark.parametrize("expr", ["v if v else 0", "if_else(v > 1, v if v else 0, 0)"])
def test_a_ternary_is_refused(expr):
    with pytest.raises(ValueError, match="use if_else"):
        validate_expression(expr)


def test_and_or_stays_refused():
    with pytest.raises(ValueError, match="use & and |"):
        validate_expression("v and 1")


@pytest.mark.parametrize("expr", [
    "v > 1",
    "(v > 1) & (v < 10)",
    "if_else(v > 1, v, 0)",
    "v * 2 + 1",
    "ntile(v, 10)",
    "rank_pct(v)",
    "sqrt(abs(v))",
])
def test_legitimate_expressions_still_pass(expr):
    _tree, reads = validate_expression(expr)
    assert reads


@pytest.mark.parametrize("expr", [
    "v.__class__",
    "v.__class__.__mro__",
    "__import__('os')",
    "open('/etc/passwd')",
    "eval('1+1')",
    "v.apply(print)",
    "(lambda: 1)()",
    "[x for x in v]",
    "(x for x in v)",
    "(y := v)",
    "v[0]",
    "f'{v}'",
    "month(v, tz='UTC')",
])
def test_the_sandbox_refuses_every_escape(expr):
    """eval runs these, so the whitelist is the only thing standing in the way."""
    with pytest.raises(ValueError):
        validate_expression(expr)


def test_an_expression_must_read_a_column():
    with pytest.raises(ValueError, match="must read at least one column"):
        validate_expression("1 + 1")


def test_the_function_namespace_is_reported_in_the_error():
    """A researcher guessing a function name should be told what exists."""
    with pytest.raises(ValueError, match="available:"):
        validate_expression("nonexistent_fn(v)")


def test_ranking_helpers_are_present():
    """ntile and rank_pct make deciles and percentile ranks expressible."""
    available = set(expression_functions())
    assert {"ntile", "rank_pct", "log", "sqrt", "coalesce", "date_trunc"} <= available
