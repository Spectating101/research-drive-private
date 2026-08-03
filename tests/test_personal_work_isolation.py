from __future__ import annotations

import sqlite3

import pytest

from scripts.research_data_mcp.desk_auth import desk_principal_context
from scripts.research_data_mcp.desk_principal import DeskPrincipal
from scripts.research_data_mcp.discover_intent_store import DiscoverIntentStore
from scripts.research_data_mcp.procurement_session import ProcurementSessionStore
from scripts.research_data_mcp.synthesis_thread_store import SynthesisThreadStore


ALICE = DeskPrincipal(
    principal_id="alice",
    email="alice@example.test",
    display_name="Alice",
    role="member",
)
BOB = DeskPrincipal(
    principal_id="bob",
    email="bob@example.test",
    display_name="Bob",
    role="member",
)
OPERATOR = DeskPrincipal(
    principal_id="operator",
    email="operator@example.test",
    display_name="Operator",
    role="operator",
)


def test_ask_session_is_private_and_operator_visible(tmp_path):
    store = ProcurementSessionStore(tmp_path / "ask.sqlite3")
    with desk_principal_context(ALICE):
        session = store.create(title="Alice question")
        store.append_message(session["id"], "user", "private question")
        assert store.messages(session["id"])[0]["content"] == "private question"
        assert session["owner_id"] == "alice"

    with desk_principal_context(BOB):
        with pytest.raises(KeyError):
            store.get(session["id"])
        with pytest.raises(KeyError):
            store.messages(session["id"])
        with pytest.raises(KeyError):
            store.update_state(session["id"], {"candidates": []})

    with desk_principal_context(OPERATOR):
        assert store.get(session["id"])["owner_id"] == "alice"


def test_discover_intent_is_private_and_lists_are_scoped(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover.sqlite3")
    with desk_principal_context(ALICE):
        intent = store.create(research_need="Find an event dataset")
        assert [row["id"] for row in store.list()] == [intent["id"]]
        assert intent["owner_id"] == "alice"

    with desk_principal_context(BOB):
        assert store.list() == []
        with pytest.raises(KeyError):
            store.get(intent["id"])
        with pytest.raises(KeyError):
            store.select_route(intent["id"], "guessed-route")

    with desk_principal_context(OPERATOR):
        assert [row["id"] for row in store.list()] == [intent["id"]]


def test_synthesis_thread_is_private_and_lists_are_scoped(tmp_path):
    store = SynthesisThreadStore(tmp_path / "synthesis.sqlite3")
    with desk_principal_context(ALICE):
        thread = store.create(objective="Construct a proxy panel")
        assert [row["id"] for row in store.list()] == [thread["id"]]
        assert thread["owner_id"] == "alice"

    with desk_principal_context(BOB):
        assert store.list() == []
        with pytest.raises(KeyError):
            store.get(thread["id"])
        with pytest.raises(KeyError):
            store.set_proposal(thread["id"], None)

    with desk_principal_context(OPERATOR):
        assert [row["id"] for row in store.list()] == [thread["id"]]


def test_ownerless_legacy_records_are_operator_only(tmp_path):
    store = ProcurementSessionStore(tmp_path / "legacy.sqlite3")
    with desk_principal_context(None):
        legacy = store.create(title="pre-migration")
    assert legacy["owner_id"] == ""

    with desk_principal_context(ALICE):
        with pytest.raises(KeyError):
            store.get(legacy["id"])

    with desk_principal_context(OPERATOR):
        assert store.get(legacy["id"])["id"] == legacy["id"]


def test_existing_databases_gain_owner_column_without_rewriting_records(tmp_path):
    ask_path = tmp_path / "legacy-ask.sqlite3"
    discover_path = tmp_path / "legacy-discover.sqlite3"
    synthesis_path = tmp_path / "legacy-synthesis.sqlite3"

    with sqlite3.connect(ask_path) as db:
        db.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, created_at TEXT, "
            "updated_at TEXT, title TEXT, state_json TEXT)"
        )
    with sqlite3.connect(discover_path) as db:
        db.execute(
            "CREATE TABLE discover_intents (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, title TEXT NOT NULL, research_need TEXT NOT NULL, "
            "session_id TEXT, user_email TEXT, state_json TEXT NOT NULL)"
        )
    with sqlite3.connect(synthesis_path) as db:
        db.execute(
            "CREATE TABLE synthesis_threads (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, title TEXT, objective TEXT NOT NULL, session_id TEXT, "
            "conversation_id TEXT, materialisation TEXT NOT NULL, state_json TEXT NOT NULL)"
        )

    ProcurementSessionStore(ask_path)
    DiscoverIntentStore(discover_path)
    SynthesisThreadStore(synthesis_path)

    for path, table in (
        (ask_path, "sessions"),
        (discover_path, "discover_intents"),
        (synthesis_path, "synthesis_threads"),
    ):
        with sqlite3.connect(path) as db:
            columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        assert "owner_id" in columns
