import { useCallback, useEffect, useRef, useState } from "react";
import { deskWarm, fetchChatSession, sendChatMessage } from "@/v2/api";
import { isTerminalJobStatus, mapSessionMessageToUi } from "@/v2/askArtifacts";
import { loadChatSessionId, loadUserEmail } from "@/v2/deskSession";

function resolveJobFields(out) {
  const artifacts = out.artifacts || {};
  const statePatch = artifacts.state_patch || out.state_patch || {};
  const jobObj =
    (out.job && typeof out.job === "object" ? out.job : null) ||
    (artifacts.job && typeof artifacts.job === "object" ? artifacts.job : null) ||
    (artifacts.collect?.job && typeof artifacts.collect.job === "object" ? artifacts.collect.job : null);

  const pendingJobId =
    out.job_id ||
    out.pending_job_id ||
    artifacts.job_id ||
    jobObj?.id ||
    jobObj?.job_id ||
    statePatch.pending_job_id ||
    null;

  let jobStatus =
    out.job_status ||
    statePatch.job_status ||
    jobObj?.status ||
    artifacts.collect?.job?.status ||
    null;

  if (!jobStatus && pendingJobId && (out.action === "submit_collect" || artifacts.background)) {
    jobStatus = "queued";
  }

  return { artifacts, pendingJobId, jobStatus };
}

function sessionHasComposerPending(messages, state) {
  if (state?.composer_pending) return true;
  const last = messages[messages.length - 1];
  return Boolean(last?.composerPending || last?.action === "composer_pending");
}

export function useAskChat({ dataset, railContext, onCollected, onToast } = {}) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const sessionRef = useRef(loadChatSessionId());
  const warmStartedRef = useRef(false);
  const railRef = useRef(railContext);
  const messageCountRef = useRef(0);
  const restoredRef = useRef(false);

  useEffect(() => {
    railRef.current = railContext;
  }, [railContext]);

  useEffect(() => {
    if (warmStartedRef.current) return;
    warmStartedRef.current = true;
    deskWarm({
      sessionId: sessionRef.current,
      userEmail: loadUserEmail(),
      background: true,
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const sid = sessionRef.current;
    if (!sid || restoredRef.current) return;
    restoredRef.current = true;
    fetchChatSession(sid)
      .then((session) => {
        if (!session?.messages?.length) return;
        const state = session.state || {};
        const mapped = session.messages.map((m) => mapSessionMessageToUi(m, state));
        messageCountRef.current = mapped.length;
        setMessages(mapped);
        if (state.composer_pending) {
          onToast?.("Composer still finishing a prior turn…");
        }
      })
      .catch(() => {});
  }, [onToast]);

  useEffect(() => {
    const sid = sessionRef.current;
    if (!sid || busy) return undefined;
    if (!sessionHasComposerPending(messages, null)) return undefined;

    let cancelled = false;
    const poll = async () => {
      try {
        const session = await fetchChatSession(sid);
        if (cancelled || !session) return;
        const state = session.state || {};
        const mapped = (session.messages || []).map((m) => mapSessionMessageToUi(m, state));
        const grew = mapped.length > messageCountRef.current;
        const cleared = !state.composer_pending && sessionHasComposerPending(messages, null);
        if (grew || cleared) {
          messageCountRef.current = mapped.length;
          setMessages(mapped);
          if (grew) {
            onToast?.("Composer finished — response updated");
            onCollected?.();
          }
        }
      } catch {
        /* ignore */
      }
    };

    poll();
    const handle = window.setInterval(poll, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [busy, messages, onCollected, onToast]);

  const patchMessageJob = useCallback(
    (jobId, nextStatus) => {
      if (!jobId) return;
      setMessages((msgs) =>
        msgs.map((m) => (m.pendingJobId === jobId ? { ...m, jobStatus: nextStatus } : m)),
      );
      if (isTerminalJobStatus(nextStatus)) {
        onCollected?.();
        if (nextStatus === "completed") {
          onToast?.("Collection job finished — catalog refreshed");
        }
      }
    },
    [onCollected, onToast],
  );

  const contextPrefix = dataset?.dataset_id
    ? `[context: ${dataset.dataset_id}] `
    : dataset?.title
      ? `[context: ${dataset.title}] `
      : "";

  const send = useCallback(
    async (text) => {
      const prompt = String(text ?? input).trim();
      if (!prompt || busy) return;
      const full = contextPrefix && !prompt.startsWith("[context:")
        ? `${contextPrefix}${prompt}`
        : prompt;

      setMessages((m) => [...m, { role: "user", text: prompt }]);
      setInput("");
      setBusy(true);
      setStatus("Planning response…");
      setMessages((m) => [
        ...m,
        { role: "assistant", text: "", streaming: true, activity: "Planning response…" },
      ]);

      try {
        const out = await sendChatMessage(full, {
          sessionId: sessionRef.current,
          userEmail: loadUserEmail(),
          railContext: railRef.current,
          onDelta: (chunk) => {
            setStatus("");
            setMessages((m) =>
              m.map((item) =>
                item.streaming
                  ? { ...item, text: `${item.text || ""}${chunk}`, activity: "" }
                  : item,
              ),
            );
          },
          onActivity: (line) => {
            setStatus(line);
            setMessages((m) =>
              m.map((item) => (item.streaming ? { ...item, activity: line } : item)),
            );
          },
        });

        if (out.session_id) sessionRef.current = out.session_id;
        const reply = out.reply || out.message || "Done.";
        const { artifacts, pendingJobId, jobStatus } = resolveJobFields(out);
        const composerPending = Boolean(
          artifacts.still_working || out.action === "composer_pending",
        );
        const licenseBlocked = Boolean(artifacts.collect?.blocked || artifacts.blocked);

        setMessages((m) => {
          const trimmed = m.filter((x) => !x.streaming);
          const next = [
            ...trimmed,
            {
              role: "assistant",
              text: reply,
              action: out.action,
              artifacts,
              search: artifacts.search,
              probe: artifacts.probe,
              preview: out.preview || artifacts.preview,
              queryPreview: artifacts.query,
              candidates: out.candidates || artifacts.candidates || [],
              suggestedPrompts: out.suggested_prompts || artifacts.suggestions || [],
              pendingJobId,
              jobStatus,
              composerPending,
              licenseBlocked,
              licenseDoi: artifacts.doi || artifacts.collect?.resolved?.doi || "",
              fastPath: Boolean(artifacts.fast_path),
              procurementSubmit: Boolean(artifacts.procurement_submit || artifacts.background),
            },
          ];
          messageCountRef.current = next.length;
          return next;
        });
        setStatus(out.campaign_id ? `Campaign ${String(out.campaign_id).slice(0, 8)}…` : "");
        if (
          ["collect", "acquire", "collect_doi", "submit_collect", "approve_collect", "queue"].includes(
            out.action,
          )
        ) {
          onCollected?.();
          onToast?.("Queued for cluster collection");
        }
        if (composerPending) {
          onToast?.("Composer still working — this thread will update when ready");
        }
        if (pendingJobId && jobStatus === "pending_approval") {
          onToast?.("Job pending approval — use Approve below");
        }
        if (licenseBlocked) {
          onToast?.("License approval required before collect");
        }
      } catch (err) {
        setMessages((m) => [
          ...m.filter((x) => !x.streaming),
          { role: "error", text: err.message || String(err) },
        ]);
        setStatus(err.message || "Chat failed");
      } finally {
        setBusy(false);
      }
    },
    [busy, contextPrefix, input, onCollected, onToast],
  );

  return {
    messages,
    input,
    setInput,
    busy,
    status,
    send,
    patchMessageJob,
    contextLabel: dataset?.dataset_id || dataset?.title || null,
  };
}
