"use client";

import { useCallback, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Spinner,
  TableToolbar,
} from "@/components/ui";
import { Dialog } from "@/components/Dialog";
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
import { TABLE, THEAD_ROW, TH, TR, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { api, ApiError } from "@/lib/api";
import { MemberProfileCard } from "@/components/members/MemberProfileCard";
import { FamilyPlanCard } from "@/components/members/FamilyPlanCard";
import { money, statusTone, titleCase } from "@/lib/format";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import type { AttendanceOut, MemberDetailOut, MemberDirectoryItem, PendingPaymentItem } from "@/lib/types";

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

function pendingTone(kind: string) {
  return kind === "failed_attempt" ? ("danger" as const) : ("warning" as const);
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="font-mono text-[10px] font-medium uppercase tracking-widest text-[var(--muted-foreground)]">{label}</dt>
      <dd className="mt-1 text-sm text-[var(--foreground)]">{children}</dd>
    </div>
  );
}

function PendingList({ items }: { items: PendingPaymentItem[] }) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="No pending payments"
        hint="Nothing is owed and no payment is waiting to settle."
        icon={
          <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        }
      />
    );
  }
  return (
    <ul className="divide-y divide-[var(--border)]">
      {items.map((p) => (
        <li key={`${p.kind}-${p.payment_id ?? p.due_at ?? p.label}`} className="flex items-center gap-3 px-5 py-4">
          <Badge tone={pendingTone(p.kind)}>{titleCase(p.kind)}</Badge>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-[var(--foreground)]">{p.label}</p>
            <p className="text-xs text-[var(--muted)]">
              {p.due_at ? `Due ${new Date(p.due_at).toLocaleDateString()}` : "No due date set"}
            </p>
          </div>
          {p.amount != null && (
            <div className="text-right">
              <div className="text-sm font-semibold tabular-nums text-[var(--foreground)]">{money(p.amount, p.currency ?? "USD")}</div>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Summary strip cell: mono label + tabular value. */
function SummaryCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card px-4 py-3">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className="mt-1 truncate text-[15px] font-semibold tabular-nums text-foreground">{value}</p>
    </div>
  );
}

const METHOD_PATHS: Record<string, string> = {
  card:
    "M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z",
  cash:
    "M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  bank_transfer:
    "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z",
  mobile_wallet:
    "M7 3h10a1 1 0 011 1v16a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1zm5 14h.01M9 6h6",
};

function MethodCell({ method }: { method: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[var(--foreground-muted)]">
      <svg className="h-3.5 w-3.5 shrink-0 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={METHOD_PATHS[method] ?? METHOD_PATHS.mobile_wallet} />
      </svg>
      {titleCase(method)}
    </span>
  );
}

/** Compact relative time: "just now", "3h ago", "12d ago", then a short date. */
function ago(iso: string): string {
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso + "Z").getTime()) / 1000));
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso + "Z").toLocaleDateString([], { month: "short", day: "numeric" });
}

/**
 * MemberDetailSheet — a member's full profile as an edge sheet.
 *
 * Opened from the members directory (keeps the table in view) or by deep link.
 * `memberId` drives it: null = closed. Loads the same `/members/{id}` payload the
 * old standalone page did, plus visits. The assign-trainer flow nests as its own
 * sheet; the QR dialog rides on top.
 */
export function MemberDetailSheet({
  memberId,
  onClose,
}: {
  memberId: string | null;
  onClose: () => void;
}) {
  const currentUser = useCurrentUser();
  const [data, setData] = useState<MemberDetailOut | null>(null);
  const [error, setError] = useState("");
  const [visits, setVisits] = useState<AttendanceOut[] | null>(null);
  const [qrOpen, setQrOpen] = useState(false);

  // Assign trainer sheet
  const [assignOpen, setAssignOpen] = useState(false);
  const [trainerOptions, setTrainerOptions] = useState<MemberDirectoryItem[]>([]);
  const [trainerChoice, setTrainerChoice] = useState("");
  const [assignError, setAssignError] = useState("");
  const [assignLoading, setAssignLoading] = useState(false);

  const isOwner = currentUser?.role === "owner";
  const canManage = isOwner || currentUser?.role === "manager";

  const load = useCallback(async (id: string) => {
    setError("");
    setData(null);
    setVisits(null);
    try {
      setData(await api.get<MemberDetailOut>(`/members/${id}`));
    } catch (e) {
      setError((e as ApiError).message);
    }
  }, []);

  useEffect(() => {
    if (!memberId) return;
    queueMicrotask(() => void load(memberId));
    queueMicrotask(() => {
      api
        .get<AttendanceOut[]>(`/attendance/members/${memberId}/visits`)
        .then(setVisits)
        .catch(() => setVisits([]));
    });
  }, [memberId, load]);

  async function openAssign() {
    setAssignOpen(true);
    setTrainerChoice("");
    setAssignError("");
    try {
      setTrainerOptions(await api.get<MemberDirectoryItem[]>("/members?role=trainer"));
    } catch (e) {
      setAssignError((e as ApiError).message);
      setTrainerOptions([]);
    }
  }

  async function assignTrainer() {
    if (!trainerChoice || !memberId) return;
    setAssignError("");
    setAssignLoading(true);
    try {
      await api.post(`/members/${memberId}/trainers`, { trainer_member_id: trainerChoice });
      setAssignOpen(false);
      await load(memberId);
    } catch (e) {
      setAssignError((e as ApiError).message);
    } finally {
      setAssignLoading(false);
    }
  }

  async function unassignTrainer(trainerMemberId: string) {
    if (!memberId) return;
    setError("");
    try {
      await api.del(`/members/${memberId}/trainers/${trainerMemberId}`);
      await load(memberId);
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  const m = data?.member;
  const name = m ? m.display_name || m.full_name || m.email : "";
  const isStaff = m ? ["trainer", "front_desk", "manager", "owner"].includes(m.role) : false;
  const sub = data?.subscription;

  // Header summary numbers (lifetime collected excludes failed/pending attempts).
  const visitCount = visits?.length ?? 0;
  const collected = (data?.payments ?? [])
    .filter((p) => p.status === "succeeded" || p.status === "partially_refunded")
    .reduce((sum, p) => sum + (p.amount - p.refunded_amount), 0);
  const currency = sub?.currency ?? data?.payments?.[0]?.currency ?? "USD";

  return (
    <>
      <Sheet
        open={!!memberId}
        onOpenChange={(open) => {
          if (!open) {
            setQrOpen(false);
            setAssignOpen(false);
            onClose();
          }
        }}
      >
        <SheetContent style={{ "--sheet-max-w": "820px" } as React.CSSProperties}>
          <SheetHeader className="flex items-center gap-4 py-4">
            <Avatar name={name || "?"} size="lg" photoUrl={data?.profile.photo_url} />
            <div className="min-w-0 flex-1">
              <SheetTitle className="truncate text-[17px]">{name || "Member"}</SheetTitle>
              {m && (
                <SheetDescription className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="truncate">{m.email}</span>
                  <span aria-hidden className="text-foreground/20">·</span>
                  <span className="inline-flex items-center gap-1.5">
                    {roleBadge(m.role)}
                    <Badge tone={statusTone(m.member_status)} size="sm">{titleCase(m.member_status)}</Badge>
                  </span>
                </SheetDescription>
              )}
            </div>
            <SheetClose asChild>
              <button
                type="button"
                aria-label="Close"
                className="shrink-0 cursor-pointer rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </SheetClose>
          </SheetHeader>

          <SheetBody className="space-y-5">
            {error && <Alert>{error}</Alert>}
            {!data && !error && <Spinner label="Loading member…" />}

            {data && m && (
              <>
                {/* Summary strip: the four numbers you want before scrolling. */}
                <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-foreground/10 bg-foreground/10 sm:grid-cols-4">
                  <SummaryCell label="Membership" value={titleCase(m.member_status)} />
                  <SummaryCell label="Plan" value={sub?.plan_name ?? "No plan"} />
                  <SummaryCell label="Visits" value={String(visitCount)} />
                  <SummaryCell label="Lifetime paid" value={money(collected, currency)} />
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  {/* Member details */}
                  <Card>
                    <CardHeader title="Member details" subtitle="Profile and contact information" />
                    <div className="flex items-center gap-3 px-5 pt-5">
                      <Avatar name={name} size="lg" photoUrl={data.profile.photo_url} />
                      <div className="min-w-0">
                        <p className="font-medium text-[var(--foreground)]">{name}</p>
                        <p className="text-xs text-[var(--muted)]">
                          {m.profile_complete ? "Profile complete" : "Profile incomplete"}
                        </p>
                      </div>
                    </div>
                    <dl className="grid gap-4 px-5 py-5 sm:grid-cols-2">
                      <Field label="Email">{m.email}</Field>
                      <Field label="Phone">{m.phone || "—"}</Field>
                      <Field label="Role">{titleCase(m.role)}</Field>
                      <Field label="Status"><Badge tone={statusTone(m.member_status)}>{titleCase(m.member_status)}</Badge></Field>
                      <Field label="Trainers">
                        {m.role === "member" ? (
                          <div className="flex flex-wrap items-center gap-1.5">
                            {data.trainer_assignments.length ? (
                              data.trainer_assignments.map((t) => (
                                <span key={t.trainer_member_id} className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--background)] px-2 py-0.5 text-xs text-[var(--foreground)]">
                                  {t.trainer_name}
                                  {canManage && (
                                    <button
                                      type="button"
                                      onClick={() => unassignTrainer(t.trainer_member_id)}
                                      aria-label={`Unassign ${t.trainer_name}`}
                                      className="text-[var(--muted)] transition-colors hover:text-[var(--danger)]"
                                    >
                                      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M6 18L18 6M6 6l12 12" /></svg>
                                    </button>
                                  )}
                                </span>
                              ))
                            ) : (
                              <span className="text-[var(--muted)]">—</span>
                            )}
                            {canManage && (
                              <Button variant="secondary" onClick={() => openAssign()}>
                                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 4.5v15m7.5-7.5h-15" /></svg>
                                Assign trainer
                              </Button>
                            )}
                          </div>
                        ) : (
                          "—"
                        )}
                      </Field>
                      <Field label="Joined">{new Date(m.created_at).toLocaleDateString()}</Field>
                      {isStaff && (
                        <>
                          <Field label="Fixed salary">
                            {m.fixed_monthly_salary > 0 ? money(m.fixed_monthly_salary) : "—"}
                          </Field>
                          <Field label="Hourly rate">
                            {m.hourly_rate > 0 ? money(m.hourly_rate) : "—"}
                          </Field>
                          <Field label="Per class">
                            {m.per_class_rate > 0 ? money(m.per_class_rate) : "—"}
                          </Field>
                          <Field label="Commission">
                            {m.commission_rate > 0 ? `${(m.commission_rate * 100).toFixed(0)}%` : "—"}
                          </Field>
                        </>
                      )}
                    </dl>
                  </Card>

                  {/* Current plan */}
                  <Card>
                    <CardHeader title="Current plan" subtitle="Active subscription and plan details" />
                    {!sub ? (
                      <EmptyState
                        title="No plan yet"
                        hint="This member hasn't subscribed to a plan."
                        icon={
                          <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg>
                        }
                      />
                    ) : (
                      <>
                        <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5">
                          <div>
                            <p className="font-heading text-xl text-[var(--foreground)]">{sub.plan_name}</p>
                            <p className="text-xs text-[var(--muted)]">{titleCase(sub.billing_type)} plan</p>
                          </div>
                          <div className="text-right">
                            <p className="font-heading text-2xl tabular-nums text-[var(--foreground)]">{money(sub.price_snapshot, sub.currency)}</p>
                            <p className="text-xs text-[var(--muted)]">per {sub.billing_type === "one_time_pack" ? "pack" : "cycle"}</p>
                          </div>
                        </div>
                        <dl className="grid gap-4 px-5 py-5 sm:grid-cols-2">
                          <Field label="Subscription status"><Badge tone={statusTone(sub.status)}>{titleCase(sub.status)}</Badge></Field>
                          <Field label="Started">{new Date(sub.started_at).toLocaleDateString()}</Field>
                          {sub.current_period_end && (
                            <Field label="Valid until">{new Date(sub.current_period_end).toLocaleDateString()}</Field>
                          )}
                          {sub.classes_remaining != null && (
                            <Field label="Visit credits">{sub.classes_remaining}{sub.credits_allowance ? ` of ${sub.credits_allowance} left` : " left"}</Field>
                          )}
                          {data.family_owner && <Field label="Family plan payer">{data.family_owner.name}</Field>}
                          {sub.grace_until && (
                            <Field label="Grace until">{new Date(sub.grace_until).toLocaleDateString()}</Field>
                          )}
                          {sub.cancelled_at && (
                            <Field label="Cancelled">{new Date(sub.cancelled_at).toLocaleDateString()}</Field>
                          )}
                        </dl>
                      </>
                    )}
                  </Card>
                </div>

                <MemberProfileCard
                  key={m.member_id}
                  memberId={m.member_id}
                  profile={data.profile}
                  canManage={canManage}
                  onSaved={() => load(m.member_id)}
                />
                <FamilyPlanCard detail={data} canManage={canManage} onSaved={() => load(m.member_id)} />

                {/* Visits (#18) */}
                <Card>
                  <CardHeader
                    title="Visits"
                    subtitle={
                      visits === null
                        ? "Loading…"
                        : visits.length === 0
                          ? "No visits yet"
                          : `${visits.length} recent check-in${visits.length === 1 ? "" : "s"} · last here ${new Date(visits[0].checked_in_at + "Z").toLocaleDateString()}`
                    }
                    action={
                      m.role === "member" ? (
                        <Button variant="secondary" onClick={() => setQrOpen(true)}>
                          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M3 7V5a2 2 0 012-2h2M17 3h2a2 2 0 012 2v2M21 17v2a2 2 0 01-2 2h-2M7 21H5a2 2 0 01-2-2v-2M7 12h10" />
                          </svg>
                          Show QR
                        </Button>
                      ) : undefined
                    }
                  />
                  {visits === null ? (
                    <div className="p-5">
                      <Spinner label="Loading visits..." />
                    </div>
                  ) : visits.length === 0 ? (
                    <EmptyState
                      title="No visits yet"
                      hint="Check this member in from the Check-in page; visits will appear here."
                    />
                  ) : (
                    <div className="overflow-x-auto px-5 pb-4 pt-4">
                      <table className={TABLE}>
                        <thead>
                          <tr className={THEAD_ROW}>
                            <th className={`${TH} ${CELL_FIRST}`}>Date</th>
                            <th className={`${TH} ${CELL}`}>Time</th>
                            <th className={`${TH} ${CELL}`}>Method</th>
                            <th className={`${TH} ${CELL_LAST} text-right`}>Ago</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visits.slice(0, 8).map((v) => (
                            <tr key={v.id} className={`${TR} transition-colors hover:bg-foreground/[0.02]`}>
                              <td className={`${TD} ${CELL_FIRST} py-2.5 whitespace-nowrap tabular-nums`}>
                                {new Date(v.checked_in_at + "Z").toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })}
                              </td>
                              <td className={`${TD} ${CELL} py-2.5 whitespace-nowrap tabular-nums text-[var(--foreground-muted)]`}>
                                {new Date(v.checked_in_at + "Z").toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                              </td>
                              <td className={`${TD} ${CELL} py-2.5`}>
                                <Badge tone="neutral" size="sm">{titleCase(v.method)}</Badge>
                              </td>
                              <td className={`${TD} ${CELL_LAST} py-2.5 text-right text-[12px] text-[var(--foreground-muted)]`}>
                                {ago(v.checked_in_at)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {visits.length > 8 && (
                        <p className="pt-3 text-center text-[12px] text-muted-foreground">
                          Showing the latest 8 of {visits.length} visits.
                        </p>
                      )}
                    </div>
                  )}
                </Card>

                {/* Pending payments */}
                <Card>
                  <CardHeader title="Pending payments" subtitle="Amounts owed and unsettled attempts" />
                  <PendingList items={data.pending_payments} />
                </Card>

                {/* Payment history */}
                <div>
                  <TableToolbar
                    title="Payment history"
                    subtitle={
                      data.payments.length
                        ? `${data.payments.length} payment${data.payments.length === 1 ? "" : "s"} · ${money(collected, currency)} collected`
                        : "No payments yet"
                    }
                  />
                  {data.payments.length === 0 ? (
                    <EmptyState
                      title="No payments yet"
                      hint="Payments will appear here once this member pays."
                      icon={
                        <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75a.75.75 0 01-.75.75h-3m-2.25 0h.75c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125H3.75m0 0a1.5 1.5 0 01-1.5-1.5V15a1.5 1.5 0 011.5-1.5h1.5M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" /></svg>
                      }
                    />
                  ) : (
                    <div className="overflow-x-auto">
                      <table className={TABLE}>
                        <thead>
                          <tr className={THEAD_ROW}>
                            <th className={`${TH} ${CELL_FIRST}`}>Date</th>
                            <th className={`${TH} ${CELL}`}>Method</th>
                            <th className={`${TH} ${CELL} text-right`}>Amount</th>
                            <th className={`${TH} ${CELL} text-right`}>Refunded</th>
                            <th className={`${TH} ${CELL_LAST}`}>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.payments.map((p) => (
                            <tr key={p.id} className={`${TR} transition-colors hover:bg-foreground/[0.02]`}>
                              <td className={`${TD} ${CELL_FIRST} py-2.5 whitespace-nowrap tabular-nums`}>{(p.paid_at || p.created_at).slice(0, 10)}</td>
                              <td className={`${TD} ${CELL} py-2.5`}><MethodCell method={p.method} /></td>
                              <td className={`${TD} ${CELL} py-2.5 text-right tabular-nums font-medium text-[var(--foreground)]`}>{money(p.amount, p.currency)}</td>
                              <td className={`${TD} ${CELL} py-2.5 text-right tabular-nums text-[var(--foreground-muted)]`}>
                                {p.refunded_amount > 0 ? money(p.refunded_amount, p.currency) : "—"}
                              </td>
                              <td className={`${TD} ${CELL_LAST} py-2.5`}>
                                <Badge tone={statusTone(p.status)}>{titleCase(p.status)}</Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}
          </SheetBody>
        </SheetContent>
      </Sheet>

      {/* Assign trainer: nested sheet over the member sheet. The trainer list is a
          Radix Select because the in-house one portals its listbox to <body>,
          which a Radix dialog makes inert. */}
      <Sheet open={assignOpen} onOpenChange={setAssignOpen}>
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <SheetTitle>Assign a trainer</SheetTitle>
              <SheetDescription>{`Choose a trainer for ${name}`}</SheetDescription>
            </div>
          </SheetHeader>
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

      <Dialog
        open={qrOpen}
        onClose={() => setQrOpen(false)}
        title="Member QR"
        subtitle={name}
      >
        <div className="flex flex-col items-center gap-3 px-6 pb-6">
          {m && (
            <>
              <div className="rounded-xl bg-white p-3">
                <QRCodeSVG value={`acron:member:${m.member_id}`} size={180} />
              </div>
              <p className="text-center text-xs text-[var(--muted)]">
                Scan this at the front desk to check in.
              </p>
              <p className="font-mono text-[10px] text-[var(--muted)]">{m.member_id}</p>
            </>
          )}
        </div>
      </Dialog>
    </>
  );
}
