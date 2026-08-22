#!/usr/bin/env python3
"""The desk loaded a researcher's domains and ranked nothing by them.

profile_score_adjustment existed with no caller: 22 statements of careful soft
ranking, and discover_search resolved the profile only for Composer hints. On
this desk's real faculty profile it moves 6 of 12 rows for "daily returns and
fundamentals" and 11 of 11 for "taiwan listed companies".

Only the boost half is applied. Measured here, the demote half dropped FaIR
climate calibration by -1.20 on a "carbon emissions by country" query, because
climate is not one of the profile's domains — burying the best answer to the
question actually asked.
"""

from __future__ import annotations

import ast
import inspect

from scripts.research_data_mcp.faculty_profile import profile_score_adjustment

PROFILE = {"domain_tags": ["equities", "taiwan_market", "fintech"]}


def test_the_adjustment_boosts_a_row_in_the_researchers_domain():
    row = {"title": "TWSE listed stocks valuation ratios", "dataset_id": "twse_valuation"}
    assert profile_score_adjustment(row, "taiwan listed companies", PROFILE) > 0


def test_no_profile_means_no_adjustment():
    row = {"title": "anything"}
    assert profile_score_adjustment(row, "q", None) == 0.0


def test_discover_search_applies_the_boost():
    """The whole point: it is reachable now."""
    from scripts.research_data_mcp.gateway import ResearchDataGateway

    src = inspect.getsource(ResearchDataGateway.discover_search)
    assert "profile_score_adjustment" in src, "profile ranking must be reachable from discover"


def test_only_positive_adjustments_are_applied():
    """Promoting what a researcher works on is helpful; hiding what they
    explicitly asked for is not."""
    from scripts.research_data_mcp.gateway import ResearchDataGateway

    tree = ast.parse(inspect.getsource(ResearchDataGateway.discover_search).lstrip())
    guarded = False
    for node in ast.walk(tree):
        # look for `if boost > 0:` guarding the score mutation
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            left = node.test.left
            if isinstance(left, ast.Name) and left.id == "boost":
                ops = node.test.ops
                if ops and isinstance(ops[0], ast.Gt):
                    guarded = True
    assert guarded, "a negative profile adjustment must not be applied to search scores"


def test_a_failing_adjustment_cannot_break_search():
    from scripts.research_data_mcp.gateway import ResearchDataGateway

    tree = ast.parse(inspect.getsource(ResearchDataGateway.discover_search).lstrip())
    protected = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and node.handlers:
            calls = {
                n.func.id for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            }
            if "profile_score_adjustment" in calls:
                protected = True
    assert protected, "ranking must survive a bad profile row"
