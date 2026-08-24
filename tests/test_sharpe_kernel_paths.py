from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ALPHA_SCRIPT = REPO / "alpha" / "scripts" / "platform_status.py"


def test_repo_root_from_alpha_script_resolves_to_monorepo_root():
    sys.path.insert(0, str(REPO / "kernel"))
    from sharpe_kernel.paths import bootstrap_repo_paths, repo_root_from_file

    root = repo_root_from_file(ALPHA_SCRIPT)
    assert root == REPO
    assert (root / "kernel").is_dir()
    assert (root / "drive").is_dir()
    assert (root / "alpha").is_dir()


def test_bootstrap_repo_paths_puts_kernel_and_alpha_on_syspath():
    sys.path.insert(0, str(REPO / "kernel"))
    from sharpe_kernel.paths import bootstrap_repo_paths

    root = bootstrap_repo_paths(ALPHA_SCRIPT)
    assert root == REPO
    assert str(REPO / "kernel") in sys.path
    assert str(REPO / "alpha") in sys.path
    assert str(REPO) in sys.path
    assert bootstrap_repo_paths(ALPHA_SCRIPT) == root


def test_build_ticker_pulse_handles_null_nested_fields():
    sys.path.insert(0, str(REPO / "kernel"))
    sys.path.insert(0, str(REPO / "alpha"))
    from scripts.idn_social_sentiment_collector import build_ticker_pulse

    out = build_ticker_pulse(
        liquid=["BBCA.JK"],
        cfg={"aliases": {}},
        providers={
            "rapidapi_symbol_intel": {
                "symbols": [
                    {
                        "yahoo_symbol": "BBCA.JK",
                        "technical": None,
                        "accumulation": None,
                        "distribution": None,
                    }
                ]
            }
        },
    )
    assert len(out) == 1
    assert out[0]["yahoo_symbol"] == "BBCA.JK"
