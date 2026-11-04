import Link from "next/link";
import { PaymentTrendChart, type PaymentTrendPoint } from "@/components/PaymentTrendChart";
import { Card } from "@/components/ui";
import { Users, CircleDollarSign, CircleCheck, ClipboardCheck, Grid2X2, ChartPie, FileText, Plus, ChevronRight, Check, Circle, CalendarDays, CreditCard, type LucideIcon } from "lucide-react";
import { DashboardEmptyState, DashboardRetry } from "@/components/DashboardUI";
import { dashboardName, dashboardNumber } from "@/lib/dashboard-format";
import "./dashboard.css";
import { WorkspaceAction } from "@/components/WorkspaceAction";
import { DashboardTaskList } from "@/components/DashboardTaskList";
import { backend } from "@/lib/backend";
import {
  fmtDate,
  dateKeyInTimeZone,
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
  TaskOut,
  ClientAssignment,
  ClassSessionOut,
  StaffScheduleOut,
} from "@/lib/types";

async function safe<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch { return null; }
}

type Tone = "neutral" | "success" | "danger" | "warning" | "info";
type RetentionSummary = { scored: number; high: number; medium: number; revenue_at_risk: number; revenue_at_risk_by_currency?: Record<string, number> };
type RetentionRiskAction = { member_id: string; name: string | null; phone: string | null; band: string };
type LeadResponseSummary = { uncontacted: number };


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

function Icon({ d: Glyph, className }: { d: LucideIcon; className?: string }) {
  return <Glyph className={className} aria-hidden="true" />;
}

const ICONS = { members: Users, revenue: CircleDollarSign, checkin: CircleCheck, approvals: ClipboardCheck, seats: Grid2X2, percent: ChartPie, invoice: FileText };

function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="dash-progress">
    <div className="dash-progress-fill" style={{ width: `${pct}%` }} />
  </div>;
}

function paymentTrend(payments: PaymentOut[], timeZone: string): PaymentTrendPoint[] {
  const today = dateKeyInTimeZone(new Date(), timeZone);
  const days = Array.from({ length: 14 }, (_, index) => {
    const date = new Date(`${today}T00:00:00Z`);
    date.setUTCDate(date.getUTCDate() - (13 - index));
    const label = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(date);
    return { date: date.toISOString().slice(0, 10), label, axisLabel: index % 2 === 0 ? label : "", count: 0 };
  });
  const byDate = new Map(days.map((day) => [day.date, day]));
  for (const payment of payments) {
    if (payment.status !== "succeeded" && payment.status !== "partially_refunded") continue;
    const day = byDate.get(dateKeyInTimeZone(new Date(payment.paid_at ?? payment.created_at), timeZone));
    if (day) day.count += 1;
  }
  return days;
}

export default async function DashboardPage() {
  const currentUser = await safe(backend<{ role: string; user_id: string; member_id: string | null }>("/auth/me"));
  const canManageWorkspace = currentUser?.role === "owner" || currentUser?.role === "manager";
  const [metrics, checklist, saas, org, payments, profile, tasks] = await Promise.all([
    safe(backend<HeadlineMetrics>("/analytics/headline")),
    safe(backend<SetupChecklist>("/organizations/me/checklist")),
    safe(backend<SaasStatusOut>("/saas-billing/status")),
    safe(backend<OrganizationOut>("/organizations/me")),
    canManageWorkspace
      ? safe(backend<PaymentOut[]>(
          `/payments?since=${encodeURIComponent(new Date(new Date().getTime() - 15 * 86400000).toISOString())}`,
        ))
      : Promise.resolve(null),
    safe(backend<ProfileOut>("/auth/me/profile")),
    safe(backend<TaskOut[]>("/staff/tasks")),
  ]);

  const canViewBusinessMetrics = canManageWorkspace;
  const isTrainer = currentUser?.role === "trainer";
  const isFrontDesk = currentUser?.role === "front_desk";

  const [trainerClients, trainerClasses, mySchedule] = await Promise.all([
    isTrainer ? safe(backend<ClientAssignment[]>("/members/assigned-to-me")) : Promise.resolve(null),
    isTrainer ? safe(backend<ClassSessionOut[]>("/classes")) : Promise.resolve(null),
    ["trainer", "front_desk", "manager"].includes(currentUser?.role ?? "")
      ? safe(backend<StaffScheduleOut[]>("/staff/schedule/mine"))
      : Promise.resolve(null),
  ]);
  const upcomingTrainerClasses = (trainerClasses ?? [])
    .filter((session) => !session.cancelled && session.trainer_member_id === currentUser?.member_id && new Date(session.starts_at) >= new Date())
    .slice(0, 4);

  const currency = org?.default_currency ?? "USD";
  const industry = org?.industry ?? "gym";
  const isOffice = industry === "office";
  const isAcademy = industry === "academy";
  const [retentionSummary, leadResponseSummary] = canManageWorkspace && industry === "gym"
    ? await Promise.all([
        safe(backend<RetentionSummary>("/retention/summary")),
        safe(backend<LeadResponseSummary>("/leads/speed-report?days=30")),
      ])
    : [null, null];
  const retentionRisks = retentionSummary && retentionSummary.high + retentionSummary.medium > 0
    ? await safe(backend<RetentionRiskAction[]>("/retention/at-risk?min_score=40&limit=3"))
    : null;
  const riskByCurrency = Object.entries(retentionSummary?.revenue_at_risk_by_currency ?? {});
  const revenueAtRiskLabel = riskByCurrency.length
    ? riskByCurrency.map(([code, amount]) => money(amount, code)).join(" · ")
    : money(retentionSummary?.revenue_at_risk ?? 0, currency);

  const today = new Date().toLocaleDateString("en-US", {
    timeZone: org?.timezone || "UTC",
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  const firstName = dashboardName(profile?.full_name, profile?.email);
  const timeZone = org?.timezone || "UTC";
  const todayKey = dateKeyInTimeZone(new Date(), timeZone);
  const openTasks = (tasks ?? []).filter((task) => !task.done).sort((a, b) =>
    (a.deadline ? new Date(a.deadline).getTime() : Number.POSITIVE_INFINITY) -
    (b.deadline ? new Date(b.deadline).getTime() : Number.POSITIVE_INFINITY),
  );
  const priorityTasks = openTasks.map((task) => {
    const dueDay = task.deadline?.slice(0, 10) ?? null;
    const overdue = dueDay !== null && dueDay < todayKey;
    const dueToday = dueDay === todayKey;
    return {
      ...task,
      overdue,
      dueToday,
      dueLabel: !task.deadline ? "No due date" : overdue ? `Overdue · ${fmtDate(task.deadline)}` : dueToday ? "Due today" : fmtDate(task.deadline),
    };
  });
  const greeting = firstName ? `Welcome back, ${firstName}` : "Welcome back";

  const stats: { label: string; value: number | null; currency?: string; suffix?: string; icon: LucideIcon; href: string; context: string }[] =
    !canViewBusinessMetrics ? [] : isOffice ? [
      { label: "Seats occupied", value: metrics?.occupied_seats ?? (metrics ? 0 : null), icon: ICONS.seats, href: "/app/members", context: "Current occupancy" },
      { label: "Occupancy", value: metrics ? Math.round(metrics.occupancy_pct ?? 0) : null, suffix: "%", icon: ICONS.percent, href: "/app/space", context: "Of available seats" },
      { label: "Monthly space revenue", value: metrics?.space_mrr ?? (metrics ? 0 : null), currency, icon: ICONS.revenue, href: "/app/payments", context: "Monthly recurring revenue" },
      { label: "Outstanding invoices", value: metrics?.outstanding_invoices ?? (metrics ? 0 : null), currency, icon: ICONS.invoice, href: "/app/invoices", context: "Awaiting payment" },
    ] : [
      { label: "Active members", value: metrics?.active_members ?? null, icon: ICONS.members, href: "/app/members", context: "Current memberships" },
      { label: "Today's revenue", value: metrics?.today_revenue ?? null, currency, icon: ICONS.revenue, href: "/app/payments", context: "Payments received today" },
      { label: "Check-ins today", value: metrics?.today_check_ins ?? null, icon: ICONS.checkin, href: "/app/attendance", context: "Visits recorded today" },
      { label: "Pending approvals", value: metrics?.pending_approvals ?? null, icon: ICONS.approvals, href: "/app/approvals", context: "Ready for review" },
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
  const attention: { key: string; label: string; value: string; href: string; tone: Tone; phone?: string | null; member_id?: string; personName?: string | null; priority: number }[] = [];
  if (metrics?.pending_receipts) {
    attention.push({ key: `pending-receipts:${todayKey}:${metrics.pending_receipts}`, label: "Review payment receipts", value: `${metrics.pending_receipts} waiting`, href: "/app/receipts", tone: "warning", priority: 3 });
  }
  if (leadResponseSummary?.uncontacted) {
    attention.push({ key: `untouched-leads:${todayKey}:${leadResponseSummary.uncontacted}`, label: "Contact untouched leads", value: `${leadResponseSummary.uncontacted} · last 30 days`, href: "/app/leads", tone: "warning", priority: 0 });
  }
  if (retentionSummary && retentionSummary.high + retentionSummary.medium > 0) {
    if (retentionRisks?.length) {
      for (const member of retentionRisks) {
        attention.push({
          key: `at-risk:${todayKey}:${member.member_id}:${member.band}`,
          label: `Follow up: ${member.name || "member"}`,
          value: `${member.band} risk`,
          href: `/app/members?member=${encodeURIComponent(member.member_id)}`,
          tone: member.band === "high" ? "danger" : "warning",
          phone: member.phone,
          member_id: member.member_id,
          personName: member.name,
          priority: member.band === "high" ? 0 : 1,
        });
      }
      attention.push({
        key: `revenue-at-risk:${todayKey}:${revenueAtRiskLabel}`,
        label: "Estimated revenue at risk",
        value: revenueAtRiskLabel,
        href: "/app/retention",
        tone: "danger",
        priority: 8,
      });
    } else {
      attention.push({
        key: `at-risk-members:${todayKey}:${retentionSummary.high + retentionSummary.medium}`,
        label: "Follow up on at-risk members",
        value: `${retentionSummary.high + retentionSummary.medium} members · ${revenueAtRiskLabel} at risk`,
        href: "/app/retention",
        tone: "danger",
        priority: 1,
      });
    }
  }
  if (metrics?.pending_approvals) {
    attention.push({ key: `pending-approvals:${todayKey}:${metrics.pending_approvals}`, label: "Resolve member approvals", value: `${metrics.pending_approvals} waiting`, href: "/app/approvals", tone: "warning", priority: 4 });
  }
  if (isOffice && (metrics?.outstanding_invoices ?? 0) > 0) {
    attention.push({ key: `outstanding-invoices:${todayKey}:${metrics!.outstanding_invoices}`, label: "Follow up on invoices", value: money(metrics!.outstanding_invoices ?? 0, currency), href: "/app/invoices", tone: "danger", priority: 3 });
  }

  // ── Quick actions ───────────────────────────────────────────────────────
  const quickActions: { label: string; href: string; icon: LucideIcon }[] = isFrontDesk
    ? [
        { label: "Check in a member", href: "/app/attendance", icon: ICONS.checkin },
        { label: "Log a cash payment", href: "/app/cash", icon: ICONS.invoice },
        { label: "Review receipts", href: "/app/receipts", icon: ICONS.approvals },
        { label: "My pay", href: "/app/my-pay", icon: ICONS.revenue },
      ]
    : isTrainer
      ? [
          { label: "My tasks", href: "/app/tasks", icon: ICONS.approvals },
          { label: "My clients", href: "/app/staff#my-clients", icon: ICONS.members },
          { label: "Log a training session", href: "/app/training", icon: ICONS.checkin },
          { label: "My classes", href: "/app/classes", icon: ICONS.approvals },
          { label: "My pay", href: "/app/my-pay", icon: ICONS.revenue },
        ]
      : canManageWorkspace && isOffice
        ? [
            { label: "Add a company", href: "/app/companies", icon: ICONS.members },
            { label: "Create a space plan", href: "/app/plans", icon: ICONS.invoice },
            { label: "Issue an invoice", href: "/app/invoices", icon: ICONS.invoice },
          ]
        : canManageWorkspace && isAcademy
          ? [
              { label: "Create a course", href: "/app/courses", icon: ICONS.invoice },
              { label: "Publish a fee plan", href: "/app/plans", icon: ICONS.revenue },
              { label: "Add a student", href: "/app/members", icon: ICONS.members },
            ]
          : canManageWorkspace
            ? [
              { label: "Invite a member", href: "/app/members?invite=1", icon: ICONS.members },
              { label: "Create a plan", href: "/app/plans", icon: ICONS.revenue },
              { label: "Log a cash payment", href: "/app/cash", icon: ICONS.invoice },
            ]
            : [{ label: "My account", href: "/app/account", icon: ICONS.members }];

  if (currentUser?.role === "manager") {
    quickActions.push({ label: "My pay", href: "/app/my-pay", icon: ICONS.revenue });
  }

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

  const nextStepAction = nextStep?.key === "stripe" || nextStep?.key === "stripe_connected" ? "Connect payout account" : "Continue setup";
  const actionDescriptions: Record<string, string> = {
    "/app/plans": "Build a plan your members can join.",
    "/app/cash": "Record a payment received in person.",
    "/app/attendance": "Record a member’s visit.",
    "/app/receipts": "Verify payments waiting for review.",
    "/app/tasks": "Organize and complete your next steps.",
    "/app/staff#my-clients": "View your assigned members.",
    "/app/training": "Track a member’s training session.",
    "/app/classes": "See sessions and bookings.",
    "/app/my-pay": "Review your pay and earnings.",
    "/app/companies": "Manage your company accounts.",
    "/app/invoices": "Create and track an invoice.",
    "/app/courses": "Set up your next course.",
    "/app/members": "Add someone to your workspace.",
  };

  return <div className="dashboard">
    <header className="dash-header">
      <div><h1>{greeting}</h1><p className="dash-muted">{today}</p></div>
      {quickActions.slice(0, 1).map(action => <WorkspaceAction key={action.href} href={action.href} primary className="dash-button dash-primary"><Plus aria-hidden="true" />{action.label}</WorkspaceAction>)}
    </header>

    {canManageWorkspace && saas?.saas_status === "past_due" && !saas.read_only && <div className="dash-notice" role="status"><strong>Payment failed.</strong> {saas.retry_count > 0 ? `Stripe retry #${saas.retry_count} failed. ` : ""}Update your card in <Link href="/app/billing" className="dash-button dash-ghost">Billing<ChevronRight aria-hidden="true" /></Link> to avoid interruption.</div>}
    {canManageWorkspace && saas?.read_only && <div className="dash-notice" role="status"><strong>Account is read-only.</strong> Update billing to restore full access.<Link href="/app/billing" className="dash-button dash-ghost">Billing<ChevronRight aria-hidden="true" /></Link></div>}
    {canManageWorkspace && saas?.saas_status === "suspended" && <div className="dash-notice" role="status"><strong>Account suspended.</strong> Contact support to reactivate your workspace.</div>}

    {canViewBusinessMetrics && <section aria-label="Key metrics" className="dash-kpis">
      {stats.map(stat => stat.value === null ? <Card key={stat.label} className="dash-card"><p className="dash-stat-label">{stat.label}</p><DashboardRetry>Metric unavailable.</DashboardRetry></Card> :
        <Link href={stat.href} key={stat.label} className="dash-stat" title={`${stat.label}: ${dashboardNumber(stat.value, stat.currency)}${stat.suffix ?? ""}`}>
          <Card className="dash-card">
            <span className="dash-stat-label">{stat.label}<Icon d={stat.icon} /></span>
            <span className={`dash-stat-value${stat.value === 0 ? " dash-zero" : ""}`}>{dashboardNumber(stat.value, stat.currency, true)}{stat.suffix}</span>
            <span className="dash-stat-context">{stat.value === 0 ? (stat.label === "Pending approvals" ? "You’re all caught up" : "No activity yet") : stat.context}</span>
          </Card>
        </Link>)}
    </section>}

    <div className="dash-action-grid">
      <Card className="dash-card">
        <DashboardTaskList tasks={priorityTasks} attention={attention} unavailable={tasks === null} storageKey={`acron-dashboard:${org?.id ?? "unknown"}`} />
      </Card>
      <Card className="dash-card">
        <div className="dash-section-heading"><h2>Quick actions</h2></div>
        <nav className="dash-quick-list" aria-label="Quick actions">
          {quickActions.slice(1).map(action => <WorkspaceAction key={action.href} href={action.href} className="dash-quick-action">
            <span className="dash-icon-tile"><Icon d={action.icon} /></span>
            <span className="dash-quick-copy"><strong>{action.label}</strong><span className="dash-meta">{actionDescriptions[action.href] ?? "Open your workspace tools."}</span></span><ChevronRight aria-hidden="true" />
          </WorkspaceAction>)}
          {canViewBusinessMetrics && <Link href="/app/analytics" className="dash-quick-action"><span className="dash-icon-tile"><ChartPie aria-hidden="true" /></span><span className="dash-quick-copy"><strong>Analytics</strong><span className="dash-meta">Explore your workspace performance.</span></span><ChevronRight aria-hidden="true" /></Link>}
        </nav>
      </Card>
    </div>

    {canViewBusinessMetrics && <Card className="dash-card">
      <div className="dash-section-heading"><h2>Payment activity</h2><Link href="/app/payments" className="dash-button dash-ghost">View payments<ChevronRight aria-hidden="true" /></Link></div>
      {trend === null ? <DashboardRetry>Payment activity couldn’t load.</DashboardRetry> : <PaymentTrendChart data={trend} actionHref={isOffice ? "/app/invoices" : "/app/cash"} actionLabel={isOffice ? "Create an invoice" : "Log a cash payment"} />}
    </Card>}

    {isTrainer && <section className="dash-trainer-grid" aria-label="Trainer workspace">
      <Card className="dash-card"><div className="dash-section-heading"><h2>My clients</h2><span className="dash-badge">{trainerClients?.length ?? "—"} assigned</span></div>
        {trainerClients === null ? <DashboardRetry>Clients couldn’t load.</DashboardRetry> : trainerClients.length ? <ul className="dash-record-list">{trainerClients.slice(0,5).map(client => <li key={client.member_id}><Link href={`/app/members?member=${encodeURIComponent(client.member_id)}`}><span>{client.member_name || client.member_email}</span><span className="dash-badge" data-tone={client.member_status === "active" ? "success" : "neutral"}>{titleCase(client.member_status)}</span></Link></li>)}</ul> : <DashboardEmptyState icon={<Users />} title="No clients assigned" href="/app/staff#my-clients" action="View my clients">Assigned members will appear here so you can follow their progress.</DashboardEmptyState>}
        {(trainerClients?.length ?? 0) > 5 && <Link href="/app/staff#my-clients" className="dash-button dash-ghost">View all {trainerClients?.length} clients<ChevronRight aria-hidden="true" /></Link>}
      </Card>
      <Card className="dash-card"><div className="dash-section-heading"><h2>Upcoming classes</h2><Link href="/app/classes" className="dash-button dash-ghost">Schedule<ChevronRight aria-hidden="true" /></Link></div>
        {trainerClasses === null ? <DashboardRetry>Classes couldn’t load.</DashboardRetry> : upcomingTrainerClasses.length ? <ul className="dash-record-list">{upcomingTrainerClasses.map(session => <li key={session.id}><div>{session.title}<p className="dash-meta">{fmtDate(session.starts_at)} · {new Date(session.starts_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZone })}</p></div><span className="dash-badge">{session.booked_count}/{session.capacity}</span></li>)}</ul> : <DashboardEmptyState icon={<CalendarDays />} title="No upcoming classes" href="/app/classes" action="View schedule">Your assigned sessions and bookings will appear here.</DashboardEmptyState>}
      </Card>
    </section>}

    {["trainer", "front_desk", "manager"].includes(currentUser?.role ?? "") && <Card className="dash-card"><div className="dash-section-heading"><h2>My upcoming shifts</h2><Link href="/app/my-pay" className="dash-button dash-ghost">My pay<ChevronRight aria-hidden="true" /></Link></div>
      {mySchedule === null ? <DashboardRetry>Shifts couldn’t load.</DashboardRetry> : mySchedule.length ? <ul className="dash-record-list">{mySchedule.slice(0,5).map(shift => <li key={shift.id}><div>{fmtDate(shift.starts_at)}<p className="dash-meta">{new Date(shift.starts_at + (shift.starts_at.endsWith("Z") ? "" : "Z")).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZone })}–{new Date(shift.ends_at + (shift.ends_at.endsWith("Z") ? "" : "Z")).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZone })}</p></div>{shift.note && <span className="dash-meta">{shift.note}</span>}</li>)}</ul> : <DashboardEmptyState icon={<CalendarDays />} title="No upcoming shifts" href="/app/my-pay" action="View my pay">Your scheduled working hours will appear here once assigned.</DashboardEmptyState>}
    </Card>}

    {canManageWorkspace && <Card className="dash-card">
      <div className="dash-section-heading"><h2>Workspace setup</h2>{checklist && <span className="dash-badge" data-tone={remaining === 0 ? "success" : "neutral"}>{remaining === 0 ? "Complete" : `${doneSteps} of ${totalSteps} complete`}</span>}</div>
      {checklist === null ? <DashboardRetry>Setup status couldn’t load.</DashboardRetry> : <>
        <div className="dash-setup-progress"><ProgressBar value={setupPct} label="Workspace setup completion" /><span className="dash-meta">{setupPct}%</span></div>
        {nextStep ? <div className="dash-next-step"><div><span className="dash-meta">Next step</span><strong>{nextStep.label}</strong></div><WorkspaceAction href={STEP_HREF[nextStep.key] ?? "/app/settings"} className="dash-button dash-primary">{nextStepAction}<ChevronRight aria-hidden="true" /></WorkspaceAction></div> : <div className="dash-next-step"><CircleCheck aria-hidden="true" /><p>{allSetCopy}</p></div>}
        {checklistItems.length > 0 && <details className="dash-checklist"><summary><ChevronRight aria-hidden="true" />View all setup steps</summary><ul>{checklistItems.map(item => <li key={item.key}>{item.done ? <Check data-complete="true" aria-label="Complete" /> : <Circle aria-label="Incomplete" />}<span>{item.label}</span>{!item.done && <WorkspaceAction href={STEP_HREF[item.key] ?? "/app/settings"} label={`Open: ${item.label}`} className="dash-button dash-ghost">Open<ChevronRight aria-hidden="true" /></WorkspaceAction>}</li>)}</ul></details>}
      </>}
    </Card>}

    {canManageWorkspace && <Card className="dash-card">
      {saas === null ? <><h2>Workspace plan</h2><DashboardRetry>Plan details couldn’t load.</DashboardRetry></> : <div className="dash-plan">
        <div><h2>Workspace plan</h2><div className="dash-plan-name"><CreditCard aria-hidden="true" /><strong>{titleCase(saas.saas_tier)}</strong><span className="dash-badge" data-tone={saasBadgeTone}>{titleCase(saas.saas_status)}</span>{org && <span className="dash-badge" data-tone={org.gym_status === "open" ? "success" : "neutral"}>{titleCase(org.gym_status)}</span>}</div></div>
        <div className="dash-plan-meter"><span className="dash-meta">{dashboardNumber(saas.current_member_count)} of {saas.member_cap === null ? "unlimited" : dashboardNumber(saas.member_cap)} members</span>{memberCapPct !== null && <ProgressBar value={memberCapPct} label="Member capacity used" />}</div>
        <div className="dash-plan-footer"><span className="dash-meta">{saas.current_period_end ? `Renews ${fmtDate(saas.current_period_end)}` : "No renewal scheduled"}</span><Link href="/app/billing" className="dash-button dash-secondary">Manage plan<ChevronRight aria-hidden="true" /></Link></div>
      </div>}
    </Card>}
  </div>;
}
