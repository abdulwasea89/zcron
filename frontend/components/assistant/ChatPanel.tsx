"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChatComposer } from "./ChatComposer";
import { ChatThread } from "./ChatThread";
import { ReferencePicker, type Reference } from "./ReferencePicker";
import { Alert, Spinner } from "@/components/ui";
import { api, ApiError, streamPost } from "@/lib/api";
import type {
  AssistantConversationDetailOut,
  AssistantFrame,
  AssistantMessageOut,
  AssistantStep,
} from "@/lib/types";

/* The three frame payloads the tree is built from, read off the protocol rather
   than restated: a field added to a frame reaches these helpers automatically,
   instead of drifting until a row silently loses the field. */
type AgentOpened = Extract<AssistantFrame, { agent_start: unknown }>["agent_start"];
type AgentSettled = Extract<AssistantFrame, { agent_done: unknown }>["agent_done"];
type SwarmStats = Extract<AssistantFrame, { swarm_stats: unknown }>["swarm_stats"];

/* ── ChatPanel ────────────────────────────────────────────────────────────
   One conversation: transcript plus composer, driven entirely by props. It
   never routes — the dock that hosts it decides what is on screen — so the
   same panel serves a blank thread (conversationId null) and an existing one.

   Two ways in, one code path out:
     · `conversationId` set    -> load it and answer a trailing unanswered turn
     · `initialPrompt` handed in -> create the thread, then stream the reply

   Streaming note: the reply arrives over SSE from /api/assistant/stream, not
   through /api/proxy (which buffers). Tokens accumulate in `draft` and become
   a real message the moment the stream ends, so the text never blinks out
   between the last token and the refetch landing. */

interface ChatPanelProps {
  /** The thread on screen, or null for a blank one. */
  conversationId: string | null;
  /** A prompt typed on the dashboard bar, not yet persisted. */
  initialPrompt?: string | null;
  /** Fired once a thread exists, so the host can record its id. */
  onCreated: (id: string) => void;
  /** Ask the host to re-sort its recents list (ordering follows recency). */
  onRailRefresh: () => void;
  /** Fired when the user sends a turn from the composer (not the auto-answer
   *  to a handed-over prompt). The host drops any record handoff here. */
  onUserMessage?: () => void;
}

/** A paused write awaiting the user's yes/no. */
interface Approval {
  id: string | null;
  value: unknown;
}

export function ChatPanel({
  conversationId,
  initialPrompt,
  onCreated,
  onRailRefresh,
  onUserMessage,
}: ChatPanelProps) {
  const [detail, setDetail] = useState<AssistantConversationDetailOut | null>(null);
  const [value, setValue] = useState("");
  const [focusSignal, setFocusSignal] = useState(0);
  const [pendingMessage, setPendingMessage] = useState<AssistantMessageOut | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  /** The in-flight turn's reasoning + tool steps, in arrival order. */
  const [steps, setSteps] = useState<AssistantStep[]>([]);
  /** How long the last completed turn took, for the "Worked for Xs" header. */
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  /** A write the assistant proposed and is waiting for the user to approve. */
  const [approval, setApproval] = useState<Approval | null>(null);
  /** The record-reference picker above the composer. */
  const [refsOpen, setRefsOpen] = useState(false);

  // Lets a switch (or unmount) cancel a reply still arriving.
  const streamRef = useRef<AbortController | null>(null);
  // Which thread the reply in flight belongs to. Needed because a switch
  // *away* from a thread must cancel its stream, while the null -> id moment
  // of a thread being created must not — that transition is the new thread
  // arriving, not the old one leaving.
  const streamConvRef = useRef<string | null>(null);
  // The trailing user turn we have already answered. Effects can run twice
  // (React StrictMode in dev); without this the same question streams twice.
  const answeredRef = useRef("");
  // The last handed-over prompt we acted on, so re-renders don't resend it.
  const promptRef = useRef<string | null>(null);
  // The turn's steps, authoritative across the interrupt/resume boundary where
  // React state would be a stale closure.
  const stepsRef = useRef<AssistantStep[]>([]);

  const loadDetail = useCallback(async (id: string) => {
    const d = await api.get<AssistantConversationDetailOut>(`/assistant/conversations/${id}`);
    setDetail(d);
    return d;
  }, []);

  const runStream = useCallback(
    async (id: string, content?: string, resume?: Record<string, unknown>) => {
      setSending(true);
      setError("");
      setDraft("");
      setApproval(null);
      setElapsedMs(null);
      const startedAt = Date.now();
      // A resumed run continues the same turn, so it keeps the steps it already
      // showed; a fresh turn starts an empty trace.
      if (!resume) {
        stepsRef.current = [];
        setSteps([]);
      }

      const controller = new AbortController();
      streamRef.current = controller;
      streamConvRef.current = id;

      let text = "";
      let streamError: string | null = null;
      let aborted = false;

      try {
        const frames = streamPost<AssistantFrame>(
          resume ? "/api/assistant/resume" : "/api/assistant/stream",
          resume
            ? { conversation_id: id, resume }
            : content === undefined
              ? { conversation_id: id }
              : { conversation_id: id, content },
          { "Idempotency-Key": crypto.randomUUID() },
          controller.signal,
        );
        for await (const frame of frames) {
          if ("delta" in frame) {
            text += frame.delta;
            setDraft(text);
          } else if ("thinking" in frame) {
            pushThinking(stepsRef.current, frame.thinking);
            setSteps([...stepsRef.current]);
          } else if ("tool_start" in frame) {
            stepsRef.current.push({
              type: "tool",
              name: frame.tool_start.name,
              args: frame.tool_start.args,
              done: false,
            });
            setSteps([...stepsRef.current]);
          } else if ("tool_result" in frame) {
            finishTool(stepsRef.current, frame.tool_result);
            setSteps([...stepsRef.current]);
          } else if ("agent_start" in frame) {
            openAgent(stepsRef.current, frame.agent_start);
            setSteps([...stepsRef.current]);
          } else if ("agent_done" in frame) {
            settleAgent(stepsRef.current, frame.agent_done);
            setSteps([...stepsRef.current]);
          } else if ("swarm_stats" in frame) {
            saveSwarmStats(stepsRef.current, frame.swarm_stats);
            setSteps([...stepsRef.current]);
          } else if ("interrupt" in frame) {
            // A write is proposed and paused; the composer is disabled until
            // the user answers the confirmation card.
            setApproval(frame.interrupt);
          } else if ("error" in frame) {
            streamError = frame.error;
          }
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          aborted = true;
        } else {
          streamError = (e as ApiError).message;
          setError((e as ApiError).message);
        }
      } finally {
        streamRef.current = null;
        if (streamConvRef.current === id) streamConvRef.current = null;
        setSending(false);
        if (!aborted) {
          setElapsedMs(Date.now() - startedAt);
          // One update: the streamed turn becomes a real message in the same
          // frame the draft disappears, carrying the steps so they don't blink
          // out before the refetch lands.
          if (text || streamError) {
            const finished: AssistantMessageOut = {
              id: `stream-${Date.now()}`,
              role: "assistant",
              content: text,
              model: null,
              error: streamError,
              created_at: new Date().toISOString(),
              steps: stepsRef.current.length ? stepsRef.current : null,
            };
            setDetail((d) =>
              d && d.id === id ? { ...d, messages: [...d.messages, finished] } : d,
            );
            stepsRef.current = [];
            setSteps([]);
          }
          setDraft(null);
        }
      }

      if (aborted) return;

      // Reconcile with what was actually stored (real ids, model label), then
      // let the rail re-sort.
      try {
        await loadDetail(id);
      } catch {
        // Keep the optimistic transcript rather than blanking the thread.
      }
      onRailRefresh();
    },
    [loadDetail, onRailRefresh],
  );

  /** Answer the confirmation card: resume the paused run with a yes or no. */
  const decide = useCallback(
    async (approved: boolean) => {
      if (!conversationId || !approval) return;
      setApproval(null);
      await runStream(conversationId, undefined, { approved });
    },
    [approval, conversationId, runStream],
  );

  /** Rate an assistant turn. Optimistic; the rating is for review only. */
  const submitFeedback = useCallback(
    async (messageId: string, feedback: "up" | "down" | null) => {
      setDetail((d) =>
        d
          ? { ...d, messages: d.messages.map((m) => (m.id === messageId ? { ...m, feedback } : m)) }
          : d,
      );
      try {
        await api.post(`/assistant/messages/${messageId}/feedback`, { feedback });
      } catch {
        // Best-effort: a lost rating is not worth disturbing the thread. The
        // optimistic mark stays until the next reload reconciles it.
      }
    },
    [],
  );

  // A prompt handed over from the dashboard bar: create the thread first, then
  // stream the reply. The trailing user message is already persisted, so the
  // stream is opened without content.
  useEffect(() => {
    if (!initialPrompt || conversationId || promptRef.current === initialPrompt) return;
    promptRef.current = initialPrompt;

    // Deferred: this sets state, and a setState in an effect body cascades
    // renders (react-hooks/set-state-in-effect). Same queueMicrotask shape the
    // other detail pages in this app use.
    queueMicrotask(() => {
      void (async () => {
        setSending(true);
        setError("");
        try {
          const created = await api.post<AssistantConversationDetailOut>(
            "/assistant/conversations",
            { content: initialPrompt },
            { "Idempotency-Key": crypto.randomUUID() },
          );

          // Mark the created user turn answered BEFORE handing the id up: the
          // load effect below fires the moment `conversationId` becomes real,
          // and without this it would see an unanswered trailing turn and
          // generate a second reply to the same question.
          const last = created.messages[created.messages.length - 1];
          if (last) answeredRef.current = last.id;

          setDetail(created);
          onCreated(created.id);
          await runStream(created.id);
        } catch (e) {
          setError((e as ApiError).message);
        } finally {
          setSending(false);
        }
      })();
    });
  }, [initialPrompt, conversationId, onCreated, runStream]);

  // Load an existing thread, and answer it if it was left with an unanswered
  // question (a thread created by an earlier visit that never got its reply).
  useEffect(() => {
    if (!conversationId) return;

    let cancelled = false;

    queueMicrotask(() => {
      void (async () => {
        setLoading(true);
        setError("");
        try {
          const d = await loadDetail(conversationId);
          if (cancelled) return;
          const last = d.messages[d.messages.length - 1];
          if (last?.role === "user" && answeredRef.current !== last.id) {
            answeredRef.current = last.id;
            void runStream(conversationId);
          }
        } catch (e) {
          if (!cancelled) setError((e as ApiError).message);
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
    });

    return () => {
      cancelled = true;
    };
  }, [conversationId, loadDetail, runStream]);

  useEffect(() => {
    // The optimistic first turn is replaced by the persisted conversation as
    // soon as its id arrives from the page shell.
    if (conversationId && pendingMessage) {
      queueMicrotask(() => setPendingMessage(null));
    }
  }, [conversationId, pendingMessage]);

  // Switching threads cancels a reply still arriving for the *old* one —
  // nothing is on screen to receive the remaining tokens, and the backend stops
  // generating the moment the connection drops.
  //
  // This runs in the effect body, not its cleanup, deliberately. A cleanup sees
  // the conversationId it was created with (still null while a brand-new thread
  // is being created), so it would abort that thread's own first reply — which
  // is exactly what used to swallow every answer: the request succeeded and the
  // reply was stored, but the client cancelled its stream microseconds into the
  // wait and rendered nothing.
  useEffect(() => {
    if (streamConvRef.current && streamConvRef.current !== conversationId) {
      streamRef.current?.abort();
    }
  }, [conversationId]);

  // Closing the chat cancels whatever is in flight.
  useEffect(() => () => streamRef.current?.abort(), []);

  const send = useCallback(async () => {
    const text = value.trim();
    if (!text || sending) return;
    setValue("");
    setError("");
    // The user is now driving; any record handoff that opened this thread is
    // spent, so the host can drop its panel.
    onUserMessage?.();

    if (!conversationId) {
      // Blank thread: create it, then stream. Same path the dashboard bar takes.
      setSending(true);
      setPendingMessage({
        id: `pending-${Date.now()}`,
        role: "user",
        content: text,
        model: null,
        error: null,
        created_at: new Date().toISOString(),
      });
      try {
        const created = await api.post<AssistantConversationDetailOut>(
          "/assistant/conversations",
          { content: text },
          { "Idempotency-Key": crypto.randomUUID() },
        );
        const last = created.messages[created.messages.length - 1];
        if (last) answeredRef.current = last.id;
        setDetail(created);
        onCreated(created.id);
        await runStream(created.id);
      } catch (e) {
        setError((e as ApiError).message);
        setPendingMessage(null);
        setValue(text); // hand the prompt back rather than swallowing it
      } finally {
        setSending(false);
      }
      return;
    }

    // Optimistic user turn, so the bubble lands on the same frame as the send.
    const optimistic: AssistantMessageOut = {
      id: `send-${Date.now()}`,
      role: "user",
      content: text,
      model: null,
      error: null,
      created_at: new Date().toISOString(),
    };
    setDetail((d) => (d && d.id === conversationId ? { ...d, messages: [...d.messages, optimistic] } : d));
    await runStream(conversationId, text);
  }, [value, sending, conversationId, onCreated, runStream, onUserMessage]);

  /** Insert a picked record as an `@kind:"label"` token at the end of the draft. */
  const insertReference = useCallback((ref: Reference) => {
    const token = `@${ref.kind}:"${ref.label}"`;
    setValue((v) => (v.trim() ? `${v.replace(/\s+$/, "")} ${token}` : token));
    setRefsOpen(false);
  }, []);

  // Read the thread only when the loaded detail is the one being shown.
  // Switching conversations therefore never flashes the previous transcript,
  // and there is no reset effect to fall out of sync.
  const active = conversationId && detail?.id === conversationId ? detail : null;
  const messages = conversationId
    ? (active?.messages ?? [])
    : pendingMessage ? [pendingMessage] : [];
  const activeDraft = conversationId || sending ? draft : null;
  const showSpinner = Boolean(conversationId) && loading && !active;
  const showCenteredComposer = !conversationId && !sending && !initialPrompt && messages.length === 0;
  const quickPrompts = [
    ["Members", "Summarize member activity and follow-ups."],
    ["Revenue", "Summarize revenue and payment trends."],
    ["Retention", "Which members are at risk of leaving?"],
    ["Plans", "Review membership plan performance."],
  ];

  const composer = (
    <>
      {refsOpen && <ReferencePicker onPick={insertReference} onClose={() => setRefsOpen(false)} />}
      <div className="mx-auto w-full max-w-3xl">
        <ChatComposer
          value={value}
          onChange={setValue}
          onSubmit={send}
          sending={sending}
          autoFocus
          focusSignal={focusSignal}
          className={showCenteredComposer ? "assistant-composer-centered" : !conversationId ? "assistant-composer-docking" : ""}
          placeholder={conversationId ? "Reply…" : "Ask your gym assistant…"}
          onReference={() => setRefsOpen((v) => !v)}
          onReview={showCenteredComposer ? () => {
            setValue("Review my gym’s recent performance and highlight what needs attention.");
            setFocusSignal((current) => current + 1);
          } : undefined}
        />
      </div>
    </>
  );

  if (showCenteredComposer) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-8 px-4 pb-8 sm:px-6">
        {error && <div className="w-full max-w-3xl"><Alert>{error}</Alert></div>}
        <div className="assistant-welcome flex flex-col items-center text-center">
          <h1 className="font-heading text-[26px] font-medium tracking-tight text-foreground sm:text-[30px]">
            How can I help you today?
          </h1>
        </div>
        <div className="assistant-welcome-composer w-full max-w-2xl">
          {composer}
        </div>
        <div className="flex flex-wrap items-center justify-center gap-x-7 gap-y-3 text-sm">
          {quickPrompts.map(([label, prompt]) => (
            <button
              key={label}
              type="button"
              onClick={() => {
                setValue(prompt);
                setFocusSignal((current) => current + 1);
              }}
              className="text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand/60"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <>
      {error && (
        <div className="shrink-0 px-4 pt-4 sm:px-6">
          <div className="mx-auto w-full max-w-3xl">
            <Alert>{error}</Alert>
          </div>
        </div>
      )}

      {showSpinner ? (
        <div className="flex flex-1 items-center justify-center">
          <Spinner />
        </div>
      ) : (
        <ChatThread
          messages={messages}
          draft={activeDraft}
          steps={sending ? steps : []}
          elapsedMs={elapsedMs}
          generating={sending}
          approval={approval}
          onDecide={decide}
          onFeedback={submitFeedback}
        />
      )}

      {!conversationId && sending && messages.length === 0 && (
        <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground" role="status">
          Starting your chat…
        </div>
      )}

      {/* The composer is bottom-anchored, so the gap under it is the one
          measurement on this page you can actually feel — and it is the sum of
          two paddings, not one. The shell's `<main>` already contributes
          `py-8`/`lg:py-10`, and this container used to add `pb-5` on top of it,
          putting the field 52–60px off the bottom. The dock bar this composer
          hands off to sits at `bottom-5`, 20px, so the two disagreed at the
          exact moment the prompt moves between them.

          The negative margin cancels the rest of the shell's padding, leaving
          20px at both breakpoints: 32 − 12 and 40 − 20. It is a negative margin
          rather than a smaller `pb-*` because the shell's padding is shared with
          every other page and this page is the only one that wants it gone. */}
      <div className="relative -mb-3 shrink-0 px-4 pb-0 pt-2 sm:px-6 lg:-mb-5">
        {composer}
      </div>
    </>
  );
}

/** Merge a reasoning delta into the trailing thinking step (or start one). */
function pushThinking(steps: AssistantStep[], text: string): void {
  const last = steps[steps.length - 1];
  if (last && last.type === "thinking") {
    last.text += text;
  } else {
    steps.push({ type: "thinking", text });
  }
}

/** Resolve the newest in-flight tool step with its result.
 *
 *  Correlated by order rather than id: the model calls one tool at a time
 *  (gpt-oss has no parallel tool calls), so the last unfinished step is always
 *  the one that just completed.
 */
function finishTool(steps: AssistantStep[], result: { name: string; summary: string }): void {
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    if (step.type === "tool" && !step.done) {
      steps[i] = { ...step, done: true, summary: result.summary };
      return;
    }
  }
  steps.push({ type: "tool", name: result.name, summary: result.summary, done: true });
}

/** Open a swarm agent's row, or update it if it is already there.
 *
 *  Every agent is announced before any of them starts, so the tree is drawn
 *  whole and then fills in. An agent that arrives twice — which cannot happen
 *  today, but would if the planner ever repeated an id — updates in place
 *  rather than growing a duplicate row. */
function openAgent(steps: AssistantStep[], agent: AgentOpened): void {
  const at = indexOfAgent(steps, agent.id);
  if (at === -1) {
    steps.push({ type: "agent", ...agent });
    return;
  }
  const existing = steps[at];
  if (existing.type === "agent") steps[at] = { ...existing, ...agent };
}

/** Settle a swarm agent with its finding.
 *
 *  Correlated by id, not by order — the opposite of `finishTool`, and for a
 *  concrete reason: tools run one at a time, so the newest unfinished step is
 *  always the one that just finished, but the swarm's forty agents run at once
 *  and settle in whatever order they happen to finish. Matching by position
 *  would hang a finding on whichever agent started last. */
function settleAgent(steps: AssistantStep[], result: AgentSettled): void {
  const at = indexOfAgent(steps, result.id);
  if (at === -1) {
    // A result with no matching row would otherwise be dropped silently, and a
    // finding the user cannot see is a finding that did not happen.
    steps.push({
      type: "agent",
      id: result.id,
      name: result.id,
      domain: "",
      status: result.status,
      summary: result.summary,
      detail: result.detail,
      ms: result.ms,
    });
    return;
  }
  const existing = steps[at];
  if (existing.type === "agent") steps[at] = { ...existing, ...result };
}

/** Record what the swarm turn cost.
 *
 *  Replaces rather than appends: a turn that resumed from an approval pause
 *  would otherwise end up with two sets of numbers disagreeing at the top of
 *  one panel. Keyed by type for the same reason agents are keyed by id — the
 *  step is a fact about the turn, and there is only one of it. */
function saveSwarmStats(steps: AssistantStep[], stats: SwarmStats): void {
  const at = steps.findIndex((s) => s.type === "swarm");
  if (at === -1) steps.push({ type: "swarm", ...stats });
  else steps[at] = { type: "swarm", ...stats };
}

function indexOfAgent(steps: AssistantStep[], id: string): number {
  return steps.findIndex((s) => s.type === "agent" && s.id === id);
}
