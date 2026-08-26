from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, got {count}")
    return text.replace(old, new, 1)

# 1) Preserve trusted Composer proposal origin through researcher acceptance.
rel = "drive/scripts/research_data_mcp/tool_handlers.py"
s = read(rel)
s = replace_once(
    s,
    "            node_id=node_id,\n            execution_spec=execution_spec,\n        )",
    "            node_id=node_id,\n            execution_spec=execution_spec,\n            origin={\n                \"kind\": \"llm_tool_call\",\n                \"authority\": \"composer\",\n                \"tool\": \"research_synthesis_propose_state\",\n            },\n        )",
    "tool handler origin",
)
write(rel, s)

rel = "drive/scripts/research_data_mcp/gateway.py"
s = read(rel)
s = replace_once(
    s,
    "        node_id: str = \"\",\n        execution_spec: dict | None = None,\n    ) -> dict:\n        \"\"\"Persist a Composer proposal for explicit researcher review only.\"\"\"",
    "        node_id: str = \"\",\n        execution_spec: dict | None = None,\n        origin: dict | None = None,\n    ) -> dict:\n        \"\"\"Persist a Composer proposal for explicit researcher review only.\"\"\"",
    "gateway proposal signature",
)
s = replace_once(
    s,
    "        if reason:\n            proposal[\"reason\"] = reason",
    "        if origin:\n            proposal[\"origin\"] = {\n                \"kind\": str(origin.get(\"kind\") or \"\")[:80],\n                \"authority\": str(origin.get(\"authority\") or \"\")[:80],\n                \"tool\": str(origin.get(\"tool\") or \"\")[:120],\n            }\n        if reason:\n            proposal[\"reason\"] = reason",
    "gateway proposal origin",
)
s = replace_once(
    s,
    "            \"preview_input_revisions\": list((state.get(\"preview\") or {}).get(\"input_revisions\") or []),\n            \"dataset_id\": spec[\"output_dataset_id\"],",
    "            \"preview_input_revisions\": list((state.get(\"preview\") or {}).get(\"input_revisions\") or []),\n            \"method_origin\": dict(state.get(\"method_origin\") or {}),\n            \"dataset_id\": spec[\"output_dataset_id\"],",
    "execution plan method origin",
)
# Direct retrieval of the immutable method artifact tied to the active completed job.
s = replace_once(
    s,
    "    def synthesis_thread_materialisation(self, thread_id: str) -> dict:\n        return self._synthesis_thread_store().materialisation(thread_id)\n\n    def synthesis_thread_record_execution",
    '''    def synthesis_thread_materialisation(self, thread_id: str) -> dict:\n        return self._synthesis_thread_store().materialisation(thread_id)\n\n    def synthesis_thread_method_export(self, thread_id: str) -> dict:\n        \"\"\"Return the exact frozen method.py for the thread's completed execution.\n\n        This never asks Composer to regenerate code. The bytes must be the artifact\n        written by the production executor and their checksum must still match the\n        recorded execution result.\n        \"\"\"\n        thread = self._synthesis_thread_store().get(thread_id)\n        state = thread.get(\"state\") or {}\n        execution = state.get(\"execution\") or {}\n        job_id = str(execution.get(\"job_id\") or \"\")\n        if not job_id:\n            raise ValueError(\"no completed Synthesis execution is attached to this thread\")\n        job = self.jobs.get(job_id)\n        if job.get(\"status\") != \"completed\":\n            raise ValueError(\"method export is available only after execution completes\")\n        result = job.get(\"result\") or {}\n        repro = result.get(\"reproducibility\") or {}\n        method_rel = str(repro.get(\"method_path\") or \"\").strip()\n        if not method_rel:\n            raise ValueError(\"completed execution has no frozen method artifact\")\n        method_path = (Path(self.repo_root) / method_rel).resolve()\n        root = Path(self.repo_root).resolve()\n        if not method_path.is_relative_to(root) or not method_path.is_file():\n            raise ValueError(\"frozen method artifact is missing or outside the repository root\")\n        script = method_path.read_text(encoding=\"utf-8\")\n        actual_sha = hashlib.sha256(script.encode(\"utf-8\")).hexdigest()\n        expected_sha = str(repro.get(\"method_sha256\") or \"\")\n        if not expected_sha or actual_sha != expected_sha:\n            raise ValueError(\"frozen method checksum does not match the execution record\")\n        return {\n            \"thread_id\": thread_id,\n            \"job_id\": job_id,\n            \"filename\": method_path.name,\n            \"script\": script,\n            \"sha256\": actual_sha,\n            \"spec_hash\": str(repro.get(\"spec_hash\") or state.get(\"accepted_spec_hash\") or \"\"),\n            \"method_origin\": dict(repro.get(\"method_origin\") or state.get(\"method_origin\") or {}),\n            \"deterministic_export\": True,\n            \"generated_by_llm\": False,\n            \"note\": \"Method was proposed through Composer, researcher-accepted, then deterministically rendered from the accepted execution spec.\",\n        }\n\n    def synthesis_thread_record_execution''',
    "gateway method export",
)
write(rel, s)

rel = "drive/scripts/research_data_mcp/synthesis_thread_store.py"
s = read(rel)
s = replace_once(
    s,
    "        next_state[\"accepted_spec_hash\"] = hashlib.sha256(\n            json.dumps(next_state[\"execution_spec\"], sort_keys=True, separators=(\",\", \":\")).encode(\"utf-8\")\n        ).hexdigest()\n        # A new accepted spec starts a new execution revision.",
    "        next_state[\"accepted_spec_hash\"] = hashlib.sha256(\n            json.dumps(next_state[\"execution_spec\"], sort_keys=True, separators=(\",\", \":\")).encode(\"utf-8\")\n        ).hexdigest()\n        origin = prop.get(\"origin\") if isinstance(prop.get(\"origin\"), dict) else {}\n        next_state[\"method_origin\"] = {\n            \"kind\": str(origin.get(\"kind\") or \"proposal\"),\n            \"authority\": str(origin.get(\"authority\") or \"\"),\n            \"tool\": str(origin.get(\"tool\") or \"\"),\n            \"proposal_id\": str(prop.get(\"id\") or \"\"),\n            \"proposal_hash\": str(prop.get(\"proposal_hash\") or \"\"),\n            \"proposal_title\": str(prop.get(\"title\") or \"\"),\n        }\n        # A new accepted spec starts a new execution revision.",
    "accepted method origin",
)
write(rel, s)

# 2) Production execution freezes method.py beside output + manifest.
rel = "drive/scripts/research_data_mcp/synthesis_executor.py"
s = read(rel)
s = replace_once(
    s,
    "    manifest = out_dir / \"manifest.json\"\n    manifest.write_text(",
    '''    from scripts.research_data_mcp.synthesis.spec_export import fingerprint_path, render_script, spec_hash\n\n    referenced_ids = [spec[\"input_dataset_id\"]]\n    for step in spec.get(\"transforms\") or []:\n        right_id = str(step.get(\"right_dataset_id\") or \"\").strip()\n        if right_id and right_id not in referenced_ids:\n            referenced_ids.append(right_id)\n    method_inputs: dict[str, dict[str, Any]] = {}\n    for dataset_id in referenced_ids:\n        source_row = _registry_row(registry, dataset_id)\n        source_path = _ensure_local_file(repo_root, source_row)\n        method_inputs[dataset_id] = fingerprint_path(source_path)\n    method_text = render_script(spec, method_inputs, runnable_on_desk=True)\n    method_text += (\n        \"\\n# Persist the independently reproduced result in the current directory.\\n\"\n        + f\"result.to_parquet({(str(spec['output_dataset_id']) + '.parquet')!r}, index=False)\\n\"\n    )\n    method = out_dir / \"method.py\"\n    method.write_text(method_text, encoding=\"utf-8\")\n    method_sha = hashlib.sha256(method_text.encode(\"utf-8\")).hexdigest()\n    method_spec_hash = spec_hash(spec)\n    method_origin = dict(plan.get(\"method_origin\") or {})\n\n    manifest = out_dir / \"manifest.json\"\n    manifest.write_text(''',
    "executor method artifact",
)
s = replace_once(
    s,
    "                \"execution_spec\": spec,\n                \"proxy\": spec.get(\"proxy\"),",
    "                \"execution_spec\": spec,\n                \"reproducibility\": {\n                    \"method_path\": str(method.relative_to(repo_root)),\n                    \"method_sha256\": method_sha,\n                    \"spec_hash\": method_spec_hash,\n                    \"method_origin\": method_origin,\n                    \"generator\": \"deterministic_spec_export\",\n                },\n                \"proxy\": spec.get(\"proxy\"),",
    "manifest reproducibility",
)
s = replace_once(
    s,
    "        \"output_manifest_id\": f\"synthesis_manifest_{job_id}\",\n        \"undefined_derived_values\": undefined,",
    "        \"output_manifest_id\": f\"synthesis_manifest_{job_id}\",\n        \"reproducibility\": {\n            \"method_path\": str(method.relative_to(repo_root)),\n            \"method_sha256\": method_sha,\n            \"spec_hash\": method_spec_hash,\n            \"method_origin\": method_origin,\n            \"generator\": \"deterministic_spec_export\",\n        },\n        \"undefined_derived_values\": undefined,",
    "result reproducibility",
)
s = replace_once(
    s,
    "            \"files\": [{\"name\": \"output.parquet\", \"path\": str(parquet.relative_to(repo_root)), \"bytes\": parquet.stat().st_size}],",
    "            \"files\": [\n                {\"name\": \"output.parquet\", \"path\": str(parquet.relative_to(repo_root)), \"bytes\": parquet.stat().st_size},\n                {\"name\": \"method.py\", \"path\": str(method.relative_to(repo_root)), \"bytes\": method.stat().st_size},\n            ],",
    "materialized method file",
)
write(rel, s)

# Stream input fingerprints instead of read_bytes so reproducibility does not add a giant RAM spike.
rel = "drive/scripts/research_data_mcp/synthesis/spec_export.py"
s = read(rel)
s = replace_once(
    s,
    "        try:\n            data = f.read_bytes()\n        except Exception as exc:  # noqa: BLE001\n            return {\"path\": str(p), \"fingerprint\": None, \"files\": len(files), \"bytes\": 0, \"note\": f\"unreadable: {exc}\"}\n        total += len(data)\n        if not single:\n            digest.update(f.name.encode(\"utf-8\"))\n        digest.update(data)",
    "        try:\n            if not single:\n                digest.update(f.name.encode(\"utf-8\"))\n            with f.open(\"rb\") as handle:\n                while True:\n                    chunk = handle.read(1024 * 1024)\n                    if not chunk:\n                        break\n                    total += len(chunk)\n                    digest.update(chunk)\n        except Exception as exc:  # noqa: BLE001\n            return {\"path\": str(p), \"fingerprint\": None, \"files\": len(files), \"bytes\": 0, \"note\": f\"unreadable: {exc}\"}",
    "stream fingerprints",
)
write(rel, s)

# 3) HTTP exposes the exact artifact; browser-supplied proposals cannot spoof Composer origin.
rel = "drive/scripts/research_data_mcp/http_router.py"
s = read(rel)
s = replace_once(
    s,
    '    {"method": "GET", "path": "/library/synthesis/threads/{thread_id}/materialisation", "handler": "library_synthesis_thread_materialisation"},\n    {"method": "POST", "path": "/library/synthesis/threads/{thread_id}/execute", "handler": "library_synthesis_thread_execute"},',
    '    {"method": "GET", "path": "/library/synthesis/threads/{thread_id}/materialisation", "handler": "library_synthesis_thread_materialisation"},\n    {"method": "GET", "path": "/library/synthesis/threads/{thread_id}/method", "handler": "library_synthesis_thread_method"},\n    {"method": "POST", "path": "/library/synthesis/threads/{thread_id}/execute", "handler": "library_synthesis_thread_execute"},',
    "method route catalog",
)
s = replace_once(
    s,
    "        return stack.gateway.synthesis_thread_set_proposal(\n            params[\"thread_id\"],\n            proposal if isinstance(proposal, dict) else None,\n        )",
    "        if isinstance(proposal, dict):\n            proposal = dict(proposal)\n            # Browser/HTTP callers cannot self-assert that a proposal came from Composer.\n            proposal.pop(\"origin\", None)\n        return stack.gateway.synthesis_thread_set_proposal(\n            params[\"thread_id\"],\n            proposal if isinstance(proposal, dict) else None,\n        )",
    "strip untrusted origin",
)
s = replace_once(
    s,
    "    def library_synthesis_thread_materialisation(stack, query, payload, params):\n        return stack.gateway.synthesis_thread_materialisation(params[\"thread_id\"])\n\n    def library_synthesis_thread_execute",
    "    def library_synthesis_thread_materialisation(stack, query, payload, params):\n        return stack.gateway.synthesis_thread_materialisation(params[\"thread_id\"])\n\n    def library_synthesis_thread_method(stack, query, payload, params):\n        return stack.gateway.synthesis_thread_method_export(params[\"thread_id\"])\n\n    def library_synthesis_thread_execute",
    "method handler",
)
write(rel, s)

# 4) Targeted backend contract tests.
test = r'''from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from scripts.research_data_mcp.synthesis_executor import execute
from scripts.research_data_mcp.synthesis_thread_store import accept_proposal, validate_synthesis_proposal
from scripts.research_data_mcp.tool_handlers import ResearchToolHandlers


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "data").mkdir(parents=True)
    frame = pd.DataFrame({"entity_id": ["a", "a", "b"], "week": [1, 2, 1], "value": [1.0, 3.0, 5.0]})
    frame.to_parquet(tmp_path / "data/base.parquet", index=False)
    (tmp_path / "config/research_query_registry.json").write_text(json.dumps({"datasets": [{
        "dataset_id": "base", "name": "Base", "local_path": "data/base.parquet", "grain": "entity-week", "join_keys": ["entity_id", "week"]
    }]}), encoding="utf-8")
    return tmp_path


def _spec():
    return {
        "input_dataset_id": "base",
        "output_dataset_id": "synthesis_method_export_v1",
        "group_by": ["entity_id"],
        "metrics": [{"function": "mean", "column": "value", "as": "mean_value"}],
    }


def test_composer_tool_stamps_llm_origin():
    captured = {}
    class Gateway:
        def synthesis_thread_propose_state(self, thread_id, **kwargs):
            captured.update(kwargs)
            return {"id": thread_id, "state": {"proposal": {"execution_preflight": {"ok": True}}}}
    handlers = ResearchToolHandlers(SimpleNamespace(gateway=Gateway()))
    handlers.research_synthesis_propose_state(
        "t", "p", "Method", "Summary", [{"op": "update_spec", "patch": {"purpose": "x"}}], execution_spec=_spec()
    )
    assert captured["origin"] == {
        "kind": "llm_tool_call", "authority": "composer", "tool": "research_synthesis_propose_state"
    }


def test_researcher_acceptance_preserves_llm_proposal_identity():
    state = {"nodes": [], "edges": [], "activity": [], "spec": {}, "proposal": None}
    proposal = validate_synthesis_proposal(state, {
        "id": "p1", "title": "LLM method", "summary": "validated method", "operations": [
            {"op": "update_spec", "patch": {"purpose": "test"}}
        ], "execution_spec": _spec(),
        "origin": {"kind": "llm_tool_call", "authority": "composer", "tool": "research_synthesis_propose_state"},
    })
    state["proposal"] = proposal
    accepted = accept_proposal(state)
    origin = accepted["method_origin"]
    assert origin["kind"] == "llm_tool_call"
    assert origin["authority"] == "composer"
    assert origin["tool"] == "research_synthesis_propose_state"
    assert origin["proposal_hash"] == proposal["proposal_hash"]
    assert accepted["accepted_spec_hash"]


def test_executor_freezes_runnable_method_from_accepted_spec(tmp_path):
    repo = _repo(tmp_path)
    origin = {
        "kind": "llm_tool_call", "authority": "composer", "tool": "research_synthesis_propose_state",
        "proposal_id": "p1", "proposal_hash": "proposal-sha"
    }
    result = execute(repo, "job1", {"thread_id": "t1", "execution_spec": _spec(), "method_origin": origin})
    repro = result["reproducibility"]
    method = repo / repro["method_path"]
    assert method.is_file()
    text = method.read_text(encoding="utf-8")
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == repro["method_sha256"]
    assert repro["method_origin"]["authority"] == "composer"
    assert "execution_spec sha256" in text
    assert "result.to_parquet" in text
    manifest = json.loads((repo / result["materialized"]["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["reproducibility"]["method_sha256"] == repro["method_sha256"]
    assert any(row["name"] == "method.py" for row in result["materialized"]["files"])

    run_dir = repo / "reproduce"
    run_dir.mkdir()
    run = subprocess.run([sys.executable, str(method)], cwd=run_dir, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    reproduced = pd.read_parquet(run_dir / "synthesis_method_export_v1.parquet")
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t1/job1/output.parquet")
    pd.testing.assert_frame_equal(
        engine.sort_values(list(engine.columns)).reset_index(drop=True),
        reproduced.sort_values(list(reproduced.columns)).reset_index(drop=True),
        check_dtype=False,
    )
'''
write("tests/test_synthesis_method_export_contract.py", test)

print("Synthesis method export patch applied")
