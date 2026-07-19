/** Canonical, additive authority contract for Library and registered Synthesis assets. */

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function toArray(value) {
  if (Array.isArray(value)) return value;
  if (value == null || value === "") return [];
  return [value];
}

function identifier(value) {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (!value || typeof value !== "object") return null;
  return firstValue(value.dataset_id, value.asset_id, value.revision_id, value.id, value.name, value.uri, value.path) || null;
}

function truthy(value) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") return /^(true|yes|verified|registered|ready|query_ready|query-ready|ok)$/i.test(value.trim());
  return false;
}

function countValue(...values) {
  const value = Number(firstValue(...values));
  return Number.isFinite(value) && value >= 0 ? value : null;
}

function readinessState(asset) {
  const raw = String(firstValue(asset?.analysis_readiness, asset?.readiness, asset?.state, asset?.status) || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  if (/^(unavailable|not_verified|not_available|not_ready|blocked|offline)$/.test(raw)) {
    return "unavailable_unverified";
  }
  if (["instant", "instant_query", "query_ready", "queryable", "ready"].includes(raw) || truthy(asset?.query_ready) || truthy(asset?.queryable)) {
    return "query_ready";
  }
  if (["registered", "catalogued", "cataloged"].includes(raw) || asset?.registry_id || truthy(asset?.registered)) return "registered";
  if (["metadata", "metadata_only", "described", "indexed"].includes(raw) || asset?.dataset_id || asset?.id) return "metadata_only";
  return "unknown";
}

function verificationState(asset) {
  const raw = String(
    firstValue(
      asset?.verification?.state,
      asset?.verification_status,
      asset?.source_verification,
      asset?.verified,
    ) || "",
  )
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  if (raw === "verified" || raw === "true") return "verified";
  if (/matched|correspond/.test(raw)) return "matched";
  if (/partial|incomplete/.test(raw)) return "partial";
  if (/unverified|false|failed/.test(raw)) return "unverified";
  return "not_checked";
}

const READINESS_LABELS = {
  metadata_only: "Metadata only",
  registered: "Registered",
  query_ready: "Query-ready",
  unavailable_unverified: "Unavailable / not verified",
  unknown: "Unknown",
};

const VERIFICATION_LABELS = {
  verified: "Verified",
  matched: "Matched",
  partial: "Partial",
  unverified: "Unverified",
  not_checked: "Not checked",
};

export function normalizeAssetAuthority(asset = {}) {
  const readiness = readinessState(asset);
  const verification = verificationState(asset);
  const source = asset?.source && typeof asset.source === "object" ? asset.source : {};
  const sourceLabel = typeof asset?.source === "string" ? asset.source : null;
  const provenance = asset?.provenance && typeof asset.provenance === "object" ? asset.provenance : {};
  const lineage = asset?.lineage && typeof asset.lineage === "object" ? asset.lineage : {};
  const manifest = asset?.manifest && typeof asset.manifest === "object" ? asset.manifest : {};
  const refresh = asset?.refresh && typeof asset.refresh === "object" ? asset.refresh : {};
  const verificationDetail = asset?.verification && typeof asset.verification === "object" ? asset.verification : {};

  const inputs = toArray(
    firstValue(
      lineage.inputs,
      provenance.inputs,
      asset?.input_dataset_ids,
      asset?.source_dataset_ids,
      asset?.parents,
      asset?.derived_from,
    ),
  )
    .map(identifier)
    .filter(Boolean);
  const snapshots = toArray(
    firstValue(lineage.source_snapshots, provenance.source_snapshots, asset?.source_snapshots),
  )
    .map(identifier)
    .filter(Boolean);

  const archiveVerified = truthy(
    firstValue(
      asset?.archive_verified,
      asset?.drive_verified,
      provenance.archive_verified,
      manifest.archive_verified,
    ),
  );

  return {
    identity: {
      dataset_id: String(firstValue(asset?.dataset_id, asset?.asset_id, asset?.id) || ""),
      registry_id: firstValue(asset?.registry_id, asset?.registration_id, provenance.registry_id) || null,
      revision_id: firstValue(asset?.revision_id, asset?.version_id, provenance.revision_id, asset?.version) || null,
      title: firstValue(asset?.title, asset?.name, asset?.label) || null,
    },
    readiness: {
      state: readiness,
      label: READINESS_LABELS[readiness],
      registered: readiness === "registered" || readiness === "query_ready",
      query_ready: readiness === "query_ready",
    },
    source: {
      id: firstValue(source.id, asset?.source_id, provenance.source_id) || null,
      label: firstValue(source.label, source.name, sourceLabel, asset?.provider, asset?.origin) || null,
      url: firstValue(source.url, asset?.source_url, asset?.url) || null,
      version: firstValue(source.version, provenance.source_version, asset?.source_version) || null,
      snapshot_at: firstValue(source.snapshot_at, provenance.snapshot_at, asset?.source_snapshot_at) || null,
    },
    verification: {
      state: verification,
      label: VERIFICATION_LABELS[verification],
      summary: firstValue(verificationDetail.summary, asset?.verification_summary) || null,
      checked_at: firstValue(verificationDetail.checked_at, asset?.verified_at) || null,
      checks: toArray(firstValue(verificationDetail.checks, asset?.verification_checks))
        .map(identifier)
        .filter(Boolean),
    },
    lineage: {
      inputs,
      source_snapshots: snapshots,
      manifest_id: firstValue(manifest.id, asset?.manifest_id, provenance.manifest_id) || null,
      checksum: firstValue(asset?.checksum, manifest.checksum, provenance.checksum, asset?.sha256) || null,
      method_revision: firstValue(asset?.method_revision, provenance.method_revision, lineage.method_revision) || null,
    },
    storage: {
      vault_path: firstValue(asset?.vault_path, asset?.gdrive_path, provenance.vault_path) || null,
      local_path: firstValue(asset?.local_root, asset?.local_path, provenance.local_path) || null,
      archive_verified: archiveVerified,
    },
    refresh: {
      policy: firstValue(refresh.policy, asset?.refresh_policy) || null,
      last_refreshed_at: firstValue(refresh.last_refreshed_at, asset?.last_refreshed_at, asset?.updated_at) || null,
      next_refresh_at: firstValue(refresh.next_refresh_at, asset?.next_refresh_at) || null,
      stale: truthy(firstValue(refresh.stale, asset?.stale)),
    },
    shape: {
      rows: countValue(asset?.rows, asset?.row_count, asset?.n_rows),
      fields: countValue(asset?.fields, asset?.field_count, asset?.n_fields),
      entities: countValue(asset?.entities, asset?.entity_count, asset?.n_entities),
      grain: firstValue(asset?.grain, asset?.data_grain, asset?.unit_of_observation) || null,
      coverage: firstValue(asset?.coverage, asset?.date_coverage, asset?.time_coverage) || null,
    },
  };
}

export function assetAuthorityContext(asset = {}) {
  const authority = normalizeAssetAuthority(asset);
  return {
    dataset_id: authority.identity.dataset_id || undefined,
    registry_id: authority.identity.registry_id || undefined,
    revision_id: authority.identity.revision_id || undefined,
    readiness: authority.readiness.state,
    source: authority.source.label || authority.source.id || undefined,
    source_url: authority.source.url || undefined,
    source_version: authority.source.version || undefined,
    verification: authority.verification.state,
    verification_summary: authority.verification.summary || undefined,
    lineage_inputs: authority.lineage.inputs.length ? authority.lineage.inputs : undefined,
    source_snapshots: authority.lineage.source_snapshots.length ? authority.lineage.source_snapshots : undefined,
    manifest_id: authority.lineage.manifest_id || undefined,
    checksum: authority.lineage.checksum || undefined,
    method_revision: authority.lineage.method_revision || undefined,
    vault_path: authority.storage.vault_path || undefined,
    archive_verified: authority.storage.archive_verified || undefined,
    refresh_policy: authority.refresh.policy || undefined,
    last_refreshed_at: authority.refresh.last_refreshed_at || undefined,
    next_refresh_at: authority.refresh.next_refresh_at || undefined,
    stale: authority.refresh.stale || undefined,
    rows: authority.shape.rows ?? undefined,
    fields: authority.shape.fields ?? undefined,
    entities: authority.shape.entities ?? undefined,
    grain: authority.shape.grain || undefined,
    coverage: authority.shape.coverage || undefined,
  };
}
