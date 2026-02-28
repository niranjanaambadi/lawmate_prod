from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from typing import Any

import boto3
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.db.models import Case, CaseHistory, Document, HearingNote, HearingNoteCitation, HearingNoteEnrichment, User


class HearingNoteEnrichmentService:
    def __init__(self) -> None:
        self.model_id = (settings.HEARING_DAY_BEDROCK_MODEL_ID or settings.BEDROCK_MODEL_ID or "").strip()
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    @staticmethod
    def _citation_hash(citations: list[HearingNoteCitation]) -> str:
        base = "|".join(
            sorted(
                f"{str(c.id)}:{c.page_number}:{(c.quote_text or '').strip()}:{(c.anchor_id or '').strip()}"
                for c in citations
            )
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    @staticmethod
    def _lines(text: str) -> list[str]:
        return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]

    def _extract_by_keywords(self, lines: list[str], patterns: list[str], limit: int = 8) -> list[str]:
        rx = re.compile("|".join(patterns), re.IGNORECASE)
        out: list[str] = []
        for line in lines:
            if rx.search(line):
                out.append(line)
            if len(out) >= limit:
                break
        return out

    def _build_context(
        self,
        case: Case,
        note: HearingNote,
        citations: list[HearingNoteCitation],
        docs_by_id: dict[str, Document],
    ) -> dict[str, Any]:
        snippet_items = []
        for c in citations[:40]:
            doc = docs_by_id.get(str(c.doc_id))
            snippet_items.append(
                {
                    "doc_id": str(c.doc_id),
                    "doc_title": doc.title if doc else None,
                    "page": c.page_number,
                    "quote": (c.quote_text or "").strip(),
                }
            )

        return {
            "case": {
                "case_id": str(case.id),
                "case_number": case.case_number,
                "efiling_number": case.efiling_number,
                "status": str(case.status.value if hasattr(case.status, "value") else case.status),
                "court_status": case.court_status,
                "stage": case.bench_type,
                "next_hearing_date": case.next_hearing_date.isoformat() if case.next_hearing_date else None,
                "petitioner_name": case.petitioner_name,
                "respondent_name": case.respondent_name,
            },
            "note": {
                "version": note.version,
                "content_text": note.content_text or "",
                "content_json": note.content_json or {},
            },
            "citations": snippet_items,
        }

    def _deterministic_enrich(
        self,
        case: Case,
        note: HearingNote,
        citations: list[HearingNoteCitation],
        docs_by_id: dict[str, Document],
        db: Session,
    ) -> dict[str, Any]:
        lines = self._lines(note.content_text or "")

        issues = self._extract_by_keywords(
            lines,
            [r"\bissue\b", r"\bdispute\b", r"\bwhether\b", r"\bquestion\b", r"\bchallenge\b"],
        )
        reliefs = self._extract_by_keywords(
            lines,
            [r"\brelief\b", r"\bprayer\b", r"\bseeking\b", r"\bquash\b", r"\bset aside\b", r"\bdirection\b"],
        )
        tasks = self._extract_by_keywords(
            lines,
            [r"\bfile\b", r"\bsubmit\b", r"\bproduce\b", r"\bserve\b", r"\bcomply\b", r"\bprepare\b", r"\bdraft\b", r"\bcollect\b"],
            limit=12,
        )

        latest_order = (
            db.query(CaseHistory)
            .filter(CaseHistory.case_id == case.id)
            .order_by(CaseHistory.event_date.desc())
            .first()
        )

        last_order_summary = case.court_status or ""
        if latest_order and latest_order.business_recorded:
            last_order_summary = latest_order.business_recorded[:600]

        cited_refs = []
        for c in citations[:25]:
            doc = docs_by_id.get(str(c.doc_id))
            cited_refs.append(
                {
                    "doc_title": doc.title if doc else "Document",
                    "doc_id": str(c.doc_id),
                    "page": c.page_number,
                    "quote": (c.quote_text or "")[:320],
                }
            )

        return {
            "hearing_context": {
                "case_number": case.case_number or case.efiling_number,
                "status": str(case.status.value if hasattr(case.status, "value") else case.status),
                "court_status": case.court_status,
                "stage": case.bench_type,
                "next_hearing_date": case.next_hearing_date.isoformat() if case.next_hearing_date else None,
            },
            "issues_in_dispute": issues,
            "reliefs_prayed": reliefs,
            "last_order_summary": last_order_summary,
            "next_hearing_tasks": tasks,
            "based_on_citations": cited_refs,
        }

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        raw = (text or "").strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        m = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                return {}

        m2 = re.search(r"\{.*\}", raw, re.DOTALL)
        if m2:
            try:
                return json.loads(m2.group(0))
            except json.JSONDecodeError:
                return {}
        return {}

    def _llm_enrich(self, context: dict[str, Any], deterministic: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "You are a legal hearing-day assistant for Kerala High Court advocates.\n"
            "Given hearing context and deterministic extraction, return STRICT JSON only with keys:\n"
            "case_brief (string), arguments_for_petitioner (array), arguments_for_respondent (array),\n"
            "judge_questions_likely (array), risks (array), action_checklist (array),\n"
            "suggested_documents_to_open (array of objects with doc_id, doc_title, page, reason),\n"
            "based_on_citations (array of objects with doc_title, page).\n"
            "No markdown, no prose, JSON only.\n\n"
            f"Context:\n{json.dumps(context, ensure_ascii=False)[:120000]}\n\n"
            f"Deterministic:\n{json.dumps(deterministic, ensure_ascii=False)[:50000]}"
        )

        last_err = None
        for attempt in range(1, 4):
            try:
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(
                        {
                            "anthropic_version": "bedrock-2023-05-31",
                            "max_tokens": 1600,
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
                if parsed:
                    return parsed
                raise ValueError("Malformed JSON from model")
            except Exception as exc:
                last_err = str(exc)
                sleep_s = attempt * 1.5
                logger.warning("Hearing-day LLM enrich attempt failed (%s/3): %s", attempt, last_err)
                time.sleep(sleep_s)

        raise RuntimeError(last_err or "LLM enrichment failed")

    def enrich_case_note(self, case_id: str, current_user: User, db: Session) -> tuple[HearingNoteEnrichment, bool, bool]:
        case = db.query(Case).filter(Case.id == case_id, Case.advocate_id == current_user.id).first()
        if not case:
            raise ValueError("Case not found")

        note = (
            db.query(HearingNote)
            .filter(HearingNote.case_id == case.id, HearingNote.user_id == current_user.id)
            .first()
        )
        if not note:
            raise ValueError("No hearing note found")

        citations = (
            db.query(HearingNoteCitation)
            .filter(HearingNoteCitation.hearing_note_id == note.id)
            .all()
        )
        citation_hash = self._citation_hash(citations)

        cached = (
            db.query(HearingNoteEnrichment)
            .filter(
                HearingNoteEnrichment.hearing_note_id == note.id,
                HearingNoteEnrichment.note_version == note.version,
                HearingNoteEnrichment.citation_hash == citation_hash,
                HearingNoteEnrichment.status == "completed",
            )
            .order_by(HearingNoteEnrichment.updated_at.desc())
            .first()
        )
        if cached:
            return cached, True, False

        doc_ids = list({c.doc_id for c in citations})
        docs = db.query(Document).filter(Document.id.in_(doc_ids)).all() if doc_ids else []
        docs_by_id = {str(d.id): d for d in docs}

        context = self._build_context(case, note, citations, docs_by_id)
        deterministic = self._deterministic_enrich(case, note, citations, docs_by_id, db)

        deterministic_only = False
        model_used = self.model_id or "deterministic"
        status_value = "completed"
        error_value = None
        llm_payload: dict[str, Any] = {}

        try:
            if self.model_id:
                llm_payload = self._llm_enrich(context, deterministic)
            else:
                deterministic_only = True
        except Exception as exc:
            deterministic_only = True
            status_value = "completed"
            error_value = str(exc)
            logger.warning("Hearing-day LLM enrichment failed, using deterministic only: %s", error_value)

        merged = {
            **deterministic,
            "llm": llm_payload,
            "case_brief": llm_payload.get("case_brief") or deterministic.get("last_order_summary") or "",
            "arguments_for_petitioner": llm_payload.get("arguments_for_petitioner") or [],
            "arguments_for_respondent": llm_payload.get("arguments_for_respondent") or [],
            "judge_questions_likely": llm_payload.get("judge_questions_likely") or [],
            "risks": llm_payload.get("risks") or [],
            "action_checklist": llm_payload.get("action_checklist") or deterministic.get("next_hearing_tasks") or [],
            "suggested_documents_to_open": llm_payload.get("suggested_documents_to_open") or [
                {
                    "doc_id": item.get("doc_id"),
                    "doc_title": item.get("doc_title"),
                    "page": item.get("page"),
                    "reason": "Cited in hearing note",
                }
                for item in deterministic.get("based_on_citations", [])[:8]
            ],
        }

        row = HearingNoteEnrichment(
            hearing_note_id=note.id,
            user_id=current_user.id,
            model=model_used,
            note_version=note.version,
            citation_hash=citation_hash,
            enrichment_json=merged,
            status=status_value,
            error=error_value,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row, False, deterministic_only

    def get_latest_for_case(self, case_id: str, current_user: User, db: Session) -> HearingNoteEnrichment | None:
        case = db.query(Case).filter(Case.id == case_id, Case.advocate_id == current_user.id).first()
        if not case:
            return None
        note = db.query(HearingNote).filter(HearingNote.case_id == case.id, HearingNote.user_id == current_user.id).first()
        if not note:
            return None
        return (
            db.query(HearingNoteEnrichment)
            .filter(HearingNoteEnrichment.hearing_note_id == note.id)
            .order_by(HearingNoteEnrichment.updated_at.desc())
            .first()
        )


hearing_note_enrichment_service = HearingNoteEnrichmentService()
