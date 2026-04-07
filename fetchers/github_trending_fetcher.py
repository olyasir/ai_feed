from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import aiohttp

from core.models import RawArticle
from fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)

# GitHub search API — find recently created/updated repos with high stars
GH_SEARCH_REPOS = "https://api.github.com/search/repositories"

# Topics to search for trending AI/agent/local-inference repos
SEARCH_QUERIES = [
    "ai agent stars:>10",
    "local llm stars:>10",
    "gguf stars:>5",
    "llama.cpp stars:>5",
    "tool calling llm stars:>5",
    "on-device inference stars:>5",
    "multi-agent stars:>10",
    "mcp server stars:>5",
]


class GitHubTrendingFetcher(BaseFetcher):
    source_name = "github"

    async def fetch(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        seen_urls: set[str] = set()
        cutoff = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "ai-feed-aggregator/1.0",
            },
        ) as session:
            for query in SEARCH_QUERIES:
                try:
                    full_query = f"{query} pushed:>={cutoff}"
                    params = {
                        "q": full_query,
                        "sort": "stars",
                        "order": "desc",
                        "per_page": "15",
                    }
                    async with session.get(GH_SEARCH_REPOS, params=params) as resp:
                        if resp.status == 403:
                            logger.warning("GitHub rate limited, stopping fetcher")
                            break
                        if resp.status != 200:
                            logger.warning("GitHub search returned status %d for query '%s'", resp.status, query)
                            continue
                        data = await resp.json()

                    for repo in data.get("items", []):
                        url = repo.get("html_url", "")
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)

                        full_name = repo.get("full_name", "")
                        description = repo.get("description", "") or ""
                        stars = repo.get("stargazers_count", 0)
                        language = repo.get("language", "") or ""
                        topics = repo.get("topics", [])
                        forks = repo.get("forks_count", 0)

                        topic_str = ", ".join(topics[:6]) if topics else ""
                        snippet_parts = [description[:200]]
                        if language:
                            snippet_parts.append(f"Lang: {language}")
                        snippet_parts.append(f"Stars: {stars:,}, Forks: {forks:,}")
                        if topic_str:
                            snippet_parts.append(f"Topics: {topic_str}")
                        snippet = " | ".join(snippet_parts)

                        created = None
                        if ts := repo.get("pushed_at"):
                            try:
                                created = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                            except Exception:
                                pass

                        articles.append(RawArticle(
                            url=url,
                            title=f"[GitHub] {full_name}: {description[:80]}" if description else f"[GitHub] {full_name}",
                            source="GitHub",
                            source_id=f"gh-{repo.get('id', '')}",
                            author=repo.get("owner", {}).get("login", ""),
                            published_at=created,
                            snippet=snippet[:300],
                        ))

                except Exception as e:
                    logger.warning("GitHub search error for query '%s': %s", query, e)

        logger.info("GitHub Trending fetched %d repos", len(articles))
        return articles
