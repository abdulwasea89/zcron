"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Button, EmptyState, Input, Spinner } from "@/components/ui";
import { useModuleGate } from "@/hooks/useModuleGate";
import { api, ApiError } from "@/lib/api";
import { LeadBookings } from "./LeadBookings";

type Lead = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  goal: string | null;
  budget: string | null;
  preferred_times: string | null;
  preferences: string | null;
  source: string;
  stage: string;
  profile_sources: Record<string, string>;
  created_at: string;
  updated_at: string;
};

const STAGES = ["new", "contacted", "trial_booked", "visited", "joined", "lost"] as const;
const SOURCES = [
  ["staff_entered", "Added by your team"],
  ["web_form", "Website form"],
  ["phone", "Phone call"],
  ["walk_in", "Walk-in"],
  ["referral", "Referral"],
  ["whatsapp", "WhatsApp"],
  ["sms", "SMS"],
  ["instagram", "Instagram"],
  ["facebook", "Facebook"],
  ["line", "LINE"],
  ["wechat", "WeChat"],
  ["other", "Other"],
] as const;
const STAGE_LABEL: Record<string, string> = {
  new: "New", contacted: "Contacted", trial_booked: "Trial booked", visited: "Visited", joined: "Joined", lost: "Lost",
};
const STAGE_STYLE: Record<string, string> = {
  new: "bg-sky-50 text-sky-700", contacted: "bg-violet-50 text-violet-700", trial_booked: "bg-amber-50 text-amber-700",
  visited: "bg-indigo-50 text-indigo-700", joined: "bg-emerald-50 text-emerald-700", lost: "bg-zinc-100 text-zinc-600",
};

function profileOf(lead: Lead) {
  return { name: lead.name, email: lead.email ?? "", phone: lead.phone ?? "", source: lead.source, goal: lead.goal ?? "", budget: lead.budget ?? "", preferred_times: lead.preferred_times ?? "", preferences: lead.preferences ?? "" };
}

export default function LeadsPage() {
  const { ready } = useModuleGate("leads");
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [profile, setProfile] = useState({ name: "", email: "", phone: "", source: "staff_entered", goal: "", budget: "", preferred_times: "", preferences: "" });

  const load = useCallback(async (preferredId?: string) => {
    try {
      const rows = await api.get<Lead[]>("/leads");
      setLeads(rows);
      const active = rows.find((lead) => lead.id === preferredId) ?? rows[0] ?? null;
      setSelectedId(active?.id ?? null);
      if (active) setProfile(profileOf(active));
    } catch (e) {
      setError((e as ApiError).message);
      setLeads([]);
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  const filtered = useMemo(() => (leads ?? []).filter((lead) =>
    `${lead.name} ${lead.email ?? ""} ${lead.phone ?? ""}`.toLowerCase().includes(query.toLowerCase().trim())
  ), [leads, query]);
  const selected = (leads ?? []).find((lead) => lead.id === selectedId) ?? null;

  function selectLead(lead: Lead) {
    setSelectedId(lead.id);
    setProfile(profileOf(lead));
    setError("");
    setNotice("");
  }

  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const payload = Object.fromEntries(form.entries());
    setBusy(true); setError(""); setNotice("");
    try {
      const lead = await api.post<Lead>("/leads", payload, { "Idempotency-Key": crypto.randomUUID() });
      setSelectedId(lead.id); await load(lead.id); setShowCreate(false); setNotice("Lead profile created.");
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  async function saveProfile(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api.patch(`/leads/${selected.id}`, profile, { "Idempotency-Key": crypto.randomUUID() });
      await load(selected.id); setNotice("Profile saved.");
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  async function changeStage(stage: string) {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      await api.patch(`/leads/${selected.id}`, { stage }, { "Idempotency-Key": crypto.randomUUID() });
      await load(selected.id);
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  if (!ready) return <div className="p-8"><Spinner /></div>;

  return (
    <main className="mx-auto max-w-7xl px-5 py-8 lg:px-8">
      <PageHeader title="Leads" subtitle="Keep every prospect’s goals and next step in one place. Add leads manually today; channel capture can connect later."
        action={<Button onClick={() => { setShowCreate((value) => !value); setError(""); }}>Add lead</Button>} />
      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <div role="status" className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</div>}
      {showCreate && <form onSubmit={create} className="mb-6 rounded-2xl border border-border bg-card p-5 shadow-sm">
        <div className="mb-4"><h2 className="text-base font-semibold">New lead</h2><p className="mt-1 text-sm text-muted-foreground">Start with a name and the best way to reach them.</p></div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Input name="name" placeholder="Full name *" required maxLength={160} />
          <Input name="email" type="email" placeholder="Email" />
          <Input name="phone" type="tel" placeholder="Phone" />
          <select name="source" aria-label="Lead source" defaultValue="staff_entered" className="h-10 rounded-md border border-foreground/15 bg-background px-3 text-sm text-foreground">{SOURCES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        </div>
        <div className="mt-4 flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setShowCreate(false)}>Cancel</Button><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create lead"}</Button></div>
      </form>}

      <div className="grid min-h-[560px] gap-5 lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.5fr)]">
        <section className="overflow-hidden rounded-2xl border border-border bg-card">
          <div className="border-b border-border p-4"><div className="flex items-center justify-between"><h2 className="font-semibold">Prospects</h2><span className="text-xs text-muted-foreground">{filtered.length}</span></div><Input aria-label="Search leads" className="mt-3" placeholder="Search name, email, phone" value={query} onChange={(e) => setQuery(e.target.value)} /></div>
          <div className="max-h-[620px] overflow-y-auto">
            {leads === null ? <div className="p-6"><Spinner /></div> : filtered.length === 0 ? <EmptyState title={query ? "No matching leads" : "No leads yet"} hint={query ? "Try another name or contact detail." : "Capture your first prospect to start a profile."} /> : filtered.map((lead) => <button key={lead.id} disabled={busy} onClick={() => selectLead(lead)} className={`block w-full border-b border-border px-4 py-4 text-left transition hover:bg-muted/50 ${selected?.id === lead.id ? "bg-muted/60" : ""}`}>
              <div className="flex items-start justify-between gap-3"><span className="truncate font-medium text-foreground">{lead.name}</span><span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium ${STAGE_STYLE[lead.stage] ?? STAGE_STYLE.new}`}>{STAGE_LABEL[lead.stage] ?? lead.stage}</span></div>
              <p className="mt-1 truncate text-sm text-muted-foreground">{lead.email || lead.phone || "Contact details not added"}</p>
              <p className="mt-2 line-clamp-1 text-xs text-muted-foreground">{lead.goal || "Goal not captured yet"}</p>
            </button>)}
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-card p-5 sm:p-7">
          {!selected ? <div className="flex h-full min-h-80 items-center justify-center"><EmptyState title="Choose a lead" hint="Select a prospect to view and update their profile." /></div> : <>
            <div className="mb-6 flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
              <div><div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Lead profile</div><h2 className="mt-1 text-2xl font-semibold">{selected.name}</h2><p className="mt-1 text-sm text-muted-foreground">Added {new Date(selected.created_at).toLocaleDateString()} · Source: {selected.source.replaceAll("_", " ")}</p></div>
              <label className="grid gap-1 text-xs font-medium text-muted-foreground">Pipeline stage<select className="h-10 min-w-40 rounded-lg border border-input bg-background px-3 text-sm text-foreground" value={selected.stage} disabled={busy} onChange={(e) => void changeStage(e.target.value)}>{STAGES.map((stage) => <option key={stage} value={stage}>{STAGE_LABEL[stage]}</option>)}</select></label>
            </div>
            <LeadBookings
              key={selected.id}
              leadId={selected.id}
              preferredTimes={selected.preferred_times}
              onLeadChanged={() => load(selected.id)}
            />
            <form onSubmit={saveProfile} className="space-y-5"><fieldset disabled={busy} className="space-y-5">
              <div><h3 className="text-sm font-semibold">Contact details</h3><div className="mt-3 grid gap-4 sm:grid-cols-2"><label className="grid gap-1.5 text-sm">Name<Input value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} required maxLength={160} /></label><label className="grid gap-1.5 text-sm">Email<Input type="email" value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} /></label><label className="grid gap-1.5 text-sm">Phone<Input type="tel" value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} /></label><label className="grid gap-1.5 text-sm">Lead source<select value={profile.source} onChange={(e) => setProfile({ ...profile, source: e.target.value })} className="h-10 rounded-md border border-foreground/15 bg-background px-3 text-sm text-foreground">{SOURCES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div></div>
              <div><h3 className="text-sm font-semibold">What matters to them</h3><p className="mt-1 text-xs text-muted-foreground">Record only what the prospect shares or your team confirms. Each saved profile detail is marked staff-entered.</p><div className="mt-3 grid gap-4 sm:grid-cols-2"><label className="grid gap-1.5 text-sm">Fitness goal<textarea className="min-h-24 rounded-lg border border-input bg-background px-3 py-2 text-sm" value={profile.goal} maxLength={2000} placeholder="Build strength, improve mobility…" onChange={(e) => setProfile({ ...profile, goal: e.target.value })} /></label><label className="grid gap-1.5 text-sm">Budget<textarea className="min-h-24 rounded-lg border border-input bg-background px-3 py-2 text-sm" value={profile.budget} maxLength={200} placeholder="Comfortable monthly range" onChange={(e) => setProfile({ ...profile, budget: e.target.value })} /></label><label className="grid gap-1.5 text-sm">Preferred times<textarea className="min-h-24 rounded-lg border border-input bg-background px-3 py-2 text-sm" value={profile.preferred_times} maxLength={500} placeholder="Weekday evenings, Saturday mornings…" onChange={(e) => setProfile({ ...profile, preferred_times: e.target.value })} /></label><label className="grid gap-1.5 text-sm">Preferences<textarea className="min-h-24 rounded-lg border border-input bg-background px-3 py-2 text-sm" value={profile.preferences} maxLength={2000} placeholder="Class style, trainer preferences, other notes…" onChange={(e) => setProfile({ ...profile, preferences: e.target.value })} /></label></div></div>
              <div className="flex justify-end border-t border-border pt-4"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</Button></div>
            </fieldset></form>
          </>}
        </section>
      </div>
    </main>
  );
}
