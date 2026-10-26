"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { Button, Select } from "@/components/ui";

type Member = { member_id: string; email: string; full_name: string | null; display_name: string | null; role: string };
type DataRequest = {
  id: string; member_id: string; member_name: string; member_email: string;
  request_type: "access" | "export" | "correction" | "erasure"; status: "open" | "in_review" | "completed" | "rejected";
  note: string | null; resolution_note: string | null; created_at: string; resolved_at: string | null;
  erasure_redacted_at: string | null;
  review_checks: Partial<Record<ReviewItem, ReviewCheck>>;
};
type MemberConsent = { whatsapp: boolean; whatsapp_updated_at: string | null; member_id: string; email: boolean; email_updated_at: string | null; sms: boolean; sms_updated_at: string | null; in_app: boolean; in_app_updated_at: string | null };

const REVIEW_ITEMS = {
  identity: "Requester identity and authority",
  linked_records: "Linked records and attachments",
  processors: "External processors and recurring charges",
  retention_backups: "Retention reasons, expiry, and backups",
};
type ReviewItem = keyof typeof REVIEW_ITEMS;
type ReviewCheck = { outcome: "verified" | "not_applicable"; note: string; reviewed_by: string; reviewed_at: string };

function PrivacyReviewChecklist({ request, onSaved }: { request: DataRequest; onSaved: (updated: DataRequest) => void }) {
  const [item, setItem] = useState<ReviewItem>("identity");
  const [note, setNote] = useState(request.review_checks.identity?.note || "");
  const [outcome, setOutcome] = useState("verified");
  const [busy, setBusy] = useState(false);
  const retryKey = useRef("");
  const closed = request.status === "completed" || request.status === "rejected";
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    retryKey.current ||= crypto.randomUUID();
    try {
      const updated = await api.put<DataRequest>(`/privacy/data-requests/${request.id}/review`, {
        item, outcome, note: note.trim(),
      }, { "Idempotency-Key": retryKey.current });
      onSaved(updated); retryKey.current = ""; toast.success("Review evidence saved.");
    } catch (error) { toast.error((error as ApiError).message || "Could not save review evidence."); }
    finally { setBusy(false); }
  }
  return <details className="mt-3 rounded-md border border-border p-3">
    <summary className="cursor-pointer text-xs font-medium">Erasure review · {Object.keys(request.review_checks).length}/4 checks recorded</summary>
    <dl className="mt-3 space-y-3 text-xs">{Object.entries(REVIEW_ITEMS).map(([key, label]) => {
      const check = request.review_checks[key as ReviewItem];
      return <div key={key}><dt className="font-medium">{label} · {check ? check.outcome.replaceAll("_", " ") : "Pending"}</dt>
        {check && <dd className="mt-1 whitespace-pre-wrap break-words text-muted-foreground">{check.note}<span className="mt-1 block">Recorded {new Date(check.reviewed_at).toLocaleString()}</span></dd>}
      </div>;
    })}</dl>
    {!closed && <form onSubmit={(event) => void save(event)} className="mt-4 space-y-3">
      <p className="text-xs leading-5 text-muted-foreground">Record what you actually verified, reference numbers, retained categories and reasons, and review/expiry dates. Avoid passwords, tokens, or copies of identity documents. Provider and backup actions must be performed separately.</p>
      <Select label="Review item" disabled={busy} value={item} onChange={(event) => {
        const next = event.target.value as ReviewItem; setItem(next);
        setNote(request.review_checks[next]?.note || ""); setOutcome(request.review_checks[next]?.outcome || "verified"); retryKey.current = "";
      }}>{Object.entries(REVIEW_ITEMS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select>
      <Select label="Outcome" disabled={busy} value={outcome} onChange={(event) => { setOutcome(event.target.value); retryKey.current = ""; }}>
        <option value="verified">Verified / action completed</option>{item !== "identity" && <option value="not_applicable">Not applicable — explain why</option>}
      </Select>
      <label className="block text-xs font-medium">Evidence or review reference
        <textarea required minLength={10} maxLength={1000} rows={3} disabled={busy} value={note} onChange={(event) => { setNote(event.target.value); retryKey.current = ""; }} className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm" />
      </label>
      <Button type="submit" variant="secondary" disabled={busy || note.trim().length < 10} loading={busy}>Save review evidence</Button>
    </form>}
  </details>;
}

const REQUEST_LABEL: Record<DataRequest["request_type"], string> = {
  access: "Access", export: "Export", correction: "Correction", erasure: "Erasure",
};

export function DataRequestsSection({ onNavigate }: { onNavigate?: () => void }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [requests, setRequests] = useState<DataRequest[]>([]);
  const [memberId, setMemberId] = useState("");
  const [requestType, setRequestType] = useState<DataRequest["request_type"]>("access");
  const [note, setNote] = useState("");
  const [consent, setConsent] = useState<MemberConsent>({ whatsapp: false, whatsapp_updated_at: null, member_id: "", email: false, email_updated_at: null, sms: false, sms_updated_at: null, in_app: false, in_app_updated_at: null });
  const [consentBusy, setConsentBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const [memberRows, requestRows] = await Promise.all([
        api.get<Member[]>("/members?role=member"),
        api.get<DataRequest[]>("/privacy/data-requests"),
      ]);
      setMembers(memberRows);
      setRequests(requestRows);
      setMemberId((current) => current || memberRows[0]?.member_id || "");
    } catch (error) {
      toast.error((error as ApiError).message || "Could not load privacy requests.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { queueMicrotask(() => void refresh()); }, []);

  useEffect(() => {
    if (!memberId) return;
    queueMicrotask(() => {
      void api.get<MemberConsent>(`/privacy/members/${memberId}/consent`)
        .then(setConsent)
        .catch((error) => toast.error((error as ApiError).message || "Could not load communication consent."));
    });
  }, [memberId]);

  async function saveConsent() {
    setConsentBusy(true);
    try {
      const updated = await api.put<MemberConsent>(`/privacy/members/${memberId}/consent`, {
        email: consent.email, sms: consent.sms, whatsapp: consent.whatsapp, in_app: consent.in_app,
      }, { "Idempotency-Key": crypto.randomUUID() });
      setConsent(updated);
      toast.success("Communication permissions saved.");
    } catch (error) {
      toast.error((error as ApiError).message || "Could not save communication permissions.");
    } finally {
      setConsentBusy(false);
    }
  }

  async function createRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!memberId) return;
    setBusy("create");
    try {
      await api.post<DataRequest>("/privacy/data-requests", {
        member_id: memberId, request_type: requestType, note: note.trim() || null,
      }, { "Idempotency-Key": crypto.randomUUID() });
      setNote("");
      toast.success("Privacy request recorded.");
      await refresh();
    } catch (error) {
      toast.error((error as ApiError).message || "Could not record this request.");
    } finally {
      setBusy(null);
    }
  }

  async function decide(request: DataRequest, status: "in_review" | "completed" | "rejected") {
    if (request.request_type === "erasure" && status === "in_review" && !request.erasure_redacted_at && !window.confirm("Redact this member's workspace profile and revoke access now? Active renewals will stop. Payment and attendance records will remain.")) return;
    const resolutionNote = status === "in_review" ? null : window.prompt("Add a short note describing the action taken:");
    if (status !== "in_review" && !resolutionNote?.trim()) return;
    setBusy(request.id);
    try {
      await api.post(`/privacy/data-requests/${request.id}/decision`, {
        status, resolution_note: resolutionNote?.trim() || null,
      }, { "Idempotency-Key": crypto.randomUUID() });
      toast.success(status === "in_review" ? "Request moved to review." : "Request closed.");
      await refresh();
    } catch (error) {
      toast.error((error as ApiError).message || "Could not update this request.");
    } finally {
      setBusy(null);
    }
  }

  async function downloadExport(request: DataRequest) {
    setBusy(request.id);
    try {
      const data = await api.get<Record<string, unknown>>(`/privacy/members/${request.member_id}/export`);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `member-data-${request.member_id}.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success("Member export downloaded.");
    } catch (error) {
      toast.error((error as ApiError).message || "Could not export member data.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      <form onSubmit={(event) => void createRequest(event)} className="space-y-3 border-b border-border pb-5">
        <p className="text-sm text-muted-foreground">Record an access, export, correction, or erasure request received by your team. Lead email/SMS opt-in and STOP opt-out controls are available on each lead profile.</p>
        <Link href="/app/leads" onClick={onNavigate} className="inline-flex text-xs font-medium text-brand no-underline hover:underline">Manage lead communication consent →</Link>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1 text-xs text-muted-foreground">Member
            <Select size="sm" value={memberId} onChange={(event) => setMemberId(event.target.value)}>
              {members.map((member) => <option key={member.member_id} value={member.member_id}>{member.display_name || member.full_name || member.email} · {member.email}</option>)}
            </Select>
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">Request type
            <Select size="sm" value={requestType} onChange={(event) => setRequestType(event.target.value as DataRequest["request_type"])}>
              {Object.entries(REQUEST_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </Select>
          </label>
        </div>
        <label className="grid gap-1 text-xs text-muted-foreground">Staff note (optional)
          <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} rows={2} className="w-full resize-y border border-border bg-background px-3 py-2 text-sm text-foreground" placeholder="What did the member ask for?" />
        </label>
        <Button type="submit" disabled={!memberId || busy !== null} loading={busy === "create"}>Record request</Button>
      </form>

      <section className="space-y-3 border-b border-border pb-5">
        <div>
          <h3 className="text-sm font-semibold">Member communication consent</h3>
          <p className="mt-1 text-xs text-muted-foreground">Only enable a channel after the member explicitly opts in. Marketing campaigns skip members without consent.</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          {([
            ["email", "Marketing email"], ["sms", "Marketing SMS"], ["whatsapp", "Marketing WhatsApp"], ["in_app", "In-app promotions"],
          ] as const).map(([key, label]) => (
            <label key={key} className="flex min-h-10 items-center gap-2 border border-border px-3 text-xs">
              <input type="checkbox" checked={consent.member_id === memberId && consent[key]} disabled={consent.member_id !== memberId} onChange={(event) => setConsent((current) => ({ ...current, [key]: event.target.checked }))} />
              <span>{label}</span>
            </label>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">SMS and WhatsApp campaigns require their connected Twilio sender and separate opt-in permissions. STOP replies revoke consent for the channel used.</p>
        <Button variant="secondary" disabled={!memberId || consent.member_id !== memberId || consentBusy || busy !== null} loading={consentBusy} onClick={() => void saveConsent()}>Save permissions</Button>
      </section>

      <div>
        <h3 className="mb-1 text-sm font-semibold">Request log</h3>
        <p className="mb-3 text-xs text-muted-foreground">Erasure starts by redacting the workspace profile, revoking access, and stopping renewals. Review linked records, processors, backups, and retention rules before closing the request. Payment and attendance remain for accounting. Shared account identities are preserved for other workspaces. Verify requester authority before redaction and record all four reviews before closure.</p>
        {loading ? <p className="py-4 text-sm text-muted-foreground">Loading requests…</p> : requests.length ? (
          <ul className="divide-y divide-border">
            {requests.map((request) => <li key={request.id} className="py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{request.member_name} <span className="font-normal text-muted-foreground">· {REQUEST_LABEL[request.request_type]}</span></p>
                  <p className="text-xs text-muted-foreground">{request.member_email} · {new Date(request.created_at).toLocaleDateString()} · {request.status.replace("_", " ")}</p>
                  {request.note && <p className="mt-1 text-xs text-muted-foreground">{request.note}</p>}
                  {request.resolution_note && <p className="mt-1 text-xs text-muted-foreground">Resolution: {request.resolution_note}</p>}
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  {(request.request_type === "export" || request.request_type === "access") && <Button variant="secondary" disabled={busy !== null} onClick={() => void downloadExport(request)}>Download export</Button>}
                  {request.status === "open" && <Button variant="secondary" disabled={busy !== null || (request.request_type === "erasure" && request.review_checks.identity?.outcome !== "verified")} onClick={() => void decide(request, "in_review")}>{request.request_type === "erasure" ? "Begin erasure review" : "Start review"}</Button>}
                  {request.status !== "completed" && request.status !== "rejected" && <Button disabled={busy !== null || (request.request_type === "erasure" && (!request.erasure_redacted_at || Object.keys(REVIEW_ITEMS).some((item) => !request.review_checks[item as ReviewItem])))} onClick={() => void decide(request, "completed")}>Mark handled</Button>}
                  {request.status !== "completed" && request.status !== "rejected" && <Button variant="secondary" disabled={busy !== null} onClick={() => void decide(request, "rejected")}>Reject</Button>}
                </div>
              </div>
              {request.request_type === "erasure" && <PrivacyReviewChecklist request={request} onSaved={(updated) => setRequests((current) => current.map((row) => row.id === updated.id ? updated : row))} />}
            </li>)}
          </ul>
        ) : <p className="py-4 text-sm text-muted-foreground">No privacy requests recorded.</p>}
      </div>
    </div>
  );
}
