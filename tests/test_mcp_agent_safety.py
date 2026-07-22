from __future__ import annotations

import pytest

from scripts.research_data_mcp.tool_handlers import ResearchToolHandlers


class _Gateway:
    def __init__(self) -> None:
        self.archive_calls: list[dict] = []
        self.hf_calls: list[dict] = []

    def archive_to_gdrive(self, local_path: str, **kwargs: object) -> dict:
        self.archive_calls.append({"local_path": local_path, **kwargs})
        return {"job": {"status": "pending_approval"}}

    def collect_huggingface_dataset(self, dataset_id: str, **kwargs: object) -> dict:
        self.hf_calls.append({"dataset_id": dataset_id, **kwargs})
        return {"job": {"status": "pending_approval"}, "approval_required": True}


class _Stack:
    def __init__(self, gateway: _Gateway) -> None:
        self.gateway = gateway


def test_huggingface_tool_cannot_request_agent_execution() -> None:
    gateway = _Gateway()
    handler = ResearchToolHandlers(_Stack(gateway))

    result = handler.huggingface_collect_dataset("org/demo", auto_execute=True)

    assert result["approval_required"] is True
    assert gateway.hf_calls == [{"dataset_id": "org/demo", "split": "train", "auto_execute": False}]


def test_archive_tool_rejects_agent_approval() -> None:
    gateway = _Gateway()
    handler = ResearchToolHandlers(_Stack(gateway))

    with pytest.raises(PermissionError, match="Archive approval"):
        handler.yzu_archive_to_gdrive("data_lake/example", auto_approve=True)

    assert gateway.archive_calls == []


def test_archive_tool_submits_pending_job_by_default() -> None:
    gateway = _Gateway()
    handler = ResearchToolHandlers(_Stack(gateway))

    result = handler.yzu_archive_to_gdrive("data_lake/example")

    assert result["job"]["status"] == "pending_approval"
    assert gateway.archive_calls == [
        {
            "local_path": "data_lake/example",
            "remote_suffix": "",
            "verify": True,
            "auto_approve": False,
        }
    ]
