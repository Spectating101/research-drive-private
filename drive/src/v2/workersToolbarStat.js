/**
 * Compact Collectors toolbar label from explicit worker pool fields only.
 * Never invents schedulable capacity from joined/stale membership.
 */

function hasExplicit(value) {
  return value != null && value !== "";
}

function withTotal(phrase, total) {
  if (!hasExplicit(total)) return phrase;
  return `${phrase} / ${total}`;
}

function aggregatePoolCounts(pools) {
  if (!pools || typeof pools !== "object") return {};
  if (
    "stale" in pools ||
    "online" in pools ||
    "busy" in pools ||
    "joined" in pools ||
    "fresh" in pools ||
    "available" in pools
  ) {
    return pools;
  }
  let total = 0;
  let online = 0;
  let stale = 0;
  let busy = 0;
  let sawOnline = false;
  let sawStale = false;
  let sawBusy = false;
  let sawTotal = false;
  for (const entry of Object.values(pools)) {
    if (!entry || typeof entry !== "object") continue;
    if (entry.total != null) {
      total += Number(entry.total) || 0;
      sawTotal = true;
    }
    if (entry.online != null) {
      online += Number(entry.online) || 0;
      sawOnline = true;
    }
    if (entry.stale != null) {
      stale += Number(entry.stale) || 0;
      sawStale = true;
    }
    if (entry.busy != null) {
      busy += Number(entry.busy) || 0;
      sawBusy = true;
    }
  }
  return {
    ...(sawTotal ? { total } : {}),
    ...(sawOnline ? { online } : {}),
    ...(sawStale ? { stale } : {}),
    ...(sawBusy ? { busy } : {}),
  };
}

/**
 * Pick only fields the resources rollup already supplies (hero + compute/runtime).
 * Does not invent an "available" / schedulable count.
 */
export function workersToolbarFieldsFromRollup(rollup) {
  const hero = rollup?.hero?.workers || {};
  const wl = rollup?.compute?.windows_lab || {};
  const deskPools = aggregatePoolCounts(
    rollup?.compute?.runtime?.worker_pools || rollup?.runtime?.desk?.worker_pools || {},
  );

  const fields = {};
  const busy = hero.busy ?? deskPools.busy ?? wl.busy;
  const total = hero.total ?? deskPools.total ?? wl.total;
  if (hasExplicit(busy)) fields.busy = busy;
  if (hasExplicit(total)) fields.total = total;
  if (hasExplicit(hero.joined) || hasExplicit(wl.joined)) fields.joined = hero.joined ?? wl.joined;
  if (hasExplicit(hero.online) || hasExplicit(deskPools.online)) {
    fields.online = hero.online ?? deskPools.online;
  }
  // Runtime desk pools are the freshness source when both report stale.
  if (hasExplicit(deskPools.stale) || hasExplicit(hero.stale)) {
    fields.stale = deskPools.stale ?? hero.stale;
  }
  if (hasExplicit(hero.fresh)) fields.fresh = hero.fresh;
  if (hasExplicit(hero.idle) || hasExplicit(wl.idle)) fields.idle = hero.idle ?? wl.idle;
  // Never promote "available" when stale membership is already reported.
  if (hasExplicit(hero.available) && !hasExplicit(fields.stale)) {
    fields.available = hero.available;
  }
  return fields;
}

/**
 * Canonical collector-state vocabulary (VC-4).
 *
 * The Resources toolbar, capability card, and rail must describe collectors
 * with the same nouns and the same denominator. Previously each site ran its
 * own `available ?? online ?? joined ?? busy ?? total` fallback chain, so one
 * screen could show three different numbers for the same pool.
 *
 * Only dimensions the backend actually reported are rendered — nothing is
 * inferred, summed, or back-filled. With no reported dimension the caller gets
 * an explicit "Not reported".
 */
export function formatCollectorState(workers) {
  if (!workers || typeof workers !== "object") return "Not reported";
  const parts = [];
  const add = (value, noun) => {
    if (hasExplicit(value)) parts.push(`${value} ${noun}`);
  };
  add(workers.total, "registered");
  // "Connected" is live presence when reported, otherwise declared membership.
  add(hasExplicit(workers.online) ? workers.online : workers.joined, "connected");
  add(workers.idle, "idle");
  add(workers.busy, "running");
  add(workers.stale, "stale");
  return parts.length ? parts.join(" · ") : "Not reported";
}

/**
 * @param {Record<string, unknown>|null|undefined} workers
 * @returns {string|null}
 */
export function formatWorkersToolbarStat(workers) {
  if (!workers || typeof workers !== "object") return null;

  const online = workers.online;
  const joined = workers.joined;
  const stale = workers.stale;
  const fresh = workers.fresh;
  const available = workers.available;
  const busy = workers.busy;
  const total = workers.total;

  const mixedMembership = hasExplicit(stale) && (hasExplicit(joined) || hasExplicit(fresh));
  if (mixedMembership) {
    const head = hasExplicit(joined) ? `${joined} joined` : `${fresh} fresh`;
    return withTotal(`${head} · ${stale} stale`, total);
  }

  // Only claim "available" when the backend supplies that trusted field.
  if (hasExplicit(available)) {
    return hasExplicit(total) && available !== total
      ? `${available}/${total} available`
      : `${available} available`;
  }

  if (hasExplicit(online) && !hasExplicit(stale)) {
    return hasExplicit(total) && online !== total
      ? `${online}/${total} online`
      : `${online} online`;
  }

  if (hasExplicit(joined) && !hasExplicit(stale)) {
    return hasExplicit(total) && joined !== total
      ? `${joined}/${total} joined`
      : `${joined} joined`;
  }

  if (hasExplicit(busy) && !hasExplicit(stale)) {
    return hasExplicit(total) && busy !== total ? `${busy}/${total} busy` : `${busy} busy`;
  }

  if (hasExplicit(stale)) {
    return withTotal(`${stale} stale`, total);
  }

  if (hasExplicit(total)) return `${total} configured`;
  return null;
}
