# Sheet2Portal

Upload an Excel workbook or CSV file and get a structural preview: worksheets, headers, inferred column types, row counts, and sample data. This is Stage 1 of a larger platform that will go on to generate full business portals (dashboards, tables, forms, AI-assisted queries) from uploaded spreadsheets.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (dev/prod), openpyxl for parsing.
- **Frontend**: TypeScript, React 19, Vite, TanStack Query, Tailwind CSS v4.
- **AI engine**: provider-agnostic interface (`backend/app/services/ai/base.py`), adapters land in Stage 2.

See `.claude/plans/` (or ask) for the full architecture/milestone/risk writeup this was built from.

## Prerequisites

- Python 3.12 (this repo was set up with [`uv`](https://docs.astral.sh/uv/) managing the interpreter and venv — no system Python changes needed).
- Node.js 20+ (set up here via [nvm](https://github.com/nvm-sh/nvm)).
- Docker (for local Postgres via `docker-compose`).

## First-time setup

```bash
# 1. Database
docker compose up -d          # starts Postgres on localhost:5433
cd backend
cp .env.example .env          # defaults already point at the docker-compose Postgres
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
alembic upgrade head           # creates tables

# 2. Backend
uvicorn app.main:app --reload --port 8000

# 3. Frontend (separate terminal)
cd frontend
cp .env.example .env
npm install
npm run dev                    # http://localhost:5173
```

## Running tests

```bash
cd backend
source .venv/bin/activate
pytest                         # runs against an isolated in-memory SQLite DB, no Postgres needed
```

```bash
cd frontend
npm run build                  # typechecks (tsc -b) and builds
```

## Project layout

```
backend/app/
  core/            config, db session
  models/          SQLAlchemy models: Tenant, Workbook, Worksheet, Column
  schemas/         Pydantic response models
  services/
    parsing/       xlsx/csv parsing + type inference (pure functions, no I/O side effects beyond reading the file)
    storage/       local filesystem storage behind a swappable interface
    ai/            LLMProvider interface (Stage 2+)
  api/routes/      health, workbooks (upload + preview)
backend/alembic/   migrations

frontend/src/
  api/             fetch wrappers for the backend
  components/      UploadDropzone, WorksheetTabs, SampleTable, TypeBadge, ErrorBanner
  types/           shared TS types mirroring the backend schemas
```

## Notes on the current state

- Every DB query is scoped by `tenant_id`. Auth isn't implemented yet (Stage 4) — the active tenant is resolved from an `X-Tenant-Id` header, defaulting to a single seeded tenant, so isolation is already structurally enforced even pre-auth.
- Parsing runs synchronously inside the upload request (fine at MVP scale/local dev; revisit with a job queue if file sizes or traffic grow).
- `MAX_UPLOAD_SIZE_BYTES` / `MAX_ROWS_PER_SHEET` (see `backend/.env.example`) bound memory use and processing time per upload.
