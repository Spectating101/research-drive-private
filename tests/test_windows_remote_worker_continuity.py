"""Static contract for the Windows remote-worker continuity bootstrap.

These checks stay offline: no SSH, no Task Scheduler, no controller, no token,
and no job submission.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "drive/scripts/yzu_cluster/install_windows_remote_worker.ps1"
RUNNER = REPO / "drive/scripts/yzu_cluster/run_windows_remote_worker.ps1"
DOCS = REPO / "drive/docs/WINDOWS_WORKER_CONTINUITY.md"
GITIGNORE = REPO / ".gitignore"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing required continuity artifact: {path}"
    return path.read_text(encoding="utf-8")


def test_continuity_artifacts_exist() -> None:
    assert INSTALL.is_file()
    assert RUNNER.is_file()
    assert DOCS.is_file()


def test_install_script_exposes_operator_modes() -> None:
    text = _read(INSTALL)
    for mode in ("Install", "Status", "Stop", "Uninstall"):
        assert mode in text
    assert "ValidateSet" in text or "param(" in text
    assert "Register-ScheduledTask" in text or "schtasks" in text
    assert re.search(r"RestartCount|RestartInterval|supervise", text, re.IGNORECASE)


def test_startup_mode_opt_in_requires_admin_and_noninteractive_principal() -> None:
    text = _read(INSTALL)
    assert "NonInteractiveStartup" in text
    assert "AtStartup" in text
    assert re.search(r"LogonType\s+S4U|-LogonType\s+S4U", text)
    assert "Assert-Administrator" in text or "WindowsBuiltInRole]::Administrator" in text
    assert "Administrator" in text
    # Opt-in: startup profile must not be the default parameter value.
    assert re.search(
        r'\$ContinuityProfile\s*=\s*"InteractiveLogon"',
        text,
    ), "default ContinuityProfile must remain InteractiveLogon"


def test_interactive_logon_fallback_for_non_admin_installs() -> None:
    text = _read(INSTALL)
    assert "InteractiveLogon" in text
    assert re.search(r"AtLogOn|ONLOGON", text, re.IGNORECASE)
    assert re.search(r"LogonType\s+Interactive|-LogonType\s+Interactive", text)
    assert "RunLevel Limited" in text or "-RunLevel Limited" in text


def test_bootstrap_targets_thin_remote_worker_with_required_flags() -> None:
    install = _read(INSTALL)
    runner = _read(RUNNER)
    combined = install + "\n" + runner
    assert "remote_worker.py" in combined
    for flag in (
        "--controller",
        "--worker-id",
        "--pool",
        "--capabilities",
        "--spool",
        "--repo-root",
    ):
        assert flag in combined
    assert "windows_lab" in combined
    assert "http,python" in combined or '"http,python"' in combined


def test_token_comes_only_from_env_or_protected_file_never_printed_or_fingerprinted() -> None:
    install = _read(INSTALL)
    runner = _read(RUNNER)
    combined = install + "\n" + runner
    assert "YZU_WORKER_CONTROL_TOKEN" in combined
    assert ".yzu-worker-token" in combined
    # Must not print/echo the secret value itself.
    forbidden_echo = [
        r"Write-Host\s+\$env:YZU_WORKER_CONTROL_TOKEN",
        r"Write-Output\s+\$env:YZU_WORKER_CONTROL_TOKEN",
        r"echo\s+\$env:YZU_WORKER_CONTROL_TOKEN",
        r"Write-Host\s+\$token\b",
        r"Write-Output\s+\$token\b",
        r"echo\s+\$token\b",
        r"Write-Host\s+\$trimmed\b",
        r"Write-Host\s+\$raw\b",
    ]
    for pattern in forbidden_echo:
        assert not re.search(pattern, combined, re.IGNORECASE), pattern
    # Must not fingerprint / hash the token for logs.
    assert "Get-TokenFingerprint" not in combined
    assert "Get-Sha256Hex" not in combined
    assert not re.search(r"sha256\s*=", combined, re.IGNORECASE)
    assert "ComputeHash" not in combined
    # Task command line builds runner args without embedding the secret.
    assert "YZU_WORKER_CONTROL_TOKEN" not in re.search(
        r'\$argument\s*=\s*"[^"]+"',
        install,
        re.DOTALL,
    ).group(0)


def test_bootstrap_does_not_submit_or_auto_approve_jobs() -> None:
    runtime = _read(INSTALL) + "\n" + _read(RUNNER)
    docs = _read(DOCS)
    assert "auto_approve" not in runtime.lower()
    assert "auto-approve" not in runtime.lower()
    assert "/v1/jobs" not in runtime
    assert "submit_job" not in runtime.lower()
    assert "does not submit" in runtime.lower()
    assert "does not submit" in docs.lower() or "does not create jobs" in docs.lower()


def test_runner_launches_python_directly_with_stdio_redirect_no_cmd_shell() -> None:
    """Regression: cmd.exe /c wrappers can exit=1 with no stdout/stderr files."""
    text = _read(RUNNER)
    assert "Start-Process" in text
    assert re.search(
        r"-FilePath\s+\$(?:PythonExe|pythonLaunch)\b",
        text,
    ), "must Start-Process Python directly (not cmd.exe)"
    assert "RedirectStandardOutput" in text
    assert "RedirectStandardError" in text
    assert re.search(r"-ArgumentList\b", text)
    assert "cmd.exe" not in text
    # Token stays in process env only — never on the launched argument list.
    assert "YZU_WORKER_CONTROL_TOKEN" not in re.search(
        r"\$workerArgs\s*=\s*@\((.*?)\)",
        text,
        re.DOTALL,
    ).group(1)
    assert "supervise_launch_error" in text


def test_gitignore_protects_local_token_file() -> None:
    text = _read(GITIGNORE)
    assert ".yzu-worker-token" in text


def test_operator_docs_document_profiles_and_modes() -> None:
    docs = _read(DOCS)
    assert "install_windows_remote_worker.ps1" in docs
    assert "ControllerUrl" in docs or "-ControllerUrl" in docs
    for mode in ("Install", "Status", "Stop", "Uninstall"):
        assert mode in docs
    assert "YZU_WORKER_CONTROL_TOKEN" in docs
    assert "InteractiveLogon" in docs
    assert "NonInteractiveStartup" in docs
    assert "AtStartup" in docs
    assert "S4U" in docs
    assert "Administrator" in docs
    assert "fingerprint" in docs.lower()
    assert "does not submit" in docs.lower() or "does not create jobs" in docs.lower()
