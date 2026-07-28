#!/usr/bin/env python3
"""Safety contracts for local and remote ops-host command execution."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.yzu_cluster.cluster_ops import (
    MAX_OPS_HOST_ARGC,
    MAX_OPS_HOST_TIMEOUT_SECONDS,
    run_on_ops_host,
)


def _ops_cfg(repo: Path, *, mode: str = "local") -> dict:
    return {
        "operations": {
            "ops_host": {
                "mode": mode,
                "repo_root": str(repo),
                "ssh_target": "ops@example.test",
                "ssh_key": "/tmp/test-key",
            }
        }
    }


def test_local_ops_host_executes_literal_argv_without_shell(tmp_path: Path) -> None:
    output = tmp_path / "literal.txt"
    injected = tmp_path / "injected.txt"
    literal = f"semi; $(touch {injected})"

    process = run_on_ops_host(
        _ops_cfg(tmp_path),
        [sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])", str(output), literal],
    )

    assert process.returncode == 0
    assert output.read_text(encoding="utf-8") == literal
    assert not injected.exists()


def test_ops_host_wrapper_preserves_argv_boundaries(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    wrapper = root / "drive/scripts/yzu_cluster/run_on_ops_host.sh"
    output = tmp_path / "wrapper-literal.txt"
    injected = tmp_path / "wrapper-injected.txt"
    literal = f"semi; $(touch {injected})"

    process = subprocess.run(
        [
            "bash",
            str(wrapper),
            sys.executable,
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])",
            str(output),
            literal,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert process.returncode == 0, process.stderr
    assert output.read_text(encoding="utf-8") == literal
    assert not injected.exists()


def test_ops_host_rejects_legacy_shell_strings_and_unbounded_inputs(tmp_path: Path) -> None:
    cfg = _ops_cfg(tmp_path)

    with pytest.raises(TypeError, match="argv sequence"):
        run_on_ops_host(cfg, "echo unsafe")
    with pytest.raises(ValueError, match="must not be empty"):
        run_on_ops_host(cfg, [])
    with pytest.raises(ValueError, match="arguments"):
        run_on_ops_host(cfg, ["echo", *["x"] * MAX_OPS_HOST_ARGC])
    with pytest.raises(ValueError, match="NUL"):
        run_on_ops_host(cfg, ["echo", "bad\x00arg"])
    with pytest.raises(ValueError, match="timeout"):
        run_on_ops_host(cfg, ["echo"], timeout=MAX_OPS_HOST_TIMEOUT_SECONDS + 1)


def test_remote_ops_host_quotes_cwd_and_each_argument(tmp_path: Path) -> None:
    repo = tmp_path / "repo with 'quote"
    argv = ["python3", "job.py", "$(touch /tmp/pwned)", "semi;colon", "it's"]
    completed = subprocess.CompletedProcess(["ssh"], 0, stdout="ok", stderr="")

    with patch("scripts.yzu_cluster.cluster_ops.ssh_run", return_value=completed) as run:
        result = run_on_ops_host(_ops_cfg(repo, mode="ssh"), argv)

    expected = (
        f'export PATH="$HOME/bin:$PATH"; '
        f"cd -- {shlex.quote(str(repo.resolve()))} && exec {shlex.join(argv)}"
    )
    assert result is completed
    run.assert_called_once_with(
        "ops@example.test",
        expected,
        key="/tmp/test-key",
        timeout=3600,
        capture=True,
    )


def test_executor_passes_argv_to_ops_host(tmp_path: Path) -> None:
    from scripts.yzu_cluster.executor import YzuExecutor

    executor = object.__new__(YzuExecutor)
    executor.repo_root = tmp_path
    executor.jobs_root = tmp_path / "jobs"
    executor.cfg = {}
    command = ["python3", "job.py", "literal;argument"]
    completed = subprocess.CompletedProcess(command, 0)

    with (
        patch("scripts.yzu_cluster.executor.use_ops_host_for_pool", return_value=True),
        patch("scripts.yzu_cluster.executor.run_on_ops_host", return_value=completed) as run,
    ):
        result = executor._run_subprocess(
            "job-1",
            command,
            log_name="pipeline.log",
            timeout=90,
        )

    run.assert_called_once_with(
        executor.cfg,
        command,
        log_path=tmp_path / "jobs/job-1/pipeline.log",
        timeout=90,
    )
    assert result == {"pool": "optiplex", "log": "jobs/job-1/pipeline.log"}


def test_registered_pipeline_keeps_command_as_argv(tmp_path: Path) -> None:
    from scripts.yzu_cluster.executor import YzuExecutor

    executor = object.__new__(YzuExecutor)
    executor.repo_root = tmp_path
    executor.jobs_root = tmp_path / "jobs"
    executor.cfg = {}
    executor.agent_cfg = {
        "pipelines": {
            "safe_pipeline": {
                "command": ["python3", "job.py", "literal;argument"],
                "pool": "optiplex",
            }
        }
    }
    executor._event = lambda *_args: None

    with patch.object(
        executor,
        "_run_subprocess",
        return_value={"pool": "optiplex", "log": "pipeline.log"},
    ) as run:
        result = executor._registered_pipeline(
            "job-1",
            {"pipeline_id": "safe_pipeline", "timeout_seconds": 45},
        )

    run.assert_called_once_with(
        "job-1",
        ["python3", "job.py", "literal;argument"],
        log_name="pipeline.log",
        timeout=45,
        pool="optiplex",
    )
    assert result["pipeline_id"] == "safe_pipeline"


def test_huggingface_collect_keeps_dataset_id_as_one_argument(tmp_path: Path) -> None:
    from scripts.yzu_cluster.executor import YzuExecutor

    executor = object.__new__(YzuExecutor)
    executor.repo_root = tmp_path
    executor.jobs_root = tmp_path / "jobs"
    executor.cfg = {}
    hf_id = "org/data;literal"

    with patch.object(
        executor,
        "_run_subprocess",
        return_value={"pool": "optiplex", "log": "hf_collect.log"},
    ) as run:
        result = executor._huggingface_collect(
            "job-2",
            {"hf_dataset_id": hf_id, "timeout_seconds": 75},
        )

    run.assert_called_once_with(
        "job-2",
        [
            "python3",
            "scripts/hf_collect_dataset.py",
            "--dataset-id",
            hf_id,
            "--split",
            "train",
            "--max-shards",
            "2",
        ],
        log_name="hf_collect.log",
        timeout=75,
        pool="optiplex",
    )
    assert result["hf_dataset_id"] == hf_id
