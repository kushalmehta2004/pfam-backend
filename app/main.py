from fastapi import FastAPI

from app.db import check_database_health


app = FastAPI(title="PFAM Backend", version="0.1.0")


@app.get("/health")
async def health_check() -> dict:
    """
    Lightweight health check.

    - Always returns {"status": "ok"} when the app is running.
    - If DATABASE_URL is configured, also attempts a trivial DB query.
    """
    db_ok = await check_database_health()
    return {"status": "ok", "database": "ok" if db_ok else "unavailable"}


@app.get("/")
async def root() -> dict:
    return {"message": "PFAM backend is running"}
    