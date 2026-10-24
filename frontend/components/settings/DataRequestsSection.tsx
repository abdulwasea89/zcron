"use client";

import { useEffect, useState, type FormEvent } from "react";
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
};

const REQUEST_LABEL: Record<DataRequest["request_type"], string> = {
  access: "Access", export: "Export", correction: "Correction", erasure: "Erasure",
};

export function DataRequestsSection({ onNavigate }: { onNavigate?: () => void }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [requests, setRequests] = useState<DataRequest[]>([]);
  const [memberId, setMemberId] = useState("");
  const [requestType, setRequestType] = useState<DataRequest["request_type"]>("access");
  const [note, setNote] = useState("");
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

      <div>
        <h3 className="mb-1 text-sm font-semibold">Request log</h3>
        <p className="mb-3 text-xs text-muted-foreground">Erasure starts by redacting the workspace profile, revoking access, and stopping renewals. Review linked records, processors, backups, and retention rules before closing the request. Payment and attendance remain for accounting; shared identities need manual review.</p>
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
                  {request.status === "open" && <Button variant="secondary" disabled={busy !== null} onClick={() => void decide(request, "in_review")}>{request.request_type === "erasure" ? "Begin erasure review" : "Start review"}</Button>}
                  {request.status !== "completed" && request.status !== "rejected" && <Button disabled={busy !== null} onClick={() => void decide(request, "completed")}>Mark handled</Button>}
                  {request.status !== "completed" && request.status !== "rejected" && <Button variant="secondary" disabled={busy !== null} onClick={() => void decide(request, "rejected")}>Reject</Button>}
                </div>
              </div>
            </li>)}
          </ul>
        ) : <p className="py-4 text-sm text-muted-foreground">No privacy requests recorded.</p>}
      </div>
    </div>
  );
}
