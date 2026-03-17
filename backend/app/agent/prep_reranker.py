"""
agent/prep_reranker.py

Reranks candidate judgment chunks using Cohere Rerank via AWS Bedrock
(bedrock-agent-runtime rerank API).

Falls back to original order (sliced to top_k) if the rerank call is
unavailable or fails — never blocks the main pipeline.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SCORE_THRESHOLD = 0.4


async def rerank(
    query: str,
    chunks: list[dict],
    top_k: int = 5,
    region: str = "ap-south-1",
) -> list[dict]:
    """
    Rerank candidate chunks using Cohere Rerank via AWS Bedrock.

    Args:
        query:   The original user query used as the relevance reference.
        chunks:  Candidate chunk dicts; each must have at least an 'excerpt' key.
        top_k:   Maximum results to return.
        region:  AWS region for the bedrock-agent-runtime client.

    Returns:
        Up to top_k chunks sorted by descending rerank score, filtered to
        relevanceScore >= 0.4. Falls back to chunks[:top_k] on any failure.
    """
    if not chunks:
        return []
    if len(chunks) <= top_k:
        return chunks

    import boto3
    from app.core.config import settings

    try:
        client = boto3.client(
            "bedrock-agent-runtime",
            region_name=region,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        model_arn = (
            f"arn:aws:bedrock:{region}::foundation-model/cohere.rerank-v3-5:0"
        )

        sources = [
            {
                "type": "INLINE",
                "inlineDocumentSource": {
                    "type": "TEXT",
                    "textDocument": {
                        "text": (c.get("excerpt") or c.get("title") or "")[:2000]
                    },
                },
            }
            for c in chunks
        ]

        response = client.rerank(
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {"modelArn": model_arn},
                    "numberOfResults": min(top_k, len(chunks)),
                },
            },
            sources=sources,
            query=query,
        )

        reranked = response.get("rerankingResults") or []
        result: list[dict] = []
        for item in reranked:
            score = item.get("relevanceScore", 0.0)
            if score < _SCORE_THRESHOLD:
                continue
            idx = item.get("index", 0)
            if 0 <= idx < len(chunks):
                enriched = dict(chunks[idx])
                enriched["rerank_score"] = round(score, 4)
                result.append(enriched)

        if result:
            logger.info(
                "Reranked %d candidates → %d selected (threshold=%.2f)",
                len(chunks), len(result), _SCORE_THRESHOLD,
            )
            return result[:top_k]

        logger.warning(
            "Reranking returned 0 results above threshold %.2f — falling back",
            _SCORE_THRESHOLD,
        )

    except Exception as exc:
        logger.warning("Reranking unavailable, using original order: %s", exc)

    return chunks[:top_k]
