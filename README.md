## PFAM Backend (FastAPI)

This is the FastAPI backend for **PFAM — Profit-First Ad Manager**.

### Tech Stack

- FastAPI (Python 3.12)
- Async SQLAlchemy 2.0 + Alembic
- Postgres (Neon)
- Celery + Redis (Upstash) — scaffolded, wired in later phases

### Getting Started

1. **Create and activate a virtualenv** (recommended):

```bash
python -m venv .venv
.venv\Scripts\activate  # on Windows
```

2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

3. **Create a `.env` file** and set at minimum:

- `DATABASE_URL` — Neon Postgres URL (async-compatible, e.g. `postgresql+asyncpg://...`)

4. **Run database migrations** (once they exist for later phases):

```bash
alembic upgrade head
```

5. **Run the API locally**:

```bash
uvicorn app.main:app --reload
```

### Health Check

The endpoint `GET /health` returns a simple JSON payload and 200 status when the app is up (and attempts a lightweight DB check when `DATABASE_URL` is configured).

### Phase 1 Environment & Manual Steps

- **Backend env vars (Phase 1)**
  - `DATABASE_URL` — Neon Postgres connection string using the `postgresql+asyncpg://` scheme.
  - `CLERK_JWT_ISSUER_URL` — your Clerk issuer URL (e.g. `https://<your-domain>.clerk.accounts.dev`) for JWT validation (used in later Phase 1 auth step).
  - `CLERK_JWKS_URL` — JWKS URL from Clerk (usually `<issuer>/.well-known/jwks.json`).
  - `REDIS_URL` — Upstash Redis URL (used in later phases for Celery; safe to add now).

- **Manual infra steps for Phase 1**
  - Create a **Neon Postgres** project and copy the `DATABASE_URL` into your local `.env` and Railway.
  - Create a **Clerk application** and copy the JWT issuer + JWKS URLs into `.env` for later auth integration.
  - Create an **Upstash Redis** instance and copy the `REDIS_URL` (needed once we wire Celery in later phases).
  - Create GitHub repos `pfam-frontend` and `pfam-backend`, push this backend there, and connect:
    - **Vercel** → `pfam-frontend`
    - **Railway** → `pfam-backend` (set the same env vars there as your local `.env`).

