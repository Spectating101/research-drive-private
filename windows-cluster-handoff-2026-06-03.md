# Windows Lab Cluster Handoff - 2026-06-03

## Goal
Turn idle Windows lab machines into a reachable compute/automation pool managed from the Linux laptop over Tailscale SSH, with persistent access after reboot.

## Management Network
Primary management network is Tailscale SSH. Ethernet/direct `192.168.77.x` was explored but is no longer the main path unless explicitly needed.

Controller/Linux laptop:
- Host: `phyrexian`
- Tailscale IP: `100.113.146.45`
- SSH key used for cluster access: `/home/phyrexian/.ssh/id_rsa` primarily; ED25519 also exists.

## Joined Nodes
Confirmed working via `ssh user@<tailscale-ip>`:

| Hostname | Tailscale IP | Login | Status |
|---|---:|---|---|
| `DESKTOP-VEFGGDH` | `100.122.168.34` | `user` | joined |
| `DESKTOP-FGEDHGV` | `100.102.0.84` | `user` | joined |
| `DESKTOP-DHFGGVE` | `100.92.237.90` | `user` | joined |
| `DESKTOP-EDHFGGV` | `100.83.34.59` | `user` | joined |

Group command verified from controller:

```bash
/home/phyrexian/cluster-lab-logs/cluster-run.sh 'hostname && whoami'
```

It returned all four machines successfully.

## Node Specs Observed
The joined Windows machines are similar ASUS workstations:
- Model: `ASUSTeK COMPUTER INC. Pro E500 G7_WS750T`
- OS: Windows 11 Pro / Windows 11 Pro localized, 64-bit, build around `10.0.26200`
- CPU: Intel Core i7-11700 @ 2.50GHz
- Cores/threads: 8 cores / 16 threads each
- RAM: about 16 GB each
- GPU: Intel UHD Graphics 750 + NVIDIA GeForce GT 730 2GB on inspected nodes

Approx confirmed pool:
- 4 nodes
- 32 physical cores / 64 logical threads
- ~64 GB RAM total

## Persistence / Hardening Done
On joined machines:
- `sshd` service is running and set to `Automatic`.
- `Tailscale` service is running and set to `Automatic`.
- SSH public keys were added to user and/or administrator OpenSSH key locations.
- `sshd_config` was fixed to allow `user`, including handling prior `AllowUsers remoteops` restriction.
- Firewall rules opened/confirmed for management ports: SSH 22, SMB 445, RDP 3389, WinRM 5985.
- Scheduled task `ClusterAccessEnsure` was installed on joined machines to repair access after reboot/logon and periodically.

Important SSH issue discovered:
- A major blocker was `AllowUsers remoteops` in `C:\ProgramData\ssh\sshd_config`, which rejected `user` before key auth.
- Fix was to ensure `AllowUsers` includes `user`.

## USB Scripts
A consolidated USB script pair was created on the flash drive root:

```text
CLUSTER_JOIN_SETUP.bat
CLUSTER_JOIN_SETUP.ps1
```

Run `CLUSTER_JOIN_SETUP.bat` as Administrator on future Windows machines.

What it does:
- Ensures OpenSSH Server.
- Installs Linux controller SSH public keys.
- Fixes `sshd_config` including `AllowUsers`.
- Opens firewall ports.
- Assigns direct `192.168.77.x` cluster IPs if Ethernet adapters exist.
- Installs `ClusterAccessEnsure` scheduled task for persistence.
- Writes cluster join inventory/logs.

Older/root scripts that existed during debugging:
- `DIRECT_ACCESS_SETUP.bat/.ps1`
- `DIRECT_ACCESS_DIAGNOSE.bat/.ps1`
- `REPAIR_CURRENT_USER_SSH.bat`
These were intermediate. Preferred future entrypoint is `CLUSTER_JOIN_SETUP.bat`.

## Local Controller Files
Created locally under:

```text
/home/phyrexian/cluster-lab-logs/
```

Key files:
- `windows-cluster-inventory.csv`
- `cluster-run.sh`
- `cluster-health.sh`
- `CLUSTER_JOIN_SETUP.ps1`
- `CLUSTER_JOIN_SETUP.bat`

Inventory currently marks all four joined nodes.

## Current Inventory Snapshot

```csv
hostname,tailscale_ip,user,status,notes
DESKTOP-VEFGGDH,100.122.168.34,user,joined,ssh+persistent guard
DESKTOP-FGEDHGV,100.102.0.84,user,joined,ssh+persistent guard
DESKTOP-DHFGGVE,100.92.237.90,user,joined,ssh+persistent guard
DESKTOP-EDHFGGV,100.83.34.59,user,joined,ssh+persistent guard
```

## Recommended Next Steps
1. Stop onboarding for a moment and build/clean the controller layer.
2. Use `/home/phyrexian/cluster-lab-logs/cluster-run.sh` for simple group commands.
3. Add a real downloader/job runner that:
   - creates `C:\ClusterData\Downloads` on each node,
   - writes per-node logs,
   - supports retries/resume,
   - limits concurrency.
4. For new machines, install/authenticate Tailscale first, then run `CLUSTER_JOIN_SETUP.bat` as Administrator.
5. After each new node, verify:

```bash
ssh user@<tailscale-ip> 'hostname && whoami'
```

## Caution
The cluster is now useful, but avoid launching huge downloads on every node blindly. Start staged, with logs and retries. Use `C:` on each Windows node unless intentionally using another disk.
