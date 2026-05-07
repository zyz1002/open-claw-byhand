"""Memory Consolidation System — background job that curates raw memories.

Architecture:
  1. Fetch today's conversations + raw memories from SQLite
  2. Send to LLM for analysis (dedup, categorize, filter)
  3. Save curated memories (source='consolidated')
  4. Mark raw/duplicate memories as 'outdated'
  5. Sync curated memories to ChromaDB for RAG
  6. Refresh user profile summary

This mirrors how human memory works: short-term (raw) memories are formed
during conversation, long-term (consolidated) memories are formed during rest.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import db
import memory_rag
from settings import Settings, get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Consolidation LLM Prompt
# ---------------------------------------------------------------------------

_CONSOLIDATION_PROMPT = """\
你是一个记忆整理助手。你的任务是分析今天的对话和原始记忆，整理出值得长期保留的高质量记忆。

## 今天的新对话记录
{conversations}

## 今天保存的原始记忆
{raw_memories}

## 用户现有的所有活跃记忆
{existing_memories}

## 你的任务

请仔细分析以上信息，完成以下工作：

1. **筛选**：从原始记忆和对话中选出真正值得记住的信息（用户偏好、重要事实、关键决策、项目信息等）。忽略废话（如"你好"、"谢谢"、闲聊内容）。

2. **去重**：检查选出的信息是否与现有记忆重复。如果意思相同但表述不同，合并为一条更精确的记忆。如果完全相同，标记为重复。

3. **分类**：为每条记忆分配合适的类别：
   - `fact` — 客观事实
   - `preference` — 用户偏好
   - `identity` — 身份信息
   - `habit` — 习惯
   - `goal` — 目标或计划
   - `project` — 项目相关信息

4. **输出格式**：严格输出以下 JSON，不要输出其他内容：

```json
{{
  "new_memories": [
    {{"content": "记忆内容", "category": "fact"}}
  ],
  "duplicate_raw_ids": [1, 2],
  "outdated_raw_ids": [3, 4]
}}
```

规则：
- `new_memories`：整理后的高质量记忆（去重后）。不够有价值的原始记忆不放进来即可。
- `duplicate_raw_ids`：与现有记忆重复的原始记忆 ID。
- `outdated_raw_ids`：被新记忆替代的原始记忆 ID。
- 没有新记忆则 `new_memories` 为空数组，没有重复则对应数组为空。
- 记忆内容用中文，简洁精确，不超过50字。
- 合并同类信息，如"用户喜欢猫"和"用户家里养了两只猫"合并为"用户养了两只猫，喜欢猫"。"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def consolidate_for_user(user_id: str, target_date: str, settings: Settings) -> dict[str, int] | None:
    """Run consolidation for a single user on a specific date.

    Returns {"raw": N, "new": N, "dedup": N} on success, None if skipped.
    """
    if await db.has_consolidation_run(user_id, target_date):
        logger.info("consolidation already ran for user=%s date=%s", user_id, target_date)
        return None

    conversations = await db.get_conversations_for_date(user_id, target_date)
    raw_memories = await db.get_raw_memories_since(user_id, target_date)
    existing_memories = await db.get_active_memories_content_set(user_id)

    if not conversations and not raw_memories:
        logger.info("no data to consolidate for user=%s date=%s", user_id, target_date)
        return None

    run_id = await db.create_consolidation_run(user_id, target_date)

    try:
        prompt = _CONSOLIDATION_PROMPT.format(
            conversations=_format_conversations(conversations) if conversations else "（今天没有对话记录）",
            raw_memories=_format_raw_memories(raw_memories) if raw_memories else "（今天没有新记忆）",
            existing_memories=_format_existing_memories(existing_memories) if existing_memories else "（暂无已有记忆）",
        )

        result_text = await _call_consolidation_llm(prompt, settings)
        if not result_text:
            await db.fail_consolidation_run(run_id, "LLM returned empty response")
            return None

        parsed = _parse_consolidation_result(result_text)
        if parsed is None:
            await db.fail_consolidation_run(run_id, f"Failed to parse JSON: {result_text[:200]}")
            return None

        stats = await _apply_consolidation(user_id, raw_memories, parsed)
        await db.complete_consolidation_run(run_id, raw_count=len(raw_memories), new_count=stats["new"], dedup_count=stats["dedup"])
        await db.refresh_user_profile_summary(user_id)

        logger.info("consolidation done user=%s date=%s: %s", user_id, target_date, stats)
        return stats

    except Exception as exc:
        logger.error("consolidation failed user=%s date=%s: %s", user_id, target_date, exc, exc_info=True)
        await db.fail_consolidation_run(run_id, str(exc))
        return None


async def run_consolidation_all_users(target_date: str | None = None) -> dict[str, Any]:
    """Run consolidation for all users. Called by cron or manual trigger."""
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    settings = get_settings()
    memory_user_ids = await db.get_distinct_user_ids()
    conv_user_ids = await db.get_conversation_user_ids_for_date(target_date)
    all_user_ids = list(set(memory_user_ids + conv_user_ids))

    if not all_user_ids:
        logger.info("no users to consolidate for date=%s", target_date)
        return {"date": target_date, "users_processed": 0}

    total_stats: dict[str, Any] = {"date": target_date, "users_processed": 0, "total_new": 0, "total_dedup": 0}

    for user_id in all_user_ids:
        try:
            result = await consolidate_for_user(user_id, target_date, settings)
            if result:
                total_stats["users_processed"] += 1
                total_stats["total_new"] += result.get("new", 0)
                total_stats["total_dedup"] += result.get("dedup", 0)
        except Exception as exc:
            logger.error("consolidation error for user %s: %s", user_id, exc)

    # Sync curated memories to ChromaDB for all users
    for user_id in all_user_ids:
        try:
            curated = await db.get_consolidated_memories(user_id)
            if curated:
                await asyncio.to_thread(memory_rag.batch_sync_memories_to_rag, curated, user_id)
                logger.info("synced %d curated memories to RAG for user=%s", len(curated), user_id)
        except Exception as exc:
            logger.error("RAG sync failed for user=%s: %s", user_id, exc)

    logger.info("consolidation complete for date=%s: %s", target_date, total_stats)
    return total_stats


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _apply_consolidation(user_id: str, raw_memories: list[dict], parsed: dict) -> dict[str, int]:
    """Apply the LLM's consolidation decisions to database and RAG."""
    new_memories = parsed.get("new_memories", [])
    duplicate_ids = parsed.get("duplicate_raw_ids", [])
    outdated_ids = parsed.get("outdated_raw_ids", [])

    # Validate IDs belong to raw memories we actually fetched
    raw_id_set = {m["id"] for m in raw_memories}
    valid_outdated = [mid for mid in set(duplicate_ids + outdated_ids) if mid in raw_id_set]

    # 1. Mark raw memories as outdated
    dedup_count = await db.bulk_mark_outdated(valid_outdated)

    # 2. Remove outdated from ChromaDB
    for mid in valid_outdated:
        memory_rag.delete_memory_from_rag(mid)

    # 3. Save new consolidated memories
    new_count = 0
    for mem in new_memories:
        content = mem.get("content", "").strip()
        category = mem.get("category", "fact").strip()
        if content:
            await db.save_consolidated_memory(user_id, content, category)
            new_count += 1

    return {"raw": len(raw_memories), "new": new_count, "dedup": dedup_count}


async def _call_consolidation_llm(prompt: str, settings: Settings) -> str | None:
    """Single-turn LLM call for consolidation. No tools, no MCP."""
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    from claude_agent_sdk.types import TextBlock, AssistantMessage

    options = ClaudeAgentOptions(
        model=settings.model,
        system_prompt="你是一个记忆整理助手。只输出JSON格式的结果。",
        permission_mode="bypassPermissions",
        env={
            "ANTHROPIC_API_KEY": settings.anthropic_api_key,
            "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
        },
        max_turns=1,
        cwd=".",
        mcp_servers={},
        allowed_tools=[],
    )

    try:
        collected = ""
        stream = query(prompt=prompt, options=options)
        async for msg in stream:
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text:
                        collected += block.text
            elif isinstance(msg, ResultMessage) and msg.result:
                collected = msg.result
        return collected.strip() or None
    except Exception as exc:
        logger.error("consolidation LLM call failed: %s", exc)
        return None


def _parse_consolidation_result(raw_text: str) -> dict | None:
    """Parse the LLM's JSON response."""
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError:
        logger.warning("failed to parse consolidation JSON: %s", text[:300])
        return None
    if "new_memories" not in data:
        return None
    return data


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_conversations(conversations: list[dict]) -> str:
    lines = []
    for msg in conversations:
        role = {"user": "用户", "assistant": "助手", "system_summary": "系统摘要"}.get(msg["role"], msg["role"])
        lines.append(f"[{role}] {msg['content']}")
    return "\n".join(lines)


def _format_raw_memories(memories: list[dict]) -> str:
    return "\n".join(f"[ID:{m['id']}] [{m['category']}] {m['content']}" for m in memories)


def _format_existing_memories(memories: list[dict]) -> str:
    lines = []
    for m in memories:
        tag = "(已整理)" if m.get("source") == "consolidated" else "(原始)"
        lines.append(f"[ID:{m['id']}] [{m.get('category', 'fact')}] {m['content']} {tag}")
    return "\n".join(lines)
