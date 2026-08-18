import json

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis_executor import (
    _apply_derive,
    _apply_transforms,
    preflight_execution_spec,
    validate_execution_spec,
)
from scripts.yzu_cluster.acquisitions import _materialized_description


def fake_repo(tmp_path):
    """A repo root with one concrete local input, so preflight actually reads columns."""
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    frame().to_csv(tmp_path / "data/src.csv", index=False)
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "src_panel", "local_path": "data/src.csv"}]}),
        encoding="utf-8",
    )
    return tmp_path


def spec(**over):
    base = {
        "input_dataset_id": "src_panel",
        "output_dataset_id": "synthesis_depeg_intensity_v1",
        "group_by": ["issuer"],
        "metrics": [{"function": "sum", "column": "is_depeg", "as": "depeg_days"}],
        "transforms": [
            {"op": "derive", "as": "is_depeg", "fn": "indicator", "column": "dev", "cmp": "gt", "value": 0.005}
        ],
    }
    base.update(over)
    return base


def frame():
    return pd.DataFrame(
        {
            "issuer": ["a", "a", "b", "b"],
            "dev": [0.01, 0.001, 0.0, 0.002],
            "mentions": [4, 6, 0, 5],
            "total": [10, 10, 0, 10],
        }
    )


def test_indicator_then_sum_keeps_zero_groups():
    """The reason derive exists: filter+count deletes units with no events."""
    normalized = validate_execution_spec(spec())
    out = _apply_transforms(None, {}, frame(), normalized["transforms"])
    grouped = out.groupby("issuer")["is_depeg"].sum().to_dict()
    assert grouped == {"a": 1, "b": 0}


def test_filter_then_count_loses_the_zero_group():
    """Documents the old idiom's failure so nobody reintroduces it."""
    normalized = validate_execution_spec(
        spec(transforms=[{"op": "filter", "column": "dev", "cmp": "gt", "value": 0.005}])
    )
    out = _apply_transforms(None, {}, frame(), normalized["transforms"])
    assert set(out["issuer"]) == {"a"}


def test_div_by_zero_is_not_a_number():
    step = {"op": "derive", "as": "share", "fn": "div", "column": "mentions", "by_column": "total"}
    out = _apply_derive(frame(), validate_execution_spec(spec(transforms=[step]))["transforms"][0])
    assert out["share"].isna().sum() == 1
    assert not (out["share"].abs() == float("inf")).any()


def test_arithmetic_against_a_constant():
    step = {"op": "derive", "as": "scaled", "fn": "mul", "column": "mentions", "value": 10}
    out = _apply_derive(frame(), validate_execution_spec(spec(transforms=[step]))["transforms"][0])
    assert list(out["scaled"]) == [40, 60, 0, 50]


def test_derive_rejects_expressions_and_unknown_fns():
    with pytest.raises(ValueError, match="derive fn must be one of"):
        validate_execution_spec(spec(transforms=[{"op": "derive", "as": "x", "fn": "eval", "column": "dev"}]))


def test_derive_requires_exactly_one_operand():
    both = {"op": "derive", "as": "x", "fn": "add", "column": "dev", "by_column": "mentions", "value": 1}
    with pytest.raises(ValueError, match="exactly one of by_column or value"):
        validate_execution_spec(spec(transforms=[both]))


def test_derive_will_not_overwrite_an_existing_column():
    step = {"op": "derive", "as": "dev", "fn": "abs", "column": "dev"}
    normalized = validate_execution_spec(spec(transforms=[step]))["transforms"][0]
    with pytest.raises(ValueError, match="would overwrite"):
        _apply_derive(frame(), normalized)


def test_proxy_is_optional_but_must_be_complete_when_present():
    assert validate_execution_spec(spec())["proxy"] is None
    with pytest.raises(ValueError, match="proxy requires limitations"):
        validate_execution_spec(
            spec(proxy={"stands_in_for": "attention", "construction": "counts", "limitations": []})
        )


def test_proxy_cannot_claim_validated_fitness():
    with pytest.raises(ValueError, match="nothing in this system measures proxy fitness"):
        validate_execution_spec(
            spec(
                proxy={
                    "stands_in_for": "attention",
                    "construction": "counts",
                    "limitations": ["threshold chosen, not estimated"],
                    "fitness": "validated",
                }
            )
        )


def test_proxy_defaults_to_untested():
    declared = validate_execution_spec(
        spec(
            proxy={
                "stands_in_for": "de-peg episode incidence",
                "construction": "daily indicator summed to issuer-month",
                "limitations": ["threshold chosen, not estimated"],
            }
        )
    )["proxy"]
    assert declared["fitness"] == "untested"


def test_registry_description_states_the_stand_in():
    job = {"id": "abc123"}
    plan = {"job_type": "synthesis_execute"}
    materialized = {
        "proxy": {
            "stands_in_for": "investor attention",
            "construction": "count of mentions per issuer-day",
            "limitations": ["ecological at firm level"],
            "fitness": "untested",
        }
    }
    described = _materialized_description(job, plan, materialized)
    assert "Proxy for investor attention" in described
    assert "not a direct measurement" in described
    assert "ecological at firm level" in described
    assert "does not validate" in described


def test_preflight_catches_a_derive_on_a_missing_column(tmp_path):
    report = preflight_execution_spec(
        fake_repo(tmp_path),
        spec(
            transforms=[
                {"op": "derive", "as": "is_spike", "fn": "indicator", "column": "absent", "cmp": "gt", "value": 1}
            ],
            metrics=[{"function": "sum", "column": "is_spike", "as": "spike_days"}],
        ),
    )
    assert report["ok"] is False
    codes = {(i["code"], i.get("op"), i.get("column")) for i in report["issues"]}
    assert ("missing_column", "derive", "absent") in codes


def test_preflight_accepts_aggregating_a_derived_column(tmp_path):
    """The derived column must be visible to the aggregate check, or every proxy fails preflight."""
    report = preflight_execution_spec(fake_repo(tmp_path), spec())
    assert report["issues"] == []
    assert report["ok"] is True


def test_preflight_flags_a_derive_that_shadows_an_input_column(tmp_path):
    report = preflight_execution_spec(
        fake_repo(tmp_path),
        spec(transforms=[{"op": "derive", "as": "dev", "fn": "abs", "column": "dev"}]),
    )
    assert any(i["code"] == "column_conflict" for i in report["issues"])


EXPRESSIBLE = [
    ("day to month grain", "date_trunc(date,'month')"),
    ("key normalisation", "lower(strip(issuer))"),
    ("share of total", "mentions / total"),
    ("dummy variable", "dev > 0.005"),
    ("conditional bucket", "if_else(dev > 0.005, 'stress', 'calm')"),
    ("deciles", "ntile(mentions, 2)"),
    ("composite key", "concat(lower(issuer), '_', date_trunc(date,'quarter'))"),
    ("log with domain guard", "log(mentions)"),
]

REFUSED = [
    ("attribute escape", "dev.__class__", "may not use Attribute"),
    ("import escape", "__import__('os')", "may only call named functions|unknown function"),
    ("subscript", "dev[0]", "may not use Subscript"),
    ("lambda", "(lambda: 1)()", "may only call named functions"),
    ("comprehension", "[x for x in dev]", "may not use ListComp"),
    ("unknown function", "eval('1')", "unknown function"),
    ("reads no column", "1 + 1", "must read at least one column"),
    ("python and/or", "dev > 1 and dev < 2", "use & and |"),
]


@pytest.mark.parametrize("label,expr", EXPRESSIBLE, ids=[x[0] for x in EXPRESSIBLE])
def test_composer_can_express_it(label, expr):
    step = validate_execution_spec(spec(transforms=[{"op": "derive", "as": "x", "expr": expr}]))["transforms"][0]
    assert step["reads"], f"{label} should declare the columns it reads"


@pytest.mark.parametrize("label,expr,message", REFUSED, ids=[x[0] for x in REFUSED])
def test_sandbox_escapes_stay_refused(label, expr, message):
    with pytest.raises(ValueError, match=message):
        validate_execution_spec(spec(transforms=[{"op": "derive", "as": "x", "expr": expr}]))


def test_grain_change_end_to_end():
    """The case that was impossible before: a daily source rolled to issuer-month."""
    daily = pd.DataFrame(
        {
            "issuer": ["A ", "a", "B", "b"],
            "date": ["2026-01-04", "2026-01-19", "2026-02-02", "2026-02-11"],
            "dev": [0.01, 0.001, 0.0, 0.02],
        }
    )
    normalized = validate_execution_spec(
        spec(
            group_by=["key", "month"],
            metrics=[{"function": "sum", "column": "is_depeg", "as": "depeg_days"}],
            transforms=[
                {"op": "derive", "as": "key", "expr": "lower(strip(issuer))"},
                {"op": "derive", "as": "month", "expr": "date_trunc(date,'month')"},
                {"op": "derive", "as": "is_depeg", "expr": "dev > 0.005"},
            ],
        )
    )
    out = _apply_transforms(None, {}, daily, normalized["transforms"])
    rolled = out.groupby(["key", "month"])["is_depeg"].sum().to_dict()
    assert rolled == {("a", "2026-01"): 1, ("b", "2026-02"): 1}


def test_expression_reading_a_missing_column_fails_before_it_runs():
    step = validate_execution_spec(
        spec(transforms=[{"op": "derive", "as": "x", "expr": "absent_col * 2"}])
    )["transforms"][0]
    with pytest.raises(ValueError, match="reads missing columns"):
        _apply_derive(frame(), step)


def test_expression_and_typed_form_are_mutually_exclusive():
    with pytest.raises(ValueError, match="either expr or fn/column"):
        validate_execution_spec(
            spec(transforms=[{"op": "derive", "as": "x", "expr": "dev * 2", "fn": "abs", "column": "dev"}])
        )


def test_expression_inf_becomes_nan():
    step = validate_execution_spec(
        spec(transforms=[{"op": "derive", "as": "share", "expr": "mentions / total"}])
    )["transforms"][0]
    out = _apply_derive(frame(), step)
    assert out["share"].isna().sum() == 1
    assert not (out["share"].abs() == float("inf")).any()


def test_drop_duplicates_is_available():
    normalized = validate_execution_spec(
        spec(transforms=[{"op": "drop_duplicates", "columns": ["issuer"]}])
    )
    out = _apply_transforms(None, {}, frame(), normalized["transforms"])
    assert list(out["issuer"]) == ["a", "b"]


def test_registry_description_without_proxy_is_unchanged():
    described = _materialized_description({"id": "abc123"}, {"job_type": "synthesis_execute"}, {})
    assert described == "Materialised by synthesis execution job `abc123`."
