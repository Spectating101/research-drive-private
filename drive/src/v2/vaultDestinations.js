/** Vault destination options for Discover collection (GDrive layout). */

export const DEFAULT_VAULT_DESTINATION = "collection/";
const RECENT_KEY = "rd_v2_recent_destinations";

export function loadRecentDestinations() {
  try {
    const raw = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((v) => typeof v === "string" && v.trim()) : [];
  } catch {
    return [];
  }
}

export function touchRecentDestination(value) {
  const v = String(value || "").trim();
  if (!v) return loadRecentDestinations();
  const next = [v, ...loadRecentDestinations().filter((item) => item !== v)].slice(0, 4);
  localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  return next;
}

export function buildVaultDestinationOptions(partitions = [], profile = null, recents = loadRecentDestinations()) {
  const out = [];
  const seen = new Set();

  const add = (value, label, hint = "") => {
    const v = String(value || "").trim();
    if (!v || seen.has(v)) return;
    seen.add(v);
    out.push({ value: v, label, hint });
  };

  for (const recent of recents) {
    add(recent, `Recent · ${recent}`, "Used on a prior collection");
  }

  add(DEFAULT_VAULT_DESTINATION, "collection/", "Default GDrive lab share");
  add("Lab root", "Lab root", "Top-level faculty tree");

  for (const part of partitions) {
    const path = part.target_drive_path || part.remote_path || part.path || part.id;
    const title = part.title || part.human_title || part.name || path;
    if (path) add(path, title, part.description || "Partition lane");
  }

  if (profile?.preferred_destination) {
    add(profile.preferred_destination, "Profile default", "From faculty research profile");
  }

  return out;
}

export function destinationHint(options, value) {
  return options.find((o) => o.value === value)?.hint || "";
}
