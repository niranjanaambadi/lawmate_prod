from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List
import re

from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from app.core.logger import logger
from app.db.models import Case, CaseStatus, TrackedCase, User
from app.services.bedrock_case_enrichment_service import bedrock_case_enrichment_service
from app.services.court_api_service import RateLimitError, court_api_service


class CaseSyncService:
    def _build_full_details_url(self, raw: Dict[str, Any]) -> str | None:
        payload = raw.get("payload") if isinstance(raw, dict) else None
        if not isinstance(payload, dict):
            return None
        cino = str(payload.get("cino") or "").strip()
        if not cino:
            return None
        return f"https://hckinfo.keralacourts.in/digicourt/Casedetailssearch/Viewcasestatusnewtab/{cino}"

    def _best_effort_status_from_raw(self, raw: Dict[str, Any]) -> str:
        payload = raw.get("payload") if isinstance(raw, dict) else None
        text = str(payload or "")
        if "PENDING" in text.upper():
            return "Pending"
        if "DISPOS" in text.upper() or "DISMISS" in text.upper() or "CLOSED" in text.upper():
            return "Disposed"
        return "Status unavailable"

    def _normalize_header(self, header: str) -> str:
        key = re.sub(r"\s+", " ", (header or "").strip().lower())
        key = key.replace("hon:", "hon ").replace("(tentative date)", "tentative date")
        return key

    def _extract_hearing_history_from_raw(self, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        payload = raw.get("payload") if isinstance(raw, dict) else None
        if not isinstance(payload, dict):
            return []

        html_candidates = [payload.get("proceedings_html")]
        history_rows: List[Dict[str, Any]] = []

        for html in html_candidates:
            if not isinstance(html, str) or "<table" not in html.lower():
                continue
            soup = BeautifulSoup(html, "html.parser")
            for table in soup.find_all("table"):
                header_row = None
                for tr in table.find_all("tr"):
                    cells = tr.find_all(["th", "td"])
                    if len(cells) < 4:
                        continue
                    probe = " ".join(self._normalize_header(c.get_text(" ", strip=True)) for c in cells)
                    if "cause list type" in probe and ("business date" in probe or "next date" in probe):
                        header_row = tr
                        break
                if header_row is None:
                    continue
                headers = [self._normalize_header(th.get_text(" ", strip=True)) for th in header_row.find_all(["th", "td"])]
                if not headers:
                    continue

                history_like = any("cause list type" in h for h in headers) and any(
                    "business date" in h or "next date" in h or "purpose" in h for h in headers
                )
                if not history_like:
                    continue

                rows: List[Any] = []
                tbody = table.find("tbody")
                if tbody:
                    rows = tbody.find_all("tr")
                if not rows:
                    all_rows = table.find_all("tr")
                    header_index = all_rows.index(header_row)
                    rows = all_rows[header_index + 1 :]
                for tr in rows:
                    cols = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                    if not cols:
                        continue
                    row_map: Dict[str, str] = {}
                    for idx, header in enumerate(headers):
                        row_map[header] = cols[idx] if idx < len(cols) else ""

                    history_rows.append(
                        {
                            "sl_no": row_map.get("#") or row_map.get("sl no") or row_map.get("serial no") or "",
                            "cause_list_type": row_map.get("cause list type") or row_map.get("list") or "",
                            "judge_name": row_map.get("hon judge name") or row_map.get("judge name") or row_map.get("bench") or "",
                            "business_date": row_map.get("business date") or "",
                            "next_date": row_map.get("next date tentative date") or row_map.get("next date") or row_map.get("tentative date") or "",
                            "purpose_of_hearing": row_map.get("purpose of hearing") or row_map.get("purpose") or "",
                            "order": row_map.get("order") or row_map.get("orders") or "",
                        }
                    )

                if history_rows:
                    return history_rows
        return history_rows

    def _json_safe(self, value: Any) -> Any:
        """Recursively convert datetime objects to ISO strings for JSON storage."""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(k): self._json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._json_safe(v) for v in value]
        return value

    def sync_cases_list(self, db: Session, user: User, cases: "List[Case]") -> Dict[str, Any]:
        """
        Sync a caller-supplied list of Case objects.
        Used by the Lambda worker endpoint so it can pass an explicit batch
        rather than re-querying all pending cases for the user.
        """
        results: List[Dict[str, Any]] = []
        updated = 0
        failed = 0

        for case in cases:
            case_no = (case.case_number or "").strip()
            now = datetime.utcnow()
            try:
                result = self.query_case_status(case_no)

                if not result.get("found"):
                    case.last_synced_at = now
                    case.sync_error = "Case not found on court portal"
                    db.commit()
                    failed += 1
                    results.append({"case_number": case_no, "success": False, "error": "Case not found"})
                    continue

                case.court_status = result.get("status_text") or case.court_status
                case.bench_type = result.get("stage") or case.bench_type
                case.judge_name = result.get("coram") or case.judge_name
                if result.get("next_hearing_date"):
                    case.next_hearing_date = result["next_hearing_date"]
                case.khc_source_url = (
                    result.get("full_details_url") or result.get("source_url") or case.khc_source_url
                )
                case.last_synced_at = now
                case.sync_status = "synced"
                case.sync_error = None
                if result.get("petitioner_name"):
                    case.petitioner_name = result["petitioner_name"]
                if result.get("respondent_name"):
                    case.respondent_name = result["respondent_name"]
                status_text = (result.get("status_text") or "").lower()
                if "dispos" in status_text or "dismiss" in status_text or "closed" in status_text:
                    case.status = CaseStatus.disposed
                case.raw_court_data = self._json_safe(result)
                db.commit()
                updated += 1
                results.append({"case_number": case_no, "success": True})
            except RateLimitError as exc:
                case.last_synced_at = now
                case.sync_error = str(exc)
                db.commit()
                failed += 1
                results.append({"case_number": case_no, "success": False, "error": str(exc)})
            except Exception as exc:
                case.last_synced_at = now
                case.sync_error = str(exc)
                db.commit()
                failed += 1
                results.append({"case_number": case_no, "success": False, "error": str(exc)})

        summary: Dict[str, Any] = {
            "total": len(cases),
            "updated": updated,
            "failed": failed,
            "results": results,
        }
        logger.info("Case batch sync summary", extra={"user_id": str(user.id), **summary})
        return summary


    def query_case_status(self, case_number: str) -> Dict[str, Any]:
        raw = court_api_service.fetch_case_status(case_number)
        if raw is None:
            return {
                "found": False,
                "case_number": case_number,
                "case_type": None,
                "filing_number": None,
                "filing_date": None,
                "registration_number": None,
                "registration_date": None,
                "cnr_number": None,
                "efile_number": None,
                "first_hearing_date": None,
                "status_text": None,
                "coram": None,
                "stage": None,
                "last_order_date": None,
                "next_hearing_date": None,
                "last_listed_date": None,
                "last_listed_bench": None,
                "last_listed_list": None,
                "last_listed_item": None,
                "petitioner_name": None,
                "petitioner_advocates": None,
                "respondent_name": None,
                "respondent_advocates": None,
                "served_on": None,
                "acts": None,
                "sections": None,
                "hearing_history": None,
                "interim_orders": None,
                "category_details": None,
                "objections": None,
                "summary": None,
                "source_url": None,
                "full_details_url": None,
                "fetched_at": datetime.utcnow(),
                "message": "Case not found",
            }
        enriched = bedrock_case_enrichment_service.enrich_case_data(raw)
        parsed_history = self._extract_hearing_history_from_raw(raw)
        hearing_history = parsed_history or enriched.get("hearing_history")

        return {
            "found": True,
            "case_number": case_number,
            "case_type": enriched.get("case_type"),
            "filing_number": enriched.get("filing_number"),
            "filing_date": enriched.get("filing_date"),
            "registration_number": enriched.get("registration_number"),
            "registration_date": enriched.get("registration_date"),
            "cnr_number": enriched.get("cnr_number"),
            "efile_number": enriched.get("efile_number"),
            "first_hearing_date": enriched.get("first_hearing_date"),
            "status_text": enriched.get("court_status"),
            "coram": enriched.get("coram"),
            "stage": enriched.get("bench"),
            "last_order_date": enriched.get("last_hearing_date"),
            "next_hearing_date": enriched.get("next_hearing_date"),
            "last_listed_date": enriched.get("last_listed_date"),
            "last_listed_bench": enriched.get("last_listed_bench"),
            "last_listed_list": enriched.get("last_listed_list"),
            "last_listed_item": enriched.get("last_listed_item"),
            "petitioner_name": enriched.get("petitioner"),
            "petitioner_advocates": enriched.get("petitioner_advocates"),
            "respondent_name": enriched.get("respondent"),
            "respondent_advocates": enriched.get("respondent_advocates"),
            "served_on": enriched.get("served_on"),
            "acts": enriched.get("acts"),
            "sections": enriched.get("sections"),
            "hearing_history": hearing_history or None,
            "interim_orders": enriched.get("interim_orders"),
            "category_details": enriched.get("category_details"),
            "objections": enriched.get("objections"),
            "summary": enriched.get("raw_summary"),
            "source_url": str(raw.get("source") or ""),
            "full_details_url": self._build_full_details_url(raw),
            "fetched_at": datetime.utcnow(),
            "message": "Case status fetched",
        }

    def add_case_to_dashboard(
        self,
        db: Session,
        user: User,
        case_number: str,
        petitioner_name: str | None = None,
        respondent_name: str | None = None,
        status_text: str | None = None,
        stage: str | None = None,
        last_order_date: datetime | None = None,
        next_hearing_date: datetime | None = None,
        source_url: str | None = None,
        full_details_url: str | None = None,
    ) -> Dict[str, Any]:
        normalized = "".join((case_number or "").upper().split())
        if not normalized:
            raise ValueError("Case number is required")

        existing = (
            db.query(TrackedCase)
            .filter(TrackedCase.user_id == user.id, TrackedCase.is_visible == True, TrackedCase.case_number.isnot(None))
            .all()
        )
        for row in existing:
            if "".join((row.case_number or "").upper().split()) == normalized:
                return {"success": True, "created": False, "case_id": str(row.id), "message": "Case already in tracked cases"}

        now = datetime.utcnow()
        year = now.year
        try:
            year = int((case_number or "").strip().split("/")[-1])
        except Exception:
            year = now.year

        new_case = TrackedCase(
            user_id=user.id,
            case_number=(case_number or "").strip(),
            case_type=((case_number or "").split("/")[0] or "UNKNOWN").strip()[:50] or "UNKNOWN",
            case_year=year,
            petitioner_name=(petitioner_name or "").strip() or None,
            respondent_name=(respondent_name or "").strip() or None,
            status_text=(status_text or "").strip() or None,
            stage=(stage or "").strip() or None,
            last_order_date=last_order_date,
            next_hearing_date=next_hearing_date,
            source_url=(source_url or "").strip() or None,
            full_details_url=(full_details_url or "").strip() or None,
            fetched_at=now,
        )
        db.add(new_case)
        db.commit()
        db.refresh(new_case)
        return {"success": True, "created": True, "case_id": str(new_case.id), "message": "Case added to tracked cases"}


case_sync_service = CaseSyncService()
