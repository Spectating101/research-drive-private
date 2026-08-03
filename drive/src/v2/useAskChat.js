import { useCallback, useEffect, useRef, useState } from "react";
import {
  deskWarm,
  getChatSession,
  linkSynthesisThreadConversation,
  sendChatMessage,
} from "@/v2/api";
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

function restoreMessage(row) {
  const artifacts = row?.artifacts && typeof row.artifacts === "object" ? row.artifacts : {};
  return {
    role: row?.role === "assistant" ? "assistant" : row?.role === "error" ? "error" : "user",
    text: String(row?.content || row?.text || ""),
    action: artifacts.action,
    toolName: artifacts.tool_name,
    candidates: Array.isArray(artifacts.candidates) ? artifacts.candidates : [],
    suggestedPrompts: Array.isArray(artifacts.suggestions) ? artifacts.suggestions : [],
    nextSteps: Array.isArray(artifacts.next_steps) ? artifacts.next_steps : [],
    pendingJobId: artifacts.job_id || artifacts.pending_job_id || null,
    jobStatus: artifacts.job_status || artifacts.job?.status,
  };
}

export function useAskChat({ dataset, railContext, onCollected, onSynthesisChanged, onToast } = {}) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const generalSessionRef = useRef(loadChatSessionId());
  const sessionRef = useRef(generalSessionRef.current);
  const previousContextKindRef = useRef(dataset?.kind || "");
  const warmStartedRef = useRef(false);
  const railRef = useRef(railContext);
  const busyRef = useRef(false);
  const intentRef = useRef("general");
  const synthesisThreadId =
    dataset?.kind === "synthesis_thread" ? String(dataset.thread_id || "") : "";
  const synthesisSessionId =
    dataset?.kind === "synthesis_thread" ? String(dataset.session_id || "") : "";

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
    const contextKind = dataset?.kind || "";
    const leavingSynthesis =
      previousContextKindRef.current === "synthesis_thread" && contextKind !== "synthesis_thread";
    previousContextKindRef.current = contextKind;
    if (contextKind !== "synthesis_thread" && !leavingSynthesis) return undefined;

    let cancelled = false;
    setMessages([]);
    setInput("");
    setStatus("");

    const targetSessionId =
      contextKind === "synthesis_thread" ? synthesisSessionId : generalSessionRef.current;
    if (!targetSessionId) {
      sessionRef.current = "";
      return () => {
        cancelled = true;
      };
    }

    sessionRef.current = targetSessionId;
    getChatSession(targetSessionId)
      .then((session) => {
        if (cancelled) return;
        const rows = Array.isArray(session?.messages) ? session.messages : [];
        setMessages(rows.map(restoreMessage));
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [dataset?.kind, synthesisThreadId, synthesisSessionId]);

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
          if (synthesisThreadId) {
            if (out.session_id !== synthesisSessionId) {
              linkSynthesisThreadConversation(synthesisThreadId, {
                sessionId: out.session_id,
              }).catch(() => {});
            }
          } else {
            generalSessionRef.current = out.session_id;
            saveChatSessionId(out.session_id);
          }
        }
        const reply = out.reply || out.message || "Done.";
        const artifacts = out.artifacts || {};
        const recordedProposal =
          artifacts.synthesis_proposal ||
          out.synthesis_proposal ||
          (artifacts.proposal_recorded ? { recorded: true } : null);
        if (synthesisThreadId && recordedProposal) {
          onSynthesisChanged?.({
            threadId: artifacts.synthesis_thread_id || synthesisThreadId,
            proposal: recordedProposal,
          });
        }
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
          if (!synthesisThreadId) {
            generalSessionRef.current = "";
            clearChatSessionId();
          }
        }
        const pendingJobId =
          artifacts.job?.id || statePatch.pending_job_id || out.pending_job_id || null;
        const jobStatus = artifacts.job?.status || statePatch.job_status;
        const toolName = artifacts.tool_name || out.tool_name || null;
        const nextSteps = Array.isArray(out.next_steps)
          ? out.next_steps
          : Array.isArray(artifacts.next_steps)
            ? artifacts.next_steps
            : [];
        const shaped = shapeAskReplyForIntent(intent, {
          action: out.action,
          toolName,
          candidates: out.candidates || artifacts.candidates || [],
          suggestedPrompts: out.suggested_prompts || artifacts.suggestions || [],
          nextSteps,
          pendingJobId,
          jobStatus,
        });

        setMessages((m) => {
          const trimmed = m.filter((x) => !x.streaming);
          return [
            ...trimmed,
            {
              role: "assistant",
              text: reply,
              intent,
              action: shaped.action,
              toolName: shaped.toolName,
              // Completed turns should not keep "Planning…" chrome in the card.
              activityLog: [],
              candidates: shaped.candidates || [],
              suggestedPrompts: shaped.suggestedPrompts || [],
              nextSteps: shaped.nextSteps || nextSteps || [],
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
        const readOnlyReview = /review endpoint does not allow desk mutations|read[- ]only.*review/i.test(msg);
        if (/composer|internal:\s*internal error|could not complete/i.test(msg)) {
          sessionRef.current = "";
          clearChatSessionId();
        }
        setMessages((m) => [
          ...m.filter((x) => !x.streaming),
          {
            role: readOnlyReview ? "notice" : "error",
            text: readOnlyReview
              ? "Ask is unavailable on this read-only review build. The question and visible results remain intact."
              : msg,
          },
        ]);
        setStatus(readOnlyReview ? "Read-only review" : (msg || "Chat failed"));
      } finally {
        busyRef.current = false;
        setBusy(false);
        intentRef.current = "general";
      }
    },
    [
      contextPrefix,
      input,
      onCollected,
      onSynthesisChanged,
      onToast,
      synthesisSessionId,
      synthesisThreadId,
    ],
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
