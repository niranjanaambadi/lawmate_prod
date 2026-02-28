"""
LLM service for Legal Insight: prompts Bedrock to summarize judgments
with strict citation_ids that map to extracted chunk_ids.
Handles long documents via map-reduce.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

import boto3

from app.core.config import settings
from app.core.logger import logger


SYSTEM_PROMPT_V1 = """You are an expert legal summarizer for Indian courts (Kerala High Court, Supreme Court of India).
Your task: analyze judgment text chunks and produce a structured JSON summary.

STRICT RULES:
1. Output ONLY valid JSON — no markdown, no preamble, no trailing text.
2. Every item MUST include non-empty "citation_ids" referencing the provided chunk_ids.
3. Never invent or hallucinate citation_ids — only use IDs from the chunks provided.
4. If uncertain about an item, still cite the best-matching chunk(s).
5. Do not reproduce large verbatim quotes — paraphrase in 1-3 sentences.
6. Never hallucinate case law, statutes, or facts not present in the chunks."""


class LegalInsightLlmService:
    """Summarizes Indian court judgments via AWS Bedrock (Claude)."""

    def __init__(self) -> None:
        raw_model = (
            getattr(settings, "LEGAL_INSIGHT_MODEL_ID", "") or settings.BEDROCK_MODEL_ID
        )
        self.model: str = raw_model.strip()
        self.max_chars: int = int(
            getattr(settings, "LEGAL_INSIGHT_MAX_CHARS_PER_CHUNK", 3000)
        )
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        logger.info("LegalInsightLlmService initialised with model=%s", self.model)

    # ------------------------------------------------------------------
    # Low-level Bedrock call
    # ------------------------------------------------------------------

    def _invoke(self, prompt: str, max_tokens: int = 8192) -> str:
        """
        Call Bedrock with *prompt* and return the assistant's text response.
        """
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        response = self.client.invoke_model(
            modelId=self.model,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        result = json.loads(response["body"].read())
        # Claude response: {"content": [{"type": "text", "text": "..."}], ...}
        content = result.get("content", [])
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        return "".join(text_parts)

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------

    def _build_chunk_context(self, chunks: list[dict]) -> str:
        """
        Serialise chunks into a compact JSON string for inclusion in prompts.
        Truncates each chunk's text to 500 characters to stay within token limits.
        """
        slim = [
            {
                "chunk_id": c["chunk_id"],
                "page_number": c["page_number"],
                "text": c["text"][:500],
            }
            for c in chunks
        ]
        return json.dumps(slim, ensure_ascii=False)

    def _build_summarize_prompt(
        self, chunk_context: str, valid_ids: list[str]
    ) -> str:
        """
        Build the full user prompt for a single-pass or batch summarization call.
        """
        return (
            f"{SYSTEM_PROMPT_V1}\n\n"
            f"Judgment chunks (cite these IDs only — {valid_ids}):\n"
            f"{chunk_context}\n\n"
            "Return ONLY this JSON structure:\n"
            "{\n"
            '  "facts": [{"text": "...", "citation_ids": ["chunk_000001"]}],\n'
            '  "issues": [{"text": "...", "citation_ids": ["chunk_000010"]}],\n'
            '  "arguments": [{"text": "...", "citation_ids": ["chunk_000022"]}],\n'
            '  "ratio": [{"text": "...", "citation_ids": ["chunk_000041"]}],\n'
            '  "final_order": [{"text": "...", "citation_ids": ["chunk_000055"]}]\n'
            "}"
        )

    # ------------------------------------------------------------------
    # Output validation
    # ------------------------------------------------------------------

    def _validate_output(
        self, data: dict, valid_chunk_ids: set[str]
    ) -> tuple[bool, str]:
        """
        Validate the LLM's JSON output against required structure and citation rules.

        Returns (True, "") if valid, or (False, <error_message>) otherwise.
        """
        required_keys = {"facts", "issues", "arguments", "ratio", "final_order"}
        missing = required_keys - data.keys()
        if missing:
            return False, f"Missing required sections: {missing}"

        for section in required_keys:
            items = data[section]
            if not isinstance(items, list):
                return False, f"Section '{section}' must be a list"
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    return False, f"Section '{section}'[{idx}] must be a dict"
                text = item.get("text", "")
                if not isinstance(text, str) or not text.strip():
                    return (
                        False,
                        f"Section '{section}'[{idx}] has empty or missing 'text'",
                    )
                citation_ids = item.get("citation_ids", [])
                if not isinstance(citation_ids, list) or len(citation_ids) == 0:
                    return (
                        False,
                        f"Section '{section}'[{idx}] has empty or missing 'citation_ids'",
                    )
                for cid in citation_ids:
                    if cid not in valid_chunk_ids:
                        return (
                            False,
                            f"Section '{section}'[{idx}] references unknown chunk_id '{cid}'",
                        )

        return True, ""

    # ------------------------------------------------------------------
    # Single-batch summarization
    # ------------------------------------------------------------------

    def _summarize_batch(self, chunks: list[dict]) -> dict:
        """
        Send *chunks* to Bedrock and parse the structured JSON response.
        Raises ValueError if the response cannot be parsed as JSON.
        """
        chunk_context = self._build_chunk_context(chunks)
        valid_ids = [c["chunk_id"] for c in chunks]
        prompt = self._build_summarize_prompt(chunk_context, valid_ids)

        logger.info(
            "_summarize_batch: sending %d chunks to Bedrock (model=%s)",
            len(chunks),
            self.model,
        )
        raw_text = self._invoke(prompt, max_tokens=8192)

        # Extract JSON object from the response (guards against stray whitespace /
        # accidental preamble lines)
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not match:
            raise ValueError(
                f"LLM did not return a JSON object. Raw response: {raw_text[:500]}"
            )

        try:
            parsed: dict = json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Failed to parse LLM JSON response: {exc}. "
                f"Raw: {raw_text[:500]}"
            ) from exc

        return parsed

    # ------------------------------------------------------------------
    # Map-reduce synthesis prompt
    # ------------------------------------------------------------------

    def _build_synthesis_prompt(
        self,
        partial_summaries: list[dict],
        all_chunk_ids: list[str],
    ) -> str:
        """
        Build a consolidation prompt from multiple partial summaries produced in
        the map phase of map-reduce summarization.
        """
        synthesis_input = json.dumps(partial_summaries, ensure_ascii=False)
        return (
            f"{SYSTEM_PROMPT_V1}\n\n"
            "You have received multiple partial summaries from different sections of a "
            "long judgment. Consolidate them into a single coherent JSON summary.\n\n"
            f"Valid chunk IDs for citations (use ONLY these): {all_chunk_ids}\n\n"
            "Partial summaries to consolidate:\n"
            f"{synthesis_input}\n\n"
            "Return ONLY this JSON structure (merge and deduplicate items across all "
            "partial summaries, preserving the most informative ones):\n"
            "{\n"
            '  "facts": [{"text": "...", "citation_ids": ["chunk_000001"]}],\n'
            '  "issues": [{"text": "...", "citation_ids": ["chunk_000010"]}],\n'
            '  "arguments": [{"text": "...", "citation_ids": ["chunk_000022"]}],\n'
            '  "ratio": [{"text": "...", "citation_ids": ["chunk_000041"]}],\n'
            '  "final_order": [{"text": "...", "citation_ids": ["chunk_000055"]}]\n'
            "}"
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def summarize(
        self,
        chunks: list[dict],
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> dict:
        """
        Summarize *chunks* and return a validated dict with sections:
            facts, issues, arguments, ratio, final_order

        Uses single-pass if len(chunks) <= MODEL_WINDOW, otherwise map-reduce.

        *on_progress* is called with an integer (0-100) at key milestones.
        """
        MODEL_WINDOW = 60  # max chunks per single Bedrock call
        valid_chunk_ids: set[str] = {c["chunk_id"] for c in chunks}
        all_chunk_ids: list[str] = [c["chunk_id"] for c in chunks]

        def _progress(pct: int) -> None:
            if on_progress is not None:
                try:
                    on_progress(pct)
                except Exception:
                    pass  # never crash on progress callback errors

        # ------------------------------------------------------------------
        # Single-pass
        # ------------------------------------------------------------------
        if len(chunks) <= MODEL_WINDOW:
            logger.info(
                "summarize: single-pass mode (%d chunks)", len(chunks)
            )
            _progress(10)
            result = self._summarize_batch(chunks)
            _progress(70)
            ok, err = self._validate_output(result, valid_chunk_ids)
            if not ok:
                logger.warning(
                    "First pass validation failed (%s), retrying once", err
                )
                result = self._summarize_batch(chunks)
                ok, err = self._validate_output(result, valid_chunk_ids)
                if not ok:
                    raise ValueError(
                        f"LLM output failed validation after retry: {err}"
                    )
            _progress(100)
            return result

        # ------------------------------------------------------------------
        # Map-reduce
        # ------------------------------------------------------------------
        logger.info(
            "summarize: map-reduce mode (%d chunks, window=%d)",
            len(chunks),
            MODEL_WINDOW,
        )
        batches = [
            chunks[i : i + MODEL_WINDOW]
            for i in range(0, len(chunks), MODEL_WINDOW)
        ]
        n_batches = len(batches)

        partial_summaries: list[dict] = []
        for batch_idx, batch in enumerate(batches):
            logger.info(
                "Map phase: batch %d/%d (%d chunks)",
                batch_idx + 1,
                n_batches,
                len(batch),
            )
            try:
                partial = self._summarize_batch(batch)
                partial_summaries.append(partial)
            except Exception as exc:
                logger.warning(
                    "Map batch %d failed: %s — skipping", batch_idx + 1, exc
                )
            progress_pct = int(10 + (batch_idx + 1) / n_batches * 60)
            _progress(progress_pct)

        if not partial_summaries:
            raise ValueError("All map batches failed — cannot produce a summary")

        # ---- Reduce / synthesis -----------------------------------------
        logger.info("Reduce phase: synthesising %d partial summaries", len(partial_summaries))
        _progress(75)
        synthesis_prompt = self._build_synthesis_prompt(partial_summaries, all_chunk_ids)
        raw_synthesis = self._invoke(synthesis_prompt, max_tokens=8192)

        match = re.search(r"\{.*\}", raw_synthesis, re.DOTALL)
        if not match:
            raise ValueError(
                f"Synthesis LLM did not return a JSON object. "
                f"Raw: {raw_synthesis[:500]}"
            )
        try:
            final: dict = json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Failed to parse synthesis JSON: {exc}. "
                f"Raw: {raw_synthesis[:500]}"
            ) from exc

        _progress(90)
        ok, err = self._validate_output(final, valid_chunk_ids)
        if not ok:
            raise ValueError(
                f"Synthesised output failed validation: {err}"
            )

        _progress(100)
        return final


# Singleton
legal_insight_llm_service = LegalInsightLlmService()
