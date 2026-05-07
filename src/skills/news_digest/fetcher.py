"""News fetcher — pulls AI articles from HackerNews and 机器之心."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp
import feedparser

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Asia/Shanghai")

HN_API = "https://hacker-news.firebaseio.com/v0"
JIQI_RSS = "https://www.jiqizhixin.com/rss"

HN_AI_KEYWORDS = {
    "ai", "artificial intelligence", "llm", "gpt", "claude", "gemini",
    "openai", "anthropic", "deepseek", "machine learning", "deep learning",
    "transformer", "diffusion", "neural", "agent", "agi", "mlops",
    "copilot", "chatbot", "language model", "foundation model",
}


def _is_ai_related(title: str) -> bool:
    lower = title.lower()
    return any(kw in lower for kw in HN_AI_KEYWORDS)


async def fetch_hackernews_ai(top_n: int = 8) -> list[dict]:
    """Fetch top AI-related stories from HackerNews."""
    async with aiohttp.ClientSession() as session:
        # Get top story IDs
        async with session.get(f"{HN_API}/topstories.json", timeout=aiohttp.ClientTimeout(total=15)) as resp:
            ids = await resp.json()

        # Fetch details for top 80, filter AI ones
        articles = []
        tasks = [_fetch_hn_item(session, item_id) for item_id in ids[:80]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, dict) and _is_ai_related(result.get("title", "")):
                articles.append(result)
            if len(articles) >= top_n:
                break

    logger.info("fetched %d AI articles from HackerNews", len(articles))
    return articles


async def _fetch_hn_item(session: aiohttp.ClientSession, item_id: int) -> dict | None:
    try:
        async with session.get(f"{HN_API}/item/{item_id}.json", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
        if not data or data.get("type") != "story" or not data.get("url"):
            return None
        return {
            "title": data["title"],
            "url": data["url"],
            "score": data.get("score", 0),
            "source": "HackerNews",
        }
    except Exception:
        return None


async def fetch_jiqizhixin(limit: int = 5) -> list[dict]:
    """Fetch latest articles from 机器之心 RSS."""
    articles = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(JIQI_RSS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                rss_text = await resp.text()

        feed = feedparser.parse(rss_text)
        yesterday = datetime.now(LOCAL_TZ) - timedelta(days=2)

        for entry in feed.entries[:limit * 2]:
            # Try to parse published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(LOCAL_TZ)

            # Only include recent articles
            if published and published < yesterday:
                continue

            summary = ""
            if hasattr(entry, "summary"):
                # Strip HTML tags roughly
                summary = entry.summary.replace("<br>", " ").replace("<br/>", " ")
                summary = summary[:200].rstrip() + "..." if len(summary) > 200 else summary

            articles.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "summary": summary,
                "source": "机器之心",
            })
            if len(articles) >= limit:
                break

    except Exception as exc:
        logger.warning("failed to fetch 机器之心 RSS: %s", exc)

    logger.info("fetched %d articles from 机器之心", len(articles))
    return articles


async def fetch_all_news() -> list[dict]:
    """Fetch from all sources in parallel."""
    hn_task = fetch_hackernews_ai()
    jiqi_task = fetch_jiqizhixin()
    hn_articles, jiqi_articles = await asyncio.gather(hn_task, jiqi_task)
    return hn_articles + jiqi_articles
