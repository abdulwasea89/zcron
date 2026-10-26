"use client";

import { useCallback, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Spinner,
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
import { MemberTagsCard } from "@/components/members/MemberTagsCard";
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

function SheetInfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(110px,0.8fr)_minmax(0,1.4fr)] items-center gap-4 border-b border-foreground/[0.07] py-3 last:border-0">
      <dt className="text-[12px] text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-[13px] text-foreground">{children}</dd>
    </div>
  );
}

function MemberDetailLink({ title, detail, onClick }: { title: string; detail: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-[60px] min-w-0 items-center justify-between gap-3 border border-foreground/[0.1] px-3.5 py-2.5 text-left transition-colors hover:border-foreground/20 hover:bg-foreground/[0.025] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand/60"
    >
      <span className="min-w-0">
        <span className="block truncate text-[12px] font-medium text-foreground">{title}</span>
        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{detail}</span>
      </span>
      <svg className="h-4 w-4 shrink-0 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="m9 18 6-6-6-6" />
      </svg>
    </button>
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
  const [detailSheet, setDetailSheet] = useState<"profile" | "visits" | "pending" | "payments" | null>(null);

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
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setDetailSheet(null);
      setQrOpen(false);
      setAssignOpen(false);
    });
    queueMicrotask(() => void load(memberId));
    queueMicrotask(() => {
      api
        .get<AttendanceOut[]>(`/attendance/members/${memberId}/visits`)
        .then(setVisits)
        .catch(() => setVisits([]));
    });
    return () => { active = false; };
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
  const sub = data?.subscription;

  // Header summary numbers (lifetime collected excludes failed/pending attempts).
  const visitCount = visits?.length ?? 0;
  const collected = (data?.payments ?? [])
    .filter((p) => p.status === "succeeded" || p.status === "partially_refunded")
    .reduce((sum, p) => sum + (p.amount - p.refunded_amount), 0);
  const successfulPaymentCount = (data?.payments ?? []).filter(
    (payment) => payment.status === "succeeded" || payment.status === "partially_refunded",
  ).length;
  const unsettledPaymentCount = (data?.payments ?? []).filter(
    (payment) => payment.status === "pending" || payment.status === "failed",
  ).length;
  const currency = sub?.currency ?? data?.payments?.[0]?.currency ?? "USD";
  const recentActivity = [
    ...(m ? [{
      id: "joined",
      at: new Date(m.created_at),
      title: "Joined",
      detail: "Member account created",
    }] : []),
    ...(visits ?? []).map((visit) => ({
      id: `visit-${visit.id}`,
      at: new Date(visit.checked_in_at + "Z"),
      title: "Checked in",
      detail: titleCase(visit.method),
    })),
    ...(data?.payments ?? []).map((payment) => ({
      id: `payment-${payment.id}`,
      at: new Date(payment.paid_at ?? payment.created_at),
      title: "Payment",
      detail: `${titleCase(payment.status)} · ${money(payment.amount, payment.currency)}`,
    })),
  ].sort((a, b) => b.at.getTime() - a.at.getTime()).slice(0, 6);

  return (
    <>
      <Sheet
        open={!!memberId}
        onOpenChange={(open) => {
          if (!open) {
            setQrOpen(false);
            setAssignOpen(false);
            setDetailSheet(null);
            onClose();
          }
        }}
      >
        <SheetContent style={{ "--sheet-max-w": "540px" } as React.CSSProperties}>
          <SheetHeader className="flex items-center gap-4 py-4">
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
                {/* Key facts first, followed by a brief account summary. */}
                <section className="border-y border-foreground/[0.08]">
                  <dl>
                    <SheetInfoRow label="Joined">{new Date(m.created_at).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}</SheetInfoRow>
                    {m.phone && <SheetInfoRow label="Phone">{m.phone}</SheetInfoRow>}
                    {sub ? <>
                      <SheetInfoRow label="Membership plan">{sub.plan_name}</SheetInfoRow>
                      <SheetInfoRow label="Plan price">{money(sub.price_snapshot, sub.currency)} <span className="text-muted-foreground">/ {sub.billing_type === "one_time_pack" ? "pack" : "cycle"}</span></SheetInfoRow>
                      <SheetInfoRow label="Plan status"><Badge tone={statusTone(sub.status)} size="sm">{titleCase(sub.status)}</Badge></SheetInfoRow>
                      <SheetInfoRow label="Started">{new Date(sub.started_at).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}</SheetInfoRow>
                      {sub.current_period_end && <SheetInfoRow label="Renews / ends">{new Date(sub.current_period_end).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}</SheetInfoRow>}
                      {sub.classes_remaining != null && <SheetInfoRow label="Visit credits">{sub.classes_remaining}{sub.credits_allowance ? ` of ${sub.credits_allowance}` : " remaining"}</SheetInfoRow>}
                      {data.family_owner && <SheetInfoRow label={data.family_owner.billing_mode === "independent" ? "Household contact" : "Family plan payer"}>{data.family_owner.name}</SheetInfoRow>}
                    </> : <SheetInfoRow label="Membership plan"><span className="text-muted-foreground">No current plan</span></SheetInfoRow>}
                  </dl>
                </section>

                <section className="border-b border-foreground/[0.08] pb-5">
                  <h2 className="mb-2 text-[12px] font-medium text-muted-foreground">Account summary</h2>
                  <p className="text-[13px] leading-relaxed text-foreground/90">
                    {name} joined on {new Date(m.created_at).toLocaleDateString([], { month: "long", day: "numeric", year: "numeric" })} and is {m.member_status.replaceAll("_", " ").toLowerCase()}
                    {sub ? ` on the ${sub.plan_name} plan` : " without a current plan"}. The account has {visits === null ? "a visit history that is still loading" : `${visitCount} recorded ${visitCount === 1 ? "visit" : "visits"}`} and {money(collected, currency)} collected across {successfulPaymentCount} successful {successfulPaymentCount === 1 ? "payment" : "payments"}{unsettledPaymentCount > 0 ? `, with ${unsettledPaymentCount} pending or failed attempts` : ""}.
                  </p>
                </section>

                <div className="grid gap-2 sm:grid-cols-2">
                  <MemberDetailLink title="Visits" detail={visits === null ? "Loading activity…" : `${visitCount} recorded`} onClick={() => setDetailSheet("visits")} />
                  <MemberDetailLink title="Pending payments" detail={`${data.pending_payments.length} to review`} onClick={() => setDetailSheet("pending")} />
                  <MemberDetailLink title="Payment history" detail={`${data.payments.length} recorded · ${money(collected, currency)} collected`} onClick={() => setDetailSheet("payments")} />
                  <MemberDetailLink title="Member profile" detail="Goals, contact and private notes" onClick={() => setDetailSheet("profile")} />
                </div>

                <section aria-labelledby="member-recent-activity" className="border-t border-foreground/[0.08] pt-4">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <h2 id="member-recent-activity" className="text-[12px] font-medium text-muted-foreground">Recent activity</h2>
                    <button type="button" onClick={() => setDetailSheet("payments")} className="text-[11px] font-medium text-brand hover:underline">View payments</button>
                  </div>
                  {visits === null ? <p className="text-[12px] text-muted-foreground">Loading activity…</p> : recentActivity.length === 0 ? (
                    <p className="text-[12px] text-muted-foreground">No check-ins or payments recorded yet.</p>
                  ) : (
                    <ul className="m-0 list-none divide-y divide-foreground/[0.07] p-0">
                      {recentActivity.map((item) => (
                        <li key={item.id} className="flex items-center justify-between gap-3 py-2.5 text-[12px]">
                          <span className="min-w-0">
                            <span className="block font-medium">{item.title}</span>
                            <span className="block text-muted-foreground">{item.detail}</span>
                          </span>
                          <time className="shrink-0 text-muted-foreground" dateTime={item.at.toISOString()}>{item.at.toLocaleDateString([], { month: "short", day: "numeric" })}</time>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </>
            )}
          </SheetBody>
          <SheetFooter>
            <SheetClose asChild><Button type="button" variant="secondary">Close</Button></SheetClose>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      <Sheet open={detailSheet === "profile"} onOpenChange={(open) => { if (!open) setDetailSheet(null); }}>
        <SheetContent style={{ "--sheet-max-w": "560px" } as React.CSSProperties}>
          <SheetHeader>
            <SheetTitle>Member profile</SheetTitle>
            <SheetDescription>{name} · contact, goals and family membership</SheetDescription>
          </SheetHeader>
          <SheetBody className="space-y-4">
            {data && m && <>
              <MemberProfileCard key={m.member_id} memberId={m.member_id} profile={data.profile} canManage={canManage} onSaved={() => load(m.member_id)} />
              <MemberTagsCard key={`tags:${m.member_id}`} memberId={m.member_id} tags={m.tags ?? []} canManage={canManage} onSaved={() => load(m.member_id)} />
              <FamilyPlanCard key={data.member.member_id} detail={data} canManage={canManage} onSaved={() => load(m.member_id)} />
              {m.role === "member" && <Card>
                <CardHeader title="Trainers" subtitle="Staff assigned to this member" action={canManage ? <Button variant="secondary" onClick={() => void openAssign()}>Assign trainer</Button> : undefined} />
                {data.trainer_assignments.length === 0 ? <p className="px-5 pb-5 text-sm text-muted-foreground">No trainer assigned.</p> : <ul className="divide-y divide-foreground/[0.08]">{data.trainer_assignments.map((trainer) => <li key={trainer.trainer_member_id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm"><span>{trainer.trainer_name}</span>{canManage && <button type="button" onClick={() => void unassignTrainer(trainer.trainer_member_id)} className="text-xs text-muted-foreground hover:text-danger">Remove</button>}</li>)}</ul>}
              </Card>}
            </>}
          </SheetBody>
        </SheetContent>
      </Sheet>

      <Sheet open={detailSheet === "visits"} onOpenChange={(open) => { if (!open) setDetailSheet(null); }}>
        <SheetContent style={{ "--sheet-max-w": "560px" } as React.CSSProperties}>
          <SheetHeader>
            <SheetTitle>Visit history</SheetTitle>
            <SheetDescription>{visits === null ? "Loading member visits…" : visits.length + " recorded check-ins"}</SheetDescription>
          </SheetHeader>
          <SheetBody className="p-0">
            {m?.role === "member" && <div className="flex justify-end px-6 pt-4"><Button variant="secondary" onClick={() => setQrOpen(true)}>Show member QR</Button></div>}
            {visits === null ? <div className="p-6"><Spinner label="Loading visits…" /></div> : visits.length === 0 ? <EmptyState title="No visits yet" hint="Member check-ins will appear here." /> : (
              <div className="overflow-x-auto px-5 py-4">
                <table className={TABLE}>
                  <thead><tr className={THEAD_ROW}>
                    <th className={TH + " " + CELL_FIRST}>Date</th>
                    <th className={TH + " " + CELL}>Time</th>
                    <th className={TH + " " + CELL}>Method</th>
                    <th className={TH + " " + CELL_LAST + " text-right"}>Ago</th>
                  </tr></thead>
                  <tbody>{visits.map((visit) => <tr key={visit.id} className={TR}>
                    <td className={TD + " " + CELL_FIRST + " py-2.5 whitespace-nowrap"}>{new Date(visit.checked_in_at + "Z").toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })}</td>
                    <td className={TD + " " + CELL + " py-2.5 whitespace-nowrap"}>{new Date(visit.checked_in_at + "Z").toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</td>
                    <td className={TD + " " + CELL + " py-2.5"}><Badge tone="neutral" size="sm">{titleCase(visit.method)}</Badge></td>
                    <td className={TD + " " + CELL_LAST + " py-2.5 text-right text-xs text-muted-foreground"}>{ago(visit.checked_in_at)}</td>
                  </tr>)}</tbody>
                </table>
              </div>
            )}
          </SheetBody>
        </SheetContent>
      </Sheet>

      <Sheet open={detailSheet === "pending"} onOpenChange={(open) => { if (!open) setDetailSheet(null); }}>
        <SheetContent style={{ "--sheet-max-w": "560px" } as React.CSSProperties}>
          <SheetHeader>
            <SheetTitle>Pending payments</SheetTitle>
            <SheetDescription>{data ? data.pending_payments.length + " items needing attention" : "Loading payment status…"}</SheetDescription>
          </SheetHeader>
          <SheetBody className="p-0">
            {data && <PendingList items={data.pending_payments} />}
          </SheetBody>
        </SheetContent>
      </Sheet>

      <Sheet open={detailSheet === "payments"} onOpenChange={(open) => { if (!open) setDetailSheet(null); }}>
        <SheetContent style={{ "--sheet-max-w": "720px" } as React.CSSProperties}>
          <SheetHeader>
            <SheetTitle>Payment history</SheetTitle>
            <SheetDescription>{data ? data.payments.length + " recorded payments · " + money(collected, currency) + " net collected" : "Loading payments…"}</SheetDescription>
          </SheetHeader>
          <SheetBody className="p-0">
            {!data ? <div className="p-6"><Spinner label="Loading payments…" /></div> : data.payments.length === 0 ? <EmptyState title="No payments yet" hint="Payments will appear here once they are recorded." /> : (
              <div className="overflow-x-auto">
                <table className={TABLE}>
                  <thead><tr className={THEAD_ROW}>
                    <th className={TH + " " + CELL_FIRST}>Date</th>
                    <th className={TH + " " + CELL}>Method</th>
                    <th className={TH + " " + CELL + " text-right"}>Amount</th>
                    <th className={TH + " " + CELL + " text-right"}>Refunded</th>
                    <th className={TH + " " + CELL_LAST}>Status</th>
                  </tr></thead>
                  <tbody>{data.payments.map((payment) => <tr key={payment.id} className={TR}>
                    <td className={TD + " " + CELL_FIRST + " py-2.5 whitespace-nowrap"}>{(payment.paid_at || payment.created_at).slice(0, 10)}</td>
                    <td className={TD + " " + CELL + " py-2.5"}><MethodCell method={payment.method} /></td>
                    <td className={TD + " " + CELL + " py-2.5 text-right tabular-nums"}>{money(payment.amount, payment.currency)}</td>
                    <td className={TD + " " + CELL + " py-2.5 text-right tabular-nums"}>{payment.refunded_amount > 0 ? money(payment.refunded_amount, payment.currency) : "—"}</td>
                    <td className={TD + " " + CELL_LAST + " py-2.5"}><Badge tone={statusTone(payment.status)} size="sm">{titleCase(payment.status)}</Badge></td>
                  </tr>)}</tbody>
                </table>
              </div>
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
