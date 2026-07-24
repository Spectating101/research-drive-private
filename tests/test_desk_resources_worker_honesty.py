"""Resources must not present stale Windows workers as available capacity."""

from scripts.research_data_mcp.desk_resources import _windows_lab_worker_rollup


def test_stale_windows_workers_are_joined_but_not_available() -> None:
    rollup = _windows_lab_worker_rollup(
        [
            {
                "status": "idle",
                "inventory_status": "joined",
                "freshness": {"state": "stale", "age_seconds": 3600},
            }
            for _ in range(3)
        ]
    )

    assert rollup["stale"] == 3
    assert rollup["online"] == 0
    assert rollup["idle"] == 0
    assert rollup["available"] == 0


def test_fresh_online_and_idle_workers_are_available() -> None:
    rollup = _windows_lab_worker_rollup(
        [
            {"status": "online", "freshness": {"state": "fresh", "age_seconds": 12}},
            {"status": "idle", "freshness": {"state": "fresh", "age_seconds": 40}},
            {"status": "joined_unseen", "freshness": None},
        ]
    )

    assert rollup == {
        "online": 1,
        "idle": 1,
        "stale": 0,
        "joined_unseen": 1,
        "available": 2,
    }
