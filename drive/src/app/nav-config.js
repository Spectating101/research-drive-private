/**
 * Research Drive navigation — professor-facing flat IA (v2).
 * IDs unchanged for routing; labels updated for visual identity.
 */

export const DESK_VIEW = "home";
export const DRIVE_VIEW = "drive";
export const CHAT_VIEW = "chat";

export const PRIMARY_NAV = [
  { id: "home", label: "Home", icon: "home" },
  { id: "drive", label: "Drive", icon: "folder-drive" },
  { id: "recommended", label: "Discover", icon: "spark" },
  { id: "chat", label: "Source", icon: "chat" },
  { id: "dashboard", label: "Pipeline", icon: "pulse", badgeKind: "jobs" },
];

export const LIBRARY_NAV = [
  { id: "recent", label: "Recent", icon: "recent" },
  { id: "starred", label: "Starred", icon: "star" },
  { id: "cluster", label: "Cluster", icon: "cluster" },
];

/** Legacy contract: section titles for e2e until contract updated */
export const NAV_SECTIONS_LEGACY = [
  { label: "Internal", itemIds: ["home", "recent", "starred", "drive", "cluster"] },
  { label: "Procure", itemIds: ["recommended"] },
  { label: "Tools", itemIds: ["chat", "dashboard"] },
];

export function navItemById(id) {
  return [...PRIMARY_NAV, ...LIBRARY_NAV].find((n) => n.id === id);
}
