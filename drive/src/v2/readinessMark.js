/**
 * Readiness read from proof, not from a claim string.
 *
 * `analysis_readiness: "instant"` is an unverified assertion — readiness_truth.py
 * only writes query_ready after a bounded query smoke succeeds. The badge follows
 * the same rule: verified when the desk proved it, never from the label alone.
 */

const PROVEN = "verified";

function shortDate(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const m = text.match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : "";
}

export function readinessMark(row) {
  if (String(row?.shelf_hint || "") === "find_datasets") {
    return { label: "Where to find it", tone: "lead" };
  }

  if (row?.query_verified) {
    const at = shortDate(row?.query_verified_at);
    return { label: at ? `Verified ${at}` : "Verified", tone: "ready", state: PROVEN };
  }

  const readiness = String(row?.analysis_readiness || row?.field_coverage || "").toLowerCase();

  if (/metadata[-_ ]?search|metadata only/.test(readiness)) {
    const entitled = String(row?.entitlement_status || "").toLowerCase();
    if (entitled && entitled !== "collected") {
      return { label: "Route ready", tone: "route", state: "route" };
    }
    return { label: "Metadata only", tone: "low", state: "metadata" };
  }

  if (row?.query_ready) return { label: "Query-ready", tone: "ready", state: "claimed" };
  if (/register|instant/.test(readiness)) return { label: "Registered", tone: "mid", state: "registered" };
  if (/metadata/.test(readiness)) return { label: "Metadata only", tone: "low", state: "metadata" };
  return null;
}

export function isHeldRow(row, labIds) {
  if (row?.local_ready || row?.in_lab === true) return true;
  const placement = String(row?.placement || "").toLowerCase();
  if (placement === "held") return true;
  const id = String(row?.dataset_id || row?.id || "").trim();
  return Boolean(id && labIds?.has?.(id));
}
