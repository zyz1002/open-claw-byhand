"""Digest generator — uses LLM to summarize articles into a structured digest."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import TextBlock

from settings import get_settings

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Asia/Shanghai")

DIGEST_PROMPT = """你是一个 AI 资讯编辑。请将以下文章整理成一份中文日报摘要。

要求：
1. 按分类整理：论文/研究、产品/发布、行业/融资、技术/开源
2. 每个分类最多选 2 条最值得关注的
3. 每条新闻用一句话概括要点
4. 保留原始链接
5. 控制总字数在 1200 字以内（QQ 消息有长度限制）
6. 语气简洁专业

输出格式（严格遵循）：
📰 AI 日报 | {date}

━━ 论文 & 研究 ━━
1. {{标题}}
   要点：{{一句话摘要}}
   🔗 {{链接}}

━━ 产品 & 发布 ━━
...

━━ 行业动态 ━━
...

━━ 技术 & 开源 ━━
...

共 {{N}} 条 | 数据源：{sources}

以下是今天的文章数据：
{articles}"""


async def generate_digest(articles: list[dict]) -> str:
    """Generate a structured digest from articles using LLM."""
    if not articles:
        return "今天没有抓到新的 AI 资讯，稍后再试试。"

    settings = get_settings()
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")

    # Format articles for the prompt
    articles_text = ""
    sources = set()
    for i, a in enumerate(articles, 1):
        source = a.get("source", "unknown")
        sources.add(source)
        score_str = f" (score: {a['score']})" if "score" in a else ""
        summary_str = f"\n   摘要：{a['summary']}" if a.get("summary") else ""
        articles_text += f"{i}. [{source}] {a['title']}{score_str}\n   链接：{a['url']}{summary_str}\n\n"

    prompt = DIGEST_PROMPT.format(
        date=today,
        articles=articles_text,
        sources=" · ".join(sorted(sources)),
    )

    # Call LLM for summarization
    options = ClaudeAgentOptions(
        model=settings.model,
        system_prompt="You are an AI news editor. Output only the formatted digest in Chinese.",
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

    result_text = ""
    try:
        stream = query(prompt=prompt, options=options)
        async for message in stream:
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and block.text:
                        result_text += block.text
            elif isinstance(message, ResultMessage) and message.result:
                result_text = message.result
    except Exception as exc:
        logger.error("digest generation failed: %s", exc, exc_info=True)
        # Fallback: format without LLM
        result_text = _fallback_digest(articles, today)

    # Truncate to QQ max length
    return result_text[: settings.qq_max_length]


def _fallback_digest(articles: list[dict], date: str) -> str:
    """Generate a simple digest without LLM as fallback."""
    lines = [f"📰 AI 日报 | {date}\n"]
    sources = set()
    for i, a in enumerate(articles, 1):
        source = a.get("source", "unknown")
        sources.add(source)
        lines.append(f"{i}. [{source}] {a['title']}")
        lines.append(f"   🔗 {a['url']}\n")
    lines.append(f"共 {len(articles)} 条 | 数据源：{' · '.join(sorted(sources))}")
    return "\n".join(lines)
