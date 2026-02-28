"""
LLM translation service — wraps AWS Bedrock converse() to translate
one text chunk at a time with legal glossary injection.
"""
from __future__ import annotations

import logging
from typing import Literal

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from .glossary_service import glossary_service
from .protect_service import protect_service

logger = logging.getLogger(__name__)

Direction = Literal["en_to_ml", "ml_to_en"]

# Token budget: never request fewer than 800 or more than the configured cap.
_MIN_TOKENS = 800
_TOKENS_PER_CHAR = 0.25        # rough chars-per-token for Malayalam/English mix
_EXPANSION_FACTOR = 1.5        # Malayalam text is ~1.5× longer than English


def _adaptive_max_tokens(source_text: str, max_cap: int) -> int:
    estimated = int(len(source_text) * _EXPANSION_FACTOR / _TOKENS_PER_CHAR)
    return max(_MIN_TOKENS, min(max_cap, estimated))


def _build_system_prompt(direction: Direction, glossary_block: str) -> str:
    if direction == "en_to_ml":
        lang_instruction = (
            "You are a certified legal translator specialising in Kerala High Court "
            "proceedings. Translate the following English legal text into formal "
            "Malayalam (Kerala legal style). "
            "Output ONLY the translated Malayalam text — no explanation, no "
            "commentary, no English."
        )
    else:
        lang_instruction = (
            "You are a certified legal translator specialising in Kerala High Court "
            "proceedings. Translate the following Malayalam legal text into formal "
            "English (standard legal style). "
            "Output ONLY the translated English text — no explanation, no "
            "commentary, no Malayalam."
        )

    rules = (
        "\n\nCritical rules:\n"
        "1. Preserve ALL placeholder tokens of the form __PROT_NNNN__ exactly — "
        "do NOT translate, skip, or paraphrase them.\n"
        "2. Use the provided glossary terms exactly as given.\n"
        "3. Maintain the original paragraph and line-break structure.\n"
        "4. Do not add any text that is not present in the source.\n"
        "5. Use formal legal register throughout."
    )

    if glossary_block:
        return lang_instruction + "\n\n" + glossary_block + rules
    return lang_instruction + rules


class LLMTranslateService:
    """
    Stateless (except for the Bedrock client) translation service.
    """

    def __init__(self) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    # ── Public API ────────────────────────────────────────────────────────

    def translate_chunk(
        self,
        text: str,
        direction: Direction,
        model_id: str | None = None,
    ) -> str:
        """
        Translate a single text chunk (already protected with placeholders).

        Parameters
        ----------
        text       : protected text chunk
        direction  : "en_to_ml" | "ml_to_en"
        model_id   : override the default model from settings

        Returns
        -------
        Translated text with placeholders intact.
        """
        if not text.strip():
            return text

        model = model_id or settings.LEGAL_TRANSLATE_MODEL_ID
        glossary_block = glossary_service.get_subset_for_prompt(
            text, direction, max_terms=settings.LEGAL_TRANSLATE_MAX_SUBSET_TERMS
        )
        system_prompt = _build_system_prompt(direction, glossary_block)
        max_tokens = _adaptive_max_tokens(text, settings.LEGAL_TRANSLATE_MAX_TOKENS)

        try:
            response = self._client.converse(
                modelId=model,
                system=[{"text": system_prompt}],
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": text}],
                    }
                ],
                inferenceConfig={
                    "temperature": settings.LEGAL_TRANSLATE_TEMPERATURE,
                    "maxTokens": max_tokens,
                },
            )
            translated: str = (
                response["output"]["message"]["content"][0]["text"].strip()
            )
            return translated
        except (BotoCoreError, ClientError) as exc:
            logger.error("Bedrock translation failed: %s", exc)
            raise RuntimeError(f"LLM translation error: {exc}") from exc

    def translate_text(self, text: str, direction: Direction) -> dict:
        """
        Full pipeline for a plain-text input:
          1. Protect entities
          2. Translate via LLM
          3. Restore entities
          4. Validate

        Returns a dict with keys: translated, warnings, glossary_hits
        """
        protected, pmap = protect_service.protect_text(text)

        translated_protected = self.translate_chunk(protected, direction)

        restored = protect_service.restore_text(translated_protected, pmap)

        warnings = protect_service.validate_protection(text, restored)
        if warnings:
            logger.warning("Protection validation issues: %s", warnings)

        matches = glossary_service.find_matches(text, direction)
        return {
            "translated": restored,
            "warnings": warnings,
            "glossary_hits": len(matches),
        }


# Module-level singleton
llm_translate_service = LLMTranslateService()
