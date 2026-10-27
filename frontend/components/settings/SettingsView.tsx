"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { AccountFields, emptyAccountFields, type AccountFieldsValue } from "@/components/settings/AccountFields";
import { AuditWorkspace } from "@/components/settings/AuditWorkspace";
import { BillingWorkspace } from "@/components/settings/BillingWorkspace";
import { MfaCard } from "@/app/app/account/MfaCard";
import { DataRequestsSection } from "@/components/settings/DataRequestsSection";
import { LeadCaptureIntegrationsSection } from "@/components/LeadCaptureIntegrationsSection";
import { LeadFollowupTemplatesSection } from "@/components/LeadFollowupTemplatesSection";
import { LiveIndicator } from "@/components/Realtime";
import { Alert, Badge, Button, Input, Select, Spinner } from "@/components/ui";
import { Row, ReadValue, Section } from "@/components/settings/primitives";
import { getIndustry, NAV_MODULE_BY_HREF } from "@/lib/industries";
import { api, ApiError } from "@/lib/api";
import { fmtDate, gymStatusLabel, statusTone, titleCase } from "@/lib/format";
import { THEME_OPTIONS } from "@/lib/themes";
import type { AdminSessionInfo, HeadlineMetrics, InvoiceSettings, OrganizationOut, ProfileOut } from "@/lib/types";

/* Notion-style settings: a left section rail and a right pane of rows, each a
   label + description on the left and a control on the right, separated by
   hairlines. Edits are staged and committed by ONE global Save bar; nothing is
   written until you press it. */

interface Baseline {
  name: string;
  enrollment: string;
  gymStatus: string;
  invoice: InvoiceSettings | null;
  account: AccountFieldsValue;
  dailyBriefEmail: boolean;
}

/** Row labels per section, so the rail search can match the things inside. */
const SECTION_KEYWORDS: Record<string, string[]> = {
  account: ["profile", "name", "email", "phone", "password", "mfa", "two-factor"],
  organization: [
    "name", "code", "industry", "status", "currency", "timezone", "plan",
    "subscription", "member", "mfa", "created",
  ],
  preferences: ["theme", "connection", "enrollment", "daily brief", "email"],
  tools: ["staff", "payroll", "receipts", "workspace", "manage"],
  invoice: ["legal", "tax", "vat", "address", "payment terms"],
  payments: ["stripe", "connect", "payments"],
  channels: ["inbox", "email", "sms", "whatsapp", "telegram", "line", "twilio", "smtp", "webhook", "instagram", "messenger", "wechat", "meta", "chat"],
  billing: ["subscription", "plan", "tier", "saas", "invoice"],
  audit: ["audit", "log", "activity", "trail", "history"],
  sessions: ["sessions", "devices", "login"],
  security: ["rotate", "code", "security"],
  privacy: ["privacy", "data", "request", "export", "erasure", "consent"],
};

/** Rail icons. */
const NAV_ICON: Record<string, string> = {
  building: "M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3H21m-3.75 3H21",
  sliders: "M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75",
  doc: "M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z",
  card: "M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z",
  shield: "M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z",
  lock: "M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z",
  person: "M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z",
  message: "M7.5 8.25h9m-9 3h6m-9.75 8.25l2.879-2.879A9 9 0 1112 21a8.963 8.963 0 01-4.371-1.129L3.75 19.5z",
};

/** Remembers the last settings tab the user opened, so reopening the dialog
 *  returns them there instead of always resetting to Organization. */
const SETTINGS_TAB_KEY = "acron.settings.tab";

export function SettingsView({ onNavigate }: { onNavigate?: () => void }) {
  const [org, setOrg] = useState<OrganizationOut | null>(null);
  const [metrics, setMetrics] = useState<HeadlineMetrics | null>(null);
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [role, setRole] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState<string>(() => {
    // The dialog only mounts client-side, but guard anyway so SSR is stable.
    if (typeof window === "undefined") return "organization";
    return window.localStorage.getItem(SETTINGS_TAB_KEY) ?? "organization";
  });

  const selectTab = useCallback((id: string) => {
    setActive(id);
    try {
      window.localStorage.setItem(SETTINGS_TAB_KEY, id);
    } catch {
      // Private mode / storage disabled: remembering the tab is best-effort.
    }
  }, []);

  // Editable state.
  const [name, setName] = useState("");
  const [enrollment, setEnrollment] = useState("open");
  const [gymStatus, setGymStatus] = useState("open");
  const [invoice, setInvoice] = useState<InvoiceSettings | null>(null);
  const [account, setAccount] = useState<AccountFieldsValue>(emptyAccountFields);
  const [dailyBriefEmail, setDailyBriefEmail] = useState(false);
  // The values as last loaded, to detect unsaved changes and to discard.
  const [baseline, setBaseline] = useState<Baseline | null>(null);

  async function load() {
    setError("");
    try {
      const [o, identity] = await Promise.all([
        api.get<OrganizationOut>("/organizations/me"),
        api.get<{ role: string }>("/auth/me"),
      ]);
      setOrg(o);
      setRole(identity.role);
      // Headline metrics and profile are secondary: a failure must not block
      // the organization settings that this dialog exists for.
      const m = await api
        .get<HeadlineMetrics>("/analytics/headline")
        .catch(() => null);
      setMetrics(m);
      const p = await api.get<ProfileOut>("/auth/me/profile").catch(() => null);
      setProfile(p);
      const briefEmail = p?.daily_brief_email ?? false;
      const inv = o.industry === "office"
        ? await api.get<InvoiceSettings>("/organizations/me/invoice-settings")
        : null;
      const acc: AccountFieldsValue = p
        ? {
            full_name: p.full_name ?? "",
            phone: p.phone ?? "",
            address: p.address ?? "",
            city: p.city ?? "",
            occupation: p.occupation ?? "",
            education: p.education ?? "",
            emergency_contact: p.emergency_contact ?? "",
          }
        : emptyAccountFields;
      setName(o.name);
      setEnrollment(o.enrollment_mode);
      setGymStatus(o.gym_status);
      setInvoice(inv);
      setAccount(acc);
      setDailyBriefEmail(briefEmail);
      setBaseline({
        name: o.name,
        enrollment: o.enrollment_mode,
        gymStatus: o.gym_status,
        invoice: inv,
        account: acc,
        dailyBriefEmail: briefEmail,
      });
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  useEffect(() => {
    queueMicrotask(() => void load());
  }, []);

  // The remembered tab may not exist for this org (e.g. Invoice details is
  // office-only). Fall back to Organization rather than showing a blank pane.
  useEffect(() => {
    if (!org) return;
    const valid = [
      "account", "organization", "preferences", "tools", "billing", "sessions", "security", "audit", "channels",
      ...(role === "owner" || role === "manager" ? ["privacy"] : []),
      ...(invoice ? ["invoice"] : []),
      ...(org.industry !== "office" ? ["payments"] : []),
    ];
    if (!valid.includes(active)) queueMicrotask(() => selectTab("organization"));
  }, [org, invoice, active, role, selectTab]);

  const dirty = useMemo(() => {
    if (!baseline) return false;
    return (
      name.trim() !== baseline.name ||
      enrollment !== baseline.enrollment ||
      gymStatus !== baseline.gymStatus ||
      JSON.stringify(invoice) !== JSON.stringify(baseline.invoice) ||
      JSON.stringify(account) !== JSON.stringify(baseline.account)
      || dailyBriefEmail !== baseline.dailyBriefEmail
    );
  }, [baseline, name, enrollment, gymStatus, invoice, account, dailyBriefEmail]);

  async function saveAll() {
    if (!org || !baseline) return;
    setError("");
    setNotice("");
    setSaving(true);
    const failures: string[] = [];

    const attempt = async (label: string, fn: () => Promise<unknown>) => {
      try {
        await fn();
      } catch (e) {
        failures.push(`${label}: ${(e as ApiError).message}`);
      }
    };

    if (name.trim() !== baseline.name) {
      await attempt("Name", () =>
        api.patch("/organizations/me/name", { name: name.trim() }),
      );
    }
    if (enrollment !== baseline.enrollment) {
      await attempt("Enrollment", () =>
        api.patch("/organizations/me/enrollment", { enrollment_mode: enrollment }),
      );
    }
    if (gymStatus !== baseline.gymStatus) {
      await attempt("Status", () =>
        api.patch("/organizations/me/gym-status", { gym_status: gymStatus }),
      );
    }
    if (invoice && JSON.stringify(invoice) !== JSON.stringify(baseline.invoice)) {
      await attempt("Invoice details", () =>
        api.put("/organizations/me/invoice-settings", {
          legal_name: invoice.legal_name || null,
          address: invoice.address || null,
          tax_id: invoice.tax_id || null,
          payment_terms_days: invoice.payment_terms_days,
        }),
      );
    }
    if (JSON.stringify(account) !== JSON.stringify(baseline.account)) {
      await attempt("Profile", () =>
        api.patch("/auth/me/profile", {
          full_name: account.full_name || null,
          phone: account.phone || null,
          address: account.address || null,
          city: account.city || null,
          occupation: account.occupation || null,
          education: account.education || null,
          emergency_contact: account.emergency_contact || null,
        }),
      );
    }
    if (dailyBriefEmail !== baseline.dailyBriefEmail) {
      await attempt("Daily brief email", () =>
        api.patch("/auth/me/profile", { daily_brief_email: dailyBriefEmail }),
      );
    }

    await load();
    setSaving(false);
    if (failures.length) setError(failures.join(" · "));
    else setNotice("Settings saved.");
  }

  function discard() {
    if (!baseline) return;
    setName(baseline.name);
    setEnrollment(baseline.enrollment);
    setGymStatus(baseline.gymStatus);
    setInvoice(baseline.invoice);
    setAccount(baseline.account);
    setDailyBriefEmail(baseline.dailyBriefEmail);
    setError("");
    setNotice("");
  }

  async function connectStripe() {
    setError("");
    try {
      const res = await api.post<{ onboarding_url: string }>("/organizations/me/connect");
      window.open(res.onboarding_url, "_blank");
      setNotice("Stripe onboarding started in a new tab.");
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function rotateCode() {
    setError("");
    setNotice("");
    if (!confirm("Rotate the org code? The old code stops working immediately and member sessions are revoked.")) return;
    try {
      const res = await api.post<{ org_code: string }>("/organizations/me/rotate-code");
      setNotice(`New org code: ${res.org_code}`);
      load();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  function setInv<K extends keyof InvoiceSettings>(key: K, value: InvoiceSettings[K]) {
    setInvoice((v) => (v ? { ...v, [key]: value } : v));
  }

  if (org === null && !error) return <Spinner label="Loading settings..." />;

  const industry = getIndustry(org?.industry);
  const toolLinks = [
    { label: "Staff", href: "/app/staff", description: "Team members, roles and shifts" },
    { label: "Payroll", href: "/app/payroll", description: "Pay runs and staff entries" },
    { label: "Receipts", href: "/app/receipts", description: "Review submitted receipts" },
  ].filter((item) => industry.modules.includes(NAV_MODULE_BY_HREF[item.href]));

  // Grouped rail (Notion settings modal): Account / Preferences / Billing / Security.
  const navGroups = org
    ? [
        {
          label: "Account",
          items: [
            { id: "account", label: "My account", icon: NAV_ICON.person },
            { id: "organization", label: "Organization", icon: NAV_ICON.building },
          ],
        },
        { label: "Preferences", items: [{ id: "preferences", label: "Preferences", icon: NAV_ICON.sliders }] },
        { label: "Communications", items: [{ id: "channels", label: "Inbox channels", icon: NAV_ICON.message }] },
        ...(toolLinks.length ? [{ label: "Workspace", items: [{ id: "tools", label: "Workspace tools", icon: NAV_ICON.building }] }] : []),
        {
          label: "Billing",
          items: [
            ...(invoice ? [{ id: "invoice", label: "Invoice details", icon: NAV_ICON.doc }] : []),
            { id: "billing", label: "Subscription", icon: NAV_ICON.card },
            ...(org.industry !== "office" ? [{ id: "payments", label: "Payments", icon: NAV_ICON.card }] : []),
          ],
        },
        ...(role === "owner" || role === "manager" ? [{
          label: "Privacy",
          items: [{ id: "privacy", label: "Data requests", icon: NAV_ICON.shield }],
        }] : []),
        {
          label: "Security",
          items: [
            { id: "sessions", label: "Sessions", icon: NAV_ICON.shield },
            { id: "security", label: "Security", icon: NAV_ICON.lock },
            { id: "audit", label: "Audit log", icon: NAV_ICON.doc },
          ],
        },
      ]
    : [];

  const q = query.trim().toLowerCase();
  const matches = (item: { id: string; label: string }) =>
    !q ||
    item.label.toLowerCase().includes(q) ||
    (SECTION_KEYWORDS[item.id] ?? []).some((k) => k.includes(q));
  const visibleGroups = navGroups
    .map((g) => ({ ...g, items: g.items.filter(matches) }))
    .filter((g) => g.items.length > 0);

  return (
    <div className="flex h-full flex-col">
      {error && <div className="mb-4 shrink-0"><Alert>{error}</Alert></div>}
      {notice && <div className="mb-4 shrink-0 animate-slide-down"><Alert tone="success">{notice}</Alert></div>}

      {org && (
        <div className="flex min-h-0 flex-1 gap-10">
          {/* Section rail (Notion settings modal). */}
          <nav className="no-scrollbar w-56 shrink-0 overflow-y-auto pr-1">
            <div className="relative mb-3">
              <svg className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search settings"
                aria-label="Search settings"
                className="h-8 w-full rounded-md border border-[var(--border)] bg-[var(--surface)] pl-8 pr-2 text-[12px] text-foreground placeholder:text-muted-foreground transition-colors hover:border-foreground/20 focus:border-foreground/30 focus:outline-none"
              />
            </div>
            {visibleGroups.length === 0 && (
              <p className="px-2 py-1.5 text-[12px] text-muted-foreground">No matches</p>
            )}
            {visibleGroups.map((g) => (
              <div key={g.label} className="mb-3">
                <p className="px-2 pb-1 text-[10px] font-medium text-muted-foreground">{g.label}</p>
                <div className="space-y-0.5">
                  {g.items.map((item) => {
                    const isActive = active === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => selectTab(item.id)}
                        className={`flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-[12px] transition-colors ${
                          isActive
                            ? "bg-foreground/[0.06] font-medium text-foreground"
                            : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
                        }`}
                      >
                        <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d={item.icon} />
                        </svg>
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>

          {/* The active page. */}
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto pr-1">
            <Section id="organization" title="Organization" description="Manage your workspace's identity and billing" hidden={active !== "organization"}>
              <Row label="Name" description="Your organization's display name">
                <Input size="sm" value={name} onChange={(e) => setName(e.target.value)} placeholder={org.name} />
              </Row>
              <Row label="Organization code" description="Share this with members so they can join">
                <ReadValue>{org.org_code}</ReadValue>
              </Row>
              <Row label="Industry" description="The vertical this workspace runs">
                <ReadValue>{industry.label}</ReadValue>
              </Row>
              <Row label="Status" description="Whether the venue is currently open">
                <Select size="sm" value={gymStatus} onChange={(e) => setGymStatus(e.target.value)}>
                  <option value="open">{gymStatusLabel("open")}</option>
                  <option value="closed">{gymStatusLabel("closed")}</option>
                  <option value="half_day">{gymStatusLabel("half_day")}</option>
                </Select>
              </Row>
              <Row label="Default currency" description="Used for all amounts in this workspace">
                <ReadValue>{org.default_currency}</ReadValue>
              </Row>
              <Row label="Timezone" description="Dates and reports are shown in this zone">
                <ReadValue>{org.timezone}</ReadValue>
              </Row>
              <Row label="Plan" description="Your SaaS tier">
                <ReadValue>{titleCase(org.saas_tier)}</ReadValue>
              </Row>
              <Row label="Subscription" description="Billing status of the plan">
                <Badge tone={statusTone(org.saas_status)}>{titleCase(org.saas_status)}</Badge>
              </Row>
              <Row label="Member cap" description="Seat limit for your current plan">
                <ReadValue>{org.member_cap ?? "Unlimited"}</ReadValue>
              </Row>
              <Row label="Active members" description="Members with an active membership">
                <ReadValue>{metrics?.active_members ?? "—"}</ReadValue>
              </Row>
              <Row label="MFA required" description="Two-factor enforced for all admins">
                <ReadValue>{org.mfa_required ? "Yes" : "No"}</ReadValue>
              </Row>
              <Row label="Created" description="When this workspace was set up">
                <ReadValue>{fmtDate(org.created_at)}</ReadValue>
              </Row>
            </Section>

            <Section id="account" title="My account" description="Your personal profile and sign-in details" hidden={active !== "account"}>
              <AccountFields
                value={account}
                onChange={(patch) => setAccount((v) => ({ ...v, ...patch }))}
                profile={profile}
              />
              <Row label="Password" description="We'll email you a link to choose a new one">
                <a
                  href="/forgot-password"
                  className="block text-sm font-medium text-brand hover:underline sm:text-right"
                >
                  Reset password
                </a>
              </Row>
            </Section>

            <Section id="preferences" title="Preferences" description="Choose how Acron looks and behaves on this device" hidden={active !== "preferences"}>
              <Row label="Theme" description="How Acron looks on this device">
                <ThemePicker />
              </Row>
              <Row label="Connection" description="Live data sync status">
                <LiveIndicator />
              </Row>
              {(role === "owner" || role === "manager") && (
                <Row label="Daily owner brief" description="Email me a copy of the daily brief alongside the in-app notification">
                  <input
                    aria-label="Email me the daily owner brief"
                    type="checkbox"
                    checked={dailyBriefEmail}
                    onChange={(event) => setDailyBriefEmail(event.target.checked)}
                    className="size-4 accent-brand"
                  />
                </Row>
              )}
              <Row
                label="Enrollment mode"
                description="Controls how new members can join your organization"
              >
                <Select size="sm" value={enrollment} onChange={(e) => setEnrollment(e.target.value)}>
                  <option value="open">Open</option>
                  <option value="approved">Approved</option>
                  <option value="invite_only">Invite-only</option>
                </Select>
              </Row>
            </Section>

            <Section id="channels" title="Inbox channels" description="Connect the providers your team uses to message members" hidden={active !== "channels"}>
              <InboxChannelsSection />
              <LeadCaptureIntegrationsSection />
              {role === "owner" && <LeadFollowupTemplatesSection />}
            </Section>

            <Section id="tools" title="Workspace tools" description="Manage the less frequent administrative work" hidden={active !== "tools"}>
              {toolLinks.map((item) => (
                <Row key={item.href} label={item.label} description={item.description}>
                  <Link href={item.href} onClick={onNavigate} className="text-sm font-medium text-brand hover:underline">
                    Open {item.label.toLowerCase()} →
                  </Link>
                </Row>
              ))}
            </Section>

            {invoice && (
              <Section id="invoice" title="Invoice details" hidden={active !== "invoice"}>
                <Row label="Legal name" description="Printed on invoices to companies">
                  <Input size="sm" value={invoice.legal_name ?? ""} onChange={(e) => setInv("legal_name", e.target.value)} placeholder={org.name} />
                </Row>
                <Row label="Tax / VAT ID" description="Shown on issued invoices">
                  <Input size="sm" value={invoice.tax_id ?? ""} onChange={(e) => setInv("tax_id", e.target.value)} placeholder="e.g. US-12-3456789" />
                </Row>
                <Row label="Billing address" description="Where invoices are addressed">
                  <Input size="sm" value={invoice.address ?? ""} onChange={(e) => setInv("address", e.target.value)} placeholder="Billing address on the invoice" />
                </Row>
                <Row label="Payment terms" description="When company invoices are due">
                  <Select
                    size="sm"
                    value={String(invoice.payment_terms_days ?? 0)}
                    onChange={(e) => setInv("payment_terms_days", parseInt(e.target.value, 10))}
                  >
                    <option value="0">Due on receipt</option>
                    <option value="7">Net 7</option>
                    <option value="14">Net 14</option>
                    <option value="30">Net 30</option>
                    <option value="60">Net 60</option>
                  </Select>
                </Row>
              </Section>
            )}

            {org.industry !== "office" && (
              <Section id="payments" title="Payments" hidden={active !== "payments"}>
                <Row
                  label="Stripe Connect"
                  description="Member fees flow directly into your bank account"
                >
                  <div className="flex items-center gap-2">
                    <Badge tone={statusTone(org.stripe_connect_status)}>
                      {titleCase(org.stripe_connect_status)}
                    </Badge>
                    <Button variant="secondary" onClick={connectStripe}>
                      {org.stripe_connect_status === "active" ? "Manage" : "Connect"}
                    </Button>
                  </div>
                </Row>
              </Section>
            )}

            <Section id="privacy" title="Privacy requests" description="Record and resolve member data requests" hidden={active !== "privacy"}>
              <DataRequestsSection onNavigate={onNavigate} />
            </Section>

            <Section id="sessions" title="Sessions" hidden={active !== "sessions"}>
              <SessionsSection />
            </Section>

            <Section id="security" title="Security" hidden={active !== "security"}>
              <MfaCard mfaRequired={org.mfa_required} />
              <Row
                label="Rotate organization code"
                description="Invalidates the current code everywhere and revokes member sessions authenticated with it."
              >
                <div className="flex justify-end">
                  <Button variant="danger" onClick={rotateCode}>
                    Rotate code
                  </Button>
                </div>
              </Row>
            </Section>

            {/* The full page views are embedded, so there is one implementation
                of each rather than a lookalike. Each renders its own Section. */}
            {active === "billing" && <BillingWorkspace embedded />}
            {active === "audit" && <AuditWorkspace embedded />}
            </div>

            {/* One global Save for every staged edit. */}
            <div className="mt-6 flex shrink-0 items-center justify-between gap-3 border-t border-[var(--border)] pt-4">
              <p className="text-[12px] text-muted-foreground">
                {dirty ? "You have unsaved changes." : "All changes saved."}
              </p>
              <div className="flex items-center gap-2">
                <Button variant="secondary" onClick={discard} disabled={!dirty || saving}>
                  Discard
                </Button>
                <Button onClick={saveAll} loading={saving} disabled={!dirty}>
                  Save changes
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* Theme picker: buttons that call setTheme directly, mirroring the header
   toggle so choosing a theme always takes effect. A swatch makes each option
   readable at a glance. */
function ThemePicker() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  // Hydration guard: the resolved theme is only known client-side.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setMounted(true), []);

  return (
    <div className="grid w-full grid-cols-2 gap-1.5">
      {THEME_OPTIONS.map((o) => {
        const active = mounted && theme === o.value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => setTheme(o.value)}
            aria-pressed={active}
            className={`theme-choice flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-[12px] transition-colors ${
              active
                ? "border-foreground/25 bg-foreground/[0.06] font-medium text-foreground"
                : "border-[var(--border)] text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
            }`}
          >
            <span
              aria-hidden="true"
              className="h-3.5 w-3.5 shrink-0 rounded-full border border-foreground/20"
              style={{ background: o.swatch }}
            />
            <span className="flex-1 truncate">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/** Active sessions, with revoke — shown inline in the settings dialog rather
 *  than on a separate page. */
function SessionsSection() {
  const [sessions, setSessions] = useState<AdminSessionInfo[] | null>(null);
  const [error, setError] = useState("");
  const [revoking, setRevoking] = useState<string | null>(null);
  const [ownerView, setOwnerView] = useState(true);

  const load = useCallback(async () => {
    setError("");
    try {
      setSessions(await api.get<AdminSessionInfo[]>("/auth/admin/sessions"));
      setOwnerView(true);
    } catch (e) {
      if ((e as ApiError).status === 403) {
        try {
          setSessions(await api.get<AdminSessionInfo[]>("/auth/sessions"));
          setOwnerView(false);
        } catch {
          setSessions([]);
        }
      } else {
        setSessions([]);
      }
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  async function revoke(id: string) {
    setRevoking(id);
    setError("");
    try {
      await api.del(`/auth/admin/sessions/${id}`);
      setSessions((prev) => prev?.map((s) => (s.id === id ? { ...s, revoked: true } : s)) ?? null);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setRevoking(null);
    }
  }

  if (sessions === null) {
    return <p className="py-3 text-sm text-muted-foreground">Loading…</p>;
  }
  if (sessions.length === 0) {
    return <p className="py-3 text-sm text-muted-foreground">No active sessions.</p>;
  }
  return (
    <div>
      {error && <p className="py-2 text-[12px] text-[var(--danger)]">{error}</p>}
      {sessions.map((s) => (
        <div key={s.id} className="flex items-center justify-between gap-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm text-foreground">
              {s.device_type || s.os || "Unknown device"}
              {s.current ? " · This device" : ""}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {ownerView ? `${s.user_email} · ` : ""}
              {s.ip_address ?? "—"} · {s.last_activity_at ? new Date(s.last_activity_at).toLocaleString() : "—"}
            </p>
          </div>
          <Button
            variant={s.revoked ? "secondary" : "danger"}
            disabled={s.revoked || revoking === s.id}
            onClick={() => revoke(s.id)}
          >
            {s.revoked ? "Revoked" : "Revoke"}
          </Button>
        </div>
      ))}
    </div>
  );
}

interface InboxConnection {
  channel: string;
  connected: boolean;
  connected_at: string | null;
  webhook_url: string | null;
  voice_webhook_url: string | null;
}

const INBOX_PROVIDERS = [
  { id: "email", title: "Email", detail: "Send with SMTP or Resend. Add Resend inbound signing secret to receive member emails.", fields: [
    ["host", "SMTP host (optional with Resend)", "text"], ["port", "Port", "number"], ["username", "SMTP username", "text"], ["password", "SMTP password", "password"], ["from_email", "Sender email", "email"], ["resend_api_key", "Resend API key (optional)", "password"], ["inbound_webhook_secret", "Resend inbound webhook secret (optional)", "password"],
  ] },
  { id: "sms", title: "SMS · Twilio", detail: "Send and receive SMS, and optionally forward gym calls and follow up on missed lead calls.", fields: [
    ["account_sid", "Account SID", "text"], ["auth_token", "Auth Token", "password"], ["from_number", "Twilio phone number", "text"], ["forward_to_number", "Gym call-forward number (optional, international format)", "tel"],
  ] },
  { id: "whatsapp", title: "WhatsApp · Twilio", detail: "Connect an approved WhatsApp sender in Twilio.", fields: [
    ["account_sid", "Account SID", "text"], ["auth_token", "Auth Token", "password"], ["from_number", "WhatsApp sender", "text"],
  ] },
  { id: "telegram", title: "Telegram", detail: "Connect a bot; Acron registers its secure webhook automatically.", fields: [
    ["bot_token", "Bot token", "password"],
  ] },
  { id: "line", title: "LINE", detail: "Connect a LINE Official Account messaging API channel.", fields: [
    ["access_token", "Channel access token", "password"], ["channel_secret", "Channel secret", "password"],
  ] },
  { id: "instagram", title: "Instagram Messaging", detail: "Connect an Instagram professional account through Meta webhooks and Graph API.", fields: [
    ["sender_id", "Instagram account ID", "text"], ["page_access_token", "Page access token", "password"], ["app_secret", "Meta app secret", "password"], ["verify_token", "Webhook verify token", "password"],
  ] },
  { id: "messenger", title: "Facebook Messenger and lead ads", detail: "Connect your Page inbox and optionally capture leads from approved Facebook forms.", fields: [
    ["sender_id", "Facebook Page ID", "text"], ["page_access_token", "Page access token", "password"], ["app_secret", "Meta app secret", "password"], ["verify_token", "Webhook verify token", "password"],
    ["lead_form_ids", "Lead form IDs (optional, comma-separated)", "text"],
  ] },
  { id: "wechat", title: "WeChat Official Account", detail: "Connect a WeChat Official Account using its customer-service API and plaintext-mode callback.", fields: [
    ["app_id", "App ID", "text"], ["app_secret", "App secret", "password"], ["verify_token", "Webhook token", "password"],
  ] },
  { id: "web_chat", title: "Member web chat", detail: "Enable a public, rate-limited chat link for members and prospects.", fields: [],
  },
] as const;

function InboxChannelsSection() {
  const [connections, setConnections] = useState<InboxConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      setConnections(await api.get<InboxConnection[]>("/inbox/channels"));
    } catch (e) {
      setError((e as ApiError).message || "Could not load inbox connections.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void refresh()); }, [refresh]);

  const startEdit = (id: string) => {
    setError(""); setNotice(""); setValues({}); setEditing(id);
  };

  const submit = async (id: string) => {
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api.put<InboxConnection>(`/inbox/channels/${id}`, { credentials: id === "web_chat" ? { enabled: true } : values });
      setConnections((items) => items.map((item) => item.channel === id ? result : item));
      setEditing(null); setValues({});
      setNotice(`${INBOX_PROVIDERS.find((provider) => provider.id === id)?.title ?? id} ${id === "web_chat" ? "enabled" : "connected and verified"}.`);
      await refresh();
    } catch (e) {
      setError((e as ApiError).message || "Could not connect this provider.");
    } finally { setBusy(false); }
  };

  const disconnect = async (id: string) => {
    const providerName = INBOX_PROVIDERS.find((provider) => provider.id === id)?.title ?? id;
    const webhookNote = ["sms", "whatsapp", "line", "instagram", "messenger", "wechat", "email"].includes(id)
      ? " Remove its webhook URL from the provider console first to stop inbound retries."
      : "";
    if (!window.confirm(`Disconnect ${providerName}? Outbound messages will stop.${webhookNote}`)) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api.del(`/inbox/channels/${id}`);
      setConnections((items) => items.map((item) => item.channel === id ? { ...item, connected: false, connected_at: null, webhook_url: null } : item));
      setNotice(`${INBOX_PROVIDERS.find((provider) => provider.id === id)?.title ?? id} disconnected.`);
    } catch (e) { setError((e as ApiError).message || "Could not disconnect this provider."); }
    finally { setBusy(false); }
  };

  const copyWebhook = async (url: string) => {
    try { await navigator.clipboard.writeText(url); setNotice("Webhook URL copied."); }
    catch { setError("Could not copy the webhook URL. Select and copy it manually."); }
  };

  const connectionFor = (id: string) => connections.find((item) => item.channel === id);
  if (loading) return <p className="py-4 text-sm text-muted-foreground">Loading connected providers…</p>;

  return <div className="space-y-4">
    <p className="text-sm leading-6 text-muted-foreground">Provider credentials are encrypted before storage. Only workspace owners can manage connections. Sending and webhook delivery require a publicly reachable HTTPS API URL.</p>
    {error && <Alert>{error}</Alert>}
    {notice && <Alert tone="success">{notice}</Alert>}
    {INBOX_PROVIDERS.map((provider) => {
      const connection = connectionFor(provider.id);
      const isEditing = editing === provider.id;
      return <div key={provider.id} className="rounded-lg border border-[var(--border)] px-4 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><div className="flex items-center gap-2"><h3 className="text-sm font-medium text-foreground">{provider.title}</h3><Badge tone={connection?.connected ? "success" : "neutral"}>{connection?.connected ? "Connected" : "Not connected"}</Badge></div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{provider.detail}</p>
            {connection?.connected_at && <p className="mt-1 text-[11px] text-muted-foreground">Verified {new Date(connection.connected_at).toLocaleString()}</p>}
          </div>
          {!isEditing && <div className="flex gap-2">
            <Button variant="secondary" onClick={() => startEdit(provider.id)}>{connection?.connected ? "Update" : "Connect"}</Button>
            {connection?.connected && <Button variant="danger" disabled={busy} onClick={() => void disconnect(provider.id)}>Disconnect</Button>}
          </div>}
        </div>
        {connection?.connected && connection.webhook_url && provider.id !== "telegram" && <div className="mt-3 rounded-md bg-foreground/[0.035] p-3">
          <p className="text-xs font-medium text-foreground">{provider.id === "web_chat" ? "Member chat link" : "Provider webhook URL"}</p><p className="mt-1 break-all font-mono text-[11px] text-muted-foreground">{connection.webhook_url}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2"><Button variant="secondary" onClick={() => void copyWebhook(connection.webhook_url!)}>Copy {provider.id === "web_chat" ? "link" : "URL"}</Button><span className="text-[11px] text-muted-foreground">{provider.id === "web_chat" ? "Share this page with members and prospects." : "Add this URL in your provider’s webhook settings. Keep it private."}</span></div>
        </div>}
        {provider.id === "messenger" && <p className="mt-3 text-xs leading-5 text-muted-foreground">For lead ads, enter the form IDs to allow, subscribe the Meta callback to leadgen, and grant the Page token lead-retrieval access. Intake does not grant marketing consent. Leaving form IDs empty disables ad intake.</p>}
        {connection?.connected && provider.id === "sms" && connection.voice_webhook_url && <div className="mt-3 rounded-md bg-foreground/[0.035] p-3">
          <p className="text-xs font-medium text-foreground">Twilio Voice webhook URL</p><p className="mt-1 break-all font-mono text-[11px] text-muted-foreground">{connection.voice_webhook_url}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2"><Button variant="secondary" onClick={() => void copyWebhook(connection.voice_webhook_url!)}>Copy URL</Button><span className="text-[11px] text-muted-foreground">Set this as the Twilio phone number’s incoming voice URL. Calls ring the configured gym number for 20 seconds; missed calls create a staff task, and SMS is sent only with lead consent.</span></div>
        </div>}
        {isEditing && <div className="mt-4 border-t border-[var(--border)] pt-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {provider.fields.map(([key, label, type]) => <label key={key} className="block text-xs text-muted-foreground">{label}
              <input type={type} inputMode={type === "number" ? "numeric" : undefined} autoComplete="off" value={values[key] ?? ""} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))} className="mt-1.5 h-9 w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-foreground outline-none focus:border-brand" />
            </label>)}
            {provider.id === "email" && <label className="flex items-center gap-2 self-end pb-2 text-xs text-muted-foreground"><input type="checkbox" checked={values.use_tls !== "false"} onChange={(event) => setValues((current) => ({ ...current, use_tls: String(event.target.checked) }))} />Use STARTTLS</label>}
          </div>
          <p className="mt-3 text-[11px] text-muted-foreground">{connection?.connected ? "Enter the provider credentials again to replace the saved connection. Saved secrets are never shown." : "Credentials are only sent to the Acron backend for verification and encrypted storage."}</p>
          <div className="mt-4 flex justify-end gap-2"><Button variant="secondary" disabled={busy} onClick={() => { setEditing(null); setValues({}); }}>Cancel</Button><Button disabled={busy} loading={busy} onClick={() => void submit(provider.id)}>{connection?.connected ? "Save connection" : "Verify and connect"}</Button></div>
        </div>}
      </div>;
    })}
    <div className="rounded-md border border-dashed border-[var(--border)] p-3 text-xs leading-5 text-muted-foreground">To enable provider webhooks, set <code>INBOX_PUBLIC_WEBHOOK_BASE_URL</code> to your public HTTPS API address and <code>INBOX_ENCRYPTION_KEY</code> in the backend environment. Telegram webhook registration is automatic; configure the displayed URLs in Twilio, Meta, LINE, WeChat, or Resend. Resend inbound email requires the email.received event and the webhook signing secret.</div>
  </div>;
}
