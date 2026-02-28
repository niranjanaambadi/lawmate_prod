"""
Translation services package for English ↔ Malayalam legal translation.
"""
from .glossary_service import glossary_service
from .protect_service import protect_service
from .llm_translate_service import llm_translate_service
from .document_translate_service import document_translate_service

__all__ = [
    "glossary_service",
    "protect_service",
    "llm_translate_service",
    "document_translate_service",
]
