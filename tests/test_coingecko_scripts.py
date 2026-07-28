from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_bulk_collect_load_env_value_reads_explicit_dotenv(monkeypatch, tmp_path):
    mod = _load_module("coingecko_bulk_collect_test", "scripts/coingecko_bulk_collect.py")
    env_file = tmp_path / ".env.local"
    env_file.write_text("export COINGECKO_API_KEY='CG-test-key'\n", encoding="utf-8")
    monkeypatch.setenv("COINGECKO_API_KEY", "CG-host-key")

    assert mod.load_env_value("COINGECKO_API_KEY", env_path=env_file) == "CG-test-key"


def test_bulk_collect_client_sets_user_agent_and_api_key(monkeypatch):
    mod = _load_module("coingecko_bulk_collect_test_headers", "scripts/coingecko_bulk_collect.py")
    seen = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode("utf-8")

    def fake_urlopen(req, timeout):
        headers = {k.lower(): v for k, v in req.header_items()}
        seen["user_agent"] = headers.get("user-agent")
        seen["api_key"] = headers.get("x-cg-pro-api-key")
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)

    client = mod.CoinGeckoClient(
        base_url=mod.PRO_BASE_URL,
        api_key="CG-test-key",
        timeout_s=9,
        min_interval_s=0.0,
    )

    assert client.get("/ping") == {"ok": True}
    assert seen["user_agent"] == mod.DEFAULT_USER_AGENT
    assert seen["api_key"] == "CG-test-key"
    assert seen["timeout"] == 9


def test_crypto_data_pipeline_load_env_value_reads_explicit_dotenv(monkeypatch, tmp_path):
    mod = _load_module("crypto_data_pipeline_test", "scripts/crypto_data_pipeline.py")
    env_file = tmp_path / ".env.local"
    env_file.write_text('COINGECKO_API_KEY="CG-pipeline-key"\n', encoding="utf-8")
    monkeypatch.setenv("COINGECKO_API_KEY", "CG-host-key")

    assert mod._load_env_value("COINGECKO_API_KEY", env_path=env_file) == "CG-pipeline-key"
