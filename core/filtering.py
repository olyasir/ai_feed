from __future__ import annotations

from datetime import datetime

from core.config_loader import get_config
from core.models import Article, RawArticle


def filter_and_score(raw_articles: list[RawArticle]) -> list[Article]:
    """Filter raw articles by keyword matching and return scored Article objects."""
    config = get_config()
    topics = config.get("topics", {})

    # Build lookup: keyword_lower -> (topic_key, original_keyword)
    keyword_map: dict[str, tuple[str, str]] = {}
    for topic_key, topic_data in topics.items():
        for kw in topic_data.get("keywords", []):
            keyword_map[kw.lower()] = (topic_key, kw)

    results: list[Article] = []

    for raw in raw_articles:
        title_lower = raw.title.lower()
        snippet_lower = raw.snippet.lower()

        matched: list[str] = []
        matched_topics: set[str] = set()
        score = 0.0

        for kw_lower, (topic_key, original_kw) in keyword_map.items():
            title_hit = kw_lower in title_lower
            snippet_hit = kw_lower in snippet_lower

            if title_hit or snippet_hit:
                matched.append(original_kw)
                matched_topics.add(topic_key)
                if title_hit:
                    score += 2.0
                if snippet_hit:
                    score += 1.0

        if not matched:
            continue

        results.append(Article(
            url=raw.url,
            title=raw.title,
            source=raw.source,
            source_id=raw.source_id,
            author=raw.author,
            published_at=raw.published_at,
            fetched_at=datetime.utcnow(),
            snippet=raw.snippet[:300],
            relevance_score=score,
            matched_keywords=matched,
            tags=sorted(matched_topics),
            thumbnail_url=raw.thumbnail_url,
        ))

    return results
