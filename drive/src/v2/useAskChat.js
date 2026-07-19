import { useCallback, useEffect, useRef, useState } from "react";
import { deskWarm, sendChatMessage } from "@/v2/api";
import { normalizeActivityStep } from "@/v2/deskIntegration";
import { loadChatSessionId, loadUserEmail } from "@/v2/deskSession";

function normalizeOutgoingMessage(value, fallback = "") {
  const raw = value ?? fallback;
  if (raw && typeof raw === "object") {
    const prompt = String(raw.prompt || raw.text || "").trim();
    const displayText = String(raw.displayText || raw.label || prompt).trim();
    return { prompt, displayText };
  }
  const prompt = String(raw || "").trim();
  return { prompt, displayText: prompt };
}

export function useAskChat({ dataset, railContext, onCollected, onToast } = {}) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const sessionRef = useRef(loadChatSessionId());
  const warmStartedRef = useRef(false);
  const railRef = useRef(railContext);

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

  const contextPrefix = dataset?.dataset_id
    ? `[context: ${dataset.dataset_id}] `
    : dataset?.title
      ? `[context: ${dataset.title}] `
      : "";

  const send = useCallback(
    async (text) => {
      const outgoing = normalizeOutgoingMessage(text, input);
      const prompt = outgoing.prompt;
      if (!prompt || busy) return;
      const full = contextPrefix && !prompt.startsWith("[context:")
        ? `${contextPrefix}${prompt}`
        : prompt;

      setMessages((m) => [...m, { role: "user", text: outgoing.displayText }]);
      setInput("");
      setBusy(true);
      setStatus("Planning response…");
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: "",
          streaming: true,
          activity: "Planning response…",
          activityLog: [{ phase: "planning", text: "Planning response…", at: Date.now() }],
        },
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
                  ? { ...item, text: `${item.text || ""}${chunk}` }
                  : item,
              ),
            );
          },
          onActivity: (event) => {
            const line =
              event && typeof event === "object" ? String(event.text || "") : String(event || "");
            setStatus(line);
            setMessages((m) =>
              m.map((item) =>
                item.streaming
                  ? {
                      ...item,
                      activity: line,
                      activityLog: normalizeActivityStep(event, item.activityLog || []),
                    }
                  : item,
              ),
            );
          },
        });

        if (out.session_id) sessionRef.current = out.session_id;
        const reply = out.reply || out.message || "Done.";
        const artifacts = out.artifacts || {};
        const statePatch = artifacts.state_patch || out.state_patch || {};
        const pendingJobId =
          artifacts.job?.id || statePatch.pending_job_id || out.pending_job_id || null;
        const jobStatus = artifacts.job?.status || statePatch.job_status;
        const toolName = artifacts.tool_name || out.tool_name || null;

        setMessages((m) => {
          const streaming = m.find((x) => x.streaming);
          const activityLog = streaming?.activityLog || [];
          const trimmed = m.filter((x) => !x.streaming);
          return [
            ...trimmed,
            {
              role: "assistant",
              text: reply,
              action: out.action,
              toolName,
              activityLog,
              candidates: out.candidates || artifacts.candidates || [],
              suggestedPrompts: out.suggested_prompts || artifacts.suggestions || [],
              pendingJobId,
              jobStatus,
            },
          ];
        });
        setStatus(out.campaign_id ? `Campaign ${String(out.campaign_id).slice(0, 8)}…` : "");
        if (["collect", "acquire", "collect_doi", "approve_collect", "queue", "schedule_refresh"].includes(out.action)) {
          onCollected?.();
          onToast?.(
            out.action === "schedule_refresh"
              ? "Refresh registered in Discover History"
              : "Queued for collection",
          );
        }
        const subId =
          artifacts.subscription_id ||
          artifacts.subscription?.id ||
          out.subscription_id ||
          null;
        if (subId || out.action === "schedule_refresh") {
          onCollected?.();
          if (out.action !== "schedule_refresh") {
            onToast?.("Refresh registered in Discover History");
          }
        }
        if (pendingJobId && jobStatus === "pending_approval") {
          onToast?.("Job pending approval — use Approve below");
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
    contextLabel:
      dataset?.kind === "external_candidate"
        ? dataset.title || dataset.row?.dataset_id || dataset.id || null
        : dataset?.dataset_id || dataset?.title || null,
  };
}
