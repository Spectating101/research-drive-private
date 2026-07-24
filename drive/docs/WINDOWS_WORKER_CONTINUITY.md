# Windows Remote Worker Continuity

Operator bootstrap that keeps a **thin** Windows checkout (`C:\cw\Sharpe-Renaissance`)
joined to the Optiplex worker-control plane so heartbeats do not go stale.

This package **does not submit or auto-approve jobs**. It only supervises
`drive/scripts/yzu_cluster/remote_worker.py`, which claims work when queued jobs
already exist.

## Prerequisites

- Host already has a thin Sharpe checkout with `drive\scripts\yzu_cluster\remote_worker.py`
- `py` (or another Python launcher) on PATH
- Tailscale reachability to the controller (`http://<optiplex-tailscale-ip>:8780`)
- Matching `YZU_WORKER_CONTROL_TOKEN` on controller and worker (never commit it)

## Continuity profiles

| Profile | Trigger | Principal | Admin? | When to use |
|---------|---------|-----------|--------|-------------|
| `InteractiveLogon` (**default**) | `AtLogOn` | `Interactive` / Limited | No | Non-admin installs; user stays signed in |
| `NonInteractiveStartup` (**opt-in**) | `AtStartup` | `S4U` (noninteractive) / Highest | **Yes — elevated Administrator** | Lab host with nobody signed in; always-ready |

`NonInteractiveStartup` fails fast unless the install session is elevated. Prefer the
default interactive profile when you cannot (or should not) elevate.

## Token (never echo / never fingerprint / never commit)

Prefer a protected local file on the Windows host:

```powershell
# Run once as the worker account. Do not paste the secret into shared logs.
Set-Content -LiteralPath "C:\cw\Sharpe-Renaissance\.yzu-worker-token" -Value $env:YZU_WORKER_CONTROL_TOKEN -Encoding ascii
icacls "C:\cw\Sharpe-Renaissance\.yzu-worker-token" /inheritance:r /grant:r "$env:USERNAME:(R)"
```

Or set `YZU_WORKER_CONTROL_TOKEN` in the install session; the installer may copy it
into the protected local file so the task can resolve it after reboot. The scheduled
task command line never embeds the secret. Status/supervisor output reports only
`present` + source (`env` / `file`) — **no value and no hash/fingerprint**.

`.yzu-worker-token` is gitignored.

## Install — interactive logon (default, non-admin safe)

From a normal PowerShell session on the Windows host after the continuity scripts
are synced into the thin checkout:

```powershell
cd C:\cw\Sharpe-Renaissance
# Token already in .yzu-worker-token OR:
# $env:YZU_WORKER_CONTROL_TOKEN = "<same-as-controller>"

powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\drive\scripts\yzu_cluster\install_windows_remote_worker.ps1 `
  -Mode Install `
  -ContinuityProfile InteractiveLogon `
  -ControllerUrl "http://<optiplex-tailscale-ip>:8780" `
  -WorkerId "windows-01" `
  -Pool "windows_lab" `
  -Capabilities "http,python" `
  -Spool ".yzu-worker-spool" `
  -StartNow
```

Task name defaults to `YzuWindowsRemoteWorker-<WorkerId>`. With
`InteractiveLogon`, the task starts at user logon and needs a signed-in session.

## Install — noninteractive startup (opt-in, Administrator required)

For a lab host that reboots with **no interactive user session**, elevate first
(`Run as administrator`), ensure `.yzu-worker-token` is readable by the install
account, then:

```powershell
cd C:\cw\Sharpe-Renaissance

# MUST be elevated Administrator PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\drive\scripts\yzu_cluster\install_windows_remote_worker.ps1 `
  -Mode Install `
  -ContinuityProfile NonInteractiveStartup `
  -ControllerUrl "http://<optiplex-tailscale-ip>:8780" `
  -WorkerId "windows-01" `
  -Pool "windows_lab" `
  -Capabilities "http,python" `
  -Spool ".yzu-worker-spool" `
  -StartupDelaySeconds 60 `
  -StartNow
```

This registers an `AtStartup` trigger with an `S4U` noninteractive principal so the
supervised claim loop can run without anyone remaining signed in. A short startup
delay (default 60s) gives Tailscale/NIC time to come up. Non-elevated installs with
this profile error with an explicit Administrator requirement and leave the default
interactive profile available as the fallback.

Both profiles restart on failure (Task Scheduler `RestartCount` + supervised runner
loop).

## Status / Stop / Uninstall

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\drive\scripts\yzu_cluster\install_windows_remote_worker.ps1 `
  -Mode Status -WorkerId "windows-01"

powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\drive\scripts\yzu_cluster\install_windows_remote_worker.ps1 `
  -Mode Stop -WorkerId "windows-01"

powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\drive\scripts\yzu_cluster\install_windows_remote_worker.ps1 `
  -Mode Uninstall -WorkerId "windows-01"
```

Logs: `C:\cw\Sharpe-Renaissance\logs\yzu-remote-worker\<worker-id>.*.log`

## Sync note

These scripts live in the private checkout under
`drive/scripts/yzu_cluster/install_windows_remote_worker.ps1` and
`run_windows_remote_worker.ps1`. Copy/sync them onto each thin host before
Install; this package itself does not deploy over SSH.

## Out of scope

- Submitting or auto-approving Research Drive jobs
- Rotating controller tokens automatically
- Changing firewall / Tailscale / worker-control bind address
- Full (venv) Windows queue execution provisioning
