import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import { PaymentTrendChart, type PaymentTrendPoint } from "@/components/PaymentTrendChart";
import { Badge } from "@/components/ui";
import { WorkspaceAction } from "@/components/WorkspaceAction";
import { backend } from "@/lib/backend";
import {
  fmtDate,
  gymStatusLabel,
  gymStatusTone,
  money,
  statusTone,
  titleCase,
} from "@/lib/format";
import type {
  HeadlineMetrics,
  OrganizationOut,
  PaymentOut,
  ProfileOut,
  SaasStatusOut,
  SetupChecklist,
} from "@/lib/types";

async function safe<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch { return null; }
}

type Tone = "neutral" | "success" | "danger" | "warning" | "info";

const PRIMARY_ACTION_CLASS = "inline-flex min-h-9 items-center justify-center gap-2 border border-primary bg-primary px-3 text-xs font-semibold text-primary-foreground no-underline transition-colors hover:bg-primary-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

type ChecklistFlag = Exclude<keyof SetupChecklist, "steps">;

const CHECKLIST_LABELS: Record<ChecklistFlag, string> = {
  gym_registered: "Gym registered",
  saas_active: "SaaS plan active",
  stripe_connected: "Connect Stripe (member payments)",
  plan_published: "Publish a membership plan",
  enrollment_configured: "Configure enrollment mode",
  staff_invited: "Invite your staff",
  office_configured: "Set office statuses & leave types",
  member_signup_unblocked: "Member signup unblocked",
};

/** Where each onboarding step sends you. Unknown codes fall back to Settings. */
const STEP_HREF: Record<string, string> = {
  stripe: "/app/settings",
  staff: "/app/staff",
  invoices: "/app/invoices",
  gym_registered: "/app/settings",
  saas_active: "/app/billing",
  stripe_connected: "/app/settings",
  plan_published: "/app/plans",
  enrollment_configured: "/app/settings",
  staff_invited: "/app/staff",
  office_configured: "/app/settings",
  member_signup_unblocked: "/app/members",
  offer: "/app/plans",
  enroll: "/app/settings",
  people: "/app/staff",
  companies: "/app/companies",
  courses: "/app/courses",
  done: "/app",
};

function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

const ICONS = {
  members: "M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z",
  revenue: "M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  checkin: "M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  approvals: "M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z",
  seats: "M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z",
  percent: "M10.5 6a7.5 7.5 0 107.5 7.5h-7.5V6zM13.5 10.5H21A7.5 7.5 0 0013.5 3v7.5z",
  invoice: "M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z",
} as const;

function ProgressBar({ value, tone = "brand" }: { value: number; tone?: "brand" | "success" }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div role="progressbar" aria-label="Progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="h-1 w-full overflow-hidden bg-foreground/[0.08]">
      <div
        className={`h-full ${tone === "success" ? "bg-success" : "bg-brand"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function calendarDay(value: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function paymentTrend(payments: PaymentOut[], timeZone: string): PaymentTrendPoint[] {
  const today = calendarDay(new Date(), timeZone);
  const days = Array.from({ length: 14 }, (_, index) => {
    const date = new Date(`${today}T00:00:00Z`);
    date.setUTCDate(date.getUTCDate() - (13 - index));
    const label = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(date);
    return { date: date.toISOString().slice(0, 10), label, axisLabel: index % 2 === 0 ? label : "", count: 0 };
  });
  const byDate = new Map(days.map((day) => [day.date, day]));
  for (const payment of payments) {
    if (payment.status !== "succeeded" && payment.status !== "partially_refunded") continue;
    const day = byDate.get(calendarDay(new Date(payment.paid_at ?? payment.created_at), timeZone));
    if (day) day.count += 1;
  }
  return days;
}

export default async function DashboardPage() {
  const [metrics, checklist, saas, org, payments, profile] = await Promise.all([
    safe(backend<HeadlineMetrics>("/analytics/headline")),
    safe(backend<SetupChecklist>("/organizations/me/checklist")),
    safe(backend<SaasStatusOut>("/saas-billing/status")),
    safe(backend<OrganizationOut>("/organizations/me")),
    safe(backend<PaymentOut[]>("/payments")),
    safe(backend<ProfileOut>("/auth/me/profile")),
  ]);

  const currency = org?.default_currency ?? "USD";
  const industry = org?.industry ?? "gym";
  const isOffice = industry === "office";
  const isAcademy = industry === "academy";

  const today = new Date().toLocaleDateString("en-US", {
    timeZone: org?.timezone || "UTC",
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  const firstName = profile?.full_name?.trim().split(/\s+/)[0] ?? null;
  const greeting = firstName ? `Welcome back, ${firstName}` : "Dashboard";

  // ── KPI strip ───────────────────────────────────────────────────────────
  const stats: { label: string; value: string; icon: string; href: string; accent?: boolean }[] =
    isOffice
      ? [
          { label: "Seats occupied", value: metrics ? String(metrics.occupied_seats ?? 0) : "—", icon: ICONS.seats, href: "/app/members" },
          { label: "Occupancy", value: metrics ? `${Math.round(metrics.occupancy_pct ?? 0)}%` : "—", icon: ICONS.percent, href: "/app/space", accent: true },
          { label: "Monthly space revenue", value: metrics ? money(metrics.space_mrr ?? 0, currency) : "—", icon: ICONS.revenue, href: "/app/payments" },
          { label: "Outstanding invoices", value: metrics ? money(metrics.outstanding_invoices ?? 0, currency) : "—", icon: ICONS.invoice, href: "/app/invoices" },
        ]
      : [
          { label: "Active members", value: metrics ? String(metrics.active_members) : "—", icon: ICONS.members, href: "/app/members" },
          { label: "Today's revenue", value: metrics ? money(metrics.today_revenue, currency) : "—", icon: ICONS.revenue, href: "/app/payments", accent: true },
          { label: "Check-ins today", value: metrics ? String(metrics.today_check_ins) : "—", icon: ICONS.checkin, href: "/app/attendance" },
          { label: "Pending approvals", value: metrics ? String(metrics.pending_approvals) : "—", icon: ICONS.approvals, href: "/app/approvals" },
        ];

  // ── Setup checklist ─────────────────────────────────────────────────────
  const checklistItems = (checklist?.steps?.length
    ? checklist.steps.map((s) => ({ key: s.code, label: s.label, done: s.done }))
    : checklist
      ? (Object.keys(CHECKLIST_LABELS) as ChecklistFlag[]).map((k) => ({
          key: k,
          label: CHECKLIST_LABELS[k],
          done: checklist[k],
        }))
      : []) as { key: string; label: string; done: boolean }[];

  const totalSteps = checklistItems.length;
  const remaining = checklistItems.filter((i) => !i.done).length;
  const doneSteps = totalSteps - remaining;
  const setupPct = totalSteps ? Math.round((doneSteps / totalSteps) * 100) : 0;
  const nextStep = checklistItems.find((i) => !i.done) ?? null;

  const allSetCopy = isOffice
    ? "All set — your space is fully configured."
    : isAcademy
      ? "All set — your academy is fully configured."
      : "All set — your gym is fully configured.";

  // ── Needs attention ─────────────────────────────────────────────────────
  const attention: { label: string; value: string; href: string; tone: Tone }[] = [];
  if (metrics?.pending_receipts) {
    attention.push({ label: "Receipts to review", value: String(metrics.pending_receipts), href: "/app/receipts", tone: "warning" });
  }
  if (metrics?.pending_approvals) {
    attention.push({ label: "Approvals pending", value: String(metrics.pending_approvals), href: "/app/approvals", tone: "warning" });
  }
  if (isOffice && (metrics?.outstanding_invoices ?? 0) > 0) {
    attention.push({ label: "Outstanding invoices", value: money(metrics!.outstanding_invoices ?? 0, currency), href: "/app/invoices", tone: "danger" });
  }

  // ── Quick actions ───────────────────────────────────────────────────────
  const quickActions: { label: string; href: string; icon: string }[] = isOffice
    ? [
        { label: "Add a company", href: "/app/companies", icon: ICONS.members },
        { label: "Create a space plan", href: "/app/plans", icon: ICONS.invoice },
        { label: "Issue an invoice", href: "/app/invoices", icon: ICONS.invoice },
      ]
    : isAcademy
      ? [
          { label: "Create a course", href: "/app/courses", icon: ICONS.invoice },
          { label: "Publish a fee plan", href: "/app/plans", icon: ICONS.revenue },
          { label: "Add a student", href: "/app/members", icon: ICONS.members },
        ]
      : [
        { label: "Invite a member", href: "/app/members?invite=1", icon: ICONS.members },
          { label: "Create a plan", href: "/app/plans", icon: ICONS.revenue },
          { label: "Log a cash payment", href: "/app/cash", icon: ICONS.invoice },
        ];

  const trend = payments ? paymentTrend(payments, org?.timezone || "UTC") : null;

  const memberCapPct =
    saas?.member_cap && saas.member_cap > 0
      ? Math.min(100, Math.round((saas.current_member_count / saas.member_cap) * 100))
      : null;

  const saasBadgeTone: Tone = saas?.read_only
    ? "danger"
    : saas?.saas_status === "past_due" || saas?.saas_status === "suspended"
      ? "warning"
      : statusTone(saas?.saas_status ?? "active");

  return (
    <>
      <PageHeader
        title={greeting}
        subtitle={today + " · " + (org?.name ?? "Workspace")}
        action={quickActions[0] ? (
          <WorkspaceAction href={quickActions[0].href} primary className={PRIMARY_ACTION_CLASS}>
            <span aria-hidden="true" className="text-base leading-none">+</span>
            {quickActions[0].label}
          </WorkspaceAction>
        ) : undefined}
      />

      {saas?.saas_status === "past_due" && !saas.read_only && (
        <div className="mb-5 border border-[var(--danger-border)] bg-[var(--danger-bg)] px-4 py-3 text-[13px] text-[var(--danger)]">
          <strong>Payment failed.</strong>{" "}
          {saas.retry_count > 0 ? "Stripe retry #" + saas.retry_count + " failed. " : ""}
          Update your card in <Link className="font-semibold underline" href="/app/billing">Billing</Link> to avoid interruption.
        </div>
      )}
      {saas?.read_only && (
        <div className="mb-5 border border-[var(--danger-border)] bg-[var(--danger-bg)] px-4 py-3 text-[13px] text-[var(--danger)]">
          <strong>Account is read-only.</strong> Update billing to restore full access.
        </div>
      )}
      {saas?.saas_status === "suspended" && (
        <div className="mb-5 border border-[var(--warning-border)] bg-[var(--warning-bg)] px-4 py-3 text-[13px] text-[var(--warning)]">
          <strong>Account suspended.</strong> Contact support to reactivate your workspace.
        </div>
      )}

      <section aria-labelledby="snapshot-title" className="mb-8">
        <div className="mb-3 flex items-center justify-between gap-4">
          <h2 id="snapshot-title" className="text-[13px] font-semibold">At a glance</h2>
          <Link href="/app/analytics" className="text-[12px] font-medium text-brand no-underline hover:underline">Explore analytics ↗</Link>
        </div>
        <div className="grid grid-cols-2 overflow-hidden border border-border bg-border gap-px md:grid-cols-4">
          {stats.map((stat) => (
            <Link key={stat.label} href={stat.href} className="group min-w-0 bg-background px-5 py-5 text-foreground no-underline transition-colors hover:bg-foreground/[0.025] focus-visible:relative focus-visible:outline-2 focus-visible:outline-brand">
              <span className="block text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{stat.label}</span>
              <span className="mt-2 block truncate text-[clamp(20px,2.5vw,28px)] font-semibold tracking-tight tabular-nums">{stat.value}</span>
            </Link>
          ))}
        </div>
      </section>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(280px,0.8fr)]">
        <section className="min-w-0 border border-border bg-background" aria-labelledby="payments-title">
          <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-4">
            <div>
              <h2 id="payments-title" className="text-[16px] font-semibold tracking-tight">Payment activity</h2>
              <p className="mt-1 text-[12px] text-muted-foreground">Successful transactions over the last 14 days</p>
            </div>
            <Link href="/app/payments" className="shrink-0 text-[12px] font-medium text-brand no-underline hover:underline">View all ↗</Link>
          </div>
          <div className="min-w-0 overflow-hidden">
            {trend === null ? (
              <p className="px-5 py-8 text-[13px] text-muted-foreground">Payments could not be loaded.</p>
            ) : (
              <PaymentTrendChart data={trend} />
            )}
          </div>
        </section>

        <aside className="min-w-0 space-y-6" aria-label="Actions and setup">
          <section aria-labelledby="action-title">
            <h2 id="action-title" className="mb-3 text-[16px] font-semibold tracking-tight">Next steps</h2>
            <div className="overflow-hidden border border-border bg-background">
              {attention.length > 0 && (
                <ul className="m-0 list-none p-0">
                  {attention.map((item) => (
                    <li key={item.label} className="border-b border-border">
                      <Link href={item.href} className="flex min-h-12 items-center justify-between gap-3 px-4 text-[12px] font-medium text-foreground no-underline transition-colors hover:bg-foreground/[0.025]">
                        <span>{item.label}</span><Badge tone={item.tone}>{item.value}</Badge>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <div className="px-4 py-4">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h3 className="text-[13px] font-semibold">Workspace setup</h3>
                  {checklist !== null && <span className="text-[11px] tabular-nums text-muted-foreground">{doneSteps} of {totalSteps}</span>}
                </div>
                {checklist === null ? (
                  <p className="text-[12px] text-muted-foreground">Setup status is temporarily unavailable.</p>
                ) : nextStep ? (
                  <>
                    <p className="text-[12px] text-muted-foreground">Next: <span className="font-medium text-foreground">{nextStep.label}</span></p>
                    <div className="my-3"><ProgressBar value={setupPct} /></div>
                    <WorkspaceAction href={STEP_HREF[nextStep.key] ?? "/app/settings"} className="inline-flex min-h-8 items-center text-[12px] font-semibold text-brand no-underline hover:underline">Continue setup →</WorkspaceAction>
                  </>
                ) : (
                  <p className="text-[12px] text-muted-foreground">{allSetCopy}</p>
                )}
                {checklistItems.length > 0 && (
                  <details className="mt-3 border-t border-border pt-3 text-[12px]">
                    <summary className="cursor-pointer text-muted-foreground">View checklist</summary>
                    <ul className="mt-3 grid list-none gap-2.5 p-0">
                      {checklistItems.map((item) => (
                        <li key={item.key} className="flex items-center gap-2">
                          <span className={item.done ? "text-success" : "text-muted-foreground"} aria-label={item.done ? "Complete" : "Incomplete"}>{item.done ? "✓" : "○"}</span>
                          <span className="min-w-0 flex-1">{item.label}</span>
                          {!item.done && <WorkspaceAction href={STEP_HREF[item.key] ?? "/app/settings"} label={"Open: " + item.label} className="text-brand no-underline hover:underline">Open</WorkspaceAction>}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            </div>
          </section>

          <nav aria-label="Common tasks">
            <h2 className="mb-3 text-[16px] font-semibold tracking-tight">Common tasks</h2>
            <div className="overflow-hidden border border-border bg-background">
              {quickActions.slice(1).map((action) => (
                <WorkspaceAction key={action.href} href={action.href} className="flex min-h-11 items-center gap-3 border-b border-border px-4 text-[12px] font-medium text-foreground no-underline transition-colors last:border-0 hover:bg-foreground/[0.025]">
                  <Icon d={action.icon} className="h-4 w-4 text-muted-foreground" />
                  <span className="flex-1">{action.label}</span><span aria-hidden="true" className="text-muted-foreground">↗</span>
                </WorkspaceAction>
              ))}
            </div>
          </nav>
        </aside>
      </div>

      <section className="mt-8 border border-border" aria-labelledby="subscription-title">
        <div className="flex items-center gap-3 border-b border-border px-5 py-4">
          <h2 id="subscription-title" className="text-[13px] font-semibold">Workspace plan</h2>
          {org && <Badge tone={gymStatusTone(org.gym_status)}>{gymStatusLabel(org.gym_status)}</Badge>}
          <Link href="/app/billing" className="ml-auto shrink-0 text-[12px] font-medium text-brand no-underline hover:underline">Manage plan ↗</Link>
        </div>
        <dl className="grid grid-cols-2 gap-px bg-border text-[12px] lg:grid-cols-4">
          <div className="min-w-0 bg-background px-5 py-4">
            <dt className="text-muted-foreground">Plan</dt>
            <dd className="mt-1 font-semibold">{saas ? titleCase(saas.saas_tier) : "Unavailable"}</dd>
          </div>
          <div className="min-w-0 bg-background px-5 py-4">
            <dt className="text-muted-foreground">Status</dt>
            <dd className="mt-1">{saas ? <Badge tone={saasBadgeTone}>{titleCase(saas.saas_status)}</Badge> : "—"}</dd>
          </div>
          <div className="min-w-0 bg-background px-5 py-4">
            <dt className="text-muted-foreground">Members</dt>
            <dd className="mt-1 font-semibold">{saas ? saas.current_member_count + " / " + (saas.member_cap ?? "Unlimited") : "—"}</dd>
            {memberCapPct !== null && <div className="mt-2 max-w-32"><ProgressBar value={memberCapPct} /></div>}
          </div>
          <div className="min-w-0 bg-background px-5 py-4">
            <dt className="text-muted-foreground">Renews</dt>
            <dd className="mt-1 font-semibold">{saas?.current_period_end ? fmtDate(saas.current_period_end) : "—"}</dd>
          </div>
        </dl>
      </section>
    </>
  );
}
