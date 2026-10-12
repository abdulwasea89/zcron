"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Avatar, Badge, Button, EmptyState, Input, Spinner } from "@/components/ui";
import { FieldSelect, NONE } from "@/components/FieldSelect";
import { SelectItem } from "@/components/ui/select";
import {
  Sheet,
  SheetBody,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ListToolbar } from "@/components/ListToolbar";
import { TABLE, THEAD_ROW, TH, TR, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { RowMenu, type RowAction } from "@/components/RowMenu";
import { MemberDetailSheet } from "@/components/members/MemberDetailSheet";
import { api, ApiError } from "@/lib/api";
import { statusTone, titleCase } from "@/lib/format";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import type { MemberDirectoryItem } from "@/lib/types";

interface InviteResult {
  member_id: string;
  email: string;
  invite_code: string;
  member_status: string;
  email_delivered: boolean;
}

function roleBadge(role: string) {
  switch (role) {
    case "owner":
      return <Badge tone="warning">Owner</Badge>;
    case "manager":
      return <Badge tone="success">Manager</Badge>;
    case "trainer":
      return <Badge tone="info">Trainer</Badge>;
    case "front_desk":
      return <Badge tone="neutral">Front Desk</Badge>;
    default:
      return null;
  }
}

export default function MembersPage() {
  const currentUser = useCurrentUser();
  const [members, setMembers] = useState<MemberDirectoryItem[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteMsg, setInviteMsg] = useState("");
  const [inviteShare, setInviteShare] = useState<{ email: string; code: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const [tab, setTab] = useState<"all" | "approvals">("all");

  // Member profile opens as a sheet over the directory. The id lives in the URL
  // (`?member=`) so the old /app/members/{id} deep links still resolve.
  const [openMemberId, setOpenMemberId] = useState<string | null>(null);

  function openMember(id: string) {
    setOpenMemberId(id);
    window.history.replaceState(null, "", `/app/members?member=${id}`);
  }
  function closeMember() {
    setOpenMemberId(null);
    window.history.replaceState(null, "", "/app/members");
  }

  function setInviteOpen(open: boolean) {
    setShowInvite(open);
    if (!open && new URLSearchParams(window.location.search).get("invite") === "1") {
      window.history.replaceState(null, "", "/app/members");
    }
  }

  // Delete member
  const [deletingMember, setDeletingMember] = useState<MemberDirectoryItem | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  // Assign trainer
  const [assigningMember, setAssigningMember] = useState<MemberDirectoryItem | null>(null);
  const [trainerChoice, setTrainerChoice] = useState("");
  const [assignError, setAssignError] = useState("");
  const [assignLoading, setAssignLoading] = useState(false);

  const isOwner = currentUser?.role === "owner";
  const canManage = isOwner || currentUser?.role === "manager";

  async function copyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked
    }
  }

  async function load() {
    setError("");
    try {
      setMembers(await api.get<MemberDirectoryItem[]>("/members"));
    } catch (e) {
      setError((e as ApiError).message);
      setMembers([]);
    }
  }

  useEffect(() => {
    queueMicrotask(() => void load());
    queueMicrotask(() => {
      const params = new URLSearchParams(window.location.search);
      const id = params.get("member");
      if (id) setOpenMemberId(id);
      if (params.get("invite") === "1") setShowInvite(true);
    });
  }, []);

  function handleInviteResult(res: InviteResult, email: string, sentVerb: string) {
    if (res.email_delivered) {
      setInviteMsg(`Invite ${sentVerb} to ${email}.`);
      setInviteShare(null);
    } else {
      setInviteMsg("");
      setInviteShare({ email, code: res.invite_code });
    }
  }

  async function act(id: string, action: string, endpoint?: string) {
    setError("");
    setInviteMsg("");
    setInviteShare(null);
    try {
      if (endpoint === "approval") {
        await api.post(`/members/${id}/approval`, { approve: action === "approve" });
      } else if (action === "resend_invite") {
        const res = await api.post<InviteResult>(`/members/${id}/resend-invite`);
        handleInviteResult(res, res.email, "re-sent");
      } else {
        await api.post(`/members/${id}/status`, { action });
      }
      await load();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setInviteMsg("");
    setInviteShare(null);
    try {
      const res = await api.post<InviteResult>("/members/invite", { email: inviteEmail });
      handleInviteResult(res, inviteEmail, "sent");
      setInviteEmail("");
      setInviteOpen(false);
      load();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function confirmDelete() {
    if (!deletingMember) return;
    setDeleteError("");
    setDeleteLoading(true);
    try {
      await api.del(`/members/${deletingMember.member_id}`);
      setDeletingMember(null);
      await load();
    } catch (e) {
      setDeleteError((e as ApiError).message);
    } finally {
      setDeleteLoading(false);
    }
  }

  const pending = (members ?? []).filter((m) => m.member_status === "pending_approval");

  const trainerOptions = (members ?? []).filter((m) => m.role === "trainer");

  async function assignTrainer() {
    if (!assigningMember || !trainerChoice) return;
    setAssignError("");
    setAssignLoading(true);
    try {
      await api.post(`/members/${assigningMember.member_id}/trainers`, {
        trainer_member_id: trainerChoice,
      });
      setAssigningMember(null);
      setTrainerChoice("");
      await load();
    } catch (e) {
      setAssignError((e as ApiError).message);
    } finally {
      setAssignLoading(false);
    }
  }

  async function unassignTrainer(member: MemberDirectoryItem, trainerName: string) {
    setError("");
    const trainer = trainerOptions.find((t) => (t.display_name || t.full_name || t.email) === trainerName);
    if (!trainer) return;
    try {
      await api.del(`/members/${member.member_id}/trainers/${trainer.member_id}`);
      await load();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  const filtered = ((tab === "approvals" ? pending : members ?? [])).filter((m) => {
    const q = query.toLowerCase();
    return !q || m.email.toLowerCase().includes(q) || (m.display_name || m.full_name || "").toLowerCase().includes(q);
  });

  return (
    <>
      <PageHeader
        title="Members"
        subtitle="Directory & status management"
        action={
          <Button onClick={() => setInviteOpen(!showInvite)} >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7.5v3m0 0v3m0-3h3m-3 0h-3m-2.25-4.125a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zM4 19.235v-.11a6.375 6.375 0 0112.75 0v.109A12.318 12.318 0 0110.374 21c-2.331 0-4.512-.645-6.374-1.766z" /></svg>
            Invite member
          </Button>
        }
      />

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {inviteMsg && (
        <div className="mb-4 animate-slide-down">
          <Alert tone="success">{inviteMsg}</Alert>
        </div>
      )}
      {inviteShare && (
        <div className="mb-4 animate-slide-down rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] shadow-xs p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-[var(--foreground)]">Invite code for {inviteShare.email}</div>
              <div className="mt-0.5 text-xs text-[var(--muted)]">
                The invite could not be emailed — share this single-use code with them.
              </div>
            </div>
            <button
              type="button"
              onClick={() => setInviteShare(null)}
              className="rounded-[var(--radius-sm)] p-1 text-[var(--muted)] hover:text-[var(--foreground)] hover:bg-[var(--background)] transition-colors"
              aria-label="Dismiss"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <code className="flex-1 overflow-x-auto whitespace-nowrap rounded-[var(--radius)] border border-[var(--border)] bg-[var(--background)] px-3 py-2.5 font-mono text-sm">
              {inviteShare.code}
            </code>
            <Button variant="secondary" onClick={() => copyCode(inviteShare.code)}>
              {copied ? (
                <>
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                  Copied
                </>
              ) : (
                <>
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H9.75" /></svg>
                  Copy
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      {/* Inviting is a create task, so it lives in a sheet: the directory stays in
          view while you type the address. Header and footer stay put, only the
          body scrolls. */}
      <Sheet open={showInvite} onOpenChange={setInviteOpen}>
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <SheetTitle>Invite a member</SheetTitle>
              <SheetDescription>Sends a single-use invite tied to their email</SheetDescription>
            </div>
          </SheetHeader>
          {/* `flex` + the form filling the sheet: header and footer stay put,
              only the body scrolls. */}
          <form onSubmit={invite} className="flex min-h-0 flex-1 flex-col">
            <SheetBody className="space-y-5">
              <Input
                label="Email"
                type="email"
                required
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="member@email.com"
              />
            </SheetBody>
            <SheetFooter>
              <SheetClose asChild>
                <Button type="button" variant="secondary">Cancel</Button>
              </SheetClose>
              <Button type="submit">
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" /></svg>
                Send invite
              </Button>
            </SheetFooter>
          </form>
        </SheetContent>
      </Sheet>

      {/* Deleting a member is destructive, so it gets a centred AlertDialog: two
          answers, and it should stop you. Being a Radix AlertDialog, outside-press
          and Escape deliberately do nothing. */}
      <AlertDialog
        open={!!deletingMember}
        onOpenChange={(open) => { if (!open) setDeletingMember(null); }}
      >
        <AlertDialogContent>
          <AlertDialogTitle>Delete member</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete{" "}
            <strong className="text-foreground">
              {deletingMember?.display_name || deletingMember?.full_name || deletingMember?.email}
            </strong>
            ? This will permanently remove them from the organization. This action cannot be undone.
          </AlertDialogDescription>
          {deleteError && <div className="mt-3"><Alert>{deleteError}</Alert></div>}
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <Button variant="secondary">Cancel</Button>
            </AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button variant="danger" onClick={confirmDelete} loading={deleteLoading}>Delete</Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Assigning a trainer edits a member, so it is a sheet too — and the
          trainer list is a Radix Select, because the in-house one portals its
          listbox to <body>, which a Radix dialog makes inert. */}
      <Sheet
        open={!!assigningMember}
        onOpenChange={(open) => { if (!open) setAssigningMember(null); }}
      >
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <SheetTitle>Assign a trainer</SheetTitle>
              <SheetDescription>
                {`Choose a trainer for ${assigningMember?.display_name || assigningMember?.full_name || assigningMember?.email}`}
              </SheetDescription>
            </div>
          </SheetHeader>
          {/* Same flex-column contract as the form above: only the body scrolls. */}
          <div className="flex min-h-0 flex-1 flex-col">
            <SheetBody className="space-y-4">
              {assignError && <Alert>{assignError}</Alert>}
              <FieldSelect
                label="Trainer"
                value={trainerChoice || NONE}
                onChange={(v) => setTrainerChoice(v === NONE ? "" : v)}
                disabled={trainerOptions.length === 0}
              >
                <SelectItem value={NONE}>
                  {trainerOptions.length === 0 ? "No trainers available" : "Select a trainer..."}
                </SelectItem>
                {trainerOptions.map((t) => (
                  <SelectItem key={t.member_id} value={t.member_id}>
                    {t.display_name || t.full_name || t.email}
                  </SelectItem>
                ))}
              </FieldSelect>
              <p className="flex items-center gap-1.5 text-xs text-[var(--foreground-muted)]">
                <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 16v-4M12 8h.01" />
                </svg>
                A member can have several trainers. Invite staff with the Trainer role to unlock this list.
              </p>
            </SheetBody>
            <SheetFooter>
              <SheetClose asChild>
                <Button variant="secondary">Cancel</Button>
              </SheetClose>
              <Button onClick={assignTrainer} loading={assignLoading} disabled={!trainerChoice}>Assign</Button>
            </SheetFooter>
          </div>
        </SheetContent>
      </Sheet>

      <ListToolbar
        tabs={[
          { value: "all" as const, label: "All", count: members?.length ?? 0 },
          { value: "approvals" as const, label: "Approvals", count: pending.length },
        ]}
        value={tab}
        onChange={setTab}
        search={query}
        onSearch={(v) => setQuery(v)}
        searchPlaceholder="Search members…"
      />

      {/* Flat workspace, not a card: rows are held by hairlines. */}
      <div className="mt-3">
        {members === null ? (
          <Spinner label="Loading members..." />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No members found"
            hint={
              tab === "approvals"
                ? "No members are waiting for approval."
                : query
                  ? "Try a different search."
                  : "Members appear here after they sign up."
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className={TABLE}>
              <thead>
                <tr className={THEAD_ROW}>
                  <th className={`${TH} ${CELL_FIRST}`}>Name</th>
                  <th className={`${TH} ${CELL}`}>Email</th>
                  <th className={`${TH} ${CELL}`}>Trainer</th>
                  <th className={`${TH} ${CELL}`}>Role</th>
                  <th className={`${TH} ${CELL}`}>Status</th>
                  <th className={`${TH} ${CELL_LAST} text-right`}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((m) => {
                  const isRowOwner = m.role === "owner";
                  const isRowSelf = m.member_id === currentUser?.member_id;
                  return (
                    <tr key={m.member_id} className={`${TR} transition-colors hover:bg-foreground/[0.02]`}>
                      <td className={`${TD} ${CELL_FIRST} py-2.5`}>
                        <div className="flex items-center gap-3">
                          <Avatar name={m.display_name || m.full_name || m.email} size="sm" photoUrl={m.photo_url} />
                          <div>
                            <div className="font-medium text-[var(--foreground)]">
                              <button
                                type="button"
                                onClick={() => openMember(m.member_id)}
                                className="cursor-pointer text-left transition-colors hover:text-[var(--primary)]"
                              >
                                {m.display_name || m.full_name || "—"}
                              </button>
                              {isRowSelf && <span className="ml-1.5 text-xs text-[var(--muted)]">(you)</span>}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className={`${TD} ${CELL} py-2.5 text-[var(--foreground-muted)]`}>{m.email}</td>
                      <td className={`${TD} ${CELL} py-2.5`}>
                        {m.assigned_trainers?.length ? (
                          <div className="flex flex-wrap gap-1.5">
                            {m.assigned_trainers.map((name) => (
                              <span key={name} className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--background)] px-2 py-0.5 text-xs text-[var(--foreground)]">
                                {name}
                                {canManage && !isRowSelf && !isRowOwner && (
                                  <button
                                    type="button"
                                    onClick={() => unassignTrainer(m, name)}
                                    aria-label={`Unassign ${name}`}
                                    className="text-[var(--muted)] transition-colors hover:text-[var(--danger)]"
                                  >
                                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M6 18L18 6M6 6l12 12" /></svg>
                                  </button>
                                )}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-[var(--muted)]">—</span>
                        )}
                      </td>
                      <td className={`${TD} ${CELL} py-2.5`}>{roleBadge(m.role)}</td>
                      <td className={`${TD} ${CELL} py-2.5`}>
                        <Badge tone={statusTone(m.member_status)}>{titleCase(m.member_status)}</Badge>
                      </td>
                      <td className={`${TD} ${CELL_LAST} py-2.5`}>
                        <div className="flex justify-end gap-2">
                          {canManage && !isRowSelf && !isRowOwner ? (
                            <RowMenu
                              actions={(() => {
                                const s = m.member_status;
                                const a: RowAction[] = [];
                                if (s === "pending_approval") {
                                  a.push({ label: "Approve", onSelect: () => act(m.member_id, "approve", "approval") });
                                  a.push({ label: "Reject", onSelect: () => act(m.member_id, "reject", "approval"), variant: "destructive" });
                                } else {
                                  if (s === "active" || s === "grace") {
                                    a.push({ label: "Assign trainer", onSelect: () => { setTrainerChoice(""); setAssignError(""); setAssigningMember(m); } });
                                    a.push({ label: "Freeze", onSelect: () => act(m.member_id, "freeze") });
                                    a.push({ label: "Ban", onSelect: () => act(m.member_id, "ban"), variant: "destructive" });
                                  }
                                  if (s === "frozen") {
                                    a.push({ label: "Unfreeze", onSelect: () => act(m.member_id, "unfreeze") });
                                  }
                                  if (s === "banned") {
                                    a.push({ label: "Unban", onSelect: () => act(m.member_id, "unban") });
                                  }
                                  if (s === "pending_activation" || s === "expired") {
                                    a.push({ label: "Resend invite", onSelect: () => act(m.member_id, "resend_invite") });
                                    a.push({ label: s === "expired" ? "Remove" : "Cancel", onSelect: () => act(m.member_id, "cancel"), variant: "destructive" });
                                  }
                                  if (s === "cancelled") {
                                    a.push({ label: "Resend invite", onSelect: () => act(m.member_id, "resend_invite") });
                                  }
                                  if (isOwner) {
                                    a.push({ label: "Delete member", onSelect: () => setDeletingMember(m), variant: "destructive" });
                                  }
                                }
                                return a;
                              })()}
                            />
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <MemberDetailSheet memberId={openMemberId} onClose={closeMember} />
    </>
  );
}
