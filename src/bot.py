import asyncio
import logging
from datetime import datetime

from botpy import Client
from botpy.errors import ServerError
from botpy.flags import Intents
from botpy.message import C2CMessage

import db
import scheduler
from assistant_service import AssistantService
from hitl import init_manager, get_manager
from settings import get_settings
from skills import skill_registry
from viz import agent_status, start_viz_server


logger = logging.getLogger(__name__)
settings = get_settings()
assistant_service = AssistantService(settings)


async def safe_reply(message: C2CMessage, content: str, *, retries: int = 3) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    text = text[: settings.qq_max_length]
    for attempt in range(retries):
        try:
            await message.reply(content=text)
            return True
        except ServerError as exc:
            logger.warning("qq reply failed on attempt %s/%s: %s", attempt + 1, retries, exc)
            if attempt == retries - 1:
                break
            await asyncio.sleep(1.2 * (attempt + 1))
        except Exception:
            logger.exception("qq reply raised unexpected error")
            break
    await agent_status.add_log("system", "QQ reply failed after retries")
    return False


class MyClient(Client):
    async def on_ready(self):
        await db.init_db()
        await db.cleanup_old_data(days=7)
        scheduler.set_bot_client(self)
        await scheduler.restore_all_reminders()
        scheduler.start_scheduler()

        # Initialize HITL manager if enabled
        if settings.hitl_enabled:
            init_manager(timeout_seconds=float(settings.hitl_timeout_seconds))
            logger.info("HITL enabled, guarded tools timeout: %ds", settings.hitl_timeout_seconds)

        # Load skills (auto-discover from src/skills/*/)
        skill_registry.load_all()
        skill_registry.register_jobs(scheduler.scheduler)

        # Load persona files and broadcast to viz
        from persona import list_persona_files

        persona_data = list_persona_files()
        await agent_status.broadcast_persona_update(persona_data)

        asyncio.create_task(start_viz_server(host=settings.viz_host, port=settings.viz_port))
        logger.info("%s is ready", settings.assistant_name)

    async def on_c2c_message_create(self, message: C2CMessage):
        content = (message.content or "").strip()
        if not content:
            return

        # HITL: Tool confirmation commands (highest priority)
        if content == "/approve" and settings.hitl_enabled:
            session_id = message.author.user_openid
            manager = get_manager()
            pending = manager.get_latest_pending_for_user(session_id)
            if pending:
                manager.approve(pending.id)
                await safe_reply(message, f"已批准工具调用: {pending.tool_name}")
            else:
                await safe_reply(message, "没有待确认的工具调用。")
            return

        if content == "/reject" and settings.hitl_enabled:
            session_id = message.author.user_openid
            manager = get_manager()
            pending = manager.get_latest_pending_for_user(session_id)
            if pending:
                manager.reject(pending.id, "User rejected via /reject")
                await safe_reply(message, f"已拒绝工具调用: {pending.tool_name}")
            else:
                await safe_reply(message, "没有待确认的工具调用。")
            return

        if content == "/start":
            await safe_reply(
                message,
                (
                    f"Hi! I'm {settings.assistant_name}.\n\n"
                    "我支持聊天、工具调用、长期记忆、提醒，还有简单的任务规划。\n"
                    "直接发消息就可以开始，`/clear` 可以清空会话。"
                ),
            )
            return
        if content == "/clear":
            session_id = message.author.user_openid
            await db.clear_session(session_id)
            if settings.hitl_enabled:
                manager = get_manager()
                manager.cancel_all_for_user(session_id)
            await safe_reply(message, "会话已清空，我们重新开始。")
            return
        if content.startswith("/deep "):
            question = content[6:].strip()
            if not question:
                await safe_reply(message, "用法: /deep <你的问题>\n示例: /deep 量子计算现在发展到什么程度了？")
                return
            await handle_private_message(message, deep_research=True)
            return
        if content == "/sync_memories":
            session_id = message.author.user_openid
            from memory_rag import batch_sync_memories_to_rag
            memories = await db.get_all_memories_for_sync(session_id)
            count = batch_sync_memories_to_rag(memories, session_id)
            await safe_reply(message, f"已将 {count} 条记忆同步到 RAG 向量库。")
            return
        if content == "/consolidate":
            session_id = message.author.user_openid
            from memory_consolidator import consolidate_for_user
            today = datetime.now().strftime("%Y-%m-%d")
            await safe_reply(message, "正在整理今天的记忆...")
            result = await consolidate_for_user(session_id, today, settings)
            if result is None:
                await safe_reply(message, "今天没有需要整理的记忆，或者已经整理过了。")
            else:
                await safe_reply(
                    message,
                    f"记忆整理完成！处理了 {result['raw']} 条原始记忆，"
                    f"生成了 {result['new']} 条高质量记忆，"
                    f"去重/淘汰了 {result['dedup']} 条。",
                )
            return
        # Skill commands: dispatch to registered skill handlers
        if content.startswith("/"):
            cmd_name = content.split()[0].lstrip("/")
            handler = skill_registry.get_command_handler(cmd_name)
            if handler:
                reply = await handler(message)
                if reply:
                    await safe_reply(message, reply)
            return
        await handle_private_message(message)


async def handle_private_message(message: C2CMessage, *, deep_research: bool = False) -> None:
    session_id = message.author.user_openid
    user_text = (message.content or "").strip()
    # For /deep command, strip the prefix to get the actual question
    if deep_research and user_text.startswith("/deep "):
        user_text = user_text[6:].strip()

    async def send_progress(text: str):
        await safe_reply(message, text)

    async def reply_callback(text: str):
        """Used by HITL to send confirmation requests to the user."""
        await safe_reply(message, text)

    try:
        result = await assistant_service.handle_message(
            session_id, user_text,
            deep_research=deep_research,
            progress_callback=send_progress if deep_research else None,
            reply_callback=reply_callback,
        )
        logger.info("handled message intent=%s task_id=%s status=%s", result.intent, result.task_id, result.status)
        delivered = await safe_reply(message, result.reply_text)
        if not delivered:
            logger.error("reply could not be delivered to qq user_openid=%s", session_id)
    except Exception as exc:
        logger.error("message handling failed: %s", exc, exc_info=True)
        fallback = "这次处理消息时出了点问题。你可以再试一次，或者把需求说得更具体一点。"
        await agent_status.add_log("system", fallback)
        await agent_status.update("done", "task failed")
        await safe_reply(message, fallback)


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(levelname)s] (%(filename)s:%(lineno)d) %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)
    file_handler = logging.FileHandler("logs/bot.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("[%(asctime)s] " + formatter._fmt))
    root.addHandler(file_handler)


if __name__ == "__main__":
    configure_logging()
    intents = Intents(public_messages=True, public_guild_messages=True)
    client = MyClient(intents=intents)
    client.run(appid=settings.app_id, secret=settings.bot_token)
