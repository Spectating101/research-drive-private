# Research Drive backend architecture and authority model — 2026-09-04

**Audience:** backend maintainers, release reviewers, operators  
**Release line:** `integration/research-drive-backend-rc-refresh-20260904`

## 1. Architectural principle

Research Drive is not a chat wrapper around a collection of tools. The backend is organized around persistent research state and explicit authority boundaries.

The system deliberately keeps these concepts separate:

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

Most backend invariants exist to prevent one of those states from silently standing in for another.

## 2. Runtime shape

At a high level:

```text
Researcher browser
    |
    | same-origin authenticated HTTP
    v
Research Drive front door / private desk API
    |
    +--> Library / registry / retrieval authority
    +--> Discover / procurement authority
    +--> Synthesis / Preview / execution authority
    +--> connected-account authority
    +--> job / manifest / provenance identity
    |
    +--> controller / worker-control plane
              |
              +--> remote worker(s)
                      |
                      +--> acquisition / artifact
                              |
                              +--> materialization
                                      |
                                      +--> registry + holdings
```

The public UI is built from the public repository, but the private backend remains the authority for the API, runtime orchestration, registry, data lake, protected operations, and release identity.

## 3. Front-door and authentication boundary

Primary runtime code lives under:

- `drive/scripts/research_query_engine/`
- `drive/scripts/research_data_mcp/`

The front door serves the chosen public UI build and the private API from one origin. Same-origin is a deployment property, not an authentication mechanism.

Authorization may be established through an approved browser session, `X-Desk-Token`, or Bearer token according to the configured authority mode. Origin/CORS headers do not grant identity.

The host release is intended to bind to the approved private network address. Public exposure is a separate release decision and is not implied by successful backend CI.

## 4. Registry and research-object authority

The registry is the canonical structured description of registered research objects, but registration alone does not prove the object is usable.

A research object may independently have:

- stable identity;
- source/provenance evidence;
- local or remote possession evidence;
- one or more physical holdings;
- freshness state;
- verification state;
- query/readiness state;
- research-context relationships.

The runtime may use either Git-owned registry authority for fixed test/reproducibility contexts or an explicitly configured runtime-owned registry for mutable host operation. `preflight_release.sh` validates that the selected mode resolves to the intended file and refuses ambiguous or arbitrary symlink ownership.

Important modules include:

- `library_provenance.py` — provenance representation and fail-closed source evidence;
- `library_possession.py` — possession/holdings boundary;
- `library_retrieval.py` — evidence-aware authoritative retrieval;
- `library_semantic_search.py` — semantic widening that must not become possession authority;
- `semantic_index.py` — semantic index construction/cache lifecycle;
- `research_seed.py` / `research_seed_http.py` — principal-bound research seed state.

## 5. Retrieval model

Retrieval is evidence-ranked rather than a binary string-match gate.

The release preserves several specific invariants:

- researcher query terms are preserved in query order in match evidence;
- informative partial lexical evidence may survive for downstream federation/ranking;
- lone generic cadence/source modifiers in a long unrelated query are suppressed;
- ordinary concepts match as complete tokens, so a term such as `election` cannot match inside `selection`;
- semantic widening can improve ranking but cannot fabricate local possession or provenance;
- physical filesystem/storage paths are not treated as semantic topic authority;
- held-only authoritative retrieval fails closed when possession cannot be established.

This design separates **candidate recall** from **authority to claim an object is actually available and usable**.

## 6. Discover and procurement authority

Discover converts a research need into evidence and, where necessary, a bounded procurement request.

Relevant backend responsibilities include:

- collecting/discovering candidate external evidence;
- compiling procurement intent into bounded execution capabilities;
- assigning resources/shards/retry limits under runtime authority;
- persisting durable submission state;
- enforcing owner isolation;
- assigning server-owned idempotency keys;
- creating immutable job authority after accepted submission.

The model may propose a procurement action, but model text is not allowed to choose unrestricted workers, pools, or execution authority.

Key modules include:

- `discover_intent_store.py`;
- `procurement_chat.py` and `procurement_chat_core.py`;
- `procurement_execution_contract.py`;
- `jobs.py`;
- `job_identity.py`.

## 7. Job, run, manifest, and registration identity

A successful operation is not represented by a single status string. Backend identity can include, where available:

```text
dataset_id
registry_id
manifest_id
job_id
run_id
attempt
worker_id
readiness
```

`job_identity.py` projects explicit persisted output-manifest evidence. The refreshed RC accepts manifest IDs persisted inside registration evidence while remaining fail-closed when no explicit manifest proof exists.

It must never infer a manifest merely because a dataset has a title, path, registration status, or other heuristic indicator.

## 8. Worker-control and materialization boundary

The worker-control plane is separate from the browser-facing desk API.

The real host path is expected to prove:

```text
worker join
-> authenticated claim
-> heartbeat / lease continuity
-> acquisition / execution
-> artifact return
-> manifest identity
-> materialization
-> registration
-> Library visibility/readiness
```

CI proves protocol and authority contracts, but only the real host can prove the configured controller address, worker token, network reachability, actual artifact transfer, filesystem ownership, and materialization against real data roots.

## 9. Synthesis authority model

Synthesis is intentionally divided into proposal, measurement, Preview, approval, and execution.

```text
research objective
-> map bounded evidence inputs
-> measure / inspect
-> construct proposed operation
-> Preview
-> review / approval
-> execute approved current spec
-> materialize output
-> register output + lineage
```

Important properties:

- Preview is non-materializing;
- approval applies to a current Preview/specification rather than a vague conversational intention;
- stale/tampered/drifted preview authority is rejected;
- execution binds to approved inputs/specification;
- deterministic method export preserves a reproducible method artifact;
- Ask object/activity targets correlate conversation/activity to bounded research objects but do not replace execution approval.

Key modules include:

- `synthesis/measured_state.py`;
- `synthesis/bounded_read.py`;
- `synthesis/multi_probe.py`;
- `synthesis/pair_probe.py`;
- `synthesis/spec_export.py`;
- `synthesis_preview.py`;
- `synthesis_execution_authority.py`;
- `synthesis_executor.py`;
- `synthesis_object_targets.py`;
- `synthesis_thread_store.py`.

## 10. Connected-account authority

Connected storage/account integrations are principal-bound. They are not global anonymous mounts.

Backend responsibilities include:

- OAuth/PKCE flow state;
- provider/account identity separation;
- multi-account handling;
- credential encryption boundary;
- principal ownership;
- connection verification;
- seed/context integration without treating an OAuth connection as proof that every remote object is held/query-ready locally.

Key modules include:

- `connected_accounts.py`;
- `connected_accounts_http.py`;
- `connected_accounts_security.py`.

CI validates the security/state contracts. The host must still prove real provider reachability and configured callback/session behavior with real credentials.

## 11. Release architecture

The front-door release flow deliberately separates **build**, **preflight**, **promotion**, and **restart verification**.

```text
exact frontend checkout + exact backend checkout
        |
        v
build_optiplex_front_door.sh
        |
        +--> releases/<public_sha>--<private_sha>/
        |       +--> index.html
        |       +--> assets...
        |       +--> research-drive-build.json
        |
        v
preflight_release.sh
        |
        v
promote_front_door.sh
        |
        +--> atomically re-points live dist symlink
        |
        v
systemd restart / verify_front_door_restartability.sh --exercise
```

A build does **not** publish. Promotion is the only action intended to change the live static release pointer.

`promote_front_door.sh` runs preflight with restartability checking before changing the live link. If preflight fails, the old live link remains untouched.

Rollback is a **pair operation**. A complete rollback restores matching frontend/backend checkouts and environment pins, preflights that pair, promotes it, and restarts the service. Repointing only static assets while leaving another backend live is not accepted rollback.

## 12. Authority table

| Concern | Authoritative owner | Non-authoritative evidence |
|---|---|---|
| UI source | chosen public repository SHA | screenshots, branch name |
| backend source | chosen private repository SHA | PR title, local uncommitted code |
| build identity | `research-drive-build.json` inside staged release | directory naming alone |
| research registration | registry authority | UI card existence |
| physical possession | holdings/local/remote possession evidence | provenance URL alone |
| provenance | explicit source/fetch/method evidence | local path alone |
| query readiness | readiness/query checks | `registered=true` |
| execution authority | approved current execution spec | model intent/chat text |
| job output identity | explicit persisted manifest/job/run evidence | dataset title/path |
| live release | live release symlink + running backend identity | latest git branch |
| connected account | principal-bound verified connection state | provider name in UI |

## 13. Failure philosophy

The backend should prefer an explicit incomplete/unknown state to an invented positive state.

Examples:

- no provenance evidence -> provenance remains unknown;
- no local/remote possession proof -> do not claim held;
- registered but missing bytes -> do not claim query-ready;
- proposed operation without current Preview/approval -> do not execute;
- output without explicit manifest evidence -> do not invent manifest identity;
- failed preflight -> do not move live release;
- failed host verification -> preserve the previous release and return evidence.

That fail-closed posture is part of the product architecture, not merely defensive error handling.
