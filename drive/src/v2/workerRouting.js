/** Additive capability/routing contract for YZU cluster jobs and workers. */

const CAPABILITY_ALIASES = new Map([
  ["puppeteer", "browser"],
  ["playwright", "browser"],
  ["crawlee", "browser"],
  ["cdp", "browser"],
  ["javascript_browser", "browser"],
  ["web_browser", "browser"],
  ["python3", "python"],
  ["powershell", "windows"],
  ["win32", "windows"],
  ["rclone", "archive"],
  ["gdrive", "archive"],
  ["google_drive", "archive"],
  ["download", "http"],
  ["requests", "http"],
  ["curl", "http"],
  ["cuda", "gpu"],
  ["large_disk", "high_disk"],
  ["disk_heavy", "high_disk"],
]);

const JOB_TYPE_REQUIREMENTS = {
  source_probe: ["http"],
  http_manifest: ["http"],
  scraper_run: ["browser"],
  harvest_shard: ["python"],
  archive_upload: ["archive"],
  registered_pipeline: ["pipeline"],
  collection_queue_task: ["python"],
  collection_queue_batch: ["python"],
};

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function toArray(value) {
  if (Array.isArray(value)) return value;
  if (value == null || value === "") return [];
  if (typeof value === "string") return value.split(/[\s,|]+/).filter(Boolean);
  return [value];
}

function capability(value) {
  const raw = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  return CAPABILITY_ALIASES.get(raw) || raw;
}

function capabilities(value) {
  return [...new Set(toArray(value).map(capability).filter(Boolean))];
}

function workerId(worker, fallback = "") {
  if (typeof worker === "string" || typeof worker === "number") return String(worker);
  if (!worker || typeof worker !== "object") return fallback;
  return String(firstValue(worker.id, worker.worker_id, worker.name, worker.label, worker.host, worker.hostname, fallback) || "");
}

function onlineState(worker) {
  if (!worker || typeof worker !== "object") return null;
  if (typeof worker.online === "boolean") return worker.online;
  if (typeof worker.reachable === "boolean") return worker.reachable;
  if (typeof worker.joined === "boolean") return worker.joined;
  const status = String(firstValue(worker.status, worker.state, worker.health) || "").toLowerCase();
  if (/online|ready|idle|busy|running|healthy|joined/.test(status)) return true;
  if (/offline|down|unreachable|disabled|dead/.test(status)) return false;
  return null;
}

export function normalizeJobRequirements(job = {}) {
  const explicit = capabilities(
    firstValue(
      job?.requirements?.capabilities,
      job?.execution?.requirements?.capabilities,
      job?.plan?.requirements?.capabilities,
      job?.required_capabilities,
      job?.capabilities_required,
    ),
  );
  const jobType = String(firstValue(job?.type, job?.job_type, job?.plan?.job_type) || "").trim();
  const defaults = JOB_TYPE_REQUIREMENTS[jobType] || [];
  return {
    capabilities: [...new Set([...explicit, ...defaults])],
    explicit: explicit.length > 0,
    job_type: jobType || null,
  };
}

export function normalizeWorker(worker, pool = null) {
  const object = worker && typeof worker === "object" ? worker : {};
  const capsValue = firstValue(
    object.capabilities,
    object.features,
    object.skills,
    object.executors,
    object.engines,
  );
  return {
    id: workerId(worker),
    pool: firstValue(object.pool, object.worker_pool, pool) || null,
    online: onlineState(object),
    busy: typeof object.busy === "boolean" ? object.busy : null,
    capabilities: capabilities(capsValue),
    capabilities_reported: capsValue !== undefined && capsValue !== null,
  };
}

function assignedWorker(job) {
  const raw = firstValue(job?.assigned_worker, job?.execution?.worker, job?.lifecycle?.worker, job?.worker);
  if (!raw) return null;
  const object = raw && typeof raw === "object" ? { ...raw } : { id: raw };
  const fallbackCaps = firstValue(
    job?.worker_capabilities,
    job?.assigned_capabilities,
    job?.execution?.worker_capabilities,
    job?.lifecycle?.worker_capabilities,
  );
  if (object.capabilities == null && fallbackCaps != null) object.capabilities = fallbackCaps;
  if (object.pool == null) object.pool = firstValue(job?.worker_pool, job?.pool, job?.execution?.pool);
  return normalizeWorker(object);
}

export function evaluateJobRouting(job = {}, workerInventory = []) {
  const requirements = normalizeJobRequirements(job);
  const required = requirements.capabilities;
  const assigned = assignedWorker(job);
  const workers = toArray(workerInventory).map((worker) => normalizeWorker(worker)).filter((worker) => worker.id);

  if (assigned) {
    const missing = assigned.capabilities_reported
      ? required.filter((item) => !assigned.capabilities.includes(item))
      : [];
    if (assigned.online === false) {
      return {
        status: "blocked",
        warn: true,
        required,
        missing,
        assigned_worker: assigned.id,
        assigned_pool: assigned.pool,
        worker_capabilities: assigned.capabilities,
        eligible_workers: [],
        detail: `assigned worker ${assigned.id} is offline`,
      };
    }
    if (missing.length) {
      return {
        status: "blocked",
        warn: true,
        required,
        missing,
        assigned_worker: assigned.id,
        assigned_pool: assigned.pool,
        worker_capabilities: assigned.capabilities,
        eligible_workers: [],
        detail: `worker ${assigned.id} lacks ${missing.join(", ")}`,
      };
    }
    return {
      status: assigned.capabilities_reported || !required.length ? "satisfied" : "assigned_unverified",
      warn: false,
      required,
      missing: [],
      assigned_worker: assigned.id,
      assigned_pool: assigned.pool,
      worker_capabilities: assigned.capabilities,
      eligible_workers: [assigned.id],
      detail: required.length ? `${assigned.id} assigned for ${required.join(", ")}` : `${assigned.id} assigned`,
    };
  }

  if (!required.length) {
    return {
      status: "not_required",
      warn: false,
      required: [],
      missing: [],
      assigned_worker: null,
      assigned_pool: null,
      worker_capabilities: [],
      eligible_workers: [],
      detail: null,
    };
  }

  const reported = workers.filter((worker) => worker.capabilities_reported);
  if (!reported.length) {
    return {
      status: "unknown",
      warn: false,
      required,
      missing: [],
      assigned_worker: null,
      assigned_pool: null,
      worker_capabilities: [],
      eligible_workers: [],
      detail: `routing capability not reported for ${required.join(", ")}`,
    };
  }

  const eligible = reported.filter(
    (worker) => worker.online !== false && required.every((item) => worker.capabilities.includes(item)),
  );
  if (eligible.length) {
    return {
      status: "eligible",
      warn: false,
      required,
      missing: [],
      assigned_worker: null,
      assigned_pool: null,
      worker_capabilities: [],
      eligible_workers: eligible.map((worker) => worker.id),
      detail: `${eligible.length} eligible worker${eligible.length === 1 ? "" : "s"}`,
    };
  }

  return {
    status: "blocked",
    warn: true,
    required,
    missing: required,
    assigned_worker: null,
    assigned_pool: null,
    worker_capabilities: [],
    eligible_workers: [],
    detail: `no online worker reports ${required.join(", ")}`,
  };
}
