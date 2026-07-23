/**
 * Capacity & access meter marks — bundled local assets (no remote CDNs).
 */

import bigqueryMark from "@/v2/assets/providers/bigquery.svg";
import clusterJobsMark from "@/v2/assets/providers/cluster-jobs.svg";
import cursorMark from "@/v2/assets/providers/cursor.png";
import googleDriveMark from "@/v2/assets/providers/google-drive.png";
import queryEngineMark from "@/v2/assets/providers/query-engine.svg";
import transcendCacheMark from "@/v2/assets/providers/transcend-cache.svg";

/** @typedef {{ id: string, src: string, alt: string, title: string }} CapacityMark */

/** @type {Record<string, CapacityMark>} */
const MARKS = {
  vault: {
    id: "vault",
    src: googleDriveMark,
    alt: "Google Drive",
    title: "Google Drive vault",
  },
  cache: {
    id: "cache",
    src: transcendCacheMark,
    alt: "Bulk cache",
    title: "Transcend bulk cache",
  },
  cursor: {
    id: "cursor",
    src: cursorMark,
    alt: "Cursor",
    title: "Cursor Ask",
  },
  bigquery: {
    id: "bigquery",
    src: bigqueryMark,
    alt: "BigQuery",
    title: "Google BigQuery",
  },
  mcp: {
    id: "mcp",
    src: queryEngineMark,
    alt: "Ask tools",
    title: "Ask MCP toolkit",
  },
  fleet: {
    id: "fleet",
    src: clusterJobsMark,
    alt: "Lab fleet",
    title: "Lab collector fleet",
  },
};

export function resolveCapacityMark(meterId = "") {
  return MARKS[meterId] || null;
}
