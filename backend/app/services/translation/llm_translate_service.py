"""
LLM translation service — wraps AWS Bedrock converse() / converse_stream()
to translate legal text with glossary placeholder protection and KHC-specific
system prompts.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, Generator, List, Literal, Union

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from .glossary_service import glossary_service
from .protect_service import protect_service

logger = logging.getLogger(__name__)

Direction = Literal["en_to_ml", "ml_to_en"]

# Token budget
_MIN_TOKENS = 800
_TOKENS_PER_CHAR = 0.25       # rough chars-per-token for Malayalam/English mix
_EXPANSION_FACTOR = 1.5       # Malayalam text is ~1.5× longer than English


def _adaptive_max_tokens(source_text: str, max_cap: int) -> int:
    estimated = int(len(source_text) * _EXPANSION_FACTOR / _TOKENS_PER_CHAR)
    return max(_MIN_TOKENS, min(max_cap, estimated))


# ── KHC-specific system prompts (Task 5) ─────────────────────────────────

_EN_TO_ML_SYSTEM = """\
You are a senior certified legal translator at the Kerala High Court, \
Ernakulam Bench, with 20 years of experience translating English legal \
documents into formal Malayalam (Kerala legal style). Your translations \
appear in official court records and must be precise, formal, and consistent \
with Kerala High Court conventions.

TRANSLATION TASK
Translate the English legal text below into formal Malayalam.
Output ONLY the Malayalam translation — no headings, no explanation, no English.

══════════════════════════════════════════════
CRITICAL RULES — READ BEFORE TRANSLATING
══════════════════════════════════════════════

PLACEHOLDER PRESERVATION (HIGHEST PRIORITY — NEVER VIOLATE):
1. Every token matching __PROT_NNNN__ (four digits, e.g. __PROT_0001__) MUST
   appear verbatim in your output. These encode case numbers, act names, dates,
   and citations that must NEVER be translated or altered.
2. Every token matching <<GLOSS_N>> (e.g. <<GLOSS_3>>) MUST appear verbatim
   in your output. These are pre-resolved glossary terms — output them exactly
   and they will be restored automatically.
3. Do NOT invent, split, merge, or partially reproduce any placeholder token.
4. If a placeholder appears mid-sentence, place it at the grammatically correct
   position in the Malayalam sentence while keeping it VERBATIM.

STYLE RULES:
5. Use formal legal register (ഔദ്യോഗിക നിയമഭാഷ) throughout.
6. Preserve the original paragraph and line-break structure exactly.
7. Court orders use standard Malayalam phrasing:
   "is directed" → "നിർദ്ദേശിക്കപ്പെടുന്നു"
   "is hereby ordered" → "ഇതിനാൽ ഉത്തരവ് ആകുന്നു"
8. Do not add any text not present in the source.

EXAMPLE (showing correct placeholder handling):
  Source:  "The __PROT_0001__ directed the respondent to pay <<GLOSS_1>> \
within 30 days of the __PROT_0002__."
  Output:  "__PROT_0001__ പ്രതിഭാഗക്കാരോട് __PROT_0002__ ന്റെ 30 ദിവസത്തിനകം \
<<GLOSS_1>> നൽകാൻ നിർദ്ദേശിച്ചു."
  ✓ __PROT_0001__, __PROT_0002__, and <<GLOSS_1>> are preserved verbatim.\
"""

_ML_TO_EN_SYSTEM = """\
You are a senior certified legal translator at the Kerala High Court, \
Ernakulam Bench, with 20 years of experience translating Malayalam legal \
documents into formal English. Your translations appear in official court \
records and must be precise, formal, and consistent with Indian legal English.

TRANSLATION TASK
Translate the Malayalam legal text below into formal English.
Output ONLY the English translation — no headings, no explanation, no Malayalam.

══════════════════════════════════════════════
CRITICAL RULES — READ BEFORE TRANSLATING
══════════════════════════════════════════════

PLACEHOLDER PRESERVATION (HIGHEST PRIORITY — NEVER VIOLATE):
1. Every token matching __PROT_NNNN__ (four digits, e.g. __PROT_0001__) MUST
   appear verbatim in your output. These encode case numbers, act names, dates,
   and citations that must NEVER be translated or altered.
2. Every token matching <<GLOSS_N>> (e.g. <<GLOSS_3>>) MUST appear verbatim
   in your output. These are pre-resolved glossary terms — output them exactly
   and they will be restored automatically.
3. Do NOT invent, split, merge, or partially reproduce any placeholder token.
4. If a placeholder appears mid-sentence, place it at the grammatically correct
   position in the English sentence while keeping it VERBATIM.

STYLE RULES:
5. Use formal Indian legal English throughout.
6. Preserve the original paragraph and line-break structure exactly.
7. Court orders use standard phrasing:
   "ഉത്തരവ് ആകുന്നു" → "It is hereby ordered"
   "നിർദ്ദേശിക്കപ്പെടുന്നു" → "is directed"
8. Do not add any text not present in the source.

EXAMPLE (showing correct placeholder handling):
  Source:  "__PROT_0001__ ഹർജ്ജിക്കാരനോട് __PROT_0002__ ന്റെ 30 ദിവസത്തിനകം \
<<GLOSS_1>> നൽകാൻ നിർദ്ദേശിച്ചു."
  Output:  "__PROT_0001__ directed the petitioner to pay <<GLOSS_1>> within \
30 days of __PROT_0002__."
  ✓ __PROT_0001__, __PROT_0002__, and <<GLOSS_1>> are preserved verbatim.\
"""


def _build_system_prompt(direction: Direction, glossary_block: str) -> str:
    base = _EN_TO_ML_SYSTEM if direction == "en_to_ml" else _ML_TO_EN_SYSTEM
    if glossary_block:
        return (
            base
            + "\n\nADDITIONAL GLOSSARY HINTS (also translate these exactly):\n"
            + glossary_block
        )
    return base


def _build_retry_system_prompt(
    direction: Direction,
    glossary_block: str,
    missing: List[str],
    term_map: Dict[str, str],
) -> str:
    """Build an emphatic retry prompt that calls out each missing placeholder."""
    base = _build_system_prompt(direction, glossary_block)
    missing_lines = "\n".join(
        f"  {ph}  (target: {term_map.get(ph, '?')})" for ph in missing
    )
    correction = (
        "\n\n"
        "⚠ CORRECTION REQUIRED ⚠\n"
        "Your previous translation was missing these placeholder tokens:\n"
        f"{missing_lines}\n"
        "You MUST include EVERY <<GLOSS_N>> and __PROT_NNNN__ token verbatim. "
        "Re-translate the complete text ensuring no placeholder is omitted."
    )
    return base + correction


# ── Validation helpers ────────────────────────────────────────────────────

def _validate_glossary_placeholders(
    translated: str, term_map: Dict[str, str]
) -> List[str]:
    """Return the list of <<GLOSS_N>> placeholders absent from *translated*."""
    return [ph for ph in term_map if ph not in translated]


# Matches any LLM preamble the model adds before the actual translation,
# e.g. "Here is the formal English translation of the Malayalam legal text:"
# or "Translation:" or "Here is the Malayalam translation:\n\n"
_PREAMBLE_RE = re.compile(
    r"^(?:"
    r"here\s+is\s+(?:the\s+)?(?:formal\s+)?(?:\w+\s+)*translation[^:\n]*[:\-]\s*"
    r"|translation[:\-]\s*"
    r"|(?:formal\s+)?(?:english|malayalam)\s+translation[^:\n]*[:\-]\s*"
    r")\n*",
    re.IGNORECASE,
)


def _strip_preamble(text: str) -> str:
    """Remove boilerplate preamble lines the LLM sometimes prepends."""
    stripped = _PREAMBLE_RE.sub("", text.lstrip())
    if stripped != text:
        logger.debug("_strip_preamble: removed LLM preamble from translation output")
    return stripped


# ── Service ───────────────────────────────────────────────────────────────

class LLMTranslateService:
    """Stateless (except for the Bedrock client) translation service."""

    def __init__(self) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    # ── Low-level Bedrock helpers ─────────────────────────────────────────

    def _call_bedrock(
        self,
        text: str,
        system_prompt: str,
        direction: Direction,
        model_id: str | None = None,
    ) -> str:
        """Single synchronous Bedrock Converse call; returns translated text."""
        model = model_id or settings.LEGAL_TRANSLATE_MODEL_ID
        max_tokens = _adaptive_max_tokens(text, settings.LEGAL_TRANSLATE_MAX_TOKENS)
        response = self._client.converse(
            modelId=model,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": text}]}],
            inferenceConfig={
                "temperature": settings.LEGAL_TRANSLATE_TEMPERATURE,
                "maxTokens": max_tokens,
            },
        )
        raw = response["output"]["message"]["content"][0]["text"].strip()
        return _strip_preamble(raw)

    def _translate_with_retry(
        self,
        tokenized: str,
        system_prompt: str,
        direction: Direction,
        term_map: Dict[str, str],
        hint_block: str,
        model_id: str | None = None,
    ) -> str:
        """
        Call Bedrock, then validate <<GLOSS_N>> placeholders.
        If any are missing, retry once with an emphatic prompt.
        Returns the translated tokenized string (still contains <<GLOSS_N>>).
        """
        translated = self._call_bedrock(tokenized, system_prompt, direction, model_id)

        if term_map:
            missing = _validate_glossary_placeholders(translated, term_map)
            if missing:
                logger.warning(
                    "llm_translate: %d <<GLOSS_N>> missing after translation: %s — retrying",
                    len(missing), missing,
                )
                retry_prompt = _build_retry_system_prompt(
                    direction, hint_block, missing, term_map
                )
                translated = self._call_bedrock(
                    tokenized, retry_prompt, direction, model_id
                )
                still_missing = _validate_glossary_placeholders(translated, term_map)
                if still_missing:
                    logger.error(
                        "llm_translate: placeholders still missing after retry: %s",
                        still_missing,
                    )

        return translated

    # ── Public API ────────────────────────────────────────────────────────

    def translate_chunk(
        self,
        text: str,
        direction: Direction,
        model_id: str | None = None,
    ) -> str:
        """
        Translate a single text chunk using the full placeholder pipeline.

        The caller may pass already-entity-protected text (containing
        __PROT_NNNN__ tokens).  This method additionally:
          1. Replaces glossary terms with <<GLOSS_N>> placeholders.
          2. Translates via Bedrock (with retry on placeholder loss).
          3. Restores glossary placeholders.

        The caller is responsible for restoring __PROT_NNNN__ tokens afterwards.

        Returns
        -------
        Translated text with __PROT_NNNN__ tokens intact.
        """
        if not text.strip():
            return text

        # 1. Glossary placeholder replacement
        tokenized, term_map = glossary_service.replace_with_placeholders(text, direction)

        # 2. Hint block for terms NOT captured as placeholders
        hint_block = glossary_service.get_subset_for_prompt(
            tokenized, direction, max_terms=10
        )

        # 3. Build system prompt
        system_prompt = _build_system_prompt(direction, hint_block)

        try:
            # 4. Translate with placeholder validation + retry
            translated = self._translate_with_retry(
                tokenized, system_prompt, direction, term_map, hint_block, model_id
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("Bedrock translation failed: %s", exc)
            raise RuntimeError(f"LLM translation error: {exc}") from exc

        # 5. Restore glossary placeholders
        if term_map:
            translated = glossary_service.restore_placeholders(translated, term_map)

        return translated

    def translate_text(self, text: str, direction: Direction) -> dict:
        """
        Full pipeline for a plain-text input:
          1. Protect entities (__PROT_NNNN__)
          2. Replace glossary terms (<<GLOSS_N>>)
          3. Build prompt with remaining glossary hints (max 10)
          4. Translate via Bedrock (with retry on placeholder loss)
          5. Restore glossary placeholders
          6. Restore entity placeholders
          7. Validate protection

        Returns
        -------
        {
          "translated"    : str,
          "warnings"      : list[str],
          "glossary_hits" : int,
          "glossary_terms": list[{"source": str, "target": str}],
        }
        """
        # 1. Protect entities
        protected, pmap = protect_service.protect_text(text)

        # 2. Glossary placeholder replacement
        tokenized, term_map = glossary_service.replace_with_placeholders(
            protected, direction
        )

        # 3. Hint block for remaining non-placeholder terms
        hint_block = glossary_service.get_subset_for_prompt(
            tokenized, direction, max_terms=10
        )

        # 4. Translate
        system_prompt = _build_system_prompt(direction, hint_block)
        try:
            translated = self._translate_with_retry(
                tokenized, system_prompt, direction, term_map, hint_block
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("Bedrock translation failed: %s", exc)
            raise RuntimeError(f"LLM translation error: {exc}") from exc

        # 5. Restore glossary placeholders
        if term_map:
            translated = glossary_service.restore_placeholders(translated, term_map)

        # 6. Restore entity placeholders
        restored = protect_service.restore_text(translated, pmap)

        # 7. Validate entity protection
        warnings = protect_service.validate_protection(text, restored)
        if warnings:
            logger.warning("Protection validation issues: %s", warnings)

        # Build glossary_terms list for frontend highlighting
        # find_matches on original text gives us (source, target) pairs
        source_matches = glossary_service.find_matches(text, direction)
        glossary_terms = [
            {"source": src, "target": tgt} for src, tgt in source_matches
        ]

        return {
            "translated": restored,
            "warnings": warnings,
            "glossary_hits": len(source_matches),
            "glossary_terms": glossary_terms,
        }

    def stream_translate_text(
        self, text: str, direction: Direction
    ) -> Generator[Union[str, dict], None, None]:
        """
        Generator that streams the translation using Bedrock converse_stream.

        Yields
        ------
        str  — raw translated text chunks as they arrive (may contain <<GLOSS_N>>
               and __PROT_NNNN__ tokens; shown as a live preview)
        dict — final event: {"done": True, "full_text": str (fully restored),
               "warnings": list[str], "glossary_hits": int,
               "glossary_terms": list[{"source", "target"}],
               "direction": str}

        The caller must handle both types and send them as SSE events.
        """
        # 1. Protect entities
        protected, pmap = protect_service.protect_text(text)

        # 2. Glossary placeholder replacement
        tokenized, term_map = glossary_service.replace_with_placeholders(
            protected, direction
        )

        # 3. Build prompt
        hint_block = glossary_service.get_subset_for_prompt(
            tokenized, direction, max_terms=10
        )
        system_prompt = _build_system_prompt(direction, hint_block)
        model = settings.LEGAL_TRANSLATE_MODEL_ID
        max_tokens = _adaptive_max_tokens(text, settings.LEGAL_TRANSLATE_MAX_TOKENS)

        # 4. Stream from Bedrock
        try:
            response = self._client.converse_stream(
                modelId=model,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": tokenized}]}],
                inferenceConfig={
                    "temperature": settings.LEGAL_TRANSLATE_TEMPERATURE,
                    "maxTokens": max_tokens,
                },
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("Bedrock stream translation failed: %s", exc)
            raise RuntimeError(f"LLM stream translation error: {exc}") from exc

        full_translated = ""
        stream = response.get("stream")
        if stream:
            for event in stream:
                if "contentBlockDelta" in event:
                    chunk_text = (
                        event["contentBlockDelta"]
                        .get("delta", {})
                        .get("text", "")
                    )
                    if chunk_text:
                        full_translated += chunk_text
                        yield chunk_text   # raw chunk — client shows as live preview

        # Strip any preamble the model emitted at the start of the stream
        full_translated = _strip_preamble(full_translated)

        # 5. Validate glossary placeholders; retry synchronously if needed
        if term_map:
            missing = _validate_glossary_placeholders(full_translated, term_map)
            if missing:
                logger.warning(
                    "stream_translate: %d <<GLOSS_N>> missing — doing sync retry",
                    len(missing),
                )
                try:
                    retry_prompt = _build_retry_system_prompt(
                        direction, hint_block, missing, term_map
                    )
                    full_translated = self._call_bedrock(
                        tokenized, retry_prompt, direction
                    )
                except (BotoCoreError, ClientError) as exc:
                    logger.error("Bedrock retry failed: %s", exc)

        # 6. Restore glossary placeholders
        if term_map:
            full_translated = glossary_service.restore_placeholders(
                full_translated, term_map
            )

        # 7. Restore entity placeholders
        full_restored = protect_service.restore_text(full_translated, pmap)

        # 8. Validate
        warnings = protect_service.validate_protection(text, full_restored)

        source_matches = glossary_service.find_matches(text, direction)
        glossary_terms = [
            {"source": src, "target": tgt} for src, tgt in source_matches
        ]

        yield {
            "done": True,
            "full_text": full_restored,
            "warnings": warnings,
            "glossary_hits": len(source_matches),
            "glossary_terms": glossary_terms,
            "direction": direction,
        }


# Module-level singleton
llm_translate_service = LLMTranslateService()
