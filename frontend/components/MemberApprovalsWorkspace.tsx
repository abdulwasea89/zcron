"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Avatar, Button, EmptyState, Input, Spinner, TableToolbar, Textarea } from "@/components/ui";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { TABLE, THEAD_ROW, TH, TR, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { api, ApiError } from "@/lib/api";
import type { MemberDirectoryItem } from "@/lib/types";

export function MemberApprovalsWorkspace() {
  const [members, setMembers] = useState<MemberDirectoryItem[] | null>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [actingId, setActingId] = useState<string | null>(null);

  const [rejectTarget, setRejectTarget] = useState<MemberDirectoryItem | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  async function load() {
    setError("");
    try {
      const data = await api.get<MemberDirectoryItem[]>("/members/approval-queue");
      setMembers(data);
    } catch (e) {
      setError((e as ApiError).message);
      setMembers([]);
    }
  }

  useEffect(() => {
    queueMicrotask(() => void load());
  }, []);

  async function handleApprove(m: MemberDirectoryItem) {
    setActingId(m.member_id);
    setError("");
    setSuccess("");
    try {
      await api.post(`/members/${m.member_id}/approval`, { approve: true });
      setSuccess(`${m.display_name || m.full_name || m.email} approved.`);
      setMembers((prev) => (prev ?? []).filter((x) => x.member_id !== m.member_id));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setActingId(null);
    }
  }

  async function handleReject() {
    const m = rejectTarget;
    if (!m) return;
    setActingId(m.member_id);
    setError("");
    setSuccess("");
    try {
      await api.post(`/members/${m.member_id}/approval`, {
        approve: false,
        reason: rejectReason || null,
      });
      setSuccess(`${m.display_name || m.full_name || m.email} rejected.`);
      setMembers((prev) => (prev ?? []).filter((x) => x.member_id !== m.member_id));
      setRejectTarget(null);
      setRejectReason("");
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setActingId(null);
    }
  }

  function formatDate(iso: string): string {
    try {
      return new Date(iso + "Z").toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return iso;
    }
  }

  const filtered = (members ?? []).filter((m) => {
    const q = search.toLowerCase();
    if (!q) return true;
    const name = (m.display_name || m.full_name || "").toLowerCase();
    return name.includes(q) || m.email.toLowerCase().includes(q);
  });

  return (
    <>
      <PageHeader title="Approvals" subtitle="Review and approve new member applications" />

      {success && (
        <div className="mb-4">
          <Alert tone="success" onDismiss={() => setSuccess("")}>{success}</Alert>
        </div>
      )}
      {error && (
        <div className="mb-4">
          <Alert onDismiss={() => setError("")}>{error}</Alert>
        </div>
      )}

      <TableToolbar
        title="Pending approvals"
        subtitle={
          members
            ? `${members.length} member${members.length === 1 ? "" : "s"} awaiting decision`
            : undefined
        }
        action={
          <div className="flex items-center gap-1.5">
            <Input
              placeholder="Search…"
              aria-label="Search pending approvals"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              size="sm"
              className="w-[150px]"
            />
          </div>
        }
      />

      {/* Flat workspace, not a card: rows are held by hairlines. */}
      <div className="mt-3">
        {members === null ? (
          <Spinner label="Loading approval queue..." />
        ) : filtered.length === 0 ? (
          <EmptyState
            title={search ? "No results" : "No members awaiting approval"}
            hint={
              search
                ? "Try a different search term."
                : 'When you set enrollment mode to Approved in Settings, new signups will appear here for review.'
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className={TABLE}>
              <thead>
                <tr className={THEAD_ROW}>
                  <th className={`${TH} ${CELL_FIRST}`}>Name</th>
                  <th className={`${TH} ${CELL}`}>Phone</th>
                  <th className={`${TH} ${CELL}`}>Signed up</th>
                  <th className={`${TH} ${CELL_LAST} text-right`}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((m) => (
                  <tr key={m.member_id} className={`${TR} transition-colors hover:bg-foreground/[0.02]`}>
                    <td className={`${TD} ${CELL_FIRST} py-2.5`}>
                      <div className="flex items-center gap-3">
                        <Avatar name={m.display_name || m.full_name || m.email} size="sm" />
                        <div>
                          <div className="font-medium text-[var(--foreground)]">
                            {m.display_name || m.full_name || "—"}
                          </div>
                          <div className="text-xs text-[var(--foreground-muted)]">{m.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className={`${TD} ${CELL} py-2.5 text-[var(--foreground-muted)]`}>{m.phone || "—"}</td>
                    <td className={`${TD} ${CELL} py-2.5 text-[var(--foreground-muted)]`}>{formatDate(m.created_at)}</td>
                    <td className={`${TD} ${CELL_LAST} py-2.5`}>
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="primary"
                          disabled={actingId === m.member_id}
                          onClick={() => handleApprove(m)}
                        >
                          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                          Approve
                        </Button>
                        <Button
                          variant="danger"
                          disabled={actingId === m.member_id}
                          onClick={() => setRejectTarget(m)}
                        >
                          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                          </svg>
                          Reject
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Rejecting is destructive — it cancels an application and notifies the
          member — so it gets a centred AlertDialog: two answers, and it should
          stop you. The reason field rides inside it, since it is only ever
          needed here. Being a Radix AlertDialog, outside-press and Escape
          deliberately do nothing. */}
      <AlertDialog
        open={rejectTarget !== null}
        onOpenChange={(open) => { if (!open) { setRejectTarget(null); setRejectReason(""); } }}
      >
        <AlertDialogContent>
          <AlertDialogTitle>
            Reject {rejectTarget ? (rejectTarget.display_name || rejectTarget.full_name || rejectTarget.email) : ""}
          </AlertDialogTitle>
          <AlertDialogDescription>
            This member will be notified and their application cancelled.
          </AlertDialogDescription>
          <div className="mt-4">
            <Textarea
              label="Reason (optional)"
              placeholder="Why are you rejecting this application?"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={3}
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <Button variant="secondary" onClick={() => { setRejectTarget(null); setRejectReason(""); }}>
                Cancel
              </Button>
            </AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button variant="danger" onClick={handleReject}>
                Reject membership
              </Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
