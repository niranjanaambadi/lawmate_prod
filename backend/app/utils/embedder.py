"""
app/utils/embedder.py

Bedrock Titan text embedding and Bedrock KB retrieval with workspaceId metadata
filtering, used by the Drafting AI feature.

Functions
---------
embed_text(text)
    Call Bedrock Titan Embed v2 and return the embedding vector.

retrieve_from_kb(query, workspace_id, top_k)
    Retrieve the most relevant chunks from the Bedrock KB that belong to the
    given workspace (filtered by metadata key "workspaceId").

ingest_chunk_to_kb(chunk, workspace_id, doc_id, filename)
    [Best-effort] Ingest a single text chunk into the Bedrock KB with metadata.
    Not a blocking operation — failures are logged and swallowed.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_TITAN_EMBED_MODEL = "amazon.titan-embed-text-v2:0"
_BEDROCK_KB_ID     = ""   # resolved at call time from env


def _kb_id() -> str:
    return os.getenv("BEDROCK_KNOWLEDGE_BASE_ID", "")


def _region() -> str:
    return os.getenv("AWS_REGION", "ap-south-1")


# ── Embedding ─────────────────────────────────────────────────────────────────

async def embed_text(text: str) -> list[float]:
    """
    Embed *text* using Bedrock Titan Embed Text v2.

    Returns the embedding vector (1024-dim).  Returns [] on failure.
    """
    import json
    import boto3
    from app.core.config import settings

    if not text or not text.strip():
        return []

    try:
        client = boto3.client(
            "bedrock-runtime",
            region_name=_region(),
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        body = json.dumps({"inputText": text[:8000]})   # Titan v2 limit
        response = client.invoke_model(
            modelId=_TITAN_EMBED_MODEL,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result.get("embedding", [])

    except Exception as exc:
        logger.warning("embed_text failed: %s", exc)
        return []


# ── KB Retrieval ──────────────────────────────────────────────────────────────

async def retrieve_from_kb(
    query: str,
    workspace_id: str,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """
    Retrieve the *top_k* most relevant chunks from the Bedrock Knowledge Base
    that belong to *workspace_id* (filtered by metadata key "workspaceId").

    Returns a list of dicts:
        {"text": str, "score": float, "metadata": dict}
    Returns [] if the KB is not configured or on failure.
    """
    import boto3
    from app.core.config import settings

    kb_id = _kb_id()
    if not kb_id:
        logger.debug("retrieve_from_kb: BEDROCK_KNOWLEDGE_BASE_ID not set — skipping")
        return []

    if not query.strip():
        return []

    try:
        client = boto3.client(
            "bedrock-agent-runtime",
            region_name=_region(),
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": top_k,
                    "filter": {
                        "equals": {
                            "key":   "workspaceId",
                            "value": workspace_id,
                        }
                    },
                }
            },
        )

        results: list[dict] = []
        for item in response.get("retrievalResults", []):
            score    = item.get("score", 0.0)
            content  = item.get("content", {}).get("text", "")
            metadata = item.get("metadata", {})
            results.append({"text": content, "score": round(score, 4), "metadata": metadata})

        return results

    except Exception as exc:
        logger.warning("retrieve_from_kb failed: %s", exc)
        return []


# ── Ingestion (best-effort / non-blocking) ────────────────────────────────────

async def ingest_chunk_to_kb(
    chunk: str,
    workspace_id: str,
    doc_id: str,
    filename: str,
) -> None:
    """
    Best-effort ingestion of a single text chunk into the Bedrock KB.

    The KB datasource must already be configured to accept inline content.
    Failures are swallowed — this never blocks the upload pipeline.
    """
    import boto3
    from app.core.config import settings

    kb_id = _kb_id()
    if not kb_id or not chunk.strip():
        return

    try:
        client = boto3.client(
            "bedrock-agent-runtime",
            region_name=_region(),
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        # Use the IngestKnowledgeBaseDocuments API (Bedrock KB Direct Ingestion)
        client.ingest_knowledge_base_documents(
            knowledgeBaseId=kb_id,
            documents=[
                {
                    "content": {
                        "dataSourceType": "INLINE",
                        "inlineContent": {
                            "textContent": {"data": chunk},
                            "type":        "TEXT",
                        },
                    },
                    "metadata": {
                        "inlineAttributes": [
                            {"key": "workspaceId", "value": {"stringValue": workspace_id}},
                            {"key": "docId",       "value": {"stringValue": doc_id}},
                            {"key": "filename",    "value": {"stringValue": filename}},
                        ]
                    },
                }
            ],
        )
        logger.debug(
            "ingest_chunk_to_kb: ingested chunk (%d chars) for workspace %s doc %s",
            len(chunk), workspace_id, doc_id,
        )

    except Exception as exc:
        logger.debug(
            "ingest_chunk_to_kb: skipped (non-blocking): %s", exc
        )
