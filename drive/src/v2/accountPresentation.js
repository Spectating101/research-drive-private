import { isProfileBound } from "./profilePresentation.js";

/** Derive compact initials from a bound faculty name; fall back to lab mark. */
export function accountInitials(profile, fallback = "YZ") {
  const name = String(profile?.name_en || profile?.name || "").trim();
  if (!name) return fallback;
  const parts = name.replace(/,/g, " ").split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] || ""}${parts[parts.length - 1][0] || ""}`.toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

export function accountDisplayName(profile) {
  if (isProfileBound(profile)) {
    return profile.name_en || profile.name || "Research context";
  }
  return "Research context";
}
