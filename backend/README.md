# Gym Platform — Backend

FastAPI backend for the Gym Operations Platform (see `Gym_Platform_Full_Plan.pdf`).
Multi-tenant (one org per gym), Stripe Connect Standard for member payments,
platform SaaS billing, payroll, and member payment-proof review.

## Stack

- **API**: FastAPI + Pydantic v2
- **DB**: PostgreSQL (SQLAlchemy 2 async + Alembic migrations, row-level tenant isolation)
- **Workers**: Celery + Redis (payment reconciliation, receipt review support, payroll, legacy spot audits)
- **Payments**: Stripe (SaaS subscriptions) + Stripe Connect Standard (member → gym)
- **Auth**: JWT (15-min access / 7-day refresh), org-scoped tokens, optional MFA

## Layout

```
app/
├── main.py                 # FastAPI app factory, middleware, router mounting
├── api/
│   ├── deps.py             # DI: current user, org scope, role guards, idempotency
│   └── v1/routes/          # One module per domain (auth, plans, payments, payroll…)
├── core/                   # config, security (JWT/hashing), tenancy, rate_limit, permissions
├── db/                     # engine/session, alembic migrations
├── models/                 # SQLAlchemy models (all org-scoped tables carry organization_id)
├── schemas/                # Pydantic request/response models, per domain
├── services/               # Business logic — routes stay thin
├── workers/                # Celery tasks (reconciliation, receipt pipeline, payroll, audits)
├── integrations/           # stripe, email, push, OCR, HIBP
└── utils/                  # org code generator, idempotency helpers, PDF generation
tests/
├── unit/
└── integration/
```

## Development

Receipt image upload and OCR require ImageMagick (`identify`, `convert`) and
Tesseract on the API host. On Debian/Ubuntu install them with
`sudo apt-get install imagemagick tesseract-ocr`. Receipts remain in staff
review if OCR is unavailable; OCR never confirms that a transfer settled.

```bash
# Install (uses uv; pip install -e . also works)
uv sync

# Run API
uv run uvicorn app.main:app --reload

# Run workers
uv run celery -A app.workers worker -l info

# Migrations
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "message"

# Tests
uv run pytest                       # all
uv run pytest tests/unit/test_x.py::test_name   # single test

# Lint / typecheck
uv run ruff check .
uv run mypy app
```

## Domain map (plan section → module)

| Plan section | Routes | Service | Worker |
|---|---|---|---|
| 3. SaaS subscription | `saas_billing` | `saas_billing_service` | — |
| 4–5. Admin reg/login | `auth`, `organizations` | `auth_service`, `organizations_service` | — |
| 6. Membership plans | `plans` | `plans_service` | — |
| 7–9. Signup/login/status | `members`, `memberships` | `members_service`, `memberships_service` | — |
| 10. AI receipts | `receipts` | `receipts_service` | `receipt_pipeline`, `spot_audit` |
| 11. Cash logging | `cash` | `cash_service` | — |
| 13. Idempotency | (all POST routes) | `utils/idempotency` | `payment_reconciliation` |
| 15. Payroll | `payroll`, `staff` | `payroll_service` | `payroll_runner` |

## Invariants

- Every state-changing endpoint requires an `Idempotency-Key` header.
- Every query on org-scoped tables must filter by the JWT's `organization_id`; RLS is the second defense.
- Members never pay the platform — Stripe Connect routes funds to the gym's account.
