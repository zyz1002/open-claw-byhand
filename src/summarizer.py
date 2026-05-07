"""Conversation summarizer — compresses old messages into a concise summary.

When conversation history exceeds a threshold, this module compresses the
earliest messages into a summary and keeps only the most recent ones as-is.
This prevents context window explosion in long conversations (especially
Deep Research sessions).
"""
from __future__ import annotations

import logging

import db
from settings import Settings

logger = logging.getLogger(__name__)

SUMMARY_TRIGGER_THRESHOLD = 20  # compress when history exceeds this
SUMMARY_KEEP_RECENT = 8         # keep this many recent messages as-is

_SUMMARY_PROMPT = """\
请将以下对话历史压缩为一段简洁的中文摘要，保留：
- 用户的关键偏好和事实
- 重要的决策和结论
- 未完成的待办事项
- 工具调用的关键结果

对话历史：
{conversation}

摘要："""


async def maybe_summarize(
    user_id: str, history: list[dict], settings: Settings
) -> list[dict]:
    """If history exceeds threshold, compress older messages into a summary.

    Returns a new list: [summary_entry] + recent_original_messages.
    If no compression needed, returns the original list unchanged.
    """
    if len(history) <= SUMMARY_TRIGGER_THRESHOLD:
        return history

    to_summarize = history[:-SUMMARY_KEEP_RECENT]
    to_keep = history[-SUMMARY_KEEP_RECENT:]

    summary_text = await _generate_summary(to_summarize, settings)
    if summary_text:
        await db.save_message(user_id, "system_summary", summary_text)
        logger.info(
            "Compressed %d messages into summary for user %s",
            len(to_summarize), user_id,
        )
        summary_entry = {"role": "system_summary", "content": f"[对话摘要] {summary_text}"}
        return [summary_entry] + to_keep

    # Summary generation failed — return original
    return history


async def _generate_summary(messages: list[dict], settings: Settings) -> str | None:
    """Call LLM to generate a conversation summary."""
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    from claude_agent_sdk.types import TextBlock, AssistantMessage

    conversation_text = "\n".join(f"[{m['role']}] {m['content']}" for m in messages)
    prompt = _SUMMARY_PROMPT.format(conversation=conversation_text)

    options = ClaudeAgentOptions(
        model=settings.model,
        system_prompt="You are a conversation summarizer. Output a concise Chinese summary.",
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
        logger.error("summary generation failed: %s", exc)
        return None
