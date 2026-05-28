import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from sift.config import RelevanceConfig
from sift.models import FeedbackItem, ProductContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelevanceStats:
    total: int
    kept: int
    rejected: int
    threshold: float
    relaxed: bool = False


class RelevanceFilter:
    """Filters scraped candidates to feedback about the resolved product."""

    def __init__(self, config: RelevanceConfig):
        self.config = config

    def filter(
        self,
        items: list[FeedbackItem],
        context: ProductContext,
    ) -> tuple[list[FeedbackItem], RelevanceStats]:
        if not self.config.enabled:
            return items, RelevanceStats(
                total=len(items),
                kept=len(items),
                rejected=0,
                threshold=self.config.threshold,
            )

        scored = [(item, self.score(item, context)) for item in items]
        kept = [
            item
            for item, score in scored
            if score >= self.config.threshold
        ]
        relaxed = False

        if len(kept) < self.config.min_items_before_relaxing:
            fallback = [
                item
                for item, score in scored
                if score > 0 and not item.metadata.get("rejection_reason")
            ]
            if len(fallback) > len(kept):
                kept = fallback
                relaxed = True

        kept_ids = {item.id for item in kept}
        for item, score in scored:
            if item.id not in kept_ids and not item.metadata.get("rejection_reason"):
                item.metadata["rejection_reason"] = f"relevance score {score:.2f} below threshold"

        rejected = len(items) - len(kept)
        if rejected:
            logger.info(
                "Relevance filter rejected %d/%d item(s) for '%s'.",
                rejected,
                len(items),
                context.canonical_name,
            )

        return kept, RelevanceStats(
            total=len(items),
            kept=len(kept),
            rejected=rejected,
            threshold=self.config.threshold,
            relaxed=relaxed,
        )

    def score(self, item: FeedbackItem, context: ProductContext) -> float:
        text = _normalize_text(item.text)
        url = item.url or ""
        metadata_text = _normalize_text(" ".join(_flatten_metadata(item.metadata)))
        matched_aliases = _matches_terms(text, context.search_terms)
        matched_identifiers = _matches_identifiers(item, context)
        matched_context = _matches_context_terms(text, context)
        matched_negatives = _matches_terms(text, context.negative_terms)

        score = 0.0
        reasons: list[str] = []

        if matched_identifiers:
            score += 0.75
            reasons.extend(f"identifier:{term}" for term in matched_identifiers)

        if matched_aliases:
            score += 0.55
            reasons.extend(f"alias:{term}" for term in matched_aliases)

        if context.website and _host_matches(url, context.website):
            score += 0.35
            reasons.append("website")

        metadata_aliases = _matches_terms(metadata_text, context.search_terms)
        if metadata_aliases:
            score += 0.45
            reasons.extend(f"metadata:{term}" for term in metadata_aliases)

        if matched_context:
            score += min(0.25, 0.08 * len(matched_context))
            reasons.extend(f"context:{term}" for term in matched_context)

        if matched_negatives:
            score -= min(0.55, 0.18 * len(matched_negatives))
            reasons.extend(f"negative:{term}" for term in matched_negatives)

        score = max(0.0, min(1.0, score))
        item.metadata["relevance_score"] = round(score, 3)
        item.metadata["matched_aliases"] = matched_aliases
        item.metadata["matched_identifiers"] = matched_identifiers
        item.metadata["matched_context_terms"] = matched_context
        if matched_negatives:
            item.metadata["negative_terms"] = matched_negatives
            if score < self.config.threshold:
                item.metadata["rejection_reason"] = (
                    "matched negative context: " + ", ".join(matched_negatives)
                )
        item.metadata["relevance_reasons"] = reasons
        return score


def _matches_identifiers(item: FeedbackItem, context: ProductContext) -> list[str]:
    values = _normalize_text(" ".join([
        item.url or "",
        *(_flatten_metadata(item.metadata)),
    ]))
    return [
        term
        for term in context.identifiers
        if _normalize_text(term) and _normalize_text(term) in values
    ]


def _matches_context_terms(text: str, context: ProductContext) -> list[str]:
    terms = [context.category, *re.split(r"[\s,/.-]+", context.description)]
    useful = [
        term
        for term in terms
        if len(term.strip()) >= 4
    ]
    return _matches_terms(text, useful)


def _matches_terms(text: str, terms: tuple[str, ...] | list[str]) -> list[str]:
    matches: list[str] = []
    for term in terms:
        normalized = _normalize_text(term)
        if not normalized:
            continue
        if _term_in_text(normalized, text):
            matches.append(term)
    return matches


def _term_in_text(term: str, text: str) -> bool:
    if not term:
        return False
    if " " in term or "-" in term or "_" in term:
        return term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _flatten_metadata(metadata: dict) -> list[str]:
    values: list[str] = []
    for value in metadata.values():
        if isinstance(value, (str, int, float)):
            values.append(str(value))
        elif isinstance(value, list):
            values.extend(str(v) for v in value if isinstance(v, (str, int, float)))
        elif isinstance(value, dict):
            values.extend(str(v) for v in value.values() if isinstance(v, (str, int, float)))
    return values


def _host_matches(url: str, website: str) -> bool:
    if not url or not website:
        return False
    url_host = urlparse(url).netloc.casefold()
    website_host = urlparse(website if "://" in website else f"https://{website}").netloc.casefold()
    return bool(url_host and website_host and url_host.endswith(website_host))


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).casefold()).strip()
