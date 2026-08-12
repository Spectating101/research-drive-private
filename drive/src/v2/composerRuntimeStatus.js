/**
 * Reads /health.desk.composer_runtime the way the backend actually produces
 * it (desk_composer_health.py composer_runtime_status): ready / degraded /
 * stale / unverified / unavailable. Settings, the header chip, and Resources
 * all render this exact mapping so they cannot disagree.
 *
 * verified: true is set on BOTH "ready" and "degraded" — it means "we have a
 * real observation," not "the provider is healthy." Branching on `verified`
 * alone (instead of `status`) would render a failed probe as Ready.
 */
export function composerRuntimeRead(runtime) {
  if (!runtime || typeof runtime !== "object") return null;
  const status = String(runtime.status || "").trim();
  switch (status) {
    case "ready":
      return {
        status,
        ready: true,
        warn: false,
        label: "Assistant ready",
        short: "Ready",
        why: "confirmed live",
      };
    case "degraded":
      return {
        status,
        ready: false,
        warn: true,
        label: "Assistant degraded",
        short: "Degraded",
        why: "last probe failed",
      };
    case "stale":
      return {
        status,
        ready: false,
        warn: true,
        label: "Assistant needs recheck",
        short: "Needs recheck",
        why: "prior observation expired",
      };
    case "unverified":
      return {
        status,
        ready: false,
        warn: true,
        label: "Assistant unverified",
        short: "Unverified",
        why: "not yet probed live",
      };
    case "unavailable":
      return {
        status,
        ready: false,
        warn: true,
        label: "Assistant unavailable",
        short: "Not configured",
        why: "no assistant key",
      };
    default:
      // Backend reported composer_runtime but with a status this frontend
      // doesn't recognize yet — never default that to Ready.
      return {
        status: status || "unknown",
        ready: false,
        warn: true,
        label: "Assistant status unknown",
        short: "Unknown",
        why: "unrecognized runtime status",
      };
  }
}
