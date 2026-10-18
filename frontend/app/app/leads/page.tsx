"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { ListToolbar } from "@/components/ListToolbar";
import { ListFilterSheet } from "@/components/ListFilterSheet";
import { FieldSelect, NONE } from "@/components/FieldSelect";
import { SelectItem } from "@/components/ui/select";
import { TABLE, THEAD_ROW, TH, TR, TR_INTERACTIVE, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Alert, Button, EmptyState, Input, Spinner } from "@/components/ui";
import { useModuleGate } from "@/hooks/useModuleGate";
import { api, ApiError } from "@/lib/api";
import { LeadBookings } from "./LeadBookings";
import { LeadFollowUps } from "./LeadFollowUps";

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
  email_followup_consent: boolean;
  email_followup_consent_at: string | null;
  lost_reason: string | null;
  lead_score: number;
  lead_score_factors: string[];
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
const LOST_REASONS = [
  ["price", "Price or budget"],
  ["schedule", "Class schedule"],
  ["timing", "Not ready yet"],
  ["location", "Location or travel"],
  ["joined_elsewhere", "Joined another gym"],
  ["no_response", "Could not reach them"],
  ["not_interested", "No longer interested"],
  ["other", "Other"],
] as const;

function profileOf(lead: Lead) {
  return { name: lead.name, email: lead.email ?? "", phone: lead.phone ?? "", source: lead.source, goal: lead.goal ?? "", budget: lead.budget ?? "", preferred_times: lead.preferred_times ?? "", preferences: lead.preferences ?? "", email_followup_consent: lead.email_followup_consent };
}

export default function LeadsPage() {
  const { ready } = useModuleGate("leads");
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"active" | "joined" | "lost">("active");
  const [sourceFilter, setSourceFilter] = useState(NONE);
  const [scoreFilter, setScoreFilter] = useState(NONE);
  const [contactFilter, setContactFilter] = useState(NONE);
  const [consentFilter, setConsentFilter] = useState(NONE);
  const [showCreate, setShowCreate] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showLostReason, setShowLostReason] = useState(false);
  const [lostReason, setLostReason] = useState("no_response");
  const [profile, setProfile] = useState({ name: "", email: "", phone: "", source: "staff_entered", goal: "", budget: "", preferred_times: "", preferences: "", email_followup_consent: false });

  const load = useCallback(async (preferredId?: string) => {
    try {
      const rows = await api.get<Lead[]>("/leads");
      setLeads(rows);
      const active = rows.find((lead) => lead.id === preferredId) ?? rows[0] ?? null;
      setSelectedId(active?.id ?? null);
      if (active) {
        setProfile(profileOf(active));
        setLostReason(active.lost_reason ?? "no_response");
      }
    } catch (e) {
      setError((e as ApiError).message);
      setLeads([]);
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  const filtered = useMemo(() => (leads ?? []).filter((lead) =>
    (filter === "active" ? !["joined", "lost"].includes(lead.stage) : lead.stage === filter) &&
    `${lead.name} ${lead.email ?? ""} ${lead.phone ?? ""} ${lead.source}`.toLowerCase().includes(query.toLowerCase().trim()) &&
    (sourceFilter === NONE || lead.source === sourceFilter) &&
    (scoreFilter === NONE || (scoreFilter === "high" ? lead.lead_score >= 70 : scoreFilter === "medium" ? lead.lead_score >= 40 && lead.lead_score < 70 : lead.lead_score < 40)) &&
    (contactFilter === NONE || (contactFilter === "email" ? Boolean(lead.email) : Boolean(lead.phone))) &&
    (consentFilter === NONE || lead.email_followup_consent === (consentFilter === "yes"))
  ), [leads, filter, query, sourceFilter, scoreFilter, contactFilter, consentFilter]);
  const activeLeadFilterCount = [sourceFilter, scoreFilter, contactFilter, consentFilter].filter((v) => v !== NONE).length;
  function clearLeadFilters() { setSourceFilter(NONE); setScoreFilter(NONE); setContactFilter(NONE); setConsentFilter(NONE); }
  const selected = (leads ?? []).find((lead) => lead.id === selectedId) ?? null;

  function selectLead(lead: Lead) {
    setSelectedId(lead.id);
    setProfile(profileOf(lead));
    setLostReason(lead.lost_reason ?? "no_response");
    setError("");
    setNotice("");
    setShowDetails(true);
  }

  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const payload = Object.fromEntries(form.entries());
    setBusy(true); setError(""); setNotice("");
    try {
      const lead = await api.post<Lead>("/leads", payload, { "Idempotency-Key": crypto.randomUUID() });
      setSelectedId(lead.id); await load(lead.id); setShowCreate(false); setShowDetails(true); setNotice("Lead profile created.");
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
    if (stage === "lost") {
      setLostReason(selected.lost_reason ?? "no_response");
      setShowLostReason(true);
      return;
    }
    await saveStage(stage);
  }

  async function saveStage(stage: string, reason?: string) {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      await api.patch(`/leads/${selected.id}`, { stage, ...(reason ? { lost_reason: reason } : {}) }, { "Idempotency-Key": crypto.randomUUID() });
      await load(selected.id);
      setShowLostReason(false);
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  if (!ready) return <div className="p-8"><Spinner /></div>;

  return (
    <main className="w-full">
      <PageHeader title="Leads" subtitle="Track prospects from first contact to membership."
        action={<Button onClick={() => { setShowCreate(true); setError(""); }}>+ New lead</Button>} />
      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <div role="status" className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</div>}
      {showLostReason && selected && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"><section role="dialog" aria-modal="true" aria-labelledby="lost-reason-title" className="w-full max-w-md rounded-2xl border border-border bg-card p-5 shadow-xl"><h2 id="lost-reason-title" className="text-lg font-semibold">Why was this lead lost?</h2><p className="mt-1 text-sm text-muted-foreground">Choose the closest reason so your team can improve follow-up and qualification.</p><label className="mt-4 grid gap-1.5 text-sm">Lost reason<select value={lostReason} onChange={(event) => setLostReason(event.target.value)} className="h-10 rounded-md border border-input bg-background px-3">{LOST_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><div className="mt-5 flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setShowLostReason(false)}>Cancel</Button><Button type="button" variant="danger" disabled={busy} onClick={() => void saveStage("lost", lostReason)}>Mark lost</Button></div></section></div>}
      <Sheet open={showCreate} onOpenChange={setShowCreate}>
        <SheetContent><SheetHeader><SheetTitle>New lead</SheetTitle><SheetDescription>Add the prospect’s contact details.</SheetDescription></SheetHeader><SheetBody>
      <form onSubmit={create} className="space-y-4">
        <div className="mb-4"><h2 className="text-base font-semibold">New lead</h2><p className="mt-1 text-sm text-muted-foreground">Start with a name and the best way to reach them.</p></div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Input name="name" placeholder="Full name *" required maxLength={160} />
          <Input name="email" type="email" placeholder="Email" />
          <Input name="phone" type="tel" placeholder="Phone" />
          <select name="source" aria-label="Lead source" defaultValue="staff_entered" className="h-10 rounded-md border border-foreground/15 bg-background px-3 text-sm text-foreground">{SOURCES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        </div>
        <label className="mt-4 flex items-start gap-2 text-sm text-muted-foreground"><input name="email_followup_consent" type="checkbox" value="true" className="mt-1" /><span>Prospect gave permission to receive these follow-up emails. Leave unchecked otherwise.</span></label>
        <div className="mt-4 flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setShowCreate(false)}>Cancel</Button><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create lead"}</Button></div>
      </form>
        </SheetBody></SheetContent>
      </Sheet>

      <ListToolbar
        tabs={[
          { value: "active", label: "Active", count: (leads ?? []).filter((lead) => !["joined", "lost"].includes(lead.stage)).length },
          { value: "joined", label: "Joined", count: (leads ?? []).filter((lead) => lead.stage === "joined").length },
          { value: "lost", label: "Lost", count: (leads ?? []).filter((lead) => lead.stage === "lost").length },
        ]}
        value={filter} onChange={setFilter} search={query} onSearch={setQuery} searchPlaceholder="Search leads…"
      >
          <ListFilterSheet title="Filter leads" description="Focus on a source, lead quality, or contact readiness." activeCount={activeLeadFilterCount} resultCount={filtered.length} onClear={clearLeadFilters}>
            <FieldSelect label="Lead source" value={sourceFilter} onChange={setSourceFilter}>
              <SelectItem value={NONE}>All sources</SelectItem>
              {SOURCES.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
            </FieldSelect>
            <FieldSelect label="Lead score" value={scoreFilter} onChange={setScoreFilter}>
              <SelectItem value={NONE}>Any score</SelectItem><SelectItem value="high">High · 70–100</SelectItem><SelectItem value="medium">Medium · 40–69</SelectItem><SelectItem value="low">Low · under 40</SelectItem>
            </FieldSelect>
            <FieldSelect label="Contact detail" value={contactFilter} onChange={setContactFilter}>
              <SelectItem value={NONE}>Any contact detail</SelectItem><SelectItem value="email">Has email</SelectItem><SelectItem value="phone">Has phone</SelectItem>
            </FieldSelect>
            <FieldSelect label="Email follow-up permission" value={consentFilter} onChange={setConsentFilter}>
              <SelectItem value={NONE}>Any permission status</SelectItem><SelectItem value="yes">Permission granted</SelectItem><SelectItem value="no">No permission</SelectItem>
            </FieldSelect>
          </ListFilterSheet>
      </ListToolbar>
      <div className="mt-3 overflow-x-auto">
        {leads === null ? <Spinner label="Loading leads…" /> : filtered.length === 0 ?
          <EmptyState title={query || activeLeadFilterCount ? "No matching leads" : `No ${filter} leads`} hint={query || activeLeadFilterCount ? "Adjust your search or filters and try again." : "Add a lead to start tracking prospects."} /> :
          <table className={`${TABLE} min-w-[720px]`}>
            <thead><tr className={THEAD_ROW}>
              <th className={`${TH} ${CELL_FIRST}`}>Name</th>
              <th className={`${TH} ${CELL}`}>Contact</th>
              <th className={`${TH} ${CELL}`}>Source</th>
              <th className={`${TH} ${CELL}`}>Stage</th>
              <th className={`${TH} ${CELL}`}>Score</th>
              <th className={`${TH} ${CELL_LAST}`}>Updated</th>
            </tr></thead>
            <tbody>{filtered.map((lead) => <tr key={lead.id} className={`${TR} ${TR_INTERACTIVE}`} onClick={() => selectLead(lead)}>
              <td className={`${TD} ${CELL_FIRST} py-3`}><button className="text-left text-[13px] font-medium text-foreground focus-visible:outline-2 focus-visible:outline-brand" onClick={(event) => { event.stopPropagation(); selectLead(lead); }}>{lead.name}</button><p className="text-[11px] text-muted-foreground">{lead.goal || "No goal added"}</p></td>
              <td className={`${TD} ${CELL} py-3 text-[12px]`}>{lead.email || lead.phone || "—"}</td>
              <td className={`${TD} ${CELL} py-3 text-[12px]`}>{lead.source.replaceAll("_", " ")}</td>
              <td className={`${TD} ${CELL} py-3`}><span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STAGE_STYLE[lead.stage] ?? STAGE_STYLE.new}`}>{STAGE_LABEL[lead.stage] ?? lead.stage}</span></td>
              <td className={`${TD} ${CELL} py-3 text-[12px] tabular-nums`}>{lead.lead_score}/100</td>
              <td className={`${TD} ${CELL_LAST} py-3 text-[12px] text-muted-foreground`}>{new Date(lead.updated_at).toLocaleDateString()}</td>
            </tr>)}</tbody>
          </table>}
      </div>

      <Sheet open={showDetails} onOpenChange={setShowDetails}>
        <SheetContent className="[--sheet-max-w:600px]">
          <SheetHeader><SheetTitle>{selected?.name ?? "Lead profile"}</SheetTitle><SheetDescription>Update their stage, bookings, follow-ups and details.</SheetDescription></SheetHeader>
          <SheetBody>
        <section>
          {!selected ? <div className="flex h-full min-h-80 items-center justify-center"><EmptyState title="Choose a lead" hint="Select a prospect to view and update their profile." /></div> : <>
            <div className="mb-6 flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
              <div><div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Lead profile</div><h2 className="mt-1 text-2xl font-semibold">{selected.name}</h2><p className="mt-1 text-sm text-muted-foreground">Added {new Date(selected.created_at).toLocaleDateString()} · Source: {selected.source.replaceAll("_", " ")}</p></div>
              <label className="grid gap-1 text-xs font-medium text-muted-foreground">Pipeline stage<select className="h-10 min-w-40 rounded-lg border border-input bg-background px-3 text-sm text-foreground" value={selected.stage} disabled={busy} onChange={(e) => void changeStage(e.target.value)}>{STAGES.map((stage) => <option key={stage} value={stage}>{STAGE_LABEL[stage]}</option>)}</select></label>
            </div>
            <section aria-label="Lead qualification score" className="mb-5 rounded-xl border border-border bg-background p-4"><div className="flex items-center justify-between"><h3 className="text-sm font-semibold">Lead score</h3><span className="text-lg font-semibold tabular-nums">{selected.lead_score}/100</span></div><p className="mt-1 text-xs text-muted-foreground">Explainable profile-completeness score—not a prediction of conversion.</p><div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">{selected.lead_score_factors.map((factor) => <span key={factor} className="text-[11px] text-muted-foreground">{factor}</span>)}</div>{selected.stage === "lost" && selected.lost_reason && <p className="mt-2 text-xs font-medium text-rose-700">Lost reason: {LOST_REASONS.find(([value]) => value === selected.lost_reason)?.[1] ?? selected.lost_reason}</p>}</section>
            <LeadBookings
              key={selected.id}
              leadId={selected.id}
              preferredTimes={selected.preferred_times}
              onLeadChanged={() => load(selected.id)}
            />
            <LeadFollowUps key={`followups-${selected.id}`} leadId={selected.id} />
            <form onSubmit={saveProfile} className="space-y-5"><fieldset disabled={busy} className="space-y-5">
              <div><h3 className="text-sm font-semibold">Contact details</h3><div className="mt-3 grid gap-4 sm:grid-cols-2"><label className="grid gap-1.5 text-sm">Name<Input value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} required maxLength={160} /></label><label className="grid gap-1.5 text-sm">Email<Input type="email" value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} /></label><label className="grid gap-1.5 text-sm">Phone<Input type="tel" value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} /></label><label className="grid gap-1.5 text-sm">Lead source<select value={profile.source} onChange={(e) => setProfile({ ...profile, source: e.target.value })} className="h-10 rounded-md border border-foreground/15 bg-background px-3 text-sm text-foreground">{SOURCES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div><label className="mt-3 flex items-start gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={profile.email_followup_consent} onChange={(event) => setProfile({ ...profile, email_followup_consent: event.target.checked })} className="mt-1" /><span>Prospect gave permission to receive day 0/1/3/7 follow-up emails. Uncheck to stop future emails. Changing the email address resets permission.</span></label>{selected.email_followup_consent_at && <p className="mt-1 text-xs text-muted-foreground">Permission recorded {new Date(selected.email_followup_consent_at).toLocaleString()}</p>}</div>
              <div><h3 className="text-sm font-semibold">What matters to them</h3><p className="mt-1 text-xs text-muted-foreground">Record only what the prospect shares or your team confirms. Each saved profile detail is marked staff-entered.</p><div className="mt-3 grid gap-4 sm:grid-cols-2"><label className="grid gap-1.5 text-sm">Fitness goal<textarea className="min-h-24 rounded-lg border border-input bg-background px-3 py-2 text-sm" value={profile.goal} maxLength={2000} placeholder="Build strength, improve mobility…" onChange={(e) => setProfile({ ...profile, goal: e.target.value })} /></label><label className="grid gap-1.5 text-sm">Budget<textarea className="min-h-24 rounded-lg border border-input bg-background px-3 py-2 text-sm" value={profile.budget} maxLength={200} placeholder="Comfortable monthly range" onChange={(e) => setProfile({ ...profile, budget: e.target.value })} /></label><label className="grid gap-1.5 text-sm">Preferred times<textarea className="min-h-24 rounded-lg border border-input bg-background px-3 py-2 text-sm" value={profile.preferred_times} maxLength={500} placeholder="Weekday evenings, Saturday mornings…" onChange={(e) => setProfile({ ...profile, preferred_times: e.target.value })} /></label><label className="grid gap-1.5 text-sm">Preferences<textarea className="min-h-24 rounded-lg border border-input bg-background px-3 py-2 text-sm" value={profile.preferences} maxLength={2000} placeholder="Class style, trainer preferences, other notes…" onChange={(e) => setProfile({ ...profile, preferences: e.target.value })} /></label></div></div>
              <div className="flex justify-end border-t border-border pt-4"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</Button></div>
            </fieldset></form>
          </>}
        </section>
          </SheetBody>
        </SheetContent>
      </Sheet>
    </main>
  );
}
