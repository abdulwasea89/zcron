// TypeScript mirrors of the backend Pydantic schemas (backend/app/schemas).
// Kept intentionally small — only the fields the admin UI consumes.

export type SaasTier = "starter" | "pro" | "enterprise";

export type GymStatus = "open" | "closed" | "half_day";

export interface OrganizationBrief {
  organization_id: string;
  name: string;
  org_code: string;
  role: string;
  member_status: string | null;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  organization_id: string | null;
  role: string | null;
  member_status: string | null;
  requires_mfa: boolean;
  organizations: { id: string; name: string; role: string }[] | null;
}

export interface OrganizationOut {
  id: string;
  name: string;
  org_code: string;
  saas_tier: string;
  saas_status: string;
  enrollment_mode: string;
  gym_status: GymStatus;
  member_cap: number | null;
  stripe_connect_status: string;
  accent_color: string | null;
  logo_url: string | null;
  mfa_required: boolean;
  /** Venue vertical: gym | office | academy (defaults to "gym"). */
  industry: string;
  default_currency: string;
  country: string;
  timezone: string;
  created_at: string;
  /** False until required owner details and first Stripe subscription checkout are verified. */
  onboarding_complete: boolean;
}

export interface SetupChecklist {
  gym_registered: boolean;
  saas_active: boolean;
  stripe_connected: boolean;
  plan_published: boolean;
  enrollment_configured: boolean;
  staff_invited: boolean;
  office_configured: boolean;
  member_signup_unblocked: boolean;
  /** Industry-ordered onboarding steps: [{code,label,done},...] (backend-built). */
  steps?: { code: string; label: string; done: boolean }[];
}

export interface PlanOut {
  id: string;
  name: string;
  public_description: string | null;
  price: number;
  joining_fee: number;
  currency: string;
  tax_mode: string;
  tax_rate: number;
  billing_type: string;
  visibility: string;
  status: string;
  featured: boolean;
  cycle_length: number | null;
  cycle_unit: string | null;
  pack_size: number | null;
  validity_days: number | null;
  audience: string;
  family_capacity: number | null;
  off_peak_start: string | null;
  off_peak_end: string | null;
  included_credits: number | null;
  /** Offer kind (membership | space | course); defaults to membership. */
  offer_kind?: string;
  /** Industry-specific attributes for space/course offers (validated server-side). */
  spec?: Record<string, unknown> | null;
  /** AI-written summary, recorded on first view. Null until generated. */
  summary?: string | null;
}

export interface PlanCreate {
  name: string;
  public_description?: string | null;
  price: number;
  joining_fee?: number;
  billing_type: string;
  visibility?: string;
  cycle_unit?: string | null;
  cycle_length?: number | null;
  pack_size?: number | null;
  validity_days?: number | null;
  featured?: boolean;
  audience?: string;
  family_capacity?: number | null;
  off_peak_start?: string | null;
  off_peak_end?: string | null;
  included_credits?: number | null;
  /** Multi-industry offer shape (defaults to the org's industry offer kind). */
  offer_kind?: string;
  spec?: Record<string, unknown> | null;
}

export interface MemberDirectoryItem {
  member_id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  display_name: string | null;
  photo_url: string | null;
  role: string;
  member_status: string;
  phone: string | null;
  profile_complete: boolean;
  created_at: string;
  fixed_monthly_salary: number | null;
  hourly_rate: number | null;
  per_class_rate: number | null;
  commission_rate: number | null;
  assigned_trainers: string[];
  tags?: string[];
}

export interface MemberSubscriptionOut {
  subscription_id: string;
  plan_id: string;
  plan_name: string;
  plan_price: number;
  price_snapshot: number;
  currency: string;
  billing_type: string;
  status: string;
  started_at: string;
  current_period_end: string | null;
  grace_until: string | null;
  frozen_until: string | null;
  cancelled_at: string | null;
  classes_remaining: number | null;
  credits_allowance: number | null;
  audience: string;
  family_capacity: number | null;
}

export interface PendingPaymentItem {
  kind: string;
  label: string;
  amount: number | null;
  currency: string | null;
  due_at: string | null;
  payment_id: string | null;
}

export interface MemberDetailOut {
  member: MemberDirectoryItem;
  profile: MemberProfile;
  subscription: MemberSubscriptionOut | null;
  payments: PaymentOut[];
  pending_payments: PendingPaymentItem[];
  trainer_assignments: TrainerAssignment[];
  family_owner: { member_id: string; name: string } | null;
  family_members: { member_id: string; name: string }[];
}

export interface MemberProfile {
  display_name: string | null;
  phone: string | null;
  photo_url: string | null;
  emergency_contact: string | null;
  goals: string | null;
  health_notes: string | null;
  id_document_type: string | null;
  id_document_last4: string | null;
  summary: string;
}

export interface TrainerAssignment {
  member_id: string;
  trainer_member_id: string;
  trainer_name: string;
  assigned_at: string;
  active: boolean;
}

export interface ClientAssignment {
  member_id: string;
  member_name: string | null;
  member_email: string;
  member_status: string;
  assigned_at: string;
}

export interface TrainerSessionLog {
  id: string;
  client_member_id: string;
  client_name: string;
  performed_at: string;
  duration_minutes: number;
  focus: string;
  notes: string;
  package_id?: string | null;
}

export interface CashMemberItem {
  member_id: string;
  full_name: string | null;
  email: string;
  member_status: string;
  role: string;
}

export interface HeadlineMetrics {
  today_check_ins: number;
  today_revenue: number;
  pending_receipts: number;
  pending_approvals: number;
  active_members: number;
  // Office vertical KPIs — present only for industry "office" orgs (the
  // backend returns an industry-shaped payload, gym keys absent for office).
  occupied_seats?: number;
  occupancy_pct?: number;
  space_mrr?: number;
  outstanding_invoices?: number;
}

export interface RevenueAnalytics {
  total_revenue: number;
  revenue_by_method: Record<string, number>;
  member_count_by_status: Record<string, number>;
  active_members: number;
  churn_count: number;
  currency: string;
  operating_expenses_by_currency: Record<string, string>;
}

export interface SaasStatusOut {
  saas_tier: string;
  saas_status: string;
  member_cap: number | null;
  current_member_count: number;
  current_period_end: string | null;
  grace_until: string | null;
  read_only: boolean;
  retry_count: number;
  state_changed_at: string | null;
}

export interface InvoiceOut {
  id: string;
  amount: number;
  currency: string;
  status: string;
  created_at: string;
}

export interface ApiError {
  detail: string | { msg: string }[];
}

// ------------------------------------------------------------------ staff
export interface ShiftOut {
  id: string;
  staff_member_id: string;
  checked_in_at: string;
  checked_out_at: string | null;
  status: string;
  hours: number;
}

export interface StaffScheduleOut {
  id: string;
  staff_member_id: string;
  starts_at: string;
  ends_at: string;
  note: string | null;
}

export interface StaffInviteOut {
  id: string;
  code: string;
  role: string;
  email: string | null;
  used: boolean;
}

export interface BookingWithMember {
  reminder_created_at?: string | null;
  reminder_email_accepted?: boolean;
  booking_id: string;
  class_session_id: string;
  member_id: string;
  member_name: string | null;
  member_email: string;
  status: string;
}

// --------------------------------------------------------------- classes
export interface ClassSessionOut {
  id: string;
  title: string;
  trainer_member_id: string | null;
  starts_at: string;
  ends_at: string | null;
  capacity: number;
  booked_count: number;
  trainer_checked_in: boolean;
  cancelled: boolean;
}

export interface ClassSessionCreate {
  title: string;
  trainer_member_id?: string;
  starts_at: string;
  ends_at?: string;
  capacity?: number;
}

// ---------------------------------------------------------------- payroll
export interface PayrollEntry {
  id: string;
  staff_member_id: string;
  fixed: number;
  hourly_amount: number;
  hours_worked: number;
  class_amount: number;
  classes_taught: number;
  commission_amount: number;
  bonus: number;
  deductions: number;
  advance_repayment: number;
  net: number;
  payout_method: string;
  paid_at?: string | null;
  payout_reference?: string | null;
  paid_amount?: number | null;
  pay_stub_url: string | null;
  notes: string | null;
}

export interface PayrollRun {
  id: string;
  period_start: string;
  period_end: string;
  status: string;
  total_gross: number;
  total_deductions: number;
  total_net: number;
  entries: PayrollEntry[];
}

export interface MyPayStatement {
  payroll_run_id: string;
  period_start: string;
  period_end: string;
  run_status: string;
  paid_at: string | null;
  entry_paid_at: string | null;
  payout_reference: string | null;
  paid_amount: number | null;
  fixed: number;
  hourly_amount: number;
  hours_worked: number;
  class_amount: number;
  classes_taught: number;
  commission_amount: number;
  bonus: number;
  deductions: number;
  advance_repayment: number;
  net: number;
  payout_method: string;
}

// --------------------------------------------------------------- receipts
export interface ReceiptReviewItem {
  id: string;
  member_id: string;
  member_name?: string | null;
  plan_id: string | null;
  status: string;
  confidence_score: number | null;
  extracted_amount: number | null;
  extracted_date: string | null;
  extracted_payer: string | null;
  extracted_payee: string | null;
  extracted_txn_id: string | null;
  extracted_method: string | null;
  is_duplicate: boolean;
  flags: string[];
  original_image_url: string | null;
}

// -------------------------------------------------------------------- cash
export interface CashPaymentOut {
  payment_id: string;
  member_id: string;
  amount: number;
  method: string;
  member_status: string;
  receipt_pdf_url: string | null;
}

export interface ReconciliationOut {
  id: string;
  business_date: string;
  system_total: number;
  counted_total: number;
  discrepancy: number;
  performed_by: string;
  alert_triggered: boolean;
}

// --------------------------------------------------------------- payments
export interface PaymentOut {
  id: string;
  member_id: string | null;
  plan_id: string | null;
  kind: string;
  method: string;
  stripe_payment_method_type?: string | null;
  status: string;
  amount: number;
  tax_amount: number;
  plan_price_amount?: number | null;
  joining_fee_amount?: number;
  discount_amount?: number;
  promo_code?: string | null;
  currency: string;
  refunded_amount: number;
  paid_at: string | null;
  created_at: string;
}

// ------------------------------------------------------------------ tasks
export interface TaskOut {
  id: string;
  title: string;
  description: string | null;
  assignee_member_id: string | null;
  deadline: string | null;
  done: boolean;
}

export interface TaskCreate {
  title: string;
  description?: string | null;
  assignee_member_id?: string | null;
  deadline?: string | null;
}

// ------------------------------------------------------------- sessions
export interface AdminSessionInfo {
  id: string;
  user_id: string;
  user_email: string;
  user_name: string | null;
  device_type: string | null;
  os: string | null;
  ip_address: string | null;
  user_agent: string | null;
  last_activity_at: string | null;
  revoked: boolean;
  current: boolean;
}

// --------------------------------------------------------------------- mfa
export interface MfaStatus {
  mfa_enabled: boolean;
}

export interface MfaEnrollResponse {
  secret: string;
  otpauth_uri: string;
  current_code: string;
}

export interface ProfileOut {
  full_name: string | null;
  email: string;
  phone: string | null;
  address: string | null;
  city: string | null;
  occupation: string | null;
  education: string | null;
  emergency_contact: string | null;
  date_of_birth: string | null;
  gender: string | null;
  photo_url: string | null;
  goals: string | null;
  health_notes: string | null;
  id_document_type: string | null;
  id_document_last4: string | null;
  summary: string | null;
  daily_brief_email: boolean;
}

// ------------------------------------------------------------------ audit
export interface AuditLogOut {
  id: string;
  action: string;
  actor_user_id: string | null;
  actor_email: string | null;
  actor_name: string | null;
  entity_type: string | null;
  entity_id: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface AuditLogPage {
  items: AuditLogOut[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AuditActionGroup {
  domain: string;
  actions: string[];
}

// ------------------------------------------------------------- office (B2B)
// Mirrors backend/app/schemas/{companies,invoices,space}.py. Company = the
// paying tenant; a seat-holder is a member row bound to a company via contract.

export interface CompanyOut {
  id: string;
  name: string;
  status: string;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  billing_email: string | null;
  tax_id: string | null;
  address: string | null;
  notes: string | null;
  created_at: string;
}

export interface CompanyListItem extends CompanyOut {
  seat_capacity: number;
  occupied_seats: number;
  outstanding_total: number;
}

export interface CompanyContractOut {
  id: string;
  company_id: string;
  plan_id: string;
  plan_name: string;
  seats: number;
  price_per_seat: number;
  currency: string;
  term: string;
  room_credits_remaining: number;
  start_date: string;
  end_date: string | null;
  next_billing_at: string;
  status: string;
  notes: string | null;
}

export interface SeatHolderOut {
  member_id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  display_name: string | null;
  member_status: string;
  company_id: string | null;
  profile_complete: boolean;
  joined_at: string | null;
}

export interface SeatHolderInviteOut {
  member_id: string;
  email: string;
  member_status: string;
  email_delivered: boolean;
  invite_code: string;
}

export interface CompanyDetailOut {
  company: CompanyOut;
  contracts: CompanyContractOut[];
  seat_holders: SeatHolderOut[];
}

export interface OfficeInvoiceOut {
  id: string;
  invoice_number: string;
  company_id: string;
  company_name: string | null;
  contract_id: string | null;
  issue_date: string;
  due_date: string;
  status: string;
  subtotal: number;
  tax_amount: number;
  total: number;
  currency: string;
  line_items: Record<string, unknown>[];
  notes: string | null;
  paid_amount: number;
  paid_at: string | null;
}

export interface InvoiceLineItem {
  description: string;
  quantity: number;
  unit_amount: number;
  amount: number;
}

export interface OfficeInvoicePaymentOut {
  id: string;
  invoice_id: string;
  method: string;
  amount: number;
  currency: string;
  note: string | null;
  paid_at: string;
}

export interface SpaceSlotOut {
  id: string;
  category: string;
  title: string;
  starts_at: string;
  ends_at: string | null;
  capacity: number;
  booked_count: number;
  cancelled: boolean;
}

export interface SpaceBookingOut {
  booking_id: string;
  status: string;
  slot: SpaceSlotOut;
}

/** Org B2B invoice template — what appears on an issued invoice. */
export interface InvoiceSettings {
  legal_name: string | null;
  address: string | null;
  tax_id: string | null;
  payment_terms_days: number | null;
}

// ---- Assistant (grounded chat over this org's data) ----

/** One reasoning or tool step in an assistant turn (ADR 018).
 *
 *  Stored with the message so the transcript can show the steps behind an
 *  answer after a reload, the way a chat assistant does. */
export type AssistantStep =
  | { type: "thinking"; text: string }
  | {
      type: "tool";
      name: string;
      args?: Record<string, unknown>;
      summary?: string;
      /** False while the tool is still running. */
      done?: boolean;
    }
  | AssistantAgentStep
  | AssistantSwarmStep;

/** What a swarm turn cost (ADR 019), as one step for the whole turn.
 *
 *  Only two of these reach the UI: `total`, which the header counts, and
 *  `turn_ms`, which it times. The rest are recorded because they are what the
 *  turn's cost argument rests on and they are cheap to store — but the header
 *  was deliberately reduced to "Worked · 45 agents" over a seconds line, and a
 *  row of counters above the tree competed with it. */
export interface AssistantSwarmStep {
  type: "swarm";
  /** Specialists that were dispatched. */
  agents: number;
  /** Domain orchestrators that ran. */
  domains: number;
  /** agents + domains — the number the header counts. */
  total: number;
  /** Model calls this turn made, counted rather than estimated. */
  model_calls: number;
  done: number;
  skipped: number;
  failed: number;
  /** Wall-clock of the fan-out alone, excluding the planner and the answer. */
  fanout_ms: number;
  /** Wall-clock of the whole turn, planner to answer, in milliseconds.
   *
   *  This is the number the header shows under "Worked · N agents". It is sent
   *  by the server and stored with the turn rather than measured in the browser,
   *  because the client's own stopwatch starts when the panel mounts and dies
   *  with the page — a reloaded thread would show no duration at all. */
  turn_ms: number;
}

/** One agent in a swarm turn (ADR 019): a specialist, or the orchestrator over
 *  one domain's specialists.
 *
 *  A row is opened by the `agent_start` frame, which carries everything the
 *  collapsed row shows — name, specialization and *why it ran*. It is settled
 *  by `agent_done`, which is matched by `id` rather than by position: unlike
 *  tools (which run one at a time), the swarm's agents run concurrently and
 *  finish out of order, so position would attribute a finding to the wrong
 *  agent. */
export interface AssistantAgentStep {
  type: "agent";
  id: string;
  name: string;
  /** One of the five domain ids: members, revenue, payroll, operations, risk. */
  domain: string;
  role?: "specialist" | "orchestrator";
  /** What this agent is for, shown as a chip beside its name. */
  specialization?: string;
  /** Why it was dispatched — the "why this happens" on an expanded row. */
  why?: string;
  /** True when this agent calls the model. Carried for the cost breakdown;
   *  deliberately not shown as a per-row label — see AgentTree. */
  model_backed?: boolean;
  /** The lookup this agent performs, named like a call (`read_member_growth`).
   *  Every agent has one, not only the model-backed eight: thirty-two of the
   *  forty read the database, which is work worth naming. */
  tool?: string;
  /** Absent while the agent is still running. */
  status?: "done" | "skipped" | "failed";
  /** Its finding, or an orchestrator's digest. */
  summary?: string;
  /** The rows behind a judgement agent's finding, or a team's raw findings
   *  behind an orchestrator's digest. Absent for a deterministic specialist,
   *  whose summary *is* the figure. */
  detail?: string;
  /** How long it took, once settled. */
  ms?: number;
}

export interface AssistantMessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Model that produced the turn; null for the offline stub. */
  model: string | null;
  error: string | null;
  created_at: string;
  /** Reasoning + tool steps that produced this turn, or null. */
  steps?: AssistantStep[] | null;
  /** Thumbs rating the user left on this turn ("up" | "down"), or null. */
  feedback?: "up" | "down" | null;
}

export interface AssistantConversationOut {
  id: string;
  title: string;
  last_message_at: string;
  created_at: string;
}

export interface AssistantConversationDetailOut extends AssistantConversationOut {
  messages: AssistantMessageOut[];
}

/** Frames the stream endpoint emits, in order: thinking and/or deltas, then done or error.
 *
 *  `thinking` carries the model's reasoning trace, which lands *before* any
 *  answer text. Reasoning and tool steps are shown in an activity panel ahead
 *  of the answer and are persisted with the turn (see AssistantStep).
 *
 *  Agent runs (ADR 018) add tool activity and a confirmation pause:
 *  `tool_start`/`tool_result` narrate what the assistant looked up, and
 *  `interrupt` marks a write awaiting the user's approval (resumed through
 *  /api/assistant/resume).
 *
 *  A swarm turn (ADR 019) adds the agent tree in between: `agent_start` opens a
 *  row for each specialist and for each of the five domain orchestrators, and
 *  `agent_done` settles it. The answer then arrives as ordinary `delta` frames,
 *  written by the lead agent that summarised the orchestrators' digests.
 *
 *  A swarm turn emits `thinking` too, on both ends of the fan-out: the planner's
 *  rationale (why this shape) and the lead agent's trace while it weighs the
 *  digests. `swarm_stats` closes the fan-out with what it cost. */
export type AssistantFrame =
  | { delta: string }
  | { thinking: string }
  | { tool_start: { name: string; args: Record<string, unknown> } }
  | { tool_result: { name: string; summary: string } }
  | { agent_start: Omit<AssistantAgentStep, "type" | "status" | "summary" | "detail" | "ms"> }
  | {
      agent_done: {
        id: string;
        status: "done" | "skipped" | "failed";
        summary: string;
        detail?: string;
        ms: number;
      };
    }
  | { swarm_stats: Omit<AssistantSwarmStep, "type"> }
  | { interrupt: { id: string | null; value: unknown }; awaiting_approval?: true }
  | { done: true; message_id: string | null; title: string | null }
  | { error: string };

// ---- Attendance / check-in (#18) ------------------------------------------

export interface AttendanceOut {
  id: string;
  member_id: string;
  member_name: string | null;
  checked_in_at: string;
  method: string;
  source: string;
  class_session_id: string | null;
  note: string | null;
  membership_status?: string | null;
  payment_due?: boolean;
  amount_due?: number | null;
  currency?: string | null;
  birthday_today?: boolean;
  at_risk?: boolean;
  days_since_last_visit?: number | null;
  hint?: string | null;
  credit_consumed?: boolean;
}

export interface CheckInOut extends AttendanceOut {
  membership_status: string;
  payment_due: boolean;
  amount_due: number | null;
  currency: string | null;
  birthday_today: boolean;
  days_since_last_visit: number | null;
  at_risk: boolean;
  visits_today: number;
  hint: string | null;
  credit_consumed: boolean;
  access_warning: string | null;
}

export interface AttendanceSummary {
  today_count: number;
  unique_today: number;
  avg_last_7_days: number;
  dormant_members: number;
}

export interface AttendanceMember {
  member_id: string;
  member_name: string | null;
  member_email: string;
  member_status: string;
  phone: string | null;
  has_attendance_card?: boolean;
  payment_due: boolean;
  amount_due: number | null;
  currency: string | null;
  birthday_today: boolean;
  at_risk: boolean;
  days_since_last_visit: number | null;
  hint: string | null;
}

// ---- Shared team inbox (#20) ----------------------------------------------

export interface InboxMessage {
  id: string;
  direction: "inbound" | "outbound";
  sender_kind: "contact" | "staff" | "ai" | "system";
  sender_user_id: string | null;
  body: string;
  channel: string;
  delivery_status: string | null;
  delivery_error: string | null;
  created_at: string;
}

export interface InboxConversation {
  id: string;
  channel: string;
  contact_handle: string;
  contact_name: string | null;
  member_id: string | null;
  member_name: string | null;
  subject: string | null;
  status: "open" | "pending" | "snoozed" | "resolved";
  assigned_to: string | null;
  assigned_name: string | null;
  last_message_at: string;
  unread_count: number;
  preview: string | null;
  preview_direction: "inbound" | "outbound" | null;
}

export interface InboxThread extends InboxConversation {
  messages: InboxMessage[];
}

export interface InboxStats {
  open: number;
  unassigned: number;
  mine: number;
  resolved: number;
  unread: number;
}

// ---- Front desk: walk-ins & lockers (#22) ---------------------------------

export interface VisitorOut {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  kind: "day_pass" | "guest" | "trial" | "walk_in" | "other";
  host_member_id: string | null;
  host_name: string | null;
  amount: number;
  method: string | null;
  paid: boolean;
  locker_number: string | null;
  note: string | null;
  checked_in_at: string;
  checked_out_at: string | null;
}

export interface LockerOut {
  id: string;
  number: string;
  status: "free" | "occupied";
  holder_label: string | null;
  assigned_at: string | null;
  note: string | null;
}

export interface FrontDeskSummary {
  visitors_today: number;
  inside_now: number;
  day_pass_revenue: number;
  lockers_occupied: number;
  lockers_total: number;
}
