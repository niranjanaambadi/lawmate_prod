"""
Glossary service — loads legal_glossary.json once at startup, builds
bidirectional indexes sorted longest-match-first, and provides fast
term lookup and placeholder replacement helpers for the translation pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class GlossaryService:
    """
    Singleton that owns the in-memory legal glossary.

    Attributes
    ----------
    _en_to_ml  : dict[str, str]  lowercase English → Malayalam
    _ml_to_en  : dict[str, str]  Malayalam → English
    _en_terms  : list[str]       English terms sorted by length DESC (longest first)
    _ml_terms  : list[str]       Malayalam terms sorted by length DESC
    _categories: dict[str, str]  lowercase English → category label
    """

    def __init__(self) -> None:
        self._en_to_ml: Dict[str, str] = {}
        self._ml_to_en: Dict[str, str] = {}
        self._en_terms: List[str] = []   # already-lowercase keys
        self._ml_terms: List[str] = []
        self._categories: Dict[str, str] = {}  # lowercase EN → category label
        self._loaded = False

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self, path: str | None = None) -> None:
        """Load the glossary JSON file.  Called once at startup."""
        if path is None:
            try:
                from app.core.config import settings
                configured = (settings.LEGAL_GLOSSARY_PATH or "").strip()
            except Exception:
                configured = ""
            if configured:
                path = configured
            else:
                base = Path(__file__).parent.parent.parent.parent.parent  # …/backend
                path = str(base / "legal_glossary.json")

        if not os.path.exists(path):
            logger.warning("legal_glossary.json not found at %s — glossary disabled", path)
            self._loaded = True
            return

        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            logger.error("Failed to load legal_glossary.json: %s", exc)
            self._loaded = True
            return

        terms: List[dict] = data.get("terms", [])

        # ── Validation pass ────────────────────────────────────────────────
        seen_en: Dict[str, int] = {}   # lowercase EN → first occurrence index
        empty_count = 0
        short_count = 0
        dup_count = 0

        for i, entry in enumerate(terms):
            en = (entry.get("en") or "").strip()
            ml = (entry.get("ml") or "").strip()

            if not en or not ml:
                empty_count += 1
                logger.debug("glossary: empty entry #%d — skipping", i)
                continue

            en_key = en.lower()

            if len(en_key) < 2 or len(ml) < 2:
                short_count += 1
                logger.debug(
                    "glossary: suspiciously short entry #%d: en=%r ml=%r — skipping",
                    i, en, ml,
                )
                continue

            if en_key in seen_en:
                dup_count += 1
                logger.debug(
                    "glossary: duplicate EN entry %r (first at #%d, again at #%d) — keeping first",
                    en, seen_en[en_key], i,
                )
                continue

            seen_en[en_key] = i
            self._en_to_ml[en_key] = ml
            self._ml_to_en[ml] = en

            category = (entry.get("category") or "").strip()
            if category:
                self._categories[en_key] = category

        if empty_count:
            logger.warning("glossary: %d entries skipped (empty EN or ML)", empty_count)
        if short_count:
            logger.warning(
                "glossary: %d entries skipped (< 2 chars — likely corrupt)", short_count
            )
        if dup_count:
            logger.warning(
                "glossary: %d duplicate EN entries skipped (kept first occurrence)", dup_count
            )

        # Sort longest-first so multi-word phrases are matched before substrings
        self._en_terms = sorted(self._en_to_ml.keys(), key=len, reverse=True)
        self._ml_terms = sorted(self._ml_to_en.keys(), key=len, reverse=True)
        self._loaded = True
        logger.info(
            "Legal glossary loaded: %d EN→ML entries, %d ML→EN entries "
            "(%d categories, %d dups / %d short / %d empty skipped)",
            len(self._en_to_ml), len(self._ml_to_en),
            len(self._categories), dup_count, short_count, empty_count,
        )

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ── Public API ────────────────────────────────────────────────────────────

    def find_matches(self, text: str, direction: str) -> List[Tuple[str, str]]:
        """
        Return a list of (source_term, target_term) pairs found in *text*.
        Only the first occurrence of each term is returned; longer matches
        take priority (thanks to the longest-first ordering).

        Parameters
        ----------
        text      : input text to scan
        direction : "en_to_ml" | "ml_to_en"
        """
        self._ensure_loaded()

        if direction == "en_to_ml":
            source_terms = self._en_terms
            mapping = self._en_to_ml
            text_lower = text.lower()
        else:
            source_terms = self._ml_terms
            mapping = self._ml_to_en
            text_lower = text

        matches: List[Tuple[str, str]] = []
        seen_spans: List[Tuple[int, int]] = []

        for term in source_terms:
            search_in = text_lower if direction == "en_to_ml" else text
            pos = search_in.find(term)
            if pos == -1:
                continue
            end = pos + len(term)
            if any(s <= pos < e or s < end <= e for s, e in seen_spans):
                continue
            seen_spans.append((pos, end))
            matches.append((term, mapping[term]))

        return matches

    def replace_with_placeholders(
        self, text: str, direction: str
    ) -> Tuple[str, Dict[str, str]]:
        """
        Scan *text* for glossary matches and replace them with deterministic
        ``<<GLOSS_N>>`` tokens (N starts at 1, increments per unique matched term).

        Each unique matched term gets one placeholder; ALL occurrences of that
        term in the text are replaced with the same placeholder.  Longest terms
        are matched first to prevent sub-term clobbering.

        Parameters
        ----------
        text      : source text (may already contain __PROT_NNNN__ tokens)
        direction : "en_to_ml" | "ml_to_en"

        Returns
        -------
        (tokenized_text, term_map)
            tokenized_text — text with glossary terms replaced by ``<<GLOSS_N>>``
            term_map       — ``{placeholder: target_language_translation}``
        """
        self._ensure_loaded()

        if direction == "en_to_ml":
            source_terms = self._en_terms   # sorted longest-first, lowercase
            mapping = self._en_to_ml
        else:
            source_terms = self._ml_terms
            mapping = self._ml_to_en

        term_map: Dict[str, str] = {}
        result = text
        counter = 1

        for term in source_terms:
            if direction == "en_to_ml":
                # Quick pre-check before expensive regex
                if term not in result.lower():
                    continue
                placeholder = f"<<GLOSS_{counter}>>"
                # Word-boundary replacement, case-insensitive for English
                result = re.sub(
                    r"\b" + re.escape(term) + r"\b",
                    placeholder,
                    result,
                    flags=re.IGNORECASE,
                )
            else:
                if term not in result:
                    continue
                placeholder = f"<<GLOSS_{counter}>>"
                result = result.replace(term, placeholder)

            term_map[placeholder] = mapping[term]
            counter += 1

        return result, term_map

    def restore_placeholders(self, translated: str, term_map: Dict[str, str]) -> str:
        """
        Replace ``<<GLOSS_N>>`` tokens in *translated* with their target-language
        equivalents from *term_map*.
        """
        for placeholder, target in term_map.items():
            translated = translated.replace(placeholder, target)
        return translated

    def get_subset_for_prompt(
        self, text: str, direction: str, max_terms: int = 10
    ) -> str:
        """
        Build a compact glossary hint block (≤ max_terms entries) to inject
        into the LLM system prompt.  Only terms actually present in *text*
        are included.

        Call this on the *tokenized* text (after ``replace_with_placeholders``)
        to get hints for terms that were **not** converted to placeholders
        (e.g. terms that appear in slightly different forms).

        Returns an empty string if no matches are found.
        """
        matches = self.find_matches(text, direction)[:max_terms]
        if not matches:
            return ""
        if direction == "en_to_ml":
            lines = [f"{src} → {tgt}" for src, tgt in matches]
            header = "English → Malayalam legal glossary (use these translations exactly):"
        else:
            lines = [f"{src} → {tgt}" for src, tgt in matches]
            header = "Malayalam → English legal glossary (use these translations exactly):"
        return header + "\n" + "\n".join(lines)


# Module-level singleton
glossary_service = GlossaryService()
