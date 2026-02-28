from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import unquote, urljoin, urlparse

import boto3
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.db.models import CauseListIngestionRun, CauseListSource

DATE_RE = re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})")
LATEST_DAILY_BTN_RE = re.compile(r"VIEW\s+LATEST\s+ENTIRE\s+LIST\s*\(DAILY\)", re.IGNORECASE)


@dataclass
class PdfTarget:
    pdf_url: str
    listing_date: date
    source: CauseListSource


@dataclass
class SyncStats:
    source: str
    fetched: int = 0
    runs: int = 0
    failed_runs: int = 0
    listing_dates: set[str] | None = None

    def __post_init__(self) -> None:
        if self.listing_dates is None:
            self.listing_dates = set()


class DailyPdfFetchService:
    def __init__(self) -> None:
        self.source_url = settings.CAUSELIST_DAILY_URL
        self.s3_bucket = settings.CAUSELIST_S3_BUCKET_NAME
        self.s3_prefix = settings.CAUSELIST_S3_PREFIX.strip("/")
        self.s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    def _fetch_html(self, url: str) -> str:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            res = client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    )
                },
            )
            res.raise_for_status()
            return res.text

    def _parse_date(self, text: str | None, fallback: date | None = None) -> date:
        if text:
            m = DATE_RE.search(text)
            if m:
                day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if year < 100:
                    year += 2000
                try:
                    return date(year, month, day)
                except ValueError:
                    pass
        return fallback or date.today()

    def _discover_recent_dates(self, html: str) -> list[date]:
        soup = BeautifulSoup(html, "html.parser")
        dates: list[date] = []
        for node in soup.find_all(["a", "button", "span", "option", "input"]):
            chunks = [
                node.get_text(" ", strip=True),
                str(node.attrs.get("data-date", "")),
                str(node.attrs.get("value", "")),
                str(node.attrs.get("onclick", "")),
            ]
            m = DATE_RE.search(" ".join(chunks))
            if not m:
                continue
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if year < 100:
                year += 2000
            try:
                dates.append(date(year, month, day))
            except ValueError:
                continue

        if not dates:
            today = date.today()
            dates = [today, today - timedelta(days=1), today + timedelta(days=1)]

        dedup: list[date] = []
        for d in dates:
            if d not in dedup:
                dedup.append(d)
        return dedup[:3]

    def _fetch_dynamic_daily_htmls(self, source_url: str, base_html: str, max_dates: int = 3) -> list[tuple[date, str]]:
        parsed = urlparse(source_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        endpoint = urljoin(origin, "/digicourt/index.php/Casedetailssearch/clistbyDate")
        candidate_dates = self._discover_recent_dates(base_html)[:max_dates]
        outputs: list[tuple[date, str]] = []

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            client.get(
                source_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    )
                },
            )
            for listing_date in candidate_dates:
                rendered = ""
                for key in ["clist_date", "cdate", "date", "listing_date"]:
                    try:
                        res = client.post(
                            endpoint,
                            data={key: listing_date.strftime("%Y-%m-%d")},
                            headers={
                                "User-Agent": (
                                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                                ),
                                "Origin": origin,
                                "Referer": source_url,
                                "X-Requested-With": "XMLHttpRequest",
                                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            },
                        )
                        if not res.is_success:
                            continue
                        body = res.text or ""
                        try:
                            payload = json.loads(body)
                            if isinstance(payload, dict):
                                body = str(payload.get("p_table") or payload.get("html") or body)
                        except Exception:
                            pass
                        if len(body) > len(rendered):
                            rendered = body
                        if ".pdf" in body.lower() or "viewentirelist" in body.lower() or "cause" in body.lower():
                            break
                    except Exception:
                        continue
                if rendered:
                    outputs.append((listing_date, rendered))
        return outputs

    def _extract_latest_daily_pdf_target(self, page_url: str, html: str, fallback_date: date) -> PdfTarget | None:
        soup = BeautifulSoup(html or "", "html.parser")
        for a in soup.find_all("a", href=True):
            label = a.get_text(" ", strip=True)
            if not LATEST_DAILY_BTN_RE.search(label or ""):
                continue
            href = a.get("href", "").strip()
            if ".pdf" not in href.lower() and "viewentirelist" not in href.lower():
                continue
            abs_url = urljoin(page_url, href)
            listing_date = self._parse_date(label, fallback=fallback_date)
            return PdfTarget(pdf_url=abs_url, listing_date=listing_date, source=CauseListSource.daily)
        return None

    def _build_pdf_s3_key(self, listing_date: date, pdf_url: str) -> str:
        host = (urlparse(pdf_url).hostname or "unknown").replace(".", "_")
        file_name = unquote(urlparse(pdf_url).path.split("/")[-1] or "causelist.pdf")
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file_name)[:120] or "causelist.pdf"
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return (
            f"{self.s3_prefix}/raw-pdf/source=daily/listing_date={listing_date.isoformat()}/"
            f"fetched_at={ts}/host={host}/{safe_name}"
        ).strip("/")

    def _save_pdf_to_s3(self, key: str, payload: bytes) -> None:
        self.s3.put_object(
            Bucket=self.s3_bucket,
            Key=key,
            Body=payload,
            ContentType="application/pdf",
            ServerSideEncryption="AES256",
        )

    def _download_pdf(self, url: str) -> bytes:
        with httpx.Client(timeout=90.0, follow_redirects=True) as client:
            res = client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    )
                },
            )
            res.raise_for_status()
            return res.content

    def fetch_daily_pdfs_to_s3(self, db: Session, max_tabs: int = 3) -> SyncStats:
        source_url = (self.source_url or "").strip()
        if not source_url:
            raise ValueError("Cause list URL not configured for source=daily")

        stats = SyncStats(source="daily")
        base_html = self._fetch_html(source_url)
        pdf_targets: list[PdfTarget] = []

        try:
            dynamic_daily = self._fetch_dynamic_daily_htmls(source_url, base_html, max_dates=max_tabs)
            for listing_date, rendered_html in dynamic_daily:
                target = self._extract_latest_daily_pdf_target(source_url, rendered_html, fallback_date=listing_date)
                if target:
                    pdf_targets.append(target)
                else:
                    logger.warning("Latest daily PDF button not found", extra={"listing_date": listing_date.isoformat()})
        except Exception:
            logger.exception("Failed dynamic daily cause-list fetch")

        dedup: dict[str, PdfTarget] = {}
        for t in pdf_targets:
            if t.pdf_url not in dedup:
                dedup[t.pdf_url] = t

        for target in dedup.values():
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            recent_run = (
                db.query(CauseListIngestionRun)
                .filter(
                    CauseListIngestionRun.source == target.source,
                    CauseListIngestionRun.listing_date == target.listing_date,
                    CauseListIngestionRun.fetched_from_url == target.pdf_url,
                    CauseListIngestionRun.fetched_at >= recent_cutoff,
                )
                .order_by(CauseListIngestionRun.fetched_at.desc())
                .first()
            )
            if recent_run:
                logger.info(
                    "Skipping cause-list ingest (already ingested in last 24h)",
                    extra={
                        "source": target.source.value,
                        "listing_date": target.listing_date.isoformat(),
                        "pdf_url": target.pdf_url,
                        "existing_run_id": str(recent_run.id),
                    },
                )
                continue

            try:
                pdf_bytes = self._download_pdf(target.pdf_url)
            except Exception:
                logger.exception("Failed downloading cause-list PDF", extra={"url": target.pdf_url})
                stats.failed_runs += 1
                continue

            stats.fetched += 1
            try:
                s3_key = self._build_pdf_s3_key(target.listing_date, target.pdf_url)
                self._save_pdf_to_s3(s3_key, pdf_bytes)
                run = CauseListIngestionRun(
                    source=target.source,
                    listing_date=target.listing_date,
                    fetched_from_url=target.pdf_url,
                    s3_bucket=self.s3_bucket,
                    s3_key=s3_key,
                    status="fetched",
                )
                db.add(run)
                db.flush()
                stats.runs += 1
                stats.listing_dates.add(target.listing_date.isoformat())
            except Exception:
                stats.failed_runs += 1
                logger.exception("Failed storing fetched daily PDF", extra={"url": target.pdf_url})

        db.commit()
        return stats


daily_pdf_fetch_service = DailyPdfFetchService()
