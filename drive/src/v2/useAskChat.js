import { useCallback, useEffect, useRef, useState } from "react";
import {
  deskWarm,
  getChatSession,
  linkSynthesisThreadConversation,
  sendChatMessage,
} from "@/v2/api";
import { normalizeActivityStep } from "@/v2/deskIntegration";
import { clearChatSessionId, loadChatSessionId, loadUserEmail, saveChatSessionId } from "@/v2/deskSession";
import { workspaceAskBindKey } from "./askWorkspaceBind.js";

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

function restoredDisplayText(row) {
  let value = String(row?.content || row?.text || "");
  if (row?.role !== "user") return value;

  // Stored prompts retain the machine context that grounded the provider turn.
  // The researcher already sees that context in the selected rail/canvas, so
  // replay only the message they actually authored.
  value = value.replace(/^\[context:[^\n]*?\]\s*/i, "");
  value = value.split(/\n\nSynthesis thread:/i)[0];
  value = value.split(/\n\nSynthesis workspace context\./i)[0];
  return value.trim();
}

function restoreMessage(row) {
  const artifacts = row?.artifacts && typeof row.artifacts === "object" ? row.artifacts : {};
  return {
    role: row?.role === "assistant" ? "assistant" : row?.role === "error" ? "error" : "user",
    text: restoredDisplayText(row),
    action: artifacts.action,
    toolName: artifacts.tool_name,
    candidates: Array.isArray(artifacts.candidates) ? artifacts.candidates : [],
    suggestedPrompts: Array.isArray(artifacts.suggestions) ? artifacts.suggestions : [],
    nextSteps: Array.isArray(artifacts.next_steps) ? artifacts.next_steps : [],
    pendingJobId: artifacts.job_id || artifacts.pending_job_id || null,
    jobStatus: artifacts.job_status || artifacts.job?.status,
    composerPending: Boolean(
      artifacts.still_working || artifacts.background_watch || artifacts.action === "composer_pending",
    ),
    backgroundWatch: Boolean(artifacts.background_watch || artifacts.background_completion),
    backgroundCompletion: Boolean(artifacts.background_completion),
  };
}

/** Bind Ask to the open desk surface so Discover/Library/Synthesis do not share a detached thread. */
export { workspaceAskBindKey };

export function useAskChat({ dataset, railContext, onCollected, onSynthesisChanged, onToast } = {}) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const generalSessionRef = useRef(loadChatSessionId());
  const sessionRef = useRef(generalSessionRef.current);
  const previousContextKindRef = useRef(dataset?.kind || "");
  const previousBindKeyRef = useRef("");
  const sessionsByBindRef = useRef(new Map());
  const bindKeyRef = useRef("");
  const warmStartedRef = useRef(false);
  const railRef = useRef(railContext);
  const busyRef = useRef(false);
  const synthesisThreadId =
    dataset?.kind === "synthesis_thread" ? String(dataset.thread_id || "") : "";
  const synthesisSessionId =
    dataset?.kind === "synthesis_thread" ? String(dataset.session_id || "") : "";
  const bindKey = workspaceAskBindKey(railContext, dataset);

  useEffect(() => {
    railRef.current = railContext;
  }, [railContext]);

  useEffect(() => {
    bindKeyRef.current = bindKey;
  }, [bindKey]);

  useEffect(() => {
    if (warmStartedRef.current) return;
    warmStartedRef.current = true;
    deskWarm({
      sessionId: sessionRef.current,
      userEmail: loadUserEmail(),
      background: true,
    }).catch(() => {});
  }, []);

  // Re-warm when Ask rebinds to a new surface/session so first message isn't cold.
  const warmedBindsRef = useRef(new Set());
  useEffect(() => {
    if (!bindKey || warmedBindsRef.current.has(bindKey)) return;
    warmedBindsRef.current.add(bindKey);
    deskWarm({
      sessionId: sessionRef.current || undefined,
      userEmail: loadUserEmail(),
      background: true,
    }).catch(() => {});
  }, [bindKey]);

  useEffect(() => {
    const contextKind = dataset?.kind || "";
    const leavingSynthesis =
      previousContextKindRef.current === "synthesis_thread" && contextKind !== "synthesis_thread";
    const prevBind = previousBindKeyRef.current;
    const isFirst = !prevBind;
    const bindChanged = Boolean(prevBind && prevBind !== bindKey);

    if (prevBind && bindChanged && !busyRef.current) {
      sessionsByBindRef.current.set(prevBind, sessionRef.current || "");
    }
    previousBindKeyRef.current = bindKey;
    previousContextKindRef.current = contextKind;

    // Synthesis threads keep their durable conversation.
    if (contextKind === "synthesis_thread" || leavingSynthesis) {
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
    }

    if (isFirst) {
      // Never paint a prior surface's general session onto Discover/Library/Synthesis.
      // Only restore when this exact workspace bind already has a remembered session.
      const remembered = sessionsByBindRef.current.get(bindKey) || "";
      if (!remembered) {
        sessionRef.current = "";
        return undefined;
      }
      let cancelled = false;
      sessionRef.current = remembered;
      getChatSession(remembered)
        .then((session) => {
          if (cancelled) return;
          if (bindKeyRef.current !== bindKey) return;
          const rows = Array.isArray(session?.messages) ? session.messages : [];
          setMessages(rows.map(restoreMessage));
        })
        .catch(() => {
          if (!cancelled) setMessages([]);
        });
      return () => {
        cancelled = true;
      };
    }

    if (!bindChanged) return undefined;

    // Open surface / Explore / dataset changed — Ask rebinds to that work.
    setMessages([]);
    setInput("");
    setStatus("");
    const remembered = sessionsByBindRef.current.get(bindKey) || "";
    if (!remembered) {
      sessionRef.current = "";
      return undefined;
    }
    let cancelled = false;
    sessionRef.current = remembered;
    getChatSession(remembered)
      .then((session) => {
        if (cancelled) return;
        if (bindKeyRef.current !== bindKey) return;
        const rows = Array.isArray(session?.messages) ? session.messages : [];
        setMessages(rows.map(restoreMessage));
      })
      .catch(() => {
        if (!cancelled) {
          sessionRef.current = "";
          setMessages([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [dataset?.kind, synthesisThreadId, synthesisSessionId, bindKey]);

  // When SLA returns early, Composer may still finish — poll the session for background_completion.
  useEffect(() => {
    const pending = messages.some(
      (m) => m.composerPending || m.backgroundWatch || m.action === "composer_pending",
    );
    const sid = sessionRef.current;
    if (!pending || busy || !sid) return undefined;

    let cancelled = false;
    const poll = async () => {
      try {
        const session = await getChatSession(sid);
        if (cancelled || !session) return;
        const state = session.state || {};
        const rows = Array.isArray(session.messages) ? session.messages : [];
        const mapped = rows.map(restoreMessage);
        const finishedBg = mapped.some((m) => m.backgroundCompletion);
        const stillPending = Boolean(state.composer_pending) || mapped.some((m) => m.composerPending);
        if (finishedBg || !stillPending) {
          setMessages(mapped);
          setStatus("");
          if (finishedBg) onToast?.("Composer finished — response updated");
        }
      } catch {
        /* ignore transient poll errors */
      }
    };

    poll();
    const handle = window.setInterval(poll, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [busy, messages, onToast]);

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
      const full =
        contextPrefix && !prompt.startsWith("[context:")
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
                item.streaming ? { ...item, text: `${item.text || ""}${chunk}` } : item,
              ),
            );
          },
          onActivity: (event) => {
            const line =
              event && typeof event === "object" ? String(event.text || "") : String(event || "");
            setStatus(line);
            setMessages((m) =>
              m.map((item) => {
                if (!item.streaming) return item;
                const next = {
                  ...item,
                  activity: line,
                  activityLog: normalizeActivityStep(event, item.activityLog || []),
                };
                if (event && typeof event === "object" && event.mutation) {
                  if (event.job_id || event.pending_job_id) {
                    next.pendingJobId = event.job_id || event.pending_job_id;
                    next.jobStatus = event.job_status || "pending_approval";
                  }
                  if (event.synthesis_proposal) {
                    next.synthesisProposal = event.synthesis_proposal;
                    next.synthesisThreadId =
                      event.synthesis_thread_id || synthesisThreadId || undefined;
                  }
                }
                return next;
              }),
            );
          },
          onDeskFacts: (facts) => {
            if (!facts || typeof facts !== "object") return;
            setStatus("Library measure ready");
            setMessages((m) =>
              m.map((item) => (item.streaming ? { ...item, deskFacts: facts } : item)),
            );
          },
        });

        if (out.session_id) {
          sessionRef.current = out.session_id;
          sessionsByBindRef.current.set(bindKeyRef.current, out.session_id);
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
        const deskFacts =
          (out.desk_facts && typeof out.desk_facts === "object" ? out.desk_facts : null) ||
          (artifacts.desk_facts && typeof artifacts.desk_facts === "object"
            ? artifacts.desk_facts
            : null);
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
        // Timeouts that are still watching in the background keep the session so the rail can poll.
        const backgroundWatch = Boolean(
          artifacts.background_watch || artifacts.still_working || out.action === "composer_pending",
        );
        const composerBroken =
          !backgroundWatch &&
          (out.action === "composer_error" ||
            artifacts.action === "composer_error" ||
            Boolean(artifacts.retryable) ||
            /could not complete that turn|composer session expired|internal:\s*internal error/i.test(
              String(reply || ""),
            ));
        // Drop poisoned Composer resume targets so the next send is fresh.
        if (composerBroken) {
          sessionRef.current = "";
          if (!synthesisThreadId) {
            generalSessionRef.current = "";
            clearChatSessionId();
          }
        }
        const pendingJobId =
          artifacts.job?.id ||
          artifacts.job_id ||
          statePatch.pending_job_id ||
          out.pending_job_id ||
          out.job_id ||
          null;
        const jobStatus = artifacts.job?.status || statePatch.job_status || out.job_status;
        const toolName = artifacts.tool_name || out.tool_name || null;
        let nextSteps = Array.isArray(out.next_steps)
          ? out.next_steps
          : Array.isArray(artifacts.next_steps)
            ? artifacts.next_steps
            : [];
        if (
          composerBroken &&
          !pendingJobId &&
          !recordedProposal &&
          prompt &&
          !nextSteps.some((step) => /try again/i.test(String(step?.label || step?.prompt || step || "")))
        ) {
          nextSteps = [
            {
              label: "Try again with a fresh Composer session",
              prompt,
            },
            ...nextSteps,
          ];
        }
        const shaped = {
          action: out.action,
          toolName,
          candidates: out.candidates || artifacts.candidates || [],
          suggestedPrompts: out.suggested_prompts || artifacts.suggestions || [],
          nextSteps,
          pendingJobId,
          jobStatus,
        };

        setMessages((m) => {
          const priorFacts = m.find((x) => x.streaming)?.deskFacts;
          const trimmed = m.filter((x) => !x.streaming);
          return [
            ...trimmed,
            {
              role: "assistant",
              text: reply,
              deskFacts: deskFacts || priorFacts || undefined,
              action: shaped.action || out.action,
              toolName: shaped.toolName,
              // Completed turns should not keep "Planning…" chrome in the card.
              activityLog: [],
              candidates: shaped.candidates || [],
              suggestedPrompts: shaped.suggestedPrompts || [],
              nextSteps: shaped.nextSteps || nextSteps || [],
              pendingJobId: shaped.pendingJobId,
              jobStatus: shaped.jobStatus,
              composerPending: backgroundWatch,
              backgroundWatch,
              synthesisProposal: recordedProposal || undefined,
              synthesisThreadId:
                artifacts.synthesis_thread_id || synthesisThreadId || undefined,
            },
          ];
        });
        setStatus(
          backgroundWatch
              ? "Composer still finishing in the background…"
            : out.campaign_id
              ? `Campaign ${String(out.campaign_id).slice(0, 8)}…`
              : "",
        );
        // Toast / refresh only when tools actually mutated — never from prose-inferred action labels.
        const subId =
          artifacts.subscription_id ||
          artifacts.subscription?.id ||
          out.subscription_id ||
          null;
        const artifactMutation = Boolean(
          pendingJobId || subId || artifacts.platform_registered || recordedProposal,
        );
        if (artifactMutation) {
          onCollected?.();
          if (subId || out.action === "schedule_refresh" || artifacts.platform_registered) {
            onToast?.("Refresh registered in Discover History");
          } else if (pendingJobId && jobStatus === "pending_approval") {
            onToast?.("Job pending approval — use Approve below");
          } else if (pendingJobId) {
            onToast?.("Queued for collection");
          }
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
