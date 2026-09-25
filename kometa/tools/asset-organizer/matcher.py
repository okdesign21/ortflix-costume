"""Confidence-scored title matching against the authoritative Plex index.

Replaces "reconstruct the correct name via regex" with "find the closest
known-good name in the set of names Plex already has" — a strictly smaller
and more reliable search space. When nothing matches with reasonable
confidence, the item is never silently guessed: it's recorded in a
:class:`MatchReview` so the operator can see it after the run (instead of
discovering a wrong/duplicate folder weeks later).

Lookup order for a given category (e.g. ``movies_shows``):

  1. ``exception_mappings.json`` — exact override, always wins (kept for
     genuine one-offs like Kometa ``title_override``/``name_mapping`` cases).
  2. Exact match against the Plex index (loose-normalized comparison).
  3. Fuzzy match against the Plex index (``difflib``, stdlib only).
  4. Unmatched — caller decides the fallback (legacy normalization rules);
     recorded in the review log regardless.
"""

from __future__ import annotations

import difflib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from plex_index import PlexIndex, normalize_key

logger = logging.getLogger(__name__)

DEFAULT_FUZZY_CUTOFF = 0.86


@dataclass
class MatchResult:
    """Outcome of matching a source name against one Plex index category."""

    canonical: Optional[str]
    confidence: float  # 1.0 = exact/override, 0.0-1.0 = fuzzy ratio, 0.0 = unmatched
    method: str  # "exception" | "exact" | "fuzzy" | "unmatched"

    @property
    def matched(self) -> bool:
        return self.canonical is not None


@dataclass
class MatchReview:
    """Collects low-confidence and unmatched results for end-of-run reporting."""

    entries: list[dict] = field(default_factory=list)

    def record(self, category: str, source_name: str, result: MatchResult) -> None:
        if result.method in ("exception", "exact"):
            return  # high-confidence, nothing to review
        self.entries.append(
            {
                "category": category,
                "source": source_name,
                "canonical": result.canonical,
                "confidence": round(result.confidence, 3),
                "method": result.method,
            }
        )

    def unmatched(self) -> list[dict]:
        return [e for e in self.entries if e["method"] == "unmatched"]

    def fuzzy(self) -> list[dict]:
        return [e for e in self.entries if e["method"] == "fuzzy"]

    def is_clean(self) -> bool:
        return not self.entries

    def save(self, path: Path) -> None:
        if not self.entries:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def log_summary(self) -> None:
        unmatched = self.unmatched()
        fuzzy = self.fuzzy()
        if fuzzy:
            logger.warning(
                "Plex match review: %d fuzzy match(es) below full confidence — please verify:",
                len(fuzzy),
            )
            for e in fuzzy:
                logger.warning(
                    "  [FUZZY %.0f%%] %s -> %r (%s)",
                    e["confidence"] * 100,
                    e["source"],
                    e["canonical"],
                    e["category"],
                )
        if unmatched:
            logger.warning(
                "Plex match review: %d item(s) not found in Plex (%s):",
                len(unmatched),
                "using legacy normalization as fallback",
            )
            for e in unmatched:
                logger.warning("  [UNMATCHED] %s (%s)", e["source"], e["category"])


class TitleMatcher:
    """Matches source names to canonical Plex names, per asset category."""

    def __init__(
        self,
        index: Optional[PlexIndex],
        exception_mappings: Optional[dict[str, str]] = None,
        fuzzy_cutoff: float = DEFAULT_FUZZY_CUTOFF,
        review: Optional[MatchReview] = None,
    ) -> None:
        self.index = index
        self.exception_mappings = exception_mappings or {}
        self.fuzzy_cutoff = fuzzy_cutoff
        self.review = review if review is not None else MatchReview()

    @property
    def enabled(self) -> bool:
        return self.index is not None and not self.index.is_empty()

    def match(self, category: str | Iterable[str], source_name: str) -> MatchResult:
        """Match ``source_name`` (a pre-cleaned candidate title) within ``category``.

        ``category`` may be a single Plex index table name (e.g. ``"people"``)
        or an ordered iterable of table names to try, useful when a source
        name is inherently ambiguous — e.g. a top-level ``Movies_Shows``
        poster file may be a franchise/collection poster ("Cars") or a
        standalone movie/show title, so callers pass
        ``("collections", "movies_shows")`` and the best match across both
        tables wins.
        """
        categories = (category,) if isinstance(category, str) else tuple(category)
        review_label = "/".join(categories)

        override = self.exception_mappings.get(source_name)
        if override:
            result = MatchResult(canonical=override, confidence=1.0, method="exception")
            self.review.record(review_label, source_name, result)
            return result

        if not self.enabled:
            result = MatchResult(canonical=None, confidence=0.0, method="unmatched")
            self.review.record(review_label, source_name, result)
            return result

        key = normalize_key(source_name)

        # Exact match: check every table before falling back to fuzzy matching
        # anywhere, so an exact hit in a later category always wins over a
        # fuzzy hit in an earlier one.
        for cat in categories:
            exact = self.index.get(cat).get(key)
            if exact:
                result = MatchResult(canonical=exact, confidence=1.0, method="exact")
                self.review.record(review_label, source_name, result)
                return result

        best_ratio = 0.0
        best_canonical: str | None = None
        for cat in categories:
            table = self.index.get(cat)
            candidates = difflib.get_close_matches(
                key, table.keys(), n=1, cutoff=self.fuzzy_cutoff
            )
            if not candidates:
                continue
            best_key = candidates[0]
            ratio = difflib.SequenceMatcher(None, key, best_key).ratio()
            if ratio > best_ratio:
                best_ratio, best_canonical = ratio, table[best_key]

        if best_canonical is not None:
            result = MatchResult(canonical=best_canonical, confidence=best_ratio, method="fuzzy")
            self.review.record(review_label, source_name, result)
            return result

        result = MatchResult(canonical=None, confidence=0.0, method="unmatched")
        self.review.record(review_label, source_name, result)
        return result

