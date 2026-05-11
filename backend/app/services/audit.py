from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _canonical(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), default=str)


def _latest_hash(db: Session) -> str:
    latest = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    return latest.signed_hash if latest else "GENESIS"


def write_audit_log(
    db: Session,
    *,
    actor: str,
    action: str,
    target: str,
    before: Any = None,
    after: Any = None,
) -> AuditLog:
    before_json = _jsonable(before)
    after_json = _jsonable(after)
    previous_hash = _latest_hash(db)
    digest = hashlib.sha256(
        "|".join(
            [
                previous_hash,
                actor,
                action,
                target,
                _canonical(before_json),
                _canonical(after_json),
            ]
        ).encode("utf-8")
    ).hexdigest()
    row = AuditLog(
        actor=actor,
        action=action,
        target=target,
        before_json=before_json,
        after_json=after_json,
        signed_hash=digest,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_audit_logs(
    db: Session,
    *,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    if from_ts is not None:
        stmt = stmt.where(AuditLog.created_at >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(AuditLog.created_at <= to_ts)
    return list(db.scalars(stmt).all())
