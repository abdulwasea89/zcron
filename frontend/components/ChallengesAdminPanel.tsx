"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { Alert, Badge, Button, Input, Spinner } from "@/components/ui";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Select as RadixSelect, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, api } from "@/lib/api";

type Challenge = { id: string; title: string; description: string | null; goal_type: string; goal_target: number; reward: string | null; status: string; is_public: boolean; starts_at: string; ends_at: string; published_at: string | null; participants: number };
type ChallengeOut = Omit<Challenge, "participants">;
type Detail = Omit<Challenge, "participants"> & { participants: { member_id: string; member_name: string; progress: number; status: string; completed_at: string | null }[] };
const statusLabel: Record<string, string> = { draft: "Draft", published: "Published", paused: "Paused", completed: "Completed", archived: "Archived" };
const safeError = (error: unknown) => error instanceof ApiError ? error.message : "Could not load challenges.";

export function ChallengesAdminPanel() {
  const [rows, setRows] = useState<Challenge[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [composer, setComposer] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [goalType, setGoalType] = useState("visits");
  const [goalTarget, setGoalTarget] = useState("8");
  const [reward, setReward] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [isPublic, setIsPublic] = useState(true);

  const loadRows = useCallback(async () => {
    const challenges = await api.get<Challenge[]>("/challenges/admin?limit=200");
    setRows(challenges);
    setSelectedId((current) => current || challenges[0]?.id || "");
  }, []);
  useEffect(() => {
    let cancelled = false;
    api.get<Challenge[]>("/challenges/admin?limit=200").then((challenges) => {
      if (!cancelled) { setRows(challenges); setSelectedId(challenges[0]?.id || ""); }
    }).catch((cause: unknown) => { if (!cancelled) setError(safeError(cause)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    api.get<Detail>(`/challenges/admin/${selectedId}?limit=100`).then((challenge) => {
      if (!cancelled) setDetail(challenge);
    }).catch((cause: unknown) => { if (!cancelled) setError(safeError(cause)); });
    return () => { cancelled = true; };
  }, [selectedId]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = z.object({ title: z.string().trim().min(1).max(120), goalTarget: z.coerce.number().int().min(1).max(999) }).safeParse({ title, goalTarget });
    if (!parsed.success) { toast.error(parsed.error.issues[0]?.message ?? "Check the challenge details."); return; }
    setBusy(true);
    try {
      const start = new Date(startsAt);
      const end = new Date(endsAt);
      if (!startsAt || !endsAt || end <= start) throw new Error("Choose an end time after the start time.");
      if (start < new Date()) throw new Error("Choose a start time in the future.");
      const challenge = await api.post<ChallengeOut>("/challenges", {
        title: title.trim(), description: description.trim() || null,
        goal_type: goalType, goal_target: Number(goalTarget), reward: reward.trim() || null,
        is_public: isPublic, starts_at: start.toISOString(), ends_at: end.toISOString(),
      });
      setComposer(false); setTitle(""); setDescription(""); setReward(""); setStartsAt(""); setEndsAt("");
      setRows(await api.get<Challenge[]>("/challenges/admin?limit=200"));
      setSelectedId(challenge.id); toast.success("Challenge saved as a draft.");
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : "Could not save challenge."); }
    finally { setBusy(false); }
  }

  async function updateStatus(status: string) {
    if (!selectedId) return; setBusy(true);
    try {
      await api.post(`/challenges/${selectedId}/status`, { status });
      setRows(await api.get<Challenge[]>("/challenges/admin?limit=200"));
      setDetail(await api.get<Detail>(`/challenges/admin/${selectedId}?limit=100`));
      toast.success(`Challenge ${statusLabel[status]?.toLowerCase() ?? status}.`);
    } catch (cause) { toast.error(safeError(cause)); }
    finally { setBusy(false); }
  }

  const tone = (status: string) => status === "published" ? "success" as const : status === "archived" ? "neutral" as const : "warning" as const;
  return <div className="space-y-4">
    <section className="border border-[var(--border)] bg-card">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-3 sm:px-5"><div><h2 className="text-sm font-semibold text-foreground">Gym challenges</h2><p className="mt-1 text-xs text-muted-foreground">Set a visit, class, or streak goal and monitor member progress.</p></div><Button onClick={() => setComposer(true)}>New challenge</Button></header>
      {error && <div className="p-4"><Alert tone="danger">{error}</Alert><Button variant="secondary" className="mt-2" onClick={() => { setLoading(true); setError(""); void loadRows().catch((cause: unknown) => setError(safeError(cause))).finally(() => setLoading(false)); }}>Try again</Button></div>}
      {loading ? <div className="flex justify-center p-8"><Spinner label="Loading challenges…" /></div> : rows.length ? <div className="grid divide-y divide-[var(--border)] md:grid-cols-[minmax(210px,0.7fr)_minmax(0,1.3fr)] md:divide-x md:divide-y-0">
        <ul className="divide-y divide-[var(--border)] md:max-h-[520px] md:overflow-y-auto md:divide-y-0">{rows.map((challenge) => <li key={challenge.id} className="border-b border-[var(--border)] last:border-0"><button type="button" aria-pressed={challenge.id === selectedId} onClick={() => setSelectedId(challenge.id)} className={`w-full px-4 py-3 text-left hover:bg-foreground/[0.03] ${challenge.id === selectedId ? "bg-foreground/[0.04]" : ""}`}><span className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium text-foreground">{challenge.title}</span><Badge tone={tone(challenge.status)}>{statusLabel[challenge.status] ?? challenge.status}</Badge></span><span className="mt-1 block text-xs text-muted-foreground">{challenge.participants} participants · {challenge.goal_target} {challenge.goal_type.replaceAll("_", " ")}</span></button></li>)}</ul>
        <div className="min-w-0 p-4 sm:p-5">{detail && <><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><h3 className="text-base font-semibold text-foreground">{detail.title}</h3><Badge tone={tone(detail.status)}>{statusLabel[detail.status] ?? detail.status}</Badge>{!detail.is_public && <Badge tone="neutral">Private</Badge>}</div>{detail.description && <p className="mt-2 text-sm leading-6 text-muted-foreground">{detail.description}</p>}{detail.reward && <p className="mt-2 text-xs text-muted-foreground">Reward: <span className="font-medium text-foreground">{detail.reward}</span></p>}</div><div className="flex flex-wrap gap-2">{detail.status === "draft" && <Button loading={busy} onClick={() => setPendingStatus("published")}>Publish</Button>}{detail.status === "published" && <><Button variant="secondary" loading={busy} onClick={() => void updateStatus("paused")}>Pause</Button><Button variant="secondary" loading={busy} onClick={() => void updateStatus("completed")}>Complete</Button></>}{detail.status === "paused" && <Button loading={busy} onClick={() => void updateStatus("published")}>Resume</Button>}{detail.status !== "archived" && <Button variant="ghost" loading={busy} onClick={() => setPendingStatus("archived")}>Archive</Button>}</div></div>
          <dl className="mt-4 grid grid-cols-2 gap-px border border-[var(--border)] bg-[var(--border)] sm:grid-cols-4">{[["Goal", `${detail.goal_target} ${detail.goal_type}`], ["Participants", detail.participants.length], ["Starts", new Date(detail.starts_at).toLocaleDateString()], ["Ends", new Date(detail.ends_at).toLocaleDateString()]].map(([label, value]) => <div key={String(label)} className="bg-card px-3 py-2.5"><dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 text-sm font-semibold tabular-nums text-foreground">{value}</dd></div>)}</dl>
          <h4 className="mt-5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Member progress</h4>{detail.participants.length ? <ul className="mt-2 max-h-72 divide-y divide-[var(--border)] overflow-y-auto border-y border-[var(--border)]">{detail.participants.map((participant) => <li key={participant.member_id} className="flex items-center gap-3 py-2.5"><span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{participant.member_name}</span><span className="text-xs tabular-nums text-muted-foreground">{participant.progress}/{detail.goal_target}</span><Badge tone={participant.status === "completed" ? "success" : "neutral"}>{participant.status}</Badge></li>)}</ul> : <p className="mt-2 border-y border-[var(--border)] py-4 text-sm text-muted-foreground">No members have joined this challenge yet.</p>}
        </>}</div>
      </div> : <p className="p-6 text-sm text-muted-foreground">No challenges yet. Create one to motivate members and track participation.</p>}
    </section>
    <Sheet open={composer} onOpenChange={setComposer}><SheetContent><SheetHeader><SheetTitle>New challenge</SheetTitle><SheetDescription>New challenges start as drafts. Publish when the goal and dates are ready; only public challenges appear to members.</SheetDescription></SheetHeader><SheetBody>
      <form onSubmit={create} className="flex flex-col gap-4">
        <Input label="Challenge name" required maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} />
        <label className="block text-sm font-medium text-foreground">Goal<RadixSelect value={goalType} onValueChange={setGoalType}><SelectTrigger className="mt-1.5 h-10"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="visits">Gym visits</SelectItem><SelectItem value="classes">Classes attended</SelectItem><SelectItem value="streak">Consecutive day streak</SelectItem></SelectContent></RadixSelect></label>
        <Input label="Target" type="number" min={1} max={999} required value={goalTarget} onChange={(e) => setGoalTarget(e.target.value)} />
        <Input label="Reward (optional)" maxLength={200} value={reward} onChange={(e) => setReward(e.target.value)} />
        <Input label="Starts at" type="datetime-local" required value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
        <Input label="Ends at" type="datetime-local" required value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
        <Input label="Description (optional)" maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />
        <label className="flex items-center gap-2 text-sm text-foreground"><input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} className="accent-brand" />Show to members when published</label>
        <div className="flex justify-end"><Button type="submit" loading={busy}>Save draft</Button></div>
      </form>
    </SheetBody></SheetContent></Sheet>
    <AlertDialog open={pendingStatus !== null} onOpenChange={(open) => { if (!open) setPendingStatus(null); }}><AlertDialogContent><AlertDialogTitle>{pendingStatus === "published" ? "Publish this challenge?" : "Archive this challenge?"}</AlertDialogTitle><AlertDialogDescription>{pendingStatus === "published" ? detail?.is_public ? "Members can see this challenge after publishing. Progress unlocks when its start date arrives." : "This challenge becomes active for staff tracking and remains hidden from members." : "Archived challenges are hidden and cannot be reopened."}</AlertDialogDescription><AlertDialogFooter><AlertDialogCancel asChild><Button variant="secondary">Cancel</Button></AlertDialogCancel><AlertDialogAction asChild><Button variant={pendingStatus === "archived" ? "danger" : "primary"} loading={busy} onClick={(event) => { event.preventDefault(); const next = pendingStatus; setPendingStatus(null); if (next) void updateStatus(next); }}>{pendingStatus === "published" ? "Publish challenge" : "Archive challenge"}</Button></AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </div>;
}
