from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.db.models import MediationListCase, User
from app.services.bedrock_case_enrichment_service import bedrock_case_enrichment_service
from app.services.block_extractor import CaseBlock
from app.services.court_api_service import RateLimitError, court_api_service

# Same honorific / non-alphanum patterns used by BlockExtractor for consistency.
_HONORIFICS_RE = re.compile(r"\b(SHRI|SMT|SRI|KUM|DR|MR|MS|MRS|ADV)\.?\b", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]+")


class MediationEnrichmentService:
    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _normalize_name(self, value: str) -> str:
        upper = (value or "").upper()
        upper = _HONORIFICS_RE.sub(" ", upper)
        upper = _NON_ALNUM_RE.sub(" ", upper)
        return re.sub(r"\s+", " ", upper).strip()

    def _to_name_list(self, value: Any) -> list[str] | None:
        """
        Coerce a court-portal advocate field (string, list of strings, or
        list of dicts with a "name" key) into a plain list of name strings.
        """
        if value is None:
            return None
        if isinstance(value, str):
            parts = [p.strip() for p in re.split(r"\n|;|,(?=\s*[A-Za-z])", value) if p.strip()]
            return parts or None
        if isinstance(value, list):
            names: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    names.append(item.strip())
                elif isinstance(item, dict):
                    name = (
                        item.get("name")
                        or item.get("advocate_name")
                        or item.get("advocateName")
                        or ""
                    )
                    if name.strip():
                        names.append(name.strip())
            return names or None
        return None

    # ------------------------------------------------------------------ #
    #  Store mediation case numbers extracted from the PDF                #
    # ------------------------------------------------------------------ #

    def store_mediation_cases(
        self,
        db: Session,
        listing_date: Any,
        mediation_blocks: list[CaseBlock],
    ) -> int:
        """
        Upsert one ``MediationListCase`` row per block.  Blocks that already
        exist (same listing_date + case_number_raw) are skipped so re-running
        the job is idempotent.

        Returns the number of *new* rows inserted.
        """
        if not mediation_blocks:
            return 0

        existing_keys: set[str] = {
            row.case_number_raw
            for row in db.query(MediationListCase.case_number_raw).filter(
                MediationListCase.listing_date == listing_date
            )
        }

        inserted = 0
        for block in mediation_blocks:
            if not block.case_number_raw:
                continue
            if block.case_number_raw in existing_keys:
                continue
            db.add(
                MediationListCase(
                    listing_date=listing_date,
                    serial_number=block.serial_number or "",
                    case_number_raw=block.case_number_raw,
                    court_number=block.court_number,
                    raw_text=block.text,
                    fetch_status="pending",
                )
            )
            existing_keys.add(block.case_number_raw)
            inserted += 1

        if inserted:
            db.flush()
        return inserted

    # ------------------------------------------------------------------ #
    #  Enrich pending cases from the court portal                         #
    # ------------------------------------------------------------------ #

    def enrich_pending_cases(
        self,
        db: Session,
        listing_date: Any,
        max_cases: int = 50,
    ) -> dict[str, int]:
        """
        For each ``MediationListCase`` row in *pending* or *failed* state
        (with fewer than 3 prior attempts), fetch the case details from the
        Kerala HC portal, extract Petitioner/Respondent advocate names, and
        persist back to the row.

        This call is synchronous and may be slow (Playwright + CAPTCHA per
        case).  Run it in a background thread or a dedicated endpoint rather
        than inside an async handler.

        Returns a summary dict: ``{pending_found, fetched, failed}``.
        """
        pending: list[MediationListCase] = (
            db.query(MediationListCase)
            .filter(
                MediationListCase.listing_date == listing_date,
                MediationListCase.fetch_status.in_(["pending", "failed"]),
                MediationListCase.fetch_attempts < 3,
            )
            .limit(max_cases)
            .all()
        )

        fetched = 0
        failed = 0

        for case in pending:
            case.fetch_status = "fetching"
            case.fetch_attempts += 1
            db.commit()

            try:
                raw = court_api_service.fetch_case_status(case.case_number_raw)
                if raw is None:
                    case.fetch_status = "failed"
                    case.last_fetch_error = "Case not found on court portal"
                    failed += 1
                    logger.warning(
                        "Mediation enrichment: case not found on portal — %s",
                        case.case_number_raw,
                    )
                else:
                    enriched = bedrock_case_enrichment_service.enrich_case_data(raw)

                    pet_raw = enriched.get("petitioner")
                    resp_raw = enriched.get("respondent")
                    case.petitioner_names = (
                        [pet_raw] if isinstance(pet_raw, str) and pet_raw else pet_raw
                    ) or None
                    case.respondent_names = (
                        [resp_raw] if isinstance(resp_raw, str) and resp_raw else resp_raw
                    ) or None

                    case.petitioner_advocates = self._to_name_list(
                        enriched.get("petitioner_advocates")
                    )
                    case.respondent_advocates = self._to_name_list(
                        enriched.get("respondent_advocates")
                    )

                    case.case_detail_raw = {
                        "status": enriched.get("court_status"),
                        "coram": enriched.get("coram"),
                        "bench": enriched.get("bench"),
                        "next_hearing_date": enriched.get("next_hearing_date"),
                        "petitioner": pet_raw,
                        "respondent": resp_raw,
                    }
                    case.fetch_status = "fetched"
                    case.fetched_at = datetime.utcnow()
                    fetched += 1
                    logger.info(
                        "Mediation enrichment: fetched %s — pet_advs=%s resp_advs=%s",
                        case.case_number_raw,
                        case.petitioner_advocates,
                        case.respondent_advocates,
                    )

            except RateLimitError as exc:
                case.fetch_status = "failed"
                case.last_fetch_error = f"RateLimit: {exc}"
                failed += 1
                logger.warning("Mediation enrichment rate-limited for %s", case.case_number_raw)
                db.commit()
                break  # stop the batch on rate-limit; caller should retry later
            except Exception as exc:
                case.fetch_status = "failed"
                case.last_fetch_error = str(exc)
                failed += 1
                logger.warning(
                    "Mediation enrichment failed for %s: %s",
                    case.case_number_raw,
                    exc,
                )

            db.commit()

        return {
            "pending_found": len(pending),
            "fetched": fetched,
            "failed": failed,
        }

    # ------------------------------------------------------------------ #
    #  Query-time: build synthetic listings for a specific advocate        #
    # ------------------------------------------------------------------ #

    def get_mediation_listings_for_advocate(
        self,
        db: Session,
        listing_date: Any,
        advocate_name: str,
    ) -> list[dict]:
        """
        Return synthetic cause-list listing dicts for mediation cases where
        *advocate_name* appears as a Petitioner Advocate or Respondent
        Advocate (as recorded on the court portal).

        Only cases with ``fetch_status == "fetched"`` are considered.
        Name matching uses the same token-normalisation as BlockExtractor
        so minor spacing/honourific differences are tolerated.
        """
        norm = self._normalize_name(advocate_name)
        if not norm:
            return []

        cases: list[MediationListCase] = (
            db.query(MediationListCase)
            .filter(
                MediationListCase.listing_date == listing_date,
                MediationListCase.fetch_status == "fetched",
            )
            .all()
        )

        listings: list[dict] = []
        for case in cases:
            role: str | None = None

            for adv_name in (case.petitioner_advocates or []):
                if norm in self._normalize_name(str(adv_name)):
                    role = "PETITIONER_ADVOCATE"
                    break

            if role is None:
                for adv_name in (case.respondent_advocates or []):
                    if norm in self._normalize_name(str(adv_name)):
                        role = "RESPONDENT_ADVOCATE"
                        break

            if role is None:
                continue

            detail = case.case_detail_raw or {}
            coram = detail.get("coram")
            listings.append(
                {
                    "serial_number": case.serial_number or "-",
                    "case_number_raw": case.case_number_raw,
                    "court_number": case.court_number or "MEDIATION",
                    "court_code": None,
                    "judges": [coram] if coram else [],
                    "section_type": "MEDIATION_LIST",
                    "section_label": "MEDIATION LIST",
                    "case_type": None,
                    "case_category": "MEDIATION",
                    "petitioner_names": case.petitioner_names or [],
                    "respondent_names": case.respondent_names or [],
                    "all_petitioner_advocates": case.petitioner_advocates or [],
                    "all_respondent_advocates": case.respondent_advocates or [],
                    "advocate_role": role,
                    "status": detail.get("status") or "UNKNOWN",
                    "pending_compliance": [],
                    # Extra mediation-specific context
                    "_mediation": True,
                }
            )

        return listings

    # ------------------------------------------------------------------ #
    #  Convenience: inject mediation listings into an existing result_json #
    # ------------------------------------------------------------------ #

    def inject_into_result(
        self,
        result_json: dict,
        mediation_listings: list[dict],
    ) -> dict:
        """Return a copy of *result_json* with mediation listings appended."""
        if not mediation_listings:
            return result_json
        existing = list(result_json.get("listings") or [])
        return {**result_json, "listings": existing + mediation_listings}

    # ------------------------------------------------------------------ #
    #  Summary of stored mediation cases for a date                       #
    # ------------------------------------------------------------------ #

    def get_status_summary(self, db: Session, listing_date: Any) -> dict:
        rows: list[MediationListCase] = (
            db.query(MediationListCase)
            .filter(MediationListCase.listing_date == listing_date)
            .all()
        )
        by_status: dict[str, int] = {}
        for r in rows:
            by_status[r.fetch_status] = by_status.get(r.fetch_status, 0) + 1
        return {
            "total": len(rows),
            "by_status": by_status,
            "cases": [
                {
                    "case_number_raw": r.case_number_raw,
                    "fetch_status": r.fetch_status,
                    "petitioner_advocates": r.petitioner_advocates,
                    "respondent_advocates": r.respondent_advocates,
                }
                for r in rows
            ],
        }


mediation_enrichment_service = MediationEnrichmentService()
