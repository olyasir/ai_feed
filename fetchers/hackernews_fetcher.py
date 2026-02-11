from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import aiohttp

from core.config_loader import get_config
from core.models import RawArticle
from fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)

HN_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"


class HackerNewsFetcher(BaseFetcher):
    source_name = "hackernews"

    async def fetch(self) -> list[RawArticle]:
        config = get_config()
        hn_cfg = config.get("hackernews", {})
        top_n = hn_cfg.get("top_stories_count", 100)
        concurrency = hn_cfg.get("concurrency", 10)

        articles: list[RawArticle] = []
        semaphore = asyncio.Semaphore(concurrency)

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            # Get top story IDs
            try:
                async with session.get(HN_TOP) as resp:
                    if resp.status != 200:
                        logger.warning("HN top stories returned status %d", resp.status)
                        return []
                    story_ids = await resp.json()
            except Exception as e:
                logger.warning("HN top stories fetch error: %s", e)
                return []

            story_ids = story_ids[:top_n]

            async def fetch_item(item_id: int) -> RawArticle | None:
                async with semaphore:
                    try:
                        async with session.get(HN_ITEM.format(item_id)) as resp:
                            if resp.status != 200:
                                return None
                            data = await resp.json()
                    except Exception:
                        return None

                if not data or data.get("type") != "story":
                    return None

                url = data.get("url", "")
                if not url:
                    # Self-post
                    url = f"https://news.ycombinator.com/item?id={item_id}"

                title = data.get("title", "")
                if not title:
                    return None

                published = None
                if ts := data.get("time"):
                    try:
                        published = datetime.fromtimestamp(ts)
                    except Exception:
                        pass

                snippet = data.get("text", "") or ""
                if "<" in snippet:
                    import re
                    snippet = re.sub(r"<[^>]+>", " ", snippet)
                    snippet = re.sub(r"\s+", " ", snippet).strip()

                return RawArticle(
                    url=url,
                    title=title,
                    source="Hacker News",
                    source_id=str(item_id),
                    author=data.get("by", ""),
                    published_at=published,
                    snippet=snippet[:300],
                )

            tasks = [fetch_item(sid) for sid in story_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, RawArticle):
                    articles.append(r)

        logger.info("HN fetched %d articles", len(articles))
        return articles
