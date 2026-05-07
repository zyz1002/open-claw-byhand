"""DEPRECATED: Intent detection has been replaced by the ReAct loop.

The agent now autonomously decides which tools to use via the ReAct
(Think → Act → Observe) pattern in assistant_service.py.

This module is kept for reference and test backward compatibility only.
"""
from __future__ import annotations

import re


CHAT = "chat"
MEMORY_WRITE = "memory_write"
REMINDER_CREATE = "reminder_create"
TASK_PLANNING = "task_planning"
QUESTION = "question"


_REMINDER_KEYWORDS = ("提醒", "闹钟", "到点", "记得叫我", "不要忘了", "定时")
_MEMORY_KEYWORDS = ("记住", "记一下", "别忘了", "以后都", "我的偏好", "我喜欢", "我不喜欢", "我习惯")
_TASK_KEYWORDS = ("规划", "安排", "计划", "帮我做个计划", "学习安排", "日程安排", "拆解一下")
_QUESTION_MARKERS = ("?", "？", "怎么", "为什么", "多少", "几点", "是否", "能不能")
_TIME_HINTS = ("今天", "明天", "后天", "今晚", "明早", "下午", "上午", "中午", "晚上", "点", ":", "：", "周", "星期", "号", "日", "月", "cron", "每天", "每周")
_DATE_PATTERN = re.compile(r"\d{1,2}[:：]\d{1,2}|\d{1,2}点|\d{1,2}月\d{1,2}日|\d{1,2}号")


def detect_intent(text: str) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return CHAT
    if _contains_any(normalized, _REMINDER_KEYWORDS):
        return REMINDER_CREATE
    if _contains_any(normalized, _TASK_KEYWORDS):
        return TASK_PLANNING
    if _contains_any(normalized, _MEMORY_KEYWORDS):
        return MEMORY_WRITE
    if _contains_any(normalized, _QUESTION_MARKERS):
        return QUESTION
    return CHAT


def needs_reminder_clarification(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return True
    return not (_contains_any(normalized, _TIME_HINTS) or bool(_DATE_PATTERN.search(normalized)))


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)
