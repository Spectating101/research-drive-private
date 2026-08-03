/**
 * Desk status is stated once in the header.
 *
 * The header renders a status badge derived from deskStatus, and separately
 * renders integration chips. Both can express the same condition — production
 * emits an integration chip literally labelled "Desk degraded" — which put two
 * identical pills side by side. Deriving the badge and filtering the chips
 * through one module keeps the rule in a single place.
 */

const TONE_VISIBLE = ["warn", "error", "danger", "bad"];

export function deskStatusBadge(deskStatus, usingSeed = false) {
  if (deskStatus === "ok") return { label: "Live registry", tone: "ok" };
  if (deskStatus === "syncing") return { label: "Syncing…", tone: "muted" };
  if (deskStatus === "empty") return { label: "Empty registry", tone: "warn" };
  if (usingSeed || deskStatus === "demo") return { label: "Demo catalog", tone: "warn" };
  if (deskStatus === "degraded") return { label: "Desk degraded", tone: "warn" };
  return { label: "Desk API offline", tone: "warn" };
}

function normalizeLabel(value) {
  return String(value || "").trim().toLowerCase();
}

/**
 * Chips worth showing beside the status badge: attention-toned, not a restatement
 * of the badge, and not duplicated among themselves.
 */
export function visibleIntegrationChips(chips, statusLabel) {
  const list = Array.isArray(chips) ? chips : [];
  const taken = new Set([normalizeLabel(statusLabel)]);
  const out = [];
  for (const chip of list) {
    if (!chip || !TONE_VISIBLE.includes(chip.tone)) continue;
    const key = normalizeLabel(chip.label);
    if (!key || taken.has(key)) continue;
    taken.add(key);
    out.push(chip);
  }
  return out;
}
