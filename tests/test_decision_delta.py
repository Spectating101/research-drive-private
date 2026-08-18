"""Whether a choice changed the finding is measured, not judged.

The desk resolves routine choices and stops for consequential ones, and which is
which used to be the agent's opinion. A preview costs about two seconds, so both
branches can be run and compared instead. These pin the rule that separates them,
including the case that defeated the first version.
"""

from __future__ import annotations

import pandas as pd

from scripts.research_data_mcp.synthesis.decision_delta import compare, explain


def frame(**columns):
    return pd.DataFrame(columns)


def test_an_identical_output_needs_nobody(tmp_path=None):
    left = frame(g=["a", "b"], m=[1.0, 2.0])
    result = compare(left, left.copy())
    assert result["verdict"] == "no material change"
    assert explain(result) == "the output is unchanged, so this was resolved without asking you"


def test_a_hundredfold_rescale_is_material():
    result = compare(frame(g=["a", "b"], m=[1.0, 2.0]), frame(g=["a", "b"], m=[100.0, 200.0]))
    assert result["verdict"] == "material"
    assert "m" in explain(result)


def test_a_rescale_on_a_zero_median_column_is_still_caught():
    """supply_growth_wow_pct has median 0.0 in the real registry. Comparing medians
    alone reported no change while the mean went 311,165 to 3,111."""
    before = frame(g=list("abcd"), m=[0.0, 0.0, 0.0, 400.0])
    after = frame(g=list("abcd"), m=[0.0, 0.0, 0.0, 4.0])
    assert before["m"].median() == 0.0 and after["m"].median() == 0.0
    result = compare(before, after)
    assert result["verdict"] == "material"
    assert result["material"][0]["summary"] == "mean"


def test_dropping_rows_is_material():
    result = compare(frame(g=["a", "b"], m=[1.0, 2.0]), frame(g=["a"], m=[1.0]))
    assert result["verdict"] == "material"
    assert "2 rows become 1" in explain(result)


def test_a_shift_below_the_threshold_is_resolved_without_asking():
    before = frame(g=["a", "b"], m=[100.0, 100.0])
    after = frame(g=["a", "b"], m=[100.0, 100.4])
    assert compare(before, after)["verdict"] == "no material change"


def test_the_threshold_is_stated_and_can_be_argued_with():
    before = frame(g=["a", "b"], m=[100.0, 100.0])
    after = frame(g=["a", "b"], m=[100.0, 100.4])
    strict = compare(before, after, value_threshold=0.0001)
    assert strict["verdict"] == "material"
    assert strict["value_threshold"] == 0.0001


def test_a_metric_that_disappears_is_material():
    result = compare(frame(g=["a"], m=[1.0]), frame(g=["a"], other=[1.0]))
    assert result["verdict"] == "material"
    assert "absent" in explain(result)


def test_a_non_numeric_column_is_not_compared_as_a_number():
    before = frame(g=["a", "b"], label=["x", "y"])
    after = frame(g=["a", "b"], label=["p", "q"])
    assert compare(before, after)["verdict"] == "no material change"


def test_the_reason_names_the_metric_and_both_values():
    result = compare(frame(g=["a"], m=[1.0]), frame(g=["a"], m=[100.0]))
    reason = explain(result)
    assert "m" in reason and "1" in reason and "100" in reason


def test_an_empty_output_on_one_side_is_material():
    result = compare(frame(g=["a", "b"], m=[1.0, 2.0]), frame(g=[], m=[]))
    assert result["verdict"] == "material"
