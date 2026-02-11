from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config_loader import load_config, get_config
from core.database import (
    get_articles,
    init_db,
    last_fetch_time,
    log_fetch,
    mark_read,
    upsert_articles,
)
from core.filtering import filter_and_score
from fetchers.arxiv_fetcher import ArxivFetcher
from fetchers.hackernews_fetcher import HackerNewsFetcher
from fetchers.reddit_fetcher import RedditFetcher
from fetchers.rss_fetcher import RSSFetcher
from fetchers.twitter_fetcher import TwitterFetcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Feed Aggregator")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

FETCHERS = [
    RSSFetcher(),
    ArxivFetcher(),
    HackerNewsFetcher(),
    RedditFetcher(),
    TwitterFetcher(),
]


@app.on_event("startup")
async def startup():
    load_config()
    await init_db()
    logger.info("AI Feed Aggregator started")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, sort: str = "date"):
    articles = await get_articles(sort_by=sort)
    config = get_config()
    topics = config.get("topics", {})
    return templates.TemplateResponse("index.html", {
        "request": request,
        "articles": articles,
        "topics": topics,
        "sort": sort,
    })


@app.post("/api/fetch")
async def api_fetch():
    config = get_config()
    intervals = config.get("fetch_intervals", {})
    total_new = 0
    results: dict[str, dict] = {}

    async def run_fetcher(fetcher):
        nonlocal total_new
        name = fetcher.source_name
        min_interval = intervals.get(name, 600)

        # Rate-limit check
        last = await last_fetch_time(name)
        if last:
            elapsed = (datetime.utcnow() - last).total_seconds()
            if elapsed < min_interval:
                results[name] = {"status": "skipped", "reason": f"too recent ({int(elapsed)}s ago)"}
                return

        try:
            raw = await fetcher.fetch()
            filtered = filter_and_score(raw)
            new_count = await upsert_articles(filtered) if filtered else 0
            total_new += new_count
            await log_fetch(name, len(raw), new_count)
            results[name] = {"status": "ok", "fetched": len(raw), "relevant": len(filtered), "new": new_count}
        except Exception as e:
            logger.exception("Fetcher %s failed", name)
            await log_fetch(name, 0, 0, status="error", error=str(e))
            results[name] = {"status": "error", "error": str(e)}

    await asyncio.gather(*(run_fetcher(f) for f in FETCHERS), return_exceptions=True)

    return JSONResponse({"total_new": total_new, "sources": results})


@app.post("/api/read/{article_id}")
async def api_mark_read(article_id: int):
    await mark_read(article_id)
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
