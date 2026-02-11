from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawArticle:
    """Intermediate representation from fetchers before filtering."""
    url: str
    title: str
    source: str
    source_id: str = ""
    author: str = ""
    published_at: datetime | None = None
    snippet: str = ""
    thumbnail_url: str = ""


@dataclass
class Article:
    """Full article stored in the database."""
    id: int | None = None
    url: str = ""
    title: str = ""
    source: str = ""
    source_id: str = ""
    author: str = ""
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    snippet: str = ""
    summary: str | None = None
    relevance_score: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    is_read: bool = False
    thumbnail_url: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Article:
        return cls(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            source=row["source"],
            source_id=row.get("source_id", ""),
            author=row.get("author", ""),
            published_at=datetime.fromisoformat(row["published_at"]) if row.get("published_at") else None,
            fetched_at=datetime.fromisoformat(row["fetched_at"]) if row.get("fetched_at") else None,
            snippet=row.get("snippet", ""),
            summary=row.get("summary"),
            relevance_score=row.get("relevance_score", 0.0),
            matched_keywords=json.loads(row["matched_keywords"]) if row.get("matched_keywords") else [],
            tags=json.loads(row["tags"]) if row.get("tags") else [],
            is_read=bool(row.get("is_read", 0)),
            thumbnail_url=row.get("thumbnail_url", ""),
        )
