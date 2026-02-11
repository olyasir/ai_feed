from __future__ import annotations

import logging
from datetime import datetime
from time import mktime

import aiohttp
import feedparser

from core.config_loader import get_config
from core.models import RawArticle
from fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)


class RSSFetcher(BaseFetcher):
    source_name = "rss"

    async def fetch(self) -> list[RawArticle]:
        config = get_config()
        feeds = config.get("rss_feeds", [])
        articles: list[RawArticle] = []

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            for feed_info in feeds:
                name = feed_info["name"]
                url = feed_info["url"]
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            logger.warning("RSS %s returned status %d", name, resp.status)
                            continue
                        body = await resp.text()
                except Exception as e:
                    logger.warning("RSS %s fetch error: %s", name, e)
                    continue

                parsed = feedparser.parse(body)
                for entry in parsed.entries:
                    published = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            published = datetime.fromtimestamp(mktime(entry.published_parsed))
                        except Exception:
                            pass
                    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                        try:
                            published = datetime.fromtimestamp(mktime(entry.updated_parsed))
                        except Exception:
                            pass

                    link = entry.get("link", "")
                    if not link:
                        continue

                    snippet = entry.get("summary", "")
                    # Strip HTML tags simply
                    if "<" in snippet:
                        import re
                        snippet = re.sub(r"<[^>]+>", " ", snippet)
                        snippet = re.sub(r"\s+", " ", snippet).strip()

                    thumbnail = ""
                    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                        thumbnail = entry.media_thumbnail[0].get("url", "")
                    elif hasattr(entry, "media_content") and entry.media_content:
                        for mc in entry.media_content:
                            if mc.get("medium") == "image" or mc.get("type", "").startswith("image"):
                                thumbnail = mc.get("url", "")
                                break

                    articles.append(RawArticle(
                        url=link,
                        title=entry.get("title", "Untitled"),
                        source=name,
                        source_id=entry.get("id", link),
                        author=entry.get("author", ""),
                        published_at=published,
                        snippet=snippet[:300],
                        thumbnail_url=thumbnail,
                    ))

        logger.info("RSS fetched %d articles from %d feeds", len(articles), len(feeds))
        return articles
