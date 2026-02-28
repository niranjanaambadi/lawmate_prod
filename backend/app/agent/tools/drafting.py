"""
agent/tools/drafting.py

Drafts legal documents for Kerala HC lawyers using Claude directly.
Supports: writ petitions, affidavits, legal arguments, memos,
vakalatnamas, counter-affidavits, and more.

This tool makes a direct Bedrock call with a specialised drafting prompt —
separate from the main agent loop to allow longer max_tokens.
"""

from __future__ import annotations

import logging
import os

import boto3

from app.agent.context import AgentContext
from app.agent.tools.registry import BaseTool
from app.core.config import settings

logger = logging.getLogger(__name__)

BEDROCK_MODEL_ID = (settings.BEDROCK_MODEL_ID or "").strip() or "anthropic.claude-3-haiku-20240307-v1:0"
AWS_REGION       = settings.AWS_REGION

SUPPORTED_DOCUMENT_TYPES = [
    "writ_petition",
    "affidavit",
    "legal_arguments",
    "memo",
    "vakalatnama",
    "counter_affidavit",
    "interlocutory_application",
    "written_statement",
    "reply_affidavit",
    "synopsis",
]


class DraftDocumentTool(BaseTool):

    name = "draft_document"

    description = (
        "Drafts legal documents for Kerala HC proceedings. "
        "Supports: writ petitions, affidavits, legal arguments, memos, "
        "vakalatnamas, counter-affidavits, interlocutory applications, "
        "written statements, reply affidavits, and synopses. "
        "Provide the document type, key facts, and any specific instructions. "
        "Always review and verify the draft before use in court."
    )

    input_schema = {
        "properties": {
            "document_type": {
                "type": "string",
                "enum": SUPPORTED_DOCUMENT_TYPES,
                "description": "Type of document to draft.",
            },
            "facts": {
                "type": "string",
                "description": (
                    "Key facts for the document. Include: parties, cause of action, "
                    "relevant dates, relief sought, and any specific legal grounds. "
                    "The more detail provided, the better the draft."
                ),
            },
            "instructions": {
                "type": "string",
                "description": (
                    "Specific drafting instructions e.g. 'focus on Article 21 grounds', "
                    "'keep it under 5 pages', 'include prayer for interim stay'. Optional."
                ),
            },
            "relevant_acts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Acts and sections to cite e.g. ['Article 226 Constitution', 'Section 482 CrPC']. Optional.",
            },
        },
        "required": ["document_type", "facts"],
    }

    async def run(self, inputs: dict, context: AgentContext) -> dict:
        try:
            document_type  = inputs["document_type"]
            facts          = inputs["facts"]
            instructions   = inputs.get("instructions", "")
            relevant_acts  = inputs.get("relevant_acts", [])

            # Build case context string if available
            case_context_str = ""
            if context.has_case():
                cd = context.case_data
                case_context_str = (
                    f"Case: {cd.get('case_type')} {cd.get('case_number', '')}\n"
                    f"Petitioner: {cd.get('petitioner_name')}\n"
                    f"Respondent: {cd.get('respondent_name')}\n"
                    f"Court: Kerala High Court\n"
                )

            drafting_prompt = _build_drafting_prompt(
                document_type=document_type,
                facts=facts,
                instructions=instructions,
                relevant_acts=relevant_acts,
                case_context=case_context_str,
                lawyer_name=context.lawyer_name,
            )

            draft = await _call_bedrock_for_draft(drafting_prompt)

            return self.ok({
                "document_type": document_type,
                "draft":         draft,
                "word_count":    len(draft.split()),
                "disclaimer":    (
                    "This is an AI-generated draft for reference only. "
                    "Please review carefully and make necessary corrections "
                    "before filing in court."
                ),
            })

        except Exception as e:
            return self.err(f"Drafting failed: {str(e)}")


# ============================================================================
# Helpers
# ============================================================================

def _build_drafting_prompt(
    document_type: str,
    facts:         str,
    instructions:  str,
    relevant_acts: list[str],
    case_context:  str,
    lawyer_name:   str,
) -> str:

    doc_label = document_type.replace("_", " ").title()
    acts_str  = "\n".join(f"- {a}" for a in relevant_acts) if relevant_acts else "Not specified"

    return f"""You are an expert Kerala High Court advocate drafting a {doc_label}.

CASE CONTEXT:
{case_context if case_context else "Not provided — use facts below."}

FACTS PROVIDED BY ADVOCATE {lawyer_name.upper()}:
{facts}

RELEVANT ACTS / SECTIONS:
{acts_str}

SPECIFIC INSTRUCTIONS:
{instructions if instructions else "Standard Kerala HC format."}

DRAFTING GUIDELINES:
- Follow Kerala High Court Rules 1971 format strictly
- Use formal legal language appropriate for High Court proceedings
- Number all paragraphs
- Include proper prayer/relief clause
- Use "RESPECTFULLY SHOWETH" for petitions
- Address to "THE HON'BLE THE CHIEF JUSTICE AND OTHER HON'BLE JUDGES OF THE HIGH COURT OF KERALA"
- Leave [BLANK] placeholders for dates, amounts, or details not provided
- Do NOT fabricate facts, dates, or case citations not provided

Draft the {doc_label} now:"""


async def _call_bedrock_for_draft(prompt: str) -> str:
    """Makes a Bedrock call with higher max_tokens for document generation."""
    try:
        client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
        response = client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={
                "maxTokens": 4096,   # Higher limit for documents
                "temperature": 0.3,  # Lower temp for consistent legal language
            },
        )
        return response["output"]["message"]["content"][0]["text"]

    except Exception as e:
        logger.error("Bedrock drafting call failed: %s", e)
        raise
