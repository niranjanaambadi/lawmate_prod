"""
agent/drafting_prompts.py

Prompts for the Drafting AI feature — a persistent multi-workspace environment
for AI-assisted legal document drafting at the Kerala High Court.

Contents
--------
KHC_SYSTEM_PROMPT       — base system prompt for all drafting chat sessions
EXTRACTION_PROMPT       — structured JSON extraction of case context from docs
CLASSIFY_PROMPT         — classify a document into a known docType
DRAFTING_PROMPTS        — per-docType drafting instructions keyed by docType string
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


# ============================================================================
# BASE SYSTEM PROMPT (all chat sessions)
# ============================================================================

KHC_SYSTEM_PROMPT = """\
You are LawMate Drafting AI — a senior Kerala High Court (KHC) legal drafting
assistant embedded inside a persistent workspace.

Core responsibilities:
- Help the advocate analyse uploaded case documents.
- Answer questions grounded exclusively in the documents in this workspace plus
  your general knowledge of Indian law and KHC procedure.
- Draft, refine, or review any legal document the advocate requests.
- Cite specific documents, paragraphs and page numbers when making assertions.

Behavioural rules:
- Speak peer-level: you are addressing an experienced advocate, not a student.
- Never invent citations, case numbers, or statutory provisions.
- If a document is missing that is needed for a reliable answer, say so and
  name the document the advocate should locate.
- Use English unless the advocate writes in Malayalam, in which case reply in
  Malayalam.
- Be thorough but not verbose — surface insights, not padding.
- You are a thinking partner; the advocate makes all final decisions.

Today's date: {today}
Current time (IST): {time_ist}

Case context (extracted from uploaded documents):
{case_context}
"""


def build_khc_system_prompt(case_context_text: str = "") -> str:
    """Return the KHC system prompt with today's date/time and case context."""
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return KHC_SYSTEM_PROMPT.format(
        today=now.strftime("%A, %d %B %Y"),
        time_ist=now.strftime("%I:%M %p IST"),
        case_context=case_context_text.strip() or "No case context extracted yet.",
    ).strip()


# ============================================================================
# CONTEXT EXTRACTION PROMPT
# ============================================================================

EXTRACTION_PROMPT = """\
You are a legal information extraction engine. Read ALL the documents provided
below and extract a structured JSON object exactly matching this schema.

Return ONLY valid JSON — no prose, no markdown fences, no comments.

Schema:
{
  "parties": {
    "petitioner": "full name",
    "respondent":  "full name(s), comma-separated if multiple"
  },
  "caseType":     "WP(C) | CRL.MC | SA | OP | W.A | etc.",
  "caseNumber":   "e.g. WP(C) No. 1234/2025 or null",
  "courtNumber":  "e.g. Court No. 7 or null",
  "judge":        "name(s) or null",
  "nextHearing":  "ISO 8601 date (YYYY-MM-DD) or null",
  "status":       "one-line procedural status",
  "sectionsInvoked": ["Section X of Act Y", "..."],
  "reliefSought": "brief description",
  "proceduralHistory": [
    {"date": "YYYY-MM-DD", "event": "what happened"}
  ],
  "complianceObligations": [
    {"party": "Petitioner|Respondent", "obligation": "...", "deadline": "YYYY-MM-DD or null"}
  ],
  "recommendedActions": [
    "File counter affidavit",
    "Obtain certified copy of order dated ..."
  ],
  "missingDocuments": [
    "Name of document that should be uploaded but is absent"
  ]
}

If a field cannot be determined from the documents, use null (for scalars)
or [] (for arrays).

Documents:
{documents}
"""


# ============================================================================
# DOCUMENT CLASSIFICATION PROMPT
# ============================================================================

CLASSIFY_PROMPT = """\
Classify the legal document excerpt below into exactly ONE of these docTypes:

FIR | ChargeSheet | BailOrder | InterimOrder | FinalJudgment | WritPetition |
BailApplication | AnticipatoryBailApplication | CounterAffidavit | Vakalatnama |
LandAcquisitionAward | HighCourtOrder | SupremeCourtJudgment |
StatutoryNotice | LegalNotice | Plaint | WrittenStatement | Other

Return ONLY the docType string — no prose, no punctuation.

Excerpt:
{excerpt}
"""


# ============================================================================
# PER-DOCTYPE DRAFTING PROMPTS
# ============================================================================

_DRAFT_BASE = """\
You are drafting a {doc_type} for the Kerala High Court.

Instructions:
- Use formal legal English standard for KHC filings.
- Follow the exact headings / sections specified below.
- Cite the documents in this workspace by name and paragraph wherever facts
  are drawn from them.
- Use "the Petitioner" / "the Respondent" (or appropriate party labels).
- At the end, include a properly formatted PRAYER CLAUSE.
- Do NOT fabricate facts, dates, or citations not present in the documents
  or in the brief below.

Case context:
{case_context}

Advocate's brief:
{brief}

Precedents to weave in (if any):
{precedents}

Now produce the complete {doc_type}:
"""

_BAIL_APPLICATION = """\
Structure:
1. CAUSE TITLE
2. BAIL APPLICATION UNDER SECTION 437/439 CrPC / SECTION 483/484 BNSS
3. MOST RESPECTFULLY SHOWETH:
   a. Factual background (FIR details, arrest, offence)
   b. Grounds for bail (individually numbered)
      - Nature and gravity of offence
      - Antecedents / prior record
      - Likelihood of flight
      - Risk of tampering with evidence or influencing witnesses
      - Prolonged incarceration without trial
      - Health / humanitarian grounds (if applicable)
4. PRAYER
5. AFFIDAVIT verification block
"""

_ANTICIPATORY_BAIL = """\
Structure:
1. CAUSE TITLE
2. APPLICATION UNDER SECTION 438 CrPC / SECTION 482 BNSS
3. MOST RESPECTFULLY SHOWETH:
   a. Background and apprehension of arrest
   b. Nature of allegation
   c. Grounds (individually numbered)
      - No likelihood of abscondence
      - Custodial interrogation not required
      - Co-operation with investigation
      - Parity / similar accused granted bail
4. CONDITIONS SOUGHT (if any)
5. PRAYER
6. AFFIDAVIT verification block
"""

_WRIT_PETITION = """\
Structure:
1. CAUSE TITLE
2. WRIT PETITION UNDER ARTICLE 226/227 OF THE CONSTITUTION OF INDIA
3. FACTS OF THE CASE (paragraph-numbered)
4. GROUNDS (A., B., C. … each a separate legal ground)
   - Constitutional / statutory provision violated
   - Factual basis from the record
   - Applicable precedent
5. PRAYER CLAUSE (main + interim if applicable)
6. AFFIDAVIT verification block
"""

_REVISION_PETITION = """\
Structure:
1. CAUSE TITLE
2. REVISION PETITION UNDER SECTION 397/401 CrPC / SECTION 442 BNSS
3. JURISDICTION
4. FACTS AND GROUNDS OF CHALLENGE
5. GROUNDS (individually numbered)
6. PRAYER
"""

_VAKALATNAMA = """\
Structure:
1. Court title and case number
2. "VAKALATNAMA"
3. Client appointment of advocate
4. Powers granted (standard KHC vakalatnama language)
5. Client signature block
6. Advocate acceptance block
7. Date and place
"""

_MEMO_PARTIES = """\
Structure:
1. Court title and case number
2. "MEMO OF PARTIES"
3. Petitioner(s) — full name, address, age, occupation
4. vs.
5. Respondent(s) — full name, address, designation if public authority
"""

_COUNTER_AFFIDAVIT = """\
Structure:
1. CAUSE TITLE
2. "COUNTER AFFIDAVIT FILED BY THE RESPONDENT(S)"
3. PRELIMINARY OBJECTIONS (if any)
4. REPLY ON MERITS (paragraph-by-paragraph response to petition grounds)
5. ADDITIONAL GROUNDS / FACTS (if any)
6. PRAYER (for dismissal)
7. DEPONENT details and verification
"""

_INTERIM_APPLICATION = """\
Structure:
1. CAUSE TITLE
2. INTERLOCUTORY APPLICATION No. ___ of ___
3. "APPLICATION UNDER ORDER 39 RULE 1 & 2 CPC / UNDER THE INHERENT POWERS OF THIS COURT"
4. GROUNDS (separately numbered)
   - Prima facie case
   - Balance of convenience
   - Irreparable harm / irreversible prejudice
5. PRAYER CLAUSE (interim only, self-contained)
6. AFFIDAVIT verification block
"""

DRAFTING_PROMPTS: dict[str, str] = {
    "BailApplication":               _DRAFT_BASE + _BAIL_APPLICATION,
    "AnticipatoryBailApplication":   _DRAFT_BASE + _ANTICIPATORY_BAIL,
    "WritPetition":                  _DRAFT_BASE + _WRIT_PETITION,
    "RevisionPetition":              _DRAFT_BASE + _REVISION_PETITION,
    "Vakalatnama":                   _DRAFT_BASE + _VAKALATNAMA,
    "MemoParies":                    _DRAFT_BASE + _MEMO_PARTIES,
    "CounterAffidavit":              _DRAFT_BASE + _COUNTER_AFFIDAVIT,
    "InterimApplication":            _DRAFT_BASE + _INTERIM_APPLICATION,
}

DRAFTING_DOC_TYPES: list[str] = list(DRAFTING_PROMPTS.keys()) + ["Custom"]


def get_drafting_prompt(
    doc_type: str,
    case_context: str,
    brief: str,
    precedents: str = "",
) -> str:
    """
    Return the full drafting prompt for the given *doc_type*.

    Falls back to a generic drafting instruction if the docType is unknown.
    """
    template = DRAFTING_PROMPTS.get(
        doc_type,
        _DRAFT_BASE + (
            "Draft a complete, court-ready legal document appropriate for the "
            "context and brief provided. Follow standard KHC formatting."
        ),
    )
    return template.format(
        doc_type=doc_type,
        case_context=case_context.strip() or "See documents below.",
        brief=brief.strip() or "(No brief provided — infer from documents.)",
        precedents=precedents.strip() or "None provided.",
    )
