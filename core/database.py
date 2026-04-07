from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import aiosqlite

from core.models import Article

import os

DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).parent.parent / "feed.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT DEFAULT '',
    author TEXT DEFAULT '',
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    snippet TEXT DEFAULT '',
    summary TEXT,
    relevance_score REAL DEFAULT 0.0,
    matched_keywords TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    is_read INTEGER DEFAULT 0,
    thumbnail_url TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_relevance ON articles(relevance_score DESC);

CREATE TABLE IF NOT EXISTS fetch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    total_fetched INTEGER DEFAULT 0,
    total_new INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok',
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_fetch_log_source ON fetch_log(source, fetched_at DESC);

CREATE TABLE IF NOT EXISTS trend_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    summary TEXT NOT NULL,
    article_ids TEXT DEFAULT '[]',
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trend_summaries_topic ON trend_summaries(topic, created_at DESC);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def upsert_article(article: Article) -> bool:
    """Insert or ignore an article. Returns True if newly inserted."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT OR IGNORE INTO articles
               (url, title, source, source_id, author, published_at, fetched_at,
                snippet, summary, relevance_score, matched_keywords, tags, is_read, thumbnail_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                article.url,
                article.title,
                article.source,
                article.source_id,
                article.author,
                article.published_at.isoformat() if article.published_at else None,
                article.fetched_at.isoformat() if article.fetched_at else datetime.utcnow().isoformat(),
                article.snippet,
                article.summary,
                article.relevance_score,
                json.dumps(article.matched_keywords),
                json.dumps(article.tags),
                int(article.is_read),
                article.thumbnail_url,
            ),
        )
        await db.commit()
        return cursor.rowcount > 0


async def upsert_articles(articles: list[Article]) -> int:
    """Bulk upsert. Returns count of newly inserted articles."""
    new_count = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for article in articles:
            cursor = await db.execute(
                """INSERT OR IGNORE INTO articles
                   (url, title, source, source_id, author, published_at, fetched_at,
                    snippet, summary, relevance_score, matched_keywords, tags, is_read, thumbnail_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    article.url,
                    article.title,
                    article.source,
                    article.source_id,
                    article.author,
                    article.published_at.isoformat() if article.published_at else None,
                    article.fetched_at.isoformat() if article.fetched_at else datetime.utcnow().isoformat(),
                    article.snippet,
                    article.summary,
                    article.relevance_score,
                    json.dumps(article.matched_keywords),
                    json.dumps(article.tags),
                    int(article.is_read),
                    article.thumbnail_url,
                ),
            )
            if cursor.rowcount > 0:
                new_count += 1
        await db.commit()
    return new_count


async def get_articles(
    source: str | None = None,
    sort_by: str = "date",
    limit: int = 200,
) -> list[Article]:
    """Fetch articles from the database."""
    order = "published_at DESC" if sort_by == "date" else "relevance_score DESC"
    conditions = []
    params: list = []

    if source:
        conditions.append("source = ?")
        params.append(source)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT * FROM articles {where} ORDER BY {order} LIMIT ?",
            params + [limit],
        )
        rows = await cursor.fetchall()
        return [Article.from_row(dict(row)) for row in rows]


async def mark_read(article_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE articles SET is_read = 1 WHERE id = ?", (article_id,))
        await db.commit()


async def log_fetch(source: str, total_fetched: int, total_new: int, status: str = "ok", error: str | None = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO fetch_log (source, fetched_at, total_fetched, total_new, status, error) VALUES (?, ?, ?, ?, ?, ?)",
            (source, datetime.utcnow().isoformat(), total_fetched, total_new, status, error),
        )
        await db.commit()


async def get_articles_by_tag(tag: str, days: int = 7) -> list[Article]:
    """Fetch articles matching a tag from the last N days."""
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM articles
               WHERE tags LIKE ? AND published_at >= ?
               ORDER BY published_at DESC""",
            (f'%"{tag}"%', cutoff),
        )
        rows = await cursor.fetchall()
        return [Article.from_row(dict(row)) for row in rows]


async def save_trend_summary(topic: str, summary: str, article_ids: list[int], date_from: str, date_to: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO trend_summaries (topic, summary, article_ids, date_from, date_to, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (topic, summary, json.dumps(article_ids), date_from, date_to, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def get_latest_trend_summary(topic: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM trend_summaries WHERE topic = ? ORDER BY created_at DESC LIMIT 1",
            (topic,),
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None


async def last_fetch_time(source: str) -> datetime | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT fetched_at FROM fetch_log WHERE source = ? AND status = 'ok' ORDER BY fetched_at DESC LIMIT 1",
            (source,),
        )
        row = await cursor.fetchone()
        if row:
            return datetime.fromisoformat(row["fetched_at"])
        return None
