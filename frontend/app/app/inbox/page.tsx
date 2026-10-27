"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { ListToolbar } from "@/components/ListToolbar";
import {
  Alert,
  Avatar,
  Badge,
  Button,
  EmptyState,
  Spinner,
} from "@/components/ui";
import { LiveIndicator, useRealtimeEvent } from "@/components/Realtime";
import { useModuleGate } from "@/hooks/useModuleGate";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { api, ApiError } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { InboxConversation, InboxStats, InboxThread } from "@/lib/types";

/* ─── Shared team inbox (#19) ───
   One place for every member conversation across channels. Left: the queue with
   filters. Right: the thread + reply, with an AI draft, assignment, and
   delivery state across configured messaging providers. */

type Filter = "open" | "unassigned" | "mine" | "resolved";
type InboxStaff = { user_id: string; name: string; role: string };

const CHANNELS: Record<string, { label: string; d: string }> = {
  whatsapp: { label: "WhatsApp", d: "M8 10.5h8M8 14h5M21 12a9 9 0 11-4.2-7.6" },
  sms: { label: "SMS", d: "M8 10h8M8 14h5M4 4h16v12H8l-4 4V4z" },
  email: { label: "Email", d: "M3 6h18v12H3zM3 7l9 6 9-6" },
  instagram: { label: "Instagram", d: "M4 8a4 4 0 014-4h8a4 4 0 014 4v8a4 4 0 01-4 4H8a4 4 0 01-4-4zM12 8a4 4 0 100 8 4 4 0 000-8zM17 7h.01" },
  messenger: { label: "Messenger", d: "M12 3c5 0 9 3.6 9 8s-4 8-9 8c-1 0-2-.1-2.9-.4L5 20l1-3.3C4.8 15.3 4 13.7 4 11c0-4.4 4-8 8-8z" },
  line: { label: "LINE", d: "M4 4h16v12H8l-4 4z" },
  wechat: { label: "WeChat", d: "M9 4C5 4 2 6.7 2 10c0 1.9 1 3.6 2.5 4.7L4 18l3-1.5c.7.2 1.4.3 2 .3h.3M15 8c3.3 0 6 2.2 6 5s-2.7 5-6 5c-.6 0-1.2-.1-1.8-.3L11 19l.4-2.2" },
  telegram: { label: "Telegram", d: "M21 5L3 12l4 1.5L9 20l3-3.5 5 3L21 5z" },
  web_chat: { label: "Web chat", d: "M4 5h16v10H8l-4 4z" },
  phone: { label: "Phone", d: "M4 5c0 8 7 15 15 15l2-3-4-2-2 2c-3-1.5-5.5-4-7-7l2-2-2-4z" },
  walk_in: { label: "Walk-in", d: "M16 7a4 4 0 11-8 0 4 4 0 018 0zM4 21v-2a5 5 0 015-5h6a5 5 0 015 5v2" },
  other: { label: "Other", d: "M8 12h.01M12 12h.01M16 12h.01M4 4h16v14H8l-4 4z" },
};

const STATUS_TONE: Record<string, "success" | "warning" | "info" | "neutral"> = {
  open: "success",
  pending: "warning",
  snoozed: "info",
  resolved: "neutral",
};

function channelOf(channel: string) {
  return CHANNELS[channel] ?? CHANNELS.other;
}

function relTime(iso: string): string {
  const date = new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return "—";
  const s = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (s < 60) return "now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function clockTime(iso: string): string {
  const date = new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function ChannelIcon({ channel, className }: { channel: string; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={channelOf(channel).d} />
    </svg>
  );
}

export default function InboxPage() {
  const { ready } = useModuleGate("inbox");
  const me = useCurrentUser();

  const [filter, setFilter] = useState<Filter>("open");
  const [query, setQuery] = useState("");
  const [conversations, setConversations] = useState<InboxConversation[] | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listFailed, setListFailed] = useState(false);
  const [stats, setStats] = useState<InboxStats | null>(null);
  const [team, setTeam] = useState<InboxStaff[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [thread, setThread] = useState<InboxThread | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [logOpen, setLogOpen] = useState(false);
  const [logChannel, setLogChannel] = useState<"phone" | "walk_in">("phone");
  const [logName, setLogName] = useState("");
  const [logHandle, setLogHandle] = useState("");
  const [logBody, setLogBody] = useState("");
  const [logBusy, setLogBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const threadPanelRef = useRef<HTMLElement>(null);
  const queueRef = useRef<HTMLElement>(null);
  const listRequestRef = useRef(0);
  const threadRequestRef = useRef(0);
  const myId = me?.user_id ?? null;
  const reply = activeId ? drafts[activeId] ?? "" : "";

  const loadList = useCallback(async () => {
    const requestId = ++listRequestRef.current;
    setListLoading(true);
    setListFailed(false);
    if (filter === "mine" && !myId) {
      setConversations([]);
      setListLoading(false);
      return;
    }
    const params = new URLSearchParams();
    if (filter === "unassigned") params.set("unassigned", "true");
    else if (filter === "mine") params.set("assigned_to", myId!);
    else if (filter === "resolved") params.set("status", "resolved");
    if (query.trim()) params.set("q", query.trim());
    try {
      const rows = await api.get<InboxConversation[]>(`/inbox/conversations?${params}`);
      if (requestId === listRequestRef.current) setConversations(rows);
    } catch (e) {
      if (requestId === listRequestRef.current) {
        setError((e as ApiError).message);
        setListFailed(true);
      }
    } finally {
      if (requestId === listRequestRef.current) setListLoading(false);
    }
  }, [filter, query, myId]);

  const loadStats = useCallback(async () => {
    try {
      setStats(await api.get<InboxStats>("/inbox/stats"));
    } catch {
      /* stats are secondary */
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void loadStats());
  }, [loadStats]);

  useEffect(() => {
    if (!me) return;
    api.get<InboxStaff[]>("/staff/directory").then(setTeam).catch(() => {});
  }, [me]);

  // Refetch when the filter or search changes; debounce typing (immediate for an
  // empty query / filter switch).
  useEffect(() => {
    const id = setTimeout(() => void loadList(), query.trim() ? 250 : 0);
    return () => {
      clearTimeout(id);
      listRequestRef.current += 1;
    };
  }, [loadList, query]);

  const openThread = useCallback(async (id: string, preserve = false) => {
    const requestId = ++threadRequestRef.current;
    if (!preserve) {
      setActiveId(id);
      setThread(null);
      setThreadLoading(true);
      if (window.innerWidth < 1024) {
        requestAnimationFrame(() => threadPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
      }
    }
    setError("");
    try {
      const updated = await api.get<InboxThread>(`/inbox/conversations/${id}`);
      if (requestId !== threadRequestRef.current) return;
      setThread(updated);
      void loadList();
      void loadStats();
    } catch (e) {
      if (requestId === threadRequestRef.current) setError((e as ApiError).message);
    } finally {
      if (requestId === threadRequestRef.current) setThreadLoading(false);
    }
  }, [loadList, loadStats]);

  useRealtimeEvent(["inbox.changed"], () => {
    void loadList();
    void loadStats();
    if (activeId) void openThread(activeId, true);
  });

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [thread?.messages.length]);

  const act = useCallback(
    async (id: string, path: string, body?: unknown): Promise<InboxThread | null> => {
      setBusy(id);
      setError("");
      try {
        const headers = path === "reply" ? { "Idempotency-Key": crypto.randomUUID() } : undefined;
        const updated = await api.post<InboxThread>(`/inbox/conversations/${id}/${path}`, body, headers);
        setThread((current) => current?.id === id ? updated : current);
        void loadList();
        void loadStats();
        return updated;
      } catch (e) {
        setError((e as ApiError).message);
        return null;
      } finally {
        setBusy(null);
      }
    },
    [loadList, loadStats],
  );

  async function sendReply() {
    if (!thread || !reply.trim() || busy) return;
    const id = thread.id;
    const body = reply.trim();
    if (await act(id, "reply", { body })) {
      setDrafts((current) => ({ ...current, [id]: "" }));
    }
  }

  async function draft() {
    if (!thread || busy) return;
    const id = thread.id;
    setBusy(id);
    setError("");
    try {
      const res = await api.post<{ body: string }>(`/inbox/conversations/${id}/draft`);
      setDrafts((current) => ({ ...current, [id]: res.body }));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  }

  async function createInteractionLog(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLogBusy(true); setError("");
    try {
      const created = await api.post<InboxThread>("/inbox/conversations/ingest", {
        channel: logChannel,
        handle: logHandle.trim() || `walk-in-${crypto.randomUUID()}`,
        contact_name: logName.trim(),
        body: logBody.trim(),
      });
      setLogOpen(false); setLogName(""); setLogHandle(""); setLogBody("");
      setFilter("open"); setQuery("");
      await openThread(created.id);
      void loadList(); void loadStats();
    } catch (cause) {
      setError((cause as ApiError).message || "Could not save the interaction.");
    } finally { setLogBusy(false); }
  }

  const tabs = useMemo(
    () => [
      { value: "open" as Filter, label: "Open", count: stats?.open },
      { value: "unassigned" as Filter, label: "Unassigned", count: stats?.unassigned },
      { value: "mine" as Filter, label: "Mine", count: stats?.mine },
      { value: "resolved" as Filter, label: "Resolved", count: stats?.resolved },
    ],
    [stats],
  );

  if (!ready) return <Spinner label="Loading inbox…" />;

  const who = (c: InboxConversation) => c.member_name || c.contact_name || c.contact_handle;

  // Belt-and-suspenders: narrow the fetched page client-side too, so typing
  // always filters immediately regardless of the server round-trip.
  const q = query.trim().toLowerCase();
  const visible = (conversations ?? []).filter((c) => {
    if (!q) return true;
    return (
      (c.member_name ?? "").toLowerCase().includes(q) ||
      (c.contact_name ?? "").toLowerCase().includes(q) ||
      c.contact_handle.toLowerCase().includes(q)
    );
  });
  const initialLoading = conversations === null && listLoading;
  const empty = !listLoading && !listFailed && conversations !== null && visible.length === 0 && !activeId;
  const emptyTitle = query.trim() ? "No matching conversations" : {
    open: "All caught up",
    unassigned: "Nothing needs assigning",
    mine: "Nothing assigned to you",
    resolved: "No resolved conversations",
  }[filter];
  const emptyHint = query.trim()
    ? "Try another name or contact detail, or clear the search."
    : {
      open: "New messages will appear here as they arrive.",
      unassigned: "Every active conversation has an owner.",
      mine: "Conversations assigned to you will appear here.",
      resolved: "Resolved conversations will stay here for reference.",
    }[filter];

  function changeFilter(next: Filter) {
    if (next === filter) return;
    listRequestRef.current += 1;
    threadRequestRef.current += 1;
    setFilter(next);
    setConversations(null);
    setThread(null);
    setActiveId(null);
    setError("");
  }

  function changeQuery(next: string) {
    listRequestRef.current += 1;
    setQuery(next);
  }

  function backToQueue() {
    threadRequestRef.current += 1;
    setActiveId(null);
    setThread(null);
    requestAnimationFrame(() => queueRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  return (
    <>
      <PageHeader
        title="Inbox"
        subtitle="Every member conversation, one shared queue"
        action={<div className="flex items-center gap-3 pt-1">
          {Boolean(stats?.unread) && <span className="text-xs font-medium text-foreground">{stats?.unread} unread</span>}
          <Button variant="secondary" onClick={() => setLogOpen(true)}>Log interaction</Button>
          <LiveIndicator className="text-xs" />
        </div>}
      />

      {logOpen && <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !logBusy) setLogOpen(false); }}>
        <form onSubmit={(event) => void createInteractionLog(event)} role="dialog" aria-modal="true" aria-labelledby="interaction-log-title" className="w-full max-w-lg rounded-xl border border-border bg-surface p-5 shadow-2xl">
          <div className="flex items-start justify-between gap-4"><div><h2 id="interaction-log-title" className="text-lg font-semibold text-foreground">Log an interaction</h2><p className="mt-1 text-sm text-muted-foreground">Record a phone call or an in-person visit in the shared inbox.</p></div><button type="button" disabled={logBusy} aria-label="Close" onClick={() => setLogOpen(false)} className="rounded-md px-2 py-1 text-muted-foreground hover:bg-foreground/5">×</button></div>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <label className="text-xs text-muted-foreground">Interaction type<select value={logChannel} onChange={(event) => setLogChannel(event.target.value as "phone" | "walk_in")} className="mt-1.5 h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"><option value="phone">Phone call</option><option value="walk_in">Walk-in visit</option></select></label>
            <label className="text-xs text-muted-foreground">Contact name<input required maxLength={120} value={logName} onChange={(event) => setLogName(event.target.value)} className="mt-1.5 h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground" /></label>
            <label className="text-xs text-muted-foreground sm:col-span-2">{logChannel === "phone" ? "Phone number" : "Email or phone (optional)"}<input required={logChannel === "phone"} maxLength={254} value={logHandle} onChange={(event) => setLogHandle(event.target.value)} placeholder={logChannel === "walk_in" ? "Leave blank to label as walk-in" : "+1 555 0100"} className="mt-1.5 h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground" /></label>
            <label className="text-xs text-muted-foreground sm:col-span-2">Summary<textarea required maxLength={4000} rows={4} value={logBody} onChange={(event) => setLogBody(event.target.value)} placeholder="What did you discuss or resolve?" className="mt-1.5 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground" /></label>
          </div>
          <div className="mt-5 flex justify-end gap-2"><Button type="button" variant="secondary" disabled={logBusy} onClick={() => setLogOpen(false)}>Cancel</Button><Button type="submit" disabled={logBusy} loading={logBusy}>Save to inbox</Button></div>
        </form>
      </div>}

      {error && (
        <div className="mb-3">
          <Alert onDismiss={() => setError("")}>{error}</Alert>
        </div>
      )}

      <ListToolbar
        tabs={tabs}
        value={filter}
        onChange={changeFilter}
        search={query}
        onSearch={changeQuery}
        searchPlaceholder="Search conversations…"
      />

      {(initialLoading || empty || (listFailed && conversations === null)) ? (
        <section className="mt-5 flex min-h-[440px] flex-col items-center justify-center border-t border-border px-6 py-16 text-center" aria-live="polite">
          {initialLoading ? <Spinner label="Loading conversations…" /> : <>
            <div className="mb-4 text-muted-foreground" aria-hidden="true">
              <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                {listFailed ? (
                  <><circle cx="12" cy="12" r="9" /><path d="M12 7.5v6M12 16.5h.01" /></>
                ) : query.trim() ? (
                  <><circle cx="10.75" cy="10.75" r="6.75" /><path d="m16 16 4.25 4.25" /></>
                ) : (
                  <><path d="M4.5 5.25h15v10.5h-10L4.5 19.5V5.25Z" /><path d="m8.5 10.5 2.25 2.25 4.75-4.75" /></>
                )}
              </svg>
            </div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">{listFailed ? "Couldn’t load conversations" : emptyTitle}</h2>
            <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
              {listFailed ? "Check your connection and try again." : emptyHint}
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {query.trim() && <Button variant="secondary" onClick={() => changeQuery("")}>Clear search</Button>}
              {filter !== "open" && <Button variant="secondary" onClick={() => changeFilter("open")}>View open</Button>}
              {(filter === "open" || listFailed) && <Button variant="secondary" onClick={() => void loadList()}>Refresh inbox</Button>}
            </div>
          </>}
        </section>
      ) : <div className="mt-3 grid min-h-[520px] border-t border-border lg:h-[calc(100vh-15rem)] lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        {/* Queue */}
        <section ref={queueRef} aria-label="Conversation queue" className={`${activeId ? "hidden lg:flex" : "flex"} min-w-0 flex-col border-b border-border lg:border-b-0 lg:border-r`}>
          <div className="flex items-center justify-between px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">Conversations</h2>
            <span className="text-xs tabular-nums text-muted-foreground">{listLoading ? "Updating…" : `${visible.length} shown`}</span>
          </div>
          <div className="min-h-[280px] flex-1 overflow-y-auto lg:min-h-0">
            {conversations === null ? (
              <div className="p-5"><Spinner label="Loading conversations…" /></div>
            ) : visible.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted-foreground">{listLoading ? "Searching…" : "No conversations in this view."}</p>
            ) : (
              <ul className="divide-y divide-border/70">
                {visible.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => void openThread(c.id)}
                      aria-current={c.id === activeId ? "true" : undefined}
                      className={`flex w-full cursor-pointer items-start gap-3 px-4 py-3.5 text-left transition-colors hover:bg-foreground/[0.04] focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand ${
                        c.id === activeId ? "bg-foreground/[0.06]" : ""
                      }`}
                    >
                      <Avatar name={who(c)} size="sm" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium text-foreground">{who(c)}</span>
                          <span className="ml-auto shrink-0 text-[11px] tabular-nums text-muted-foreground">
                            {relTime(c.last_message_at)}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                          <ChannelIcon channel={c.channel} className="h-3.5 w-3.5 shrink-0" />
                          <span className="truncate">
                            {c.preview_direction === "outbound" ? "You: " : ""}
                            {c.preview ?? "—"}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center gap-1.5">
                          {c.unread_count > 0 && <Badge tone="info" size="sm">{c.unread_count} new</Badge>}
                          {c.assigned_name ? (
                            <span className="text-[11px] text-muted-foreground">· {c.assigned_name}</span>
                          ) : (
                            <Badge tone="warning" size="sm">Unassigned</Badge>
                          )}
                        </div>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Thread */}
        <section ref={threadPanelRef} aria-label="Conversation" className={`${activeId ? "flex" : "hidden lg:flex"} min-w-0 flex-col`}>
          {!thread ? (
            <div className="flex min-h-[280px] flex-1 flex-col items-center justify-center px-6 text-center">
              {threadLoading ? <Spinner label="Loading conversation…" /> : activeId ? (
                <>
                  <p className="text-sm text-muted-foreground">This conversation couldn’t be opened.</p>
                  <div className="mt-4 flex gap-2">
                    <Button variant="secondary" onClick={backToQueue}>Back to inbox</Button>
                    <Button onClick={() => void openThread(activeId)}>Retry</Button>
                  </div>
                </>
              ) : (
                <EmptyState
                  title="Choose a conversation"
                  hint="Select a message from the queue to read and reply."
                />
              )}
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
                <div className="min-w-0">
                  <button type="button" className="mb-3 min-h-9 text-xs font-medium text-muted-foreground lg:hidden" onClick={backToQueue}>← Back to inbox</button>
                  <div className="flex items-center gap-2">
                    <span className="truncate text-base font-semibold text-foreground">{who(thread)}</span>
                    <Badge tone="neutral" size="sm">
                      <span className="inline-flex items-center gap-1">
                        <ChannelIcon channel={thread.channel} className="h-3 w-3" />
                        {channelOf(thread.channel).label}
                      </span>
                    </Badge>
                    <Badge tone={STATUS_TONE[thread.status] ?? "neutral"} size="sm">{titleCase(thread.status)}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{thread.contact_handle}</p>
                </div>
                <div className="flex items-center gap-1.5">
                  <select
                    aria-label="Assign conversation to staff"
                    value={thread.assigned_to ?? ""}
                    disabled={busy === thread.id}
                    onChange={(event) => void act(thread.id, "assign", { user_id: event.target.value || null })}
                    className="h-9 max-w-48 cursor-pointer rounded-md border border-foreground/20 bg-card px-2 text-xs text-foreground focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                  >
                    <option value="">Unassigned</option>
                    {thread.assigned_to && !team.some((member) => member.user_id === thread.assigned_to) && <option value={thread.assigned_to}>{thread.assigned_name ?? "Current assignee"}</option>}
                    {team.map((member) => <option key={member.user_id} value={member.user_id}>{member.name}{member.user_id === myId ? " (me)" : ` · ${titleCase(member.role)}`}</option>)}
                  </select>
                  <select
                    aria-label="Conversation status"
                    value={thread.status}
                    disabled={busy === thread.id}
                    onChange={(e) => act(thread.id, "status", { status: e.target.value })}
                    className="h-9 cursor-pointer rounded-md border border-foreground/20 bg-card px-2 text-xs text-foreground focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                  >
                    {["open", "pending", "snoozed", "resolved"].map((s) => (
                      <option key={s} value={s}>{titleCase(s)}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div ref={scrollRef} className="min-h-[280px] flex-1 space-y-4 overflow-y-auto px-5 py-5 lg:min-h-0">
                {thread.messages.map((m) => {
                  const out = m.direction === "outbound";
                  return (
                    <div key={m.id} className={`flex ${out ? "justify-end" : "justify-start"}`}>
                      <div
                        className={`max-w-[78%] rounded-lg px-3.5 py-2.5 text-sm leading-relaxed ${
                          out
                            ? "rounded-br-sm bg-brand text-brand-foreground"
                            : "rounded-bl-sm bg-surface text-foreground"
                        }`}
                      >
                        <p className="whitespace-pre-wrap break-words">{m.body}</p>
                        <div className={`mt-1 flex items-center justify-end gap-2 text-[11px] ${out ? "text-brand-foreground/80" : "text-muted-foreground"}`}>
                          <span>{clockTime(m.created_at)}</span>
                          {out && <span>{m.delivery_status === "complained" ? "Complaint after delivery" : m.delivery_status === "delivered" ? "Delivered" : m.delivery_status === "sent" ? "Sent" : m.delivery_status === "sending" ? "Sending…" : m.delivery_status === "failed" ? "Not sent" : "Delivery unknown"}</span>}
                        </div>
                        {out && m.delivery_status === "failed" && (
                          <div className="mt-2 border-t border-current/20 pt-2 text-xs">
                            <p>{m.delivery_error || "Delivery failed. Check channel setup and try again."}</p>
                            <button
                              type="button"
                              className="mt-1 font-semibold underline underline-offset-2"
                              disabled={busy === thread.id}
                              onClick={() => void act(thread.id, `messages/${m.id}/retry`)}
                            >Retry delivery</button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="border-t border-border px-5 py-4">
                <div className="mb-2 flex items-center gap-2">
                  <Button variant="ghost" disabled={busy === thread.id} onClick={draft}>
                    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M12 3l1.6 4.6L18 9l-4.4 1.4L12 15l-1.6-4.6L6 9l4.4-1.4L12 3zM18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8L18 15z" />
                    </svg>
                    AI draft
                  </Button>
                  <span className="text-xs text-muted-foreground">Drafts a reply you can edit before sending.</span>
                </div>
                <div className="flex items-end gap-2">
                  <textarea
                    value={reply}
                    onChange={(e) => {
                      const value = e.target.value;
                      setDrafts((current) => ({ ...current, [thread.id]: value }));
                    }}
                    aria-label="Reply"
                    disabled={busy === thread.id}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void sendReply();
                      }
                    }}
                    rows={2}
                    placeholder="Write a reply… (Enter to send, Shift+Enter for a new line)"
                    className="max-h-40 min-h-[44px] w-full resize-none rounded-md border border-foreground/20 bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                  />
                  <Button
                    disabled={!reply.trim() || busy === thread.id}
                    onClick={sendReply}
                    loading={busy === thread.id}
                  >
                    Send
                  </Button>
                </div>
              </div>
            </>
          )}
        </section>
      </div>}
    </>
  );
}
