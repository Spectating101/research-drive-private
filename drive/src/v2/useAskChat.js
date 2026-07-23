import { useCallback, useEffect, useRef, useState } from "react";
import { deskWarm, sendChatMessage } from "@/v2/api";
import { normalizeActivityStep } from "@/v2/deskIntegration";
import { clearChatSessionId, loadChatSessionId, loadUserEmail, saveChatSessionId } from "@/v2/deskSession";
import { classifyAskIntent, shapeAskReplyForIntent } from "@/v2/askIntent";

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
  const busyRef = useRef(false);
  const intentRef = useRef("general");

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
      if (!prompt || busyRef.current) return;
      busyRef.current = true;
      const intent = classifyAskIntent(outgoing.displayText || prompt);
      intentRef.current = intent;
      const full =
        contextPrefix && !prompt.startsWith("[context:")
          ? `${contextPrefix}${prompt}`
          : prompt;

      setMessages((m) => [...m, { role: "user", text: outgoing.displayText, intent }]);
      setInput("");
      setBusy(true);
      setStatus(intent === "status" ? "Checking status…" : "Planning response…");
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: "",
          streaming: true,
          intent,
          activity: intent === "status" ? "Checking status…" : "Planning response…",
          activityLog:
            intent === "status"
              ? []
              : [{ phase: "planning", text: "Planning response…", at: Date.now() }],
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
                item.streaming ? { ...item, text: `${item.text || ""}${chunk}` } : item,
              ),
            );
          },
          onActivity: (event) => {
            if (intentRef.current === "status") {
              setStatus("Checking status…");
              return;
            }
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

        if (out.session_id) {
          sessionRef.current = out.session_id;
          saveChatSessionId(out.session_id);
        }
        const reply = out.reply || out.message || "Done.";
        const artifacts = out.artifacts || {};
        const statePatch = artifacts.state_patch || out.state_patch || {};
        // Stuck Composer resume targets poison the browser session — start fresh next send.
        const composerBroken =
          out.action === "composer_error" ||
          artifacts.action === "composer_error" ||
          /could not complete that turn|composer session expired|internal:\s*internal error/i.test(
            String(reply || ""),
          );
        if (composerBroken) {
          sessionRef.current = "";
          clearChatSessionId();
        }
        const pendingJobId =
          artifacts.job?.id || statePatch.pending_job_id || out.pending_job_id || null;
        const jobStatus = artifacts.job?.status || statePatch.job_status;
        const toolName = artifacts.tool_name || out.tool_name || null;
        const shaped = shapeAskReplyForIntent(intent, {
          action: out.action,
          toolName,
          candidates: out.candidates || artifacts.candidates || [],
          suggestedPrompts: out.suggested_prompts || artifacts.suggestions || [],
          pendingJobId,
          jobStatus,
        });

        setMessages((m) => {
          const streaming = m.find((x) => x.streaming);
          const activityLog = intent === "status" ? [] : streaming?.activityLog || [];
          const trimmed = m.filter((x) => !x.streaming);
          return [
            ...trimmed,
            {
              role: "assistant",
              text: reply,
              intent,
              action: shaped.action,
              toolName: shaped.toolName,
              activityLog,
              candidates: shaped.candidates || [],
              suggestedPrompts: shaped.suggestedPrompts || [],
              pendingJobId: shaped.pendingJobId,
              jobStatus: shaped.jobStatus,
            },
          ];
        });
        setStatus(
          intent === "status"
            ? ""
            : out.campaign_id
              ? `Campaign ${String(out.campaign_id).slice(0, 8)}…`
              : "",
        );
        if (
          intent !== "status" &&
          ["collect", "acquire", "collect_doi", "approve_collect", "queue", "schedule_refresh"].includes(
            out.action,
          )
        ) {
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
        if (intent !== "status" && (subId || out.action === "schedule_refresh")) {
          onCollected?.();
          if (out.action !== "schedule_refresh") {
            onToast?.("Refresh registered in Discover History");
          }
        }
        if (intent !== "status" && shaped.pendingJobId && shaped.jobStatus === "pending_approval") {
          onToast?.("Job pending approval — use Approve below");
        }
      } catch (err) {
        const msg = err.message || String(err);
        if (/composer|internal:\s*internal error|could not complete/i.test(msg)) {
          sessionRef.current = "";
          clearChatSessionId();
        }
        setMessages((m) => [
          ...m.filter((x) => !x.streaming),
          { role: "error", text: msg },
        ]);
        setStatus(msg || "Chat failed");
      } finally {
        busyRef.current = false;
        setBusy(false);
        intentRef.current = "general";
      }
    },
    [contextPrefix, input, onCollected, onToast],
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
