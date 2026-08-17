"""What the engine measured has to reach whoever judges the result.

The executor records source_rows, rows_aggregated, a per-step row ledger, as-of
match rates and masked non-finite counts. All of it went into the manifest and
none of it into the thread, so the model reading a thread could not tell an
aggregate over 50 of 1000 rows from one over all of them. Measuring is worth
nothing if the reader is blind to the measurement.

The engine still judges none of it. A 12% match rate is reported, not refused.
"""

from __future__ import annotations

from scripts.research_data_mcp.synthesis_thread_store import build_materialisation_view

MEASURED = {
    "source_rows": 5694,
    "rows_aggregated": 2387,
    "row_ledger": [{"step": 1, "op": "filter", "rows_in": 5694, "rows_out": 2387}],
    "asof_coverage": [{"right_dataset_id": "b", "match_rate_pct": 50.0,
                       "unmatched_rows": 1, "undated_left_rows_dropped": 1}],
    "undefined_derived_values": {"ratio": 1},
}


def _thread(**execution):
    base = {"status": "registered", "job_id": "j1", "output_dataset_id": "synthesis_demo",
            "rows": 13, "drive_verified": True, "manifest_id": "m1"}
    base.update(execution)
    return {"id": "t1", "state": {"materialisation": "registered", "execution": base}}


def test_the_reader_sees_how_many_rows_the_aggregate_covered():
    view = build_materialisation_view(_thread(measured=MEASURED))
    assert view["measured"]["source_rows"] == 5694
    assert view["measured"]["rows_aggregated"] == 2387


def test_the_reader_sees_where_the_rows_went():
    view = build_materialisation_view(_thread(measured=MEASURED))
    assert view["measured"]["row_ledger"][0]["op"] == "filter"


def test_the_reader_sees_the_asof_match_rate():
    view = build_materialisation_view(_thread(measured=MEASURED))
    assert view["measured"]["asof_coverage"][0]["match_rate_pct"] == 50.0


def test_the_reader_sees_values_that_blew_up():
    view = build_materialisation_view(_thread(measured=MEASURED))
    assert view["measured"]["undefined_derived_values"] == {"ratio": 1}


def test_a_weak_match_is_reported_not_refused():
    """The engine states the number. Whoever reads it decides if it is enough."""
    weak = dict(MEASURED, asof_coverage=[{"right_dataset_id": "b", "match_rate_pct": 12.0}])
    view = build_materialisation_view(_thread(measured=weak))
    assert view["measured"]["asof_coverage"][0]["match_rate_pct"] == 12.0
    assert view["output_registered"] is True


def test_a_thread_with_no_execution_invents_no_measurements():
    view = build_materialisation_view({"id": "t2", "state": {}})
    assert view["measured"] == {}
    assert view["output_registered"] is False


def test_an_execution_recorded_without_measurements_reports_empty_not_absent():
    view = build_materialisation_view(_thread())
    assert view["measured"] == {}
    assert view["execution_recorded"] is True
