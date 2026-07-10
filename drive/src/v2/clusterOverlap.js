/** Registry-derived overlap — join keys + grain (not row counts without query). */

function keySet(dataset) {
  const keys = [
    ...(dataset?.join_keys || []),
    ...(dataset?.entity_fields || []),
    dataset?.time_field,
  ].filter(Boolean);
  return new Set(keys.map((k) => String(k).toLowerCase()));
}

export function coverageWidth(dataset) {
  const cov = String(dataset?.coverage || dataset?.date_range || dataset?.temporal_coverage || "");
  const m = cov.match(/(\d{4})/g);
  if (!m || m.length < 1) return 55;
  const start = Number(m[0]);
  const end = Number(m[m.length - 1]);
  const span = Math.min(14, Math.max(1, end - start));
  return Math.round((span / 14) * 100);
}

export function computeDatasetOverlap(a, b) {
  if (!a || !b) return null;
  const keysA = keySet(a);
  const keysB = keySet(b);
  const shared = [...keysA].filter((k) => keysB.has(k));
  const union = new Set([...keysA, ...keysB]);
  const grainA = String(a.grain || "").toLowerCase();
  const grainB = String(b.grain || "").toLowerCase();
  const grainMatch = Boolean(grainA && grainA === grainB);
  const keyPct = union.size ? Math.round((shared.length / union.size) * 100) : 0;
  const pct = grainMatch ? Math.max(keyPct, 35) : Math.min(keyPct, 45);
  const onlyA = [...keysA].filter((k) => !keysB.has(k));
  const onlyB = [...keysB].filter((k) => !keysA.has(k));
  const join = shared.length ? shared.join(" · ") : grainMatch ? a.grain : "partial";

  return {
    pct,
    grainMatch,
    join,
    shared,
    onlyA,
    onlyB,
    rows: null,
    label: `${pct}% key overlap${grainMatch ? " · matching grain" : ""}`,
  };
}

const PIN_KEY = "rd_v2_pinned_compares";

export function loadPinnedCompares() {
  try {
    const raw = JSON.parse(localStorage.getItem(PIN_KEY) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

export function savePinnedCompare(aId, bId, label) {
  const cur = loadPinnedCompares().filter((p) => !(p.a === aId && p.b === bId));
  cur.unshift({ a: aId, b: bId, label: label || `${aId} × ${bId}`, at: Date.now() });
  localStorage.setItem(PIN_KEY, JSON.stringify(cur.slice(0, 8)));
  return cur[0];
}
