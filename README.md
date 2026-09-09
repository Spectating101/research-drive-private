# Research Drive — private backend runtime

This repository is the private/runtime half of **Research Drive**. It owns the backend API, research-object registry and data-lake authority, Discover procurement lifecycle, Library provenance/retrieval, Synthesis Preview/execution authority, connected-account state, worker orchestration, and host release tooling.

The researcher-facing UI lives in the public `Spectating101/yzu-cluster` repository. A production Research Drive release is always an explicit pair:

```text
<frontend_sha>--<backend_sha>
```

Branch names, PR titles, screenshots, or “latest” are not release identity.

## Current release candidate

Current backend release line:

```text
integration/research-drive-backend-rc-refresh-20260904
```

PR:

```text
#61 — refreshed Research Drive backend release candidate
```

Last behavior-changing backend SHA certified before the documentation-only pass:

```text
92cf9a417c778b228d91570d2b1a8654ca0dc251
```

The **host checkout must use the final PR #61 head after all later documentation/config-example commits also pass the release gates**. Do not deploy the historical SHA above merely because it is written here if the PR has moved to a newer green descendant.

Repository certification is not production authorization. The remaining acceptance boundary is intentionally the real host: systemd, private network binding, mounted runtime data, OAuth/provider reachability, real workers, real held-data journeys, promotion, restart, and rollback.

## Start here

Current operator/reviewer documentation is indexed at:

[`drive/docs/status/releases/README.md`](drive/docs/status/releases/README.md)

The four primary current documents are:

- [`BACKEND_RELEASE_HANDOFF_20260904.md`](drive/docs/status/releases/BACKEND_RELEASE_HANDOFF_20260904.md) — release scope, certification boundary, operator rules, stop conditions;
- [`BACKEND_ARCHITECTURE_20260904.md`](drive/docs/status/releases/BACKEND_ARCHITECTURE_20260904.md) — backend subsystem and authority model;
- [`BACKEND_HOST_RELEASE_RUNBOOK_20260904.md`](drive/docs/status/releases/BACKEND_HOST_RELEASE_RUNBOOK_20260904.md) — exact staging, preflight, promotion, restart, golden paths, rollback;
- [`BACKEND_HOST_ACCEPTANCE_20260904.md`](drive/docs/status/releases/BACKEND_HOST_ACCEPTANCE_20260904.md) — fillable real-machine acceptance/evidence record.

## Backend architecture

Research Drive is organized around persistent research state and explicit authority boundaries.

The backend intentionally keeps these concepts separate:

```text
object identity
!= provenance
!= physical possession
!= storage location
!= freshness
!= verification
!= query readiness
!= research context
!= model intent
!= execution authority
```

That separation is the core semantic contract of the backend.

### Library / research-object authority

Library owns the authoritative model of registered research objects, provenance, possession/holdings, retrieval evidence, semantic widening, freshness/readiness, and principal research state.

Key implementation areas:

```text
drive/scripts/research_data_mcp/library_provenance.py
drive/scripts/research_data_mcp/library_possession.py
drive/scripts/research_data_mcp/library_retrieval.py
drive/scripts/research_data_mcp/library_semantic_search.py
drive/scripts/research_data_mcp/semantic_index.py
drive/scripts/research_data_mcp/research_seed.py
```

Registration alone does not prove possession or query readiness. Semantic relevance does not prove that bytes are held. Physical storage paths do not define research topic authority.

### Discover / procurement authority

Discover turns a research need into evidence and, where required, a bounded procurement lifecycle.

The runtime—not model text—owns capabilities, placement, durable submission state, server-side idempotency, owner isolation, job identity, and execution boundaries.

Key implementation areas:

```text
drive/scripts/research_data_mcp/discover_intent_store.py
drive/scripts/research_data_mcp/procurement_chat.py
drive/scripts/research_data_mcp/procurement_chat_core.py
drive/scripts/research_data_mcp/procurement_execution_contract.py
drive/scripts/research_data_mcp/jobs.py
drive/scripts/research_data_mcp/job_identity.py
```

### Synthesis authority

Synthesis separates reasoning/proposal from consequential execution:

```text
objective
-> bounded evidence mapping
-> measurement
-> Preview
-> review/approval
-> execute approved current spec
-> materialize
-> register output + lineage
```

Preview is non-materializing. A successful model response is not execution authority. Stale/tampered/drifted preview authority is rejected.

Key implementation areas:

```text
drive/scripts/research_data_mcp/synthesis/
drive/scripts/research_data_mcp/synthesis_preview.py
drive/scripts/research_data_mcp/synthesis_execution_authority.py
drive/scripts/research_data_mcp/synthesis_executor.py
drive/scripts/research_data_mcp/synthesis_object_targets.py
```

### Connected accounts

Connected-account state is principal-bound and uses an explicit OAuth/PKCE/security boundary. A connected provider is not automatically proof that every remote object is locally held or query-ready.

Key implementation areas:

```text
drive/scripts/research_data_mcp/connected_accounts.py
drive/scripts/research_data_mcp/connected_accounts_http.py
drive/scripts/research_data_mcp/connected_accounts_security.py
```

### Front door and release tooling

The private front door serves the chosen public UI build and protected private API from one origin. Same-origin is a deployment property, not authentication.

Release tooling lives in:

```text
drive/scripts/research_query_engine/
```

Core release sequence:

```text
exact frontend checkout + exact backend checkout
-> build_optiplex_front_door.sh
-> releases/<frontend_sha>--<backend_sha>/
-> preflight_release.sh
-> promote_front_door.sh
-> systemd restart
-> verify_front_door_restartability.sh --exercise
```

A build stages; it does **not** publish. `promote_front_door.sh` is the controlled live-link transition and runs fail-closed preflight before changing the live release.

Rollback is a complete UI/backend pair operation, not a frontend-only symlink flip.

## Local development / tests

The release workflows are the authoritative composed gates for the current RC. For focused local work, keep repository-root imports consistent with CI and use the test targets associated with the subsystem being changed.

Important workflow gates:

```text
.github/workflows/backend-release-proof.yml
.github/workflows/research-drive-backend-rc.yml
.github/workflows/private-runtime-contract.yml
```

Do not replace the broad Private Runtime gate with only subsystem-specific tests when certifying a release candidate.

## Host configuration

Copy the example environment to the real host-local path and protect it:

```bash
mkdir -p ~/.config/research-drive
cp drive/config/optiplex-front-door.env.example ~/.config/research-drive/front-door.env
chmod 600 ~/.config/research-drive/front-door.env
```

The example deliberately does **not** contain the current approved frontend SHA. Set `YZU_PUBLIC_SHA` explicitly for the exact frontend being paired with the backend candidate.

Never commit or paste real tokens, OAuth secrets, credential-store contents, or the complete private environment file.

## Release acceptance

CI can prove repository properties and release mechanics. The actual host must prove:

- exact frontend/backend checkout identity;
- environment ownership/mode and release pins;
- runtime registry/data-root authority;
- complete staged build identity;
- current-host preflight;
- systemd/linger/restart recovery;
- authenticated session continuity;
- real provider/OAuth reachability where configured;
- real remote-worker join/claim/heartbeat/artifact/materialization;
- real Discover, Library, and Synthesis journeys;
- live promotion identity;
- rollback to the previous complete pair.

Use the host acceptance record instead of informal notes:

[`drive/docs/status/releases/BACKEND_HOST_ACCEPTANCE_20260904.md`](drive/docs/status/releases/BACKEND_HOST_ACCEPTANCE_20260904.md)

## Legacy repository content

This repository originated from the broader **Sharpe-Renaissance** codebase and still contains financial/data-processing components such as `api/`, `high_perf/`, `trading/`, `engine/`, and older agent code.

Those directories may remain useful dependencies or historical assets, but they are **not the current repository-level product definition or release authority**. Current Research Drive backend/release documentation takes precedence for the Research Drive runtime.

One inherited repository-hygiene issue remains: `agents/finrobot` is a malformed historical gitlink with no recoverable `.gitmodules` URL. It produces checkout cleanup noise but is not part of the current release authority. Do not invent a remote URL or mutate the certified RC merely to silence that warning.
