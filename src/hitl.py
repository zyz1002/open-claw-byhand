"""HITL (Human-in-the-Loop) tool confirmation manager.

Manages pending tool calls that require user confirmation before execution.
Used together with claude-agent-sdk's `can_use_tool` callback.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PendingToolStatus(str, Enum):
    WAITING = "waiting"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


@dataclass
class PendingToolCall:
    id: str
    user_id: str
    tool_name: str
    tool_input: dict
    tool_use_id: str | None
    created_at: float
    timeout_seconds: float
    status: PendingToolStatus = PendingToolStatus.WAITING
    resolve_event: asyncio.Event = field(default_factory=asyncio.Event)
    reject_reason: str = ""


class PendingToolManager:
    """Manages pending HITL tool confirmations across all users."""

    def __init__(self, timeout_seconds: float = 60.0):
        self._pending: dict[str, PendingToolCall] = {}
        self._user_pending: dict[str, list[str]] = {}
        self._timeout_seconds = timeout_seconds

    def create_pending(
        self,
        user_id: str,
        tool_name: str,
        tool_input: dict,
        tool_use_id: str | None = None,
    ) -> PendingToolCall:
        call_id = uuid.uuid4().hex[:8]
        pending = PendingToolCall(
            id=call_id,
            user_id=user_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
            created_at=time.monotonic(),
            timeout_seconds=self._timeout_seconds,
        )
        self._pending[call_id] = pending
        self._user_pending.setdefault(user_id, []).append(call_id)
        return pending

    async def wait_for_decision(self, call_id: str) -> PendingToolStatus:
        """Block until a decision is made or timeout occurs."""
        pending = self._pending.get(call_id)
        if not pending:
            return PendingToolStatus.TIMED_OUT

        try:
            await asyncio.wait_for(pending.resolve_event.wait(), timeout=pending.timeout_seconds)
        except asyncio.TimeoutError:
            pending.status = PendingToolStatus.TIMED_OUT
            pending.reject_reason = "Confirmation timed out"
            self._cleanup(pending)

        return pending.status

    def approve(self, call_id: str) -> bool:
        pending = self._pending.get(call_id)
        if not pending or pending.status != PendingToolStatus.WAITING:
            return False
        pending.status = PendingToolStatus.APPROVED
        pending.resolve_event.set()
        self._cleanup(pending)
        return True

    def reject(self, call_id: str, reason: str = "User rejected") -> bool:
        pending = self._pending.get(call_id)
        if not pending or pending.status != PendingToolStatus.WAITING:
            return False
        pending.status = PendingToolStatus.REJECTED
        pending.reject_reason = reason
        pending.resolve_event.set()
        self._cleanup(pending)
        return True

    def get_latest_pending_for_user(self, user_id: str) -> PendingToolCall | None:
        call_ids = self._user_pending.get(user_id, [])
        for cid in reversed(call_ids):
            p = self._pending.get(cid)
            if p and p.status == PendingToolStatus.WAITING:
                return p
        return None

    def cancel_all_for_user(self, user_id: str) -> int:
        """Reject all pending calls for a user (used by /clear)."""
        call_ids = self._user_pending.pop(user_id, [])
        count = 0
        for cid in call_ids:
            p = self._pending.get(cid)
            if p and p.status == PendingToolStatus.WAITING:
                p.status = PendingToolStatus.REJECTED
                p.reject_reason = "Session cleared"
                p.resolve_event.set()
                del self._pending[cid]
                count += 1
        return count

    def _cleanup(self, pending: PendingToolCall) -> None:
        call_ids = self._user_pending.get(pending.user_id, [])
        if pending.id in call_ids:
            call_ids.remove(pending.id)


def format_confirmation_message(pending: PendingToolCall) -> str:
    args_summary = json.dumps(pending.tool_input, ensure_ascii=False)[:200]
    return (
        f"[需要确认] 工具调用需要你的授权：\n"
        f"  工具: {pending.tool_name}\n"
        f"  参数: {args_summary}\n"
        f"  ID: {pending.id}\n"
        f"\n回复 /approve 确认执行，/reject 拒绝执行。\n"
        f"({int(pending.timeout_seconds)}秒无操作将自动拒绝)"
    )


# Module-level singleton
_manager: PendingToolManager | None = None


def get_manager() -> PendingToolManager:
    global _manager
    if _manager is None:
        raise RuntimeError("PendingToolManager not initialized. Call init_manager() first.")
    return _manager


def init_manager(timeout_seconds: float = 60.0) -> PendingToolManager:
    global _manager
    _manager = PendingToolManager(timeout_seconds=timeout_seconds)
    return _manager
