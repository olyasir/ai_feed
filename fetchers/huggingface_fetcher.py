from __future__ import annotations

import logging
from datetime import datetime

import aiohttp

from core.models import RawArticle
from fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)

# HuggingFace API endpoints
HF_TRENDING_MODELS = "https://huggingface.co/api/models"
HF_TRENDING_SPACES = "https://huggingface.co/api/spaces"


class HuggingFaceFetcher(BaseFetcher):
    source_name = "huggingface"

    async def fetch(self) -> list[RawArticle]:
        articles: list[RawArticle] = []

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            # Fetch trending GGUF models (sorted by recent downloads)
            gguf_articles = await self._fetch_gguf_models(session)
            articles.extend(gguf_articles)

            # Fetch trending models (general, sorted by trending)
            trending_articles = await self._fetch_trending_models(session)
            articles.extend(trending_articles)

            # Fetch trending spaces (often showcase agent demos)
            spaces_articles = await self._fetch_trending_spaces(session)
            articles.extend(spaces_articles)

        logger.info("HuggingFace fetched %d items (GGUF: %d, trending: %d, spaces: %d)",
                     len(articles), len(gguf_articles), len(trending_articles), len(spaces_articles))
        return articles

    async def _fetch_gguf_models(self, session: aiohttp.ClientSession) -> list[RawArticle]:
        """Fetch recently popular GGUF models."""
        articles = []
        try:
            params = {
                "search": "gguf",
                "sort": "downloads",
                "direction": "-1",
                "limit": "30",
            }
            async with session.get(HF_TRENDING_MODELS, params=params) as resp:
                if resp.status != 200:
                    logger.warning("HF GGUF models returned status %d", resp.status)
                    return []
                models = await resp.json()

            for model in models:
                model_id = model.get("modelId", model.get("id", ""))
                if not model_id:
                    continue

                tags = model.get("tags", [])
                pipeline_tag = model.get("pipeline_tag", "")
                downloads = model.get("downloads", 0)
                likes = model.get("likes", 0)

                tag_str = ", ".join(tags[:5]) if tags else pipeline_tag
                snippet = f"GGUF model — {tag_str}. Downloads: {downloads:,}, Likes: {likes:,}"

                created = None
                if ts := model.get("createdAt"):
                    try:
                        created = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                articles.append(RawArticle(
                    url=f"https://huggingface.co/{model_id}",
                    title=f"[GGUF] {model_id}",
                    source="HuggingFace",
                    source_id=f"hf-model-{model_id}",
                    author=model_id.split("/")[0] if "/" in model_id else "",
                    published_at=created,
                    snippet=snippet[:300],
                ))

        except Exception as e:
            logger.warning("HF GGUF models fetch error: %s", e)

        return articles

    async def _fetch_trending_models(self, session: aiohttp.ClientSession) -> list[RawArticle]:
        """Fetch trending models relevant to local inference."""
        articles = []
        try:
            params = {
                "sort": "trending",
                "direction": "-1",
                "limit": "30",
            }
            async with session.get(HF_TRENDING_MODELS, params=params) as resp:
                if resp.status != 200:
                    logger.warning("HF trending models returned status %d", resp.status)
                    return []
                models = await resp.json()

            for model in models:
                model_id = model.get("modelId", model.get("id", ""))
                if not model_id:
                    continue

                tags = model.get("tags", [])
                pipeline_tag = model.get("pipeline_tag", "")
                downloads = model.get("downloads", 0)
                likes = model.get("likes", 0)

                tag_str = ", ".join(tags[:5]) if tags else pipeline_tag
                snippet = f"Trending model — {tag_str}. Downloads: {downloads:,}, Likes: {likes:,}"

                created = None
                if ts := model.get("createdAt"):
                    try:
                        created = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                articles.append(RawArticle(
                    url=f"https://huggingface.co/{model_id}",
                    title=f"[Trending] {model_id}",
                    source="HuggingFace",
                    source_id=f"hf-trending-{model_id}",
                    author=model_id.split("/")[0] if "/" in model_id else "",
                    published_at=created,
                    snippet=snippet[:300],
                ))

        except Exception as e:
            logger.warning("HF trending models fetch error: %s", e)

        return articles

    async def _fetch_trending_spaces(self, session: aiohttp.ClientSession) -> list[RawArticle]:
        """Fetch trending Spaces — often agent demos and local AI tools."""
        articles = []
        try:
            params = {
                "sort": "trending",
                "direction": "-1",
                "limit": "20",
            }
            async with session.get(HF_TRENDING_SPACES, params=params) as resp:
                if resp.status != 200:
                    logger.warning("HF trending spaces returned status %d", resp.status)
                    return []
                spaces = await resp.json()

            for space in spaces:
                space_id = space.get("id", "")
                if not space_id:
                    continue

                tags = space.get("tags", [])
                likes = space.get("likes", 0)
                sdk = space.get("sdk", "")

                tag_str = ", ".join(tags[:5]) if tags else ""
                snippet = f"Trending Space (SDK: {sdk}). {tag_str}. Likes: {likes:,}"

                created = None
                if ts := space.get("createdAt"):
                    try:
                        created = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                articles.append(RawArticle(
                    url=f"https://huggingface.co/spaces/{space_id}",
                    title=f"[Space] {space_id}",
                    source="HuggingFace",
                    source_id=f"hf-space-{space_id}",
                    author=space_id.split("/")[0] if "/" in space_id else "",
                    published_at=created,
                    snippet=snippet[:300],
                ))

        except Exception as e:
            logger.warning("HF trending spaces fetch error: %s", e)

        return articles
