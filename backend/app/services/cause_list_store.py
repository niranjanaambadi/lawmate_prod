from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import DailyCauseList


class CauseListStore:
    def upsert_result(
        self,
        db: Session,
        advocate_id: str,
        listing_date: date,
        total_listings: int,
        result_json: dict[str, Any],
        parse_error: str | None,
    ) -> None:
        stmt = insert(DailyCauseList.__table__).values(
            id=uuid.uuid4(),
            advocate_id=advocate_id,
            date=listing_date,
            total_listings=max(0, int(total_listings)),
            result_json=result_json or {},
            parse_error=parse_error,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[DailyCauseList.__table__.c.advocate_id, DailyCauseList.__table__.c.date],
            set_={
                "total_listings": stmt.excluded.total_listings,
                "result_json": stmt.excluded.result_json,
                "parse_error": stmt.excluded.parse_error,
                "created_at": DailyCauseList.__table__.c.created_at,
            },
        )
        db.execute(stmt)

    def fetch_result(self, db: Session, advocate_id: str, listing_date: date) -> DailyCauseList | None:
        return (
            db.query(DailyCauseList)
            .filter(DailyCauseList.advocate_id == advocate_id, DailyCauseList.date == listing_date)
            .first()
        )

    def purge_older_than(self, db: Session, keep_days: int) -> int:
        keep_days = max(1, int(keep_days))
        cutoff = date.today() - timedelta(days=keep_days)
        deleted = (
            db.query(DailyCauseList)
            .filter(DailyCauseList.date < cutoff)
            .delete(synchronize_session=False)
        )
        return int(deleted or 0)


cause_list_store = CauseListStore()
