"""CI-only native MCP acceptance with an explicitly synthetic registry.

Run in a disposable checkout: native bootstrap can initialize checkout-local state.
This never copies a live registry, queries a provider, or claims host deployment.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from portfolio_mcp.client import PortfolioSession, StdioConnection

ROOT = Path(__file__).resolve().parents[2]
DATASET = "synthetic_portfolio_dataset"


def result_object(response: dict) -> dict:
    assert not response["is_error"], response
    value = response.get("structured_content")
    if value is None:
        blocks = response["content"]
        assert len(blocks) == 1 and blocks[0]["type"] == "text", blocks
        value = json.loads(blocks[0]["text"])
    assert isinstance(value, dict), value
    return value


async def exercise(engine_python: str) -> None:
    with tempfile.TemporaryDirectory(prefix="research-mcp-synthetic-") as directory:
        scratch = Path(directory)
        dataset_path = scratch / "observations.csv"
        dataset_path.write_text("item,value\nalpha,10\nbeta,20\n", encoding="utf-8")
        # The native CSV backend returns inferred numeric values, not csv module strings.
        expected_rows = [{"item": "alpha", "value": 10}, {"item": "beta", "value": 20}]
        registry = scratch / "synthetic-registry.json"
        registry.write_text(json.dumps({
            "schema": "portfolio.mcp.synthetic-registry.v1",
            "synthetic": True,
            "datasets": [{
                "dataset_id": DATASET,
                "name": "Synthetic portfolio integration dataset",
                "description": "Synthetic numbers for protocol acceptance only.",
                "backend": "local_csv_file",
                "local_path": str(dataset_path),
                "analysis_readiness": "instant",
                "access_shape": "local_file",
                "synthetic": True,
            }],
        }), encoding="utf-8")
        original_registry = registry.read_bytes()
        env = dict(os.environ, SHARPE_REGISTRY_PATH=str(registry),
                   RESEARCH_MCP_SYNTHESIS_READ_ONLY="true")
        command = ("-m", "portfolio_mcp.cli", "serve", "--manifest",
                   str(ROOT / "integrations/mcp/manifest.json"), "--root", str(ROOT),
                   "--engine-python", engine_python)
        connection = StdioConnection(sys.executable, command, env, str(ROOT))
        async with asyncio.timeout(90):
            async with PortfolioSession(connection) as session:
                catalog = await session.inspect()
                names = {tool["name"] for tool in catalog["tools"]}
                assert {"research_list_datasets", "research_describe_dataset", "research_query_dataset"} <= names
                assert "research_synthesis_run" not in names
                listing = result_object(await session.invoke("research_list_datasets", {}))
                # Synthetic rows may intentionally be hidden from the desk view.
                assert listing["authority_summary"]["registry_total"] == 1, listing
                described = result_object(await session.invoke("research_describe_dataset", {"dataset_id": DATASET}))
                assert described["dataset_id"] == DATASET, described
                queried = result_object(await session.invoke("research_query_dataset", {
                    "dataset_id": DATASET, "params_json": json.dumps({"limit": 2}),
                }))
                assert queried["dataset_id"] == DATASET, queried
                assert queried["rows"] == expected_rows, queried
                assert all(type(row["value"]) is int for row in queried["rows"]), queried
        assert registry.read_bytes() == original_registry, "Read-only query changed the fixture registry"
        missing = scratch / "does-not-exist.json"
        native_env = dict(env, SHARPE_REGISTRY_PATH=str(missing),
                          PYTHONPATH=os.pathsep.join(str(ROOT / p) for p in ("drive", "kernel", ".")))
        failed = subprocess.run(
            [engine_python, "-m", "scripts.research_data_mcp.server", "--transport", "stdio"],
            cwd=ROOT, env=native_env, input="", capture_output=True, text=True, timeout=30,
        )
        assert failed.returncode != 0, "Missing registry unexpectedly started"
        assert "SHARPE_REGISTRY_PATH" in failed.stderr, failed.stderr
        assert not missing.exists(), "Startup fabricated a missing registry"
        print(json.dumps({
            "schema": "portfolio.mcp.acceptance.v1",
            "project": "research-drive", "synthetic": True,
            "checks": ["native_discovery", "registry_override", "native_describe",
                       "native_csv_query_exact_rows", "native_numeric_types", "read_only_tool_profile",
                       "registry_unchanged", "missing_registry_fails_closed"],
            "live_registry_used": False, "deployment_verified": False,
        }))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-python", required=True)
    args = parser.parse_args()
    asyncio.run(exercise(args.engine_python))
