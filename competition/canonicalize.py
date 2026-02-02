from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import CompetitorProduct


def _tokenize(s: str) -> set[str]:
    return {t for t in (s or "").lower().split() if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


@dataclass(frozen=True)
class CanonicalCandidate:
    normalized_name: str
    score: float


def canonicalize_normalized_name(
    db: Session,
    normalized_name: str,
    *,
    website: str | None = None,
    category: str | None = None,
    threshold: float = 0.88,
    max_rows: int = 5000,
) -> str:
    """
    Try to map a normalized_name to an already-existing normalized_name in DB.

    Purpose:
      - If two sites normalize to slightly different outputs, pick the "canonical"
        one you already have, so matching is stable over time.

    Strategy:
      - Jaccard similarity on token sets.
      - Prefer same category (if provided).
      - Prefer shorter existing names when scores tie.

    If no match above threshold, returns the input unchanged.
    """
    src = (normalized_name or "").strip()
    if not src:
        return ""

    src_tokens = _tokenize(src)

    q = db.query(CompetitorProduct.normalized_name).filter(CompetitorProduct.normalized_name.isnot(None))
    if website:
        q = q.filter(CompetitorProduct.website == website)
    if category:
        q = q.filter(CompetitorProduct.category == category)

    # Fetch a bounded set. In practice your competitor table is not huge.
    rows = q.limit(max_rows).all()
    best_name = src
    best_score = 0.0

    for (cand,) in rows:
        cand = (cand or "").strip()
        if not cand or cand == src:
            continue
        score = _jaccard(src_tokens, _tokenize(cand))
        if score > best_score:
            best_score = score
            best_name = cand
        elif score == best_score and score > 0:
            # tie-break: shorter canonical wins
            if len(cand) < len(best_name):
                best_name = cand

    return best_name if best_score >= threshold else src
