"""
app/utils/chunker.py

Word-based text chunking for the Drafting AI feature.

Uses word count as a proxy for token count (legal English ≈ 1.0–1.3 tokens/word).
"""
from __future__ import annotations


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 50,
) -> list[str]:
    """
    Split *text* into overlapping word-count chunks.

    Parameters
    ----------
    text       : Plain text to split.
    chunk_size : Target word count per chunk (default 512).
    overlap    : Number of words carried over from the previous chunk (default 50).

    Returns
    -------
    List of non-empty chunk strings.  Returns [] if *text* is blank.
    """
    if not text or not text.strip():
        return []

    words = text.split()
    if len(words) <= chunk_size:
        return [text.strip()]

    step   = max(chunk_size - overlap, 1)
    chunks: list[str] = []
    start  = 0

    while start < len(words):
        end   = start + chunk_size
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        start += step

    return chunks


def estimate_tokens(text: str) -> int:
    """
    Rough token estimate: word_count × 1.3  (conservative for legal English).
    """
    if not text:
        return 0
    return int(len(text.split()) * 1.3)
