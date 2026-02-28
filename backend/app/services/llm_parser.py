from __future__ import annotations

import asyncio
import boto3
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.core.config import settings
from app.core.logger import logger
from app.services.block_extractor import AdvocateRecord, CaseBlock


@dataclass
class AdvocateParseResult:
    advocate_id: str
    date: str
    total_listings: int
    listings: list[dict[str, Any]]
    parse_error: str | None = None


SECTION_ENUMS = [
    "ADMISSION",
    "FOR_HEARING",
    "SEPARATE_LIST",
    "URGENT_MEMO",
    "MEDIATION_LIST",
    "ARBITRATION_LIST",
    "SUPPLEMENTARY_LIST",
    "DAILY_LIST",
    "OTHER",
]

STATUS_ENUMS = [
    "ADMITTED",
    "ALLOWED",
    "DISPOSED",
    "PART_HEARD",
    "SERVICE_NOT_COMPLETE",
    "ADJOURNED",
    "NOT_ADMITTED",
    "UNKNOWN",
]


class LlmParser:
    def __init__(self) -> None:
        self.model = (
            getattr(settings, "CAUSELIST_BEDROCK_MODEL_ID", "") or getattr(settings, "BEDROCK_MODEL_ID", "")
        ).strip() or "anthropic.claude-3-haiku-20240307-v1:0"
        self.max_parallel = 10
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    def _build_prompt(self, advocate_name: str, listing_date: date, blocks: list[CaseBlock]) -> str:
        compact_blocks = []
        for b in blocks:
            compact_blocks.append(
                {
                    "serial_number": b.serial_number,
                    "case_number_raw": b.case_number_raw,
                    "page_number": b.page_number,
                    "court_number": b.court_number,
                    "court_code": b.court_code,
                    "section_label": b.section_label,
                    "judges": b.judges,
                    "raw_text": b.text[:5000],
                }
            )

        return (
            "You are extracting structured case listings for one advocate from Kerala High Court cause-list blocks. "
            "Return STRICT JSON only, no markdown.\n\n"
            f"Advocate Name: {advocate_name}\n"
            f"Date: {listing_date.isoformat()}\n\n"
            "Return object format:\n"
            "{\"advocate_id\":\"...\",\"date\":\"YYYY-MM-DD\",\"total_listings\":N,\"listings\":[...]}\n"
            "Each listing must contain keys exactly:\n"
            "serial_number,is_sub_item,parent_serial_number,court_number,court_code,judges,"
            "section_type,section_label,case_number_raw,case_type,case_number,case_year,case_category,"
            "filing_mode_raw,bench_type,petitioner_names,respondent_names,advocate_role,"
            "advocate_role_detail,represented_parties,is_lead_advocate,status,remarks,"
            "all_petitioner_advocates,all_respondent_advocates,interlocutory_applications,"
            "linked_cases,pending_compliance,interim_order_expiry,urgent_memo_by,urgent_memo_service_status,page_number\n"
            f"section_type enum: {SECTION_ENUMS}\n"
            "case_category enum: [CIVIL,CRIMINAL,MEDIATION,ARBITRATION,OTHER]\n"
            "advocate_role enum: [PETITIONER_ADVOCATE,RESPONDENT_ADVOCATE,OTHER]\n"
            f"status enum: {STATUS_ENUMS}\n"
            "If unknown, use null/UNKNOWN consistently; do not invent facts.\n\n"
            f"BLOCKS JSON:\n{json.dumps(compact_blocks, ensure_ascii=False)}"
        )

    def _invoke_bedrock(self, prompt: str) -> dict[str, Any]:
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8192,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = self.client.invoke_model(modelId=self.model, body=json.dumps(payload))
        data = json.loads(response["body"].read())

        text = ""
        for part in data.get("content", []):
            if isinstance(part, dict) and part.get("type") == "text":
                text += part.get("text", "")

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise ValueError("Anthropic response does not contain JSON object")
        parsed = json.loads(m.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("Anthropic JSON is not an object")
        return parsed

    async def _parse_one(
        self,
        sem: asyncio.Semaphore,
        advocate: AdvocateRecord,
        listing_date: date,
        blocks: list[CaseBlock],
    ) -> AdvocateParseResult:
        if not blocks:
            return AdvocateParseResult(
                advocate_id=advocate.id,
                date=listing_date.isoformat(),
                total_listings=0,
                listings=[],
                parse_error=None,
            )

        prompt = self._build_prompt(advocate.name, listing_date, blocks)
        async with sem:
            try:
                parsed = await asyncio.to_thread(self._invoke_bedrock, prompt)
                listings = parsed.get("listings") if isinstance(parsed.get("listings"), list) else []
                return AdvocateParseResult(
                    advocate_id=advocate.id,
                    date=listing_date.isoformat(),
                    total_listings=int(parsed.get("total_listings") or len(listings)),
                    listings=listings,
                    parse_error=None,
                )
            except Exception as exc:
                logger.warning("LLM parse failed for advocate_id=%s: %s", advocate.id, str(exc))
                return AdvocateParseResult(
                    advocate_id=advocate.id,
                    date=listing_date.isoformat(),
                    total_listings=0,
                    listings=[],
                    parse_error=str(exc),
                )

    async def parse_per_advocate(
        self,
        listing_date: date,
        advocates: list[AdvocateRecord],
        matched_blocks: dict[str, list[CaseBlock]],
    ) -> list[AdvocateParseResult]:
        sem = asyncio.Semaphore(self.max_parallel)
        tasks = [
            self._parse_one(sem, adv, listing_date, matched_blocks.get(adv.id, []))
            for adv in advocates
        ]
        return await asyncio.gather(*tasks)


llm_parser = LlmParser()
