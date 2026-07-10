import { useEffect, useRef } from "react";
import { getJob } from "@/v2/api";
import { isTerminalJobStatus } from "@/v2/askArtifacts";

/** Poll a cluster job until terminal; invoke onUpdate with fresh status. */
export function useJobPoll(jobId, jobStatus, onUpdate, { enabled = true, intervalMs = 4000 } = {}) {
  const statusRef = useRef(jobStatus);

  useEffect(() => {
    statusRef.current = jobStatus;
  }, [jobStatus]);

  useEffect(() => {
    if (!enabled || !jobId || isTerminalJobStatus(jobStatus)) return undefined;
    let cancelled = false;

    const tick = async () => {
      try {
        const job = await getJob(jobId);
        if (cancelled || !job) return;
        const next = job.status || job.state;
        if (next && next !== statusRef.current) {
          statusRef.current = next;
          onUpdate?.(next, job);
        }
      } catch {
        /* ignore transient poll errors */
      }
    };

    tick();
    const handle = window.setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [enabled, jobId, jobStatus, onUpdate, intervalMs]);
}
