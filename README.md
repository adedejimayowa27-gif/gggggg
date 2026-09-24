# Mayorcity Bizintel

AI-powered business intelligence and decision simulator for small and growing
businesses. Import sales from spreadsheets, see clear analytics, test
"what if" decisions before making them, and get alerted when the numbers
change.

## What it does

- **Data import** -- upload `.csv` / `.xlsx` files (5 MB, 5,000 rows max), or
  connect Google Sheets or Excel on OneDrive (read-only) for automatic
  re-syncs every 6 hours. Column names are matched automatically, rows are
  validated with a preview and error report, and duplicate transactions are
  never double-counted.
- **Manual entry** -- add a sale by hand, correct a wrong row, or delete
  one (deleting needs the Admin role). Changes to rows that came from an
  import or sync are remembered, so the next sync never brings the old row
  back or duplicates it.
- **Analytics** -- revenue, cost and profit summaries and time series, product
  rankings, breakdowns by category / customer / payment method / branch,
  new vs. returning customers, seasonality, and 80/20 (Pareto) analysis.
- **Simulator** -- test changes to selling price, cost price, demand or sales
  volume for the whole business, a category or a product. Compares current vs.
  projected results side by side; real data is never modified. Scenarios can
  be saved.
- **Alerts** -- daily automatic detection of unusual sales, revenue/profit
  changes, falling margins, fast-growing and slow-moving products, cost
  changes, unusual transactions and forecast revenue decline. Urgent alerts
  are emailed to the team.
- **AI assistant** -- ask questions in plain English; answers are computed by
  server-side tools scoped to your business (the model never supplies its own
  numbers or a business id). Chat history is saved.
- **Teams and branches** -- multiple businesses per account, branches, and
  team invites by email with Owner / Admin / Member / Viewer roles.
- **Billing plans** -- plan and usage-limit model with a Stripe checkout flow.
  Payments are **not live yet**: every business is on the free plan and the
  checkout route returns a clean `503 billing_not_configured`.
- **Installable app (PWA)** -- can be installed on a phone or computer.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, Recharts |
| Backend | FastAPI, SQLAlchemy 2.0, Alembic, APScheduler |
| Database | PostgreSQL 16 |
| AI | Groq-hosted model via the OpenAI-compatible SDK |
| Optional services | Resend (email), Stripe (billing), Google / Microsoft OAuth, Sentry |

## Project structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/routes/     # one module per feature (auth, imports, analytics, ...)
│   │   ├── api/deps.py     # auth + business/role authorization dependencies
│   │   ├── core/           # config, security, middleware, rate limiting, logging
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── services/       # business logic (import pipeline, alert engine,
│   │   │                   #   scenario engine, AI assistant, sync jobs, ...)
│   │   └── main.py         # FastAPI entrypoint
│   ├── alembic/versions/   # database migrations
│   ├── scripts/            # backup_db.sh / restore_db.sh
│   └── tests/              # pytest suite (runs against real Postgres)
├── frontend/
│   ├── src/app/            # pages: landing, auth, and /dashboard/*
│   ├── src/components/     # UI components
│   ├── src/lib/            # typed API client modules
│   └── public/             # icons and service worker
├── docs/
│   ├── API.md              # API conventions: auth, errors, rate limits, tenancy
│   └── BACKUP_RECOVERY.md  # backups, recovery runbook, data retention
└── docker-compose.yml      # local PostgreSQL
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (for local Postgres), or a local Postgres 16 install

## Getting started

### 1. Start PostgreSQL

```bash
docker compose up -d
```

Postgres runs on `localhost:5432` (user `bizintel_user`, password
`bizintel_pass`, database `bizintel_db`). These match `backend/.env.example`.
They are for local development only.

### 2. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # then set SECRET_KEY (see below)
alembic upgrade head              # creates all tables
uvicorn app.main:app --reload
```

Generate a proper `SECRET_KEY` for your `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

The backend runs at http://localhost:8000:

- Interactive API docs: http://localhost:8000/docs (Swagger) and `/redoc`
- Health check: http://localhost:8000/health

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

The frontend runs at http://localhost:3000. Sign up, create a business, and
import a transactions file from the dashboard.

## Configuration

Every setting is documented, with comments, in `backend/.env.example`. Only
`DATABASE_URL` and `SECRET_KEY` are required. Everything else is optional and
the related feature degrades cleanly when unset:

| Feature | Settings | If unset |
|---|---|---|
| AI assistant | `GROQ_API_KEY`, `GROQ_MODEL` | assistant route returns 503 |
| Email | `RESEND_API_KEY`, `EMAIL_FROM_ADDRESS` | emails are logged, not sent |
| Google Sheets | `GOOGLE_*` | connect route returns 503 |
| Excel / OneDrive | `MICROSOFT_*` | connect route returns 503 |
| Billing | `STRIPE_*` | everyone stays on the free plan |
| Error monitoring | `SENTRY_DSN` | disabled |

Frontend settings are in `frontend/.env.example`.

## Running the tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Tests run against a real Postgres database (the models use Postgres-specific
JSONB/UUID types), in a separate `_test`-suffixed database that is created
automatically on first run, so your dev data is never touched. See
`backend/tests/conftest.py` for details, including `TEST_DATABASE_URL`.

## Security overview

- Passwords hashed with bcrypt. Two-token sessions: a short-lived (15 min)
  JWT access token plus a long-lived, revocable, hashed-at-rest refresh
  token that rotates on every use, with reuse detection (a stolen/replayed
  refresh token revokes the whole session). Logout and a password reset
  both revoke sessions server-side. Short-lived, purpose-bound
  password-reset and email-verification tokens; no account enumeration on
  reset or resend.
- Email verification: every new signup gets a confirmation link (valid ~24h),
  with a resend option and a dashboard banner until confirmed. Informational
  only -- an unverified account can use the app fully.
- Rate limiting on sign-up, login and password reset, plus a default limit on
  all other routes.
- Every business-scoped endpoint authorizes the caller against the business on
  every request; unauthorized access returns `404`, not `403`.
- Role-based access on every business route: Viewers are read-only, Members do
  day-to-day work, Admins manage integrations and the team (see the table in
  [docs/API.md](docs/API.md)). A test fails if a route is added without a
  declared role or a write route is left open to Viewers.
- Google / Microsoft connections are read-only and their tokens are encrypted
  at rest.
- Audit log of sign-ins, team changes, integrations and billing actions.
- Security headers on API responses (`app/core/security_headers.py`) and on
  frontend pages, including a Content-Security-Policy (`frontend/next.config.mjs`).
- Request-size and upload limits, with row-level validation before any data
  is saved.

See [docs/API.md](docs/API.md) for the full conventions.

## Deploying

- **Never commit `backend/.env`** (it is git-ignored). Keep real secrets in
  your host's environment settings.
- Production checklist: `ENVIRONMENT=production`, `DEBUG=false`, a strong
  `SECRET_KEY`, `CORS_ORIGINS` and `FRONTEND_URL` set to your real frontend
  origin, `LOG_FORMAT=json`, and `NEXT_PUBLIC_API_URL` set to your API origin
  when building the frontend.
- Use a managed Postgres with automatic backups, and run
  `alembic upgrade head` on every deploy. See
  [docs/BACKUP_RECOVERY.md](docs/BACKUP_RECOVERY.md).
- On the first frontend deploy, set `CSP_REPORT_ONLY=true`, check the browser
  console for policy violations on each page, then remove it to enforce.
- Rate limiting and the background scheduler are in-process, which is correct
  for a single backend instance. Move rate limiting to a shared store (Redis)
  before running multiple instances.

## Known limitations

- No account or business deletion endpoint yet (see the retention notes in
  `docs/BACKUP_RECOVERY.md`).
- No inventory tracking, so the stock-shortage alert never fires.
- Payments are not live (see Billing plans above).
