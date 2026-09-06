# YZUC commissioning freeze — 2026-09-07

This document is an operations-only freeze record. It does **not** reopen product development and it does **not** authorize production by itself.

## Exact release authority

```text
FRONTEND_REPO=Spectating101/yzu-cluster
FRONTEND_BRANCH=integration/research-drive-final-release-20260906
FRONTEND_SHA=b46f57c70df5a854fbc706249f6aeafba2664f17

BACKEND_REPO=Spectating101/research-drive-private
BACKEND_BRANCH=integration/research-drive-backend-rc-refresh-20260904
BACKEND_SHA=4d88a1b624e24e2d52e0aa8fa3d6c8ba986f874b

RELEASE_ID=b46f57c70df5a854fbc706249f6aeafba2664f17--4d88a1b624e24e2d52e0aa8fa3d6c8ba986f874b
```

Branch names are convenience only. The release identity is the two exact commit SHAs above.

## Repository certification already satisfied

Frontend exact head:

- `contract-and-build` — SUCCESS
- `viewport-matrix` — SUCCESS
- `build-and-mock-e2e` — SUCCESS

Backend exact head:

- `runtime-contract` — SUCCESS
- `backend-release-proof` — SUCCESS
- `certify` — SUCCESS

No additional frontend/backend feature work is required before host commissioning unless the host proves a real defect.

## Remaining blocking acceptance

Run the existing `BACKEND_HOST_RELEASE_RUNBOOK_20260904.md` on the real OptiPlex against the exact pair above.

Minimum blocking sequence:

1. preserve and record the current live release/rollback candidate;
2. detach the backend checkout at `BACKEND_SHA` and frontend checkout at `FRONTEND_SHA`;
3. verify tracked working trees are clean;
4. verify `~/.config/research-drive/front-door.env` remains secret (`0600` normal target) and pins `YZU_PUBLIC_SHA=FRONTEND_SHA`;
5. verify registry/runtime-drive ownership and worker/provider prerequisites;
6. build the pair with `build_optiplex_front_door.sh` and verify `research-drive-build.json` names both exact SHAs;
7. run `preflight_release.sh` with restartability enabled; any non-zero result is a hard stop;
8. perform one genuine Discover -> execution/materialization -> Library visibility journey and one bounded Synthesis journey against real held data;
9. promote only the exact `RELEASE_ID` with `promote_front_door.sh`;
10. restart the user service and run `verify_front_door_restartability.sh --exercise`;
11. verify live `/research-drive-build.json` reports the exact pair;
12. prove the previous complete pair remains a usable rollback candidate and record sanitized evidence in the host acceptance record.

## Fail-closed rules

Do not:

- substitute a moving branch head for either SHA;
- use `PROMOTE_SKIP_PREFLIGHT=1` during normal commissioning;
- weaken registry/identity/auth checks to make a host failure pass;
- delete the previous staged release before acceptance completes;
- claim production completion from repository CI alone.

## Current state

Repository side: **frozen/certified**.

Host side: **pending real-machine commissioning**. At creation time no authorized remote OptiPlex device was reachable from the commissioning session.
