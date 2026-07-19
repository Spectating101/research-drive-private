# Sol review: agent operates platform (schedule → History)

Branch: `feat/discover-main-converge`  
Date: 2026-07-14

## Product claim under review

Ask should **operate** the desk: when faculty ask to schedule procurement/refresh (e.g. every Monday 10:00), the platform must register a durable Discover History row — not leave the action as chat prose.

## What landed

### FE (drive/src/v2)
- Integration indicators: desk trust chips, Ask tool-phase timeline, object estate crumb
- History: subscriptions classify under **Scheduled** (not Active)
- Rail context passes `selected.source_id` / `connector_id` into Ask
- Ask `schedule_refresh` refreshes History via `onCollected`

### BE slice (drive/scripts/research_data_mcp) — newly surfaced on this branch
- MCP exposes `research_discover_create_refresh_subscription` + `research_discover_history`
- Direct equipment path: schedule language → `discover_refresh_create` in ~0.1s
- Cadence buckets: manual|daily|weekly|monthly; faculty wording kept as `requested_schedule`
- Honest: `execution_mode=non_executing` until per-source YZU runner exists

## Live proof (this machine)

Ask: “Schedule refresh every Monday at 10:00” + TWSE rail context  
→ action `schedule_refresh`, subscription id returned, History → Scheduled shows Monday wording + “Recorded on platform · auto-run not claimed”

## Open for Sol

1. Is non-executing-but-registered the right honesty bar, or block schedule until a runner exists?
2. Should Monday 10:00 become a real cron/YZU schedule, or stay weekly bucket + requested_schedule?
3. Any FE grammar issues with trust chips / Ask phases vs authority (Nav | Centre | Detail/Ask)?
