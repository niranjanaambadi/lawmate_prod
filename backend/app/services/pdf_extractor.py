from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date

import boto3
import pdfplumber
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import CauseListIngestionRun, CauseListSource


@dataclass
class ExtractedPdfText:
    text: str
    page_count: int
    s3_bucket: str
    s3_key: str


class PdfExtractor:
    def __init__(self) -> None:
        self.s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    def _get_pdf_bytes(self, bucket: str, key: str) -> bytes:
        obj = self.s3.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()

    def _find_ingestion_run(self, db: Session, listing_date: date) -> CauseListIngestionRun | None:
        return (
            db.query(CauseListIngestionRun)
            .filter(
                CauseListIngestionRun.source == CauseListSource.daily,
                CauseListIngestionRun.listing_date == listing_date,
            )
            .order_by(CauseListIngestionRun.fetched_at.desc())
            .first()
        )

    def extract_text_for_date(self, db: Session, listing_date: date) -> ExtractedPdfText:
        run = self._find_ingestion_run(db, listing_date)
        if not run:
            raise FileNotFoundError(f"No S3 cause-list PDF found for date={listing_date.isoformat()}")

        pdf_bytes = self._get_pdf_bytes(run.s3_bucket, run.s3_key)
        parts: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                parts.append(f"[PAGE {i}]\n{page_text}\n")
            page_count = len(pdf.pages)

        return ExtractedPdfText(
            text="\n".join(parts),
            page_count=page_count,
            s3_bucket=run.s3_bucket,
            s3_key=run.s3_key,
        )


pdf_extractor = PdfExtractor()
