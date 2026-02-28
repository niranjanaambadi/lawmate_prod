"""
Document Comparison Service — LawMate
======================================
Handles text extraction from PDF/DOCX/image files and computes
a rich legal diff including:
  - Paragraph-level SequenceMatcher diff
  - Inline word-level diff for replaced blocks
  - Legal-entity detection (sections, dates, citations, amounts)
  - Prayer/Relief section isolation
  - Comparison Memo PDF generation via ReportLab
"""
from __future__ import annotations

import difflib
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

import pypdf

# PyMuPDF (fitz) for rasterising scanned PDFs
try:
    import fitz  # type: ignore
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

# Tesseract OCR
try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

# python-docx
try:
    from docx import Document as DocxDocument  # type: ignore
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# ReportLab for memo PDF
try:
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.enums import TA_CENTER, TA_LEFT  # type: ignore
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
    from reportlab.lib.units import inch  # type: ignore
    from reportlab.platypus import (  # type: ignore
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# ── Result TTL ────────────────────────────────────────────────────────────────
# Comparison results are kept in PostgreSQL for this long, then deleted.
COMPARISON_TTL = timedelta(hours=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Legal-Entity Regex Patterns
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SECTION_RE = re.compile(
    r"""
    \bSection\s+\d+[A-Z]?(?:\([a-z0-9]+\))*   # Section 438(1)(a)
    (?:\s+(?:of\s+the\s+)?(?:Cr\.?P\.?C\.?|I\.?P\.?C\.?|C\.?P\.?C\.?|Evidence\s+Act|Kerala\b[^,\n]*?))?
    | \bS\.\s*\d+[A-Z]?(?:\([a-z0-9]+\))*     # S.438(1)
    | \bArticle\s+\d+[A-Z]?                   # Article 21
    | \b(?:Order|Rule)\s+\d+[A-Z]?\s+Rule\s+\d+[A-Z]?  # Order XXXIX Rule 1
    """,
    re.IGNORECASE | re.VERBOSE,
)

_DATE_RE = re.compile(
    r"""
    \b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b        # 01/01/2024
    | \b\d{1,2}\s+
      (?:January|February|March|April|May|June|July|
         August|September|October|November|December)
      \s+\d{4}\b                               # 1 January 2024
    | \b(?:January|February|March|April|May|June|July|
           August|September|October|November|December)
      \s+\d{1,2},?\s+\d{4}\b                  # January 1, 2024
    """,
    re.IGNORECASE | re.VERBOSE,
)

_CITATION_RE = re.compile(
    r"""
    \b(?:AIR|SCC|SCR|All|Bom|Mad|Cal|Del|Ker|MLJ|KLT|KLJ|KHC)\s*
    \d{4}\s*(?:SC|HC|SCC|SCR|[A-Z]{1,5})?\s*\d+\b
    | \b\d{4}\s+SCC\s+\d+\b
    | \b\d{4}\s+\(\d+\)\s+SCC\s+\d+\b
    | \bWP\s*\(?\s*C\s*\)?\s*No\.?\s*\d+\s*/\s*\d{4}\b
    | \b(?:WA|RP|CRL\.?A|SA|OS|OP|CRL\.?MC)\s*No\.?\s*\d+\s*/\s*\d{4}\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_AMOUNT_RE = re.compile(
    r"""
    (?:Rs\.?|₹|INR)\s*[\d,]+(?:\.\d{1,2})?
    | \b[\d,]+(?:\.\d{1,2})?\s*(?:lakhs?|crores?|rupees?)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_PRAYER_RE = re.compile(
    r"^(?:PRAYER|PRAYERS|PRAYER\s+CLAUSE|PRAYERS\s+CLAUSE|RELIEF\s+SOUGHT|"
    r"RELIEFS\s+SOUGHT|WHEREFORE|IN\s+VIEW\s+OF\s+THE\s+ABOVE|"
    r"THE\s+PETITIONER\s+(?:PRAYS|HUMBLY\s+PRAYS)|"
    r"IT\s+IS\s+(?:THEREFORE\s+)?PRAYED|"
    r"YOUR\s+LORDSHIP\s+(?:MAY\s+BE\s+PLEASED|IS\s+PRAYED))",
    re.IGNORECASE | re.MULTILINE,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data Classes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class LegalEntities:
    sections: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    amounts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sections": self.sections,
            "dates": self.dates,
            "citations": self.citations,
            "amounts": self.amounts,
        }


@dataclass
class DiffBlock:
    """One unit of a document comparison."""
    type: str            # "equal" | "insert" | "delete" | "replace"
    left_text: str
    right_text: str
    left_start: int      # paragraph index in original
    right_start: int
    entities_left: LegalEntities = field(default_factory=LegalEntities)
    entities_right: LegalEntities = field(default_factory=LegalEntities)
    is_substantive: bool = False
    word_diff: list[dict] | None = None  # inline word-level diff for "replace"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "left_text": self.left_text,
            "right_text": self.right_text,
            "left_start": self.left_start,
            "right_start": self.right_start,
            "entities_left": self.entities_left.to_dict(),
            "entities_right": self.entities_right.to_dict(),
            "is_substantive": self.is_substantive,
            "word_diff": self.word_diff,
        }


@dataclass
class ComparisonResult:
    comparison_id: str
    doc_a_name: str
    doc_b_name: str
    blocks: list[DiffBlock]
    prayer_a: Optional[str]
    prayer_b: Optional[str]
    prayer_diff: list[DiffBlock]
    total_additions: int
    total_deletions: int
    total_changes: int
    substantive_changes: int
    legal_entity_changes: dict
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "comparison_id": self.comparison_id,
            "doc_a_name": self.doc_a_name,
            "doc_b_name": self.doc_b_name,
            "blocks": [b.to_dict() for b in self.blocks],
            "prayer_a": self.prayer_a,
            "prayer_b": self.prayer_b,
            "prayer_diff": [b.to_dict() for b in self.prayer_diff],
            "total_additions": self.total_additions,
            "total_deletions": self.total_deletions,
            "total_changes": self.total_changes,
            "substantive_changes": self.substantive_changes,
            "legal_entity_changes": self.legal_entity_changes,
            "created_at": self.created_at.isoformat(),
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Text Extraction
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_text_from_bytes(
    file_bytes: bytes,
    content_type: str,
    filename: str,
    language: str = "eng",
) -> str:
    """Extract readable text from PDF, DOCX, image, or plain-text bytes."""
    ct = (content_type or "").lower()
    fname = (filename or "").lower()

    if "pdf" in ct or fname.endswith(".pdf"):
        return _extract_pdf(file_bytes, language)
    elif "word" in ct or "docx" in ct or fname.endswith(".docx"):
        return _extract_docx(file_bytes)
    elif any(img in ct for img in ("image/", "png", "jpg", "jpeg", "tiff", "bmp", "webp")):
        return _ocr_image_bytes(file_bytes, language)
    elif "text" in ct or fname.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="replace")
    else:
        # Best-effort: try PDF then raw decode
        try:
            return _extract_pdf(file_bytes, language)
        except Exception:
            return file_bytes.decode("utf-8", errors="replace")


def _extract_pdf(file_bytes: bytes, language: str = "eng") -> str:
    """Native PDF text extraction with OCR fallback for scanned pages."""
    # 1. Try native text (pypdf)
    native_pages: list[str] = []
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            native_pages.append((page.extract_text() or "").strip())
    except Exception:
        pass

    native_text = "\n\n".join(native_pages).strip()

    # 2. If native text is sparse, use OCR via fitz + tesseract
    if len(native_text) < 200 and HAS_FITZ and HAS_OCR:
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            ocr_pages: list[str] = []
            lang_str = _tesseract_lang(language)
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_pages.append(pytesseract.image_to_string(img, lang=lang_str).strip())
            doc.close()
            ocr_text = "\n\n".join(ocr_pages).strip()
            # Prefer whichever is longer
            return ocr_text if len(ocr_text) > len(native_text) else native_text
        except Exception:
            pass

    return native_text


def _extract_docx(file_bytes: bytes) -> str:
    if not HAS_DOCX:
        raise RuntimeError("python-docx is not installed; cannot parse .docx files.")
    doc = DocxDocument(io.BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _ocr_image_bytes(file_bytes: bytes, language: str = "eng") -> str:
    if not HAS_OCR:
        raise RuntimeError("pytesseract / Pillow not installed; cannot OCR images.")
    img = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(img, lang=_tesseract_lang(language)).strip()


def _tesseract_lang(language: str) -> str:
    """Map language code to tesseract lang string."""
    lang = language.lower()
    if "mal" in lang or "ml" in lang:
        return "mal+eng"
    return "eng"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Core Comparison Logic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def compare_documents(
    text_a: str,
    text_b: str,
    doc_a_name: str,
    doc_b_name: str,
) -> ComparisonResult:
    """Run the full comparison pipeline and return a ComparisonResult."""
    comparison_id = str(uuid.uuid4())

    paras_a = _split_paragraphs(text_a)
    paras_b = _split_paragraphs(text_b)

    matcher = difflib.SequenceMatcher(None, paras_a, paras_b, autojunk=False)

    blocks: list[DiffBlock] = []
    total_additions = 0
    total_deletions = 0
    total_changes = 0
    substantive_changes = 0

    for opcode, a1, a2, b1, b2 in matcher.get_opcodes():
        if opcode == "equal":
            for i in range(a2 - a1):
                blocks.append(
                    DiffBlock(
                        type="equal",
                        left_text=paras_a[a1 + i],
                        right_text=paras_b[b1 + i],
                        left_start=a1 + i,
                        right_start=b1 + i,
                    )
                )

        elif opcode == "insert":
            for i, pb in enumerate(paras_b[b1:b2]):
                ent_b = _extract_entities(pb)
                subst = bool(ent_b.sections or ent_b.citations or ent_b.amounts)
                blocks.append(
                    DiffBlock(
                        type="insert",
                        left_text="",
                        right_text=pb,
                        left_start=a1,
                        right_start=b1 + i,
                        entities_right=ent_b,
                        is_substantive=subst,
                    )
                )
                total_additions += 1
                if subst:
                    substantive_changes += 1

        elif opcode == "delete":
            for i, pa in enumerate(paras_a[a1:a2]):
                ent_a = _extract_entities(pa)
                subst = bool(ent_a.sections or ent_a.citations or ent_a.amounts)
                blocks.append(
                    DiffBlock(
                        type="delete",
                        left_text=pa,
                        right_text="",
                        left_start=a1 + i,
                        right_start=b1,
                        entities_left=ent_a,
                        is_substantive=subst,
                    )
                )
                total_deletions += 1
                if subst:
                    substantive_changes += 1

        elif opcode == "replace":
            a_list = paras_a[a1:a2]
            b_list = paras_b[b1:b2]
            max_len = max(len(a_list), len(b_list))
            for i in range(max_len):
                pa = a_list[i] if i < len(a_list) else ""
                pb = b_list[i] if i < len(b_list) else ""
                ent_a = _extract_entities(pa)
                ent_b = _extract_entities(pb)
                subst = _is_substantive(ent_a, ent_b)
                word_diff = _word_diff(pa, pb) if pa and pb else None
                blocks.append(
                    DiffBlock(
                        type="replace",
                        left_text=pa,
                        right_text=pb,
                        left_start=a1 + i,
                        right_start=b1 + i,
                        entities_left=ent_a,
                        entities_right=ent_b,
                        is_substantive=subst,
                        word_diff=word_diff,
                    )
                )
                total_changes += 1
                if subst:
                    substantive_changes += 1

    # Prayer sections
    prayer_a = _extract_prayer(text_a)
    prayer_b = _extract_prayer(text_b)
    prayer_diff = _diff_prayer(prayer_a or "", prayer_b or "") if (prayer_a or prayer_b) else []

    # Global legal entity change summary
    legal_entity_changes = _legal_entity_diff(text_a, text_b)

    result = ComparisonResult(
        comparison_id=comparison_id,
        doc_a_name=doc_a_name,
        doc_b_name=doc_b_name,
        blocks=blocks,
        prayer_a=prayer_a,
        prayer_b=prayer_b,
        prayer_diff=prayer_diff,
        total_additions=total_additions,
        total_deletions=total_deletions,
        total_changes=total_changes,
        substantive_changes=substantive_changes,
        legal_entity_changes=legal_entity_changes,
    )

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; further split very long single-line paragraphs."""
    raw = re.split(r"\n\s*\n", text)
    result = []
    for chunk in raw:
        chunk = chunk.strip()
        if not chunk:
            continue
        # If a chunk has many lines (e.g. a table), keep as-is
        result.append(chunk)
    return result or [""]


def _extract_entities(text: str) -> LegalEntities:
    return LegalEntities(
        sections=list(dict.fromkeys(_SECTION_RE.findall(text))),
        dates=list(dict.fromkeys(_DATE_RE.findall(text))),
        citations=list(dict.fromkeys(_CITATION_RE.findall(text))),
        amounts=list(dict.fromkeys(_AMOUNT_RE.findall(text))),
    )


def _is_substantive(a: LegalEntities, b: LegalEntities) -> bool:
    return (
        set(a.sections) != set(b.sections)
        or set(a.citations) != set(b.citations)
        or set(a.amounts) != set(b.amounts)
        or set(a.dates) != set(b.dates)
    )


def _word_diff(text_a: str, text_b: str) -> list[dict]:
    """
    Compute an inline word-level diff between two strings.
    Returns a list of {type: 'equal'|'insert'|'delete'|'replace', left, right}.
    """
    words_a = text_a.split()
    words_b = text_b.split()
    sm = difflib.SequenceMatcher(None, words_a, words_b, autojunk=False)
    result: list[dict] = []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        result.append({
            "op": op,
            "left": " ".join(words_a[a1:a2]),
            "right": " ".join(words_b[b1:b2]),
        })
    return result


def _extract_prayer(text: str) -> Optional[str]:
    """Locate the prayer / relief section in the document."""
    m = _PRAYER_RE.search(text)
    if not m:
        return None
    start = m.start()
    # Take up to 4000 chars to capture full prayer block
    return text[start: start + 4000].strip()


def _diff_prayer(prayer_a: str, prayer_b: str) -> list[DiffBlock]:
    """Line-level diff of prayer sections."""
    lines_a = [l.strip() for l in prayer_a.splitlines() if l.strip()]
    lines_b = [l.strip() for l in prayer_b.splitlines() if l.strip()]
    sm = difflib.SequenceMatcher(None, lines_a, lines_b)
    blocks: list[DiffBlock] = []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal":
            for i in range(a2 - a1):
                blocks.append(DiffBlock(type="equal", left_text=lines_a[a1 + i], right_text=lines_b[b1 + i], left_start=a1 + i, right_start=b1 + i))
        elif op == "insert":
            for i, lb in enumerate(lines_b[b1:b2]):
                blocks.append(DiffBlock(type="insert", left_text="", right_text=lb, left_start=a1, right_start=b1 + i))
        elif op == "delete":
            for i, la in enumerate(lines_a[a1:a2]):
                blocks.append(DiffBlock(type="delete", left_text=la, right_text="", left_start=a1 + i, right_start=b1))
        else:
            a_ls = lines_a[a1:a2]
            b_ls = lines_b[b1:b2]
            for i in range(max(len(a_ls), len(b_ls))):
                blocks.append(DiffBlock(
                    type="replace",
                    left_text=a_ls[i] if i < len(a_ls) else "",
                    right_text=b_ls[i] if i < len(b_ls) else "",
                    left_start=a1 + i,
                    right_start=b1 + i,
                    word_diff=_word_diff(a_ls[i], b_ls[i]) if i < len(a_ls) and i < len(b_ls) else None,
                ))
    return blocks


def _legal_entity_diff(text_a: str, text_b: str) -> dict:
    sec_a = set(_SECTION_RE.findall(text_a))
    sec_b = set(_SECTION_RE.findall(text_b))
    cit_a = set(_CITATION_RE.findall(text_a))
    cit_b = set(_CITATION_RE.findall(text_b))
    amt_a = set(_AMOUNT_RE.findall(text_a))
    amt_b = set(_AMOUNT_RE.findall(text_b))
    date_a = set(_DATE_RE.findall(text_a))
    date_b = set(_DATE_RE.findall(text_b))
    return {
        "sections_added": sorted(sec_b - sec_a),
        "sections_removed": sorted(sec_a - sec_b),
        "sections_common": sorted(sec_a & sec_b),
        "citations_added": sorted(cit_b - cit_a),
        "citations_removed": sorted(cit_a - cit_b),
        "citations_common": sorted(cit_a & cit_b),
        "amounts_added": sorted(amt_b - amt_a),
        "amounts_removed": sorted(amt_a - amt_b),
        "dates_added": sorted(date_b - date_a),
        "dates_removed": sorted(date_a - date_b),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Comparison Memo PDF Generation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def store_comparison(result: ComparisonResult, owner_id: str, db: "Session") -> None:
    """Persist a ComparisonResult to PostgreSQL scoped to owner_id."""
    from app.db.models import DocComparison
    import uuid as _uuid

    row = DocComparison(
        id=_uuid.UUID(result.comparison_id),
        owner_id=_uuid.UUID(owner_id),
        doc_a_name=result.doc_a_name,
        doc_b_name=result.doc_b_name,
        result_json=result.to_dict(),
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + COMPARISON_TTL,
    )
    db.add(row)
    db.commit()


def get_stored_comparison(
    comparison_id: str, owner_id: str, db: "Session"
) -> Optional[ComparisonResult]:
    """
    Retrieve a ComparisonResult from PostgreSQL.
    Returns None if:
      - the row doesn't exist
      - it belongs to a different user
      - it has expired
    Expired rows are deleted lazily on access.
    """
    from app.db.models import DocComparison
    import uuid as _uuid

    try:
        cid = _uuid.UUID(comparison_id)
        oid = _uuid.UUID(owner_id)
    except ValueError:
        return None

    row: Optional[DocComparison] = db.query(DocComparison).filter(
        DocComparison.id == cid,
        DocComparison.owner_id == oid,
    ).first()

    if row is None:
        return None

    # Lazy expiry
    if row.expires_at < datetime.utcnow():
        db.delete(row)
        db.commit()
        return None

    return _dict_to_result(row.result_json)


def delete_expired_comparisons(db: "Session") -> int:
    """Delete all expired rows. Called by the periodic cleanup task."""
    from app.db.models import DocComparison

    deleted = (
        db.query(DocComparison)
        .filter(DocComparison.expires_at < datetime.utcnow())
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def _dict_to_result(data: dict) -> ComparisonResult:
    """Reconstruct a ComparisonResult from its to_dict() representation."""

    def _make_entities(d: dict) -> LegalEntities:
        return LegalEntities(
            sections=d.get("sections", []),
            dates=d.get("dates", []),
            citations=d.get("citations", []),
            amounts=d.get("amounts", []),
        )

    def _make_block(b: dict) -> DiffBlock:
        return DiffBlock(
            type=b["type"],
            left_text=b["left_text"],
            right_text=b["right_text"],
            left_start=b["left_start"],
            right_start=b["right_start"],
            entities_left=_make_entities(b.get("entities_left", {})),
            entities_right=_make_entities(b.get("entities_right", {})),
            is_substantive=b.get("is_substantive", False),
            word_diff=b.get("word_diff"),
        )

    return ComparisonResult(
        comparison_id=data["comparison_id"],
        doc_a_name=data["doc_a_name"],
        doc_b_name=data["doc_b_name"],
        blocks=[_make_block(b) for b in data.get("blocks", [])],
        prayer_a=data.get("prayer_a"),
        prayer_b=data.get("prayer_b"),
        prayer_diff=[_make_block(b) for b in data.get("prayer_diff", [])],
        total_additions=data.get("total_additions", 0),
        total_deletions=data.get("total_deletions", 0),
        total_changes=data.get("total_changes", 0),
        substantive_changes=data.get("substantive_changes", 0),
        legal_entity_changes=data.get("legal_entity_changes", {}),
        created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow(),
    )


def generate_comparison_memo_pdf(result: ComparisonResult) -> bytes:
    """Generate a formatted PDF Comparison Memo."""
    if not HAS_REPORTLAB:
        raise RuntimeError("ReportLab is not installed; cannot generate PDF.")

    buf = io.BytesIO()
    doc_pdf = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=0.75 * inch, leftMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()

    def S(name: str, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)

    title_st = S("T", fontSize=16, spaceAfter=6, alignment=TA_CENTER,
                 textColor=colors.HexColor("#1e3a5f"), fontName="Helvetica-Bold")
    sub_st = S("Sub", fontSize=9, spaceAfter=10, alignment=TA_CENTER,
               textColor=colors.HexColor("#6b7280"))
    sec_st = S("Sec", fontSize=11, spaceBefore=14, spaceAfter=6,
               textColor=colors.HexColor("#1e40af"), fontName="Helvetica-Bold")
    body_st = S("Body", fontSize=8.5, leading=13)
    footer_st = S("Ftr", fontSize=7, alignment=TA_CENTER,
                  textColor=colors.HexColor("#9ca3af"), spaceBefore=6)

    story = []
    story.append(Paragraph("⚖  DOCUMENT COMPARISON MEMO", title_st))
    story.append(Paragraph(
        f"LawMate · Generated {result.created_at.strftime('%d %B %Y, %I:%M %p')} · ID: {result.comparison_id[:8]}",
        sub_st,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
    story.append(Spacer(1, 10))

    # ── Documents Compared ───────────────────────────────────────────────────
    story.append(Paragraph("Documents Compared", sec_st))
    story.append(_table(
        [["Document A (Original)", result.doc_a_name],
         ["Document B (Amended / New)", result.doc_b_name]],
        col_widths=[2 * inch, 4.5 * inch],
        header_color="#f1f5f9", header_text_color="#1e3a5f",
    ))
    story.append(Spacer(1, 10))

    # ── Summary ─────────────────────────────────────────────────────────────
    story.append(Paragraph("Change Summary", sec_st))
    story.append(_table(
        [["Metric", "Count"],
         ["Paragraphs Added (Doc B only)", str(result.total_additions)],
         ["Paragraphs Deleted (Doc A only)", str(result.total_deletions)],
         ["Paragraphs Modified", str(result.total_changes)],
         ["Substantive Legal Changes", str(result.substantive_changes)]],
        col_widths=[3.5 * inch, 3 * inch],
        header_color="#1e40af",
    ))
    story.append(Spacer(1, 10))

    # ── Legal Entity Changes ─────────────────────────────────────────────────
    lec = result.legal_entity_changes
    if any(lec.get(k) for k in ("sections_added", "sections_removed", "citations_added",
                                 "citations_removed", "amounts_added", "amounts_removed")):
        story.append(Paragraph("Legal Entity Changes", sec_st))
        rows = [["Entity Type", "Added in Doc B", "Removed from Doc A"]]
        for label, add_k, rem_k in [
            ("Sections / Articles", "sections_added", "sections_removed"),
            ("Case Citations", "citations_added", "citations_removed"),
            ("Monetary Amounts", "amounts_added", "amounts_removed"),
            ("Key Dates", "dates_added", "dates_removed"),
        ]:
            added = ", ".join(lec.get(add_k, [])[:8]) or "—"
            removed = ", ".join(lec.get(rem_k, [])[:8]) or "—"
            if added != "—" or removed != "—":
                rows.append([label, added, removed])
        if len(rows) > 1:
            story.append(_table(rows, col_widths=[1.5 * inch, 3 * inch, 2 * inch], header_color="#7c3aed"))
            story.append(Spacer(1, 10))

    # ── Prayer Comparison ────────────────────────────────────────────────────
    if result.prayer_a or result.prayer_b:
        story.append(Paragraph("Prayer / Relief Comparison", sec_st))
        pa_text = (result.prayer_a or "No prayer section detected.")[:1200]
        pb_text = (result.prayer_b or "No prayer section detected.")[:1200]
        story.append(_table(
            [["Document A — Original Prayer", "Document B — Amended Prayer"],
             [Paragraph(pa_text, body_st), Paragraph(pb_text, body_st)]],
            col_widths=[3.25 * inch, 3.25 * inch],
            header_color="#b45309",
        ))
        story.append(Spacer(1, 10))

    # ── Substantive Changes ──────────────────────────────────────────────────
    subst = [b for b in result.blocks if b.type in ("replace", "insert", "delete") and b.is_substantive]
    if subst:
        story.append(Paragraph("Substantive Changes — Legal Entities Affected", sec_st))
        rows = [["#", "Original (Doc A)", "Amended (Doc B)", "Type"]]
        type_labels = {"replace": "Modified", "insert": "Added", "delete": "Removed"}
        for idx, b in enumerate(subst[:60], 1):
            rows.append([
                str(idx),
                Paragraph((b.left_text or "—")[:350], body_st),
                Paragraph((b.right_text or "—")[:350], body_st),
                type_labels.get(b.type, b.type),
            ])
        story.append(_table(rows, col_widths=[0.3 * inch, 2.6 * inch, 2.6 * inch, 0.9 * inch], header_color="#166534"))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e5e7eb")))
    story.append(Paragraph(
        f"Generated by LawMate · Document Comparison · {result.comparison_id}",
        footer_st,
    ))

    doc_pdf.build(story)
    return buf.getvalue()


def _table(data: list, col_widths: list[float], header_color: str = "#1e40af", header_text_color: str = "#ffffff") -> Table:
    """Helper to build a styled ReportLab table."""
    t = Table(data, colWidths=col_widths)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(header_text_color)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]
    t.setStyle(TableStyle(style))
    return t
