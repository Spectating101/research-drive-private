/**
 * History noise fence — Phase 1 truth.
 *
 * Backend triage already cancels fixture/integration jobs with
 * `triage noise: fixture_*`. Those cancelled rows must not reappear as
 * professor-facing "Recovery required" lifecycle items.
 *
 * System verification / host-prove traffic is a separate tier: kept accessible
 * but demoted from the default research lifecycle trail. Records are never
 * deleted; lifecycle labels are not inferred here.
 */

const NOISE_RE =
  /triage\s*noise|fixture[_ -]?(http_manifest|probe|h\b)|fixture_|no[_ -]?promotion|archive[_ -]?before[_ -]?promote|missing[_ -]?manifest|deploy\s*smoke|post-merge|day\d+\s*deploy|integration[_ -]?smoke|smoke:\s*http_manifest/i;

const FIXTURE_TARGET_RE = /^(raw_usdt_history|fixture[_-]|probe[_-]?no[_-]?promotion)/i;

/** Desk/Ask/search telemetry — useful audit, not durable procurement lifecycle. */
const SEARCH_TELEMETRY_ACTIONS =
  /^(ask|semantic_discover|discover|search|probe|query|preview|bq_)/i;

/**
 * Explicit provenance / traffic markers from desk or adapters.
 * Prefer these over name heuristics.
 */
const EXPLICIT_SYSTEM_VERIFICATION_RE =
  /^(system[_-]?verification|ops[_-]?verification|host[_-]?acceptance|prove|canary|ops[_-]?traffic)$/i;

/**
 * Narrow legacy name prefixes that are obviously host/system prove traffic.
 * Transparent fallback only when explicit metadata is absent.
 */
const LEGACY_SYSTEM_VERIFICATION_NAME_RE =
  /\b(harden_|aa_prove|hostile_|rev_live|autoblock_|host_auto_|ssrf\d*_|revision[-_]?prove|canary_|robust[_-]?gate)/i;

function blob(event) {
  const meta = event?.meta || {};
  return [
    event?.target,
    event?.title,
    event?.summary,
    event?.status,
    event?.error,
    meta.summary,
    meta.error,
    meta.status,
    meta.kind,
    event?.id,
  ]
    .filter(Boolean)
    .join("\n");
}

function nameBlob(event) {
  const meta = event?.meta || {};
  return [
    event?.id,
    event?.target,
    event?.title,
    event?.dataset_id,
    meta.dataset_id,
    meta.evidence_identity,
    meta.identity,
  ]
    .filter(Boolean)
    .join("\n");
}

function explicitSystemVerificationMark(event) {
  if (!event) return "";
  const meta = event.meta || {};
  if (event.system_verification === true || meta.system_verification === true) {
    return "system_verification";
  }
  if (meta.ops_traffic === true || event.ops_traffic === true) {
    return "ops_traffic";
  }
  const candidates = [
    event.traffic_kind,
    meta.traffic_kind,
    meta.traffic,
    meta.lane,
    meta.purpose,
    meta.origin,
    meta.provenance?.kind,
    typeof meta.provenance === "string" ? meta.provenance : "",
    event.provenance?.kind,
    typeof event.provenance === "string" ? event.provenance : "",
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  for (const value of candidates) {
    if (EXPLICIT_SYSTEM_VERIFICATION_RE.test(value)) return value;
  }
  return "";
}

export function isHistoryNoise(event) {
  if (!event) return true;
  const text = blob(event);
  if (NOISE_RE.test(text)) return true;
  const target = String(event.target || event.title || "").trim();
  if (FIXTURE_TARGET_RE.test(target) && /fixture|triage|noise|stuck/i.test(text)) return true;
  if (event.meta?.noise === true || event.noise === true) return true;
  if (String(event.meta?.noise_reason || event.noise_reason || "").trim()) return true;
  return false;
}

/** Terra donor: Ask/search rows stay off the default durable trail. */
export function isDeskSearchTelemetry(event) {
  if (!event) return false;
  if (event.durable === true || event.kind === "collection_run") return false;
  const action = String(event.action || "").toLowerCase();
  if (SEARCH_TELEMETRY_ACTIONS.test(action)) return true;
  if (event.meta?.telemetry === true || event.telemetry === true) return true;
  if (event.meta?.ask_telemetry === true) return true;
  return false;
}

/**
 * System verification / host-prove traffic — secondary in History UI.
 * Does not change lifecycle labels; only presentation tiering.
 *
 * @returns {{ matched: boolean, basis: 'explicit_metadata' | 'name_pattern' | '', detail: string }}
 */
export function systemVerificationClassification(event) {
  if (!event) return { matched: false, basis: "", detail: "" };
  const explicit = explicitSystemVerificationMark(event);
  if (explicit) {
    return { matched: true, basis: "explicit_metadata", detail: explicit };
  }
  const names = nameBlob(event);
  const match = names.match(LEGACY_SYSTEM_VERIFICATION_NAME_RE);
  if (match) {
    return { matched: true, basis: "name_pattern", detail: match[1] };
  }
  return { matched: false, basis: "", detail: "" };
}

export function isSystemVerificationTraffic(event) {
  return systemVerificationClassification(event).matched;
}

function collapseKey(event) {
  const target = String(event?.target || event?.title || "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
  const status = String(event?.status || event?.meta?.status || "")
    .trim()
    .toLowerCase();
  const summary = String(event?.summary || event?.meta?.summary || "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
    .slice(0, 120);
  return `${target}|${status}|${summary}`;
}

function collapseDuplicates(events = []) {
  const seen = new Set();
  const visible = [];
  let collapsedDuplicates = 0;
  for (const event of events) {
    const key = collapseKey(event);
    if (!key || seen.has(key)) {
      collapsedDuplicates += 1;
      continue;
    }
    seen.add(key);
    visible.push(event);
  }
  return { visible, collapsedDuplicates };
}

/**
 * @returns {{
 *   visible: object[],
 *   searchTelemetry: object[],
 *   systemVerification: object[],
 *   hiddenNoise: number,
 *   hiddenSearchTelemetry: number,
 *   hiddenSystemVerification: number,
 *   collapsedDuplicates: number,
 * }}
 */
export function fenceHistoryEvents(
  events = [],
  {
    includeNoise = false,
    includeSearchTelemetry = false,
    includeSystemVerification = false,
  } = {},
) {
  const list = Array.isArray(events) ? events.filter(Boolean) : [];
  const withoutNoise = includeNoise ? list : list.filter((event) => !isHistoryNoise(event));
  const hiddenNoise = list.length - withoutNoise.length;
  const searchTelemetry = withoutNoise.filter((event) => isDeskSearchTelemetry(event));
  const afterSearch = includeSearchTelemetry
    ? withoutNoise
    : withoutNoise.filter((event) => !isDeskSearchTelemetry(event));
  const hiddenSearchTelemetry = includeSearchTelemetry ? 0 : searchTelemetry.length;

  const systemVerification = afterSearch.filter((event) => isSystemVerificationTraffic(event));
  const researcher = includeSystemVerification
    ? afterSearch
    : afterSearch.filter((event) => !isSystemVerificationTraffic(event));
  const hiddenSystemVerification = includeSystemVerification ? 0 : systemVerification.length;

  const { visible, collapsedDuplicates } = collapseDuplicates(researcher);
  const systemCollapsed = collapseDuplicates(systemVerification);

  return {
    visible,
    searchTelemetry,
    systemVerification: systemCollapsed.visible,
    hiddenNoise,
    hiddenSearchTelemetry,
    hiddenSystemVerification,
    collapsedDuplicates: collapsedDuplicates + systemCollapsed.collapsedDuplicates,
  };
}
