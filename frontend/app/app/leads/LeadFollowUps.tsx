"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type FollowUp = {
  id: string;
  day: 0 | 1 | 3 | 7;
  due_at: string;
  status: "scheduled" | "due" | "completed" | "skipped";
  completed_at: string | null;
  note: string | null;
  email_status: "pending" | "sent" | "failed" | "skipped";
  email_sent_at: string | null;
  sms_status: "pending" | "sent" | "failed" | "skipped";
  sms_sent_at: string | null;
};

type Props = { leadId: string };

const LABELS: Record<FollowUp["status"], string> = {
  scheduled: "Upcoming",
  due: "Due now",
  completed: "Completed",
  skipped: "Skipped",
};

const STYLES: Record<FollowUp["status"], string> = {
  scheduled: "bg-muted text-muted-foreground",
  due: "bg-amber-100 text-amber-800",
  completed: "bg-emerald-100 text-emerald-800",
  skipped: "bg-zinc-100 text-zinc-600",
};

const EMAIL_LABELS: Record<FollowUp["email_status"], string> = {
  pending: "Email pending",
  sent: "Email sent",
  failed: "Email failed — follow up manually",
  skipped: "No email sent",
};

const SMS_LABELS: Record<FollowUp["sms_status"], string> = {
  pending: "SMS pending",
  sent: "SMS accepted by provider",
  failed: "SMS failed — follow up manually",
  skipped: "No SMS sent",
};

export function LeadFollowUps({ leadId }: Props) {
  const [items, setItems] = useState<FollowUp[] | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setItems(await api.get<FollowUp[]>(`/leads/${leadId}/followups`));
    } catch (caught) {
      setError((caught as ApiError).message);
      setItems([]);
    }
  }, [leadId]);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  async function closeStep(item: FollowUp, status: "completed" | "skipped") {
    setBusyId(item.id);
    setError("");
    try {
      await api.patch(`/leads/${leadId}/followups/${item.id}`, {
        status,
        note: notes[item.id] || null,
      });
      await load();
    } catch (caught) {
      setError((caught as ApiError).message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section aria-labelledby="lead-followups-title" className="mb-6 rounded-xl border border-border bg-background p-4">
      <div className="mb-3">
        <h3 id="lead-followups-title" className="text-sm font-semibold">Follow-up sequence</h3>
        <p className="mt-1 text-xs text-muted-foreground">Email and SMS follow-ups run only with the matching recorded permission. Text delivery needs a connected provider; recipients can reply STOP to opt out.</p>
      </div>
      {error && <Alert tone="danger">{error}</Alert>}
      {items === null ? <Spinner /> : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No follow-up steps are scheduled.</p>
      ) : (
        <ol className="space-y-2">
          {items.map((item) => (
            <li key={item.id} className="rounded-lg border border-border px-3 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="text-sm font-medium">Day {item.day}</span>
                  <span className="ml-2 text-xs text-muted-foreground">
                    {new Date(item.due_at).toLocaleString()}
                  </span>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${STYLES[item.status]}`}>
                  {LABELS[item.status]}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Email: {EMAIL_LABELS[item.email_status]}
                {item.email_sent_at && ` · ${new Date(item.email_sent_at).toLocaleString()}`}
                <br />SMS: {SMS_LABELS[item.sms_status]}
                {item.sms_sent_at && ` · ${new Date(item.sms_sent_at).toLocaleString()}`}
              </p>
              {item.note && <p className="mt-2 text-xs text-muted-foreground">{item.note}</p>}
              {item.status === "due" && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <input
                    aria-label={`Day ${item.day} follow-up note`}
                    value={notes[item.id] ?? ""}
                    onChange={(event) => setNotes((current) => ({ ...current, [item.id]: event.target.value }))}
                    maxLength={2000}
                    placeholder="Optional outcome note"
                    className="h-9 min-w-48 flex-1 rounded-md border border-input bg-background px-3 text-sm"
                  />
                  <Button type="button" disabled={busyId !== null} loading={busyId === item.id} onClick={() => void closeStep(item, "completed")}>
                    Done
                  </Button>
                  <Button type="button" variant="secondary" disabled={busyId !== null} onClick={() => void closeStep(item, "skipped")}>
                    Skip
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
