# Feature delivery and evidence ledger

Updated: 2026-10-30. Status is **not completed** until implementation, meaningful tests, integration checks, and commit/push evidence are recorded. An existing partial capability is not completion. Work proceeds in the numbered order requested. Scope and acceptance criteria below are initial definitions; refine against code and real integration requirements before implementation. Do not fabricate provider or hardware verification.

| # | Feature | Status | Minimum completion evidence |
|---|---|---|---|
| 1 | Retail POS and inventory | In progress: inventory foundation | Tenant-scoped product catalog, stock adjustments and low-stock alerts; checkout, payment and stock movements; permissions, audit, migration, UI and tests for concurrency/refunds. |
| 2 | Door and turnstile access | Not started | Concrete supported controller, entitlement enforcement, revocation, failure recovery, tenant isolation, hardware integration tests and operational documentation. |
| 3 | Member self-check-in kiosk | Not started | Member-facing kiosk, secure identification, eligibility, accessible responsive UI and end-to-end tests. |
| 4 | Personal-training appointments | Not started | Trainer availability, conflict-safe booking/cancellation, credits/checkout, staff/member UI and tests. |
| 5 | Workout programming | Not started | Exercise catalog, plans, member logging, progress and personal records, permissions and tests. |
| 6 | Nutrition coaching | Not started | Coach-authored plans and member tracking, privacy controls and tested flows. |
| 7 | Multi-location management | Not started | Parent/branch relationships, role isolation, administrative controls and consolidated reporting with tests. |
| 8 | Cross-location memberships | Not started | Explicit shared entitlements and cross-branch authorization, billing/access rules and tests. |
| 9 | Marketing automation builder | Not started | Editable triggers, conditions and actions; consent, execution history, deduplication and tests. |
| 10 | Custom lead pipelines | Not started | Tenant-defined stages, transitions, migration from existing stages and tests. |
| 11 | Complete migration | Not started | Supported import of plans, payment history, attendance and consent; preview, idempotency, reconciliation and tests; provider token migration documented separately. |
| 12 | Custom report builder | Not started | Authorized fields/filters, saved definitions, exports, tenant isolation and performance tests. |
| 13 | Gift cards and vouchers | Not started | Issuance, redemption, balances, refunds, expiry policy, accounting and concurrency tests. |
| 14 | Branded apps | Not started | Tenant branding, build configuration, publishing/release workflow and tested tenant isolation. |
| 15 | Content and video library | Not started | Secure upload/hosting, permissions, member playback, access entitlements and tests. |
| 16 | Member discovery marketplace | Not started | Public discovery, search, gym listings, booking attribution, moderation and privacy tests. |
| 17 | Website and SEO builder | Not started | Editable public pages, preview/publish, responsive SEO metadata and security tests. |
| 18 | Class spot selection | Not started | Layouts, per-session reservations, conflict-safe allocation, UI and tests. |
| 19 | Martial-arts progression | Not started | Ranks, promotions, curriculum and member/staff history with authorization and tests. |
| 20 | Franchise administration | Not started | HQ permissions, branch administration, royalty configuration, reporting and tests. |
| 21 | Accounting and bank reconciliation | Not started | Double-entry ledger, bank import/matching, financial exports, reconciliation controls and tests; jurisdiction-specific requirements documented. |

## Evidence record template

For each feature append its scope, relevant files and migrations, validation commands and results, known limitations, commit SHA, push result and any live-provider/hardware checks. A failed or skipped check must be recorded explicitly. Production readiness requires configuration and live integration verification where applicable.

## 1. Retail POS and inventory — investigation

- Reviewed the existing expense ledger, payment model, permissions, transaction lifecycle, idempotency service and migration conventions. Initial search found no product or stock model in the inspected backend modules.
- Existing financial flows are tenant-scoped, use idempotency keys and audit records, and commit or roll back with the request session. The new implementation must preserve these properties and must not create a sale without a corresponding valid payment or allow concurrent sales to oversell stock.
- Required work remains: settle sale/payment and refund integration, add migrations and transaction-safe stock movement history, implement authorized API and UI, and run meaningful backend/frontend and migration tests. No POS functionality is complete or tested yet.
- Commit: none. Push: none.

### Inventory foundation, 2026-10-30

- Added product and stock-movement models, an Alembic migration, and an atomic conditional stock adjustment service with audit recording.
- Validation: Ruff passed for the new files; Alembic reports `o3p4q5r6s7t8` as the single head. The focused integration test did not finish and was interrupted; it has not passed.
- Not yet implemented: product/stock API, checkout/payment and refund integration, frontend, low-stock UI, idempotent adjustment endpoints, migration execution, PostgreSQL row-level-security verification and concurrency verification. Do not deploy this partial feature.
- Commit: none. Push: none.

- Follow-up: migration now creates PostgreSQL tenant policies for both retail tables. Policy behavior has not been tested. A second focused pytest attempt timed out after 25 seconds during the test; the cause is not established.

- Added tenant-scoped product listing/creation and idempotent stock adjustment API with input validation and audit records. Focused integration tests: 2 passed when run outside the sandbox (SQLite initialization stalls inside it); Ruff passed. Checkout, payment/refund handling, stock purchase flows, UI, migration execution, and concurrency/RLS verification remain. No commit or push.

- Migration check: the retail migration upgraded an isolated SQLite database stamped at its parent revision successfully. A fresh full SQLite migration failed earlier at `f9c0d1e2f3a4_plan_variants_family_credits.py` because SQLite does not support direct ALTER of foreign-key constraints. The complete migration path remains unverified.

- Fresh SQLite migration chain repaired and verified from an empty database to the current head, including foreign-key checks. Focused migration and retail integration tests: 3 passed outside the sandbox. Checkout, refunds, UI, PostgreSQL RLS and concurrency testing remain unfinished; no commit or push.
