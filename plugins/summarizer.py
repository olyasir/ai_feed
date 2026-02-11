from __future__ import annotations

from abc import ABC, abstractmethod


class BaseSummarizer(ABC):
    """Interface for future AI summarization plugins."""

    @abstractmethod
    async def summarize(self, title: str, text: str) -> str:
        """Return a concise summary of the article text."""
        ...


class NoOpSummarizer(BaseSummarizer):
    """Default no-op summarizer. Returns empty string."""

    async def summarize(self, title: str, text: str) -> str:
        return ""
