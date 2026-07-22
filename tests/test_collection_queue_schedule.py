from __future__ import annotations

import json
from pathlib import Path

from scripts.yzu_cluster.executor import collection_queue_runner
from scripts.yzu_cluster.scheduler import YzuScheduler


ROOT = Path(__file__).resolve().parents[1]


def test_split_checkout_resolves_root_queue_runner() -> None:
    runner = collection_queue_runner(ROOT)
    assert runner == ROOT / "scripts/run_data_collection_queue.py"


def test_daily_schedule_targets_a_deployed_public_task() -> None:
    config = json.loads((ROOT / "drive/config/yzu_cluster.json").read_text(encoding="utf-8"))
    schedule = next(item for item in config["schedules"] if item["id"] == "public_collection_daily")
    plan = schedule["plan"]
    assert plan["job_type"] == "collection_queue_batch"
    assert plan["only"] == ["sec_company_tickers"]

    queue = json.loads((ROOT / "drive/config/data_collection_queue.json").read_text(encoding="utf-8"))
    task = next(item for item in queue["tasks"] if item["id"] == "sec_company_tickers")
    assert task["enabled"] is True
    assert (ROOT / task["command"][1]).exists()


def test_manual_schedule_run_uses_a_retry_key(tmp_path: Path) -> None:
    config = {
        "controller": {"status_root": "status"},
        "schedules": [{
            "id": "daily",
            "enabled": True,
            "interval_hours": 24,
            "plan": {"job_type": "collection_queue_batch"},
        }],
    }
    scheduler = YzuScheduler(tmp_path, config)
    scheduled = scheduler.build_emission("daily", now_ts=1_800_000_000, force=False)
    manual = scheduler.build_emission("daily", now_ts=1_800_000_000, force=True)
    assert scheduled["idempotency_key"] == "sched:daily:20833"
    assert manual["idempotency_key"].startswith("sched:daily:manual-")
    assert manual["idempotency_key"] != scheduled["idempotency_key"]
