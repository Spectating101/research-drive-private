/**
 * Shared Desk API / registry health wording for Header and Settings.
 * Derived only from live /health facts — never invents Ready / Live when unknown.
 * Prefers backend health.projection when complete; otherwise raw health.status.
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

function projectionDetail(components) {
  if (components == null) return "";
  if (typeof components === "string") return components.trim();
  if (Array.isArray(components)) {
    return components
      .map((c) => {
        if (c == null) return "";
        if (typeof c === "string") return c;
        const name = c.name || c.id || c.label || "";
        const st = c.status != null ? String(c.status) : "";
        if (name && st) return `${name}: ${st}`;
        return String(name || st || "");
      })
      .filter(Boolean)
      .join(" · ");
  }
  if (typeof components === "object") {
    return Object.entries(components)
      .map(([key, value]) => `${key}: ${value}`)
      .join(" · ");
  }
  return "";
}

/**
 * Complete projection requires an explicit desk_status or status.
 * Incomplete / missing projection must not be promoted to Live.
 * @returns {null|{ status: string, label: string, detail: string, tone: string, ok: boolean }}
 */
function presentationFromProjection(projection, { usingSeed = false } = {}) {
  if (projection == null || typeof projection !== "object") return null;

  const statusSource =
    projection.desk_status != null && String(projection.desk_status).trim() !== ""
      ? projection.desk_status
      : projection.status;
  if (statusSource == null || String(statusSource).trim() === "") return null;

  const status = String(statusSource).toLowerCase();
  const label =
    projection.label != null && String(projection.label).trim() !== ""
      ? String(projection.label)
      : deskStatusBadgeLabel(status, { usingSeed });
  const fromComponents = projectionDetail(projection.components);

  if (usingSeed && status === "ok") {
    return {
      status: "empty",
      label: deskStatusBadgeLabel("empty"),
      detail: fromComponents || "Live /health ok but catalog is empty — showing seed fixtures",
      tone: "warn",
      ok: false,
    };
  }

  if (usingSeed || status === "demo") {
    return {
      status: "demo",
      label: deskStatusBadgeLabel("demo", { usingSeed: true }),
      detail: fromComponents || "Offline seed fixtures — not live registry truth",
      tone: "warn",
      ok: false,
    };
  }

  if (status === "ok") {
    return {
      status: "ok",
      label,
      detail: fromComponents || "Catalog · Ask · jobs reachable",
      tone: "ok",
      ok: true,
    };
  }

  if (status === "degraded") {
    return {
      status: "degraded",
      label,
      detail: fromComponents || "Health payload reports degraded",
      tone: "warn",
      ok: false,
    };
  }

  return {
    status,
    label,
    detail: fromComponents || `Health status: ${statusSource}`,
    tone: status === "syncing" ? "muted" : "warn",
    ok: false,
  };
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

  const projected = presentationFromProjection(health.projection, { usingSeed });
  if (projected) return projected;

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

  const count = Number(datasetCount) || 0;

  // Only an explicit /health ok may yield Live — catalog count informs detail only.
  if (raw === "ok") {
    return {
      status: "ok",
      label: deskStatusBadgeLabel("ok"),
      detail:
        count > 0
          ? `Catalog · Ask · jobs reachable · ${count} datasets`
          : "Catalog · Ask · jobs reachable",
      tone: "ok",
      ok: true,
    };
  }

  if (!raw) {
    return {
      status: "unknown",
      label: deskStatusBadgeLabel("unknown"),
      detail:
        count > 0
          ? `Health payload missing status · ${count} catalog datasets seen`
          : "Health payload missing or degraded",
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
