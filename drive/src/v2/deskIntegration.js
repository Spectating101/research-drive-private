/** Integration indicators — subordinate trust chips & object estate crumbs.
 * Authority: UI_PRODUCT_AUTHORITY §14–15 (named tool activity, freshness, location).
 * Not an ops console: only surfaces faculty-relevant estate truth.
 */

function formatAge(ts) {
  if (!ts) return null;
  const ms = typeof ts === "number" ? ts : Date.parse(String(ts));
  if (!Number.isFinite(ms)) return String(ts);
  const sec = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
  return `${Math.round(sec / 86400)}d ago`;
}

/**
 * Compact header chips from live /health — faculty chrome only.
 * Emit warn/bad only (ok/muted estate detail belongs on Resources).
 * @returns {{ id: string, label: string, tone: 'warn'|'bad' }[]}
 */
export function buildDeskIntegrationChips(health) {
  if (!health?.desk) return [];
  const desk = health.desk;
  const chips = [];

  // Desk status badge already lives in the header — only chip when degraded.
  if (String(health.status || "").toLowerCase() === "degraded") {
    chips.push({ id: "desk", label: "Desk degraded", tone: "warn" });
  }

  const gdrive = desk.gdrive;
  if (gdrive && gdrive.ok === false) {
    chips.push({ id: "gdrive", label: "Vault unreachable", tone: "bad" });
  }

  const hot = desk.storage_tiers?.hot;
  if (hot && hot.headroom_ok === false) {
    const pct = hot.used_pct != null ? `${Math.round(Number(hot.used_pct))}%` : "tight";
    chips.push({ id: "hot", label: `NVMe ${pct}`, tone: "warn" });
  }

  const cache = desk.storage_tiers?.cache;
  if (cache?.mounted === false) {
    chips.push({ id: "cache", label: "Cache unmounted", tone: "warn" });
  }

  const pending = Number(desk.jobs?.pending_approval ?? 0);
  const oldest = desk.jobs?.actionable?.pending_oldest_age_days;
  if (pending > 0 && oldest != null && Number(oldest) >= 7) {
    chips.push({
      id: "debt",
      label: `${pending} pending · ${Math.round(Number(oldest))}d`,
      tone: "warn",
    });
  }

  const priority = { bad: 0, warn: 1 };
  return chips
    .sort((a, b) => (priority[a.tone] ?? 9) - (priority[b.tone] ?? 9))
    .slice(0, 3);
}

/**
 * One-line estate crumb for a selected Library dataset or Discover candidate.
 * @returns {{ location: string|null, freshness: string|null, authority: string|null }}
 */
export function buildObjectEstateCrumb(object, { probeState = null, searchMeta = null } = {}) {
  if (!object) return { location: null, freshness: null, authority: null };

  const vault =
    object.vault_path ||
    object.gdrive_path ||
    object.path ||
    object.local_path ||
    object.fields?.vault ||
    null;
  const endpoint = object.endpoint || object.url || object.source_url || null;
  const provider = object.provider || object.source || object.publisher || null;

  let location = null;
  if (vault) location = `Vault · ${String(vault).slice(0, 64)}`;
  else if (endpoint) location = `Remote · ${String(endpoint).replace(/^https?:\/\//, "").slice(0, 48)}`;
  else if (provider) location = `Provider · ${String(provider).slice(0, 40)}`;
  else if (object.dataset_id) location = `Registry · ${object.dataset_id}`;

  const stamp =
    object.refreshed_at ||
    object.updated_at ||
    object.last_modified ||
    object.as_of ||
    object.checked_at ||
    null;
  let freshness = formatAge(stamp);
  if (probeState?.observedAt) {
    freshness = `Probed ${formatAge(probeState.observedAt)}`;
  } else if (probeState?.loading) {
    freshness = "Probe in flight";
  } else if (searchMeta?.search_mode) {
    const mode = String(searchMeta.search_mode);
    freshness =
      mode === "catalog"
        ? "Catalog · query-time"
        : mode === "live"
          ? "Live search"
          : `Search · ${mode}`;
  } else if (!freshness && object.access_mode) {
    freshness = `Access · ${String(object.access_mode).replace(/_/g, " ")}`;
  }

  let authority = null;
  if (object.kind === "external_candidate" || object.external || object.source_id) {
    authority = searchMeta?.search_mode === "live" ? "Live connector" : "Source registry";
  } else if (object.dataset_id) {
    const ready =
      object.analysis_readiness === "query_ready" ||
      object.analysis_readiness === "instant" ||
      object.analysis_readiness === "instant_or_minutes" ||
      object.analysis_readiness === "queryable";
    authority = ready ? "Query-ready registry" : "Library registry";
  }
  if (object.cached === true) authority = (authority ? `${authority} · ` : "") + "Cached";
  if (object.demo || object._demo) authority = "Demo fixture — verify source";

  return { location, freshness, authority };
}

/**
 * Normalize stream activity/progress into a timeline step.
 */
export function normalizeActivityStep(eventOrText, prev = []) {
  const event =
    eventOrText && typeof eventOrText === "object"
      ? eventOrText
      : { text: String(eventOrText || "") };
  const text = String(event.text || event.label || "").trim();
  if (!text) return prev;
  const phase = String(event.phase || event.action || "working").trim() || "working";
  const last = prev[prev.length - 1];
  if (last && last.text === text && last.phase === phase) return prev;
  const next = [...prev, { phase, text, at: Date.now() }];
  return next.slice(-8);
}
