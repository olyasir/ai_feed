from __future__ import annotations

import logging

from core.config_loader import get_config
from core.models import RawArticle
from fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)


class TwitterFetcher(BaseFetcher):
    """Stub fetcher for Twitter/X. Returns empty unless configured with a bearer token."""

    source_name = "twitter"

    async def fetch(self) -> list[RawArticle]:
        config = get_config()
        twitter_cfg = config.get("twitter", {})

        if not twitter_cfg.get("enabled") or not twitter_cfg.get("bearer_token"):
            logger.debug("Twitter fetcher disabled or not configured")
            return []

        # Future implementation would use the Twitter/X API v2 here
        logger.info("Twitter fetcher stub — API integration not yet implemented")
        return []
