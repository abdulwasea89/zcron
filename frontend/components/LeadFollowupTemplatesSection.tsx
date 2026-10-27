"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Template = { subject: string; body: string };
type Templates = Record<"0" | "1" | "3" | "7", Template>;
const DAYS = ["0", "1", "3", "7"] as const;

export function LeadFollowupTemplatesSection() {
  const [templates, setTemplates] = useState<Templates | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    api.get<Templates>("/leads/followup-templates")
      .then((value) => { if (active) setTemplates(value); })
      .catch((error) => { if (active) toast.error((error as ApiError).message || "Could not load lead email templates."); });
    return () => { active = false; };
  }, []);

  function update(day: keyof Templates, field: keyof Template, value: string) {
    setTemplates((current) => current ? {
      ...current,
      [day]: { ...current[day], [field]: value },
    } : current);
  }

  async function save() {
    if (!templates) return;
    setBusy(true);
    try {
      setTemplates(await api.put<Templates>("/leads/followup-templates", { templates }));
      toast.success("Lead follow-up emails saved.");
    } catch (error) {
      toast.error((error as ApiError).message || "Could not save lead email templates.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="mt-6 space-y-4 border-t border-border pt-5">
    <div>
      <h3 className="text-sm font-semibold text-foreground">Lead follow-up emails</h3>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">Customize the consent-gated day 0, 1, 3, and 7 emails. Use <code>{"{name}"}</code> for the lead’s first name. Timing and consent rules stay in effect.</p>
    </div>
    {templates ? <div className="space-y-4">
      {DAYS.map((day) => <fieldset key={day} className="space-y-2 border border-border p-3">
        <legend className="px-1 text-xs font-medium text-foreground">Day {day}</legend>
        <label className="grid gap-1 text-xs text-muted-foreground">Subject
          <input value={templates[day].subject} maxLength={120} onChange={(event) => update(day, "subject", event.target.value)} className="h-9 border border-border bg-background px-3 text-sm text-foreground" />
        </label>
        <label className="grid gap-1 text-xs text-muted-foreground">Email body
          <textarea value={templates[day].body} maxLength={2000} rows={4} onChange={(event) => update(day, "body", event.target.value)} className="resize-y border border-border bg-background px-3 py-2 text-sm text-foreground" />
        </label>
      </fieldset>)}
      <Button variant="secondary" disabled={busy} onClick={() => void save()}>{busy ? "Saving…" : "Save follow-up emails"}</Button>
    </div> : <p role="status" className="text-xs text-muted-foreground">Loading email templates…</p>}
  </div>;
}
