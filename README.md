# Mayorcity Bizintel — Step 1: Project Foundation

AI-powered Business Intelligence & Simulator platform for SMBs.
This step builds the foundation only: project scaffolding, database
connection, health check, landing page, and basic auth + business
creation. AI assistant, data import, forecasting, and simulation are
**not** built yet — those come in later steps.

## Stack

- **Frontend:** Next.js 14 (App Router) + TypeScript
- **Backend:** FastAPI + SQLAlchemy 2.0 + Alembic
- **Database:** PostgreSQL 16

## Project structure

```
project/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/        # individual route modules
│   │   │   └── router.py      # aggregates all routers
│   │   ├── core/
│   │   │   ├── config.py      # env-driven settings
│   │   │   ├── security.py    # password hashing, JWT
│   │   │   └── exceptions.py  # error handling
│   │   ├── db/
│   │   │   ├── session.py     # engine + get_db dependency
│   │   │   ├── base_class.py  # declarative Base
│   │   │   └── base.py        # imports all models for Alembic
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   └── main.py            # FastAPI app entrypoint
│   ├── alembic/                # migrations
│   ├── alembic.ini
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/                # Next.js App Router pages
│   │   ├── lib/                # API client, utilities
│   │   ├── components/
│   │   └── types/
│   ├── package.json
│   └── .env.example
├── docker-compose.yml           # local PostgreSQL
└── README.md
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (for local Postgres) — or a local Postgres install

## 1. Start PostgreSQL

```bash
docker compose up -d
```

This starts Postgres on `localhost:5432` with:
- user: `bizintel_user`
- password: `bizintel_pass`
- database: `bizintel_db`

(These match `backend/.env.example` — no extra config needed for local dev.)

## 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # edit if your DB creds differ

# Run the initial migration (creates tables once models exist in a later step)
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload
```

Backend runs at **http://localhost:8000**
Interactive API docs: **http://localhost:8000/docs**
Health check: **http://localhost:8000/health**

## 3. Frontend setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Frontend runs at **http://localhost:3000**

## Verifying everything works

1. `curl http://localhost:8000/health` → should return `{"status": "ok", "database": "ok"}`
2. Visit `http://localhost:3000` → should show the placeholder homepage
3. (Once auth + business models land in the next steps) register a user, log in, and create a business

## What's in this step vs. later steps

**Included now:** project scaffolding, DB connection, migrations setup,
health check, minimal homepage, error handling foundation.

**Not yet built (intentionally):** User/Business models & migrations,
auth endpoints & pages, business creation flow, AI assistant, data
import, forecasting, simulator. These land in the next build steps on
top of this foundation without requiring a rewrite.
