from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

import db


logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
scheduler = AsyncIOScheduler(timezone=LOCAL_TZ)
_bot_client = None


def set_bot_client(client) -> None:
    global _bot_client
    _bot_client = client


def get_bot_client():
    """Return the bot client instance (for skill scheduled jobs)."""
    return _bot_client


async def _send_reminder(user_id: str, content: str, reminder_id: int, trigger_type: str) -> None:
    logger.info("triggering reminder id=%s user=%s", reminder_id, user_id)
    try:
        if _bot_client is None:
            raise RuntimeError("bot client is not ready")
        await _bot_client.api.post_c2c_message(
            openid=user_id,
            msg_type=0,
            content=f"提醒：{content}",
        )
        await db.touch_reminder_trigger(reminder_id)
        if trigger_type == "date":
            await db.complete_reminder(reminder_id)
    except Exception as exc:
        logger.error("failed to send reminder %s: %s", reminder_id, exc, exc_info=True)
        await db.fail_reminder(reminder_id, str(exc))


async def register_reminder(reminder_id: int) -> bool:
    reminders = await db.get_active_reminders()
    for reminder in reminders:
        if reminder["id"] == reminder_id:
            return await _register_loaded_reminder(reminder)
    return False


async def restore_all_reminders() -> None:
    reminders = await db.get_active_reminders()
    restored = 0
    for reminder in reminders:
        if await _register_loaded_reminder(reminder):
            restored += 1
    logger.info("restored %s active reminders", restored)


async def _register_loaded_reminder(reminder: dict) -> bool:
    reminder_id = reminder["id"]
    trigger_type = reminder["trigger_type"]
    trigger_expr = reminder["trigger_expr"]
    user_id = reminder["user_id"]
    content = reminder["content"]
    job_id = f"reminder_{reminder_id}"
    try:
        if trigger_type == "date":
            run_date = _parse_date_trigger(trigger_expr)
            if run_date <= datetime.now(LOCAL_TZ):
                raise ValueError("trigger time is already in the past")
            scheduler.add_job(
                _send_reminder,
                trigger=DateTrigger(run_date=run_date),
                args=[user_id, content, reminder_id, trigger_type],
                id=job_id,
                replace_existing=True,
            )
        elif trigger_type == "cron":
            minute, hour, day, month, day_of_week = _parse_cron_trigger(trigger_expr)
            scheduler.add_job(
                _send_reminder,
                trigger=CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week,
                    timezone=LOCAL_TZ,
                ),
                args=[user_id, content, reminder_id, trigger_type],
                id=job_id,
                replace_existing=True,
            )
        else:
            raise ValueError("unsupported trigger_type: {0}".format(trigger_type))
        logger.info("registered reminder %s", reminder_id)
        return True
    except Exception as exc:
        logger.error("failed to register reminder %s: %s", reminder_id, exc)
        await db.fail_reminder(reminder_id, str(exc))
        return False


def remove_job(reminder_id: int) -> None:
    try:
        scheduler.remove_job(f"reminder_{reminder_id}")
    except Exception:
        pass


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        logger.info("scheduler started")
    _register_consolidation_job()


def _register_consolidation_job() -> None:
    """Register the daily memory consolidation cron job."""
    from settings import get_settings
    s = get_settings()
    scheduler.add_job(
        _run_daily_consolidation,
        trigger=CronTrigger(
            hour=s.consolidation_hour,
            minute=s.consolidation_minute,
            timezone=LOCAL_TZ,
        ),
        id="memory_consolidation",
        replace_existing=True,
    )
    logger.info("registered daily memory consolidation at %02d:%02d", s.consolidation_hour, s.consolidation_minute)


async def _run_daily_consolidation() -> None:
    """Cron job callback: run consolidation for all users."""
    logger.info("starting daily memory consolidation")
    try:
        from memory_consolidator import run_consolidation_all_users
        stats = await run_consolidation_all_users()
        logger.info("daily consolidation complete: %s", stats)
    except Exception as exc:
        logger.error("daily consolidation failed: %s", exc, exc_info=True)


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        logger.info("scheduler stopped")


def _parse_date_trigger(trigger_expr: str) -> datetime:
    raw_value = datetime.fromisoformat(trigger_expr)
    if raw_value.tzinfo is None:
        return raw_value.replace(tzinfo=LOCAL_TZ)
    return raw_value.astimezone(LOCAL_TZ)


def _parse_cron_trigger(trigger_expr: str) -> tuple[str, str, str, str, str]:
    parts = trigger_expr.split()
    if len(parts) != 5:
        raise ValueError("cron expression must have 5 parts")
    return tuple(parts)  # type: ignore[return-value]
