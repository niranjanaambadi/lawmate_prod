"""
Glossary service — loads legal_glossary.json once at startup, builds
bidirectional indexes sorted longest-match-first, and provides fast
term lookup helpers for the translation pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class GlossaryService:
    """
    Singleton that owns the in-memory legal glossary.

    Attributes
    ----------
    _en_to_ml : dict[str, str]  lowercase English → Malayalam
    _ml_to_en : dict[str, str]  Malayalam → English
    _en_terms  : list[str]      English terms sorted by length DESC (longest first)
    _ml_terms  : list[str]      Malayalam terms sorted by length DESC
    """

    def __init__(self) -> None:
        self._en_to_ml: Dict[str, str] = {}
        self._ml_to_en: Dict[str, str] = {}
        self._en_terms: List[str] = []   # already-lowercase keys
        self._ml_terms: List[str] = []
        self._loaded = False

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self, path: str | None = None) -> None:
        """Load the glossary JSON file.  Called once at startup."""
        if path is None:
            # Use settings override if set, otherwise auto-resolve from backend root
            try:
                from app.core.config import settings
                configured = (settings.LEGAL_GLOSSARY_PATH or "").strip()
            except Exception:
                configured = ""
            if configured:
                path = configured
            else:
                # Resolve relative to the backend root (two levels above this file)
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
        for entry in terms:
            en = (entry.get("en") or "").strip()
            ml = (entry.get("ml") or "").strip()
            if en and ml:
                self._en_to_ml[en.lower()] = ml
                self._ml_to_en[ml] = en

        # Sort longest-first so multi-word phrases are matched before substrings
        self._en_terms = sorted(self._en_to_ml.keys(), key=len, reverse=True)
        self._ml_terms = sorted(self._ml_to_en.keys(), key=len, reverse=True)
        self._loaded = True
        logger.info(
            "Legal glossary loaded: %d EN→ML, %d ML→EN entries",
            len(self._en_to_ml), len(self._ml_to_en),
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
            text_lower = text  # Malayalam is case-insensitive by default

        matches: List[Tuple[str, str]] = []
        seen_spans: List[Tuple[int, int]] = []

        for term in source_terms:
            # Case-insensitive search for EN; exact for ML
            search_in = text_lower if direction == "en_to_ml" else text
            pos = search_in.find(term)
            if pos == -1:
                continue
            end = pos + len(term)
            # Avoid overlapping with an already-matched span
            if any(s <= pos < e or s < end <= e for s, e in seen_spans):
                continue
            seen_spans.append((pos, end))
            matches.append((term, mapping[term]))

        return matches

    def get_subset_for_prompt(
        self, text: str, direction: str, max_terms: int = 30
    ) -> str:
        """
        Build a compact glossary block (≤ max_terms entries) to inject into
        the LLM system prompt.  Only terms actually present in *text* are
        included so we don't pollute the prompt with irrelevant noise.

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
