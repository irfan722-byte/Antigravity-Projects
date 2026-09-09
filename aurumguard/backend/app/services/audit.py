"""Append-only, hash-chained audit log. Also mirrors each record as a JSON line on disk."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.models import AuditLog


def _canon(d: dict) -> str:
    return json.dumps(d, sort_keys=True, default=str, separators=(",", ":"))


def record(db: Session, actor: str, action: str, subject: str = "", detail: dict | None = None) -> AuditLog:
    last = db.query(AuditLog).order_by(desc(AuditLog.id)).first()
    prev = last.row_hash if last else ""
    ts = datetime.now(tz=UTC)
    detail = json.loads(_canon(detail or {}))  # store exactly what is hashed (JSON-native types only)
    body = {"ts": ts.isoformat(), "actor": actor, "action": action, "subject": subject, "detail": detail, "prev": prev}
    row_hash = hashlib.sha256(_canon(body).encode()).hexdigest()
    row = AuditLog(ts=ts, actor=actor, action=action, subject=subject, detail=detail, prev_hash=prev, row_hash=row_hash)
    db.add(row)
    db.commit()
    try:
        d = get_settings().audit_dir
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"audit-{ts:%Y-%m}.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(_canon(body | {"row_hash": row_hash}) + "\n")
    except OSError:
        pass
    return row


def verify_chain(db: Session, limit: int | None = None) -> dict:
    rows = db.query(AuditLog).order_by(AuditLog.id).all()
    if limit:
        rows = rows[-limit:]
    prev = rows[0].prev_hash if rows else ""
    bad = []
    for r in rows:
        ts = r.ts if r.ts.tzinfo is not None else r.ts.replace(tzinfo=UTC)
        body = {"ts": ts.isoformat(), "actor": r.actor, "action": r.action, "subject": r.subject, "detail": r.detail, "prev": r.prev_hash}
        if r.prev_hash != prev or hashlib.sha256(_canon(body).encode()).hexdigest() != r.row_hash:
            bad.append(r.id)
        prev = r.row_hash
    return {"rows": len(rows), "ok": not bad, "broken_ids": bad}
