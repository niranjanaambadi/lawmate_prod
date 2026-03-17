"""
agent/prep_multi_query.py

Expands a single user legal query into 3-4 targeted search queries using the
Bedrock LLM. Each generated query is scoped to Kerala High Court and Supreme
Court of India.

Falls back to [user_query] on any failure — never blocks the main pipeline.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_EXPAND_SYSTEM = (
    "You are a legal search query expert for Indian courts. "
    "Given a legal question, generate 3 to 4 specific search queries. "
    "Each query must include relevant statute sections, legal terms, and "
    "'Kerala High Court OR Supreme Court of India'. "
    "Return only a JSON array of strings. No explanation, no markdown, no code fences."
)


async def expand_query(user_query: str, model_id: str, region: str) -> list[str]:
    """
    Call Bedrock converse API to expand user_query into 3-4 legal search queries.

    Each generated query is scoped to 'Kerala High Court OR Supreme Court of India'.
    Falls back to [user_query] if the LLM call fails or returns invalid output.

    Args:
        user_query: The original user question.
        model_id:   Bedrock model ID (e.g. settings.CASE_PREP_MODEL_ID).
        region:     AWS region string (e.g. "ap-south-1").

    Returns:
        List of 1-4 query strings. Always contains at least [user_query].
    """
    import boto3
    from app.core.config import settings

    try:
        client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        response = client.converse(
            modelId=model_id,
            system=[{"text": _EXPAND_SYSTEM}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": f"Legal question: {user_query}"}],
                }
            ],
            inferenceConfig={"maxTokens": 512, "temperature": 0.2},
        )

        raw = (
            response.get("output", {})
            .get("message", {})
            .get("content", [{}])[0]
            .get("text", "")
            .strip()
        )

        # Strip markdown code fences if the model wraps the JSON
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) >= 2 else raw
            if raw.lower().startswith("json"):
                raw = raw[4:]

        queries: list = json.loads(raw.strip())
        valid = [q.strip() for q in queries if isinstance(q, str) and q.strip()][:4]

        if valid:
            logger.info(
                "Multi-query expansion: %d queries for %r", len(valid), user_query[:60]
            )
            return valid

    except Exception as exc:
        logger.warning("Multi-query expansion failed, using original query: %s", exc)

    return [user_query]
