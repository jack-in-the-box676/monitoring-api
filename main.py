import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


DB_PATH = os.getenv("DB_PATH", "/data/monitoring.db")
API_KEY = os.getenv("API_KEY", "")

STALE_AFTER = timedelta(hours=24)

app = FastAPI(title="Homelab Monitoring API")


class CheckResult(BaseModel):
    name: str
    status: str
    summary: str
    checked_at: str
    job_url: str | None = None
    details: dict = {}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            job_url TEXT,
            details TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


@app.on_event("startup")
def startup():
    init_db()


def get_check_age(checked_at: str):
    try:
        checked = datetime.fromisoformat(checked_at)

        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age = now - checked

        total_seconds = max(0, int(age.total_seconds()))

        if total_seconds < 60:
            return "just now"

        minutes = total_seconds // 60

        if minutes < 60:
            return f"{minutes} min ago"

        hours = minutes // 60

        if hours < 24:
            return f"{hours} hr ago"

        days = hours // 24

        if days == 1:
            return "1 day ago"

        return f"{days} days ago"

    except (ValueError, TypeError):
        return "unknown"


def get_effective_status(status: str, checked_at: str):
    try:
        checked = datetime.fromisoformat(checked_at)

        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - checked

        if age > STALE_AFTER:
            return "UNKNOWN", True

    except (ValueError, TypeError):
        return "UNKNOWN", True

    return status, False


def get_details_value(row, key, default=None):
    try:
        details = json.loads(row["details"])
        return details.get(key, default)
    except (ValueError, TypeError, json.JSONDecodeError):
        return default


def row_to_check(row, include_details=True):
    status, stale = get_effective_status(
        row["status"],
        row["checked_at"],
    )

    result = {
        "id": row["id"],
        "name": row["name"],
        "status": status,
        "stale": stale,
        "summary": row["summary"],
        "checked_at": row["checked_at"],
        "age_text": get_check_age(row["checked_at"]),
        "job_url": row["job_url"],
        "reboot_required": get_details_value(
            row,
            "reboot_required",
            False,
        ),
    }

    if include_details:
        result["details"] = json.loads(row["details"])

    return result


@app.get("/api/status")
def get_status():
    """
    Compact overview for Homarr.
    """

    conn = get_db()

    rows = conn.execute("""
        SELECT id, name, status, summary, checked_at, job_url, details
        FROM checks
        ORDER BY id
    """).fetchall()

    conn.close()

    result = []

    for row in rows:
        status, stale = get_effective_status(
            row["status"],
            row["checked_at"],
        )

        result.append({
            "id": row["id"],
            "name": row["name"],
            "status": status,
            "stale": stale,
            "summary": row["summary"],
            "checked_at": row["checked_at"],
            "age_text": get_check_age(row["checked_at"]),
            "job_url": row["job_url"],
            "reboot_required": get_details_value(
                row,
                "reboot_required",
                False,
            ),
            "details": json.loads(row["details"]),
        })

    return result


@app.get("/api/status/{check_id}")
def get_check(check_id: str):
    """
    Full details for one check.
    """

    conn = get_db()

    row = conn.execute("""
        SELECT id, name, status, summary, checked_at, job_url, details
        FROM checks
        WHERE id = ?
    """, (check_id,)).fetchone()

    conn.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Check not found",
        )

    return row_to_check(row, include_details=True)


@app.post("/api/status/{check_id}")
def update_check(
    check_id: str,
    result: CheckResult,
    x_api_key: str | None = Header(default=None),
):
    """
    Update a monitoring check.
    Only authenticated Windmill requests may write.
    """

    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    conn = get_db()

    conn.execute("""
        INSERT INTO checks (
            id,
            name,
            status,
            summary,
            checked_at,
            job_url,
            details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            status = excluded.status,
            summary = excluded.summary,
            checked_at = excluded.checked_at,
            job_url = excluded.job_url,
            details = excluded.details
    """, (
        check_id,
        result.name,
        result.status,
        result.summary,
        result.checked_at,
        result.job_url,
        json.dumps(result.details),
    ))

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "id": check_id,
    }