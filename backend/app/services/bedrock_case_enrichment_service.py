from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

import boto3

from app.core.config import settings
from app.core.logger import logger


class BedrockCaseEnrichmentService:
    """Extract structured status fields from raw court response using Bedrock."""

    def __init__(self) -> None:
        self.model_id = (settings.CASE_SYNC_BEDROCK_MODEL_ID or settings.BEDROCK_MODEL_ID).strip()
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    def _parse_date(self, value: Optional[str]) -> Optional[datetime]:
        raw = (value or "").strip()
        if not raw:
            return None
        raw = raw.split("T")[0].strip()

        # Keep common machine-friendly date only when embedded in longer text.
        m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
        if m:
            raw = m.group(1)
        else:
            m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})", raw)
            if m:
                raw = m.group(1)

        # Normalize textual ordinals, e.g., "15th" -> "15".
        normalized = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", raw, flags=re.IGNORECASE)
        normalized = normalized.replace(",", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()

        for fmt in (
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%A the %d day of %B %Y",
            "%d day of %B %Y",
            "%d %B %Y",
        ):
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
        return None

    def _to_string_list(self, value: Any) -> Optional[list[str]]:
        if value is None:
            return None
        if isinstance(value, list):
            out = [str(v).strip() for v in value if str(v).strip()]
            return out or None
        text = str(value).strip()
        if not text:
            return None
        parts = [p.strip() for p in re.split(r"\n|;|,(?=\s*[A-Za-z0-9])", text) if p.strip()]
        return parts or [text]

    def _to_dict_list(self, value: Any) -> Optional[list[dict[str, Any]]]:
        if value is None:
            return None
        if isinstance(value, list):
            out: list[dict[str, Any]] = []
            for item in value:
                if isinstance(item, dict):
                    clean = {str(k): v for k, v in item.items() if str(k).strip()}
                    if clean:
                        out.append(clean)
                elif str(item).strip():
                    out.append({"text": str(item).strip()})
            return out or None
        if isinstance(value, dict):
            clean = {str(k): v for k, v in value.items() if str(k).strip()}
            return [clean] if clean else None
        text = str(value).strip()
        return [{"text": text}] if text else None

    def _extract_json(self, text: str) -> Dict[str, Any]:
        data = (text or "").strip()
        if not data:
            return {}
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            pass
        code_block = re.search(r"```json\s*(\{.*?\})\s*```", data, re.DOTALL | re.IGNORECASE)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except json.JSONDecodeError:
                return {}
        obj = re.search(r"\{.*\}", data, re.DOTALL)
        if obj:
            try:
                return json.loads(obj.group(0))
            except json.JSONDecodeError:
                return {}
        return {}

    def _adaptive_max_tokens(self, prompt_html: str) -> int:
        """
        Keep output budget low enough to reduce throttling, but scale slightly for larger pages.
        """
        n = len(prompt_html or "")
        if n < 20_000:
            return 700
        if n < 60_000:
            return 900
        if n < 100_000:
            return 1100
        return 1300

    def enrich_case_data(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        if not raw:
            return {
                "next_hearing_date": None,
                "court_status": None,
                "is_disposed": False,
                "bench": None,
                "last_hearing_date": None,
                "petitioner": None,
                "respondent": None,
                "raw_summary": "No raw data",
                "error": None,
            }

        payload = raw.get("payload") if isinstance(raw, dict) else None
        detail_html = ""
        if isinstance(payload, dict):
            detail_html = str(payload.get("detail_html") or payload.get("search_json") or "")
        if not detail_html:
            detail_html = json.dumps(raw, ensure_ascii=False)

        prompt = (
            "You are a legal data extraction assistant. "
            "Extract case status fields from Kerala High Court case-status HTML.\n\n"
            "Return STRICT JSON only with keys: "
            "case_type (string or null), "
            "filing_number (string or null), "
            "filing_date (YYYY-MM-DD or null), "
            "registration_number (string or null), "
            "registration_date (YYYY-MM-DD or null), "
            "cnr_number (string or null), "
            "efile_number (string or null), "
            "first_hearing_date (YYYY-MM-DD or null), "
            "next_hearing_date (YYYY-MM-DD or null), "
            "court_status (string or null), "
            "is_disposed (boolean), "
            "coram (string or null), "
            "bench (string or null), "
            "last_hearing_date (YYYY-MM-DD or null), "
            "last_listed_date (YYYY-MM-DD or null), "
            "last_listed_bench (string or null), "
            "last_listed_list (string or null), "
            "last_listed_item (string or null), "
            "petitioner (string or null), "
            "respondent (string or null), "
            "petitioner_advocates (array of strings or null), "
            "respondent_advocates (array of strings or null), "
            "served_on (array of strings or null), "
            "acts (array of strings or null), "
            "sections (array of strings or null), "
            "hearing_history (array of objects or null), "
            "interim_orders (array of objects or null), "
            "category_details (object or null), "
            "objections (array of strings or array of objects or null), "
            "raw_summary (single sentence string).\n\n"
            f"Input HTML:\n{detail_html[:140000]}"
        )

        try:
            max_tokens = self._adaptive_max_tokens(detail_html[:140000])
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": max_tokens,
                        "temperature": 0,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                ),
            )
            body = json.loads(response["body"].read())
            text = ""
            if isinstance(body.get("content"), list) and body["content"]:
                text = str(body["content"][0].get("text") or "")
            parsed = self._extract_json(text)
            populated_keys = [k for k, v in parsed.items() if v not in (None, "", [], {})] if isinstance(parsed, dict) else []
            logger.info("Bedrock case-status populated keys: %s", ", ".join(populated_keys) if populated_keys else "(none)")
            logger.info(
                "Bedrock case-status parsed JSON (truncated): %s",
                json.dumps(parsed, ensure_ascii=False, default=str)[:5000] if isinstance(parsed, dict) else str(parsed)[:5000],
            )

            status_text = str(parsed.get("court_status") or "").strip() or None
            is_disposed = bool(parsed.get("is_disposed"))
            if status_text and not parsed.get("is_disposed"):
                lower = status_text.lower()
                if "dispos" in lower or "dismiss" in lower or "closed" in lower:
                    is_disposed = True

            return {
                "case_type": str(parsed.get("case_type") or "").strip() or None,
                "filing_number": str(parsed.get("filing_number") or "").strip() or None,
                "filing_date": self._parse_date(parsed.get("filing_date")),
                "registration_number": str(parsed.get("registration_number") or "").strip() or None,
                "registration_date": self._parse_date(parsed.get("registration_date")),
                "cnr_number": str(parsed.get("cnr_number") or "").strip() or None,
                "efile_number": str(parsed.get("efile_number") or "").strip() or None,
                "first_hearing_date": self._parse_date(parsed.get("first_hearing_date")),
                "next_hearing_date": self._parse_date(parsed.get("next_hearing_date")),
                "court_status": status_text,
                "is_disposed": is_disposed,
                "coram": str(parsed.get("coram") or "").strip() or None,
                "bench": str(parsed.get("bench") or "").strip() or None,
                "last_hearing_date": self._parse_date(parsed.get("last_hearing_date")),
                "last_listed_date": self._parse_date(parsed.get("last_listed_date")),
                "last_listed_bench": str(parsed.get("last_listed_bench") or "").strip() or None,
                "last_listed_list": str(parsed.get("last_listed_list") or "").strip() or None,
                "last_listed_item": str(parsed.get("last_listed_item") or "").strip() or None,
                "petitioner": str(parsed.get("petitioner") or "").strip() or None,
                "respondent": str(parsed.get("respondent") or "").strip() or None,
                "petitioner_advocates": self._to_string_list(parsed.get("petitioner_advocates")),
                "respondent_advocates": self._to_string_list(parsed.get("respondent_advocates")),
                "served_on": self._to_string_list(parsed.get("served_on")),
                "acts": self._to_string_list(parsed.get("acts")),
                "sections": self._to_string_list(parsed.get("sections")),
                "hearing_history": self._to_dict_list(parsed.get("hearing_history")),
                "interim_orders": self._to_dict_list(parsed.get("interim_orders")),
                "category_details": parsed.get("category_details") if isinstance(parsed.get("category_details"), dict) else None,
                "objections": self._to_dict_list(parsed.get("objections")) or self._to_dict_list(self._to_string_list(parsed.get("objections"))),
                "raw_summary": str(parsed.get("raw_summary") or "").strip() or "Case status extracted",
                "error": None,
            }
        except Exception as exc:
            logger.warning("Bedrock enrichment failed: %s", str(exc))
            return {
                "case_type": None,
                "filing_number": None,
                "filing_date": None,
                "registration_number": None,
                "registration_date": None,
                "cnr_number": None,
                "efile_number": None,
                "first_hearing_date": None,
                "next_hearing_date": None,
                "court_status": None,
                "is_disposed": False,
                "coram": None,
                "bench": None,
                "last_hearing_date": None,
                "last_listed_date": None,
                "last_listed_bench": None,
                "last_listed_list": None,
                "last_listed_item": None,
                "petitioner": None,
                "respondent": None,
                "petitioner_advocates": None,
                "respondent_advocates": None,
                "served_on": None,
                "acts": None,
                "sections": None,
                "hearing_history": None,
                "interim_orders": None,
                "category_details": None,
                "objections": None,
                "raw_summary": "Enrichment failed",
                "error": str(exc),
            }


bedrock_case_enrichment_service = BedrockCaseEnrichmentService()
