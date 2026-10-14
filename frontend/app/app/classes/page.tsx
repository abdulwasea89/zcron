"use client";

import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, EmptyState, Input, Spinner } from "@/components/ui";
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
import { ListFilterSheet } from "@/components/ListFilterSheet";
import { TABLE, THEAD_ROW, TH, TR, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { api, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useRealtimeEvent } from "@/components/Realtime";
import type { ClassSessionOut, ClassSessionCreate, MemberDirectoryItem, BookingWithMember } from "@/lib/types";

export default function ClassesPage() {
  const currentUser = useCurrentUser();
  const [sessions, setSessions] = useState<ClassSessionOut[] | null>(null);
  const [members, setMembers] = useState<MemberDirectoryItem[]>([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"upcoming" | "past" | "cancelled">("upcoming");
  const [search, setSearch] = useState("");
  const [trainerFilter, setTrainerFilter] = useState(NONE);
  const [capacityFilter, setCapacityFilter] = useState(NONE);
  const [showForm, setShowForm] = useState(false);
  const [cancelling, setCancelling] = useState<ClassSessionOut | null>(null);

  // Form state
  const [formTitle, setFormTitle] = useState("");
  const [formTrainer, setFormTrainer] = useState("");
  const [formStartsAt, setFormStartsAt] = useState("");
  const [formEndsAt, setFormEndsAt] = useState("");
  const [formCapacity, setFormCapacity] = useState("20");
  const [formError, setFormError] = useState("");
  const [formLoading, setFormLoading] = useState(false);

  // Bookings dialog
  const [bookingsSession, setBookingsSession] = useState<ClassSessionOut | null>(null);
  const [bookings, setBookings] = useState<BookingWithMember[] | null>(null);
  const [bookingsError, setBookingsError] = useState("");

  // Check-in
  const [checkInLoading, setCheckInLoading] = useState<string | null>(null);

  // Kebab menu
  const [menuSession, setMenuSession] = useState<ClassSessionOut | null>(null);
  const [menuPos, setMenuPos] = useState<{ top?: number; bottom?: number; right: number } | null>(null);

  const isStaff = currentUser?.role === "owner" || currentUser?.role === "manager" || currentUser?.role === "trainer";

  const load = useCallback(async () => {
    setError("");
    try {
      const c = await api.get<ClassSessionOut[]>("/classes");
      setSessions(c);
    } catch (e) {
      setError((e as ApiError).message);
      setSessions([]);
    }
    try {
      const m = await api.get<MemberDirectoryItem[]>("/members");
      setMembers(m);
    } catch {
      // best-effort for trainer names
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  useRealtimeEvent(["classes.changed"], load);

  const trainerById = Object.fromEntries(
    members.map((m) => [m.member_id, m.display_name || m.full_name || m.email]),
  );

  const trainers = members.filter((m) => m.role === "trainer" || m.role === "manager" || m.role === "owner");

  const now = new Date();
  const all = sessions ?? [];

  const inTab = (s: ClassSessionOut, tab: typeof filter) => {
    if (s.cancelled) return tab === "cancelled";
    if (tab === "cancelled") return false;
    const start = new Date(s.starts_at);
    return tab === "upcoming" ? start >= now : start < now;
  };

  const q = search.trim().toLowerCase();
  const filtered = all.filter((s) => {
    if (!inTab(s, filter)) return false;
    const trainer = s.trainer_member_id ? trainerById[s.trainer_member_id] ?? "" : "";
    const matchesSearch = !q || s.title.toLowerCase().includes(q) || trainer.toLowerCase().includes(q);
    const matchesTrainer = trainerFilter === NONE || (trainerFilter === "__unassigned__" ? !s.trainer_member_id : s.trainer_member_id === trainerFilter);
    const matchesCapacity = capacityFilter === NONE || (capacityFilter === "full" ? s.booked_count >= s.capacity : s.booked_count < s.capacity);
    return matchesSearch && matchesTrainer && matchesCapacity;
  });
  const activeClassFilterCount = [trainerFilter, capacityFilter].filter((v) => v !== NONE).length;
  function clearClassFilters() { setTrainerFilter(NONE); setCapacityFilter(NONE); }

  const tabs = [
    { value: "upcoming" as const, label: "Upcoming", count: all.filter((s) => inTab(s, "upcoming")).length },
    { value: "past" as const, label: "Past", count: all.filter((s) => inTab(s, "past")).length },
    { value: "cancelled" as const, label: "Cancelled", count: all.filter((s) => inTab(s, "cancelled")).length },
  ];

  function resetForm() {
    setFormTitle("");
    setFormTrainer("");
    setFormStartsAt("");
    setFormEndsAt("");
    setFormCapacity("20");
    setFormError("");
    setShowForm(false);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setFormError("");
    setFormLoading(true);
    try {
      const body: ClassSessionCreate = {
        title: formTitle,
        trainer_member_id: formTrainer || undefined,
        starts_at: new Date(formStartsAt).toISOString(),
        ends_at: formEndsAt ? new Date(formEndsAt).toISOString() : undefined,
        capacity: parseInt(formCapacity, 10) || 20,
      };
      await api.post("/classes", body);
      resetForm();
      load();
    } catch (e) {
      setFormError((e as ApiError).message);
    } finally {
      setFormLoading(false);
    }
  }

  async function confirmCancel() {
    if (!cancelling) return;
    setError("");
    try {
      await api.post(`/classes/${cancelling.id}/cancel`);
      setCancelling(null);
      load();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function doCheckIn(session: ClassSessionOut) {
    setCheckInLoading(session.id);
    setError("");
    try {
      await api.post(`/classes/${session.id}/check-in`);
      load();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setCheckInLoading(null);
    }
  }

  async function loadBookings(session: ClassSessionOut) {
    setBookingsSession(session);
    setBookings(null);
    setBookingsError("");
    try {
      const b = await api.get<BookingWithMember[]>(`/classes/${session.id}/bookings`);
      setBookings(b);
    } catch (e) {
      setBookingsError((e as ApiError).message);
    }
  }

  const closeMenu = useCallback(() => { setMenuSession(null); setMenuPos(null); }, []);

  function openMenu(session: ClassSessionOut, e: React.MouseEvent) {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const vh = window.innerHeight;
    const top = rect.bottom + 4;
    setMenuPos(top + 200 > vh
      ? { bottom: vh - rect.top + 4, right: document.documentElement.clientWidth - rect.right }
      : { top, right: document.documentElement.clientWidth - rect.right });
    setMenuSession(session);
  }

  const menuOpen = Boolean(menuSession);
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") closeMenu(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [menuOpen, closeMenu]);

  function fmtDateTime(iso: string) {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function fmtTime(iso: string) {
    return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  }

  function sessionStatus(s: ClassSessionOut): { label: string; tone: "info" | "success" | "neutral" | "warning" } {
    if (s.cancelled) return { label: "Cancelled", tone: "warning" };
    const start = new Date(s.starts_at);
    const end = s.ends_at ? new Date(s.ends_at) : null;
    if (start > now) return { label: "Upcoming", tone: "info" };
    if (end && end < now) return { label: "Done", tone: "neutral" };
    return { label: "Live", tone: "success" };
  }

  function capacityColor(booked: number, capacity: number): string {
    const ratio = booked / capacity;
    if (ratio >= 1) return "bg-[var(--danger)]";
    if (ratio >= 0.7) return "bg-[var(--warning)]";
    return "bg-[var(--success)]";
  }

  return (
    <>
      <PageHeader
        title="Classes"
        subtitle="Schedule and manage class sessions"
        action={
          <Button onClick={() => { resetForm(); setShowForm(true); }}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Schedule class
          </Button>
        }
      />

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      {/* Create lives in a sheet: it is about the class timetable below it, so the
          list stays in view while you fill the session in. */}
      <Sheet open={showForm} onOpenChange={resetForm}>
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div>
              <SheetTitle>Schedule a class</SheetTitle>
              <SheetDescription>Set up a new class session</SheetDescription>
            </div>
          </SheetHeader>
          {/* `flex` + the form filling the sheet: header and footer stay put,
              only the fields scroll. */}
          <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
            <SheetBody className="space-y-4">
              {formError && <Alert>{formError}</Alert>}
              <Input
                label="Class title"
                required
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
                placeholder="e.g. Morning HIIT"
              />
              <FieldSelect
                label="Trainer"
                value={formTrainer || NONE}
                onChange={(v) => setFormTrainer(v === NONE ? "" : v)}
              >
                <SelectItem value={NONE}>Unassigned</SelectItem>
                {trainers.map((t) => (
                  <SelectItem key={t.member_id} value={t.member_id}>
                    {t.display_name || t.full_name || t.email} ({t.role})
                  </SelectItem>
                ))}
              </FieldSelect>
              <div className="grid grid-cols-2 gap-3">
                <Input label="Starts at" type="datetime-local" required value={formStartsAt} onChange={(e) => setFormStartsAt(e.target.value)} />
                <Input label="Ends at" type="datetime-local" value={formEndsAt} onChange={(e) => setFormEndsAt(e.target.value)} />
              </div>
              <Input label="Capacity" type="number" min={1} value={formCapacity} onChange={(e) => setFormCapacity(e.target.value)} hint="Maximum number of members" />
            </SheetBody>
            <SheetFooter>
              <SheetClose asChild>
                <Button type="button" variant="secondary" onClick={resetForm}>Cancel</Button>
              </SheetClose>
              <Button type="submit" loading={formLoading}>Schedule</Button>
            </SheetFooter>
          </form>
        </SheetContent>
      </Sheet>

      {/* Cancelling is destructive and affects everyone booked in, so it gets a
          centred AlertDialog: two answers, and it should stop you. */}
      <AlertDialog open={!!cancelling} onOpenChange={(open) => { if (!open) setCancelling(null); }}>
        <AlertDialogContent>
          <AlertDialogTitle>Cancel class</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to cancel <strong className="text-foreground">{cancelling?.title}</strong>? All
            bookings will be cancelled and members will be notified.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <Button variant="secondary">Keep class</Button>
            </AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button variant="danger" onClick={confirmCancel}>Cancel class</Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bookings are a detail, so they read beside the timetable, not over it. */}
      <Sheet
        open={!!bookingsSession}
        onOpenChange={(open) => { if (!open) { setBookingsSession(null); setBookings(null); } }}
      >
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <SheetTitle>{bookingsSession ? `Bookings — ${bookingsSession.title}` : ""}</SheetTitle>
              <SheetDescription>
                {`${bookings?.length ?? 0} booking${bookings?.length === 1 ? "" : "s"}`}
              </SheetDescription>
            </div>
          </SheetHeader>
          <SheetBody>
            {bookings === null ? (
              <Spinner label="Loading bookings..." />
            ) : bookingsError ? (
              <Alert>{bookingsError}</Alert>
            ) : bookings.length === 0 ? (
              <p className="py-4 text-center text-sm text-[var(--foreground-muted)]">No bookings yet.</p>
            ) : (
              <div className="divide-y divide-[var(--border)]">
                {bookings.map((b) => (
                  <div key={b.booking_id} className="flex items-center justify-between py-2.5">
                    <div>
                      <p className="text-sm font-medium text-[var(--foreground)]">{b.member_name || b.member_email}</p>
                      <p className="text-xs text-[var(--muted)]">{b.member_email}</p>
                    </div>
                    <Badge tone={b.status === "booked" ? "success" : "neutral"}>{b.status}</Badge>
                  </div>
                ))}
              </div>
            )}
          </SheetBody>
          <SheetFooter>
            <SheetClose asChild>
              <Button type="button" variant="secondary">Close</Button>
            </SheetClose>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      {/* Kebab menu portal */}
      {menuSession && menuPos && createPortal(
        <>
          <div className="fixed inset-0 z-40" onClick={closeMenu} />
          <div
            className="fixed z-50 min-w-[160px] animate-pop-in overflow-hidden rounded-lg border border-[var(--border)] bg-popover p-1 shadow-lg shadow-black/10"
            style={{ top: menuPos.top, bottom: menuPos.bottom, right: menuPos.right }}
          >
            {!menuSession.cancelled && !menuSession.trainer_checked_in && (
              <button
                type="button"
                onClick={() => { closeMenu(); doCheckIn(menuSession); }}
                className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/[0.06]"
              >
                <svg className="h-3.5 w-3.5 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {checkInLoading === menuSession.id ? "Checking in..." : "Check in"}
              </button>
            )}
            <button
              type="button"
              onClick={() => { closeMenu(); loadBookings(menuSession); }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-foreground/[0.06]"
            >
              <svg className="h-3.5 w-3.5 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
              </svg>
              View bookings
            </button>
            {!menuSession.cancelled && (
              <>
                <hr className="border-t border-[var(--border)]" />
                <button
                  type="button"
                  onClick={() => { closeMenu(); setCancelling(menuSession); }}
                  className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[12px] text-[var(--danger)] transition-colors hover:bg-danger-bg"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                  </svg>
                  Cancel class
                </button>
              </>
            )}
          </div>
        </>,
        document.body,
      )}

      <ListToolbar
        tabs={tabs}
        value={filter}
        onChange={setFilter}
        search={search}
        onSearch={(v) => setSearch(v)}
        searchPlaceholder="Search classes…"
        children={(
          <ListFilterSheet title="Filter classes" description="Narrow sessions by trainer and available capacity." activeCount={activeClassFilterCount} resultCount={filtered.length} onClear={clearClassFilters}>
            <FieldSelect label="Trainer" value={trainerFilter} onChange={setTrainerFilter}>
              <SelectItem value={NONE}>Any trainer</SelectItem><SelectItem value="__unassigned__">Unassigned</SelectItem>
              {trainers.map((trainer) => <SelectItem key={trainer.member_id} value={trainer.member_id}>{trainer.display_name || trainer.full_name || trainer.email}</SelectItem>)}
            </FieldSelect>
            <FieldSelect label="Booking capacity" value={capacityFilter} onChange={setCapacityFilter}>
              <SelectItem value={NONE}>Any capacity</SelectItem><SelectItem value="available">Has open spots</SelectItem><SelectItem value="full">Fully booked</SelectItem>
            </FieldSelect>
          </ListFilterSheet>
        )}
      />

      {/* Flat workspace, not a card: rows are held by hairlines. */}
      <div className="mt-3">
        {sessions === null ? (
          <Spinner label="Loading classes..." />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No classes found"
            hint={
              filter === "upcoming"
                ? "Schedule your first class to get started."
                : filter === "past"
                  ? "No past classes yet."
                  : "No cancelled classes."
            }
            action={filter === "upcoming" ? <Button onClick={() => { resetForm(); setShowForm(true); }}>+ Schedule class</Button> : undefined}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className={TABLE}>
              <thead>
                <tr className={THEAD_ROW}>
                  <th className={`${TH} ${CELL_FIRST}`}>Class</th>
                  <th className={`${TH} ${CELL}`}>Trainer</th>
                  <th className={`${TH} ${CELL}`}>Date / Time</th>
                  <th className={`${TH} ${CELL}`}>Capacity</th>
                  <th className={`${TH} ${CELL}`}>Status</th>
                  {isStaff && <th className={`${TH} ${CELL_LAST} w-12`} />}
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => {
                  const st = sessionStatus(s);
                  return (
                    <tr
                      key={s.id}
                      className={`${TR} transition-colors hover:bg-foreground/[0.02] ${s.cancelled ? "opacity-50" : ""}`}
                    >
                      <td className={`${TD} ${CELL_FIRST} py-2.5 max-w-[200px]`}>
                        <p className={`truncate font-medium ${s.cancelled ? "text-[var(--muted)] line-through" : "text-[var(--foreground)]"}`}>
                          {s.title}
                        </p>
                      </td>
                      <td className={`${TD} ${CELL} py-2.5`}>
                        <span className="text-[var(--foreground-muted)]">
                          {s.trainer_member_id ? (trainerById[s.trainer_member_id] || "—") : "Unassigned"}
                        </span>
                      </td>
                      <td className={`${TD} ${CELL} py-2.5`}>
                        <div className="text-[var(--foreground-muted)]">
                          <p className="whitespace-nowrap">{fmtDateTime(s.starts_at)}</p>
                          {s.ends_at && (
                            <p className="text-xs text-[var(--muted)]">
                              until {fmtTime(s.ends_at)}
                            </p>
                          )}
                        </div>
                      </td>
                      <td className={`${TD} ${CELL} py-2.5`}>
                        <div className="flex items-center gap-2.5">
                          <div className="flex-1">
                            <div className="h-2 w-20 rounded-full bg-[var(--border)]">
                              <div
                                className={`h-2 rounded-full transition-all ${capacityColor(s.booked_count, s.capacity)}`}
                                style={{ width: `${Math.min(100, (s.booked_count / s.capacity) * 100)}%` }}
                              />
                            </div>
                          </div>
                          <span className="tabnum text-xs text-[var(--foreground-muted)]">
                            {s.booked_count}/{s.capacity}
                          </span>
                        </div>
                      </td>
                      <td className={`${TD} ${CELL} py-2.5`}>
                        <div className="flex items-center gap-2">
                          <Badge tone={st.tone}>{st.label}</Badge>
                          {!s.cancelled && s.trainer_checked_in && (
                            <span className="flex h-2 w-2 rounded-full bg-[var(--success)]" title="Trainer checked in" />
                          )}
                        </div>
                      </td>
                      {isStaff && (
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
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
