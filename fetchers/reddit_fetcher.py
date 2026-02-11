from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import aiohttp

from core.config_loader import get_config
from core.models import RawArticle
from fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)


class RedditFetcher(BaseFetcher):
    source_name = "reddit"

    async def fetch(self) -> list[RawArticle]:
        config = get_config()
        reddit_cfg = config.get("reddit", {})
        client_id = reddit_cfg.get("client_id", "")
        client_secret = reddit_cfg.get("client_secret", "")
        subreddits = reddit_cfg.get("subreddits", [])
        limit = reddit_cfg.get("post_limit", 50)

        if client_id and client_secret:
            try:
                return await self._fetch_praw(client_id, client_secret, reddit_cfg, subreddits, limit)
            except Exception as e:
                logger.warning("PRAW failed, falling back to public JSON: %s", e)

        return await self._fetch_public_json(subreddits, limit)

    async def _fetch_praw(
        self,
        client_id: str,
        client_secret: str,
        reddit_cfg: dict,
        subreddits: list[str],
        limit: int,
    ) -> list[RawArticle]:
        import praw

        def _praw_work() -> list[RawArticle]:
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=reddit_cfg.get("user_agent", "ai_feed_aggregator/1.0"),
            )
            articles: list[RawArticle] = []
            for sub_name in subreddits:
                try:
                    subreddit = reddit.subreddit(sub_name)
                    for post in subreddit.hot(limit=limit):
                        url = post.url if post.url and not post.is_self else f"https://reddit.com{post.permalink}"
                        published = None
                        try:
                            published = datetime.fromtimestamp(post.created_utc)
                        except Exception:
                            pass
                        snippet = (post.selftext or "")[:300]
                        articles.append(RawArticle(
                            url=url,
                            title=post.title,
                            source=f"r/{sub_name}",
                            source_id=post.id,
                            author=str(post.author) if post.author else "",
                            published_at=published,
                            snippet=snippet,
                            thumbnail_url=post.thumbnail if post.thumbnail and post.thumbnail.startswith("http") else "",
                        ))
                except Exception as e:
                    logger.warning("PRAW error on r/%s: %s", sub_name, e)
            return articles

        return await asyncio.to_thread(_praw_work)

    async def _fetch_public_json(self, subreddits: list[str], limit: int) -> list[RawArticle]:
        articles: list[RawArticle] = []
        headers = {"User-Agent": "ai_feed_aggregator/1.0"}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers=headers) as session:
            for sub_name in subreddits:
                url = f"https://www.reddit.com/r/{sub_name}/hot.json?limit={limit}"
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            logger.warning("Reddit JSON r/%s returned status %d", sub_name, resp.status)
                            continue
                        data = await resp.json()
                except Exception as e:
                    logger.warning("Reddit JSON r/%s error: %s", sub_name, e)
                    continue

                for child in data.get("data", {}).get("children", []):
                    post = child.get("data", {})
                    if not post:
                        continue

                    is_self = post.get("is_self", False)
                    post_url = post.get("url", "")
                    if not post_url or is_self:
                        post_url = f"https://reddit.com{post.get('permalink', '')}"

                    published = None
                    if ts := post.get("created_utc"):
                        try:
                            published = datetime.fromtimestamp(ts)
                        except Exception:
                            pass

                    snippet = (post.get("selftext", "") or "")[:300]
                    thumbnail = post.get("thumbnail", "")
                    if thumbnail and not thumbnail.startswith("http"):
                        thumbnail = ""

                    articles.append(RawArticle(
                        url=post_url,
                        title=post.get("title", "Untitled"),
                        source=f"r/{sub_name}",
                        source_id=post.get("id", ""),
                        author=post.get("author", ""),
                        published_at=published,
                        snippet=snippet,
                        thumbnail_url=thumbnail,
                    ))

                # Small delay between subreddit requests
                await asyncio.sleep(1)

        logger.info("Reddit (public JSON) fetched %d articles", len(articles))
        return articles
