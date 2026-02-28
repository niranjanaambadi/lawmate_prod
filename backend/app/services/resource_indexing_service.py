"""
services/resource_indexing_service.py

Indexes legal resources (PDFs from S3, web URLs) into Bedrock Knowledge Base.

Resources are defined in agent/resources/registry.yaml.
This service reads the registry, fetches each resource, and stores it in
the Bedrock Resources KB (separate from the judgments KB).

Adding a new resource:
  1. Edit agent/resources/registry.yaml
  2. Call POST /api/v1/admin/resources/index  (or run directly)
  3. Done — agent can now search it via search_resources tool

Environment variables:
  BEDROCK_RESOURCES_KB_ID        — separate KB for legal resources
  BEDROCK_RESOURCES_KB_DS_ID     — data source ID within resources KB
  RESOURCES_KB_S3_BUCKET         — S3 bucket for resource documents
  AWS_REGION
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

RESOURCES_KB_S3_BUCKET = os.getenv("RESOURCES_KB_S3_BUCKET", "lawmate-resources-kb")
BEDROCK_RESOURCES_KB_ID     = os.getenv("BEDROCK_RESOURCES_KB_ID", "")
BEDROCK_RESOURCES_KB_DS_ID  = os.getenv("BEDROCK_RESOURCES_KB_DS_ID", "")
AWS_REGION                  = os.getenv("AWS_REGION", "ap-south-1")

REGISTRY_PATH = Path(__file__).parent.parent / "agent" / "resources" / "registry.yaml"


# ============================================================================
# Public interface
# ============================================================================

async def index_all_resources(force: bool = False) -> dict:
    """
    Indexes all resources defined in registry.yaml into Bedrock KB.

    Args:
        force: If True, re-indexes even if already in S3.
               Use when a resource has been updated.

    Returns:
        { "indexed": int, "failed": int, "skipped": int }
    """
    registry = _load_registry()
    resources = registry.get("resources", [])

    if not resources:
        logger.warning("No resources found in registry.yaml")
        return {"indexed": 0, "failed": 0, "skipped": 0}

    stats = {"indexed": 0, "failed": 0, "skipped": 0}

    for resource in resources:
        resource_id = resource.get("id")
        if not resource_id:
            stats["skipped"] += 1
            continue

        try:
            s3_key = _resource_s3_key(resource_id)

            if not force and await _s3_key_exists(s3_key):
                logger.debug("Resource '%s' already indexed — skipping", resource_id)
                stats["skipped"] += 1
                continue

            text = await _fetch_resource_text(resource)
            if not text:
                logger.warning("Could not fetch text for resource '%s'", resource_id)
                stats["failed"] += 1
                continue

            kb_doc = _build_kb_document(resource, text)
            await _write_to_s3(s3_key, kb_doc)
            stats["indexed"] += 1
            logger.info("Indexed resource: %s", resource_id)

        except Exception as e:
            logger.error("Failed to index resource '%s': %s", resource_id, e)
            stats["failed"] += 1

    if stats["indexed"] > 0:
        await _trigger_kb_sync()

    logger.info(
        "Resource indexing complete: +%d indexed, %d failed, %d skipped",
        stats["indexed"], stats["failed"], stats["skipped"],
    )
    return stats


async def index_single_resource(resource_id: str, force: bool = True) -> dict:
    """Indexes a single resource by ID. Useful for partial re-indexing."""
    registry  = _load_registry()
    resources = registry.get("resources", [])

    resource = next((r for r in resources if r.get("id") == resource_id), None)
    if not resource:
        return {"error": f"Resource '{resource_id}' not found in registry"}

    try:
        s3_key = _resource_s3_key(resource_id)
        text   = await _fetch_resource_text(resource)
        if not text:
            return {"error": f"Could not fetch text for resource '{resource_id}'"}

        kb_doc = _build_kb_document(resource, text)
        await _write_to_s3(s3_key, kb_doc)
        await _trigger_kb_sync()
        return {"indexed": 1, "resource_id": resource_id}

    except Exception as e:
        return {"error": str(e)}


def list_registry_resources() -> list[dict]:
    """Returns all resources in registry.yaml — used by admin API."""
    registry = _load_registry()
    return [
        {
            "id":          r.get("id"),
            "name":        r.get("name"),
            "type":        r.get("type"),
            "tags":        r.get("tags", []),
            "description": r.get("description", ""),
        }
        for r in registry.get("resources", [])
    ]


# ============================================================================
# Registry loader
# ============================================================================

def _load_registry() -> dict:
    """Loads and parses registry.yaml."""
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Registry not found at {REGISTRY_PATH}")
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ============================================================================
# Resource text fetcher
# ============================================================================

async def _fetch_resource_text(resource: dict) -> Optional[str]:
    """
    Fetches text content from a resource.
    Handles two source types: pdf (from S3) and url (live fetch).
    """
    source_type = resource.get("type", "url")

    if source_type == "pdf":
        return await _fetch_pdf_from_s3(resource)
    elif source_type == "url":
        return await _fetch_url_text(resource)
    else:
        logger.warning("Unknown resource type: %s", source_type)
        return None


async def _fetch_pdf_from_s3(resource: dict) -> Optional[str]:
    """Downloads a PDF from S3 and extracts text using pdfplumber."""
    try:
        import boto3
        import pdfplumber
        import io

        s3_bucket = resource.get("s3_bucket", RESOURCES_KB_S3_BUCKET)
        s3_key    = resource.get("s3_key", "")

        if not s3_key:
            logger.warning("No s3_key for PDF resource '%s'", resource.get("id"))
            return None

        s3       = boto3.client("s3", region_name=AWS_REGION)
        response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        pdf_data = response["Body"].read()

        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        full_text = "\n\n".join(text_parts)
        return full_text if len(full_text) > 50 else None

    except Exception as e:
        logger.warning("PDF fetch failed for '%s': %s", resource.get("id"), e)
        return None


async def _fetch_url_text(resource: dict) -> Optional[str]:
    """Fetches and extracts text from a URL."""
    url = resource.get("url", "")
    if not url:
        return None

    try:
        import httpx
        import re

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 LawMate/1.0 (legal research bot)"
            })
            resp.raise_for_status()
            html = resp.text

        # Strip HTML tags
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean if len(clean) > 100 else None

    except Exception as e:
        logger.warning("URL fetch failed for '%s': %s", resource.get("id"), e)
        return None


# ============================================================================
# KB document builder
# ============================================================================

def _build_kb_document(resource: dict, text: str) -> dict:
    """Builds the KB document structure for a legal resource."""
    from datetime import datetime

    # Truncate to ~50k chars to stay within Bedrock limits
    truncated_text = text[:50000]

    return {
        "text": truncated_text,
        "metadata": {
            "resource_id": resource.get("id", ""),
            "name":        resource.get("name", ""),
            "type":        resource.get("type", "url"),
            "tags":        resource.get("tags", []),
            "description": resource.get("description", ""),
            "source":      resource.get("url") or resource.get("s3_key", ""),
            "version":     resource.get("version", "1.0"),
            "indexed_at":  datetime.utcnow().isoformat(),
        },
    }


# ============================================================================
# S3 + Bedrock operations
# ============================================================================

def _resource_s3_key(resource_id: str) -> str:
    return f"resources/{resource_id}.json"


async def _s3_key_exists(s3_key: str) -> bool:
    try:
        import boto3
        s3 = boto3.client("s3", region_name=AWS_REGION)
        s3.head_object(Bucket=RESOURCES_KB_S3_BUCKET, Key=s3_key)
        return True
    except Exception:
        return False


async def _write_to_s3(s3_key: str, document: dict) -> None:
    import boto3
    s3      = boto3.client("s3", region_name=AWS_REGION)
    content = json.dumps(document, ensure_ascii=False, indent=2)
    s3.put_object(
        Bucket=RESOURCES_KB_S3_BUCKET,
        Key=s3_key,
        Body=content.encode("utf-8"),
        ContentType="application/json",
    )


async def _trigger_kb_sync() -> None:
    if not BEDROCK_RESOURCES_KB_ID or not BEDROCK_RESOURCES_KB_DS_ID:
        logger.warning("Resources KB sync skipped — KB IDs not configured")
        return

    try:
        import boto3
        client = boto3.client("bedrock-agent", region_name=AWS_REGION)
        resp   = client.start_ingestion_job(
            knowledgeBaseId=BEDROCK_RESOURCES_KB_ID,
            dataSourceId=BEDROCK_RESOURCES_KB_DS_ID,
        )
        job_id = resp.get("ingestionJob", {}).get("ingestionJobId", "unknown")
        logger.info("Resources KB ingestion job started: %s", job_id)
    except Exception as e:
        logger.warning("Resources KB sync trigger failed (non-blocking): %s", e)