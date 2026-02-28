"""
agent/tools/search_resources.py

Searches the indexed legal resources Knowledge Base.
Resources are defined in agent/resources/registry.yaml and indexed
by resource_indexing_service.py into Bedrock KB.

Examples of resources: Kerala HC Rules, court fee schedules,
bare acts, e-filing guidelines, practice directions.
"""

from __future__ import annotations

import logging
import os

from app.agent.context import AgentContext
from app.agent.tools.registry import BaseTool

logger = logging.getLogger(__name__)


class SearchResourcesTool(BaseTool):

    name = "search_resources"

    description = (
        "Searches indexed Kerala HC legal resources: court rules, fee schedules, "
        "bare acts, e-filing guidelines, and practice directions. "
        "Use when the lawyer asks about court fees, filing procedures, "
        "limitation periods, specific sections of acts, or HC practice directions. "
        "Always cite the resource name and section in your response."
    )

    input_schema = {
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search query e.g. 'court fee for writ petition' or "
                    "'e-filing document requirements' or 'Section 34 Limitation Act'."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional tag filters to narrow search. "
                    "Available tags: fees, filing, procedure, rules, limitation, "
                    "constitution, bare_acts, practice_directions, efiling."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Max results. Default 3.",
                "default": 3,
            },
        },
        "required": ["query"],
    }

    async def run(self, inputs: dict, context: AgentContext) -> dict:
        try:
            query       = inputs["query"]
            tags        = inputs.get("tags", [])
            max_results = min(inputs.get("max_results", 3), 5)

            results = await _search_resources_kb(
                query=query,
                tags=tags,
                max_results=max_results,
            )

            if not results:
                return self.ok({
                    "results": [],
                    "count":   0,
                    "message": (
                        "No relevant resources found for this query. "
                        "You may want to check the Kerala HC website directly at "
                        "https://www.hckreala.nic.in or IndiaCode at https://indiacode.nic.in."
                    ),
                })

            return self.ok({
                "results": results,
                "count":   len(results),
                "source":  "LawMate Legal Resources KB",
            })

        except Exception as e:
            return self.err(f"Resource search failed: {str(e)}")


async def _search_resources_kb(
    query:       str,
    tags:        list[str],
    max_results: int,
) -> list[dict]:
    """
    Queries the Bedrock KB partition for legal resources.
    Uses a separate KB ID from judgment search to keep them isolated.
    """
    try:
        import boto3
        kb_id  = os.getenv("BEDROCK_RESOURCES_KB_ID", "")
        region = os.getenv("AWS_REGION", "ap-south-1")

        if not kb_id:
            logger.warning("BEDROCK_RESOURCES_KB_ID not set — resource search unavailable")
            return []

        # Build query with tag context if provided
        enriched_query = query
        if tags:
            enriched_query = f"{query} [{' '.join(tags)}]"

        client = boto3.client("bedrock-agent-runtime", region_name=region)
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": enriched_query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        )

        results = []
        for item in response.get("retrievalResults", []):
            content  = item.get("content", {}).get("text", "")
            metadata = item.get("metadata", {})
            score    = item.get("score", 0)

            if score < 0.35:
                continue

            results.append({
                "resource_name": metadata.get("name", "Unknown Resource"),
                "resource_id":   metadata.get("resource_id", ""),
                "tags":          metadata.get("tags", []),
                "excerpt":       content[:600],
                "score":         round(score, 3),
                "source_type":   metadata.get("type", ""),    # pdf | url
                "source":        metadata.get("source", ""),  # S3 key or URL
            })

        return results

    except Exception as e:
        logger.warning("Resources KB search failed: %s", e)
        return []