"use client";

import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import { StaffPerformanceCard } from "@/components/StaffPerformanceCard";
import { Alert, Badge, Button, Card, EmptyState, Input, Spinner, TableToolbar } from "@/components/ui";
import { FieldSelect } from "@/components/FieldSelect";
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
import { api, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useRealtimeEvent } from "@/components/Realtime";
import type { StaffInviteOut, MemberDirectoryItem, ShiftOut, ClientAssignment, StaffScheduleOut } from "@/lib/types";

const STAFF_ROLES = ["manager", "trainer", "front_desk"];
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
type TrainerAvailability = { id: string; trainer_member_id: string; weekday: number; start_time: string; end_time: string };

/** Format a shift duration (ms) as HH:MM:SS. Pure, so it lives at module scope. */
function formatDuration(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export default function StaffPage() {
  const currentUser = useCurrentUser();
  const [members, setMembers] = useState<MemberDirectoryItem[] | null>(null);
  const [invites, setInvites] = useState<StaffInviteOut[]>([]);
  const [error, setError] = useState("");
  const [staffSearch, setStaffSearch] = useState("");
  const [staffRole, setStaffRole] = useState<"all" | "manager" | "trainer" | "front_desk">("all");
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteResult, setInviteResult] = useState<StaffInviteOut | null>(null);

  // Invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("manager");
  const [inviteFormError, setInviteFormError] = useState("");
  const [inviteLoading, setInviteLoading] = useState(false);

  // Kebab menu
  const [menuMember, setMenuMember] = useState<MemberDirectoryItem | null>(null);
  const [menuPos, setMenuPos] = useState<{ top?: number; bottom?: number; right: number } | null>(null);

  // Role change
  const [changingRole, setChangingRole] = useState<MemberDirectoryItem | null>(null);
  const [newRole, setNewRole] = useState("");
  const [roleChangeError, setRoleChangeError] = useState("");
  const [roleChangeLoading, setRoleChangeLoading] = useState(false);

  // Edit email
  const [editingEmail, setEditingEmail] = useState<MemberDirectoryItem | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [emailLoading, setEmailLoading] = useState(false);

  // Remove
  const [removing, setRemoving] = useState<MemberDirectoryItem | null>(null);
  const [removeError, setRemoveError] = useState("");
  const [removeLoading, setRemoveLoading] = useState(false);

  // Revoke invite
  const [revoking, setRevoking] = useState<StaffInviteOut | null>(null);
  const [revokeLoading, setRevokeLoading] = useState(false);

  // Invite kebab menu
  const [menuInvite, setMenuInvite] = useState<StaffInviteOut | null>(null);
  const [menuInvitePos, setMenuInvitePos] = useState<{ top?: number; bottom?: number; right: number } | null>(null);

  // Invite email edit
  const [editingInviteEmail, setEditingInviteEmail] = useState<StaffInviteOut | null>(null);
  const [inviteEmailValue, setInviteEmailValue] = useState("");
  const [inviteEmailError, setInviteEmailError] = useState("");
  const [inviteEmailLoading, setInviteEmailLoading] = useState(false);

  // Invite role change
  const [changingInviteRole, setChangingInviteRole] = useState<StaffInviteOut | null>(null);
  const [inviteRoleValue, setInviteRoleValue] = useState("");
  const [inviteRoleError, setInviteRoleError] = useState("");
  const [inviteRoleLoading, setInviteRoleLoading] = useState(false);

  // Shift check-in/out
  const [currentShift, setCurrentShift] = useState<ShiftOut | null>(null);
  const [shiftLoading, setShiftLoading] = useState(false);
  const [shiftError, setShiftError] = useState("");
  const [shiftErrorTimer, setShiftErrorTimer] = useState<ReturnType<typeof setTimeout> | null>(null);
  const [shiftTime, setShiftTime] = useState("");

  // Compensation
  const [compMember, setCompMember] = useState<MemberDirectoryItem | null>(null);
  const [compValues, setCompValues] = useState({ fixed_monthly_salary: 0, hourly_rate: 0, per_class_rate: 0, commission_rate: 0 });
  const [compLoading, setCompLoading] = useState(false);
  const [compError, setCompError] = useState("");

  // Trainer "my clients" view
  const [myClients, setMyClients] = useState<ClientAssignment[] | null>(null);
  const [schedule, setSchedule] = useState<StaffScheduleOut[]>([]);
  const [scheduleStaffId, setScheduleStaffId] = useState("");
  const [scheduleStarts, setScheduleStarts] = useState("");
  const [scheduleEnds, setScheduleEnds] = useState("");
  const [scheduleNote, setScheduleNote] = useState("");
  const [scheduleError, setScheduleError] = useState("");
  const [scheduleSaving, setScheduleSaving] = useState(false);
  const [availability, setAvailability] = useState<TrainerAvailability[]>([]);
  const [availabilityTrainerId, setAvailabilityTrainerId] = useState("");
  const [availabilityWeekday, setAvailabilityWeekday] = useState("0");
  const [availabilityStart, setAvailabilityStart] = useState("");
  const [availabilityEnd, setAvailabilityEnd] = useState("");
  const [availabilityError, setAvailabilityError] = useState("");
  const [availabilitySaving, setAvailabilitySaving] = useState(false);

  const isOwner = currentUser?.role === "owner";
  const canManageSchedule = isOwner || currentUser?.role === "manager";
  const isStaff = isOwner || currentUser?.role === "manager" || currentUser?.role === "trainer" || currentUser?.role === "front_desk";

  const load = useCallback(async () => {
    setError("");
    try {
      const m = await api.get<MemberDirectoryItem[]>("/members");
      setMembers(m);
    } catch (e) {
      setError((e as ApiError).message);
      setMembers([]);
    }
    try {
      const i = await api.get<StaffInviteOut[]>("/staff/invites");
      setInvites(i);
    } catch {
      // best-effort
    }
    if (canManageSchedule) {
      try { setSchedule(await api.get<StaffScheduleOut[]>("/staff/schedule")); } catch { /* best-effort */ }
      try { setAvailability(await api.get<TrainerAvailability[]>("/staff/availability")); } catch { /* best-effort */ }
    }
  }, [canManageSchedule]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  useRealtimeEvent(["staff.changed", "member.status_changed"], load);

  const loadShift = useCallback(async () => {
    try {
      const s = await api.get<ShiftOut | null>("/staff/shifts/current");
      setCurrentShift(s);
      if (s?.status === "checked_in") {
        const dur = Date.now() - new Date(s.checked_in_at + "Z").getTime();
        setShiftTime(formatDuration(dur));
      } else {
        setShiftTime("");
      }
    } catch {
      // best-effort
    }
  }, []);

  useEffect(() => {
    if (!isStaff) return;
    queueMicrotask(() => void loadShift());
  }, [loadShift, isStaff]);

  useEffect(() => {
    if (currentUser?.role !== "trainer") return;
    api.get<ClientAssignment[]>("/members/assigned-to-me")
      .then(setMyClients)
      .catch(() => setMyClients([]));
  }, [currentUser?.role]);

  useEffect(() => {
    if (!isStaff || currentShift?.status !== "checked_in") return;
    const interval = setInterval(() => {
      const dur = Date.now() - new Date(currentShift.checked_in_at + "Z").getTime();
      setShiftTime(formatDuration(dur));
    }, 1000);
    return () => clearInterval(interval);
  }, [isStaff, currentShift?.status, currentShift?.checked_in_at]);

  useRealtimeEvent(["shift.check_in", "shift.check_out"], loadShift);

  async function handleCheckIn() {
    setShiftLoading(true);
    setShiftError("");
    if (shiftErrorTimer) clearTimeout(shiftErrorTimer);
    try {
      const s = await api.post<ShiftOut>("/staff/shifts/check-in");
      setCurrentShift(s);
      setShiftTime("00:00:00");
    } catch (e) {
      const msg = (e as ApiError).message;
      setShiftError(msg);
      setShiftErrorTimer(setTimeout(() => setShiftError(""), 5000));
    } finally {
      setShiftLoading(false);
    }
  }

  async function handleCheckOut() {
    setShiftLoading(true);
    setShiftError("");
    if (shiftErrorTimer) clearTimeout(shiftErrorTimer);
    try {
      const s = await api.post<ShiftOut>("/staff/shifts/check-out");
      setCurrentShift(s);
      setShiftTime("");
    } catch (e) {
      const msg = (e as ApiError).message;
      setShiftError(msg);
      setShiftErrorTimer(setTimeout(() => setShiftError(""), 5000));
    } finally {
      setShiftLoading(false);
    }
  }

  const staff = (members ?? []).filter((m) => STAFF_ROLES.includes(m.role));
  const scheduleStaff = staff.filter((m) => m.member_status === "active");
  const scheduleTrainers = scheduleStaff.filter((m) => m.role === "trainer");
  const pendingInvites = invites.filter((i) => !i.used);

  async function createScheduledShift(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setScheduleError("");
    setScheduleSaving(true);
    try {
      await api.post<StaffScheduleOut>("/staff/schedule", {
        staff_member_id: scheduleStaffId,
        starts_at: new Date(scheduleStarts).toISOString(),
        ends_at: new Date(scheduleEnds).toISOString(),
        note: scheduleNote.trim() || undefined,
      });
      setScheduleStarts("");
      setScheduleEnds("");
      setScheduleNote("");
      await load();
    } catch (e) {
      setScheduleError((e as ApiError).message);
    } finally {
      setScheduleSaving(false);
    }
  }

  async function removeScheduledShift(shift: StaffScheduleOut) {
    setScheduleError("");
    try {
      await api.del(`/staff/schedule/${shift.id}`);
      await load();
    } catch (e) {
      setScheduleError((e as ApiError).message);
    }
  }

  async function createAvailability(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAvailabilityError("");
    setAvailabilitySaving(true);
    try {
      await api.post<TrainerAvailability>("/staff/availability", {
        trainer_member_id: availabilityTrainerId,
        weekday: Number(availabilityWeekday),
        start_time: availabilityStart,
        end_time: availabilityEnd,
      });
      setAvailabilityStart("");
      setAvailabilityEnd("");
      setAvailability(await api.get<TrainerAvailability[]>("/staff/availability"));
    } catch (error) {
      setAvailabilityError((error as ApiError).message || "Could not save trainer availability.");
    } finally {
      setAvailabilitySaving(false);
    }
  }

  async function removeAvailability(window: TrainerAvailability) {
    setAvailabilityError("");
    try {
      await api.del(`/staff/availability/${window.id}`);
      setAvailability((rows) => rows.filter((row) => row.id !== window.id));
    } catch (error) {
      setAvailabilityError((error as ApiError).message || "Could not remove availability.");
    }
  }

  const staffTabs = [
    { value: "all" as const, label: "All", count: staff.length },
    { value: "manager" as const, label: "Managers", count: staff.filter((s) => s.role === "manager").length },
    { value: "trainer" as const, label: "Trainers", count: staff.filter((s) => s.role === "trainer").length },
    { value: "front_desk" as const, label: "Front Desk", count: staff.filter((s) => s.role === "front_desk").length },
  ];

  const staffQuery = staffSearch.trim().toLowerCase();
  const filteredStaff = staff.filter((s) => {
    if (staffRole !== "all" && s.role !== staffRole) return false;
    if (!staffQuery) return true;
    return (
      (s.display_name || s.full_name || "").toLowerCase().includes(staffQuery) ||
      s.email.toLowerCase().includes(staffQuery)
    );
  });

  const closeMenu = useCallback(() => { setMenuMember(null); setMenuPos(null); }, []);
  const closeInviteMenu = useCallback(() => { setMenuInvite(null); setMenuInvitePos(null); }, []);

  const menuOpen = Boolean(menuMember || menuInvite);
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") { closeMenu(); closeInviteMenu(); } };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [menuOpen, closeMenu, closeInviteMenu]);

  function openMenu(member: MemberDirectoryItem, e: React.MouseEvent) {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const vh = window.innerHeight;
    const top = rect.bottom + 4;
    setMenuPos(top + 200 > vh
      ? { bottom: vh - rect.top + 4, right: document.documentElement.clientWidth - rect.right }
      : { top, right: document.documentElement.clientWidth - rect.right });
    setMenuMember(member);
  }

  function openInviteMenu(invite: StaffInviteOut, e: React.MouseEvent) {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const vh = window.innerHeight;
    const top = rect.bottom + 4;
    setMenuInvitePos(top + 200 > vh
      ? { bottom: vh - rect.top + 4, right: document.documentElement.clientWidth - rect.right }
      : { top, right: document.documentElement.clientWidth - rect.right });
    setMenuInvite(invite);
  }

  async function createInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviteFormError("");
    if (!inviteEmail.trim()) { setInviteFormError("Email is required."); return; }
    setInviteLoading(true);
    try {
      const result = await api.post<StaffInviteOut>("/staff/invites", {
        role: inviteRole,
        email: inviteEmail.trim(),
      });
      setInviteResult(result);
      setInviteEmail("");
      load();
    } catch (e) {
      setInviteFormError((e as ApiError).message);
    } finally {
      setInviteLoading(false);
    }
  }

  async function submitRoleChange() {
    if (!changingRole || !newRole) return;
    setRoleChangeError("");
    setRoleChangeLoading(true);
    try {
      await api.patch(`/members/${changingRole.member_id}/role`, { role: newRole });
      setChangingRole(null);
      setNewRole("");
      load();
    } catch (e) {
      setRoleChangeError((e as ApiError).message);
    } finally {
      setRoleChangeLoading(false);
    }
  }

  async function submitEmailChange() {
    if (!editingEmail || !newEmail.trim()) return;
    setEmailError("");
    setEmailLoading(true);
    try {
      await api.patch(`/members/${editingEmail.member_id}/email`, { email: newEmail.trim() });
      setEditingEmail(null);
      setNewEmail("");
      load();
    } catch (e) {
      setEmailError((e as ApiError).message);
    } finally {
      setEmailLoading(false);
    }
  }

  async function confirmRemove() {
    if (!removing) return;
    setRemoveError("");
    setRemoveLoading(true);
    try {
      await api.post(`/members/${removing.member_id}/status`, { action: "cancel" });
      setRemoving(null);
      load();
    } catch (e) {
      setRemoveError((e as ApiError).message);
    } finally {
      setRemoveLoading(false);
    }
  }

  async function confirmRevoke() {
    if (!revoking) return;
    setRevokeLoading(true);
    try {
      await api.del(`/staff/invites/${revoking.id}`);
      setRevoking(null);
      load();
    } catch {
      // best-effort
    } finally {
      setRevokeLoading(false);
    }
  }

  async function saveCompensation() {
    if (!compMember) return;
    setCompError("");
    setCompLoading(true);
    try {
      await api.patch(`/staff/${compMember.member_id}/compensation`, {
        fixed_monthly_salary: compValues.fixed_monthly_salary || 0,
        hourly_rate: compValues.hourly_rate || 0,
        per_class_rate: compValues.per_class_rate || 0,
        commission_rate: compValues.commission_rate || 0,
      });
      setCompMember(null);
      load();
    } catch (e) {
      setCompError((e as ApiError).message);
    } finally {
      setCompLoading(false);
    }
  }

  async function submitInviteEmailChange() {
    if (!editingInviteEmail || !inviteEmailValue.trim()) return;
    setInviteEmailError("");
    setInviteEmailLoading(true);
    try {
      await api.patch(`/staff/invites/${editingInviteEmail.id}/email`, { email: inviteEmailValue.trim() });
      setEditingInviteEmail(null);
      setInviteEmailValue("");
      load();
    } catch (e) {
      setInviteEmailError((e as ApiError).message);
    } finally {
      setInviteEmailLoading(false);
    }
  }

  async function submitInviteRoleChange() {
    if (!changingInviteRole || !inviteRoleValue) return;
    setInviteRoleError("");
    setInviteRoleLoading(true);
    try {
      await api.patch(`/staff/invites/${changingInviteRole.id}/role`, { role: inviteRoleValue });
      setChangingInviteRole(null);
      setInviteRoleValue("");
      load();
    } catch (e) {
      setInviteRoleError((e as ApiError).message);
    } finally {
      setInviteRoleLoading(false);
    }
  }

  function closeInviteResult() {
    setInviteResult(null);
    setShowInviteForm(false);
  }

  function maskCode(code: string): string {
    if (code.length <= 10) return code;
    return code.slice(0, 10) + "-••••";
  }

  const roleBadgeTone = (role: string): "info" | "success" | "neutral" | "warning" => {
    switch (role) {
      case "manager": return "info";
      case "trainer": return "success";
      case "front_desk": return "warning";
      default: return "neutral";
    }
  };

  const roleLabel = (role: string) =>
    role === "front_desk" ? "Front Desk" : role.charAt(0).toUpperCase() + role.slice(1);

  return (
    <>
      <PageHeader
        title="Staff"
        subtitle="Manage your team members and invites"
        action={
          <Button onClick={() => { setInviteResult(null); setShowInviteForm(true); }}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Invite staff
          </Button>
        }
      />

      {currentUser && ["owner", "manager"].includes(currentUser.role) && <StaffPerformanceCard />}
      {currentUser && ["owner", "manager"].includes(currentUser.role) && <Link href="/app/training" className="mb-5 inline-block text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground">Manage trainer session credits →</Link>}

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      {/* Inviting staff is a create task, so it gets a sheet: the directory stays
          in view while you fill it in. The generated code is the tail of the same
          task, so it shares the sheet rather than opening a second surface. */}
      <Sheet
        open={showInviteForm}
        onOpenChange={(open) => { if (!open) { setShowInviteForm(false); setInviteResult(null); } }}
      >
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div>
              <SheetTitle>{inviteResult ? "Invite created" : "Invite a staff member"}</SheetTitle>
              <SheetDescription>
                {inviteResult ? "Share this code with the staff member" : "Choose a role and enter their email"}
              </SheetDescription>
            </div>
          </SheetHeader>
          {inviteResult ? (
            <>
              <SheetBody className="space-y-4">
                <div className="rounded-lg border border-[var(--success-border)] bg-[var(--success-bg)] p-4 text-center">
                  <p className="mb-1 text-sm font-medium text-[var(--success)]">Invite code</p>
                  <p className="font-mono text-lg font-bold tracking-wider text-[var(--foreground)] select-all">{inviteResult.code}</p>
                </div>
                <p className="text-sm text-[var(--foreground-muted)]">
                  Share this code with the staff member. They can redeem it at <strong className="text-[var(--foreground)]">/redeem</strong> to create their account.
                </p>
              </SheetBody>
              <SheetFooter>
                <Button onClick={() => { navigator.clipboard.writeText(inviteResult.code); }}>Copy code</Button>
                <Button variant="secondary" onClick={closeInviteResult}>Done</Button>
              </SheetFooter>
            </>
          ) : (
            /* `flex` + the form filling the sheet: header and footer stay put,
               only the body scrolls. */
            <form onSubmit={createInvite} className="flex min-h-0 flex-1 flex-col">
              <SheetBody className="space-y-4">
                {inviteFormError && <Alert>{inviteFormError}</Alert>}
                <Input label="Email" type="email" required value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} placeholder="staff@example.com" />
                <FieldSelect label="Role" value={inviteRole} onChange={setInviteRole}>
                  <SelectItem value="manager">Manager</SelectItem>
                  <SelectItem value="trainer">Trainer</SelectItem>
                  <SelectItem value="front_desk">Front Desk</SelectItem>
                </FieldSelect>
              </SheetBody>
              <SheetFooter>
                <SheetClose asChild>
                  <Button type="button" variant="secondary">Cancel</Button>
                </SheetClose>
                <Button type="submit" loading={inviteLoading}>Generate invite</Button>
              </SheetFooter>
            </form>
          )}
        </SheetContent>
      </Sheet>

      {/* Editing a staff member's email is a form about the directory behind it,
          so it rides in a sheet rather than covering it. */}
      <Sheet open={!!editingEmail} onOpenChange={(open) => { if (!open) setEditingEmail(null); }}>
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <SheetTitle>Edit email</SheetTitle>
              <SheetDescription>
                {`Change email for ${editingEmail?.display_name || editingEmail?.full_name || editingEmail?.email}`}
              </SheetDescription>
            </div>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col">
            <SheetBody className="space-y-4">
              {emailError && <Alert>{emailError}</Alert>}
              <Input
                label="New email"
                type="email"
                required
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                placeholder="newemail@example.com"
              />
            </SheetBody>
            <SheetFooter>
              <SheetClose asChild>
                <Button variant="secondary">Cancel</Button>
              </SheetClose>
              <Button onClick={submitEmailChange} loading={emailLoading}>Save</Button>
            </SheetFooter>
          </div>
        </SheetContent>
      </Sheet>

      {/* Role changes edit the staff record, so they get a sheet. The role list
          is a Radix Select, because the in-house one portals its listbox to
          <body>, which a Radix dialog makes inert. */}
      <Sheet open={!!changingRole} onOpenChange={(open) => { if (!open) setChangingRole(null); }}>
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <SheetTitle>Change role</SheetTitle>
              <SheetDescription>
                {`Change role for ${changingRole?.display_name || changingRole?.full_name || changingRole?.email}`}
              </SheetDescription>
            </div>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col">
            <SheetBody className="space-y-4">
              {roleChangeError && <Alert>{roleChangeError}</Alert>}
              <FieldSelect label="New role" value={newRole || changingRole?.role || ""} onChange={setNewRole}>
                <SelectItem value="manager">Manager</SelectItem>
                <SelectItem value="trainer">Trainer</SelectItem>
                <SelectItem value="front_desk">Front Desk</SelectItem>
                <SelectItem value="member">Member</SelectItem>
              </FieldSelect>
              {newRole && newRole !== changingRole?.role && (
                <p className="text-xs text-[var(--warning)]">
                  {newRole === "member"
                    ? "This will remove all staff privileges."
                    : `This will grant ${roleLabel(newRole)} permissions.`
                  }
                </p>
              )}
            </SheetBody>
            <SheetFooter>
              <SheetClose asChild>
                <Button variant="secondary">Cancel</Button>
              </SheetClose>
              <Button onClick={submitRoleChange} loading={roleChangeLoading} variant={newRole === "member" ? "danger" : "primary"}>Save</Button>
            </SheetFooter>
          </div>
        </SheetContent>
      </Sheet>

      {/* Removing staff cancels their membership, so it gets a centred
          AlertDialog: two answers, and it should stop you. */}
      <AlertDialog open={!!removing} onOpenChange={(open) => { if (!open) setRemoving(null); }}>
        <AlertDialogContent>
          <AlertDialogTitle>Remove staff member</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to remove{" "}
            <strong className="text-foreground">
              {removing?.display_name || removing?.full_name || removing?.email}
            </strong>{" "}
            from staff? Their membership will be cancelled.
          </AlertDialogDescription>
          {removeError && <div className="mt-3"><Alert>{removeError}</Alert></div>}
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <Button variant="secondary">Keep staff</Button>
            </AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button variant="danger" onClick={confirmRemove} loading={removeLoading}>Remove</Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Staff directory */}
      <ListToolbar
        tabs={staffTabs}
        value={staffRole}
        onChange={setStaffRole}
        search={staffSearch}
        onSearch={(v) => setStaffSearch(v)}
        searchPlaceholder="Search staff…"
      />
      <div className="mt-3">
        {members === null ? (
          <Spinner label="Loading staff..." />
        ) : filteredStaff.length === 0 ? (
          <EmptyState
            title={staffQuery || staffRole !== "all" ? "No staff match" : "No staff yet"}
            hint={
              staffQuery || staffRole !== "all"
                ? "Try a different search or role filter."
                : "Invite managers, trainers, or front desk staff to help run your gym."
            }
            action={
              staffQuery || staffRole !== "all"
                ? undefined
                : <Button onClick={() => { setInviteResult(null); setShowInviteForm(true); }}>+ Invite staff</Button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className={TABLE}>
              <thead>
                <tr className={THEAD_ROW}>
                  <th className={`${TH} ${CELL_FIRST}`}>Name</th>
                  <th className={`${TH} ${CELL}`}>Email</th>
                  <th className={`${TH} ${CELL}`}>Role</th>
                  <th className={`${TH} ${CELL}`}>Status</th>
                  {isOwner && <th className={`${TH} ${CELL}`}>Rates</th>}
                  {isOwner && <th className={`${TH} ${CELL_LAST} w-12`} />}
                </tr>
              </thead>
              <tbody>
                {filteredStaff.map((s) => (
                  <tr key={s.member_id} className={`${TR} transition-colors hover:bg-[var(--background)]`}>
                    <td className={`${TD} ${CELL_FIRST} py-2.5`}>
                      <p className="font-medium text-[var(--foreground)]">{s.display_name || s.full_name || "—"}</p>
                    </td>
                    <td className={`${TD} ${CELL} py-2.5 text-[var(--foreground-muted)]`}>{s.email}</td>
                    <td className={`${TD} ${CELL} py-2.5`}>
                      <Badge tone={roleBadgeTone(s.role)}>{roleLabel(s.role)}</Badge>
                    </td>
                    <td className={`${TD} ${CELL} py-2.5`}>
                      <Badge tone={s.member_status === "active" ? "success" : "neutral"}>{s.member_status}</Badge>
                    </td>
                    {isOwner && (
                      <td className={`${TD} ${CELL} py-2.5 text-xs text-[var(--foreground-muted)]`}>
                        {["trainer", "front_desk", "manager"].includes(s.role) ? (
                          <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                            {(s.fixed_monthly_salary ?? 0) > 0 && <span>${s.fixed_monthly_salary}/mo</span>}
                            {(s.hourly_rate ?? 0) > 0 && <span>${s.hourly_rate}/hr</span>}
                            {(s.per_class_rate ?? 0) > 0 && <span>${s.per_class_rate}/class</span>}
                            {(s.commission_rate ?? 0) > 0 && <span>{(s.commission_rate ?? 0) * 100}% comm</span>}
                            {(s.fixed_monthly_salary ?? 0) === 0 && (s.hourly_rate ?? 0) === 0 && (s.per_class_rate ?? 0) === 0 && (s.commission_rate ?? 0) === 0 && (
                              <span className="text-[var(--muted)] italic">Not set</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-[var(--muted)]">—</span>
                        )}
                      </td>
                    )}
                    {isOwner && (
                      <td className={`${TD} ${CELL_LAST} py-2.5`}>
                        <div className="flex justify-end">
                          <button
                            type="button"
                            onClick={(e) => openMenu(s, e)}
                            className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--muted)] transition-colors hover:bg-[var(--background)] hover:text-[var(--foreground)]"
                          >
                            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                              <circle cx="12" cy="5" r="1.5" />
                              <circle cx="12" cy="12" r="1.5" />
                              <circle cx="12" cy="19" r="1.5" />
                            </svg>
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Kebab menu portal */}
      {menuMember && menuPos && createPortal(
        <>
          <div className="fixed inset-0 z-40" onClick={closeMenu} />
          <div
            className="fixed z-50 min-w-[160px] animate-pop-in overflow-hidden rounded-lg border border-[var(--border)] bg-popover p-1 shadow-lg shadow-black/10"
            style={{ top: menuPos.top, bottom: menuPos.bottom, right: menuPos.right }}
          >
            <button
              type="button"
              onClick={() => { closeMenu(); setChangingRole(menuMember); setNewRole(menuMember.role); setRoleChangeError(""); }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/[0.06]"
            >
              <svg className="h-3.5 w-3.5 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
              </svg>
              Change role
            </button>
            <button
              type="button"
              onClick={() => { closeMenu(); setEditingEmail(menuMember); setNewEmail(menuMember.email); setEmailError(""); }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/[0.06]"
            >
              <svg className="h-3.5 w-3.5 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
              </svg>
              Edit email
            </button>
            {["trainer", "front_desk", "manager"].includes(menuMember.role) && (
              <button
                type="button"
                onClick={() => {
                  closeMenu();
                  setCompMember(menuMember);
                  setCompValues({
                    fixed_monthly_salary: menuMember.fixed_monthly_salary || 0,
                    hourly_rate: menuMember.hourly_rate || 0,
                    per_class_rate: menuMember.per_class_rate || 0,
                    commission_rate: menuMember.commission_rate || 0,
                  });
                  setCompError("");
                }}
                className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/[0.06]"
              >
                <svg className="h-3.5 w-3.5 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Compensation
              </button>
            )}
            <hr className="border-t border-[var(--border)]" />
            <button
              type="button"
              onClick={() => { closeMenu(); setRemoving(menuMember); setRemoveError(""); }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-[var(--danger)] transition-colors hover:bg-danger-bg"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
              </svg>
              Remove
            </button>
          </div>
        </>,
        document.body,
      )}

      {/* Revoking kills the code outright, so it is a centred AlertDialog: two
          answers, and it should stop you. */}
      <AlertDialog open={!!revoking} onOpenChange={(open) => { if (!open) setRevoking(null); }}>
        <AlertDialogContent>
          <AlertDialogTitle>Revoke invite</AlertDialogTitle>
          <AlertDialogDescription>
            This invite for <strong className="text-foreground">{revoking?.email || "this person"}</strong> will
            be cancelled. The invite code will no longer work.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <Button variant="secondary">Keep invite</Button>
            </AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button variant="danger" onClick={confirmRevoke} loading={revokeLoading}>Revoke</Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Editing a pending invite is a form about the invites table behind it,
          so it rides in a sheet rather than covering it. */}
      <Sheet open={!!editingInviteEmail} onOpenChange={(open) => { if (!open) setEditingInviteEmail(null); }}>
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <SheetTitle>Edit invite email</SheetTitle>
              <SheetDescription>Change email for the pending invite</SheetDescription>
            </div>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col">
            <SheetBody className="space-y-4">
              {inviteEmailError && <Alert>{inviteEmailError}</Alert>}
              <Input
                label="New email"
                type="email"
                required
                value={inviteEmailValue}
                onChange={(e) => setInviteEmailValue(e.target.value)}
                placeholder="newemail@example.com"
              />
            </SheetBody>
            <SheetFooter>
              <SheetClose asChild>
                <Button variant="secondary">Cancel</Button>
              </SheetClose>
              <Button onClick={submitInviteEmailChange} loading={inviteEmailLoading}>Save</Button>
            </SheetFooter>
          </div>
        </SheetContent>
      </Sheet>

      {/* The pending invite's role is the same edit on the same table, so it opens
          the same surface beside it. Radix Select again, for the same reason. */}
      <Sheet open={!!changingInviteRole} onOpenChange={(open) => { if (!open) setChangingInviteRole(null); }}>
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <SheetTitle>Change invite role</SheetTitle>
              <SheetDescription>Change role for the pending invite</SheetDescription>
            </div>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col">
            <SheetBody className="space-y-4">
              {inviteRoleError && <Alert>{inviteRoleError}</Alert>}
              <FieldSelect label="New role" value={inviteRoleValue || "manager"} onChange={setInviteRoleValue}>
                <SelectItem value="manager">Manager</SelectItem>
                <SelectItem value="trainer">Trainer</SelectItem>
                <SelectItem value="front_desk">Front Desk</SelectItem>
              </FieldSelect>
            </SheetBody>
            <SheetFooter>
              <SheetClose asChild>
                <Button variant="secondary">Cancel</Button>
              </SheetClose>
              <Button onClick={submitInviteRoleChange} loading={inviteRoleLoading}>Save</Button>
            </SheetFooter>
          </div>
        </SheetContent>
      </Sheet>

      {/* Invite kebab menu portal */}
      {menuInvite && menuInvitePos && createPortal(
        <>
          <div className="fixed inset-0 z-40" onClick={closeInviteMenu} />
          <div
            className="fixed z-50 min-w-[160px] animate-pop-in overflow-hidden rounded-lg border border-[var(--border)] bg-popover p-1 shadow-lg shadow-black/10"
            style={{ top: menuInvitePos.top, bottom: menuInvitePos.bottom, right: menuInvitePos.right }}
          >
            <button
              type="button"
              onClick={() => { closeInviteMenu(); setEditingInviteEmail(menuInvite); setInviteEmailValue(menuInvite.email || ""); setInviteEmailError(""); }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/[0.06]"
            >
              <svg className="h-3.5 w-3.5 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
              </svg>
              Edit email
            </button>
            <button
              type="button"
              onClick={() => { closeInviteMenu(); setChangingInviteRole(menuInvite); setInviteRoleValue(menuInvite.role); setInviteRoleError(""); }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/[0.06]"
            >
              <svg className="h-3.5 w-3.5 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
              </svg>
              Change role
            </button>
            <button
              type="button"
              onClick={() => { closeInviteMenu(); navigator.clipboard.writeText(menuInvite.code); }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/[0.06]"
            >
              <svg className="h-3.5 w-3.5 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
              </svg>
              Copy code
            </button>
            <hr className="border-t border-[var(--border)]" />
            <button
              type="button"
              onClick={() => { closeInviteMenu(); setRevoking(menuInvite); }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-[var(--danger)] transition-colors hover:bg-danger-bg"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
              Revoke
            </button>
          </div>
        </>,
        document.body,
      )}

      {/* Shift check-in/out — only for operational staff */}
      {(["trainer", "front_desk", "manager"].includes(currentUser?.role ?? "")) && (
        <Card className={`mb-4 ${currentShift?.status === "checked_in" ? "border-[var(--success-border)]" : ""}`}>
          <div className={`flex items-center gap-4 p-5 ${currentShift?.status === "checked_in" ? "bg-[var(--success-bg)]" : ""}`}>
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${currentShift?.status === "checked_in" ? "bg-[var(--success)]" : "bg-[var(--border-strong)]"}`}>
              {currentShift?.status === "checked_in" ? (
                <svg className="h-5 w-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              ) : (
                <svg className="h-5 w-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9v6m3-3H9" />
                </svg>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className={`inline-block h-2 w-2 rounded-full ${currentShift?.status === "checked_in" ? "bg-[var(--success)] shadow-[0_0_6px_var(--success)]" : "bg-[var(--muted)]"}`} />
                <p className="font-medium text-[var(--foreground)]">
                  {currentShift?.status === "checked_in" ? "On shift" : "Off duty"}
                </p>
              </div>
              {currentShift?.status === "checked_in" ? (
                <p className="mt-1 font-mono text-2xl font-bold tracking-tight text-[var(--foreground)]">{shiftTime}</p>
              ) : (
                <p className="mt-0.5 text-sm text-[var(--foreground-muted)]">Not checked in today</p>
              )}
            </div>
            <div className="flex flex-col items-end gap-1">
              {currentShift?.status === "checked_in" ? (
                <>
                  <Button variant="danger" onClick={handleCheckOut} loading={shiftLoading} className="whitespace-nowrap">
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
                    </svg>
                    Check out
                  </Button>
                  <p className="text-xs text-[var(--foreground-muted)]">
                    Since {new Date(currentShift.checked_in_at + "Z").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </p>
                </>
              ) : (
                <Button onClick={handleCheckIn} loading={shiftLoading} className="whitespace-nowrap">
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
                  </svg>
                  Check in
                </Button>
              )}
            </div>
          </div>
          {shiftError && <div className="border-t border-[var(--border)] px-5 pb-4 pt-3"><Alert>{shiftError}</Alert></div>}
        </Card>
      )}

      {/* Planned shifts stay separate from recorded attendance hours. */}
      {canManageSchedule && <section className="mt-8 border border-border bg-background" aria-labelledby="schedule-title">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 id="schedule-title" className="text-sm font-semibold">Staff schedule</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">Plan shifts separately from clocked work hours.</p>
          </div>
          <span className="text-xs tabular-nums text-muted-foreground">{schedule.length} upcoming</span>
        </div>
        <form onSubmit={createScheduledShift} className="grid gap-3 border-b border-border p-4 sm:grid-cols-2 lg:grid-cols-5">
          <label className="block text-xs text-muted-foreground sm:col-span-2 lg:col-span-1">
            Staff member
            <select required value={scheduleStaffId} onChange={(event) => setScheduleStaffId(event.target.value)} className="mt-1 block h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground">
              <option value="">Choose staff…</option>
              {scheduleStaff.map((person) => <option key={person.member_id} value={person.member_id}>{person.display_name || person.full_name || person.email}</option>)}
            </select>
          </label>
          <Input label="Starts" type="datetime-local" required value={scheduleStarts} onChange={(event) => setScheduleStarts(event.target.value)} />
          <Input label="Ends" type="datetime-local" required value={scheduleEnds} onChange={(event) => setScheduleEnds(event.target.value)} />
          <Input label="Note (optional)" value={scheduleNote} maxLength={300} onChange={(event) => setScheduleNote(event.target.value)} placeholder="Front desk, opening…" />
          <div className="flex items-end"><Button type="submit" loading={scheduleSaving} disabled={!scheduleStaffId || !scheduleStarts || !scheduleEnds}>Add shift</Button></div>
          {scheduleError && <div className="sm:col-span-2 lg:col-span-5"><Alert>{scheduleError}</Alert></div>}
        </form>
        {schedule.length ? <div className="divide-y divide-border">
          {schedule.map((shift) => {
            const person = scheduleStaff.find((item) => item.member_id === shift.staff_member_id);
            return <div key={shift.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{person?.display_name || person?.full_name || person?.email || "Staff member"}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{new Date(shift.starts_at + (shift.starts_at.endsWith("Z") ? "" : "Z")).toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} – {new Date(shift.ends_at + (shift.ends_at.endsWith("Z") ? "" : "Z")).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}{shift.note ? ` · ${shift.note}` : ""}</p>
              </div>
              <Button variant="secondary" onClick={() => void removeScheduledShift(shift)} aria-label="Remove scheduled shift">Remove</Button>
            </div>;
          })}
        </div> : <p className="px-4 py-5 text-sm text-muted-foreground">No upcoming shifts have been planned.</p>}
      </section>}

      {canManageSchedule && <section className="mt-6 border border-border bg-background" aria-labelledby="availability-title">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 id="availability-title" className="text-sm font-semibold">Trainer availability</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">Set recurring weekly windows to help staff plan classes and sessions.</p>
          </div>
          <span className="text-xs tabular-nums text-muted-foreground">{availability.length} windows</span>
        </div>
        <form onSubmit={createAvailability} className="grid gap-3 border-b border-border p-4 sm:grid-cols-2 lg:grid-cols-5">
          <label className="block text-xs text-muted-foreground sm:col-span-2 lg:col-span-1">
            Trainer
            <select required value={availabilityTrainerId} onChange={(event) => setAvailabilityTrainerId(event.target.value)} className="mt-1 block h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground">
              <option value="">Choose trainer…</option>
              {scheduleTrainers.map((person) => <option key={person.member_id} value={person.member_id}>{person.display_name || person.full_name || person.email}</option>)}
            </select>
          </label>
          <label className="block text-xs text-muted-foreground">
            Day
            <select value={availabilityWeekday} onChange={(event) => setAvailabilityWeekday(event.target.value)} className="mt-1 block h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground">
              {WEEKDAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}
            </select>
          </label>
          <Input label="Available from" type="time" required value={availabilityStart} onChange={(event) => setAvailabilityStart(event.target.value)} />
          <Input label="Available until" type="time" required value={availabilityEnd} onChange={(event) => setAvailabilityEnd(event.target.value)} />
          <div className="flex items-end"><Button type="submit" loading={availabilitySaving} disabled={!availabilityTrainerId || !availabilityStart || !availabilityEnd}>Add window</Button></div>
          {availabilityError && <div className="sm:col-span-2 lg:col-span-5"><Alert>{availabilityError}</Alert></div>}
        </form>
        {availability.length ? <div className="divide-y divide-border">
          {availability.map((window) => {
            const trainer = scheduleTrainers.find((person) => person.member_id === window.trainer_member_id);
            return <div key={window.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{trainer?.display_name || trainer?.full_name || trainer?.email || "Trainer"}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{WEEKDAYS[window.weekday]} · {window.start_time.slice(0, 5)}–{window.end_time.slice(0, 5)}</p>
              </div>
              <Button variant="secondary" onClick={() => void removeAvailability(window)} aria-label="Remove trainer availability">Remove</Button>
            </div>;
          })}
        </div> : <p className="px-4 py-5 text-sm text-muted-foreground">No weekly availability has been entered.</p>}
      </section>}

      {/* Trainer: my clients */}
      {currentUser?.role === "trainer" && (
        <>
          <div id="my-clients">
          <TableToolbar
            title="My clients"
            subtitle={myClients ? `${myClients.length} member${myClients.length === 1 ? "" : "s"} assigned to you` : undefined}
          />
          <div className="mt-3">
            {myClients === null ? (
            <Spinner label="Loading your clients..." />
          ) : myClients.length === 0 ? (
            <EmptyState
              title="No clients yet"
              hint="The gym owner or a manager can assign members to you from the Members page."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className={TABLE}>
                <thead>
                  <tr className={THEAD_ROW}>
                    <th className={`${TH} ${CELL_FIRST}`}>Name</th>
                    <th className={`${TH} ${CELL}`}>Email</th>
                    <th className={`${TH} ${CELL_LAST}`}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {myClients.map((c) => (
                    <tr key={c.member_id} className={`${TR} transition-colors hover:bg-[var(--background)]`}>
                      <td className={`${TD} ${CELL_FIRST} py-2.5 font-medium text-[var(--foreground)]`}>{c.member_name || "—"}</td>
                      <td className={`${TD} ${CELL} py-2.5 text-[var(--foreground-muted)]`}>{c.member_email}</td>
                      <td className={`${TD} ${CELL_LAST} py-2.5`}>
                        <Badge tone={c.member_status === "active" ? "success" : c.member_status === "grace" ? "warning" : "neutral"}>{c.member_status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          </div>
          </div>
        </>
      )}

      {/* Compensation is four money fields in two two-up groups, so this is the one
          sheet that needs the wider panel. */}
      <Sheet open={!!compMember} onOpenChange={(open) => { if (!open) setCompMember(null); }}>
        <SheetContent className="[--sheet-max-w:520px]">
          <SheetHeader className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <SheetTitle>Compensation rates</SheetTitle>
              <SheetDescription>
                {`Set pay rates for ${compMember?.display_name || compMember?.full_name || compMember?.email}`}
              </SheetDescription>
            </div>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col">
            <SheetBody className="space-y-5">
              {compError && <Alert>{compError}</Alert>}

              <div>
                <p className="mb-3 text-[10px] font-semibold text-muted-foreground">Fixed pay</p>
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Monthly salary"
                    type="number"
                    min="0"
                    step="0.01"
                    value={compValues.fixed_monthly_salary || ""}
                    onChange={(e) => setCompValues({ ...compValues, fixed_monthly_salary: parseFloat(e.target.value) || 0 })}
                    prefix="$"
                  />
                  <Input
                    label="Hourly rate"
                    type="number"
                    min="0"
                    step="0.01"
                    value={compValues.hourly_rate || ""}
                    onChange={(e) => setCompValues({ ...compValues, hourly_rate: parseFloat(e.target.value) || 0 })}
                    prefix="$"
                    suffix="/hr"
                  />
                </div>
              </div>

              <hr className="border-[var(--border)]" />

              <div>
                <p className="mb-3 text-[10px] font-semibold text-muted-foreground">Variable pay</p>
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Per-class rate"
                    type="number"
                    min="0"
                    step="0.01"
                    value={compValues.per_class_rate || ""}
                    onChange={(e) => setCompValues({ ...compValues, per_class_rate: parseFloat(e.target.value) || 0 })}
                    prefix="$"
                    suffix="/class"
                  />
                  <Input
                    label="Commission rate"
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    value={compValues.commission_rate ? compValues.commission_rate * 100 : ""}
                    onChange={(e) => setCompValues({ ...compValues, commission_rate: (parseFloat(e.target.value) || 0) / 100 })}
                    suffix="%"
                  />
                </div>
              </div>

              <p className="flex items-center gap-1.5 text-xs text-[var(--foreground-muted)]">
                <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 16v-4M12 8h.01" />
                </svg>
                Commission is a percentage of revenue from referred members (strict 12-month window).
              </p>
            </SheetBody>
            <SheetFooter>
              <SheetClose asChild>
                <Button variant="secondary">Cancel</Button>
              </SheetClose>
              <Button onClick={saveCompensation} loading={compLoading}>Save changes</Button>
            </SheetFooter>
          </div>
        </SheetContent>
      </Sheet>

      {/* Pending invites (owner only) */}
      {isOwner && pendingInvites.length > 0 && (
        <>
          <TableToolbar
            title="Pending invites"
            subtitle={`${pendingInvites.length} unredeemed invite${pendingInvites.length === 1 ? "" : "s"}`}
          />
          <div className="mt-3">
            <div className="overflow-x-auto">
            <table className={TABLE}>
              <thead>
                <tr className={THEAD_ROW}>
                  <th className={`${TH} ${CELL_FIRST}`}>Email</th>
                  <th className={`${TH} ${CELL}`}>Role</th>
                  <th className={`${TH} ${CELL}`}>Code</th>
                  <th className={`${TH} ${CELL_LAST} w-24 text-right`}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {pendingInvites.map((inv) => (
                  <tr key={inv.id} className={`${TR} transition-colors hover:bg-[var(--background)]`}>
                    <td className={`${TD} ${CELL_FIRST} py-2.5 text-[var(--foreground-muted)]`}>{inv.email || "—"}</td>
                    <td className={`${TD} ${CELL} py-2.5`}><Badge tone={roleBadgeTone(inv.role)}>{roleLabel(inv.role)}</Badge></td>
                    <td className={`${TD} ${CELL} py-2.5`}>
                      <span className="font-mono text-xs text-[var(--muted)]" title={inv.code}>{maskCode(inv.code)}</span>
                    </td>
                    <td className={`${TD} ${CELL_LAST} py-2.5 text-right`}>
                      <button
                        type="button"
                        onClick={(e) => openInviteMenu(inv, e)}
                        className="ml-auto flex h-8 w-8 items-center justify-center rounded-full text-[var(--muted)] transition-colors hover:bg-[var(--background)] hover:text-[var(--foreground)]"
                      >
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                          <circle cx="12" cy="5" r="1.5" />
                          <circle cx="12" cy="12" r="1.5" />
                          <circle cx="12" cy="19" r="1.5" />
                        </svg>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}
