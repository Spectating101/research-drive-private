"""The embedding model costs ~9s to load and the corpus ~5s to embed. Both were
once paid by whichever user searched first after a restart, which timed out the
client and rendered as a false "0 results". These assert the warmup stays wired."""

import ast
from pathlib import Path

DRIVE = Path(__file__).resolve().parents[1]
SERVER = DRIVE / "scripts/research_query_engine/server.py"
PREFETCH = DRIVE / "scripts/research_data_mcp/datacite_prefetch.py"
SEMANTIC = DRIVE / "scripts/research_data_mcp/semantic_index.py"


def _fn(tree, name):
    return next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name),
        None,
    )


def _calls(node):
    return {
        c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", "")
        for c in ast.walk(node)
        if isinstance(c, ast.Call)
    }


def test_main_starts_the_warmup():
    main = _fn(ast.parse(SERVER.read_text()), "main")
    assert main is not None
    assert "_start_search_warmup" in _calls(main)


def test_warmup_runs_off_the_request_path():
    tree = ast.parse(SERVER.read_text())
    warm = _fn(tree, "_start_search_warmup")
    assert warm is not None
    threads = [
        c
        for c in ast.walk(warm)
        if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "Thread"
    ]
    assert threads, "warmup must not block serve_forever"
    assert any(
        k.arg == "daemon" and getattr(k.value, "value", None) is True
        for t in threads
        for k in t.keywords
    ), "warmup thread must be a daemon so shutdown is not held open"


def test_warmup_covers_both_cold_costs():
    warm = _fn(ast.parse(SERVER.read_text()), "_start_search_warmup")
    called = _calls(warm)
    assert "warm_search_indexes" in called
    assert "discover_search" in called, "corpus embeddings only warm via a real search"


def test_prefetch_warms_the_embedding_model():
    warm = _fn(ast.parse(PREFETCH.read_text()), "warm_search_indexes")
    assert warm is not None
    assert "warm_embedding_model" in _calls(warm)


def test_warm_embedding_model_exists():
    assert _fn(ast.parse(SEMANTIC.read_text()), "warm_embedding_model") is not None
