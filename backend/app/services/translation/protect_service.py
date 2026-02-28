"""
Protect service — identifies legal entities that must survive translation
unchanged (case numbers, act citations, section references, dates, court
names, Latin phrases) and replaces them with opaque placeholders before
sending text to the LLM.  After translation the placeholders are restored.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# ── Regex patterns ─────────────────────────────────────────────────────────

# Case numbers  e.g. "WP(C) No. 1234/2023", "CRL.A. 456/22", "O.P. No. 789 of 2021"
_CASE_NUMBER = re.compile(
    r"\b(?:[A-Z]{1,6}[\s.]?(?:\([A-Z]+\))?[\s.]*No\.?\s*\d+[\s/\-]+\d{2,4}|"
    r"[A-Z]{2,6}\.?[A-Z]{0,4}\.?\s*\d+\s*(?:of|/)\s*\d{2,4})\b",
    re.IGNORECASE,
)

# Section/article refs  e.g. "Section 302", "Sec. 420 IPC", "Art. 226", "Article 21"
_SECTION_REF = re.compile(
    r"\b(?:Section|Sec\.|Article|Art\.|Clause|S\.)\s*\d+(?:[A-Z])?(?:\s*\(\d+\))*"
    r"(?:\s+(?:of\s+the\s+)?(?:[A-Z][A-Za-z\s]+?Act|IPC|CrPC|CPC|IEA|POCSO|NDPS|IT Act))?",
    re.IGNORECASE,
)

# Act / statute names  e.g. "Indian Penal Code", "CrPC", "Motor Vehicles Act, 1988"
_ACT_NAME = re.compile(
    r"\b(?:Indian Penal Code|Code of Criminal Procedure|Civil Procedure Code|"
    r"Indian Evidence Act|Motor Vehicles Act|Arbitration and Conciliation Act|"
    r"Consumer Protection Act|Limitation Act|Transfer of Property Act|"
    r"Specific Relief Act|Contract Act|Negotiable Instruments Act|"
    r"Prevention of Corruption Act|Domestic Violence Act|Protection of Children|"
    r"POCSO|NDPS Act|IT Act|GST Act|Income Tax Act|"
    r"IPC|CrPC|CPC|IEA)\b"
    r"(?:,\s*\d{4})?",
    re.IGNORECASE,
)

# Date patterns  e.g. "12/03/2024", "March 12, 2024", "12th January 2023"
_DATE = re.compile(
    r"\b(?:\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{4})\b",
    re.IGNORECASE,
)

# Latin / untranslatable legal phrases
_LATIN = re.compile(
    r"\b(?:habeas corpus|mens rea|actus reus|prima facie|sub judice|res judicata|"
    r"obiter dicta|ratio decidendi|locus standi|amicus curiae|ex parte|ad interim|"
    r"suo motu|inter alia|viz\.|i\.e\.|e\.g\.|et al\.|ipso facto|ultra vires|"
    r"intra vires|bona fide|mala fide|pro bono|en banc|nemo dat|certiorari|"
    r"mandamus|prohibition|quo warranto)\b",
    re.IGNORECASE,
)

# Court names
_COURT_NAME = re.compile(
    r"\b(?:Supreme Court of India|Kerala High Court|High Court of Kerala|"
    r"District Court|Sessions Court|Magistrate Court|Family Court|"
    r"Consumer Forum|National Consumer Disputes Redressal Commission|NCDRC|"
    r"Debt Recovery Tribunal|National Green Tribunal|NGT|DRAT|DRT)\b",
    re.IGNORECASE,
)

# Ordered list of (pattern, label) — checked in order; earlier = higher priority
_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (_CASE_NUMBER,  "CASE"),
    (_COURT_NAME,   "COURT"),
    (_ACT_NAME,     "ACT"),
    (_SECTION_REF,  "SECT"),
    (_DATE,         "DATE"),
    (_LATIN,        "LAT"),
]

_PLACEHOLDER_RE = re.compile(r"__PROT_(\d{4})__")


@dataclass
class ProtectionMap:
    """Holds the mapping from placeholder → original text for one segment."""
    store: Dict[str, str] = field(default_factory=dict)
    counter: int = 0

    def add(self, original: str) -> str:
        key = f"__PROT_{self.counter:04d}__"
        self.store[key] = original
        self.counter += 1
        return key


class ProtectService:
    """
    Deterministic pre/post processor that shields legal entities from
    being mis-translated by the LLM.

    Usage
    -----
    protected_text, pmap = protect_service.protect_text(raw_text)
    # … send protected_text to LLM …
    restored_text = protect_service.restore_text(translated_text, pmap)
    """

    # ── Public API ─────────────────────────────────────────────────────────

    def protect_text(self, text: str) -> Tuple[str, ProtectionMap]:
        """
        Replace protected entities with placeholders.

        Returns (modified_text, ProtectionMap).
        """
        pmap = ProtectionMap()
        result = text

        # Collect all non-overlapping matches from all patterns, then replace
        # them from rightmost to leftmost so offsets stay valid.
        all_matches: List[Tuple[int, int, str]] = []  # (start, end, original)

        occupied: List[Tuple[int, int]] = []

        for pattern, _label in _PATTERNS:
            for m in pattern.finditer(result):
                s, e = m.start(), m.end()
                # Skip if already claimed by a higher-priority pattern
                if any(os_ <= s < oe or os_ < e <= oe for os_, oe in occupied):
                    continue
                all_matches.append((s, e, m.group()))
                occupied.append((s, e))

        # Sort rightmost first so we can do in-place substitution
        all_matches.sort(key=lambda x: x[0], reverse=True)

        for start, end, original in all_matches:
            placeholder = pmap.add(original)
            result = result[:start] + placeholder + result[end:]

        return result, pmap

    def restore_text(self, text: str, pmap: ProtectionMap) -> str:
        """Replace all __PROT_NNNN__ placeholders with their originals."""

        def _replacer(m: re.Match) -> str:
            key = m.group(0)
            return pmap.store.get(key, key)

        return _PLACEHOLDER_RE.sub(_replacer, text)

    def validate_protection(self, original: str, restored: str) -> List[str]:
        """
        Return a list of any entities that appear in *original* but are
        missing from *restored* (useful for logging / alerting).
        """
        issues: List[str] = []
        for pattern, label in _PATTERNS:
            for m in pattern.finditer(original):
                entity = m.group()
                if entity not in restored:
                    issues.append(f"[{label}] '{entity}' lost after restoration")
        return issues


# Module-level singleton
protect_service = ProtectService()
