import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .settings import AUDIT_DB_PATH


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(AUDIT_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(AUDIT_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            user_id TEXT,
            role TEXT,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT,
            latency_ms INTEGER,
            request_id TEXT,
            ip TEXT
        );
        """
    )
    return conn


def log_event(
    *,
    tenant_id: str,
    action: str,
    status: str,
    user_id: str | None = None,
    role: str | None = None,
    detail: dict[str, Any] | str | None = None,
    latency_ms: int | None = None,
    request_id: str | None = None,
    ip: str | None = None,
) -> None:
    payload: str | None
    if isinstance(detail, dict):
        payload = json.dumps(detail, ensure_ascii=True)
    else:
        payload = detail

    conn = _connect()
    conn.execute(
        """
        INSERT INTO audit_logs (
            ts, tenant_id, user_id, role, action, status, detail, latency_ms, request_id, ip
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            tenant_id,
            user_id,
            role,
            action,
            status,
            payload,
            latency_ms,
            request_id,
            ip,
        ),
    )
    conn.commit()
    conn.close()
