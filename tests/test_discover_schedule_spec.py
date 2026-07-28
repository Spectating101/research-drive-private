from scripts.research_data_mcp.discover_schedule_spec import (
    build_schedule_spec,
    compute_next_run_at,
    infer_cadence,
)


def test_monday_1000_weekly_cron():
    spec = build_schedule_spec(requested_schedule="every Monday at 10:00", cadence="weekly")
    assert spec["schedule_type"] == "cron"
    assert spec["cron"] == "0 10 * * 1"
    assert spec["timezone"] == "Asia/Taipei"
    assert spec["executable"] is False
    assert spec["inferred"] is True
    assert compute_next_run_at(spec) is None


def test_daily_infer():
    assert infer_cadence("refresh daily at 9am") == "daily"
    spec = build_schedule_spec(requested_schedule="every day at 9:30", cadence="daily")
    assert spec["cron"] == "30 9 * * *"


def test_explicit_cron():
    spec = build_schedule_spec(
        requested_schedule="faculty wording",
        cadence="weekly",
        explicit={"cron": "0 10 * * 1", "timezone": "Asia/Taipei"},
    )
    assert spec["inferred"] is False
    assert spec["cron"] == "0 10 * * 1"
    assert spec["executable"] is False
