import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import boto3
import httpx
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.logger import logger


@dataclass
class ActiveRoster:
    label: str
    effective_date: Optional[str]
    source_page: str
    source_pdf_url: str


class RosterService:
    def __init__(self) -> None:
        self.source_url = settings.ROSTER_SOURCE_URL
        self.bucket = settings.ROSTER_S3_BUCKET_NAME
        self.prefix = settings.ROSTER_S3_PREFIX.strip("/")
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
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            res.raise_for_status()
            return res.text

    def _parse_effective_date(self, label: str) -> Optional[str]:
        m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", label)
        if not m:
            return None
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    def _extract_active_roster(self, html: str) -> ActiveRoster:
        start = html.find('id="screenrosterBoard"')
        if start < 0:
            raise ValueError("Roster modal not found in source HTML")

        scope = html[start : min(len(html), start + 50000)]
        selected_match = re.search(
            r'<option[^>]*selected=["\']selected["\'][^>]*>([\s\S]*?)</option>',
            scope,
            re.IGNORECASE,
        )
        label = (
            re.sub(r"<[^>]+>", " ", selected_match.group(1)).strip()
            if selected_match
            else "Roster PDF"
        )
        label = re.sub(r"\s+", " ", label)

        pdf_match = re.search(
            r'const\s+url\s*=\s*["\']([^"\']*/writereaddata/[^"\']+\.pdf[^"\']*)["\']',
            html,
            re.IGNORECASE,
        )
        if not pdf_match:
            raise ValueError("Active roster PDF URL not found in source HTML")

        source_pdf_url = urljoin(self.source_url, pdf_match.group(1))
        return ActiveRoster(
            label=label,
            effective_date=self._parse_effective_date(label),
            source_page=self.source_url,
            source_pdf_url=source_pdf_url,
        )

    def _download_pdf(self, url: str) -> bytes:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
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
            content_type = (res.headers.get("content-type") or "").lower()
            if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                logger.warning("Roster source returned non-PDF content-type: %s", content_type)
            return res.content

    def _put_object(self, key: str, body: bytes, content_type: str) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )

    def _key(self, suffix: str) -> str:
        return f"{self.prefix}/{suffix}".strip("/")

    def _read_latest_meta(self) -> Optional[dict[str, Any]]:
        latest_meta_key = self._key("latest.json")
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=latest_meta_key)
            body = obj["Body"].read().decode("utf-8")
            return json.loads(body)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404"}:
                return None
            raise

    def _presigned_url(self, key: str, expires_in: int = 3600) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def sync_latest_roster(self) -> dict[str, Any]:
        html = self._fetch_html(self.source_url)
        active = self._extract_active_roster(html)
        pdf_bytes = self._download_pdf(active.source_pdf_url)
        checksum = hashlib.sha256(pdf_bytes).hexdigest()
        now = datetime.now(timezone.utc).isoformat()

        parsed = urlparse(active.source_pdf_url)
        filename = parsed.path.split("/")[-1] or "roster.pdf"
        effective_part = active.effective_date or datetime.now(timezone.utc).date().isoformat()
        archival_key = self._key(f"{effective_part}/{filename}")
        latest_pdf_key = self._key("latest.pdf")
        latest_meta_key = self._key("latest.json")

        latest_existing = self._read_latest_meta()
        if latest_existing and latest_existing.get("checksum") == checksum:
            latest_existing["lastCheckedAt"] = now
            self._put_object(
                latest_meta_key,
                json.dumps(latest_existing, ensure_ascii=True).encode("utf-8"),
                "application/json",
            )
            latest_existing["signedUrl"] = self._presigned_url(latest_existing["s3Key"])
            return latest_existing

        self._put_object(archival_key, pdf_bytes, "application/pdf")
        self._put_object(latest_pdf_key, pdf_bytes, "application/pdf")

        meta = {
            "label": active.label,
            "effectiveDate": active.effective_date,
            "sourcePage": active.source_page,
            "sourcePdfUrl": active.source_pdf_url,
            "bucket": self.bucket,
            "s3Key": latest_pdf_key,
            "archivalKey": archival_key,
            "checksum": checksum,
            "fetchedAt": now,
            "lastCheckedAt": now,
        }
        self._put_object(
            latest_meta_key,
            json.dumps(meta, ensure_ascii=True).encode("utf-8"),
            "application/json",
        )

        meta["signedUrl"] = self._presigned_url(latest_pdf_key)
        return meta

    def get_latest_roster(self) -> dict[str, Any]:
        meta = self._read_latest_meta()
        if not meta:
            return self.sync_latest_roster()
        meta["signedUrl"] = self._presigned_url(meta["s3Key"])
        return meta
