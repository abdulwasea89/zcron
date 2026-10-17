# Web product gap audit

Reviewed: 2026-10-15
Scope: static review of the web app routes and their visible API interactions. This identifies likely user-facing gaps from the current code; it is not a runtime usability, security, or data accuracy certification.

## Highest priority

| Priority | Area | User impact | Suggested completion | Status |
|---|---|---|---|---|
| P0 | Existing local database schema | Older SQLite databases lacked onboarding columns, causing `/organizations/me` to fail and the app shell to redirect a successfully authenticated owner to login. | Keep additive SQLite upgrades in `backend/app/db/session.py`; production uses the versioned Alembic migration. | Fixed in the current local DB; automatic additive upgrade added for existing SQLite installs. |
| P0 | Subscription lifecycle | Hosted Checkout, prorated tier upgrades, scheduled end-of-period downgrades, immediate/period-end cancellation, resume, invoice history and Stripe customer credit history are implemented. Billing changes use Stripe subscription and customer records; canceled workspaces remain readable. | Configure Customer Portal and both platform/Connect webhook secrets; validate checkout, proration, cancellation, credit carry-forward and 3-D Secure with the Stripe test account. | Web flow implemented; live verification awaits `STRIPE_PUBLISHABLE_KEY`, `STRIPE_CONNECT_WEBHOOK_SECRET`, and Customer Portal setup. |
| P1 | Analytics | The page requests a single `/analytics/revenue` result and has no visible period selector, comparison window, or export. Owners cannot answer “what changed this month?” from the page. | Add date range and comparison controls, consistent timezone/currency labels, and CSV export; ensure API aggregation follows those ranges. | Open |
| P1 | Assistant | The shell provides the assistant UI, but the route needs clear source attribution and links from answers to the relevant records; users need to distinguish confirmed data from suggestions. | Show data freshness, cited records, and “open record” actions; give explicit unavailable/permission states and safe confirmation before write actions. | Open |
| P1 | Member servicing | Member directory supports key actions and request queues, but routine admin tasks span separate views. There is no obvious consolidated member timeline for payments, attendance, messages, requests, and staff notes. | Add a member activity timeline and a visible audit trail, with role-appropriate fields and filters. | Open |
| P1 | Offline payments and receipts | Cash logging, reconciliation, and receipt review exist. Operators still need dependable duplicate prevention, reversal handling, and a clear link from a receipt decision to the resulting ledger entry. | Add idempotency/reference duplicate warnings, explicit void/refund correction paths, and a linked receipt/payment history. | Open |

## Route-by-route findings

| Route | Gap observed in the web implementation | Useful next improvement |
|---|---|---|
| `/app` Home | The dashboard combines headline metrics, checklist and quick actions, but metrics can be absent when a source request fails. | Show per-widget stale/error state and last updated time; make each metric’s reporting window explicit. |
| `/app/analytics` | Revenue and membership charts load from one endpoint without a visible date filter or export. | Add date ranges, prior-period comparisons, drill-downs and CSV export. |
| `/app/assistant` | Conversation UI exists, but operational answers need traceability and safe action boundaries. | Cite data and timestamps, link records, identify estimates, and require confirmation for changes. |
| `/app/members` | Directory actions include invites, approvals, freeze and change requests, and trainer assignment. | Add saved views, bulk-safe operations with previews, and a complete member activity timeline. |
| `/app/members/[memberId]` | A standalone profile can hold personal and membership data. | Make billing, attendance, tasks, notes, communication and request history navigable from one page; make private data visibility clear. |
| `/app/plans` | Plans have create/edit/archive and filters; lifecycle details such as existing subscribers affected by edits need clear explanation. | Preview changes for current subscribers, distinguish future-only edits from migrations, and show who is eligible for each plan. |
| `/app/leads` | Lead create/edit/stage and lost reasons exist, with bookings/follow-ups/history components. | Add ownership, next-action reminders, overdue follow-up queue, duplicate detection and conversion attribution. |
| `/app/referrals` | Program setup, reward fulfillment and filters exist. | Add referral attribution detail, fraud/duplicate review, reward eligibility explanation and delivery history. |
| `/app/tasks` | Task assignment/completion exists. | Add overdue and recurring task views, escalation/reminders, and an activity log for reassignment and edits. |
| `/app/inbox` | Shared conversation queue has assignment and resolution concepts. | Add SLA/age indicators, unread and failed-message states, bulk assignment and links to member profiles. |
| `/app/classes` | Class/session management and booking operations exist. | Surface capacity/waitlist, attendance reconciliation, cancellations/no-shows and member notification status together. |
| `/app/attendance` | Check-in/roster actions support daily operations. | Add correction history, duplicate check-in feedback, offline recovery status and quick member search. |
| `/app/front-desk` | Visitor and locker workflows support desk use. | Add expiring/overdue alerts, handover reconciliation and a single quick-action path for visitor/member check-in. |
| `/app/staff` | Staff, roles, invites, shifts and assignments are available. | Add invite expiry/resend status, schedule conflict warnings, permission preview and change history. |
| `/app/payments` | Payment list and refund action exist. | Add saved filters, settlement/refund status, export, and clear handling for pending/failed/offline transactions. |
| `/app/cash` | Cash/offline collection and reconciliation exist. | Show opening/closing balances, variance explanation, duplicate reference warnings and immutable correction trail. |
| `/app/receipts` | Review queue supports approve, request-info and reject. | Show matching payment/member evidence, queue age, reviewer history and a direct path to resolve mismatches. |
| `/app/payroll` | Runs can be drafted, reviewed, finalized and adjusted. | Add period templates, validation before finalization, payout tracking and clear lock/undo policy after finalization. |
| `/app/invoices` | Invoice list/detail/payment recording and voiding exist. | Add overdue reminders, delivery status, partial payment balance, export and a confirmation path that preserves audit context. |
| `/app/companies` and `/app/companies/[id]` | Company records support office billing workflows. | Add contact history, contract/seat utilization and a joined view of company invoices and payments. |
| `/app/approvals` | Queue supports approve/reject and rejection reason. | Add queue age, applicant completeness, reviewer history and batch triage without hiding individual decisions. |
| `/app/audit` | Search, action groups and pagination exist. | Add export, saved filters, actor/entity drill-down and readable before/after values for changed fields. |
| `/app/billing` | Shows plan status/cap, invoices, Stripe credit history, upgrade, scheduled downgrade, cancellation and resume controls. Workspace reads remain accessible after cancellation. | Configure the portal and webhook secrets, then verify each Stripe action in test mode and reconcile timing/credit results. |
| `/app/account` | Profile editing and MFA controls exist. | Add active session/device management, email/password change verification and data export/account deletion policy. |
| `/app/space` | Desk/room slots and bookings can be created and canceled. | Add occupancy calendar, recurring availability, conflicts, booking history and member notifications. |
| `/app/create-gym` | A legacy second-workspace form remains in the web app. | Route owners through the same verified, required Stripe onboarding path; avoid any alternate path that skips paid activation. |
| `/app/settings` | Settings is a dialog/view rather than a standalone route, and settings are split across several workflows. | Group settings by workspace, billing, security and integrations, with unsaved-change warnings and clear save status. |

## Signup and billing flow follow-up

- Registration now collects email/password, verifies a one-time email code, and offers code resend.
- Verified owners enter a blocking web onboarding dialog for profile, workspace and plan details.
- Checkout uses Stripe-hosted subscription mode; card data is entered on Stripe and is not posted to Acron.
- Billing settings now offer Stripe-backed tier changes, cancellation/resume, and customer credit history. The Stripe Customer Portal still needs to be enabled in the test account; plan and cancellation behavior needs a live test-mode walkthrough.
- Server confirmation checks the persisted session, organization, tier, amount, currency, paid status, customer and subscription before unlocking the workspace. Signed webhook handling provides an asynchronous confirmation path.
- Local SQLite databases created before the onboarding columns need the additive schema upgrade. The current local database has been upgraded; a backup was saved at `/tmp/gym_platform_before_owner_onboarding.sqlite3`.
- Before a full Stripe test run, configure `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_WEBHOOK_SECRET`, and `STRIPE_PUBLISHABLE_KEY`. Use Stripe's test card directly in hosted Checkout or the Stripe card element; Acron does not receive raw card details.
- The Enterprise tier is intentionally not selectable in this self-serve checkout yet; it requires a sales-assisted contract.

## Limitations and next sequence

This report is based on code inspection, not screen-reader testing, live Stripe checkout, or interviews with gym/office/academy operators. Validate P0 billing and database behavior first, then run a role-based walkthrough for owner, manager, front desk and member, and prioritize P1 findings with the actual workflows observed.
