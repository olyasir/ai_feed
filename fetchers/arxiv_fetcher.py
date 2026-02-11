from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import aiohttp
import feedparser

from core.config_loader import get_config
from core.models import RawArticle
from fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"


class ArxivFetcher(BaseFetcher):
    source_name = "arxiv"

    async def fetch(self) -> list[RawArticle]:
        config = get_config()
        arxiv_cfg = config.get("arxiv", {})
        categories = arxiv_cfg.get("categories", ["cs.AI", "cs.LG"])
        max_results = arxiv_cfg.get("max_results", 200)
        delay = arxiv_cfg.get("delay_between_calls", 3)

        articles: list[RawArticle] = []

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            for i, cat in enumerate(categories):
                if i > 0:
                    await asyncio.sleep(delay)

                query = f"cat:{cat}"
                params = {
                    "search_query": query,
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }

                try:
                    async with session.get(ARXIV_API, params=params) as resp:
                        if resp.status != 200:
                            logger.warning("Arxiv %s returned status %d", cat, resp.status)
                            continue
                        body = await resp.text()
                except Exception as e:
                    logger.warning("Arxiv %s fetch error: %s", cat, e)
                    continue

                parsed = feedparser.parse(body)
                for entry in parsed.entries:
                    link = entry.get("link", "")
                    if not link:
                        continue

                    published = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            from time import mktime
                            published = datetime.fromtimestamp(mktime(entry.published_parsed))
                        except Exception:
                            pass

                    snippet = entry.get("summary", "").replace("\n", " ").strip()

                    authors = ""
                    if hasattr(entry, "authors"):
                        authors = ", ".join(a.get("name", "") for a in entry.authors[:3])
                        if len(entry.authors) > 3:
                            authors += " et al."

                    articles.append(RawArticle(
                        url=link,
                        title=entry.get("title", "Untitled").replace("\n", " "),
                        source="Arxiv",
                        source_id=entry.get("id", link),
                        author=authors,
                        published_at=published,
                        snippet=snippet[:300],
                    ))

        logger.info("Arxiv fetched %d articles from %d categories", len(articles), len(categories))
        return articles
