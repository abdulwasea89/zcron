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

interface FreezeRequest {
  id: string;
  member_id: string;
  member_name: string;
  member_email: string;
  reason: string;
  requested_until: string | null;
  source: "member" | "inbox";
  status: string;
  created_at: string;
  reviewed_at: string | null;
  decision_note: string | null;
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
  const [pauseRequests, setPauseRequests] = useState<FreezeRequest[]>([]);
  const [showPauseRequests, setShowPauseRequests] = useState(false);
  const [pauseDecisionBusy, setPauseDecisionBusy] = useState(false);
  const [tab, setTab] = useState<"all" | "approvals">("all");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState(NONE);
  const [roleFilter, setRoleFilter] = useState(NONE);
  const [trainerFilter, setTrainerFilter] = useState(NONE);
  const [joinedFilter, setJoinedFilter] = useState(NONE);
  const [profileFilter, setProfileFilter] = useState(NONE);
  const [contactFilter, setContactFilter] = useState(NONE);

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

  async function loadPauseRequests() {
    if (!canManage) return;
    try {
      setPauseRequests(await api.get<FreezeRequest[]>("/members/freeze-requests"));
    } catch (e) {
      setError((e as ApiError).message);
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

  useEffect(() => {
    if (canManage) queueMicrotask(() => void loadPauseRequests());
  }, [canManage]);

  async function decidePauseRequest(request: FreezeRequest, approve: boolean) {
    setPauseDecisionBusy(true);
    setError("");
    try {
      await api.post(`/members/freeze-requests/${request.id}/decision`, { approve });
      setInviteMsg(approve ? `Pause approved for ${request.member_name}.` : `Pause request declined for ${request.member_name}.`);
      await Promise.all([load(), loadPauseRequests()]);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setPauseDecisionBusy(false);
    }
  }

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

  const activeFilterCount = [
    tab === "all" ? statusFilter : NONE,
    roleFilter,
    trainerFilter,
    joinedFilter,
    profileFilter,
    contactFilter,
  ].filter((value) => value !== NONE).length;
  const filtered = ((tab === "approvals" ? pending : members ?? [])).filter((m) => {
    const q = query.trim().toLowerCase();
    const matchesSearch = !q || [
      m.email,
      m.display_name || m.full_name || "",
      m.phone || "",
      ...m.assigned_trainers,
    ].some((value) => value.toLowerCase().includes(q));
    const matchesStatus = statusFilter === NONE || m.member_status === statusFilter;
    const matchesRole = roleFilter === NONE || m.role === roleFilter;
    const hasTrainer = m.assigned_trainers.length > 0;
    const matchesTrainer = trainerFilter === NONE ||
      (trainerFilter === "__assigned__" ? hasTrainer : !hasTrainer);
    const ageDays = (Date.now() - new Date(m.created_at).getTime()) / 86_400_000;
    const matchesJoined = joinedFilter === NONE ||
      (joinedFilter === "30" ? ageDays <= 30 :
        joinedFilter === "90" ? ageDays <= 90 :
          joinedFilter === "365" ? ageDays <= 365 : ageDays > 365);
    const matchesProfile = profileFilter === NONE ||
      (profileFilter === "complete" ? m.profile_complete : !m.profile_complete);
    const matchesContact = contactFilter === NONE ||
      (contactFilter === "phone" ? Boolean(m.phone?.trim()) : !m.phone?.trim());
    return matchesSearch && matchesStatus && matchesRole && matchesTrainer && matchesJoined && matchesProfile && matchesContact;
  });

  function clearFilters() {
    setQuery("");
    setStatusFilter(tab === "approvals" ? "pending_approval" : NONE);
    setRoleFilter(NONE);
    setTrainerFilter(NONE);
    setJoinedFilter(NONE);
    setProfileFilter(NONE);
    setContactFilter(NONE);
  }

  return (
    <>
      <PageHeader
        title="Members"
        subtitle="Directory & status management"
        action={<div className="flex flex-wrap gap-2">
          {canManage && <Button variant="secondary" onClick={() => { setShowPauseRequests(true); void loadPauseRequests(); }}>
            Pause requests{pauseRequests.length > 0 ? ` · ${pauseRequests.length}` : ""}
          </Button>}
          <Button onClick={() => setInviteOpen(!showInvite)} >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7.5v3m0 0v3m0-3h3m-3 0h-3m-2.25-4.125a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zM4 19.235v-.11a6.375 6.375 0 0112.75 0v.109A12.318 12.318 0 0110.374 21c-2.331 0-4.512-.645-6.374-1.766z" /></svg>
            Invite member
          </Button>
        </div>}
      />

      <Sheet open={showPauseRequests} onOpenChange={setShowPauseRequests}>
        <SheetContent side="right" className="sm:max-w-[520px]">
          <SheetHeader>
            <SheetTitle>Membership pause requests</SheetTitle>
            <SheetDescription>Review member requests and inbox messages before pausing access.</SheetDescription>
          </SheetHeader>
          <SheetBody className="space-y-3">
            {pauseRequests.length === 0 ? (
              <EmptyState title="No requests waiting" hint="New member requests and detected inbox requests will appear here." />
            ) : pauseRequests.map((request) => (
              <article key={request.id} className="rounded-lg border border-[var(--border)] bg-background/40 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">{request.member_name}</h3>
                    <p className="text-xs text-muted-foreground">{request.member_email}</p>
                  </div>
                  <Badge tone={request.source === "inbox" ? "info" : "neutral"}>{request.source === "inbox" ? "Detected in inbox" : "Member request"}</Badge>
                </div>
                <p className="mt-3 text-sm text-foreground">{request.reason}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  Requested {new Date(request.created_at).toLocaleDateString()}
                  {request.requested_until ? ` · Until ${new Date(request.requested_until).toLocaleDateString()}` : " · No end date"}
                </p>
                <div className="mt-4 flex justify-end gap-2">
                  <Button type="button" variant="secondary" disabled={pauseDecisionBusy} onClick={() => void decidePauseRequest(request, false)}>Decline</Button>
                  <Button type="button" disabled={pauseDecisionBusy} onClick={() => void decidePauseRequest(request, true)}>Approve pause</Button>
                </div>
              </article>
            ))}
          </SheetBody>
          <SheetFooter>
            <SheetClose asChild><Button type="button" variant="secondary">Close</Button></SheetClose>
          </SheetFooter>
        </SheetContent>
      </Sheet>

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
        onChange={(nextTab) => {
          setTab(nextTab);
          setStatusFilter(nextTab === "approvals" ? "pending_approval" : NONE);
        }}
        search={query}
        onSearch={(v) => setQuery(v)}
        searchPlaceholder="Search members…"
        children={(
          <Button
            type="button"
            variant={filtersOpen || activeFilterCount > 0 ? "secondary" : "ghost"}
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen((open) => !open)}
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 7h9m4 0h3M4 17h3m4 0h9" />
              <circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" />
            </svg>
            Filters{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ""}
          </Button>
        )}
      />

      <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
        <SheetContent side="right" className="sm:max-w-[420px]">
          <SheetHeader>
            <div className="flex items-start justify-between gap-4">
              <div>
                <SheetTitle>Filter members</SheetTitle>
                <SheetDescription>Combine filters to find the members you need.</SheetDescription>
              </div>
              <SheetClose asChild>
                <button type="button" aria-label="Close filters" className="-mr-2 -mt-1 rounded-md p-2 text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand/60">
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="m18 6-12 12M6 6l12 12" /></svg>
                </button>
              </SheetClose>
            </div>
          </SheetHeader>

          <SheetBody className="space-y-5">
            <div className="flex items-center justify-between rounded-md border border-[var(--border)] bg-background/40 px-3 py-2.5">
              <span className="text-sm text-foreground">Matching members</span>
              <span className="text-sm font-semibold tabular-nums text-[var(--primary)]">{filtered.length}</span>
            </div>

            <FieldSelect
              label="Membership status"
              value={statusFilter}
              disabled={tab === "approvals"}
              onChange={setStatusFilter}
            >
              <SelectItem value={NONE}>All statuses</SelectItem>
              {[
                ["active", "Active"],
                ["pending_payment", "Pending payment"],
                ["pending_approval", "Pending approval"],
                ["pending_activation", "Pending activation"],
                ["grace", "Grace period"],
                ["expired", "Expired"],
                ["frozen", "Frozen"],
                ["cancelled", "Cancelled"],
                ["banned", "Banned"],
              ].map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
            </FieldSelect>

            <FieldSelect label="Role" value={roleFilter} onChange={setRoleFilter}>
              <SelectItem value={NONE}>All roles</SelectItem>
              {[
                ["member", "Member"],
                ["owner", "Owner"],
                ["manager", "Manager"],
                ["trainer", "Trainer"],
                ["front_desk", "Front desk"],
              ].map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
            </FieldSelect>

            <FieldSelect label="Trainer assignment" value={trainerFilter} onChange={setTrainerFilter}>
              <SelectItem value={NONE}>Any assignment</SelectItem>
              <SelectItem value="__assigned__">Has a trainer</SelectItem>
              <SelectItem value="__unassigned__">No trainer</SelectItem>
            </FieldSelect>

            <FieldSelect label="Joined" value={joinedFilter} onChange={setJoinedFilter}>
              <SelectItem value={NONE}>Any time</SelectItem>
              <SelectItem value="30">In the last 30 days</SelectItem>
              <SelectItem value="90">In the last 90 days</SelectItem>
              <SelectItem value="365">In the last year</SelectItem>
              <SelectItem value="older">More than a year ago</SelectItem>
            </FieldSelect>

            <FieldSelect label="Profile" value={profileFilter} onChange={setProfileFilter}>
              <SelectItem value={NONE}>Any profile</SelectItem>
              <SelectItem value="complete">Profile complete</SelectItem>
              <SelectItem value="incomplete">Profile incomplete</SelectItem>
            </FieldSelect>

            <FieldSelect label="Phone number" value={contactFilter} onChange={setContactFilter}>
              <SelectItem value={NONE}>Any phone status</SelectItem>
              <SelectItem value="phone">Has a phone number</SelectItem>
              <SelectItem value="no_phone">Missing phone number</SelectItem>
            </FieldSelect>
          </SheetBody>

          <SheetFooter className="justify-between">
            <span className="text-xs text-muted-foreground" aria-live="polite">
              {activeFilterCount ? `${activeFilterCount} active` : "No filters applied"}
            </span>
            <div className="flex items-center gap-2">
              <Button type="button" variant="ghost" onClick={clearFilters} disabled={activeFilterCount === 0}>Clear all</Button>
              <SheetClose asChild><Button type="button">Done</Button></SheetClose>
            </div>
          </SheetFooter>
        </SheetContent>
      </Sheet>

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
                : query || activeFilterCount > 0
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
