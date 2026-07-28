from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INTEGRATION = REPO / "alpha" / "config" / "platform_integration.json"
CYCLE = REPO / "alpha" / "scripts" / "run_unified_platform_cycle.py"


@pytest.fixture
def integration_cfg() -> dict:
    return json.loads(INTEGRATION.read_text(encoding="utf-8"))


def test_platform_integration_tightened_governance(integration_cfg: dict) -> None:
    ga = integration_cfg["global_alpha"]
    assert ga["promotion_gate"] == "block"
    assert ga["control_profile"] == "defensive_live"
    assert ga.get("on_block_fallback") == "beta_core"
    assert integration_cfg.get("alpha_fuel", {}).get("enabled") is True

    idn = integration_cfg["idn_sleeve"]
    assert idn["operator_brief"] is False
    assert idn["operator_aggressive"] is False
    assert idn["operator_llm"] == "skip"
    assert idn["bandar_confirm"] == "prefer"
    assert idn["max_single_name_weight"] == 0.25
    assert idn.get("max_tilt_symbols") == 12
    assert idn.get("signal_universe") == "tradable"


def test_defensive_live_profile_caps_crypto() -> None:
    sys.path.insert(0, str(REPO / "alpha"))
    from src.strategy.control_profiles import resolve_profile

    prof = resolve_profile("defensive_live")
    assert prof["max_crypto_gross"] == 0.35
    assert prof["min_cash_weight"] == 0.10


def test_unified_cycle_global_alpha_cmd_includes_policy_flags() -> None:
    proc = subprocess.run(
        [sys.executable, str(CYCLE), "--dry-run", "--skip-fetch", "--skip-idn", "--skip-news", "--skip-audit"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env={
            **dict(__import__("os").environ),
            "PYTHONPATH": f"{REPO / 'kernel'}:{REPO / 'alpha'}:{REPO}",
        },
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    manifest = json.loads((REPO / "backtests/outputs/platform/latest.json").read_text(encoding="utf-8"))
    global_step = next(s for s in manifest["steps"] if s["label"] == "global_alpha")
    cmd = " ".join(global_step["cmd"])
    assert "--promotion-gate" in cmd and "block" in cmd
    assert "--on-block-fallback" in cmd and "beta_core" in cmd
    assert "--control-profile" in cmd and "defensive_live" in cmd
    labels = {s["label"] for s in manifest["steps"]}
    assert "alpha_fuel_inventory" in labels
    assert "idn_operator_brief" not in labels
