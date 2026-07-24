import { Fragment } from "react";

/** Light Ask-rail formatting — bold, inline code, line breaks. No full markdown. */
export function formatAskText(text) {
  const raw = String(text ?? "");
  if (!raw) return null;
  const parts = raw.split(/(\*\*[^*]+\*\*|`[^`]+`|\n)/g).filter((part) => part !== "");
  return parts.map((part, i) => {
    if (part === "\n") return <br key={`br-${i}`} />;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={`b-${i}`}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={`c-${i}`}>{part.slice(1, -1)}</code>;
    }
    return <Fragment key={`t-${i}`}>{part}</Fragment>;
  });
}

function inferReadiness(text) {
  const raw = String(text || "");
  const blocked = /not (yet |fully )?materialized|no usable local files|not on disk|metadata\/search only|catalog\/(metadata|sample)|metadata-ready|more catalog|still need|needs? review|pending approval/i.test(raw);
  if (blocked) return "needs_review";
  if (/\bfail(?:ed|ure)?\b|\berror\b|\bblocked\b/i.test(raw)) return "not_ready";
  if (/query[_ -]?(ready|instant)|instant query|can query it now|ready shelf|ready for (query|analysis)/i.test(raw)) {
    return "query_ready";
  }
  return "";
}

/**
 * Split a desk reply into showcase sections.
 * Typical describe_dataset shape:
 *   **Title** (`id`) — readiness: query_ready
 *   Body paragraph…
 */
export function parseAskReply(text) {
  const raw = String(text ?? "").trim();
  if (!raw) {
    return { title: "", readiness: "", datasetId: "", paragraphs: [], bullets: [] };
  }

  const lines = raw.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  let title = "";
  let readiness = "";
  let datasetId = "";
  const bodyLines = [];

  const head = lines[0] || "";
  const titleMatch = head.match(/^\*\*(.+?)\*\*/);
  const idMatch = head.match(/`([^`]+)`/);
  const readyMatch = head.match(/readiness:\s*([a-z0-9_ -]+)/i);

  if (titleMatch) {
    title = titleMatch[1].trim();
    datasetId = idMatch?.[1]?.trim() || "";
    readiness = readyMatch?.[1]?.trim().replace(/[.,;]+$/, "") || "";
    const remainder = head
      .replace(/^\*\*.+?\*\*/, "")
      .replace(/`[^`]+`/, "")
      .replace(/[—–-]\s*readiness:\s*[a-z0-9_ -]+/i, "")
      .replace(/^\s*[—–-]\s*/, "")
      .trim();
    if (remainder) bodyLines.push(remainder);
    bodyLines.push(...lines.slice(1));
  } else {
    // Soft title from a leading entity phrase ("Taiwan MOPS governance is…").
    const soft = head.match(/^([A-Z][^.]{8,56}?)(?:\s[—–-]\s|\sis\s|\sare\s)/);
    const candidate = soft?.[1]?.replace(/\*+/g, "").trim() || "";
    if (candidate && !/^(For|The|About|If|When|With|After|Before)\b/i.test(candidate)) {
      title = candidate;
    }
    bodyLines.push(...lines);
  }

  const paragraphs = [];
  const bullets = [];
  for (const line of bodyLines) {
    if (/^[-*•]\s+/.test(line)) {
      bullets.push(line.replace(/^[-*•]\s+/, "").trim());
    } else {
      paragraphs.push(line);
    }
  }

  if (!readiness) readiness = inferReadiness(raw);
  return { title, readiness, datasetId, paragraphs, bullets };
}

export function readinessLabel(value) {
  const key = String(value || "").toLowerCase().replace(/\s+/g, "_");
  if (!key) return "";
  if (key.includes("query_ready") || key === "ready" || key === "instant") return "Query ready";
  if (key.includes("review")) return "Needs review";
  if (key.includes("fail") || key.includes("error")) return "Not ready";
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function readinessTone(value) {
  const key = String(value || "").toLowerCase();
  if (key.includes("query_ready") || key === "ready" || key === "instant") return "ready";
  if (key.includes("review") || key.includes("pending")) return "review";
  if (key.includes("fail") || key.includes("error")) return "fail";
  return "neutral";
}

export function humanizeAction(action) {
  const key = String(action || "").toLowerCase();
  if (!key || /describe[_ ]?dataset|planning|working/.test(key)) return "";
  return key.replace(/_/g, " ");
}
