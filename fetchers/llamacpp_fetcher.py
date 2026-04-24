from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiohttp

from core.database import get_existing_urls
from core.models import RawArticle
from fetchers.base import BaseFetcher
from plugins.summarizer import summarize_llamacpp_release

logger = logging.getLogger(__name__)

GH_API = "https://api.github.com"
REPO = "ggml-org/llama.cpp"


class LlamaCppFetcher(BaseFetcher):
    source_name = "llamacpp"

    async def fetch(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ai-feed-aggregator/1.0",
        }

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers=headers,
        ) as session:
            releases = await self._fetch_releases(session)
            articles.extend(releases)

            hot_issues = await self._fetch_hot_issues(session)
            articles.extend(hot_issues)

            discussions = await self._fetch_recent_prs(session)
            articles.extend(discussions)

        logger.info("llama.cpp fetched %d items (releases: %d, issues: %d, PRs: %d)",
                     len(articles), len(releases), len(hot_issues), len(discussions))
        return articles

    async def _fetch_releases(self, session: aiohttp.ClientSession) -> list[RawArticle]:
        """Fetch recent releases — new features, breaking changes."""
        articles = []
        try:
            url = f"{GH_API}/repos/{REPO}/releases"
            params = {"per_page": "10"}
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning("llama.cpp releases returned status %d", resp.status)
                    return []
                releases = await resp.json()

            # Skip AI summarization for releases we already have — avoids re-calling
            # the API on every fetch cycle.
            release_urls = [r.get("html_url", "") for r in releases if r.get("html_url")]
            existing = await get_existing_urls(release_urls)

            for rel in releases:
                tag = rel.get("tag_name", "")
                name = rel.get("name", "") or tag
                body = rel.get("body", "") or ""
                html_url = rel.get("html_url", "")
                if not html_url:
                    continue

                # Trim body to key points
                snippet = body[:300].replace("\r\n", " ").replace("\n", " ")

                published = None
                if ts := rel.get("published_at"):
                    try:
                        published = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                summary = None
                if html_url not in existing:
                    summary = await summarize_llamacpp_release(name, body)

                articles.append(RawArticle(
                    url=html_url,
                    title=f"[llama.cpp Release] {name}",
                    source="llama.cpp",
                    source_id=f"llamacpp-rel-{tag}",
                    author=rel.get("author", {}).get("login", ""),
                    published_at=published,
                    snippet=snippet,
                    summary=summary,
                ))
        except Exception as e:
            logger.warning("llama.cpp releases fetch error: %s", e)
        return articles

    async def _fetch_hot_issues(self, session: aiohttp.ClientSession) -> list[RawArticle]:
        """Fetch recent issues with most comments — shows what people are talking about."""
        articles = []
        try:
            cutoff = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
            url = f"{GH_API}/repos/{REPO}/issues"
            params = {
                "state": "all",
                "sort": "comments",
                "direction": "desc",
                "since": f"{cutoff}T00:00:00Z",
                "per_page": "25",
            }
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning("llama.cpp issues returned status %d", resp.status)
                    return []
                issues = await resp.json()

            for issue in issues:
                # Skip pull requests (they also appear in issues endpoint)
                if issue.get("pull_request"):
                    continue

                html_url = issue.get("html_url", "")
                title = issue.get("title", "")
                if not html_url or not title:
                    continue

                comments = issue.get("comments", 0)
                labels = [l.get("name", "") for l in issue.get("labels", [])]
                label_str = ", ".join(labels[:4]) if labels else ""
                body = (issue.get("body", "") or "")[:200].replace("\r\n", " ").replace("\n", " ")

                snippet_parts = []
                if body:
                    snippet_parts.append(body)
                snippet_parts.append(f"Comments: {comments}")
                if label_str:
                    snippet_parts.append(f"Labels: {label_str}")
                snippet = " | ".join(snippet_parts)

                created = None
                if ts := issue.get("created_at"):
                    try:
                        created = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                articles.append(RawArticle(
                    url=html_url,
                    title=f"[llama.cpp Issue] {title}",
                    source="llama.cpp",
                    source_id=f"llamacpp-issue-{issue.get('number', '')}",
                    author=issue.get("user", {}).get("login", ""),
                    published_at=created,
                    snippet=snippet[:300],
                ))
        except Exception as e:
            logger.warning("llama.cpp issues fetch error: %s", e)
        return articles

    async def _fetch_recent_prs(self, session: aiohttp.ClientSession) -> list[RawArticle]:
        """Fetch recently merged PRs — shows what features are landing."""
        articles = []
        try:
            # Search for recently merged PRs
            cutoff = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
            url = f"{GH_API}/search/issues"
            params = {
                "q": f"repo:{REPO} is:pr is:merged merged:>={cutoff}",
                "sort": "comments",
                "order": "desc",
                "per_page": "20",
            }
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning("llama.cpp PRs search returned status %d", resp.status)
                    return []
                data = await resp.json()

            for pr in data.get("items", []):
                html_url = pr.get("html_url", "")
                title = pr.get("title", "")
                if not html_url or not title:
                    continue

                comments = pr.get("comments", 0)
                labels = [l.get("name", "") for l in pr.get("labels", [])]
                label_str = ", ".join(labels[:4]) if labels else ""
                body = (pr.get("body", "") or "")[:200].replace("\r\n", " ").replace("\n", " ")

                snippet_parts = []
                if body:
                    snippet_parts.append(body)
                snippet_parts.append(f"Comments: {comments}")
                if label_str:
                    snippet_parts.append(f"Labels: {label_str}")
                snippet = " | ".join(snippet_parts)

                created = None
                if ts := pr.get("closed_at") or pr.get("created_at"):
                    try:
                        created = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                articles.append(RawArticle(
                    url=html_url,
                    title=f"[llama.cpp PR Merged] {title}",
                    source="llama.cpp",
                    source_id=f"llamacpp-pr-{pr.get('number', '')}",
                    author=pr.get("user", {}).get("login", ""),
                    published_at=created,
                    snippet=snippet[:300],
                ))
        except Exception as e:
            logger.warning("llama.cpp PRs fetch error: %s", e)
        return articles
