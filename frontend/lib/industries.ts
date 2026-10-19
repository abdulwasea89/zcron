// TypeScript mirror of the backend Industry registry (backend/app/core/industry.py).
// The registry is the single source of truth for what differs between venue
// verticals: gym (gyms & fitness), office (serviced/coworking space, B2B
// invoicing), academy (education, term tuition paid by guardians).
//
// Keeping a static mirror here (rather than only fetching /api/v1/industries)
// lets server + client components derive nav, labels and onboarding copy
// synchronously and with the same guarantees as the backend default of "gym".

export type IndustryKey = "gym" | "office" | "academy";
export type OfferKindKey = "membership" | "space" | "course";
export type MoneyModeKey = "consumer_connect" | "b2b_invoice";
export type ScheduleKindKey = "classes" | "space" | "cohorts";

export type RoleKey = "owner" | "manager" | "trainer" | "front_desk" | "member";

export interface RoleLabels {
  owner: string;
  manager: string;
  trainer: string;
  front_desk: string;
  member: string;
}

export interface IndustryMeta {
  key: IndustryKey;
  /** Human label, e.g. "Education academy" (registration picker card title). */
  label: string;
  tagline: string;
  money: MoneyModeKey;
  offerKind: OfferKindKey;
  schedule: ScheduleKindKey;
  requiresConnect: boolean;
  orgCodeFallbackPrefix: string;
  defaultCurrency: string;
  defaultAccent: string;
  /** Ordered onboarding checklist step codes (subset of the backend labels). */
  checklist: string[];
  /** Enabled feature modules. A route's module drives nav visibility. */
  modules: string[];
  rolesLabels: RoleLabels;
  memberNoun: string;
  payerNoun: string;
  offerSchemaName: string;
  analyticsHeadline: string[];
  /** Short venue noun used to build onboarding copy ("gym" | "space" | "academy"). */
  shortNoun: string;
  /** Example venue name used as a form placeholder. */
  sampleName: string;
  /** Header label of the offer/plan builder page for this vertical. */
  offerPageTitle: string;
  /** Caption under the offer/plan builder page title. */
  offerPageSubtitle: string;
  /** Button label for a new offer on the builder page. */
  offerNewLabel: string;
}

const ROLE_LABELS = {
  owner: "Owner",
  manager: "Manager",
  trainer: "Trainer",
  front_desk: "Front desk",
  member: "Member",
};

export const INDUSTRIES: Record<IndustryKey, IndustryMeta> = {
  gym: {
    key: "gym",
    label: "Gym & fitness",
    tagline: "Gyms, studios and fitness clubs",
    money: "consumer_connect",
    offerKind: "membership",
    schedule: "classes",
    requiresConnect: true,
    orgCodeFallbackPrefix: "GYM",
    defaultCurrency: "USD",
    defaultAccent: "brand",
    checklist: ["stripe", "offer", "enroll", "staff", "done"],
    modules: [
      "dashboard", "assistant", "analytics", "offers", "members", "leads", "referrals", "payments",
      "cash", "receipts", "tasks", "classes", "attendance", "inbox",
      "visitors", "staff", "audit", "approvals", "payroll", "billing", "account", "settings",
    ],
    rolesLabels: ROLE_LABELS,
    memberNoun: "member",
    payerNoun: "member",
    offerSchemaName: "gym-offer.json",
    analyticsHeadline: ["active_members", "today_revenue", "today_checkins", "pending_approvals"],
    shortNoun: "gym",
    sampleName: "Iron Pulse Boxing",
    offerPageTitle: "Membership plans",
    offerPageSubtitle: "Owner-defined plans shown to members at signup",
    offerNewLabel: "New plan",
  },
  office: {
    key: "office",
    label: "Corporate offices",
    tagline: "Serviced offices & coworking space for companies",
    money: "b2b_invoice",
    offerKind: "space",
    schedule: "space",
    requiresConnect: false,
    orgCodeFallbackPrefix: "OFF",
    defaultCurrency: "USD",
    defaultAccent: "brand",
    checklist: ["companies", "offer", "invoices", "staff", "done"],
    modules: [
      "dashboard", "assistant", "analytics", "offers", "companies", "invoices",
      "space", "members", "leads", "payments", "cash", "tasks", "inbox", "visitors",
      "staff", "audit", "approvals", "payroll", "billing", "account", "settings",
    ],
    rolesLabels: {
      owner: "Owner",
      manager: "Manager",
      trainer: "Space manager",
      front_desk: "Reception / Concierge",
      member: "Seat-holder",
    },
    memberNoun: "seat-holder",
    payerNoun: "company",
    offerSchemaName: "office-offer.json",
    analyticsHeadline: ["occupied_seats", "occupancy_pct", "space_mrr", "outstanding_invoices"],
    shortNoun: "space",
    sampleName: "Downtown Serviced Offices",
    offerPageTitle: "Space plans",
    offerPageSubtitle: "Desk, room & office offers billed to companies",
    offerNewLabel: "New plan",
  },
  academy: {
    key: "academy",
    label: "Education academy",
    tagline: "Tutoring centres, skill academies & coaching institutes",
    money: "consumer_connect",
    offerKind: "course",
    schedule: "cohorts",
    requiresConnect: true,
    orgCodeFallbackPrefix: "ACAD",
    defaultCurrency: "USD",
    defaultAccent: "brand",
    checklist: ["courses", "offer", "enroll", "staff", "done"],
    modules: [
      "dashboard", "assistant", "analytics", "offers", "courses", "attendance",
      "members", "leads", "referrals", "payments", "cash", "receipts", "tasks", "inbox",
      "visitors", "staff", "audit", "approvals", "payroll", "billing", "account", "settings",
    ],
    rolesLabels: {
      owner: "Owner",
      manager: "Manager",
      trainer: "Teacher",
      front_desk: "Registrar",
      member: "Student",
    },
    memberNoun: "student",
    payerNoun: "guardian",
    offerSchemaName: "academy-offer.json",
    analyticsHeadline: ["enrolled_students", "term_fee_collected", "attendance_rate", "pending_enrollments"],
    shortNoun: "academy",
    sampleName: "Bright Minds Academy",
    offerPageTitle: "Fee plans",
    offerPageSubtitle: "Term tuition offers for course batches",
    offerNewLabel: "New fee plan",
  },
};

/** Ordered catalog — the order registration pickers present the options in. */
export const INDUSTRY_LIST: readonly IndustryMeta[] = [
  INDUSTRIES.gym,
  INDUSTRIES.office,
  INDUSTRIES.academy,
];

const LEGACY_GYM_VALUES = new Set(["gym_fitness"]);

/** Coerce a stored/legacy value into a canonical IndustryKey (default gym). */
export function normalizeIndustryKey(value?: string | null): IndustryKey {
  const v = (value ?? "").trim().toLowerCase();
  if (LEGACY_GYM_VALUES.has(v)) return "gym";
  return v === "office" || v === "academy" ? v : "gym";
}

/** Resolve an IndustryMeta by key; unknown/empty values fall back to gym. */
export function getIndustry(key?: string | null): IndustryMeta {
  return INDUSTRIES[normalizeIndustryKey(key)];
}

/** Pluralize a simple member/payer noun ("member" → "members"). */
export function pluralize(noun: string): string {
  return /(?:[^aeiou]y|company)$/i.test(noun) && noun.endsWith("y")
    ? noun.slice(0, -1) + "ies"
    : noun + "s";
}

/** The role label for a vertical, keyed by backend role value. */
export function roleLabelOf(meta: IndustryMeta, role: string): string {
  switch (role) {
    case "owner":
      return meta.rolesLabels.owner;
    case "manager":
      return meta.rolesLabels.manager;
    case "trainer":
      return meta.rolesLabels.trainer;
    case "front_desk":
      return meta.rolesLabels.front_desk;
    case "member":
      return meta.rolesLabels.member;
    default:
      return meta.rolesLabels.member;
  }
}

// ---------------------------------------------------------------------------
// Sidebar navigation. The canonical, gym-reference item list lives in
// components/Sidebar.tsx (with its icons). These two tables let any industry
// filter that list to its enabled modules and swap venue-specific labels,
// without forking the component.

/** Maps each sidebar route to the registry module that gates it. */
export const NAV_MODULE_BY_HREF: Record<string, string> = {
  "/app": "dashboard",
  "/app/assistant": "assistant",
  "/app/analytics": "analytics",
  "/app/plans": "offers",
  "/app/companies": "companies",
  "/app/invoices": "invoices",
  "/app/space": "space",
  "/app/members": "members",
  "/app/onboarding": "members",
  "/app/leads": "leads",
  "/app/referrals": "referrals",
  "/app/payments": "payments",
  "/app/cash": "cash",
  "/app/receipts": "receipts",
  "/app/tasks": "tasks",
  "/app/classes": "classes",
  "/app/attendance": "attendance",
  "/app/inbox": "inbox",
  "/app/front-desk": "visitors",
  "/app/staff": "staff",
  "/app/audit": "audit",
  "/app/approvals": "approvals",
  "/app/payroll": "payroll",
  "/app/billing": "billing",
  "/app/account": "account",
  "/app/settings": "settings",
};

/** Venue-specific nav labels, keyed by industry then route. The gym reference
 *  labels are the default in the Sidebar, so gym needs no entry here. */
export const NAV_LABEL_OVERRIDES: Partial<Record<IndustryKey, Record<string, string>>> = {
  office: {
    "/app/plans": "Space plans",
    "/app/members": "Seat-holders",
    "/app/space": "Desks & rooms",
  },
  academy: {
    "/app/plans": "Fee plans",
    "/app/members": "Students",
  },
};

/** Which vertical an admin page belongs to (for module gating). Pages whose
 *  module isn't enabled for the active org's industry redirect to /app. */
export const PAGE_MODULE_BY_HREF: Record<string, string> = {
  "/app/companies": "companies",
  "/app/invoices": "invoices",
  "/app/space": "space",
  "/app/attendance": "attendance",
  "/app/inbox": "inbox",
  "/app/front-desk": "visitors",
};
