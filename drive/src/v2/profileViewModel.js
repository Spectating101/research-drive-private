/**
 * Organic Profile view-model — derived only from faculty_profile / registry fields.
 * No hardcoded Kong copy; thin profiles simply yield fewer blocks.
 * Pilot email is exported for explicit local tests only — never auto-bound.
 */

/** @deprecated Prefer PROFILE_TEST_EMAIL from profilePresentation — explicit test identity only. */
export const PILOT_PREVIEW_EMAIL = "drkong@saturn.yzu.edu.tw";

const IN_LAB_ROUTES = new Set(["vault", "bigquery"]);

export function humanTag(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bMl\b/g, "ML")
    .replace(/\bNft\b/g, "NFT");
}

export function clipText(value, max = 88) {
  const text = String(value || "").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function trackTitle(track) {
  if (!track) return "";
  if (typeof track === "string") return track;
  return String(track.title || track.name || "").trim();
}

function trackId(track) {
  if (!track || typeof track === "string") return "";
  return String(track.id || track.track_id || "");
}

function formatSpecialtyList(specialties) {
  const parts = (specialties || []).map((s) => String(s).trim()).filter(Boolean);
  if (!parts.length) return "";
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]} and ${parts[1]}`;
  return `${parts.slice(0, -1).join(", ")}, and ${parts[parts.length - 1]}`;
}

function primaryTrack(tracks) {
  const list = (tracks || []).filter((t) => t && (typeof t === "string" || t.title || t.name));
  if (!list.length) return null;
  const active = list.find((t) => typeof t === "object" && String(t.phase || "") === "active_grant");
  if (active) return active;
  return [...list].sort((a, b) => {
    const wa = typeof a === "object" ? Number(a.weight) || 0 : 0;
    const wb = typeof b === "object" ? Number(b.weight) || 0 : 0;
    return wb - wa;
  })[0];
}

function shortTheme(title) {
  const raw = String(title || "").trim();
  if (!raw) return "";
  const head = raw.split("—")[0].split("–")[0].trim();
  return clipText(head || raw, 56);
}

/** Pull a readable title from a citation string when possible. */
export function workTitleFromHighlight(highlight) {
  const text = String(highlight || "").trim();
  if (!text) return "";
  const m = text.match(/\((?:19|20)\d{2}\)[.\s]+(.+)$/);
  if (m) {
    let rest = m[1].trim();
    rest = rest.replace(/\s*SSRN\s+\d+\.?$/i, "").trim();
    rest = rest.replace(/\.\s*[A-Z][A-Za-z &.-]{3,80},?\s*\d+.*$/, "").trim();
    rest = rest.replace(/\.\s*Journal of.*$/i, "").trim();
    rest = rest.replace(/\.\s*Pacific-Basin.*$/i, "").trim();
    rest = rest.replace(/\.\s*Forthcoming\.?$/i, "").trim();
    if (rest.endsWith(".")) rest = rest.slice(0, -1);
    return clipText(rest, 90);
  }
  return clipText(text, 90);
}

function stackKeys(stack) {
  const keys = new Set();
  for (const item of stack || []) {
    if (!item || typeof item !== "object") continue;
    if (item.id) keys.add(String(item.id).toLowerCase());
    if (item.label) keys.add(String(item.label).toLowerCase());
    if (item.partition_id) keys.add(String(item.partition_id).toLowerCase());
    for (const id of item.registry_dataset_ids || []) {
      if (id) keys.add(String(id).toLowerCase());
    }
  }
  return keys;
}

function recLabel(rec) {
  return String(rec?.dataset || rec?.title || rec?.prompt || rec?.search_query || "").trim();
}

function recAlreadyLinked(rec, linked) {
  const candidates = [
    rec?.dataset_id,
    rec?.dataset,
    rec?.partition_id,
    rec?.title,
  ]
    .map((v) => String(v || "").toLowerCase())
    .filter(Boolean);
  return candidates.some((c) => linked.has(c) || [...linked].some((k) => k.includes(c) || c.includes(k)));
}

/**
 * Memory cards from specialties, tracks, methods — omit empty cards.
 */
export function buildMemoryCards(profile) {
  if (!profile || profile.unknown) return [];
  const cards = [];
  const focus = formatSpecialtyList(profile.specialties);
  if (focus) cards.push({ id: "focus", text: focus });

  const tracks = profile.research_tracks || [];
  const primary = primaryTrack(tracks);
  if (primary) {
    const title = trackTitle(primary);
    if (title) cards.push({ id: "current", text: `Current: ${title}` });
  }

  const others = tracks
    .filter((t) => t !== primary && trackId(t) !== trackId(primary))
    .map((t) => shortTheme(trackTitle(t)))
    .filter(Boolean);
  if (others.length) {
    cards.push({ id: "also", text: `Also: ${others.join(" · ")}` });
  }

  const methods = (profile.method_tags || []).map(humanTag).filter(Boolean);
  if (methods.length) {
    const soft = methods.map((m) => m.toLowerCase());
    cards.push({ id: "methods", text: `Methods: ${soft.join(", ")}` });
  }

  return cards;
}

export function buildWorks(profile) {
  const highlights = profile?.publication_highlights || [];
  const paperCount = profile?.paper_count_parsed || profile?.paper_count || null;
  const primary = primaryTrack(profile?.research_tracks || []);
  const relation = shortTheme(trackTitle(primary)) || "Research output";
  const items = highlights
    .map((h) => ({
      raw: h,
      title: workTitleFromHighlight(h),
      type: "Publication",
      relationship: relation,
    }))
    .filter((w) => w.title)
    .slice(0, 6);
  return { paperCount, items };
}

/**
 * Lab: Linked = lab_fintech_stack; Suggested = recs not linked.
 * Link = in-lab route (vault/bq) not on stack; Search = everything else.
 */
export function buildLab(profile) {
  const stack = profile?.lab_fintech_stack || [];
  const linked = stack
    .filter((item) => item && (item.label || item.id))
    .map((item) => {
      const route = String(item.route || "vault").toLowerCase();
      const routeLabel = route === "bigquery" ? "BigQuery" : "Vaulted";
      return {
        id: item.id || item.partition_id || item.label,
        label: item.label || item.id || "Holding",
        route,
        routeLabel,
        datasetIds: item.registry_dataset_ids || [],
        partitionId: item.partition_id || "",
        action: "open",
      };
    });

  const linkedKeys = stackKeys(stack);
  const suggested = [];
  const seen = new Set();

  for (const rec of profile?.procurement_recommendations || []) {
    if (!rec || typeof rec !== "object") continue;
    if (recAlreadyLinked(rec, linkedKeys)) continue;
    const label = recLabel(rec);
    if (!label) continue;
    const key = label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);

    const route = String(rec.source_route || "").toLowerCase();
    const inLab = IN_LAB_ROUTES.has(route);
    suggested.push({
      id: rec.dataset_id || key,
      label: clipText(label, 64),
      reason: inLab ? "in lab, not linked" : "not in lab yet",
      action: inLab ? "link" : "search",
      query: rec.search_query || rec.prompt || label,
      datasetId: rec.dataset_id || "",
      sourceRoute: route,
    });
  }

  // Prefer Link rows before Search rows; cap at 4
  suggested.sort((a, b) => Number(b.action === "link") - Number(a.action === "link"));
  return {
    linked,
    suggested: suggested.slice(0, 4),
  };
}

/** DETAIL rail: Scholar + Strengths + Desk — evidence-gated, no Memory re-list. */
export function buildDeskRead(profile, { previewing = false } = {}) {
  if (!profile || profile.unknown) {
    return { scholar: "", strengths: [], desk: "", previewing };
  }

  const discipline = String(profile.discipline || "").trim() || "Faculty";
  const primary = primaryTrack(profile.research_tracks || []);
  const focus = shortTheme(trackTitle(primary));
  const scholar = focus
    ? `${discipline} faculty · present focus on ${focus.toLowerCase()}.`
    : `${discipline} faculty research program on file.`;

  const strengths = [];
  const stack = profile.lab_fintech_stack || [];
  const hasFintechStack = stack.some((s) => {
    const blob = `${s?.label || ""} ${s?.id || ""}`.toLowerCase();
    return /crypto|nft|opensea|coingecko|skynet|token|fintech|usdt|ethereum/.test(blob);
  });
  if (hasFintechStack) strengths.push("FinTech through-line");

  const hasOnChain =
    stack.some((s) => String(s?.route || "").toLowerCase() === "bigquery")
    || (profile.method_tags || []).some((m) => /on.?chain|machine_learning|panel/i.test(String(m)));
  if (hasOnChain) strengths.push("Market + on-chain panels");

  if (strengths.length < 2 && primary && String(primary.phase || "") === "active_grant") {
    strengths.push("Clear present research direction");
  }
  if (strengths.length < 2 && (profile.paper_count_parsed || 0) >= 10) {
    strengths.push("Established publication record");
  }

  const lab = buildLab(profile);
  const deskParts = [];
  if (lab.linked.length) {
    const fintechLinked = lab.linked.some((r) => /crypto|nft|opensea|coingecko|skynet|token|usdt|ethereum/i.test(r.label));
    deskParts.push(fintechLinked ? "FinTech panels linked." : `${lab.linked.length} holdings linked.`);
  }
  const openBits = [];
  for (const s of lab.suggested) {
    const blob = `${s.label} ${s.query}`.toLowerCase();
    if (/taiwan|twse|mops|momentum|equity/.test(blob)) openBits.push("Taiwan equity");
    if (/governance|trust|misconduct|reputation/.test(blob)) openBits.push("misconduct");
  }
  const uniqOpen = [...new Set(openBits)];
  if (uniqOpen.length) {
    deskParts.push(`${uniqOpen.join(" / ")} open to link.`);
  } else if (lab.suggested.length) {
    deskParts.push(`${lab.suggested.length} suggested next.`);
  } else if (!lab.linked.length) {
    deskParts.push("No lab holdings linked yet.");
  }

  return {
    scholar,
    strengths: strengths.slice(0, 2),
    desk: deskParts.join(" "),
    previewing,
    name: profile.name_en || profile.name || "",
    discipline,
  };
}
