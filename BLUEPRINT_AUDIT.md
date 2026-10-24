# Acron Feature Audit — Full Table

Every material feature identified in both source PDFs and the current codebase inventory, with its implementation surface and status.

- **PDF** — `AI-Native CRM  Global Product Blueprint_V3.pdf`: 79 department-level feature rows plus 73 cross-cutting, UX, safety, evidence, expansion, and detailed Sales Pack requirements.
- **Strategy PDF** — `Zhilo_Labs_AI_Business_OS_Strategy_Report.pdf`: 106 product/platform requirement rows, including explicit mappings where it restates or strengthens a Blueprint feature.
- **API** — `backend/app` (FastAPI).
- **Web** — `frontend/app` (Next.js).
- **Mobile** — `mobileapp/src/app` (Expo).
- **Code snapshot** — based on the working tree on 2026-10-14, including the lead-profile, referral, pipeline, member-profile, plan-variant, and membership change-request work. The temporary plans-screen render harness is excluded from shipped-feature counts.
- **Method** — static inspection of models, routes, services, workers, and reachable web/mobile screens. Feature claims in the PDF are treated as requirements, not agent instructions. The pipeline update passed six focused backend tests, frontend TypeScript, and scoped lint; other rows retain their original static-audit basis.

**Part A** = features stated in the Blueprint PDF. **Part B** = features that exist in code but are not itemised in that PDF. **Part C** = every material product/platform feature stated in the Strategy PDF, including marked overlaps with Part A.

### Status definitions

| Status | Meaning |
|---|---|
| ✅ **Built** | Implemented and wired end-to-end for the scope named in the feature row |
| 🔧 **Improvement** | A usable implementation exists; the remaining gap is a refinement or broader coverage |
| ⚠️ **Partial** | Some meaningful parts work, but a material requirement in the row is missing |
| 🧨 **Broken / stubbed** | Code is present, but a central promised behavior is a placeholder or cannot perform its purpose |
| ❌ **Not built** | No usable implementation exists; an enum, comment, or unused schema alone does not count |
| ⏸️ **Deferred** | Valid later-stage feature that the Strategy Report explicitly says should not delay validation |

---

## Summary

| Status | Part A: Blueprint (152) | Part B: code-only (18) | Part C: Strategy (106) | Traceability rows (276) |
|---|---:|---:|---:|---:|
| ✅ Built | 33 | 15 | 1 | **49** |
| 🔧 Improvement | 3 | 0 | 0 | **3** |
| ⚠️ Partial | 60 | 3 | 53 | **116** |
| 🧨 Broken / stubbed | 0 | 0 | 0 | **0** |
| ❌ Not built | 56 | 0 | 46 | **102** |
| ⏸️ Deferred | 0 | 0 | 6 | **6** |

The surface columns are not mutually exclusive; a row can have API and web coverage, for example. Counts above classify each traceability row once by its overall status. Part C intentionally maps overlaps, so 276 traceability rows do not mean 276 unique product capabilities. Blueprint rows 80–152 expand cross-cutting architecture, UX, evidence, localisation, expansion, and Sales Pack details; those row numbers are audit indices, not numbering printed in the PDF.

For the original prioritized rows in Parts A and B: P0 — 29 built, 1 improvement, 10 partial, 7 not built; P1 — 11 built, 1 improvement, 13 partial, 11 not built; P1–P2 — 2 built, 2 partial, 1 not built; P2 — 4 partial, 5 not built. Part B priorities are assigned by this audit. Cross-cutting Blueprint detail rows carry no printed PDF priority, while Part C retains the Strategy Report's P0/P1/P2 sequencing.

### Source-to-row coverage recheck

| Source document section | Audit rows | Coverage result |
|---|---|---|
| Blueprint §1.1–§1.13 department feature tables | 1–79 | Every printed feature-table row represented |
| Blueprint §2 AI architecture, autonomy, agents, examples, messaging economics | 80–98, 130–137, 151 | Layers, agents, controls, economics, explanations, tone, undo, voice handling, and prompt safety represented |
| Blueprint §3 users, core screens, daily/front-desk/member flows, UX requirements | 122–138, 151–152 | All named screens and material interaction/performance requirements represented |
| Blueprint §5 differentiation | 99–128, 130–138, 152 | Customer brain, action engine, channels, payments, compliance, ROI, trust, evidence, and pricing controls represented |
| Blueprint §6 localisation | 99–108 | Country Packs, channels, payments, laws, language/RTL, currency, tax, culture, and PPP represented |
| Blueprint §7 stack/guardrails/metrics | 80–108, 135–137 | Product-facing architecture and guardrails represented; vendor choices are not counted as features |
| Blueprint §8 Evidence Vault | 109–118, 138–140 | Storage, recovery, exports, alerts, privacy, evidence events, and safety UX represented |
| Blueprint §9 domains and Sales-Company Pack | 119–121, 141–150 | Generic engine, pack model, and every Sales Pack feature group represented |
| Blueprint §11 build order | Existing Part A rows | Repeats earlier requirements; no duplicate feature rows added solely for phases |
| Strategy Chapter 1 differentiation opportunities | S008–S009, S022–S026, S033, S041, S072, S103–S105 | Simulation, collaboration, cross-system work, verified outcomes, templates, and history represented |
| Strategy Chapters 2–3 pillars and P0/P1/P2 roadmap | S001–S051, S101, S104 | Every named pillar and roadmap module represented |
| Strategy Chapter 4 Flow builder | S052–S073, S102, S106 | Node types, natural-language lifecycle, simulation, limits, recovery, editor UX, and payment validation represented |
| Strategy Chapter 5 showcase workflows | S074–S080 | All seven workflows represented |
| Strategy Chapter 6 architecture and engineering rules | S081–S095, S103, S106 | Ledger, durable execution, policy gateway, tools, evidence, integrations, six rules, and evaluation suite represented |
| Strategy Chapter 7 owner experience | S096–S100 | Navigation, role workspaces, and trustworthy Ask action sequence represented |
| Strategy Chapters 8–14 | Section 19 of `backend/STRATEGY_BLUEPRINT_MASTER_REPORT.md` | Pricing, GTM, moat, expansion, operating roadmap, metrics, and decision rules are company requirements rather than software features |

### Confirmed broken or stubbed behavior

No central behavior is currently classified as broken/stubbed in this audit snapshot. Receipt screenshots are OCR-extracted and visually deduplicated, then always held for an authorized staff member to verify against the receiving bank or wallet. An image alone is not treated as settlement proof.

Other absent capabilities are classified as **Not built**; incomplete but functioning capabilities remain **Partial** or **Improvement**. Email, push, Stripe, and assistant fallback modes are intentional development behavior when credentials are absent, so they are not counted as broken. The booking `NO_SHOW` enum has no detection or assignment workflow and is therefore counted as **Not built**, not broken.

### Notion comparison limitation

The supplied Notion page did not load in the available browser during this audit, so its current table could not be independently checked. A prior copied tracker was reported to use numbering one higher than the PDF table; treat that offset as provisional until the live Notion rows can be read. The statuses in this file are based on the PDF and repository evidence, not a fresh Notion read.


---

## Part A — Blueprint features (PDF, rows 1–152)

| # | Feature | Pri | PDF | API | Web | Mobile | Status | Evidence / gap |
|---|---|---|---|---|---|---|---|---|
| 1 | Lead capture from WhatsApp, SMS, Instagram, Facebook, LINE, WeChat, web forms, calls, walk-ins | P0 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Manual/source-tagged intake at `/app/leads` now uses a controlled source vocabulary, normalized email/phone data, tenant-scoped duplicate rejection, editable attribution, and previous/new audit values. No provider-driven public form, WhatsApp, SMS, or social channel connectors are implemented. |
| 2 | Lead profile: goal, budget, preferred times, preferences | P0 | ✓ | ✓ | — | — | ✅ Built | Tenant-scoped profile fields editable in `/app/leads`, with field provenance, searchable prospects, and pipeline stage tracking; does not include AI extraction or conversation linking |
| 3 | Pipeline: New → Contacted → Trial booked → Visited → Joined / Lost | P0 | ✓ | ✓ | ✓ | — | ✅ Built | Board/list views, six stages, search/filter/counts, accessible stage controls, and paginated actor/timestamp history at `/app/leads` and `GET /leads/{id}/history`. Referral conversions share audited transitions; legacy unknown previous stages are labeled. Trial/visit automation remains separate. |
| 4 | Instant first reply 24/7 | P0 | ✓ | — | — | — | ❌ Not built | No auto-reply, no FAQ knowledge base |
| 5 | Trial and tour booking | P0 | ✓ | ✓ | ✓ | — | ✅ Built | Lead booking panel at `frontend/app/app/leads`: available class slots for trials and custom tour times; tenant-scoped reservations, capacity enforcement, duplicate-active-booking prevention, and attended/no-show/cancel transitions (`GET /leads/trial-slots`, `POST /leads/{id}/bookings`, `PATCH /leads/{id}/bookings/{booking_id}`). No automated confirmation/reminders |
| 6 | Follow-up sequences (day 0, 1, 3, 7) | P0 | ✓ | ✓ | ✓ | — | ✅ Built | Consent-gated day 0/1/3/7 email sequence, scheduled worker, per-step delivery tracking, staff due notifications, completion/skip controls, and outcome notes; copy is currently fixed |
| 7 | Lost-reason tracking and lead scoring | P1 | ✓ | ✓ | ✓ | — | ✅ Built | Marking a lead Lost requires a controlled reason; `/app/leads` shows a 0–100 explainable profile-completeness score with per-factor breakdown, not a predictive conversion claim |
| 8 | Speed-to-lead reporting; missed-call text-back | P1 | ✓ | — | — | — | ❌ Not built | — |
| 9 | Corporate and group memberships; referral tracking | P1–P2 | ✓ | ✓ | ✓ | ✓ | ✅ Built | Corporate contracts/invoices and team seat management exist (`models/company.py`, `company_contract.py`, `invoices_service.py`, `/app/companies`). Referral program supports member codes, signup attribution, qualification after successful payment, dual rewards, admin tracking/manual fulfillment, mobile share/status, and joined Lead attribution (`services/referrals_service.py`, `/app/referrals`, mobile dashboard). Rewards are recorded and manually delivered; no automatic wallet credit/discount. Not available for office B2B tenants or invite-only enrollment. |
| 10 | Member profile: photo, ID (where legal), contact, emergency contact, goals, health notes | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | Organization-scoped photo URL, contact, emergency contact, goals, private health notes, optional ID type/final four, and a deterministic profile summary. Owner/manager edit via `/members/{id}/profile` and `/app/members`; members edit their own profile on mobile. Health notes and ID metadata are hidden from front desk. Audit records changed field names without sensitive values; archive clears private fields. Photo is linked by HTTPS URL; full ID numbers and document images are intentionally not stored. |
| 11 | Plans: daily to yearly, family, student, off-peak, class packs, credits | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | Owner plan builder exposes day/week/month/year cycles, student/family audience, family capacity, local off-peak window, class-pack size/validity, and optional recurring visit credits. Purchase snapshots the allowance; check-in consumes one credit atomically and flags out-of-window or exhausted visits while still logging attendance. Owner/manager can link same-org members to an active family plan; they share the payer's entitlement and credits. Student status is a plan label and is not automatically verified. Visit credits are separate from account/payment credits in row 30. |
| 12 | Joining fees, discounts, promo codes | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | Plans define a first-purchase joining fee; owner/manager can create and activate tenant-scoped percentage or fixed promo codes, optionally limited to one plan. Card signup and offline payments use the same server quote for plan price, joining fee, discount, added tax, and total; the charged payment snapshots each component. Mobile checkout and web cash logging show the breakdown, and offline receipts include it. No usage limits or automatic referral wallet credits. |
| 13 | Freeze/pause (travel, illness, seasonal) | P0 | ✓ | ✓ | ✓ | — | ✅ Built | Backend pause-request API and owner/manager review in the web member directory are implemented. Approved pauses preserve prior member/subscription status, extend billing time, and resume on schedule. Linked-member inbox messages with explicit pause language create review-only requests. Mobile is not counted as delivered; signed Twilio inbound can now feed supported SMS/WhatsApp pause requests into the web review flow. |
| 14 | Renewals and expiry reminders | P0 | ✓ | ✓ | — | — | ✅ Built | Hourly membership worker sends idempotent email and in-app renewal reminders at T-7/T-3/T-1, plus grace reminders on days 1/2/3 after expiry. Reminder records are unique per subscription, billing-period end, and stage, so hourly sweeps do not resend them. |
| 15 | Upgrades, downgrades, transfers, cancellation with save offer | P1 | ✓ | ✓ | ✓ | — | ✅ Built | Web scope: member Account supports plan-change requests, save-offer responses, recurring-plan vault resumptions, and scheduled cancellation. Owner/manager review handles prorated upgrades (vault credit first, Connect payment for any remainder), transfers, downgrade credits, save offers, and end-of-period processing. Workspace Billing settings support plan changes, cancellation/resume, and invoice-credit history. |
| 16 | Family and multi-payer accounts; segmentation and tags | P1–P2 | ✓ | ✓ | — | — | ⚠️ Partial | Segments are dynamic and computed: `campaign_service.py:82 _resolve_segment` (status, plan, days-since-visit). Missing: family accounts, multi-payer, tags |
| 17 | Check-in by QR, card/RFID, app, biometric or manual | P0 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Web: manual, QR, and staff-operated RFID/card check-in are implemented. RFID UID assignments are unique per workspace, owner/manager-only to assign or remove, and staff attendance-gated to resolve/check in; visits use the existing idempotent attendance path and status receipt. QR remains available through the webcam scanner. Mobile self-check-in and biometric hardware are outside the requested web scope and remain unbuilt. |
| 18 | Status on check-in: expired, dues, birthday, at-risk | P0 | ✓ | ✓ | ✓ | — | ✅ Built | `services/attendance_service.py:142` renewal line, `:43 _RISK_DAYS = 14`, `:184` status payload |
| 19 | Shared team inbox for all channels | P0 | ✓ | ✓ | ✓ | — | ✅ Built | Web inbox covers member matching, assignment/status, AI drafts, retry/diagnostics, and SMTP/Resend email, Twilio SMS/WhatsApp (including signed delivery callbacks), Telegram, LINE, Instagram/Messenger, and WeChat inbound/outbound. A signed-session, rate-limited member web chat is available at the workspace chat link; phone calls and walk-ins can be logged by staff. Workspace owners manage encrypted provider connections in Settings → Inbox channels. Provider account permissions, webhook setup, and public HTTPS hosting remain workspace configuration. |
| 20 | Staff "Today" task list | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `models/staff.py:28 class Task`, `staff_service.py:272-348` CRUD, `frontend/app/app/tasks`, `mobileapp/src/app/(admin)/tasks.tsx` |
| 21 | Walk-ins, day passes, guest log, lockers | P1–P2 | ✓ | ✓ | ✓ | — | ✅ Built | `models/visitor.py`, `visitor_service.py:130` day pass → `Payment(kind=DAY_PASS)`, `routes/front_desk.py` |
| 22 | Offline mode with sync | P1 | ✓ | ✓ | ✓ | — | ✅ Built | Previously loaded app pages, Next assets, and workspace-scoped API GETs are available offline when the response policy permits local caching. The IndexedDB outbox syncs check-ins, cash/manual payments, and lead bookings when connectivity returns, with cash idempotency and visible rejected-item reasons. Card payments and drawer reconciliation remain online-only. |
| 23 | Local payment methods per country | P0 | ✓ | ✓ | — | — | ✅ Built | Web member signup and approved plan changes use Stripe Payment Element with dynamic methods on the gym’s connected account. Stripe filters methods by buyer location, currency, payment flow, and connected-account eligibility; redirect and delayed confirmations settle through Connect webhooks. Actual method type is recorded on the payment. Available methods still depend on Stripe support and activation for the gym’s country/account; bespoke non-Stripe rails such as JazzCash are not included. |
| 24 | Recurring billing: cards, direct debit, mandates | P0 | ✓ | ✓ | — | — | ✅ Built | Web signup offers explicit auto-renew consent. Stripe Connect PaymentIntents save eligible methods for off-session use; Stripe SetupIntents let members enroll or replace a method and collect any required mandate. An hourly worker creates idempotent renewal charges; succeeded webhooks extend the term, while failures move membership into a three-day grace period and the member can replace the method in Account. Method support and mandate requirements depend on Stripe and the gym's connected-account country/settings. Existing subscriptions stay non-renewing until the member opts in. Stripe card updater remains outside this row's delivered scope. |
| 25 | Failed-payment and overdue recovery (dunning) | P0 | ✓ | ✓ | — | — | ✅ Built | SaaS billing retains its Stripe retry/grace escalation. Member renewals use bounded retries only for Stripe-classified retryable declines (three attempts maximum, with shorter processor-error and 24-hour insufficient-funds backoff); hard declines and ambiguous errors stop automatic charges. Members receive day 1/2/3 recovery notices with an Account link; staff get idempotent day-one review, day-two call, and day-three manager escalation tasks. Failure/decline codes are stored for staff context. |
| 26 | Cash and manual payments with digital receipts | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `models/cash.py`, `cash_service.py`, `routes/cash.py:63` receipt PDF, `CashReconciliation` |
| 27 | Payment-proof verification (bank-transfer or wallet screenshots) | P1 | ✓ | ✓ | — | — | ✅ Built | Local Tesseract OCR extracts visible amount, date, payer/payee, transaction reference, and payment method without inventing missing values. A 64-bit dHash checks recent same-workspace receipts (latest 2,000) for near-duplicates. Validated images are stored with the receipt and served only to authorized workspace reviewers. Every screenshot remains pending until staff verify settlement in the bank/wallet; OCR scores are field/readability signals, never authenticity or settlement guarantees. API hosts require ImageMagick for validation/hash and Tesseract for OCR; if Tesseract is unavailable, receipts remain reviewable with an OCR-unavailable flag. Older uploads that stored only a filename cannot be backfilled and have no viewable image. |
| 28 | Invoices with local tax (VAT, GST, sales tax) | P1 | ✓ | ✓ | ✓ | — | ⚠️ Partial | `plan.tax_rate` end-to-end incl. inclusive-tax: `invoices_service.py:83`, `memberships_service.py:345 _amount_with_tax()`. Missing: country/region rule packs |
| 29 | Expenses, P&L, revenue by plan, branch or trainer | P1 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Revenue by plan/trainer ✅ (swarm specialists `rev_by_plan`, `payroll_commissions`). 0 matches for `expense`. No P&L, no branch dimension |
| 30 | Refunds, credits, chargeback evidence; accounting export | P1 | ✓ | ✓ | — | — | ⚠️ Partial | Verified Connect refunds, a tenant/member/currency-scoped immutable member credit vault, and Stripe customer invoice-credit balance/history preserve eligible unused value and prevent double credit/refund. Missing: chargeback evidence assembly and accounting export |
| 31 | 90-day onboarding journey (day 1, days 2–7, weeks 2–4) | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `models/onboarding.py`, `onboarding_service.py`, `routes/onboarding.py`, `workers/onboarding.py`; staff web page at `frontend/app/app/onboarding/page.tsx` supports roster/search/status, milestone completion, and pause/resume; member mobile screen at `mobileapp/src/app/(member)/onboarding.tsx` shows progress and milestones, linked from the member dashboard |
| 32 | Attendance-drop detection vs each member's own baseline | P0 | ✓ | ✓ | ✓ | — | ✅ Built | `retention_service.py` computes each member’s 14-day weekly pace against the prior 56 days; eligible members need 21+ days of tenure and a baseline of at least 1 visit/week. Staff can search/filter silent, severe, and moderate drops, compare baseline and recent counts, and open the member sheet at `frontend/app/app/retention/page.tsx` |
| 33 | Churn-risk score with reasons | P0 | ✓ | ✓ | ✓ | — | ✅ Built | Deterministic 0–100 risk roster with high/medium/low filters, signal reasons and weights, last visit, and member-sheet links at `frontend/app/app/retention/page.tsx`; API scoring remains in `retention_service.py` |
| 34 | Inactivity ladder: 5 days message, 10 days staff check-in, 14–21 days call | P0 | ✓ | ✓ | — | — | ✅ Built | Staff retention view shows each active member's current inactivity episode and rung delivery/completion state, with complete/skip actions; owners can edit outreach steps. `/inactivity-ladder/roster` returns tenant-scoped episode data for the UI; the daily worker retains dispatch and dedupe behavior. |
| 35 | Win-back campaigns; milestones; birthdays | P1 | ✓ | ✓ | — | — | ⚠️ Partial | `models/winback.py`, `models/celebration.py`, both services + workers. Missing: UI |
| 36 | NPS at day 7, 30, 90; complaint clustering | P1 | ✓ | ✓ | — | — | ⚠️ Partial | `nps_service.py:435 _nps()`, theme taxonomy at `:75`; day-7/30/90 daily sweep, `routes/nps.py`. Missing: UI |
| 37 | Challenges, streaks, leaderboards | P2 | ✓ | ✓ | — | — | ⚠️ Partial | `models/gamification.py` — `GymChallenge`, `MemberChallengeProgress`, `MemberStreak`; `routes/challenges.py`, daily worker. Missing: UI |
| 38 | Segmented campaigns by channel (WhatsApp, SMS, email, LINE, and others) | P1 | ✓ | ✓ | — | — | ⚠️ Partial | Segment resolution real (`campaign_service.py:82 _resolve_segment`); `CampaignChannel` = **IN_APP, EMAIL, BOTH** — not WhatsApp/SMS/LINE. `routes/campaigns.py` exists. Missing: the named channels, and UI |
| 39 | Seasonal offers (New Year, summer, Ramadan, Diwali, Lunar New Year, and more) | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `seasonal`. No local calendar |
| 40 | Referral programme; review requests after positive moments | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `review_request`. Referral *attribution* exists (row 9); no programme, no rewards, no review requests |
| 41 | Lead-ad integrations (Meta, Google, TikTok) | P1 | ✓ | — | — | — | ❌ Not built | — |
| 42 | Campaign ROI: leads → trials → members → revenue | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `roi` in campaign context. No funnel attribution |
| 43 | Landing pages; content ideas | P2 | ✓ | — | — | — | ❌ Not built | — |
| 44 | Trainer profiles, schedules, availability | P1 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Staff model + `Shift` (`models/staff.py:13`) + payroll rates. Missing: availability model, public profile |
| 45 | PT package sales and session tracking | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `pt_package` / `session_credit`. `member_trainer.py` is a coach link only |
| 46 | Trainer–client matching | P1 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Manual assignment only: `member_trainer.py`, `routes/members.py:245-283 assign_trainer/unassign`. Missing: goal/preference/timing matching |
| 47 | Workout and diet plans; progress tracking | P2 | ✓ | — | — | — | ❌ Not built | No routine/program/exercise model |
| 48 | Trainer performance by client retention | P1 | ✓ | — | — | — | ❌ Not built | No retention ranking per trainer |
| 49 | Timetable, booking, capacity, waitlist | P1 | ✓ | ✓ | ✓ | ✓ | ⚠️ Partial | `class_session.py:30 capacity: int = 20`, booking + cancel built (`classes_service.py:174`), member booking in web + mobile (`mobileapp/(member)/classes.tsx:60-140` idempotent). **0 matches for `waitlist`/`wait_list`** |
| 50 | No-show tracking and reminders | P1 | ✓ | — | — | — | ❌ Not built | `BookingStatus.NO_SHOW` exists (`core/constants.py:205`) and is in the DB enum, but is **never assigned anywhere** — 0 matches for `BookingStatus.NO_SHOW` outside the definition. No no-show detection, no reminder logic, no risk signal |
| 51 | Utilisation analytics; instructor substitution | P2 | ✓ | ✓ | — | — | ⚠️ Partial | Swarm specialists `ops_class_fill`, `ops_space_use`, `ops_peak_hours`. Missing: instructor substitution (0 matches for `substitut`) |
| 52 | Roles and permissions: owner, manager, front desk, trainer | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `Role` enum + `Capability` enum (incl. `TAKE_ATTENDANCE`), enforced in API deps |
| 53 | Activity and audit log | P0 | ✓ | ✓ | ✓ | — | ✅ Built | `models/audit_log.py`, `audit_service.py`, `routes/audit.py`, `record_audit()` called from services |
| 54 | Shifts, attendance, salaries, commissions, per-session pay | P1 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `models/staff.py:13 Shift` + `:221/:246 check_in/check_out`; `payroll_service.py` fixed+hourly+per-class+commission; `workers/payroll_runner.py:93` 12-month commission window; `frontend/app/app/payroll`, `mobileapp/(staff)/shift.tsx` |
| 55 | Staff performance: response time, conversions, collections | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for staff KPI/performance aggregation (`performance\|kpi\|response_time\|conversion`) |
| 56 | POS for supplements, merchandise, day passes | P1 | ✓ | ✓ | — | — | ⚠️ Partial | Day passes write real payments (`visitor_service.py:130`). 0 matches for `sale/retail/merch/stock` — no retail POS |
| 57 | Inventory and low-stock alerts | P2 | ✓ | — | — | — | ❌ Not built | 0 matches for `inventory` |
| 58 | Door and turnstile access tied to membership status | P2 | ✓ | — | — | — | ❌ Not built | No device integration |
| 59 | Equipment register and maintenance | P2 | ✓ | — | — | — | ❌ Not built | 0 matches for `asset` / `maintenance` |
| 60 | Peak-hour tracking; safety checklists | P2 | ✓ | ✓ | — | — | ⚠️ Partial | `ops_peak_hours` specialist. Missing: safety checklists |
| 61 | "Today" command centre | P0 | ✓ | — | ✓ | — | ⚠️ Partial | Dashboard priority queue combines team deadlines, receipt/member approvals, office invoices, and gym at-risk member count plus estimated revenue at risk. Still lacks per-person ranked actions with Send/Edit/Skip/Call |
| 62 | Daily owner brief on the owner's preferred channel | P0 | ✓ | ✓ | — | — | 🔧 Improvement | `routes/assistant.py:331 POST /briefing` → `workflows.weekly_briefing`. **Weekly, not daily**; **in-app only**, not on preferred channel |
| 63 | KPIs: active members, joins, churn, MRR, collections, conversion | P0 | ✓ | ✓ | ✓ | ✓ | ✅ Built | `analytics_service.py`, `routes/analytics.py`, KPI strip `frontend/app/app/page.tsx:196` |
| 64 | Revenue-at-risk panel; Wins feed (money recovered) | P0 | ✓ | ✓ | — | — | ⚠️ Partial | Revenue-at-risk remains on the owner dashboard. Web Retention now records tenant-scoped successful renewals that restore grace-status memberships and shows the latest five; mobile wins and lead-conversion attribution remain open. |
| 65 | Ask-anything analytics | P1 | ✓ | ✓ | ✓ | — | 🔧 Improvement | `routes/assistant.py`, `agent/` LangGraph graph, 40-specialist swarm, `ChatGroq` live when `GROQ_API_KEY` set (`agent/model.py:32`) with documented offline stub; web `frontend/app/app/assistant` + streaming API |
| 66 | Multi-branch, multi-currency, franchise royalties | P1–P2 | ✓ | — | — | — | ❌ Not built | 0 matches for `branch_id\|location_id\|site_id\|royalty\|franchise` in models. "venue" hits are the industry vertical. `default_currency` on org only |
| 67 | Waivers, health forms (PAR-Q), contracts with e-signature | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `waiver` / `parq`. All `esignature` hits are `Stripe-Signature` webhook headers |
| 68 | Consent management per channel and purpose (opt-in, opt-out) | P0 | ✓ | ✓ | ⚠️ | — | ⚠️ Partial | Lead email/SMS follow-up consent is stored separately. Owner/manager Settings records member email, SMS, and in-app marketing consent with audit history; email/in-app campaigns exclude members without matching consent, and inbound SMS STOP revokes SMS permission. Bulk SMS and country-specific purpose rules are not implemented |
| 69 | Data-subject requests: access, export, correction, erasure | P0 | ✓ | ✓ | ✓ | — | ⚠️ Partial | Owner/manager Settings queue records and audits requests; provides workspace-scoped member exports; correction uses existing profile editing; erasure redacts workspace profile, revokes access, and stops renewals before staff reviews linked records and retention. Shared identities are blocked for manual review; payment/attendance records and external processor/backups are retained |
| 70 | Auto-renewal disclosures, cooling-off and online cancellation | P0 | ✓ | — | — | — | ❌ Not built | 0 matches for `cooling_off\|auto_renewal` |
| 71 | Role-based access to sensitive data | P0 | ✓ | ✓ | — | — | ⚠️ Partial | Sensitive member health/ID fields are owner/manager-only; compensation endpoints are owner-only and member directory responses now omit rates for managers. Remaining: consistent field-level policy across all personal data and audit review |
| 72 | Evidence Vault (section 8) | P0 | ✓ | — | — | — | ❌ Not built | Audit log exists but is editable — no hash chain (`prev_hash: 0`), no soft delete (`deleted_at: 0`), no packs, no WORM, no residency. See rows 109–118 |
| 73 | Data residency options (EU, India, Gulf, and others) | P1 | ✓ | — | — | — | ❌ Not built | 0 matches for `storage_region` |
| 74 | Messaging-first member self-service: renew, pay, freeze, book | P0 | ✓ | ✓ | — | ✓ | ⚠️ Partial | Member app can book, view dues/history, and request/withdraw membership pauses (`(member)/membership-pause.tsx`; `GET/POST/DELETE /memberships/me/freeze-requests`). Owner/manager approval is available in the web member directory. Missing: renewal self-service and messaging/AI concierge. |
| 75 | Web portal or PWA: card, QR, dues, history | P1 | ✓ | ✓ | — | ✓ | ⚠️ Partial | Earlier audit said "No `mobile/` directory" — **`mobileapp/` exists**: Expo app, 44 screens under `mobileapp/src/app/`, member dues + payment history real (`payments.tsx`). Missing: digital member card, QR code (0 matches for `qr`/`member_card` in mobileapp) |
| 76 | Branded app, workout log, streaks, rewards | P2 | ✓ | ✓ | — | ✓ | ⚠️ Partial | Branded Expo app exists (`mobileapp/app.json`, industry-aware tabs in `(member)/_layout.tsx:31-70`). Backend streaks/challenges complete. Missing: workout log, streak/reward UI (0 matches in mobileapp screens) |
| 77 | Import from spreadsheets and competitor exports | P0 | ✓ | ✓ | — | — | ⚠️ Partial | Owner/manager web sheet uploads CSV with a downloadable template, 2 MB cap, activation-email disclosure, and created/skipped/row-error results. Backend creates pending-activation members and emails setup links. Competitor-specific formats and XLSX are not supported |
| 78 | Multilingual UI, right-to-left support, local date and number formats | P0 | ✓ | — | — | — | ❌ Not built | `org.country/timezone/default_currency` fields only. 0 matches for `i18n`/`translation`; the "locale" frontend hits are `toLocaleDateString` |
| 79 | Public API and webhooks; usage and cost meter | P1–P2 | ✓ | ✓ | — | — | ⚠️ Partial | Inbound Stripe webhooks ✅ signature-verified, two endpoints (`routes/webhooks.py:1-60` — `/webhooks/stripe`, `/webhooks/stripe-connect`). Missing: outbound public API, API keys, usage/cost meter |
| 80 | L1 Event ledger: append-only timeline per person, nothing overwritten | — | ✓ | ✓ | — | — | ⚠️ Partial | `AuditLog` + append-only attendance records. No per-person raw event stream (messages, notes, calls) as source of truth |
| 81 | L2 Understanding: LLM + rules extract intent, goal, objection, sentiment, payment details, freeze requests, any language | — | ✓ | ✓ | — | — | ⚠️ Partial | LLM live in assistant (`agent/model.py:32 ChatGroq`). Linked-member inbox messages with explicit membership-pause wording create review-only requests through deterministic phrase matching. General intent/entity extraction across arbitrary messages and external channels remains missing. |
| 82 | L3 Customer model: structured state + history — plan, expiry, dues, visit baseline, risk, goal, trainer, summary | — | ✓ | ✓ | — | — | ✅ Built | Snapshot + `plan_summaries.py` one-paragraph summary; risk from `retention_service.py`; visit baseline computed |
| 83 | L4 Signal engine: deterministic triggers + ML risk scoring (expiry, absence, visit drop, unpaid dues, unanswered lead) | — | ✓ | ✓ | — | — | ⚠️ Partial | Deterministic triggers (workers) + weighted score (`retention_service.py:166-245`). **No ML**; no unanswered-lead signal (no leads) |
| 84 | L5 Decision layer: next best action, draft, value estimate, owner assignment, autonomy level | — | ✓ | ✓ | — | — | ⚠️ Partial | Assistant proposes writes via `_proposal()` with draft text. No ranked next-best-action engine, no value estimate, no owner assignment, no autonomy level |
| 85 | L6 Action layer: auto-send · approve-then-send · staff task · call | — | ✓ | ✓ | — | — | ⚠️ Partial | Auto / approve / task all exist but scattered across workers and features. No call action; sends limited to email + push |
| 86 | L7 Outcome loop: did they reply, return, pay, renew? Model learns; Wins feed shows money recovered | — | ✓ | — | — | — | ❌ Not built | No learning loop, no outcome attribution, no Wins feed (`wins: 0`) |
| 87 | L0 Observe: update summary, compute risk, tag lead — always automatic | — | ✓ | ✓ | — | — | ⚠️ Partial | Risk computation and summaries run automatically in workers. No lead tagging (no leads) |
| 88 | L1 Auto-act (safe): FAQ reply, receipt, renewal reminder, class reminder, first lead reply — automatic, template-bound, reversible | — | ✓ | ✓ | — | — | ⚠️ Partial | Grace reminders, onboarding messages, celebration messages auto-send on schedule. No FAQ reply, no first-lead reply |
| 89 | L2 Approve first: discounts, win-back offers, complaint replies, freezes, bulk campaigns — one-tap approval | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Real human-in-the-loop gate: `agent/tools/write.py` 8 approval-gated writes via `_proposal()` / `_rejected()`. No one-tap approval UI for the full set |
| 90 | L3 Human only: refunds, price changes, medical topics, angry customers, cash mismatches — AI briefs a human | — | ✓ | — | — | — | ❌ Not built | Not distinguished from L2. No risk classification, no fail-closed timeout |
| 91 | Owner trust ladder: move any action type between levels; promote to L1 after seeing results; AI-disclosure setting per country | — | ✓ | — | — | — | ❌ Not built | No L0–L3 tiers, no owner-controlled promotion dial, no AI-disclosure setting (`AI Act Art. 50`) |
| 92 | Lead Concierge — instant reply, qualification, trial booking, follow-up | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Lead pipeline, trial/tour booking, consent-gated follow-up emails, controlled lost reasons, and profile score exist; instant reply and automated qualification remain absent |
| 93 | Renewal & Collections — expiry reminders, dunning, payment links, proof matching | — | ✓ | ✓ | — | — | ⚠️ Partial | Grace reminders (days 1/2/3), payment-proof pipeline, SaaS dunning ladder. Missing: payment links to members, member escalation ladder |
| 94 | Retention Coach — onboarding, absence check-ins, milestones, save offers | — | ✓ | ✓ | — | — | ✅ Built | Onboarding journey + inactivity ladder + win-back + celebrations all built with routes and daily workers |
| 95 | Front-Desk Copilot — check-in context, draft replies | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Check-in status card (row 18) + inbox AI draft (`inbox_service.py`). Missing: context summary at check-in beyond status flags |
| 96 | Owner Analyst — morning brief, Q&A, explanations | — | ✓ | ✓ | ✓ | — | ✅ Built | `POST /assistant/briefing` + ask-anything with 40 specialists (`routes/assistant.py:331`) |
| 97 | Reputation Agent — review requests, complaint clustering | — | ✓ | ✓ | — | — | ⚠️ Partial | NPS + complaint clustering built (`nps_service.py:75` theme taxonomy). Missing: review requests (0 matches for `review_request`) |
| 98 | Compliance Guard — checks consent, quiet hours, disclosures, cancellation rules per country | — | ✓ | — | — | — | ❌ Not built | No consent model, no country rule packs, no quiet hours — nothing to check against |
| 99 | Country Pack container: quiet hours, consent types, reminder schedules, cooling-off, cancellation channels, AI-disclosure text, retention defaults | — | ✓ | — | — | — | ❌ Not built | 0 matches for `country_pack`. `org.country/timezone/default_currency` are bare fields |
| 100 | Messaging channels by region (WhatsApp, SMS, LINE, WeChat, Telegram; email fallback) | — | ✓ | — | — | — | ⚠️ Partial | Inbox can send through Twilio SMS/WhatsApp, Telegram, LINE, and configured SMTP/Resend email. Signed inbound webhooks exist for Twilio, Telegram, and LINE. Instagram/Messenger, WeChat, inbound email, delivery callbacks, and regional provider selection remain unimplemented; supported providers are managed per workspace from Settings. |
| 101 | Local payment methods by region (SEPA, Pix, UPI AutoPay, M-Pesa, JazzCash, cards/ACH, Stripe/Adyen gateway) | — | ✓ | ✓ | — | — | ⚠️ Partial | Stripe + cash + bank_transfer + mobile_wallet generic. No regional rails (0 matches for `pix\|upi\|m_pesa\|sepa\|jazzcash`) |
| 102 | Privacy-law rule packs (GDPR, AI Act, CCPA, LGPD, DPDP, PDPL) with deadline tracking | — | ✓ | — | — | — | ❌ Not built | 0 matches for `gdpr\|privacy_rule\|deadline` tracking |
| 103 | Membership and messaging rules (US state auto-renewal, UK DMCC cooling-off, opt-in/STOP, quiet hours 8am–9pm) | — | ✓ | — | — | — | ❌ Not built | 0 matches for `quiet_hours\|cooling_off\|stop_keyword` |
| 104 | Languages and RTL (major languages, Hinglish/Roman Urdu/Spanglish/Arabizi, Arabic/Urdu/Hebrew layouts) | — | ✓ | — | — | — | ❌ Not built | 0 matches for `i18n` / `translation` / `rtl` |
| 105 | Currency: multi-currency pricing, reports, multi-branch consolidation | — | ✓ | ✓ | — | — | ⚠️ Partial | `org.default_currency` only. No multi-currency pricing or consolidation |
| 106 | Tax: VAT, GST, sales tax on invoices by country and region | — | ✓ | ✓ | — | — | ⚠️ Partial | `plan.tax_rate` incl. inclusive-tax handling (`memberships_service.py:345`). No country/region rule packs |
| 107 | Culture: local holidays/seasons, women-only hours, tone per country, local names and formats | — | ✓ | — | — | — | ❌ Not built | 0 matches for `holiday\|women_only\|tone` |
| 108 | Pricing: tiers adjusted for purchasing power (PPP) | — | ✓ | — | — | — | ❌ Not built | 0 matches for `ppp\|purchasing_power` |
| 109 | Append-only ledger: old versions kept on every edit | — | ✓ | — | — | — | ❌ Not built | `AuditLog` records changes but rows are editable/deletable. No version history |
| 110 | Soft delete + Recycle Bin: 90-day restorable, one-click undo | — | ✓ | — | — | — | ❌ Not built | 0 matches for `deleted_at` / `recycle`. Hard deletes only (`members_service.py:417 delete_member`) |
| 111 | Automatic Evidence Packs: PDF + Excel snapshot before delete, merge, bulk edit or payment change | — | ✓ | — | — | — | ❌ Not built | 0 matches for evidence pack generation |
| 112 | Tamper-evident audit chain: hash-chained entries + signed daily checkpoints outside the DB | — | ✓ | — | — | — | ❌ Not built | 0 matches for `prev_hash` / checkpoint signing |
| 113 | WORM storage: object lock blocks deletion/overwrite during retention | — | ✓ | — | — | — | ❌ Not built | 0 matches for `worm` / object lock |
| 114 | Point-in-time recovery + 3-2-1 backups (three copies, two media, one off-site) | — | ✓ | — | — | — | ❌ Not built | No PITR/backup config in codebase |
| 115 | Owner-held daily exports: daily Excel to email/cloud, monthly PDF statement | — | ✓ | — | — | — | ❌ Not built | 0 matches for daily export worker |
| 116 | Access and export log: records who viewed or exported what | — | ✓ | ✓ | — | — | ⚠️ Partial | Partial via `AuditLog` (record_audit covers state changes). No dedicated view/export logging |
| 117 | Owner alerts: bulk deletes, payment edits, large exports, after-hours changes | — | ✓ | — | — | — | ❌ Not built | No alert rules on audit events |
| 118 | Erasure with hash-only stub: personal fields erased, hash keeps chain valid | — | ✓ | — | — | — | ❌ Not built | No erasure path at all |
| 119 | Generic engine: Person / Event / Payment / "Say-Do-Pay" core | — | ✓ | ✓ | ✓ | ✓ | ⚠️ Partial | **Multi-industry built** — `org.industry ∈ {gym, office, academy}` (`models/organization.py:29`), `core/industry.py` per-industry labels/modules/checklist/nouns, schema-driven plan builder, `routes/industries.py`, industry-aware mobile tabs (`(member)/_layout.tsx:31-70`). Missing: clinic/salon/real-estate/B2B verticals |
| 120 | Sales-company pack (contacts, deals, meetings, quotes, lead ownership) | — | ✓ | — | — | — | ❌ Not built | 0 matches for sales-company pack |
| 121 | Pack builder / vertical marketplace | — | ✓ | — | — | — | ❌ Not built | Industry schemas are hardcoded, not installable packs |
| 122 | Today: one ranked list ("8 people need you today; USD 1,240 at stake") with Send / Edit / Skip / Call per card | — | ✓ | — | ✓ | — | ⚠️ Partial | `frontend/app/app/page.tsx` (494 lines) has KPI strip + headline metrics but no ranked action list, no value-at-stake cards, no per-item actions |
| 123 | Inbox: all channels in one place, member summary alongside, AI drafts | — | ✓ | ✓ | ✓ | — | ✅ Built | Inbox UI includes assignment/status, linked member context, AI drafts, and the supported multi-channel adapters, with public member chat and staff logging for phone/walk-in interactions. |
| 124 | Desk: check-in scanner with a status card for each arrival | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Web desk supports QR webcam scan, manual lookup, RFID keyboard-wedge scan, and post-check-in status receipt (`attendance/page.tsx`; `POST /attendance/card/check-in`). Biometric hardware integration remains unbuilt and outside the requested web scope. |
| 125 | People: one scrollable timeline of messages, visits and payments per person | — | ✓ | ✓ | ✓ | — | 🔧 Improvement | Member detail sheet shows visits + payments (`member_detail`, `frontend/app/app/members/[memberId]`). No unified message timeline |
| 126 | Money: collections, dues, cash drawer, P&L, recovered this month | — | ✓ | — | ✓ | — | ⚠️ Partial | Collections/dues/cash drawer ✅ (`frontend/app/app/cash`, `payments`, `analytics`). No P&L (row 29), no "recovered this month" |
| 127 | Ask: natural-language questions in any language, action buttons in the answer | — | ✓ | ✓ | ✓ | — | ✅ Built | Assistant with LangGraph + 40 specialists, streaming (`frontend/app/api/assistant/stream`), approval-gated write actions |
| 128 | Wins: feed of members saved, money recovered, leads converted | — | ✓ | — | — | — | ❌ Not built | 0 matches for wins feed. Shares root cause with row 64 and layer 86 |
| 129 | Paper-register photo import with immediate expired-member and unpaid-dues opportunity scan | — | ✓ | — | — | — | ❌ Not built | Spreadsheet/CSV import exists, but no paper-register image import or instant opportunity analysis |
| 130 | Explain every AI suggestion with a visible “Why?” line, source evidence, and value at stake | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Retention risks expose reasons and some assistant answers explain results; no uniform source-linked explanation contract |
| 131 | Undo everywhere with a clear owner-controlled autonomy dial | — | ✓ | ✓ | — | — | ⚠️ Partial | Selected actions can be reversed and approvals exist; there is no universal undo or configurable trust dial |
| 132 | Learn the gym's voice from past conversations and owner edits, including culture-specific tone | — | ✓ | — | — | — | ❌ Not built | Tone is not learned from approved edits or historical conversations |
| 133 | Zero-inbox completion state showing “All done for today” | — | ✓ | — | — | — | ❌ Not built | Inbox/task states exist, but no unified daily completion state is implemented |
| 134 | Front-desk UX for inexpensive tablets/old desktops, large controls, sub-second check-in, and instant Today loading | — | ✓ | ✓ | ✓ | ✓ | ⚠️ Partial | Responsive check-in surfaces exist; device/performance budgets and measured sub-second guarantees do not |
| 135 | Messaging economics controls: consolidate replies, classify utility/marketing templates, pace sends, and estimate broadcast cost | — | ✓ | ✓ | — | — | ⚠️ Partial | Campaign records and generic limits exist; no provider-aware template category, consolidation, pacing, or reliable cost estimator |
| 136 | Guided import with AI-assisted cleaning, duplicate merge, and low-quality-data handling | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | CSV import and lead duplicate rejection exist; guided cleaning and merge workflows are incomplete |
| 137 | Mask personally identifiable information before sending prompts to AI providers | — | ✓ | — | — | — | ❌ Not built | No central prompt-redaction/PII-masking gateway was found |
| 138 | Evidence Vault UX: per-record History, Download Evidence, Recycle Bin, safety score, and deletion receipts | — | ✓ | ✓ | — | — | ⚠️ Partial | Audit history and selected exports exist; the complete user-facing evidence suite does not |
| 139 | Block bulk deletes until owner approval and generate an Evidence Pack for every affected record | — | ✓ | — | — | — | ❌ Not built | No bulk-delete approval threshold or per-record evidence-pack workflow exists |
| 140 | Preserve signed-document evidence, renewal/cancellation delivery proof, removed-staff ownership snapshots, and daily signed checkpoints | — | ✓ | — | — | — | ❌ Not built | These automatic evidence events and proofs are not implemented |
| 141 | Sales Pack intake from official messaging numbers, SMS, email, forms, ads, calls, imports, and listing portals | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Manual lead intake/import and source fields exist; official provider and listing-portal ingestion do not |
| 142 | Sales Pack routing by round robin, territory, product, or language with SLA timers and no-response reassignment | — | ✓ | — | — | — | ❌ Not built | No configurable sales routing or SLA engine exists |
| 143 | Sales Pack pipeline with custom stages, value, close date, and conversation-driven AI stage updates | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | A fixed lead pipeline and audited transitions exist; custom stages/value/close date/AI updates do not |
| 144 | Sales Pack AI for call/meeting summaries, multilingual voice transcription, follow-up drafts, deal risk, and “who to call today” | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | General assistant and inbox drafts exist; call ingestion, transcription, deal risk, and ranked sales queue are incomplete |
| 145 | Sales Pack quotes, invoices, deposits, payment links, and multi-currency handling | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Membership invoices/payments exist; sales quotes/deposits and true multi-currency deal flows do not |
| 146 | Sales Pack team targets, leaderboards, activity, commissions, and coaching insights | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | Staff activity/payroll commissions exist; sales targets, leaderboards, and coaching insights are incomplete |
| 147 | Field-sales location check-ins, voice visit notes, and route planning | — | ✓ | — | — | — | ❌ Not built | Attendance check-ins are not field-sales visits; no route planning or voice visit-note flow exists |
| 148 | Sales lead ownership history and conversations locked in Evidence Vault, retained when representatives leave | — | ✓ | ✓ | — | — | ⚠️ Partial | Lead source/history and user audit records exist; immutable rep ownership/conversation preservation does not |
| 149 | Sales manager daily brief for new, untouched, and stalled leads with forecast | — | ✓ | ✓ | ✓ | — | ⚠️ Partial | General owner briefing and lead stages exist; no complete sales-specific forecast brief |
| 150 | Configurable Industry Pack contract for vocabulary, schema, signals, playbooks, dashboards, integrations, and compliance | — | ✓ | ✓ | ✓ | ✓ | ⚠️ Partial | Industry labels/modules/schemas exist for hard-coded verticals; installable configuration-only packs do not |
| 151 | Front-desk voice notes transformed by AI into clean outbound messages | — | ✓ | — | — | — | ❌ Not built | No voice-note capture, transcription, cleanup, and review/send flow exists |
| 152 | Messaging-native lead/member self-service in the customer's usual app without requiring an app download | — | ✓ | ✓ | ✓ | ✓ | ⚠️ Partial | Native mobile self-service and an internal inbox exist; no complete WhatsApp/SMS/LINE/WeChat self-service flow |

---

## Part B — App-only features (in code, not itemised in the PDF)

| # | Feature | Pri | PDF | API | Web | Mobile | Status | Evidence / gap |
|---|---|---|---|---|---|---|---|---|
| A1 | Authentication: register, email-code verify, login, JWT refresh, password reset | P0 | — | ✓ | ✓ | ✓ | ✅ Built | `auth.py` (24 endpoints); web `/login` `/register` `/forgot-password`; mobile `(auth)` group = 20 screens |
| A2 | MFA (TOTP) with QR enrolment + recovery codes | P0 | — | ✓ | ✓ | ✓ | ✅ Built | `auth.py /mfa*`, `/recover-codes`, `mfa_service.py`; web Account→Security `MfaCard.tsx`; mobile `(auth)/mfa*` |
| A3 | Magic-link passwordless login | P1 | — | ✓ | ✓ | ✓ | ✅ Built | `/magic-link/request` + `/magic-link/verify`; web `/magic-link`; mobile `(auth)/magic-link` |
| A4 | Session inventory and revocation (self + admin) | P0 | — | ✓ | ✓ | — | ✅ Built | `/sessions`, `/admin/sessions`, revoke; web `SettingsView.tsx` section `sessions` |
| A5 | Multi-org membership and org switcher | P1 | — | ✓ | — | — | ⚠️ Partial | `/my-organizations`, `/switch-org` exist; **no switcher UI** — web and mobile only ask for an org code at login |
| A6 | Member self-signup: org code → verify → password → plan → pay | P0 | — | ✓ | — | ✓ | ✅ Built | `memberships.py signup/*`; mobile `(auth)/join/{pick-plan,verify-email,set-password,pay}`; no web equivalent |
| A7 | Invite-only redemption (single-use code bound to email) | P1 | — | ✓ | ✓ | ✓ | ✅ Built | `POST /members/invite`, `/memberships/invite/redeem`; web `/redeem`; mobile `(auth)/redeem` |
| A8 | Approved-enrollment approval queue (prospect review) | P1 | — | ✓ | ✓ | ✓ | ✅ Built | `GET /members/approval-queue`, `POST /{id}/approval`; web `/approvals`; mobile `(admin)/approvals` |
| A9 | Notification centre (bell, unread count, mark read) | P1 | — | ✓ | — | ✓ | ✅ Built | `notifications.py` (4 endpoints); mobile `notification-bell.tsx` + `realtime.ts`; **no web bell** |
| A10 | Real-time sync over WebSocket (ticketed) | P1 | — | ✓ | ✓ | ✓ | ✅ Built | `routes/ws.py /ws`, `frontend/app/api/ws-ticket`; web live attendance; mobile `lib/realtime.ts` |
| A11 | Gym registration wizard + setup checklist | P0 | — | ✓ | ✓ | ✓ | ✅ Built | `/organizations/register`, `/me/checklist`; web `/create-gym`; mobile `(auth)/register/step-1..3`, `tier`, `payment` |
| A12 | Stripe Connect onboarding and connect status | P0 | — | ✓ | ✓ | ✓ | ✅ Built | `/me/connect`, `/me/connect/complete`; web `SettingsView` payments; mobile `gym-settings/stripe.tsx` |
| A13 | Org code rotation, enrollment mode, gym open/closed status | P0 | — | ✓ | ✓ | ✓ | ✅ Built | `/me/rotate-code`, `/me/enrollment`, `/me/gym-status`; mobile `gym-settings/rotate-code`, `(admin)/gym-status` |
| A14 | SaaS subscription: tier upgrade/downgrade/cancel, invoices, PDF | P0 | — | ✓ | ✓ | — | ⚠️ Partial | Stripe-backed upgrade/proration, scheduled downgrade, immediate or end-of-period cancellation, resume/recheckout, customer invoice-credit history, invoices and PDFs; web Billing settings expose the controls. Live billing actions depend on Stripe keys, portal configuration, and webhook forwarding. Cancellation keeps the workspace readable. |
| A15 | Space / resource booking (rooms and slots, capacity) | P1 | — | ✓ | ✓ | ✓ | ✅ Built | `space.py` (8 endpoints); web `/space`; mobile `(member)/space` |
| A16 | Multi-industry verticals (gym / office / academy) + offer schema | P1 | — | ✓ | ✓ | ✓ | ⚠️ Partial | Industry catalog, offer schemas, registration pickers, and industry-aware screens exist for three hard-coded verticals. No installable pack builder or other vertical packs |
| A17 | Idempotency framework (key claim, hash check, stuck reconciliation) | P0 | — | ✓ | — | — | ✅ Built | `idempotency_service.py` (claim/complete/fail, 106 lines); used by payments, classes, invoices, memberships, assistant |
| A18 | Email + push transports (transactional delivery) | P0 | — | ✓ | — | — | ⚠️ Partial | `integrations/email.py`, `push.py`; **no SMS/WhatsApp/LINE/Telegram transport exists** — see PDF rows 19/38/100 |

---

## Notes on the three 🔧 Improvement rows

| Row | Feature | What works | What to improve |
|---|---|---|---|
| 62 | Daily owner brief | `POST /assistant/briefing` → `workflows.weekly_briefing` | Runs **weekly**, not daily, and lands **in-app only** instead of the owner's preferred channel |
| 65 | Ask-anything analytics | LangGraph graph, 40 specialists, streaming, write actions | Needs `GROQ_API_KEY` in production — without it every answer is the `[offline stub]` |
| 125 | People timeline | Member sheet shows visits + payments | No unified message/visit/payment timeline on one scroll |

---

## Where the biggest holes are

1. **Sales & leads (rows 1–8)** — lead profiles, pipeline, trial/tour booking, consent-gated follow-up emails, controlled lost reasons, and explainable profile scoring are implemented; manual intake remains partial. Provider capture, instant replies, qualification automation, and speed-to-lead reporting remain missing.
2. **Evidence Vault (rows 109–118)** — 9 of 10 not built: no hash chain, no soft delete, no evidence packs, no WORM.
3. **Compliance & legal (rows 67–73)** — 6 of 7 not built: no waivers, consent, data-subject requests or cooling-off.
4. **Localisation (§6, rows 99–108)** — 7 of 10 not built: no i18n/RTL, no local payment rails, no privacy-law packs.
5. **Remaining retention UI (rows 35–37)** — rows 31–34 now have staff UI; row 31 also has a member screen. Three retention workflows still need feature-specific UI.

---

*The Blueprint and code-only inventory above is followed by the complete Strategy Report feature inventory below. Overlapping requirements remain explicitly marked so they are not mistaken for separate underlying capabilities.*

---

## Part C — Strategy Report features (rows S001–S106)

Status meanings remain the same as the Blueprint audit: `Built` is usable
end-to-end, `Partial` has meaningful implementation but an incomplete flow or
surface, and `Not built` has no production-capable implementation. `Deferred`
means the Strategy Report itself says not to build it before validation.

### C1 Cases, context, control, evidence, and outcomes

| ID | Requirement | Pri | Relation | Status | Current evidence or exact gap |
|---|---|---|---|---|---|
| S001 | First-class operational case with a measurable business objective | P0 | Strategy-only | Not built | Tasks, approvals, and alerts exist, but there is no case aggregate |
| S002 | Case stores source evidence, owner/agent, allowed actions, deadline, resolution criteria, and outcome | P0 | Strategy-only | Not built | No shared case schema or lifecycle exists |
| S003 | Case shows situation and value at risk | P0 | Both: B64/B122 | Partial | Retention and revenue-at-risk data exist but are not attached to cases |
| S004 | Close a case only after evidence verifies its resolution | P0 | Strategy-only | Not built | Existing tasks can complete without verified business outcome evidence |
| S005 | Simple Mode creates workflows from plain-language intent | P1 | Strategy-only | Not built | Assistant can answer and propose selected writes, not define workflows |
| S006 | Advanced Mode provides a connected visual workflow canvas | P2 | Both: B121 | Not built | No Flow Studio or workflow graph editor exists |
| S007 | Owner reviews recipients, conditions, messages, budgets, and approvals before activation | P1 | Strategy-only | Not built | No workflow draft/review/publish lifecycle exists |
| S008 | Simulate workflows on historical data with no side effects | P1 | Strategy-only | Not built | No replay-safe simulation runtime exists |
| S009 | Inspect workflow execution history and troubleshoot failed nodes | P1 | Both: B76 | Not built | Feature logs exist, but no shared run/step trace exists |
| S010 | Business context links customer, membership, attendance, trainer, messages, and payments | P0 | Both: B56/B125 | Partial | Structured records exist but no unified source-linked context graph/timeline |
| S011 | Store observed facts, model estimates, and recommendations as different evidence classes | P0 | Strategy-only | Not built | No common provenance/confidence model enforces this distinction |
| S012 | Policy-aware next-best-action recommendation | P1 | Both: B78 | Partial | Assistant and retention rules suggest actions, but do not rank through one policy layer |
| S013 | Formal L0 observe, L1 safe auto-act, L2 approval, and L3 human-only levels | P0 | Both: B87–B91 | Partial | Some automatic and approval-gated paths exist; no common autonomy classification |
| S014 | Enforce autonomy permissions in backend services, not in prompts | P0 | Strategy-only | Partial | RBAC and write tools enforce selected paths, but not every automated action |
| S015 | Workflow-wide emergency stop | P0 | Strategy-only | Not built | No workflow/agent kill switch exists |
| S016 | Per-customer and workflow message-frequency limits | P0 | Both: B91/B103 | Not built | No cross-channel frequency policy exists |
| S017 | Spending, action, tool-call, time, and execution-deadline caps | P0 | Strategy-only | Not built | No finite run-budget model exists |
| S018 | Approval expiry and fail-closed timeout | P0 | Strategy-only | Not built | Selected approvals exist without a shared expiry policy |
| S019 | Pause actions for one workflow, organization, or location | P0 | Strategy-only | Not built | No common pause scope exists |
| S020 | Tamper-evident audit events | P1 | Both: B112 | Not built | Audit rows are not hash-chained or externally checkpointed |
| S021 | Preserve workflow definitions and versions used for every action | P1 | Strategy-only | Not built | No workflow definition/version records exist |
| S022 | Cryptographically attributable approval signatures | P1 | Strategy-only | Not built | Approver IDs may exist on domain approvals, but no signed approval evidence |
| S023 | Configurable financial evidence exports | P1 | Both: B111/B115 | Partial | Invoice/report exports exist; no case/workflow evidence export package |
| S024 | Evidence retention schedules, redaction, lawful erasure, and scoped access | P0 | Both: B69–B73/B118 | Partial | RBAC exists; retention, redaction, DSAR, and lawful erasure workflows do not |
| S025 | Outcome comparison against baseline or suitable control group | P1 | Strategy-only | Not built | No counterfactual or control-group analysis exists |
| S026 | Track conversion, retention, contribution margin, time saved, complaints, and message costs | P0 | Both: B64/B66/B86 | Partial | Some conversion/revenue/NPS data exists; no workflow-linked cost/outcome model |
| S027 | Country Pack as the deployable localization unit | P1 | Both: B99 | Not built | Country, currency, and timezone are fields, not an enforceable pack |
| S028 | Country Pack binds language, providers, gateways, currency, timezone, policies, and local workflows | P1 | Both: B99–B108 | Not built | No pack contract or runtime enforcement exists |

### C2 Commercial product scope and platform expansion

| ID | Requirement | Pri | Relation | Status | Current evidence or exact gap |
|---|---|---|---|---|---|
| S029 | Core CRM: leads, contacts, membership status, searchable history | P0 | Both: B1/B56 | Partial | Core records and search exist; customer history remains fragmented |
| S030 | Unified timeline of conversations, visits, billing events, and staff actions | P0 | Both: B125 | Partial | Member views show visits/payments but not one complete timeline |
| S031 | Integration layer with webhooks, CSV import, and one or two supported incumbent systems | P0 | Both: B2/B100 | Partial | Webhooks/CSV exist; no supported incumbent gym-system connector |
| S032 | Shared inbox, authorized outbound follow-up, and reply tracking | P0 | Both: B123 | Partial | Inbox stores conversations/drafts; no production external provider loop |
| S033 | Five configurable workflow templates | P0 | Strategy-only | Not built | Feature-specific workers are not reusable configurable templates |
| S034 | AI summaries, drafts, classification, and action suggestions | P0 | Both: B77–B83 | Partial | Drafts/assistant/some classification exist; source-grounding is inconsistent |
| S035 | Owner Today dashboard, staff tasks, and approval inbox | P0 | Both: B59/B122 | Partial | Dashboard/tasks/approvals exist but are not one ranked case queue |
| S036 | Deduplication, retries, message limits, and execution logs | P0 | Both: B76 | Partial | Idempotency and some retries/logs exist; shared message/run controls do not |
| S037 | Roles, channel consent, workflow permissions, and human handoffs | P0 | Both: B67–B71/B89 | Partial | RBAC and selected approvals exist; consent and workflow policy are missing |
| S038 | Lead conversion, renewal outcomes, hours saved, and estimated financial impact | P0 | Both: B8/B64/B66 | Partial | Some conversion/revenue metrics exist; time saved and credible impact do not |
| S039 | Flow Studio branching, reusable steps, and versioning | P1 | Strategy-only | Not built | No shared workflow definition format or editor exists |
| S040 | AI Workflow Copilot creates and debugs workflows in natural language | P1 | Strategy-only | Not built | Current assistant does not author or debug workflow definitions |
| S041 | Long-running, resumable workflows with approvals and checkpoints | P1 | Strategy-only | Not built | Scheduled workers do not preserve durable run checkpoints |
| S042 | Advanced cancellation prevention, failed-payment handling, and retention cases | P1 | Both: B31–B37/B93 | Partial | Rules and reminders exist; no case-based recovery loop |
| S043 | Staff work queues, deadlines, escalation, and performance tracking | P1 | Both: B47/B50/B53 | Partial | Tasks and payroll/attendance metrics exist; common escalation/performance loop does not |
| S044 | Multi-location permissions, policy inheritance, and standardized workflows | P1 | Both: B63 | Not built | Organization switching is not location hierarchy or policy inheritance |
| S045 | Marketplace of verified industry workflow templates/modules | P2 | Both: B121 | Deferred | No marketplace; Strategy says it must follow validated workflows |
| S046 | Industry Pack SDK for fitness, salons, education, and home services | P2 | Both: B119–B121 | Deferred | Three hard-coded industries exist; no installable pack SDK |
| S047 | Developer platform with APIs, SDKs, signed webhooks, and integrations | P2 | Strategy-only | Partial | REST API and verified inbound Stripe webhooks exist; no public SDK/integration platform |
| S048 | Delegated AI staff interface across specialized permissioned agents | P2 | Both: B77–B85 | Partial | Specialized assistant graph exists; durable delegated work and uniform policy do not |
| S049 | Predictive retention and demand optimization after sufficient data | P2 | Both: B33/B45 | Deferred | Current risk logic is deterministic; Strategy delays predictive models until evidence exists |
| S050 | Franchise management with central policy, regional oversight, and branch analytics | P2 | Both: B63 | Deferred | No franchise hierarchy exists |
| S051 | Region-specific deployments and enterprise controls | P2 | Strategy-only | Deferred | No data-residency deployment/control plane exists |

### C3 Workflow engine contract and lifecycle

| ID | Requirement | Pri | Relation | Status | Current evidence or exact gap |
|---|---|---|---|---|---|
| S052 | Strict typed input/output contract for every workflow node | P0 | Strategy-only | Not built | Service schemas exist, but there is no workflow-node contract system |
| S053 | Trigger nodes: lead, payment failure, expiry, check-in, schedule, webhook | P0 | Both | Partial | Domain events/workers cover several triggers but not through one engine |
| S054 | Data nodes: customer, membership, history, and availability lookup | P0 | Strategy-only | Not built | Services can query data; no reusable workflow data nodes exist |
| S055 | Condition nodes: branch, compare, filter, consent, duplicate | P0 | Strategy-only | Partial | Business rules exist; consent and reusable typed condition nodes do not |
| S056 | AI nodes: classify, summarize, draft, structured extraction | P0 | Both: B77–B85 | Partial | Several AI functions exist but are not reusable workflow nodes |
| S057 | Action nodes: message, task, booking, CRM update, payment-link request | P0 | Both: B85 | Partial | Tasks/bookings/updates exist; external messaging/payment-link action set is incomplete |
| S058 | Control nodes: wait, retry, approval, stop, escalation, error branch | P0 | Strategy-only | Partial | Workers retry and approvals exist in places; no common control-node runtime |
| S059 | Measurement nodes: outcome, baseline, expense, and report | P0 | Strategy-only | Not built | No workflow-linked measurement node contract exists |
| S060 | Parse natural language into a structured workflow specification | P1 | Strategy-only | Not built | No workflow specification generator exists |
| S061 | Identify required events and integrations during workflow creation | P1 | Strategy-only | Not built | No workflow dependency resolver exists |
| S062 | Present proposed workflow with editable conditions | P1 | Strategy-only | Not built | No workflow draft UI exists |
| S063 | Detect missing permissions and unsupported actions before publication | P1 | Strategy-only | Partial | Route/tool authorization exists, but no workflow preflight validator |
| S064 | Run dry-run simulation before activation | P1 | Strategy-only | Not built | No side-effect-free workflow simulator exists |
| S065 | Require explicit approval before workflow activation | P1 | Strategy-only | Not built | No draft-to-active workflow lifecycle exists |
| S066 | Publish an immutable versioned workflow | P1 | Strategy-only | Not built | No workflow records or immutable versions exist |
| S067 | Explain any node using its inputs, decision, and outcome | P1 | Strategy-only | Not built | No shared execution trace exists |
| S068 | Pin active runs to their starting version unless explicitly migrated | P1 | Strategy-only | Not built | No run/version model exists |
| S069 | Dedicated manager approval inbox outside the editor | P0 | Both: B89 | Partial | Approval screens exist, but not a unified workflow action inbox |
| S070 | Run limits for actions, costs, deadlines, and customer frequency | P0 | Strategy-only | Not built | No workflow budget/limit policy exists |
| S071 | Retry safe failures and route exhausted/unsafe failures to a human | P0 | Strategy-only | Partial | Some jobs retry; no common failure classification and escalation path |
| S072 | Business-specific templates instead of an empty canvas | P0 | Strategy-only | Partial | Fixed domain workers embody workflows but are not configurable templates |
| S073 | Kill switch prevents new workflow or agent actions immediately | P0 | Strategy-only | Not built | No workflow/agent action circuit breaker exists |

### C4 Seven showcase workflows

| ID | Requirement | Pri | Relation | Status | Current evidence or exact gap |
|---|---|---|---|---|---|
| S074 | Trial-to-paid: capture, qualify, schedule, confirm, attend, follow up, verify purchase | P0 | Both: B1–B8 | Partial | Trial/tour scheduling, attendance tracking, and consent-gated day 0/1/3/7 follow-up emails exist; instant capture, qualification, booking confirmations, and verified purchase loop remain absent |
| S075 | Retention: detect baseline decline, review context, intervene, observe return | P0 | Both: B31–B37 | Partial | Detection and messages/tasks exist; case, provider replies, and verified incremental result do not |
| S076 | Payment recovery: verified failure, permitted outreach/link, provider verification, closure | P0 | Both: B23/B25/B93 | Partial | Payment events and dunning pieces exist; member recovery workflow is incomplete |
| S077 | Complaint resolution: classify, gather policy/context, assign, respond, track, request feedback | P1 | Both: B44/B97 | Partial | NPS/theme clustering and tasks exist; no complaint case lifecycle |
| S078 | Staff accountability: assign, monitor deadline, remind once, escalate, record completion | P1 | Both: B47/B50 | Partial | Tasks/deadlines exist; deduplicated reminder/escalation workflow does not |
| S079 | Campaign optimization: source to booking/purchase, spend, conversion, and recommendations | P1 | Both: B38–B41 | Partial | Campaign/segment data exists; spend-to-confirmed-outcome optimization is incomplete |
| S080 | Multi-location operations: aggregate authorized branch signals and route exceptions | P1 | Both: B63 | Not built | No branch hierarchy, scoped aggregation, or location-manager routing exists |

### C5 Architecture, safety rules, evaluation, and owner UX

| ID | Requirement | Pri | Relation | Status | Current evidence or exact gap |
|---|---|---|---|---|---|
| S081 | Append-only business event ledger with transactional outbox | P0 | Both: B109 | Not built | Domain/audit rows exist; no unified ledger/outbox transaction exists |
| S082 | Durable engine for schedules, waits, retries, approvals, and checkpoints | P0 | Strategy-only | Not built | Background jobs exist without durable workflow state |
| S083 | Central policy/tool gateway for authorization, validation, approvals, limits, and idempotency | P0 | Strategy-only | Partial | Dependencies, RBAC, tool wrappers, and idempotency exist but are not one gateway |
| S084 | Typed AI tools with explicit state and checkpoints | P0 | Strategy-only | Partial | Typed assistant tools exist; resumable state/checkpoints do not |
| S085 | Semantic retrieval with PostgreSQL/pgvector only when justified | P2 | Strategy-only | Deferred | Correctly absent until a validated retrieval requirement exists |
| S086 | Retention-controlled object storage for files and evidence | P1 | Both: B113/B114 | Partial | File/storage abstractions exist; WORM and enforceable retention do not |
| S087 | Structured logs, traces, execution metrics, and alerting | P0 | Both: B76 | Partial | Application logs/metrics exist; workflow-level traces and alerts do not |
| S088 | Approved external integrations for gym systems, messaging, payments, and calendars | P0 | Both: B2/B100/B101 | Partial | Stripe/email/push exist; gym-system, two-way messaging, and calendar connectors are missing |
| S089 | LLMs mutate state only through validated application tools | P0 | Strategy-only | Built | Assistant write actions route through typed application tools and approval gates |
| S090 | Every external/state-changing action is idempotent | P0 | Both: A17 | Partial | Framework is strong but is not uniformly required on every state-changing endpoint |
| S091 | Financial settlement comes only from verified payment records | P0 | Both: B23/B84 | Partial | Stripe flows verify provider events; screenshot claims require staff confirmation against the receiving bank/wallet and are never auto-booked from OCR |
| S092 | Every workflow is versioned and reconstructable | P0 | Strategy-only | Not built | No workflow version/execution provenance model exists |
| S093 | Tenant isolation at database, service, and tool layers | P0 | Both | Partial | Service/JWT scoping is broad; complete RLS/tool-layer proof is not established |
| S094 | Every agent has finite tool-call, time, money, and action budgets | P0 | Strategy-only | Not built | No agent budget object or enforcement exists |
| S095 | Automated adversarial evaluations for wrong customer, discount, injection, hallucination, opt-out, webhook, and conflict failures | P0 | Strategy-only | Not built | Normal tests exist; no dedicated safety/evaluation suite covers this matrix |
| S096 | Navigation centered on Today, Customers, Cases, Flows, Approvals, and Evidence | P1 | Strategy-only | Partial | Customers and approvals exist; cases, flows, evidence, and ranked Today are incomplete |
| S097 | Role-specific owner, manager, and automation-specialist workspaces | P1 | Strategy-only | Partial | Role-based navigation exists, but not the three Strategy workspaces |
| S098 | Ask interface returns filtered, source-linked operational lists | P0 | Both: B127 | Partial | Ask is capable, but evidence links and uniform source grounding are incomplete |
| S099 | Ask interface prepares a reviewable action batch | P0 | Both: B127 | Partial | Selected proposal actions exist; general batch review does not |
| S100 | Ask executes only authorized, consent-checked actions and returns a result summary | P0 | Both: B127 | Partial | Authorization/approval exists for selected tools; consent and uniform execution summaries do not |
| S101 | Native management suite covering complete scheduling, billing, attendance, and facility operations | P2 | Both: B42–B58 | Partial | Broad native operations exist, but scheduling depth, POS/inventory, access hardware, and facility maintenance remain incomplete |
| S102 | Production Flow Studio nodes have configuration panels, connection handles, schemas, validation, and execution traces | P1 | Strategy-only | Not built | No production visual workflow editor or node-inspection experience exists |
| S103 | Complex cross-system workflows coordinate messaging, attendance, CRM, booking, and verified payment data | P0 | Strategy-only | Partial | Each domain exists in varying depth, but no shared workflow engine coordinates them end-to-end |
| S104 | AI analytics answers natural-language questions grounded in live business data | P1 | Both: B65/B127 | Partial | Ask-anything analytics exists; production grounding, evidence links, and complete live-domain coverage remain incomplete |
| S105 | Mistaken automated actions have defined rollback or remediation procedures | P0 | Strategy-only | Not built | Selected domain reversals exist, but no platform-wide remediation contract or operator flow exists |
| S106 | Payment workflow nodes validate amounts against billing records and authorized rules, never arbitrary model output | P0 | Strategy-only | Partial | Payment services validate structured records, but no typed workflow payment node or uniform AI boundary exists |

---

*Authoritative inventory after source-to-row recheck: 152 Blueprint-derived rows, 18 code-only rows, and 106 Strategy Report feature rows. Strategy overlaps are traceability rows, not additional unique capabilities. The Notion page remains unverified.*
