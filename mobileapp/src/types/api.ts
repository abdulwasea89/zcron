export interface OrganizationOut {
  id: string;
  name: string;
  org_code: string;
  saas_tier: string;
  saas_status: string;
  stripe_connect_status?: string;
  gym_status?: string;
  enrollment_mode?: string;
  mfa_required?: boolean;
  timezone?: string;
  currency?: string;
  accent_color?: string;
  logo_url?: string;
  address?: string;
  country?: string;
  /** Venue vertical: gym | office | academy (default gym). */
  industry?: string;
}

export interface AuthUserResponse {
  user_id: string;
  email: string;
  full_name?: string;
  role: string;
  org_id: string;
  member_id?: string | null;
  member_status?: string | null;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: AuthUserResponse;
  requires_mfa?: boolean;
}

/** One row of `GET /auth/my-organizations` (org switcher). */
export interface OrgSummaryResponse {
  organization_id: string;
  name: string;
  org_code: string;
  role: string;
  member_status?: string | null;
  /** Venue vertical: gym | office | academy (default gym). */
  industry?: string;
}

export interface HeadlineMetrics {
  active_members: number;
  today_revenue: number;
  today_check_ins: number;
  pending_receipts: number;
  pending_approvals: number;
}

/** `GET /analytics/revenue` — owner/manager only (view_revenue_analytics). */
export interface RevenueAnalytics {
  total_revenue: number;
  revenue_by_method: Record<string, number>;
  member_count_by_status: Record<string, number>;
  active_members: number;
  churn_count: number;
  currency: string;
}

export interface PlanOut {
  id: string;
  name: string;
  public_description?: string | null;
  price: number;
  currency?: string;
  billing_type: string;
  visibility?: string;
  status?: string;
  featured?: boolean;
}

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

export interface PaymentOut {
  id: string;
  organization_id: string;
  member_id: string;
  plan_id: string | null;
  subscription_id: string | null;
  kind: "saas_subscription" | "member_fee" | "trainer_payout" | "cash" | "refund";
  method: string;
  status: string;
  amount: number;
  tax_amount: number;
  currency: string;
  refunded_amount: number;
  stripe_payment_intent_id: string | null;
  idempotency_key: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface ReceiptReviewItem {
  id: string;
  member_id: string;
  plan_id: string | null;
  status: string;
  confidence_score: number | null;
  extracted_amount: number | null;
  extracted_date: string | null;
  extracted_payer: string | null;
  extracted_payee: string | null;
  is_duplicate: boolean;
  flags: string[];
  original_image_url: string | null;
}

export interface ShiftOut {
  id: string;
  staff_member_id: string;
  checked_in_at: string;
  checked_out_at: string | null;
  status: string;
  hours: number;
}

export interface TaskOut {
  id: string;
  title: string;
  description: string | null;
  assignee_member_id: string | null;
  deadline: string | null;
  done: boolean;
}

export interface MemberDirectoryItem {
  member_id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  display_name: string | null;
  role: string;
  member_status: string;
  phone: string | null;
  profile_complete: boolean;
  created_at: string;
  assigned_trainers: string[];
}

/** `GET /auth/me` — identity + role within the active org. */
export interface MeResponse {
  user_id: string;
  org_id: string;
  role: string;
  member_id: string | null;
  member_status: string | null;
}

export interface ProfileOut {
  full_name?: string;
  email: string;
  phone?: string | null;
  address?: string | null;
  city?: string | null;
  occupation?: string | null;
  education?: string | null;
  emergency_contact?: string | null;
  date_of_birth?: string | null;
  gender?: string | null;
  photo_url?: string | null;
  goals?: string | null;
  health_notes?: string | null;
  id_document_type?: string | null;
  id_document_last4?: string | null;
  summary?: string | null;
}

export interface ProfileUpdateRequest {
  full_name?: string;
  phone?: string | null;
  address?: string | null;
  city?: string | null;
  occupation?: string | null;
  education?: string | null;
  emergency_contact?: string | null;
  photo_url?: string | null;
  goals?: string | null;
  health_notes?: string | null;
  id_document_type?: string | null;
  id_document_last4?: string | null;
}

export interface CashLogPayload {
  member_id: string;
  plan_id: string;
  amount: number;
  method: "cash" | "bank_transfer" | "mobile_wallet";
  notes?: string;
}

export interface ReceiptUploadResult {
  receipt_id: string;
  status: string;
  confidence?: number;
}

// --- Auth Shared -------------------------------------------------------
export interface Message {
  message: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type?: string;
}

export interface MfaStatus {
  mfa_enabled: boolean;
}

export interface MfaEnrollResponse {
  secret: string;
  otpauth_uri: string;
  current_code: string;
}

// --- Owner Registration (Register Gym) --------------------------------
export interface OwnerRegisterStartRequest {
  full_name: string;
  email: string;
  password: string;
  confirm_password: string;
  cnic: string;
  phone: string;
  occupation: string;
  education: string;
  address: string;
  date_of_birth: string;
  gender: "male" | "female" | "other";
  city: string;
  emergency_contact: string;
}

export interface EmailVerifyRequest {
  email: string;
  code: string;
}

export interface ResendCodeRequest {
  email: string;
}

export interface GymDetails {
  name: string;
  country?: string;
  timezone?: string;
  default_currency?: string;
  address?: string | null;
  logo_url?: string | null;
  accent_color?: string | null;
  working_hours?: string | null;
  /** Venue vertical: gym | office | academy (default gym). */
  industry?: string;
}

export interface RegisterGymRequest {
  owner_email: string;
  details: GymDetails;
  tier: "starter" | "pro" | "enterprise";
  payment_token?: string;
}

export interface RegisterGymResponse {
  organization: OrganizationOut;
  access_token: string;
  refresh_token: string;
  token_type?: string;
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
}

// --- Member Signup (Join Gym) -----------------------------------------
export interface SignupStartRequest {
  org_code: string;
  captcha_token?: string | null;
}

export interface SignupStartOut {
  organization_id: string;
  organization_name: string;
  enrollment_mode: string;
  accepting_signups: boolean;
}

export interface SignupEmailRequest {
  org_code: string;
  email: string;
  captcha_token?: string | null;
}

export interface SignupVerifyRequest {
  org_code: string;
  email: string;
  code: string;
}

export interface SignupSetPasswordRequest {
  org_code: string;
  email: string;
  password: string;
}

export interface SignupSetPasswordOut {
  member_id: string;
  organization_id: string;
  member_status: string;
}

export interface PublicPlanOut {
  id: string;
  name: string;
  public_description?: string | null;
  price: number;
  currency: string;
  billing_type: string;
  featured: boolean;
}

export interface SignupPayRequest {
  org_code: string;
  email: string;
  plan_id: string;
  payment_token?: string;
}

export interface ProfileCompleteRequest {
  full_name: string;
  photo_url?: string | null;
  phone?: string | null;
  emergency_contact?: string | null;
}

// --- Login ------------------------------------------------------------
export interface LoginRequest {
  email: string;
  password: string;
  org_code?: string | null;
  organization_id?: string | null;
  remember?: boolean;
  mfa_code?: string | null;
}

export interface MemberLoginRequest {
  org_code: string;
  email: string;
  password: string;
  remember?: boolean;
  mfa_code?: string | null;
}

// --- Magic Link -------------------------------------------------------
export interface MagicLinkRequest {
  org_code: string;
  email: string;
}

export interface MagicLinkVerifyRequest {
  org_code: string;
  email: string;
  token: string;
  remember?: boolean;
  mfa_code?: string | null;
}

// --- Password Reset ---------------------------------------------------
export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirm {
  email: string;
  token: string;
  new_password: string;
}

// --- Invite -----------------------------------------------------------
export interface RedeemInviteRequest {
  org_code: string;
  email: string;
  code: string;
  password: string;
}

// --- Recovery ---------------------------------------------------------
export interface RecoverCodesRequest {
  email: string;
}

// --- MFA --------------------------------------------------------------
export interface MfaConfirmRequest {
  code: string;
}

export interface MfaDisableRequest {
  password: string;
}

// --- Session ----------------------------------------------------------
export interface SessionInfo {
  id: string;
  device_type?: string | null;
  os?: string | null;
  ip_address?: string | null;
  last_activity_at?: string | null;
  revoked?: boolean;
  current?: boolean;
}

// --- Task (staff/admin) -----------------------------------------------
export interface TaskCreateRequest {
  title: string;
  description?: string | null;
  assignee_member_id?: string | null;
  deadline?: string | null;
}

// --- My Bookings (member, GET /classes/my-bookings) -------------------
export interface MyBookingOut {
  booking_id: string;
  status: string;
  class_session: ClassSessionOut;
}

// --- Members approval (admin) -----------------------------------------
export interface ApprovalDecisionRequest {
  approve: boolean;
  reason?: string | null;
}

// --- Cash (staff) ------------------------------------------------------
export interface CashMemberOut {
  member_id: string;
  full_name: string | null;
  email: string;
  member_status: string;
  role: string;
}

export interface CashPaymentOut {
  payment_id: string;
  member_id: string;
  amount: number;
  method: string;
  member_status: string;
  receipt_pdf_url: string | null;
}

export interface ReconciliationRequest {
  business_date: string;
  counted_total: number;
  notes?: string | null;
}

// --- Office vertical: space slots & B2B invoices (seat-holder view) ----
// Shapes mirror the backend office API (app/schemas/space.py, app/schemas/invoices.py).

/** A bookable desk/room slot (ClassSession row with category="space_slot"). */
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

/** A seat-holder's space booking joined with its slot. */
export interface SpaceBookingOut {
  booking_id: string;
  status: string;
  slot: SpaceSlotOut;
}

/** A company invoice (B2B). `GET /invoices/my-company` returns sent/partial. */
export interface InvoiceOut {
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

export interface ReconciliationOut {
  id: string;
  business_date: string;
  system_total: number;
  counted_total: number;
  discrepancy: number;
  performed_by: string;
  alert_triggered: boolean;
}

// --- Receipts (staff review) ------------------------------------------
export interface ReceiptReviewActionRequest {
  action: "approve" | "reject" | "request_info";
  reason?: string | null;
}

// --- Notifications --------------------------------------------------
export type NotificationCategory =
  | "approval"
  | "receipt"
  | "receipt_review"
  | "payment"
  | "task"
  | "membership"
  | "cash"
  | "system";

export interface NotificationOut {
  id: string;
  category: NotificationCategory;
  title: string;
  body: string;
  data?: Record<string, unknown> | null;
  read: boolean;
  created_at: string;
}

export interface UnreadCountOut {
  count: number;
}
