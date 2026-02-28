"""
services/judgment_ingestion_service.py

Ingests Kerala HC judgments from IndianKanoon into Bedrock Knowledge Base.

Called fire-and-forget from judgment_search.py after a live IndianKanoon
API hit — results are cached in Bedrock KB so future searches are free and fast.

Flow:
  1. Receive judgment list from IndianKanoon
  2. Fetch full document text for each judgment (IndianKanoon /doc/ endpoint)
  3. Chunk into overlapping segments
  4. Embed + store in Bedrock KB via S3 → KB sync

Bedrock KB ingestion model:
  - Documents stored as JSON in S3 (lawmate-judgments-kb bucket)
  - Bedrock KB data source points to that S3 prefix
  - After S3 write, trigger KB ingestion job to embed new docs

Environment variables:
  BEDROCK_KNOWLEDGE_BASE_ID    — KB ID for judgments
  BEDROCK_KB_DATA_SOURCE_ID    — data source ID within the KB
  JUDGMENT_KB_S3_BUCKET        — S3 bucket for judgment documents
  INDIANKANOON_API_TOKEN       — for fetching full document text
  AWS_REGION
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

INDIANKANOON_API_URL   = "https://api.indiankanoon.org"
INDIANKANOON_TOKEN     = os.getenv("INDIANKANOON_API_TOKEN", "")
JUDGMENT_KB_S3_BUCKET  = os.getenv("JUDGMENT_KB_S3_BUCKET", "lawmate-judgments-kb")
BEDROCK_KB_ID          = os.getenv("BEDROCK_KNOWLEDGE_BASE_ID", "")
BEDROCK_KB_DS_ID       = os.getenv("BEDROCK_KB_DATA_SOURCE_ID", "")
AWS_REGION             = os.getenv("AWS_REGION", "ap-south-1")

CHUNK_SIZE    = 800   # tokens per chunk (approximate — using word count)
CHUNK_OVERLAP = 150   # overlap between chunks for context continuity


# ============================================================================
# Public interface
# ============================================================================

async def ingest_judgments(
    judgments: list[dict],
    query:     str,
) -> dict:
    """
    Ingests a list of IndianKanoon judgment results into Bedrock KB.

    Args:
        judgments: List of judgment dicts from IndianKanoon search results.
                   Each dict has: title, citation, date, court, doc_id, source_url
        query:     The original search query (stored as metadata for context)

    Returns:
        { "ingested": int, "failed": int, "skipped": int }
    """
    if not BEDROCK_KB_ID or not JUDGMENT_KB_S3_BUCKET:
        logger.warning(
            "Judgment ingestion skipped — BEDROCK_KNOWLEDGE_BASE_ID or "
            "JUDGMENT_KB_S3_BUCKET not configured"
        )
        return {"ingested": 0, "failed": 0, "skipped": len(judgments)}

    stats = {"ingested": 0, "failed": 0, "skipped": 0}

    for judgment in judgments:
        doc_id = judgment.get("doc_id")
        if not doc_id:
            stats["skipped"] += 1
            continue

        # Check if already in KB (by S3 key existence)
        s3_key = _judgment_s3_key(doc_id)
        if await _s3_key_exists(s3_key):
            logger.debug("Judgment %s already in KB — skipping", doc_id)
            stats["skipped"] += 1
            continue

        try:
            # Fetch full document text from IndianKanoon
            full_text = await _fetch_judgment_text(doc_id)
            if not full_text:
                stats["skipped"] += 1
                continue

            # Chunk the document
            chunks = _chunk_text(full_text)

            # Build KB document with metadata
            kb_doc = _build_kb_document(
                judgment=judgment,
                chunks=chunks,
                query=query,
            )

            # Write to S3
            await _write_to_s3(s3_key, kb_doc)
            stats["ingested"] += 1

        except Exception as e:
            logger.warning("Judgment ingestion failed for doc %s: %s", doc_id, e)
            stats["failed"] += 1

    # Trigger Bedrock KB sync job if anything was ingested
    if stats["ingested"] > 0:
        await _trigger_kb_sync()

    logger.info(
        "Judgment ingestion complete: +%d ingested, %d failed, %d skipped",
        stats["ingested"], stats["failed"], stats["skipped"],
    )
    return stats


# ============================================================================
# IndianKanoon full document fetch
# ============================================================================

async def _fetch_judgment_text(doc_id: str) -> Optional[str]:
    """
    Fetches full judgment text from IndianKanoon /doc/ endpoint.
    Cost: ₹0.50 per document fetch.
    """
    if not INDIANKANOON_TOKEN:
        return None

    try:
        import httpx
        import re

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{INDIANKANOON_API_URL}/doc/{doc_id}/",
                headers={"Authorization": f"Token {INDIANKANOON_TOKEN}"},
            )
            resp.raise_for_status()
            data = resp.json()

        # Response contains HTML — strip tags for clean text
        html_text = data.get("doc", "")
        clean     = re.sub(r"<[^>]+>", " ", html_text)
        clean     = re.sub(r"\s+", " ", clean).strip()
        return clean if len(clean) > 100 else None

    except Exception as e:
        logger.warning("Failed to fetch judgment text for doc %s: %s", doc_id, e)
        return None


# ============================================================================
# Chunking
# ============================================================================

def _chunk_text(text: str) -> list[str]:
    """
    Splits judgment text into overlapping chunks.

    Uses word-based splitting (approx 1.3 words per token for legal text).
    Overlap ensures citations and context at chunk boundaries aren't lost.
    """
    words      = text.split()
    total      = len(words)
    chunks     = []
    start      = 0

    while start < total:
        end   = min(start + CHUNK_SIZE, total)
        chunk = " ".join(words[start:end])
        chunks.append(chunk)

        if end >= total:
            break

        # Move forward by chunk_size minus overlap
        start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


# ============================================================================
# KB document builder
# ============================================================================

def _build_kb_document(
    judgment: dict,
    chunks:   list[str],
    query:    str,
) -> dict:
    """
    Builds the KB document structure written to S3.

    Bedrock KB expects documents with a text field and metadata.
    We store each judgment as a single document with metadata —
    Bedrock handles chunking on its own for embedding, but we pre-chunk
    to keep individual document sizes manageable.
    """
    return {
        "metadata": {
            "title":       judgment.get("title", ""),
            "citation":    judgment.get("citation", ""),
            "date":        judgment.get("date", ""),
            "court":       judgment.get("court", "Kerala High Court"),
            "source_url":  judgment.get("source_url", ""),
            "doc_id":      str(judgment.get("doc_id", "")),
            "query_hint":  query,          # helps with relevance for similar future queries
            "ingested_at": datetime.utcnow().isoformat(),
        },
        "chunks": chunks,
        # Bedrock KB uses the first chunk as the primary text for retrieval
        "text": chunks[0] if chunks else "",
    }


# ============================================================================
# S3 operations
# ============================================================================

def _judgment_s3_key(doc_id: str) -> str:
    """Deterministic S3 key for a judgment document."""
    return f"judgments/{doc_id}.json"


async def _s3_key_exists(s3_key: str) -> bool:
    """Checks if a judgment is already stored in S3."""
    try:
        import boto3
        s3 = boto3.client("s3", region_name=AWS_REGION)
        s3.head_object(Bucket=JUDGMENT_KB_S3_BUCKET, Key=s3_key)
        return True
    except Exception:
        return False


async def _write_to_s3(s3_key: str, document: dict) -> None:
    """Writes a KB document to S3 as JSON."""
    import boto3

    s3      = boto3.client("s3", region_name=AWS_REGION)
    content = json.dumps(document, ensure_ascii=False, indent=2)

    s3.put_object(
        Bucket=JUDGMENT_KB_S3_BUCKET,
        Key=s3_key,
        Body=content.encode("utf-8"),
        ContentType="application/json",
    )
    logger.debug("Wrote judgment to S3: %s", s3_key)


# ============================================================================
# Bedrock KB sync trigger
# ============================================================================

async def _trigger_kb_sync() -> None:
    """
    Triggers a Bedrock KB ingestion job to embed newly added S3 documents.
    Fire-and-forget — ingestion runs asynchronously in Bedrock.
    """
    if not BEDROCK_KB_ID or not BEDROCK_KB_DS_ID:
        logger.warning("KB sync skipped — KB ID or data source ID not configured")
        return

    try:
        import boto3

        client = boto3.client("bedrock-agent", region_name=AWS_REGION)
        resp   = client.start_ingestion_job(
            knowledgeBaseId=BEDROCK_KB_ID,
            dataSourceId=BEDROCK_KB_DS_ID,
        )
        job_id = resp.get("ingestionJob", {}).get("ingestionJobId", "unknown")
        logger.info("Bedrock KB ingestion job started: %s", job_id)

    except Exception as e:
        logger.warning("KB sync trigger failed (non-blocking): %s", e)