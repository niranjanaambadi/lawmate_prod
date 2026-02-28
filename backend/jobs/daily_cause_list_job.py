from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
import re

from app.core.logger import logger
from app.db.database import SessionLocal
from app.services.block_extractor import block_extractor
from app.services.cause_list_store import cause_list_store
from app.services.llm_parser import llm_parser
from app.services.mediation_enrichment_service import mediation_enrichment_service
from app.services.pdf_extractor import pdf_extractor


def _parse_date_arg(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _normalize_case(value: str | None) -> str:
    text = (value or "").upper()
    text = re.sub(r"\s+", "", text)
    return text


async def run_daily_cause_list_job(listing_date: date) -> dict:
    db = SessionLocal()
    try:
        advocates = block_extractor.get_verified_advocates(db)
        extracted = pdf_extractor.extract_text_for_date(db, listing_date)
        blocks = block_extractor.split_blocks(extracted.text)
        matched_by_adv = block_extractor.match_blocks_by_advocate(blocks, advocates)

        results = await llm_parser.parse_per_advocate(
            listing_date=listing_date,
            advocates=advocates,
            matched_blocks=matched_by_adv,
        )

        total_with_listings = 0
        total_with_errors = 0

        for result in results:
            matched_blocks_for_adv = matched_by_adv.get(result.advocate_id, [])
            allowed_cases = {_normalize_case(b.case_number_raw) for b in matched_blocks_for_adv if b.case_number_raw}
            filtered_listings = []
            for item in result.listings:
                if not isinstance(item, dict):
                    continue
                case_raw = _normalize_case(str(item.get("case_number_raw") or ""))
                if allowed_cases and case_raw and case_raw not in allowed_cases:
                    continue
                filtered_listings.append(item)

            result.listings = filtered_listings
            result.total_listings = len(filtered_listings)

            payload = {
                "advocate_id": result.advocate_id,
                "date": result.date,
                "total_listings": result.total_listings,
                "listings": result.listings,
            }

            parse_error = result.parse_error
            if parse_error:
                total_with_errors += 1
                # Store raw_text for malformed JSON / parse-type errors for later reprocessing.
                payload["parse_error"] = parse_error
                if "JSON" in parse_error.upper() and matched_blocks_for_adv:
                    payload["error_raw_text"] = "\n\n".join([b.text for b in matched_blocks_for_adv[:5]])

            if result.total_listings > 0:
                total_with_listings += 1

            cause_list_store.upsert_result(
                db=db,
                advocate_id=result.advocate_id,
                listing_date=listing_date,
                total_listings=result.total_listings,
                result_json=payload,
                parse_error=parse_error,
            )

        db.commit()

        # ── Extract Mediation List case numbers ─────────────────────────────
        # The MEDIATION LIST at the end of the PDF does not contain advocate
        # names inline, so the name-matching above misses those cases entirely.
        # We store the raw case numbers here; a separate enrichment step
        # (POST /cause-list/enrich-mediation) fetches case details from the
        # court portal and discovers which advocates are involved.
        mediation_blocks = block_extractor.extract_mediation_blocks(blocks)
        mediation_stored = mediation_enrichment_service.store_mediation_cases(
            db=db, listing_date=listing_date, mediation_blocks=mediation_blocks
        )
        db.commit()

        if mediation_stored:
            logger.info(
                "Stored %d new mediation list cases for %s (run enrich-mediation to fetch advocate details)",
                mediation_stored,
                listing_date.isoformat(),
            )

        summary = {
            "date": listing_date.isoformat(),
            "total_advocates_processed": len(advocates),
            "total_with_listings": total_with_listings,
            "total_with_errors": total_with_errors,
            "page_count": extracted.page_count,
            "s3_bucket": extracted.s3_bucket,
            "s3_key": extracted.s3_key,
            "mediation_cases_stored": mediation_stored,
            "mediation_blocks_found": len(mediation_blocks),
        }
        logger.info("Daily cause list job completed: %s", summary)
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily cause-list processing job")
    parser.add_argument("--date", dest="listing_date", help="YYYY-MM-DD")
    args = parser.parse_args()

    target_date = _parse_date_arg(args.listing_date)
    summary = asyncio.run(run_daily_cause_list_job(target_date))
    print(summary)


if __name__ == "__main__":
    main()
