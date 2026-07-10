/**
 * Canonical Discover candidate identity (D0a).
 *
 * Precedence:
 * 1. server-provided candidate_key
 * 2. dataset_id
 * 3. canonical DOI
 * 4. source-specific external identifier
 * 5. canonical URL
 * 6. namespaced normalized title fallback
 *
 * Typed prefixes prevent cross-type collisions.
 */

function trim(value) {
  return String(value ?? "").trim();
}

/** Canonical DOI: strip resolver/prefix, lowercase. */
export function canonicalizeDoi(value) {
  let doi = trim(value);
  if (!doi) return "";
  doi = doi.replace(/^doi:\s*/i, "");
  doi = doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "");
  return doi.toLowerCase();
}

/**
 * Canonical URL for identity:
 * - prefer backend-resolved URL when present
 * - trim, drop fragment
 * - lowercase scheme + hostname
 * - remove default ports
 * - keep meaningful query parameters
 */
export function canonicalizeUrl(value) {
  const raw = trim(value);
  if (!raw) return "";
  try {
    const u = new URL(raw);
    u.hash = "";
    u.protocol = u.protocol.toLowerCase();
    u.hostname = u.hostname.toLowerCase();
    if (
      (u.protocol === "http:" && u.port === "80") ||
      (u.protocol === "https:" && u.port === "443")
    ) {
      u.port = "";
    }
    // Normalize pathname trailing slash only for root
    if (u.pathname !== "/" && u.pathname.endsWith("/")) {
      u.pathname = u.pathname.replace(/\/+$/, "");
    }
    return u.toString();
  } catch {
    return raw.toLowerCase();
  }
}

export function normalizeTitle(value) {
  return trim(value).replace(/\s+/g, " ").toLowerCase();
}

/**
 * Canonical action URL for probe / collect / Add-to-lab.
 * Same field preference as the url: identity tier (before DOI fallback):
 * resolved_url → source_url → url → DOI resolver.
 */
export function discoverCandidateUrl(row) {
  if (!row || typeof row !== "object") return "";
  const raw = trim(row.resolved_url || row.source_url || row.url);
  if (raw) return raw;
  const doi = canonicalizeDoi(row.doi);
  if (doi) return `https://doi.org/${doi}`;
  const handle = trim(row.open_handle || row.handle);
  if (handle.startsWith("doi:")) return `https://doi.org/${canonicalizeDoi(handle.slice(4))}`;
  return "";
}

/**
 * Unicode-safe provider namespace (D0.2).
 * NFKC → trim → lowercase → keep letters/numbers/._- → collapse other runs to _.
 */
export function slugifyProvider(value) {
  const raw = trim(value);
  if (!raw) return "unknown";
  let s = raw.normalize("NFKC").trim().toLowerCase();
  s = s.replace(/[^\p{L}\p{N}._-]+/gu, "_").replace(/^_+|_+$/gu, "");
  s = Array.from(s).slice(0, 80).join("");
  if (!/[\p{L}\p{N}]/u.test(s)) return "unknown";
  return s || "unknown";
}

function providerSlug(row) {
  const host = (() => {
    const url = trim(row?.url || row?.source_url || row?.resolved_url || "");
    if (!url) return "";
    try {
      return new URL(url).hostname.replace(/^www\./, "").toLowerCase();
    } catch {
      return "";
    }
  })();
  const raw =
    trim(row?.provider) ||
    trim(row?.publisher) ||
    trim(row?.source) ||
    trim(row?.collect_via) ||
    trim(row?.kind) ||
    host ||
    "";
  return slugifyProvider(raw);
}

function sourceExternalId(row) {
  const kind = trim(row?.kind).toLowerCase();
  const handle = trim(row?.handle || row?.open_handle);
  if (handle.startsWith("hf:")) return { provider: "huggingface", id: handle.slice(3) };
  if (handle.startsWith("doi:")) return null; // DOI handled separately
  if (kind === "huggingface") {
    const id = trim(row?.hf_id || row?.id || row?.external_id);
    if (id && !id.includes("://")) return { provider: "huggingface", id };
  }
  const external = trim(row?.external_id || row?.source_id);
  if (external) return { provider: providerSlug(row), id: external };
  return null;
}

/**
 * @param {object|null|undefined} row
 * @returns {string} typed candidate key, or "" if empty
 */
export function candidateKey(row) {
  if (!row || typeof row !== "object") return "";

  const serverKey = trim(row.candidate_key);
  if (serverKey) return serverKey;

  const datasetId = trim(row.dataset_id || (row.kind === "local_registry" ? row.id : ""));
  if (datasetId) return `dataset:${datasetId}`;

  const doi = canonicalizeDoi(row.doi);
  if (doi) return `doi:${doi}`;

  const ext = sourceExternalId(row);
  if (ext?.id) return `source:${ext.provider}:${ext.id}`;

  const url = canonicalizeUrl(row.resolved_url || row.source_url || row.url);
  if (url) return `url:${url}`;

  const title = normalizeTitle(row.title || row.name);
  if (title) return `title:${providerSlug(row)}:${title}`;

  return "";
}

/** Stamp candidate_key onto a row copy (does not mutate). */
export function withCandidateKey(row) {
  if (!row || typeof row !== "object") return row;
  const key = candidateKey(row);
  if (!key || row.candidate_key === key) return row;
  return { ...row, candidate_key: key };
}

/**
 * Exact job↔candidate association only (no title matching).
 * Jobs may carry candidate_key / connector_id at top level or under request/plan.
 */
export function jobMatchesCandidate(job, row) {
  if (!job || !row) return false;
  const rowKey = candidateKey(row);
  const jobKey = trim(
    job.candidate_key ||
      job.request?.candidate_key ||
      job.plan?.candidate_key ||
      "",
  );
  if (rowKey && jobKey && rowKey === jobKey) return true;

  const rowConnector = trim(
    row.connector_id || row.probe_connector_id || row.connector?.connector_id || row.connector?.id || "",
  );
  const jobConnector = trim(
    job.connector_id ||
      job.request?.connector_id ||
      job.plan?.connector_id ||
      "",
  );
  if (rowConnector && jobConnector && rowConnector === jobConnector) return true;
  return false;
}

export function isCandidateQueued(row, jobs = []) {
  if (!row || !Array.isArray(jobs) || !jobs.length) return false;
  if (row.queued === true && (row.candidate_key || row.connector_id)) {
    // Trust only if already stamped from an exact association path
    return jobs.some((j) => jobMatchesCandidate(j, row));
  }
  return jobs.some((j) => {
    const status = String(j?.status || "").toLowerCase();
    if (!["pending_approval", "queued", "running"].includes(status)) return false;
    return jobMatchesCandidate(j, row);
  });
}
