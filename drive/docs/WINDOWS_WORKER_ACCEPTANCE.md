# Windows Worker / GDrive Acceptance Runbook

This runbook is the remaining deployment gate for private PR #1. It proves the
runtime on real hosts; it does not change the application architecture.

Before host work, fast-forward the local checkout to the exact remote head and
confirm the private runtime workflow is green. Do not redesign the scheduler,
registry, lifecycle, or frontend contracts during acceptance. Any host-specific
code change must be isolated, explained, tested, and pushed back to the same
draft PR before the acceptance run is repeated.

## Security boundary

- Bind the worker-control service only to the Optiplex Tailscale interface or a
  firewall-restricted private interface.
- Generate a fresh high-entropy token outside Git and expose it through
  `YZU_WORKER_CONTROL_TOKEN` on the controller and worker.
- Never commit the token, `.env` files, Tailscale auth keys, SSH keys, rclone
  configuration, or worker inventory secrets.
- The control plane rejects missing/incorrect tokens and fences every write by
  `worker_id + attempt`.

## 1. Controller

From the private checkout on the Optiplex:

```bash
export PYTHONPATH="$PWD:$PWD/kernel:$PWD/drive"
export YZU_WORKER_CONTROL_TOKEN="<fresh-secret>"
python -m scripts.yzu_cluster.worker_control \
  --repo-root "$PWD/drive" \
  --host "<optiplex-tailscale-ip>" \
  --port 8780
```

Health is intentionally non-sensitive:

```bash
curl http://<optiplex-tailscale-ip>:8780/health
```

Expected:

```json
{"status":"ok","token_required":true}
```

## 2. Windows worker

The Windows checkout must contain:

- `scripts/cluster_agent/remote_collect.py`
- `scripts/yzu_cluster/remote_worker.py`
- the Python packages needed by the remote collector
- outbound HTTPS access to the public source
- Tailscale access to the controller port

PowerShell:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\kernel;$PWD\drive"
$env:YZU_WORKER_CONTROL_TOKEN = "<same-fresh-secret>"
py -m scripts.yzu_cluster.remote_worker `
  --controller "http://<optiplex-tailscale-ip>:8780" `
  --repo-root "C:\cw\Sharpe-Renaissance\drive" `
  --worker-id "windows-01" `
  --pool "windows_lab" `
  --capabilities "http,python" `
  --lease-seconds 120 `
  --heartbeat-seconds 30
```

The worker deliberately supports only `http_manifest` in this acceptance lane.
Unsupported jobs are failed explicitly rather than executed through arbitrary
shell input.

## 3. Submit one safe public-source collection

Use the existing Research Drive job submission path to create an auto-approved
`http_manifest` job with:

- a stable idempotency key;
- one or more direct public HTTPS items;
- a declared dataset ID;
- validation requiring at least one non-empty file;
- declared `http` capability;
- no credentials or private source data.

The job must be visible as queued before the Windows worker claims it.

## 4. Required success evidence

Capture the following identifiers and payloads:

1. Worker join response:
   - worker ID;
   - pool;
   - capabilities;
   - measured CPU, free memory, and free disk;
   - fresh heartbeat.
2. Claim response:
   - job ID;
   - run ID;
   - attempt;
   - lease expiry;
   - declared outputs.
3. Runtime heartbeat while the download is active.
4. Attempt-fenced artifact upload response:
   - artifact path;
   - bytes;
   - SHA-256;
   - worker ID and attempt.
5. Controller materialisation:
   - dataset ID;
   - output manifest ID/path;
   - validation result;
   - file checksums.
6. GDrive proof:
   - `rclone copy` success;
   - `rclone check --one-way` success;
   - canonical remote path.
7. Registry proof:
   - promoted dataset ID matches the manifest output ID;
   - canonical remote matches the verified archive;
   - registry read-back succeeds.
8. Final state:
   - runtime lifecycle is `registered` or `query_ready`;
   - legacy job remains `completed` as a compatibility projection;
   - Library, Resources, and Synthesis expose the same run/output identity.

A completed process without manifest, verified archive, promotion, and registry
read-back is not an accepted result.

## 5. Required failure/retry evidence

Run a second harmless job and stop the Windows worker after it enters `running`.
Do not send a terminal result.

Verify:

1. Heartbeats stop.
2. The lease expires.
3. Runtime moves to `retrying` while legacy state reconciles back to `queued`.
4. A new claim receives `attempt + 1`.
5. A late heartbeat, usage report, artifact upload, completion, or failure from
   the old attempt is rejected.
6. No duplicate Library registration or lifecycle event is created.

## 6. Stop conditions

Stop and preserve logs if any of these occur:

- private code or credentials would need to be pushed to a public remote;
- worker control is reachable outside the intended private interface;
- a stale attempt is accepted;
- canonical registry mutation occurs before manifest/archive proof;
- GDrive verification fails but Library still exposes the asset;
- legacy and runtime states cannot be reconciled without destructive migration.

## 7. Acceptance report

Return:

- controller and worker commit SHA;
- worker-control URL with host redacted where appropriate;
- exact commands used, excluding secrets;
- job/run/attempt/output/manifest/registry IDs;
- relevant JSON responses and logs;
- GDrive verification evidence;
- retry/fencing evidence;
- final Resources, Synthesis, and Library state;
- any remaining deployment-specific blocker.

## 8. Durable supervision and token drift (repository-owned procedure)

The accepted Optiplex lane failed twice in production for host ritual debt — not architecture:

1. the Windows loop process exited and was not supervised;
2. `.yzu-worker-token` on the Windows checkout drifted from the controller process env `YZU_WORKER_CONTROL_TOKEN`, so `/v1/workers/join` returned 401.

### Token identity (never log the secret)

On the Optiplex controller process, hash the live env value:

```bash
# presence + fingerprint only
python3 - <<'PY'
from pathlib import Path
import hashlib, os
# Prefer reading the controller process environ in ops; example fingerprint helper:
token = os.environ.get("YZU_WORKER_CONTROL_TOKEN", "").encode()
print("present" if token else "missing", hashlib.sha256(token).hexdigest() if token else "")
PY
```

On Windows, fingerprint the token file the same way and sync **only when hashes differ** (write via a temporary helper script + base64; do not echo the secret into shell history). Keep the file mode restricted to the worker account.

### Supervised loop

Prefer a durable Windows Task Scheduler entry or a small `win_worker_loop.py` started with `Start-Process` that:

- loads the token from the local token file into `YZU_WORKER_CONTROL_TOKEN`;
- sets `PYTHONPATH` for repo/kernel/drive;
- calls `scripts.yzu_cluster.remote_worker` with `windows-01` / `windows_lab` / `http,python`;
- appends stdout/stderr to a local log (for example `windows-01-worker.log`).

After restart, confirm join succeeds (no 401) and the desk job can move `queued → running → registered` for an allowed `http_manifest` only.

### Out of scope for this procedure

- committing the token or log contents;
- exposing `:8780` beyond Tailscale;
- claiming non-`http_manifest` job types on the Windows acceptance worker.
