from __future__ import annotations

from abc import ABC, abstractmethod

from core.models import RawArticle


class BaseFetcher(ABC):
    """Abstract base for all feed fetchers."""

    source_name: str = "unknown"

    @abstractmethod
    async def fetch(self) -> list[RawArticle]:
        """Fetch raw articles from the source. Must not raise — return empty list on error."""
        ...
