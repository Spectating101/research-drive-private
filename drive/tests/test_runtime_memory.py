from pathlib import Path

from scripts.research_data_mcp.credential_vault import vault_path
from scripts.research_data_mcp.desk_activity import log_path
from scripts.research_data_mcp.desk_runtime import desk_active_path
from scripts.research_data_mcp.desk_usage import ledger_path
from scripts.research_data_mcp.discover_intent_store import discover_intent_store_path
from scripts.research_data_mcp.discover_refresh_store import discover_refresh_store_path
from scripts.research_data_mcp.procured_dataset import pins_path
from scripts.research_data_mcp.procurement_cache import ProcurementCache
from scripts.research_data_mcp.procurement_chat_core import ProcurementChatOrchestrator
from scripts.research_data_mcp.runtime_memory import (
    procurement_memory_path,
    procurement_memory_root,
)
from scripts.research_data_mcp.synthesis_thread_store import default_synthesis_thread_db


def test_procurement_memory_defaults_to_checkout_for_development(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_DRIVE_MEMORY_ROOT", raising=False)
    monkeypatch.delenv("YZU_RUNTIME_DRIVE_ROOT", raising=False)

    assert procurement_memory_root(tmp_path) == tmp_path / "data_lake/procurement_memory"
    assert procurement_memory_path(tmp_path, "chat.sqlite3") == (
        tmp_path / "data_lake/procurement_memory/chat.sqlite3"
    )


def test_runtime_drive_owns_all_mutable_desk_memory(tmp_path, monkeypatch):
    checkout = tmp_path / "immutable-release"
    runtime = tmp_path / "runtime-authority"
    monkeypatch.delenv("RESEARCH_DRIVE_MEMORY_ROOT", raising=False)
    monkeypatch.setenv("YZU_RUNTIME_DRIVE_ROOT", str(runtime))
    expected = runtime / "data_lake/procurement_memory"

    assert procurement_memory_root(checkout) == expected
    assert default_synthesis_thread_db(checkout) == expected / "synthesis_threads.sqlite3"
    assert discover_intent_store_path(checkout) == expected / "discover_intents.sqlite3"
    assert discover_refresh_store_path(checkout) == expected / "discover_refresh_subscriptions.sqlite3"
    assert vault_path(checkout) == expected / "credentials.json"
    assert log_path(checkout) == expected / "desk_activity.jsonl"
    assert desk_active_path(checkout) == expected / "desk_active.json"
    assert ledger_path(checkout) == expected / "desk_usage.json"
    assert pins_path(checkout) == expected / "pins.json"
    assert ProcurementCache(checkout).root == expected / "cache"

    chat = ProcurementChatOrchestrator(checkout)
    assert chat.sessions.path == expected / "chat_sessions.sqlite3"


def test_explicit_memory_root_overrides_runtime_drive(tmp_path, monkeypatch):
    checkout = tmp_path / "immutable-release"
    runtime = tmp_path / "runtime-authority"
    explicit = tmp_path / "dedicated-private-state"
    monkeypatch.setenv("YZU_RUNTIME_DRIVE_ROOT", str(runtime))
    monkeypatch.setenv("RESEARCH_DRIVE_MEMORY_ROOT", str(explicit))

    assert procurement_memory_root(checkout) == explicit


def test_relative_explicit_memory_root_is_checkout_relative(tmp_path, monkeypatch):
    monkeypatch.delenv("YZU_RUNTIME_DRIVE_ROOT", raising=False)
    monkeypatch.setenv("RESEARCH_DRIVE_MEMORY_ROOT", "host-state/private")

    assert procurement_memory_root(tmp_path) == (tmp_path / "host-state/private").resolve()
