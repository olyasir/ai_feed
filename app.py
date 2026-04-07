from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config_loader import load_config, get_config
from core.database import (
    get_articles,
    get_articles_by_tag,
    get_latest_trend_summary,
    init_db,
    last_fetch_time,
    log_fetch,
    mark_read,
    save_trend_summary,
    upsert_articles,
)
from core.filtering import filter_and_score
from fetchers.arxiv_fetcher import ArxivFetcher
from fetchers.hackernews_fetcher import HackerNewsFetcher
from fetchers.reddit_fetcher import RedditFetcher
from fetchers.rss_fetcher import RSSFetcher
from fetchers.twitter_fetcher import TwitterFetcher
from fetchers.huggingface_fetcher import HuggingFaceFetcher
from fetchers.github_trending_fetcher import GitHubTrendingFetcher
from fetchers.llamacpp_fetcher import LlamaCppFetcher
from plugins.summarizer import generate_trend_summary

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
    HuggingFaceFetcher(),
    GitHubTrendingFetcher(),
    LlamaCppFetcher(),
]

scheduler = AsyncIOScheduler()

SUMMARY_CACHE_HOURS = 24


async def run_fetch() -> dict:
    """Reusable fetch logic — used by both the API endpoint and the scheduler."""
    config = get_config()
    intervals = config.get("fetch_intervals", {})
    total_new = 0
    results: dict[str, dict] = {}

    async def run_fetcher(fetcher):
        nonlocal total_new
        name = fetcher.source_name
        min_interval = intervals.get(name, 600)

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
    return {"total_new": total_new, "sources": results}


async def scheduled_fetch():
    """Wrapper for the scheduler to call run_fetch + regenerate trend summary."""
    logger.info("Scheduled weekly fetch starting")
    result = await run_fetch()
    logger.info("Scheduled fetch complete: %s", result)

    # Auto-regenerate AI agents trend summary after weekly fetch
    try:
        articles = await get_articles_by_tag("ai_agents", days=7)
        if articles:
            summary_html = await generate_trend_summary(articles)
            now = datetime.utcnow()
            week_ago = now - timedelta(days=7)
            await save_trend_summary(
                topic="ai_agents",
                summary=summary_html,
                article_ids=[a.id for a in articles if a.id],
                date_from=week_ago.isoformat(),
                date_to=now.isoformat(),
            )
            logger.info("Trend summary regenerated with %d articles", len(articles))
        else:
            logger.info("No AI agent articles found, skipping summary generation")
    except Exception:
        logger.exception("Failed to regenerate trend summary after weekly fetch")


@app.on_event("startup")
async def startup():
    load_config()
    await init_db()
    scheduler.add_job(scheduled_fetch, "cron", day_of_week="mon", hour=6, minute=0, id="weekly_fetch")
    scheduler.start()
    logger.info("AI Feed Aggregator started — weekly fetch scheduled for Monday 06:00 UTC")


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)


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
    result = await run_fetch()
    return JSONResponse(result)


@app.post("/api/read/{article_id}")
async def api_mark_read(article_id: int):
    await mark_read(article_id)
    return JSONResponse({"ok": True})


@app.get("/trends/ai-agents", response_class=HTMLResponse)
async def trends_ai_agents(request: Request):
    articles = await get_articles_by_tag("ai_agents", days=7)

    cached = await get_latest_trend_summary("ai_agents")
    summary_html = None
    summary_date = None

    if cached:
        created = datetime.fromisoformat(cached["created_at"])
        if datetime.utcnow() - created < timedelta(hours=SUMMARY_CACHE_HOURS):
            summary_html = cached["summary"]
            summary_date = created

    if not summary_html and articles:
        summary_html = await generate_trend_summary(articles)
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)
        await save_trend_summary(
            topic="ai_agents",
            summary=summary_html,
            article_ids=[a.id for a in articles if a.id],
            date_from=week_ago.isoformat(),
            date_to=now.isoformat(),
        )
        summary_date = now

    return templates.TemplateResponse("trends_ai_agents.html", {
        "request": request,
        "summary_html": summary_html,
        "summary_date": summary_date,
        "articles": articles,
        "article_count": len(articles),
    })


@app.post("/api/trends/ai-agents/regenerate")
async def regenerate_ai_agents_summary():
    articles = await get_articles_by_tag("ai_agents", days=7)
    if not articles:
        return JSONResponse({"ok": False, "error": "No AI agent articles found"})

    summary_html = await generate_trend_summary(articles)
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    await save_trend_summary(
        topic="ai_agents",
        summary=summary_html,
        article_ids=[a.id for a in articles if a.id],
        date_from=week_ago.isoformat(),
        date_to=now.isoformat(),
    )
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
