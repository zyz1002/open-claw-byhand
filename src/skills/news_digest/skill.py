"""News Digest skill — daily AI news push from HackerNews + 机器之心."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from apscheduler.triggers.cron import CronTrigger

from skills.base import Skill

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from botpy.message import C2CMessage

logger = logging.getLogger(__name__)


class NewsDigestSkill(Skill):
    name = "news_digest"
    description = "AI 资讯日报：每天自动抓取 HackerNews 和机器之心的 AI 新闻，整理后推送"

    def get_commands(self) -> dict:
        return {
            "/news": self.handle_news,
        }

    def register_jobs(self, scheduler: AsyncIOScheduler) -> None:
        scheduler.add_job(
            _daily_news_push,
            trigger=CronTrigger(hour=8, minute=0, timezone="Asia/Shanghai"),
            id="news_digest_daily",
            replace_existing=True,
        )
        logger.info("registered daily news digest job at 08:00")

    # -- Command handlers --

    @staticmethod
    async def handle_news(message: C2CMessage) -> str | None:
        """Handle /news command — fetch and return AI news digest."""
        from .fetcher import fetch_all_news
        from .digest import generate_digest

        articles = await fetch_all_news()
        if not articles:
            return "今天没有抓到新的 AI 资讯，稍后再试试。"

        digest = await generate_digest(articles)
        return digest


# -- Scheduled job callback --

async def _daily_news_push() -> None:
    """Cron job: fetch news and push to all known users."""
    import db
    from botpy import logging as botpy_logging

    logger.info("starting daily news digest push")

    try:
        from .fetcher import fetch_all_news
        from .digest import generate_digest

        articles = await fetch_all_news()
        if not articles:
            logger.info("no articles found, skipping push")
            return

        digest = await generate_digest(articles)
    except Exception as exc:
        logger.error("failed to generate news digest: %s", exc, exc_info=True)
        return

    # Push to all users who have memories (i.e., have interacted with the bot)
    try:
        user_ids = await db.get_distinct_user_ids()
    except Exception:
        logger.warning("no users found for news push")
        return

    from scheduler import get_bot_client
    client = get_bot_client()
    if not client:
        logger.error("bot client not available for news push")
        return

    for user_id in user_ids:
        try:
            await client.api.post_c2c_message(
                openid=user_id,
                msg_type=0,
                content=digest,
            )
            logger.info("pushed news digest to user %s", user_id)
        except Exception as exc:
            logger.error("failed to push news to %s: %s", user_id, exc)
