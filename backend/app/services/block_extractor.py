from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sqlalchemy.orm import Session

from app.db.models import User

PAGE_RE = re.compile(r"\[PAGE\s+(\d+)\]", re.IGNORECASE)
BLOCK_START_RE = re.compile(
    r"^(?P<serial>\d+(?:\.\d+)?)\s+(?P<case>[A-Z][A-Z()./ -]{1,50}\s*\d+\s*/\s*\d{2,4})\b",
    re.IGNORECASE,
)
COURT_RE = re.compile(r"COURT\s*NO\.?\s*([0-9A-Z]+)\s*[-–]\s*(\d{3,5})", re.IGNORECASE)
JUDGE_RE = re.compile(r"HON['’]?BLE[^\n]{0,220}", re.IGNORECASE)
SECTION_HINT_RE = re.compile(
    r"\b(ADMISSION|FOR\s+HEARING|SEPARATE\s+LIST\s*\d*|URGENT\s+MEMO|MEDIATION\s+LIST|ARBITRATION\s+LIST|SUPPLEMENTARY\s+LIST\s*\d*|DAILY\s+LIST)\b",
    re.IGNORECASE,
)

HONORIFICS_RE = re.compile(r"\b(SHRI|SMT|SRI|KUM|DR|MR|MS|MRS|ADV)\.?\b", re.IGNORECASE)
NON_ALNUM_RE = re.compile(r"[^A-Z0-9]+")


@dataclass
class AdvocateRecord:
    id: str
    name: str
    name_normalized: str


@dataclass
class CaseBlock:
    serial_number: str
    case_number_raw: str
    page_number: int | None
    court_number: str | None
    court_code: str | None
    section_label: str | None
    judges: list[str]
    text: str


@dataclass
class _NameSpan:
    advocate_id: str
    start: int
    end: int
    length: int


class BlockExtractor:
    def _normalize_for_tokens(self, value: str) -> str:
        upper = (value or "").upper()
        upper = HONORIFICS_RE.sub(" ", upper)
        upper = NON_ALNUM_RE.sub(" ", upper)
        return re.sub(r"\s+", " ", upper).strip()

    def _tokenize_name(self, value: str) -> list[str]:
        normalized = self._normalize_for_tokens(value)
        if not normalized:
            return []
        return [t for t in normalized.split(" ") if t]

    def _normalize_name(self, value: str) -> str:
        return "".join(self._tokenize_name(value))

    def _build_name_newline_pattern(self, name_tokens: list[str]) -> re.Pattern[str] | None:
        if not name_tokens:
            return None
        # Enforce explicit end-of-name boundary at newline.
        # This differentiates e.g. "SANJAY JOHNSON\\n" from
        # "SANJAY JOHNSON MATHEW\\n".
        pattern = r"(?<![A-Z0-9])" + r"\s+".join(re.escape(t) for t in name_tokens) + r"\s*\n"
        return re.compile(pattern, re.IGNORECASE)

    def get_verified_advocates(self, db: Session) -> list[AdvocateRecord]:
        # Mapping requested fields to existing User model.
        users = (
            db.query(User)
            .filter(User.is_verified == True, User.is_active == True)
            .all()
        )
        out: list[AdvocateRecord] = []
        for user in users:
            name = (user.khc_advocate_name or "").strip()
            if not name:
                continue
            out.append(
                AdvocateRecord(
                    id=str(user.id),
                    name=name,
                    name_normalized=self._normalize_name(name),
                )
            )
        return out

    def _extract_context(self, text_before: str, fallback_page: int | None) -> tuple[int | None, str | None, str | None, str | None, list[str]]:
        page = fallback_page
        page_matches = list(PAGE_RE.finditer(text_before))
        if page_matches:
            page = int(page_matches[-1].group(1))

        court_number = None
        court_code = None
        section_label = None
        judges: list[str] = []

        court_matches = list(COURT_RE.finditer(text_before))
        if court_matches:
            m = court_matches[-1]
            court_number = m.group(1).strip()
            court_code = m.group(2).strip()

        section_matches = list(SECTION_HINT_RE.finditer(text_before))
        if section_matches:
            section_label = section_matches[-1].group(0).strip().upper()

        judge_matches = list(JUDGE_RE.finditer(text_before))
        if judge_matches:
            seen = set()
            for j in judge_matches[-3:]:
                value = re.sub(r"\s+", " ", j.group(0)).strip()
                key = value.upper()
                if key not in seen:
                    seen.add(key)
                    judges.append(value)

        return page, court_number, court_code, section_label, judges

    def split_blocks(self, full_text: str) -> list[CaseBlock]:
        blocks: list[CaseBlock] = []
        lines = full_text.splitlines()

        current_page: int | None = None
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            pm = PAGE_RE.match(line)
            if pm:
                current_page = int(pm.group(1))
                i += 1
                continue

            m = BLOCK_START_RE.match(line)
            if not m:
                i += 1
                continue

            serial = m.group("serial").strip()
            case_raw = re.sub(r"\s+", " ", m.group("case")).strip().upper()

            start_idx = i
            end_idx = i + 1
            while end_idx < len(lines):
                next_line = lines[end_idx].strip()
                if BLOCK_START_RE.match(next_line):
                    break
                end_idx += 1

            block_text = "\n".join(lines[start_idx:end_idx]).strip()
            before_text = "\n".join(lines[max(0, start_idx - 120):start_idx])
            page, court_no, court_code, section_label, judges = self._extract_context(before_text, current_page)

            blocks.append(
                CaseBlock(
                    serial_number=serial,
                    case_number_raw=case_raw,
                    page_number=page,
                    court_number=court_no,
                    court_code=court_code,
                    section_label=section_label,
                    judges=judges,
                    text=block_text,
                )
            )
            i = end_idx

        return blocks

    def match_blocks_by_advocate(
        self,
        blocks: Iterable[CaseBlock],
        advocates: Iterable[AdvocateRecord],
    ) -> dict[str, list[CaseBlock]]:
        matched: dict[str, list[CaseBlock]] = {a.id: [] for a in advocates}
        advocates_list = list(advocates)
        advocate_tokens: dict[str, list[str]] = {adv.id: self._tokenize_name(adv.name) for adv in advocates_list}
        advocate_patterns: dict[str, re.Pattern[str] | None] = {
            adv.id: self._build_name_newline_pattern(advocate_tokens.get(adv.id) or [])
            for adv in advocates_list
        }

        for block in blocks:
            for adv in advocates_list:
                pattern = advocate_patterns.get(adv.id)
                if pattern is None:
                    continue
                if pattern.search(block.text):
                    matched[adv.id].append(block)

        return matched


    def extract_mediation_blocks(self, blocks: list[CaseBlock]) -> list[CaseBlock]:
        """
        Return the subset of parsed blocks that belong to the MEDIATION LIST
        section of the PDF.  These blocks do NOT contain advocate names inline,
        so they cannot be matched via ``match_blocks_by_advocate``; they are
        handled separately by ``MediationEnrichmentService``.
        """
        return [
            b for b in blocks
            if b.section_label and "MEDIATION" in b.section_label.upper()
        ]


block_extractor = BlockExtractor()
