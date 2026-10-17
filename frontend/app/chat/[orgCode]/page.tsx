"use client";

import { CSSProperties, FormEvent, useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

type ChatMessage = { id: string; direction: string; body: string; created_at: string };
type Thread = { id: string; status: string; messages: ChatMessage[] };
type Workspace = { organization_name: string; accent_color: string | null };

export default function PublicMemberChatPage() {
  const params = useParams<{ orgCode: string }>();
  const orgCode = params.orgCode;
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [thread, setThread] = useState<Thread | null>(null);
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const conversationId = thread?.id;

  const loadThread = useCallback(async (sessionToken: string, id: string) => {
    const response = await fetch(`/api/public-chat/conversations/${encodeURIComponent(id)}`, { headers: { Authorization: `Bearer ${sessionToken}` }, cache: "no-store" });
    if (!response.ok) throw new Error("This chat session has expired. Start a new conversation.");
    const data = await response.json() as Thread;
    setThread(data);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch(`/api/public-chat/${encodeURIComponent(orgCode)}`, { cache: "no-store" });
        if (!response.ok) throw new Error("This workspace has not enabled web chat.");
        const info = await response.json() as Workspace;
        if (cancelled) return;
        setWorkspace(info);
        const savedToken = window.localStorage.getItem(`acron-chat:${orgCode}`) ?? "";
        const savedId = window.localStorage.getItem(`acron-chat-thread:${orgCode}`) ?? "";
        if (savedToken && savedId) {
          setToken(savedToken);
          try { await loadThread(savedToken, savedId); }
          catch {
            window.localStorage.removeItem(`acron-chat:${orgCode}`);
            window.localStorage.removeItem(`acron-chat-thread:${orgCode}`);
            setToken("");
          }
        }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load chat.");
      }
    })();
    return () => { cancelled = true; };
  }, [orgCode, loadThread]);

  useEffect(() => {
    if (!conversationId || !token) return;
    const timer = window.setInterval(() => { void loadThread(token, conversationId).catch(() => undefined); }, 5000);
    return () => window.clearInterval(timer);
  }, [conversationId, token, loadThread]);

  const start = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/public-chat/${encodeURIComponent(orgCode)}/conversations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, email, message }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not start the chat.");
      setToken(data.token); setThread(data.thread); setMessage("");
      window.localStorage.setItem(`acron-chat:${orgCode}`, data.token);
      window.localStorage.setItem(`acron-chat-thread:${orgCode}`, data.thread.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not start the chat."); }
    finally { setBusy(false); }
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (!message.trim() || !thread || !token) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/public-chat/conversations/${encodeURIComponent(thread.id)}/messages`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ message }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not send your message.");
      setThread(data); setMessage("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not send your message."); }
    finally { setBusy(false); }
  };

  const startNew = () => {
    window.localStorage.removeItem(`acron-chat:${orgCode}`);
    window.localStorage.removeItem(`acron-chat-thread:${orgCode}`);
    setThread(null); setToken(""); setName(""); setEmail(""); setError("");
  };

  return <main className="min-h-screen bg-[var(--background)] px-4 py-10 text-[var(--foreground)]" style={{ "--chat-accent": workspace?.accent_color || "#f97316" } as CSSProperties}>
    <section className="mx-auto flex min-h-[min(760px,calc(100vh-5rem))] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-xl">
      <header className="flex items-center justify-between border-b border-[var(--border)] px-6 py-5">
        <div><p className="text-xs uppercase tracking-[.18em] text-[var(--chat-accent)]">Member support</p><h1 className="mt-1 text-lg font-semibold">{workspace?.organization_name || "Loading chat…"}</h1><p className="mt-1 text-xs text-muted-foreground">Messages go directly to the team inbox.</p></div>
        {thread && <button type="button" onClick={startNew} className="rounded-lg border border-[var(--border)] px-3 py-2 text-xs hover:bg-foreground/5">New conversation</button>}
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto p-6" aria-live="polite">
        {!thread && <div className="mx-auto mt-12 max-w-md text-center"><h2 className="text-2xl font-semibold">How can we help?</h2><p className="mt-2 text-sm text-muted-foreground">Leave a message and our team will reply here.</p></div>}
        {thread?.messages.map((item) => <div key={item.id} className={`flex ${item.direction === "inbound" ? "justify-end" : "justify-start"}`}><p className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm ${item.direction === "inbound" ? "bg-[var(--chat-accent)] text-white" : "border border-[var(--border)] bg-background"}`}>{item.body}<time className="mt-1 block text-[10px] opacity-65">{new Date(item.created_at).toLocaleString()}</time></p></div>)}
      </div>
      {error && <p role="alert" className="mx-6 mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
      {!thread ? <form onSubmit={start} className="grid gap-3 border-t border-[var(--border)] p-5 sm:grid-cols-2">
        <label className="text-xs text-muted-foreground">Your name<input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5 h-10 w-full rounded-lg border border-[var(--border)] bg-background px-3 text-sm text-foreground" /></label>
        <label className="text-xs text-muted-foreground">Email<input required type="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1.5 h-10 w-full rounded-lg border border-[var(--border)] bg-background px-3 text-sm text-foreground" /></label>
        <label className="text-xs text-muted-foreground sm:col-span-2">Message<textarea required maxLength={4000} rows={3} value={message} onChange={(e) => setMessage(e.target.value)} className="mt-1.5 w-full resize-y rounded-lg border border-[var(--border)] bg-background px-3 py-2 text-sm text-foreground" /></label>
        <button disabled={busy} className="h-10 rounded-lg bg-[var(--chat-accent)] px-4 text-sm font-medium text-white disabled:opacity-50 sm:col-span-2">{busy ? "Sending…" : "Start conversation"}</button>
      </form> : <form onSubmit={send} className="flex items-end gap-3 border-t border-[var(--border)] p-5"><textarea aria-label="Write a message" rows={2} maxLength={4000} value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} className="max-h-36 min-h-11 flex-1 resize-y rounded-xl border border-[var(--border)] bg-background px-4 py-3 text-sm text-foreground" placeholder="Write a message…" /><button disabled={busy || !message.trim()} className="h-11 rounded-xl bg-[var(--chat-accent)] px-5 text-sm font-medium text-white disabled:opacity-50">{busy ? "Sending…" : "Send"}</button></form>}
    </section>
  </main>;
}
