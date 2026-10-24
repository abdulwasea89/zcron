# Blueprint vs Codebase — Full Feature Status List

> **Superseded summary:** Use the [root audit](../BLUEPRINT_AUDIT.md) and [complete feature matrix](full-feature-table.md) for current totals and status definitions. This document is a PDF-only audit snapshot; its earlier aggregate counts do not include the newer broken/stubbed category or the separate code-only inventory.

**Blueprint:** `AI-Native CRM Global Product Blueprint_V3.pdf` — 23 pp, extracted to `/tmp/blueprint.txt`.
**Codebase:** `backend/app` + `frontend/` + `mobileapp/` at commit `b464b68`.
**Method:** 79 Section-1 rows enumerated from the PDF (priority markers read directly from the tables), cross-cutting sections expanded into 49 sub-items (7 pipeline layers, 5 autonomy items, 7 agents, 10 localisation, 10 Evidence Vault, 3 multi-domain, 7 core screens). Every verdict re-verified against code, including a dedicated pass over `mobileapp/` which the earlier audit missed entirely.

**Legend:** ✅ Built · ⚠️ Partial · ❌ Not built
**Surface:** where the feature is reachable — `backend` / `web` / `mobile` / combinations / `none`

---

## Summary

| | Section 1 (79) | Cross-cutting (49) | Total (128) |
|---|---|---|---|
| ✅ Built | 15 | 4 | **19** |
| ⚠️ Partial | 32 | 21 | **53** |
| ❌ Not built | 32 | 24 | **56** |

By priority (Section 1 only):

| Priority | ✅ | ⚠️ | ❌ | Total |
|---|---|---|---|---|
| P0 | 9 | 15 | 13 | 37 |
| P1 | 5 | 10 | 13 | 28 |
| P1–P2 | 1 | 3 | 1 | 5 |
| P2 | 0 | 4 | 5 | 9 |
| **Total** | **15** | **32** | **32** | **79** |

### Three largest gap clusters

1. **Sales & leads (rows 1–8) — 8 of 8 absent.** No `Lead`, `Deal`, `Pipeline` or trial-booking entity exists anywhere. The product begins at "member".
2. **Evidence Vault (rows 109–118) — 9 of 10 absent.** Audit log exists but is editable; no hash chain, no soft delete, no packs, no WORM.
3. **Retention stack (rows 31–37) — 4 built, 3 backend-only.** Rows 31–34 now have staff interfaces; row 31 also has a member interface. Rows 35–37 still need feature-specific UI.

---

## Part 1 — Section 1: Feature Map by Department (79 rows)

### 1.1 Sales and Lead Management — 0 ✅ / 1 ⚠️ / 8 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 1 | Lead capture from WhatsApp, SMS, Instagram, Facebook, LINE, WeChat, web forms, calls, walk-ins | P0 | ❌ | No `Lead`/`Deal`/`Pipeline` model anywhere. `models/inbox.py:9` mentions "a lead messaging before they are a member" — prose, not an entity | none |
| 2 | Lead profile: goal, budget, preferred times, preferences | P0 | ❌ | — | none |
| 3 | Pipeline: New → Contacted → Trial booked → Visited → Joined / Lost | P0 | ❌ | No stage enum, no pipeline entity | none |
| 4 | Instant first reply 24/7 | P0 | ⚠️ | Enabled public web chat sends an immediate, idempotent receipt reply visible to the visitor and team inbox; other channels and FAQ-based answers remain unbuilt | backend + frontend web |
| 5 | Trial and tour booking | P0 | ❌ | `plan.trial_days` is a SaaS free trial; `visitor.py:4` says "a trial" in prose only. Only class booking exists | none |
| 6 | Follow-up sequences (day 0, 1, 3, 7) | P0 | ❌ | Member-side onboarding exists (row 31); lead-side does not | none |
| 7 | Lost-reason tracking and lead scoring | P1 | ❌ | — | none |
| 8 | Speed-to-lead reporting; missed-call text-back | P1 | ❌ | — | none |
| 9 | Corporate and group memberships; referral tracking | P1–P2 | ⚠️ | Corporate fully built: `models/company.py`, `company_contract.py`, `invoices_service.py`, `routes/companies.py`. Referral: `membership.py:56 referred_by_member_id` + 12-month commission attribution (`workers/payroll_runner.py:93`). Missing: referral programme, rewards, lead-side attribution | backend + web |

### 1.2 Membership Management — 0 ✅ / 5 ⚠️ / 2 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 10 | Member profile: photo, ID (where legal), contact, emergency contact, goals, health notes | P0 | ⚠️ | `membership.py:40 photo_url`, `:41 emergency_contact`, `user.py:35 emergency_contact`. Missing: ID, goals, health notes, auto-generated summary | backend + web |
| 11 | Plans: daily to yearly, family, student, off-peak, class packs, credits | P0 | ⚠️ | `PlanBillingType` = recurring / one_time_pack / drop_in; duration + price free-form so most variants expressible. Missing: credits, family linkage | backend + web + mobile |
| 12 | Joining fees, discounts, promo codes | P0 | ❌ | 0 matches for `discount\|coupon\|promo\|joining_fee` in `backend/app`. No promotion engine at all | none |
| 13 | Freeze/pause (travel, illness, seasonal) | P0 | ✅ | Backend pause-request API and owner/manager review in the web member directory are implemented. Approved pauses preserve prior member/subscription status, extend billing time, and resume on schedule. Linked-member inbox messages with explicit pause language create review-only requests. Mobile is not counted as delivered; signed Twilio inbound can now feed supported SMS/WhatsApp pause requests into the web review flow. | backend + web |
| 14 | Renewals and expiry reminders | P0 | ✅ | Hourly membership worker sends idempotent email and in-app renewal reminders at T-7/T-3/T-1, plus grace reminders on days 1/2/3 after expiry. Reminder records are unique per subscription, billing-period end, and stage, so hourly sweeps do not resend them. | backend |
| 15 | Upgrades, downgrades, transfers, cancellation with save offer | P1 | ✅ | Web Account supports plan-change requests, save-offer responses, recurring-plan vault resumptions, and scheduled cancellation. Owner/manager review handles prorated upgrades (vault credit first, Connect payment for any remainder), transfers, downgrade credits, save offers, and end-of-period processing. Workspace Billing settings support plan changes, cancellation/resume, and invoice-credit history. | backend + web |
| 16 | Family and multi-payer accounts; segmentation and tags | P1–P2 | ⚠️ | Segments are dynamic and computed: `campaign_service.py:82 _resolve_segment` (status, plan, days-since-visit). Missing: family accounts, multi-payer, tags | backend |

### 1.3 Front Desk and Daily Operations — 4 ✅ / 2 ⚠️ / 0 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 17 | Check-in by QR, card/RFID, app, biometric or manual | P0 | ⚠️ | Web: manual, QR, and staff-operated RFID/card check-in are implemented. RFID assignments are unique per workspace; managers assign/remove cards, and attendance-authorized staff resolve card scans through the idempotent check-in path. Missing: member self-check-in and biometric hardware; these remain outside the requested web scope. | backend + web |
| 18 | Status on check-in: expired, dues, birthday, at-risk | P0 | ✅ | `services/attendance_service.py:142` renewal line, `:43 _RISK_DAYS = 14`, `:184` status payload | backend + web |
| 19 | Shared team inbox for all channels | P0 | ✅ | Web inbox supports member matching, assignment/status, AI drafts, retries, and delivery diagnostics. Real inbound/outbound adapters cover SMTP/Resend email, Twilio SMS/WhatsApp with signed delivery callbacks, Telegram, LINE, Instagram/Messenger, WeChat Official Accounts, and a signed-session, rate-limited member web-chat page; phone calls and walk-ins can be logged by staff. Workspace owners manage encrypted provider connections in Settings → Inbox channels. Provider accounts, access permissions, webhook registration, and public HTTPS hosting are workspace setup requirements. | backend + web |
| 20 | Staff "Today" task list | P0 | ✅ | `models/staff.py:28 class Task`, `staff_service.py:272-348` CRUD, `frontend/app/app/tasks`, `mobileapp/src/app/(admin)/tasks.tsx` | backend + web + mobile |
| 21 | Walk-ins, day passes, guest log, lockers | P1–P2 | ✅ | `models/visitor.py`, `visitor_service.py:130` day pass → `Payment(kind=DAY_PASS)`, `routes/front_desk.py` | backend + web |
| 22 | Offline mode with sync | P1 | ✅ Built | Previously loaded web app pages, Next assets, and workspace-scoped API GET responses are cached when their response policy permits local caching. IndexedDB syncs check-ins, cash/manual payments, and lead trial/tour requests; cash retries are idempotent and rejected actions show their reason. Card payments and drawer reconciliation remain online-only. | backend + web |

### 1.4 Finance and Billing — 5 ✅ / 3 ⚠️ / 0 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 23 | Local payment methods per country | P0 | ✅ | Web member signup and approved plan changes use Stripe Payment Element with dynamic methods on the gym’s connected account. Stripe filters methods by buyer location, currency, payment flow, and connected-account eligibility; redirect and delayed confirmations settle through Connect webhooks. Actual method type is recorded on the payment. Available methods depend on Stripe support and activation for the gym’s country/account; bespoke non-Stripe rails such as JazzCash are not included. | backend + web |
| 24 | Recurring billing: cards, direct debit, mandates | P0 | ✅ | Web signup offers explicit auto-renew consent. Stripe Connect PaymentIntents save eligible methods for off-session use; Stripe SetupIntents let members enroll or replace a method and collect any required mandate. An hourly worker creates idempotent renewal charges; succeeded webhooks extend the term, while failures move membership into a three-day grace period and the member can replace the method in Account. Method support and mandate requirements depend on Stripe and the gym's connected-account country/settings. Existing subscriptions stay non-renewing until the member opts in. Stripe card updater remains outside this row's delivered scope. | backend + web |
| 25 | Failed-payment and overdue recovery (dunning) | P0 | ✅ Built | Member renewals use at most three scheduled attempts for Stripe-classified retryable declines; processor errors retry after 6/18 hours and insufficient-funds declines after 24 hours. Hard declines and ambiguous errors stop automatic collection. Member day 1/2/3 notices link to Account; owner/manager tasks escalate from review to a member call to final grace-period review. Decline codes are recorded, and Account shows retry timing and remaining attempts. SaaS recovery continues through Stripe Billing's retry and grace lifecycle. | backend + web |
| 26 | Cash and manual payments with digital receipts | P0 | ✅ | `models/cash.py`, `cash_service.py`, `routes/cash.py:63` receipt PDF, `CashReconciliation` | backend + web + mobile |
| 27 | Payment-proof verification (bank-transfer or wallet screenshots) | P1 | ✅ | Local Tesseract OCR extracts only visible receipt fields; ImageMagick validates/normalizes images for a 64-bit dHash near-duplicate signal (latest 2,000 same-workspace receipts). Images persist and are served to authorized same-workspace reviewers. Every screenshot stays pending until staff confirm the transfer in the receiving bank/wallet; OCR is not settlement confirmation. API hosts need Tesseract and ImageMagick. Old filename-only uploads cannot be backfilled. | backend + web |
| 28 | Invoices with local tax (VAT, GST, sales tax) | P1 | ⚠️ | `plan.tax_rate` end-to-end incl. inclusive-tax: `invoices_service.py:83`, `memberships_service.py:345 _amount_with_tax()`. Missing: country/region rule packs | backend + web |
| 29 | Expenses, P&L, revenue by plan, branch or trainer | P1 | ⚠️ | Revenue by plan/trainer ✅ (swarm specialists `rev_by_plan`, `payroll_commissions`). 0 matches for `expense`. No P&L, no branch dimension | backend + web |
| 30 | Refunds, credits, chargeback evidence; accounting export | P1 | ⚠️ | Verified Connect refunds, tenant/member/currency-scoped immutable member vault credit, and Stripe customer invoice-credit balance/history exist; converted cash cannot also be refunded. Missing: chargeback evidence assembly and accounting export | backend + web |

### 1.5 Retention and Member Success — 4 ✅ / 3 ⚠️ / 0 ❌

**All seven have backend workflows. Rows 31–34 now have staff web UI; row 31 also has a member mobile screen. Rows 35–37 remain backend-only.**

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 31 | 90-day onboarding journey (day 1, days 2–7, weeks 2–4) | P0 | ✅ | `models/onboarding.py`, `onboarding_service.py`, `routes/onboarding.py`, `workers/onboarding.py`; staff roster, risk/search filters, milestones, pause/resume in `frontend/app/app/onboarding/page.tsx`; member progress and milestone actions in `mobileapp/src/app/(member)/onboarding.tsx` | web + mobile |
| 32 | Attendance-drop detection vs each member's own baseline | P0 | ✅ | `retention_service.py` compares each eligible member’s recent 14-day weekly pace with their prior 56-day baseline (minimum 21-day tenure and 1 visit/week baseline); web roster filters by severity, compares counts, and opens the member sheet in `frontend/app/app/retention/page.tsx` | backend + web |
| 33 | Churn-risk score with reasons | P0 | ✅ | Deterministic 0–100 score with high/medium/low filters, human-readable weighted signals, last visit, and links to each member sheet in `frontend/app/app/retention/page.tsx`; score calculation remains in `retention_service.py` | backend + web |
| 34 | Inactivity ladder: 5 days message, 10 days staff check-in, 14–21 days call | P0 | ✅ | Daily ladder dispatch and deduplication remain in the worker; `/inactivity-ladder/roster` exposes tenant-scoped member episodes and rung states. Staff can search/filter, record complete/skip outcomes, and owners can edit rung actions at `/app/retention` → Inactivity ladder. | backend + web |
| 35 | Win-back campaigns; milestones; birthdays | P1 | ⚠️ | `models/winback.py`, `models/celebration.py`, both services + workers. Missing: UI | backend only |
| 36 | NPS at day 7, 30, 90; complaint clustering | P1 | ⚠️ | `nps_service.py:435 _nps()`, theme taxonomy at `:75`; day-7/30/90 daily sweep, `routes/nps.py`. Missing: UI | backend only |
| 37 | Challenges, streaks, leaderboards | P2 | ⚠️ | `models/gamification.py` — `GymChallenge`, `MemberChallengeProgress`, `MemberStreak`; `routes/challenges.py`, daily worker. Missing: UI | backend only |

*Verified: rows 31–32 are visible to staff on the web; row 31 also has a member mobile screen. Rows 33–37 still lack feature-specific interfaces in `frontend/` and `mobileapp/`.*

### 1.6 Marketing and Growth — 0 ✅ / 1 ⚠️ / 5 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 38 | Segmented campaigns by channel (WhatsApp, SMS, email, LINE, and others) | P1 | ⚠️ | Segment resolution real (`campaign_service.py:82 _resolve_segment`); `CampaignChannel` = **IN_APP, EMAIL, BOTH** — not WhatsApp/SMS/LINE. `routes/campaigns.py` exists. Missing: the named channels, and UI | backend only |
| 39 | Seasonal offers (New Year, summer, Ramadan, Diwali, Lunar New Year, and more) | P1 | ❌ | 0 matches for `seasonal`. No local calendar | none |
| 40 | Referral programme; review requests after positive moments | P1 | ❌ | 0 matches for `review_request`. Referral *attribution* exists (row 9); no programme, no rewards, no review requests | none |
| 41 | Lead-ad integrations (Meta, Google, TikTok) | P1 | ❌ | — | none |
| 42 | Campaign ROI: leads → trials → members → revenue | P1 | ❌ | 0 matches for `roi` in campaign context. No funnel attribution | none |
| 43 | Landing pages; content ideas | P2 | ❌ | — | none |

### 1.7 Trainers, Personal Training and Coaching — 0 ✅ / 2 ⚠️ / 3 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 44 | Trainer profiles, schedules, availability | P1 | ⚠️ | Staff model + `Shift` (`models/staff.py:13`) + payroll rates. Missing: availability model, public profile | backend + web |
| 45 | PT package sales and session tracking | P1 | ❌ | 0 matches for `pt_package` / `session_credit`. `member_trainer.py` is a coach link only | none |
| 46 | Trainer–client matching | P1 | ⚠️ | Manual assignment only: `member_trainer.py`, `routes/members.py:245-283 assign_trainer/unassign`. Missing: goal/preference/timing matching | backend + web |
| 47 | Workout and diet plans; progress tracking | P2 | ❌ | No routine/program/exercise model | none |
| 48 | Trainer performance by client retention | P1 | ❌ | No retention ranking per trainer | none |

### 1.8 Classes and Scheduling — 0 ✅ / 2 ⚠️ / 1 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 49 | Timetable, booking, capacity, waitlist | P1 | ⚠️ | `class_session.py:30 capacity: int = 20`, booking + cancel built (`classes_service.py:174`), member booking in web + mobile (`mobileapp/(member)/classes.tsx:60-140` idempotent). **0 matches for `waitlist`/`wait_list`** | backend + web + mobile |
| 50 | No-show tracking and reminders | P1 | ❌ | `BookingStatus.NO_SHOW` exists (`core/constants.py:205`) and is in the DB enum, but is **never assigned anywhere** — 0 matches for `BookingStatus.NO_SHOW` outside the definition. No no-show detection, no reminder logic, no risk signal | none |
| 51 | Utilisation analytics; instructor substitution | P2 | ⚠️ | Swarm specialists `ops_class_fill`, `ops_space_use`, `ops_peak_hours`. Missing: instructor substitution (0 matches for `substitut`) | backend |

### 1.9 HR, Staff and Payroll — 3 ✅ / 0 ⚠️ / 1 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 52 | Roles and permissions: owner, manager, front desk, trainer | P0 | ✅ | `Role` enum + `Capability` enum (incl. `TAKE_ATTENDANCE`), enforced in API deps | backend + web + mobile |
| 53 | Activity and audit log | P0 | ✅ | `models/audit_log.py`, `audit_service.py`, `routes/audit.py`, `record_audit()` called from services | backend + web |
| 54 | Shifts, attendance, salaries, commissions, per-session pay | P1 | ✅ | `models/staff.py:13 Shift` + `:221/:246 check_in/check_out`; `payroll_service.py` fixed+hourly+per-class+commission; `workers/payroll_runner.py:93` 12-month commission window; `frontend/app/app/payroll`, `mobileapp/(staff)/shift.tsx` | backend + web + mobile |
| 55 | Staff performance: response time, conversions, collections | P1 | ❌ | 0 matches for staff KPI/performance aggregation (`performance\|kpi\|response_time\|conversion`) | none |

### 1.10 POS, Inventory, Facility and Access — 0 ✅ / 2 ⚠️ / 3 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 56 | POS for supplements, merchandise, day passes | P1 | ⚠️ | Day passes write real payments (`visitor_service.py:130`). 0 matches for `sale/retail/merch/stock` — no retail POS | backend |
| 57 | Inventory and low-stock alerts | P2 | ❌ | 0 matches for `inventory` | none |
| 58 | Door and turnstile access tied to membership status | P2 | ❌ | No device integration | none |
| 59 | Equipment register and maintenance | P2 | ❌ | 0 matches for `asset` / `maintenance` | none |
| 60 | Peak-hour tracking; safety checklists | P2 | ⚠️ | `ops_peak_hours` specialist. Missing: safety checklists | backend |

### 1.11 Management, Analytics and Multi-Branch — 2 ✅ / 3 ⚠️ / 1 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 61 | "Today" command centre | P0 | ⚠️ | Dashboard queue shows deadlines, receipts/approvals, estimated at-risk revenue, and the top three high/medium-risk members with direct member-sheet links; Retention offers direct calls and internal follow-up tasks. A unified ranked queue and Send/Edit/Skip actions remain open | web |
| 62 | Daily owner brief on the owner's preferred channel | P0 | ⚠️ | `routes/assistant.py:331 POST /briefing` → `workflows.weekly_briefing`. **Weekly, not daily**; **in-app only**, not on preferred channel | backend |
| 63 | KPIs: active members, joins, churn, MRR, collections, conversion | P0 | ✅ | `analytics_service.py`, `routes/analytics.py`, KPI strip `frontend/app/app/page.tsx:196` | backend + web + mobile |
| 64 | Revenue-at-risk panel; Wins feed (money recovered) | P0 | ⚠️ | Revenue-at-risk remains on the owner dashboard. Web Retention records tenant-scoped successful renewals that restore grace-status memberships and shows the latest five; mobile wins and lead-conversion attribution remain open | backend + frontend web |
| 65 | Ask-anything analytics | P1 | ✅ | `routes/assistant.py`, `agent/` LangGraph graph, 40-specialist swarm, `ChatGroq` live when `GROQ_API_KEY` set (`agent/model.py:32`) with documented offline stub; web `frontend/app/app/assistant` + streaming API | backend + web |
| 66 | Multi-branch, multi-currency, franchise royalties | P1–P2 | ❌ | 0 matches for `branch_id\|location_id\|site_id\|royalty\|franchise` in models. "venue" hits are the industry vertical. `default_currency` on org only | none |

### 1.12 Compliance, Legal and Data — 0 ✅ / 1 ⚠️ / 6 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 67 | Waivers, health forms (PAR-Q), contracts with e-signature | P1 | ❌ | 0 matches for `waiver` / `parq`. All `esignature` hits are `Stripe-Signature` webhook headers | none |
| 68 | Consent management per channel and purpose (opt-in, opt-out) | P0 | ⚠️ | Lead email/SMS follow-up consent is stored separately. Owner/manager Settings records member email, SMS, and in-app marketing consent with audit history; email/in-app campaigns exclude members without matching consent, and inbound SMS STOP revokes SMS permission. Bulk SMS and country-specific purpose rules are not implemented | backend + web |
| 69 | Data-subject requests: access, export, correction, erasure | P0 | ⚠️ | Owner/manager Settings queue records and audits requests; provides workspace-scoped member exports; correction uses existing profile editing; erasure redacts workspace profile, revokes access, and stops renewals before staff reviews linked records and retention. Shared identities are blocked for manual review; payment/attendance records and external processor/backups are retained | backend + web |
| 70 | Auto-renewal disclosures, cooling-off and online cancellation | P0 | ❌ | 0 matches for `cooling_off\|auto_renewal` | none |
| 71 | Role-based access to sensitive data | P0 | ⚠️ | Sensitive member health/ID fields are owner/manager-only; compensation endpoints are owner-only and member directory responses now omit rates for managers. Remaining: consistent field-level policy across all personal data and audit review | backend + web |
| 72 | Evidence Vault (section 8) | P0 | ❌ | Audit log exists but is editable — no hash chain (`prev_hash: 0`), no soft delete (`deleted_at: 0`), no packs, no WORM, no residency. See rows 109–118 | none |
| 73 | Data residency options (EU, India, Gulf, and others) | P1 | ❌ | 0 matches for `storage_region` | none |

### 1.13 Member Experience and Platform — 0 ✅ / 5 ⚠️ / 1 ❌

| # | Feature | Pri | Status | Evidence / gap | Surface |
|---|---|---|---|---|---|
| 74 | Messaging-first member self-service: renew, pay, freeze, book | P0 | ⚠️ **(Δ)** | Member app can book (`(member)/classes.tsx`), view dues/history (`(member)/payments.tsx`), and request/withdraw a membership pause (`(member)/membership-pause.tsx`; `POST/GET/DELETE /memberships/me/freeze-requests`). Owner/manager approval is available in the web member directory. Missing: renewal self-service and messaging/AI concierge. | mobile + backend + web |
| 75 | Web portal or PWA: card, QR, dues, history | P1 | ⚠️ **(Δ)** | Earlier audit said "No `mobile/` directory" — **`mobileapp/` exists**: Expo app, 44 screens under `mobileapp/src/app/`, member dues + payment history real (`payments.tsx`). Missing: digital member card, QR code (0 matches for `qr`/`member_card` in mobileapp) | mobile + backend |
| 76 | Branded app, workout log, streaks, rewards | P2 | ⚠️ | Branded Expo app exists (`mobileapp/app.json`, industry-aware tabs in `(member)/_layout.tsx:31-70`). Backend streaks/challenges complete. Missing: workout log, streak/reward UI (0 matches in mobileapp screens) | mobile + backend |
| 77 | Import from spreadsheets and competitor exports | P0 | ⚠️ **(Δ)** | Owner/manager web sheet uploads CSV with a downloadable template, 2 MB cap, activation-email disclosure, and created/skipped/row-error results. Backend creates pending-activation members and emails setup links. Competitor-specific formats and XLSX are not supported | backend + web |
| 78 | Multilingual UI, right-to-left support, local date and number formats | P0 | ❌ | `org.country/timezone/default_currency` fields only. 0 matches for `i18n`/`translation`; the "locale" frontend hits are `toLocaleDateString` | none |
| 79 | Public API and webhooks; usage and cost meter | P1–P2 | ⚠️ | Inbound Stripe webhooks ✅ signature-verified, two endpoints (`routes/webhooks.py:1-60` — `/webhooks/stripe`, `/webhooks/stripe-connect`). Missing: outbound public API, API keys, usage/cost meter | backend |

---

## Part 2 — Cross-Cutting Sections (49 items)

### 2.1 Seven-layer AI pipeline — 1 ✅ / 5 ⚠️ / 1 ❌

| # | Layer | Status | Evidence / gap | Surface |
|---|---|---|---|---|
| 80 | L1 Event ledger: append-only timeline per person, nothing overwritten | ⚠️ | `AuditLog` + append-only attendance records. No per-person raw event stream (messages, notes, calls) as source of truth | backend |
| 81 | L2 Understanding: LLM + rules extract intent, goal, objection, sentiment, payment details, freeze requests, any language | ⚠️ | LLM live in assistant (`agent/model.py:32 ChatGroq`). Linked-member inbox messages with explicit membership-pause wording create a review-only freeze request through deterministic phrase matching. General intent/entity extraction across arbitrary messages and external channels remains missing. | backend |
| 82 | L3 Customer model: structured state + history — plan, expiry, dues, visit baseline, risk, goal, trainer, summary | ✅ | Snapshot + `plan_summaries.py` one-paragraph summary; risk from `retention_service.py`; visit baseline computed | backend |
| 83 | L4 Signal engine: deterministic triggers + ML risk scoring (expiry, absence, visit drop, unpaid dues, unanswered lead) | ⚠️ | Deterministic triggers (workers) + weighted score (`retention_service.py:166-245`). **No ML**; no unanswered-lead signal (no leads) | backend |
| 84 | L5 Decision layer: next best action, draft, value estimate, owner assignment, autonomy level | ⚠️ | Assistant proposes writes via `_proposal()` with draft text. No ranked next-best-action engine, no value estimate, no owner assignment, no autonomy level | backend |
| 85 | L6 Action layer: auto-send · approve-then-send · staff task · call | ⚠️ | Auto / approve / task all exist but scattered across workers and features. No call action; sends limited to email + push | backend |
| 86 | L7 Outcome loop: did they reply, return, pay, renew? Model learns; Wins feed shows money recovered | ❌ | No learning loop, no outcome attribution, no Wins feed (`wins: 0`) | none |

### 2.2 Autonomy levels L0–L3 and human-in-the-loop — 0 ✅ / 3 ⚠️ / 2 ❌

| # | Level | Status | Evidence / gap | Surface |
|---|---|---|---|---|
| 87 | L0 Observe: update summary, compute risk, tag lead — always automatic | ⚠️ | Risk computation and summaries run automatically in workers. No lead tagging (no leads) | backend |
| 88 | L1 Auto-act (safe): FAQ reply, receipt, renewal reminder, class reminder, first lead reply — automatic, template-bound, reversible | ⚠️ | Pre-expiry renewal and grace reminders, onboarding messages, and celebrations auto-send on schedule. No FAQ reply, no first-lead reply | backend |
| 89 | L2 Approve first: discounts, win-back offers, complaint replies, freezes, bulk campaigns — one-tap approval | ⚠️ | Real human-in-the-loop gate: `agent/tools/write.py` 8 approval-gated writes via `_proposal()` / `_rejected()`. No one-tap approval UI for the full set | backend + web |
| 90 | L3 Human only: refunds, price changes, medical topics, angry customers, cash mismatches — AI briefs a human | ❌ | Not distinguished from L2. No risk classification, no fail-closed timeout | none |
| 91 | Owner trust ladder: move any action type between levels; promote to L1 after seeing results; AI-disclosure setting per country | ❌ | No L0–L3 tiers, no owner-controlled promotion dial, no AI-disclosure setting (`AI Act Art. 50`) | none |

### 2.3 Seven named agents — 2 ✅ / 3 ⚠️ / 2 ❌

| # | Agent | Status | Evidence / gap | Surface |
|---|---|---|---|---|
| 92 | Lead Concierge — instant reply, qualification, trial booking, follow-up | ❌ | No lead entity, no inbound auto-reply | none |
| 93 | Renewal & Collections — expiry reminders, dunning, payment links, proof matching | ⚠️ | Pre-expiry reminders (T-7/T-3/T-1), grace reminders (days 1/2/3), payment-proof pipeline, and SaaS dunning ladder. Missing: payment links to members and a member escalation ladder | backend |
| 94 | Retention Coach — onboarding, absence check-ins, milestones, save offers | ✅ | Onboarding journey + inactivity ladder + win-back + celebrations all built with routes and daily workers | backend |
| 95 | Front-Desk Copilot — check-in context, draft replies | ⚠️ | Check-in status card (row 18) + inbox AI draft (`inbox_service.py`). Missing: context summary at check-in beyond status flags | backend + web |
| 96 | Owner Analyst — morning brief, Q&A, explanations | ✅ | `POST /assistant/briefing` + ask-anything with 40 specialists (`routes/assistant.py:331`) | backend + web |
| 97 | Reputation Agent — review requests, complaint clustering | ⚠️ | NPS + complaint clustering built (`nps_service.py:75` theme taxonomy). Missing: review requests (0 matches for `review_request`) | backend |
| 98 | Compliance Guard — checks consent, quiet hours, disclosures, cancellation rules per country | ❌ | No consent model, no country rule packs, no quiet hours — nothing to check against | none |

### §6 Localisation Layer — 0 ✅ / 3 ⚠️ / 7 ❌

| # | Component | Status | Evidence / gap | Surface |
|---|---|---|---|---|
| 99 | Country Pack container: quiet hours, consent types, reminder schedules, cooling-off, cancellation channels, AI-disclosure text, retention defaults | ❌ | 0 matches for `country_pack`. `org.country/timezone/default_currency` are bare fields | none |
| 100 | Messaging channels by region (WhatsApp, SMS, LINE, WeChat, Telegram; email fallback) | ⚠️ | Twilio SMS/WhatsApp, Telegram, LINE and SMTP/Resend email have outbound adapters; signed inbound webhooks cover Twilio, Telegram, and LINE. Instagram/Messenger, WeChat, inbound email, per-workspace connection management, and regional provider choice remain missing | backend + web |
| 101 | Local payment methods by region (SEPA, Pix, UPI AutoPay, M-Pesa, JazzCash, cards/ACH, Stripe/Adyen gateway) | ⚠️ | Stripe + cash + bank_transfer + mobile_wallet generic. No regional rails (0 matches for `pix\|upi\|m_pesa\|sepa\|jazzcash`) | backend |
| 102 | Privacy-law rule packs (GDPR, AI Act, CCPA, LGPD, DPDP, PDPL) with deadline tracking | ❌ | 0 matches for `gdpr\|privacy_rule\|deadline` tracking | none |
| 103 | Membership and messaging rules (US state auto-renewal, UK DMCC cooling-off, opt-in/STOP, quiet hours 8am–9pm) | ❌ | 0 matches for `quiet_hours\|cooling_off\|stop_keyword` | none |
| 104 | Languages and RTL (major languages, Hinglish/Roman Urdu/Spanglish/Arabizi, Arabic/Urdu/Hebrew layouts) | ❌ | 0 matches for `i18n` / `translation` / `rtl` | none |
| 105 | Currency: multi-currency pricing, reports, multi-branch consolidation | ⚠️ | `org.default_currency` only. No multi-currency pricing or consolidation | backend |
| 106 | Tax: VAT, GST, sales tax on invoices by country and region | ⚠️ | `plan.tax_rate` incl. inclusive-tax handling (`memberships_service.py:345`). No country/region rule packs | backend |
| 107 | Culture: local holidays/seasons, women-only hours, tone per country, local names and formats | ❌ | 0 matches for `holiday\|women_only\|tone` | none |
| 108 | Pricing: tiers adjusted for purchasing power (PPP) | ❌ | 0 matches for `ppp\|purchasing_power` | none |

### §8 Evidence Vault (10 items) — 0 ✅ / 1 ⚠️ / 9 ❌

| # | Block | Status | Evidence / gap | Surface |
|---|---|---|---|---|
| 109 | Append-only ledger: old versions kept on every edit | ❌ | `AuditLog` records changes but rows are editable/deletable. No version history | none |
| 110 | Soft delete + Recycle Bin: 90-day restorable, one-click undo | ❌ | 0 matches for `deleted_at` / `recycle`. Hard deletes only (`members_service.py:417 delete_member`) | none |
| 111 | Automatic Evidence Packs: PDF + Excel snapshot before delete, merge, bulk edit or payment change | ❌ | 0 matches for evidence pack generation | none |
| 112 | Tamper-evident audit chain: hash-chained entries + signed daily checkpoints outside the DB | ❌ | 0 matches for `prev_hash` / checkpoint signing | none |
| 113 | WORM storage: object lock blocks deletion/overwrite during retention | ❌ | 0 matches for `worm` / object lock | none |
| 114 | Point-in-time recovery + 3-2-1 backups (three copies, two media, one off-site) | ❌ | No PITR/backup config in codebase | none |
| 115 | Owner-held daily exports: daily Excel to email/cloud, monthly PDF statement | ❌ | 0 matches for daily export worker | none |
| 116 | Access and export log: records who viewed or exported what | ⚠️ | Partial via `AuditLog` (record_audit covers state changes). No dedicated view/export logging | backend |
| 117 | Owner alerts: bulk deletes, payment edits, large exports, after-hours changes | ❌ | No alert rules on audit events | none |
| 118 | Erasure with hash-only stub: personal fields erased, hash keeps chain valid | ❌ | No erasure path at all | none |

### §9 Beyond Gyms (3 items) — 0 ✅ / 1 ⚠️ / 2 ❌

| # | Component | Status | Evidence / gap | Surface |
|---|---|---|---|---|
| 119 | Generic engine: Person / Event / Payment / "Say-Do-Pay" core | ⚠️ | **Multi-industry built** — `org.industry ∈ {gym, office, academy}` (`models/organization.py:29`), `core/industry.py` per-industry labels/modules/checklist/nouns, schema-driven plan builder, `routes/industries.py`, industry-aware mobile tabs (`(member)/_layout.tsx:31-70`). Missing: clinic/salon/real-estate/B2B verticals | backend + web + mobile |
| 120 | Sales-company pack (contacts, deals, meetings, quotes, lead ownership) | ❌ | 0 matches for sales-company pack | none |
| 121 | Pack builder / vertical marketplace | ❌ | Industry schemas are hardcoded, not installable packs | none |

### §3.2 Core Screens (7 items) — 1 ✅ / 5 ⚠️ / 1 ❌

| # | Screen | Status | Evidence / gap | Surface |
|---|---|---|---|---|
| 122 | Today: one ranked list ("8 people need you today; USD 1,240 at stake") with Send / Edit / Skip / Call per card | ⚠️ | `frontend/app/app/page.tsx` (494 lines) has KPI strip + headline metrics but no ranked action list, no value-at-stake cards, no per-item actions | web |
| 123 | Inbox: all channels in one place, member summary alongside, AI drafts | ✅ | Shared inbox provides linked member context, assignment/status, AI drafts, encrypted provider setup, and live inbound/outbound adapters for supported channels. Public member web chat and phone/walk-in interaction logging are included. | backend + web |
| 124 | Desk: check-in scanner with a status card for each arrival | ⚠️ | Web desk supports QR webcam scan, manual lookup, RFID keyboard-wedge scan, and post-check-in status receipt (`attendance/page.tsx`; `POST /attendance/card/check-in`). Biometric hardware integration is not included in the requested web scope. | backend + web |
| 125 | People: one scrollable timeline of messages, visits and payments per person | ⚠️ | Member detail sheet shows visits + payments (`member_detail`, `frontend/app/app/members/[memberId]`). No unified message timeline | backend + web |
| 126 | Money: collections, dues, cash drawer, P&L, recovered this month | ⚠️ | Collections/dues/cash drawer ✅ (`frontend/app/app/cash`, `payments`, `analytics`). No P&L (row 29), no "recovered this month" | web |
| 127 | Ask: natural-language questions in any language, action buttons in the answer | ✅ | Assistant with LangGraph + 40 specialists, streaming (`frontend/app/api/assistant/stream`), approval-gated write actions | backend + web |
| 128 | Wins: feed of members saved, money recovered, leads converted | ❌ | 0 matches for wins feed. Shares root cause with row 64 and layer 86 | none |

---

## Part 3 — Changes vs `BLUEPRINT_AUDIT.md`

The prose audit at the repo root remains the methodology record. This file is the authoritative status list and supersedes those verdicts. Four verdicts changed:

| Row | Was | Now | Why |
|---|---|---|---|
| **74** Messaging-first member self-service | ❌ | **⚠️** | Member app supports class booking, dues/history, and pause request/withdrawal. Web owners/managers can review pause requests. Renewal self-service and messaging/AI concierge remain missing. |
| **75** Web portal / PWA | ❌ | **⚠️** | Audit said "No `mobile/` directory" — the directory is named `mobileapp/` (44 screens). Dues + history real. Member-facing card/QR still absent (staff-facing QR in `MemberDetailSheet.tsx:602` counts for row 17, not here) |
| **76** Branded app | ⚠️ (thin) | **⚠️** (evidenced) | Expo app confirmed (`mobileapp/app.json`); no workout log, no streaks UI confirmed |
| **77** Import | ⚠️ "CSV import built" | **⚠️** (backend only) | Route + service exist; **zero UI** in web or mobile. Surface corrected |

**Row 15 rechecked for the requested web scope:** member changes use `membership_changes_service.py`, `member_vault_service.py`, the web Account surface, owner/manager review, and scheduled lifecycle processing. The row is marked Built for backend + web; mobile is excluded from this scope.

**Confirmed inventory gaps:** waitlist 0 matches; promos 0 matches; consent 0 matches; staff KPIs 0 matches; branches/royalties 0 matches; no Wins feed; retention rows 35–37 have no feature-specific UI in `frontend/` or `mobileapp/`. Row 31 has staff web and member mobile UI; rows 32–34 now have staff retention views. Receipt OCR and perceptual duplicate detection have since been implemented; see row 27.

**Corrected after re-verification (three earlier claims were wrong):**
1. **QR generation exists** — `MemberDetailSheet.tsx:602` issues `acron:member:{member_id}`, `QrScanner.tsx` decodes it back into check-in. Row 17's QR path is real, not an enum-only parameter.
2. **No-show is an enum, not a void** — `BookingStatus.NO_SHOW` (`core/constants.py:205`, in the DB enum) but never assigned anywhere. Row 50 stays ❌ for logic, not for the enum.
3. **`integrations/` has no stub sms/whatsapp/telegram files** — those files never existed. Only `email.py`, `push.py`, `llm.py`, `ocr.py`, `hibp.py`, `stripe_*`. Rows 19/100 reworded accordingly.

---

## Part 4 — Suggested build order

Ordered by leverage:

1. **Remaining retention UI** — 3 features (rows 35–37) have backend workflows but need staff/member interfaces.
2. **Promotion engine** (row 12, P0) — discounts, promo codes, joining fees. Small surface (`Plan`/`Subscription`/`Payment`), direct revenue impact.
3. **Lead pipeline + trial booking** (rows 1–8: P0 ×6, P1 ×2) — closes the largest hole; reuses `Conversation` and `Notification`.
4. **Member app completion** (rows 74–76) — renewal self-service, member card/QR, workout log. Membership-pause requests now work end-to-end; the app shell already exists.
5. **Consent + audit hash chain + soft delete** (rows 68, 110, 112) — cheap; prerequisite for selling into any regulated market.
6. **Member dunning ladder** (row 25) — extend `send_grace_reminders` with the escalating cadence that already exists for SaaS.
7. **Member dunning and payment links** (row 93) — add payment links and escalation controls to the reminder cadence now implemented in row 14.
9. **Waitlist + no-shows** (rows 49–50) — booking exists; these are additive.
10. **Multi-location** (row 66) — `location_id` on membership/payment/attendance. Cheap now, expensive later.
