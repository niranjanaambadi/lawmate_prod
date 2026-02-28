"""
Idempotency Service — LawMate
==============================
Prevents duplicate side-effecting operations when the same request is fired
from multiple browser tabs or retried after a network failure.

Usage in an endpoint:
    cached = get_idempotent_response(key, str(current_user.id), db)
    if cached:
        status_code, body = cached
        return JSONResponse(body, status_code=status_code)

    # ... do the real work ...
    result = do_the_work()

    store_idempotent_response(key, str(current_user.id), 200, result, db)
    return result
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

_DEFAULT_TTL_HOURS = 24


def get_idempotent_response(
    key: str,
    user_id: str,
    db: Session,
) -> Optional[tuple[int, dict]]:
    """
    Return (status_code, response_body) if a non-expired record exists for
    this (key, user_id) pair, otherwise None.
    """
    from app.db.models import IdempotencyRecord

    if not key:
        return None

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return None

    row: Optional[IdempotencyRecord] = (
        db.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.idempotency_key == key,
            IdempotencyRecord.user_id == uid,
            IdempotencyRecord.expires_at > datetime.utcnow(),
        )
        .first()
    )

    if row is None:
        return None

    logger.info(
        "idempotency_hit key=%s user=%s endpoint=%s",
        key, user_id, row.endpoint,
    )
    return (row.status_code, row.response_body)


def store_idempotent_response(
    key: str,
    user_id: str,
    status_code: int,
    response_body: dict,
    db: Session,
    endpoint: str = "",
    ttl_hours: int = _DEFAULT_TTL_HOURS,
) -> None:
    """
    Persist the result of a side-effecting operation.
    On duplicate key (race between two tabs), silently ignores the conflict —
    the first writer wins, which is the desired behaviour.
    """
    from app.db.models import IdempotencyRecord

    if not key:
        return

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return

    row = IdempotencyRecord(
        idempotency_key=key,
        user_id=uid,
        endpoint=endpoint,
        status_code=status_code,
        response_body=response_body,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=ttl_hours),
    )
    try:
        db.add(row)
        db.commit()
    except IntegrityError:
        # Another tab/process already stored this key — that's fine.
        db.rollback()
        logger.debug("idempotency_duplicate_ignored key=%s user=%s", key, user_id)


def delete_expired_idempotency_records(db: Session) -> int:
    """Sweep expired rows. Called by a periodic background task."""
    from app.db.models import IdempotencyRecord

    deleted = (
        db.query(IdempotencyRecord)
        .filter(IdempotencyRecord.expires_at < datetime.utcnow())
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
