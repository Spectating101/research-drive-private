/**
 * Shared Desk API / registry health wording for Header and Settings.
 * Derived only from live /health facts — never invents Ready / Live when unknown.
 */

/** Badge / summary label for a normalized deskStatus code (Header + Settings). */
export function deskStatusBadgeLabel(status, { usingSeed = false } = {}) {
  if (status === "ok") return "Live registry";
  if (status === "syncing") return "Syncing…";
  if (status === "empty") return "Empty registry";
  if (usingSeed || status === "demo") return "Demo catalog";
  if (status === "degraded") return "Desk degraded";
  return "Desk API offline";
}

/**
 * @param {object|null|undefined} health
 * @param {{ usingSeed?: boolean, datasetCount?: number }} [opts]
 * @returns {{
 *   status: string,
 *   label: string,
 *   detail: string,
 *   tone: 'ok'|'warn'|'muted',
 *   ok: boolean,
 * }}
 */
export function deskApiHealthPresentation(health, { usingSeed = false, datasetCount = 0 } = {}) {
  if (health == null) {
    return {
      status: "syncing",
      label: deskStatusBadgeLabel("syncing"),
      detail: "Waiting for /health",
      tone: "muted",
      ok: false,
    };
  }

  const raw = String(health.status || "").toLowerCase();

  if (usingSeed && raw === "ok") {
    return {
      status: "empty",
      label: deskStatusBadgeLabel("empty"),
      detail: "Live /health ok but catalog is empty — showing seed fixtures",
      tone: "warn",
      ok: false,
    };
  }

  if (usingSeed || raw === "demo") {
    return {
      status: "demo",
      label: deskStatusBadgeLabel("demo", { usingSeed: true }),
      detail: "Offline seed fixtures — not live registry truth",
      tone: "warn",
      ok: false,
    };
  }

  if (raw === "degraded") {
    return {
      status: "degraded",
      label: deskStatusBadgeLabel("degraded"),
      detail: "Health payload reports degraded",
      tone: "warn",
      ok: false,
    };
  }

  if (raw === "ok" || Number(datasetCount) > 0) {
    return {
      status: "ok",
      label: deskStatusBadgeLabel("ok"),
      detail: "Catalog · Ask · jobs reachable",
      tone: "ok",
      ok: true,
    };
  }

  if (!raw) {
    return {
      status: "unknown",
      label: deskStatusBadgeLabel("unknown"),
      detail: "Health payload missing or degraded",
      tone: "warn",
      ok: false,
    };
  }

  return {
    status: raw,
    label: deskStatusBadgeLabel(raw),
    detail: `Health status: ${health.status}`,
    tone: "warn",
    ok: false,
  };
}
