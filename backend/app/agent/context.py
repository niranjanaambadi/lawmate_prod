"""
agent/context.py

Builds the AgentContext object that is passed into every agent invocation.

AgentContext carries:
  - which page the lawyer is on (drives system prompt selection)
  - case data fetched from DB (when on a case-specific page)
  - lawyer identity (from auth token)

This is the single place where page → context mapping lives.
Adding new context fields = edit _build_case_context() only.

Usage:
    from app.agent.context import build_agent_context, AgentContext

    context = await build_agent_context(
        page="hearing_day",
        case_id="4e43f0c0-...",
        lawyer_id="uuid",
        db=db,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Case, User


# ============================================================================
# Valid page identifiers — must match frontend page names
# ============================================================================

VALID_PAGES = frozenset({
    "global",
    "case_detail",
    "hearing_day",
    "cause_list",
})


# ============================================================================
# AgentContext dataclass
# ============================================================================

@dataclass
class AgentContext:
    """
    Immutable context object passed into every agent invocation.

    Attributes:
        page:            Which LawMate page the chat was opened from.
                         Controls system prompt selection and tool bias.

        lawyer_id:       UUID of the authenticated lawyer.
                         Used by tools to scope DB queries.

        lawyer_name:     KHC advocate name — injected into prompts.

        case_id:         UUID of the active case (None on global/cause_list).

        case_data:       Dict of case fields for prompt injection.
                         None when no case is in context.

        conversation_id: Frontend-generated UUID for this chat session.
                         Used to maintain message history per session.

        extra:           Arbitrary additional context for future use
                         e.g. selected_date on cause_list page.
    """
    page:            str
    lawyer_id:       str
    lawyer_name:     str
    case_id:         Optional[str]  = None
    case_data:       Optional[dict] = None
    conversation_id: Optional[str]  = None
    extra:           dict           = field(default_factory=dict)

    def has_case(self) -> bool:
        return self.case_id is not None and self.case_data is not None

    def to_prompt_context(self) -> dict:
        """Returns the dict passed to get_system_prompt()."""
        return {
            "page":         self.page,
            "case_context": self.case_data,
        }


# ============================================================================
# Public builder function
# ============================================================================

async def build_agent_context(
    page:            str,
    lawyer_id:       str,
    db:              Session,
    case_id:         Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> AgentContext:
    """
    Builds AgentContext for an incoming agent chat request.

    Fetches:
      - Lawyer name from users table
      - Case data from cases table (when case_id provided)

    Args:
        page:            Page identifier from frontend
                         ("global" | "case_detail" | "hearing_day" | "cause_list")
        lawyer_id:       Authenticated lawyer's user ID (from JWT)
        db:              SQLAlchemy session
        case_id:         Case UUID (from URL param on case/hearing-day pages)
        conversation_id: Chat session UUID from frontend

    Returns:
        AgentContext ready for agent.py

    Raises:
        ValueError:      If case_id is not found in DB
        PermissionError: If case_id does not belong to lawyer_id
    """

    # Validate and normalise page identifier
    resolved_page = _resolve_page(page)

    # Fetch lawyer name
    lawyer_name = await _get_lawyer_name(lawyer_id, db)

    # Fetch case data only on case-specific pages
    case_data = None
    resolved_case_id = None

    if case_id and resolved_page in ("case_detail", "hearing_day"):
        case_data, resolved_case_id = await _build_case_context(
            case_id=case_id,
            lawyer_id=lawyer_id,
            db=db,
        )

    return AgentContext(
        page=resolved_page,
        lawyer_id=lawyer_id,
        lawyer_name=lawyer_name,
        case_id=resolved_case_id,
        case_data=case_data,
        conversation_id=conversation_id,
    )


# ============================================================================
# Private helpers
# ============================================================================

def _resolve_page(page: str) -> str:
    """
    Normalises and validates the page identifier.
    Falls back to 'global' for unknown values rather than raising —
    safer for frontend changes not yet reflected here.
    """
    normalised = (page or "").strip().lower()
    if normalised not in VALID_PAGES:
        import logging
        logging.getLogger(__name__).warning(
            "Unknown page identifier '%s' — defaulting to 'global'", page
        )
        return "global"
    return normalised


async def _get_lawyer_name(lawyer_id: str, db: Session) -> str:
    """Fetches the KHC advocate name for the lawyer."""
    user = db.query(User).filter(
        User.id == UUID(lawyer_id),
        User.is_active == True,
    ).first()

    if not user:
        return "Advocate"  # safe fallback, auth middleware catches invalid IDs

    return user.khc_advocate_name


async def _build_case_context(
    case_id:   str,
    lawyer_id: str,
    db:        Session,
) -> tuple[dict, str]:
    """
    Fetches case from DB and builds the context dict for prompt injection.

    Only returns cases that belong to the requesting lawyer — prevents
    cross-lawyer data leakage into the agent context.

    Returns:
        (case_data dict, resolved case_id string)

    Raises:
        ValueError:      If case not found
        PermissionError: If case does not belong to this lawyer
    """
    case = db.query(Case).filter(
        Case.id == UUID(case_id),
        Case.is_visible == True,
    ).first()

    if not case:
        raise ValueError(f"Case {case_id} not found")

    # Security: case must belong to this lawyer
    if str(case.advocate_id) != lawyer_id:
        raise PermissionError(
            f"Case {case_id} does not belong to lawyer {lawyer_id}"
        )

    # Build context dict injected into system prompt + available to tools.
    # When Case model grows (e.g. CNR number after MoU), add fields here.
    case_data = {
        "case_id":           str(case.id),
        "case_number":       case.case_number or "Not yet assigned",
        "efiling_number":    case.efiling_number,
        "case_type":         case.case_type,
        "case_year":         case.case_year,
        "petitioner_name":   case.petitioner_name,
        "respondent_name":   case.respondent_name,
        "status":            case.status.value if case.status else "unknown",
        "next_hearing_date": _format_date(case.next_hearing_date),
        "judge_name":        case.judge_name or "Not assigned",
        "court_number":      case.court_number or "N/A",
        "bench_type":        case.bench_type or "N/A",
        "court_status":      case.court_status or "",
        "last_synced_at":    _format_date(case.last_synced_at),
        # Full raw_court_data available for tools needing deeper detail
        "raw_court_data":    case.raw_court_data or {},
    }

    return case_data, str(case.id)


def _format_date(dt) -> str:
    """Formats a datetime for prompt injection. Returns 'N/A' if None."""
    if dt is None:
        return "N/A"
    try:
        return dt.strftime("%d %B %Y")
    except Exception:
        return str(dt)