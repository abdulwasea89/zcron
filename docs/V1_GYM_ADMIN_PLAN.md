# Version 1: Gym Admin Web Plan

This is the working plan for a single-location gym's web application for owners, managers, front-desk staff, and trainers. It tracks the twelve agreed priorities in delivery order. A priority is complete only when its completion criteria have been checked against the current implementation and its relevant checks have passed.

For each priority: inspect the existing workflow, implement the remaining work, review permissions and failure cases, run focused checks, commit and push to `main`, then record the evidence below before moving to the next priority.

| Priority | Feature | Status | Verification | Commit / push | Remaining limitations |
|---:|---|---|---|---|---|
| 1 | Member payments and receipts | In progress | Full backend suite: 611 passed, 2 optional PostgreSQL tests skipped; both PostgreSQL checks passed separately. Offline queue checks passed. GitHub passed the frontend production build, type check, and smoke checks for `5285336`. | `75ba0ee`, `f244301`, and `5285336` pushed; backend CI test fixes pending commit | Automatic recovery of stale idempotency claims and live provider behavior remain unverified. The latest GitHub backend run predates the locally verified test fixes. |
| 2 | Member invoices and receivables | Not started | Not verified | — | To be assessed |
| 3 | Refunds, credits, and disputes | Not started | Not verified | — | To be assessed |
| 4 | Audit log | Not started | Not verified | — | To be assessed |
| 5 | Data requests and exports | Not started | Not verified | — | To be assessed |
| 6 | Gym's software subscription | Not started | Not verified | — | To be assessed |
| 7 | Member import | Not started | Not verified | — | To be assessed |
| 8 | Shared inbox | Not started | Not verified | — | To be assessed |
| 9 | Lead capture and profiles | Not started | Not verified | — | To be assessed |
| 10 | Retention and win-back | Not started | Not verified | — | To be assessed |
| 11 | Analytics and operating reports | Not started | Not verified | — | To be assessed |
| 12 | Waivers and signed health forms | Not started | Not verified | — | To be assessed |

## Completion criteria

1. **Member payments and receipts:** Staff can record supported offline payments, review receipt evidence, see pending payments, and reconcile recorded cash. Online states distinguish pending, successful, failed, and refunded transactions. Retries do not duplicate payments.
2. **Member invoices and receivables:** Admins can create and send supported membership invoices, record full or partial payments, see outstanding balances, and void eligible invoices with a reason. Invoice and payment records stay consistent.
3. **Refunds, credits, and disputes:** Authorized admins can review supported refunds and credits, see their effect on balances, and collect or export available dispute evidence. Duplicate refund attempts are prevented and financial actions are audited.
4. **Audit log:** Important financial changes, sensitive-data access, and exports are recorded with the actor, time, organization, and affected record. Authorized admins can review events without private content appearing in audit metadata.
5. **Data requests and exports:** Admins can record and resolve requests, export supported member data, and track erasure reviews. Exports identify truncated sections; external processors and backup handling remain explicit staff-review steps.
6. **Gym's software subscription:** Verify workspace plans, invoices, payment failures, upgrades, downgrades, cancellation, and resume with Stripe test mode and webhooks. Billing and access states are clear in web settings.
7. **Member import:** Staff can map CSV/XLSX columns, preview validation errors and likely duplicates, choose how to handle matching records, and import confirmed rows. Existing financial and attendance records are preserved.
8. **Shared inbox:** Supported channels can be configured, receive and send messages, assign conversations, and display available delivery outcomes. Staff can see connection and delivery failures.
9. **Lead capture and profiles:** Staff entry, website forms, generic webhooks, and the existing Meta integration create or update the correct lead. Duplicate submissions are handled safely and new leads enter the follow-up workflow.
10. **Retention and win-back:** Staff can move from risk or inactivity signals to an assigned case, record the next action and due date, and close it with an outcome. Version 1 uses the existing rule-based signals.
11. **Analytics and operating reports:** Core membership, revenue, payment, refund, expense, and retention figures are accurate for their stated dates and currencies. Reports explain their data basis and do not mix currencies.
12. **Waivers and signed health forms:** Admins can manage gym-authored forms, record acceptance, and store and review signed evidence collected by staff. Health information and evidence are restricted to authorized roles.

## Progress notes

- Priority 1: Offline payment requests reject card/invoice methods and invalid amounts. Receipt approval locks the receipt and requires staff to enter a settled amount matching the current quote, including tax and joining fees. The cash form queues network failures using the original idempotency key, and the offline queue reports success only after its browser transaction commits.
- Priority 1: Cash reconciliation separates currencies, uses the gym's local business date, includes dated cash refunds, and accounts for the opening float. Existing reconciliation rows retain their original totals; their historical currency remains unspecified.
- Priority 1: The stale-payment worker reports uncertain requests without marking them successful or failed. Verified provider lookup and recovery remain to be implemented.
- Priority 1: Connected-account payment events are checked against the recorded settled amount and currency. Delayed failure and success events cannot overwrite settled or refunded records; signup confirmation locks the payment and rejects refunded records.
- Priority 1: Owners and managers can recheck a recorded pending or failed card payment against the gym's connected Stripe account. Only an amount- and currency-matched success is fulfilled; other outcomes remain visible without guessing.

## Verification and scope

- Extend existing admin pages and APIs; add migrations only when necessary and preserve existing records.
- Test the main workflow and failure cases for each feature, including role permissions, organization isolation, retries, and duplicate requests. Test financial calculations and transitions with provider test events.
- Run relevant backend and frontend checks and review each change for vulnerabilities before committing. Run production-build and integration checks where relevant.
- Verify live billing and messaging only when valid provider configuration is available. Local tests do not establish that production credentials or webhooks work.
- Version 1 supports one gym location and the existing supported providers. Tax amounts and waiver text are configured by the gym; the app does not claim automatic compliance with an unspecified jurisdiction.
- Full accounting P&L, additional payment providers, predictive retention models, and a tamper-evident evidence vault are outside these twelve priorities.
- Live production provider configuration and every deployed role have not yet been checked.
