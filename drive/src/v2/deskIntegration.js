/** Integration indicators — subordinate trust chips & object estate crumbs.
 * Authority: UI_PRODUCT_AUTHORITY §14–15 (named tool activity, freshness, location).
 * Not an ops console: only surfaces faculty-relevant estate truth.
 */

function tierLabel(tier) {
  if (!tier || typeof tier !== "object") return null;
  return String(tier.label || tier.role || "").trim() || null;
}

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
 * Compact header chips from live /health — only when something is notable.
 * @returns {{ id: string, label: string, tone: 'ok'|'warn'|'muted'|'bad' }[]}
 */
export function buildDeskIntegrationChips(health) {
  if (!health?.desk) return [];
  const desk = health.desk;
  const chips = [];
  const status = String(health.status || "").toLowerCase();

  if (status === "degraded") {
    chips.push({ id: "desk", label: "Desk degraded", tone: "warn" });
  } else if (status === "ok") {
    chips.push({ id: "desk", label: "Desk online", tone: "ok" });
  }

  const gdrive = desk.gdrive;
  if (gdrive && gdrive.ok === false) {
    chips.push({ id: "gdrive", label: "Vault unreachable", tone: "bad" });
  } else if (gdrive && gdrive.ok === true) {
    const label = tierLabel(desk.storage_tiers?.canonical) || "GDrive vault";
    chips.push({ id: "gdrive", label, tone: "ok" });
  }

  const hot = desk.storage_tiers?.hot;
  if (hot && hot.headroom_ok === false) {
    const pct = hot.used_pct != null ? `${Math.round(Number(hot.used_pct))}%` : "tight";
    chips.push({ id: "hot", label: `NVMe ${pct}`, tone: "warn" });
  }

  const cache = desk.storage_tiers?.cache;
  if (cache?.mounted === false) {
    chips.push({ id: "cache", label: "Cache unmounted", tone: "warn" });
  } else if (cache?.mounted === true && cache.label) {
    chips.push({ id: "cache", label: String(cache.label).slice(0, 22), tone: "muted" });
  }

  const mcp = desk.mcp_tools?.total;
  if (mcp != null && Number(mcp) > 0) {
    chips.push({ id: "mcp", label: `${mcp} agent tools`, tone: "muted" });
  }

  const brain = desk.brain || desk.composer_model;
  if (brain) {
    chips.push({
      id: "brain",
      label: String(brain).replace(/_/g, " ").slice(0, 24),
      tone: "muted",
    });
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

  // Cap: keep header quiet — prefer warn/bad, then ok/muted.
  const priority = { bad: 0, warn: 1, ok: 2, muted: 3 };
  return chips
    .sort((a, b) => (priority[a.tone] ?? 9) - (priority[b.tone] ?? 9))
    .slice(0, 5);
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
    authority = object.analysis_readiness === "query_ready" ? "Query-ready registry" : "Lab registry";
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
