import { useEffect, useRef } from "react";
import { getJob } from "@/v2/api";
import { isTerminalJobStatus } from "@/v2/askArtifacts";

/** Poll multiple cluster jobs until each reaches a terminal status. */
export function useJobsPoll(jobs, onUpdate, { enabled = true, intervalMs = 4000 } = {}) {
  const statusRef = useRef({});

  useEffect(() => {
    const next = {};
    for (const job of jobs || []) {
      if (job?.id) next[job.id] = job.status;
    }
    statusRef.current = next;
  }, [jobs]);

  useEffect(() => {
    if (!enabled) return undefined;
    const active = (jobs || []).filter((j) => j?.id && !isTerminalJobStatus(j.status));
    if (!active.length) return undefined;

    let cancelled = false;
    const tick = async () => {
      for (const job of active) {
        if (cancelled) return;
        try {
          const row = await getJob(job.id);
          if (!row) continue;
          const next = row.status || row.state;
          if (next && next !== statusRef.current[job.id]) {
            statusRef.current[job.id] = next;
            onUpdate?.(job.id, next, row);
          }
        } catch {
          /* ignore transient poll errors */
        }
      }
    };

    tick();
    const handle = window.setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [enabled, jobs, onUpdate, intervalMs]);
}
