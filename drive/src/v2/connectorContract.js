/** Additive connector/access contract for Discover candidates and source routes. */

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function toArray(value) {
  if (Array.isArray(value)) return value;
  if (value == null || value === "") return [];
  return [value];
}

function truthy(value) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") return /^(true|yes|available|configured|ready|ok|supported)$/i.test(value.trim());
  return false;
}

function accessState(candidate, connector) {
  const raw = String(
    firstValue(
      connector?.access_state,
      connector?.status,
      candidate?.access_state,
      candidate?.access,
      candidate?.availability,
      candidate?.status,
    ) || "",
  )
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  if (/credential|required_auth|needs_auth|unauthorized/.test(raw)) return "credential_required";
  if (/rate_limit|quota_exceeded|throttled/.test(raw)) return "rate_limited";
  if (/unsupported|blocked|forbidden|unavailable|offline/.test(raw)) return "unavailable";
  if (/available|configured|ready|reachable|public|ok/.test(raw) || truthy(connector?.configured)) return "available";
  return "unknown";
}

function syncMode(candidate, connector) {
  const raw = String(
    firstValue(
      connector?.sync_mode,
      connector?.replication_method,
      candidate?.sync_mode,
      candidate?.refresh_mode,
    ) || "",
  )
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  if (/incremental|cursor|cdc/.test(raw) || connector?.cursor_field) return "incremental";
  if (/stream|continuous/.test(raw)) return "stream";
  if (/full|snapshot|batch/.test(raw)) return "snapshot";
  return "unknown";
}

function schemaFields(value) {
  if (Array.isArray(value)) {
    return value
      .map((field) => {
        if (typeof field === "string") return field;
        if (!field || typeof field !== "object") return null;
        return firstValue(field.name, field.field, field.id) || null;
      })
      .filter(Boolean);
  }
  if (value && typeof value === "object") return Object.keys(value);
  return [];
}

function numberValue(...values) {
  const value = Number(firstValue(...values));
  return Number.isFinite(value) && value >= 0 ? value : null;
}

export function normalizeConnectorContract(candidate = {}) {
  const connector = candidate?.connector && typeof candidate.connector === "object" ? candidate.connector : {};
  const state = accessState(candidate, connector);
  const mode = syncMode(candidate, connector);
  const schema = schemaFields(
    firstValue(connector?.schema?.fields, connector?.schema, candidate?.schema?.fields, candidate?.fields),
  );
  const credentialRequired =
    state === "credential_required" || truthy(firstValue(connector?.credential_required, candidate?.credential_required));
  const retryable = truthy(firstValue(connector?.retryable, candidate?.retryable)) || state === "rate_limited";
  const sourceId = firstValue(
    candidate?.source_id,
    connector?.source_id,
    connector?.id,
    candidate?.connector_id,
    candidate?.desk_connector_id,
  );

  return {
    identity: {
      connector_id: firstValue(candidate?.connector_id, candidate?.desk_connector_id, connector?.id) || null,
      source_id: sourceId || null,
      name: firstValue(connector?.name, candidate?.source_name, candidate?.provider, candidate?.source) || null,
      endpoint: firstValue(connector?.endpoint, connector?.url, candidate?.endpoint, candidate?.url) || null,
    },
    access: {
      state,
      credential_required: credentialRequired,
      credential_profile: firstValue(connector?.credential_profile, candidate?.credential_profile) || null,
      license: firstValue(connector?.license, candidate?.license, candidate?.access_license) || null,
      terms_url: firstValue(connector?.terms_url, candidate?.terms_url) || null,
    },
    sync: {
      mode,
      cursor_field: firstValue(connector?.cursor_field, candidate?.cursor_field) || null,
      state_token: firstValue(connector?.state_token, connector?.cursor, candidate?.state_token) || null,
      refresh_policy: firstValue(connector?.refresh_policy, candidate?.refresh_policy) || null,
      last_synced_at: firstValue(connector?.last_synced_at, candidate?.last_synced_at) || null,
    },
    schema: {
      discovered: schema.length > 0 || truthy(firstValue(connector?.schema_discovered, candidate?.schema_discovered)),
      fields: schema,
      primary_key: toArray(firstValue(connector?.primary_key, candidate?.primary_key)).filter(Boolean),
    },
    limits: {
      rate_limit: firstValue(connector?.rate_limit, candidate?.rate_limit) || null,
      quota_remaining: numberValue(connector?.quota_remaining, candidate?.quota_remaining),
      estimated_bytes: numberValue(connector?.estimated_bytes, candidate?.estimated_bytes, candidate?.size_bytes),
      max_retries: numberValue(connector?.max_retries, candidate?.max_retries),
    },
    execution: {
      probe_required: truthy(firstValue(connector?.probe_required, candidate?.probe_required)) || state === "unknown",
      retryable,
      supported: state !== "unavailable",
    },
  };
}

export function connectorContext(candidate = {}) {
  const contract = normalizeConnectorContract(candidate);
  return {
    connector_id: contract.identity.connector_id || undefined,
    source_id: contract.identity.source_id || undefined,
    source_name: contract.identity.name || undefined,
    endpoint: contract.identity.endpoint || undefined,
    access_state: contract.access.state,
    credential_required: contract.access.credential_required || undefined,
    credential_profile: contract.access.credential_profile || undefined,
    license: contract.access.license || undefined,
    sync_mode: contract.sync.mode,
    cursor_field: contract.sync.cursor_field || undefined,
    state_token: contract.sync.state_token || undefined,
    refresh_policy: contract.sync.refresh_policy || undefined,
    schema_discovered: contract.schema.discovered,
    schema_fields: contract.schema.fields.length ? contract.schema.fields : undefined,
    primary_key: contract.schema.primary_key.length ? contract.schema.primary_key : undefined,
    rate_limit: contract.limits.rate_limit || undefined,
    quota_remaining: contract.limits.quota_remaining ?? undefined,
    estimated_bytes: contract.limits.estimated_bytes ?? undefined,
    probe_required: contract.execution.probe_required || undefined,
    retryable: contract.execution.retryable || undefined,
    supported: contract.execution.supported,
  };
}
