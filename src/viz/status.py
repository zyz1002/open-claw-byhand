"""Agent status manager — manages state broadcasting and rich data for viz."""
import asyncio
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentStatus:
    """Singleton status manager with rich data stores and WebSocket broadcast."""

    def __init__(self):
        self.state: str = "idle"
        self.detail: str = "在沙发上休息"
        self.log_entries: list[dict] = []
        self.ws_clients: set = set()

        # Rich data stores
        self.conversation_history: list[dict] = []
        self.thinking_steps: list[dict] = []
        self.tool_calls: list[dict] = []
        self.current_plan: dict | None = None
        self.persona_files: dict[str, str] = {}

        # Deep research mode toggle
        self.deep_research_active: bool = False

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    async def _broadcast(self, data: dict):
        """Broadcast message to all WebSocket clients."""
        msg = json.dumps(data, ensure_ascii=False)
        dead = set()
        for ws in self.ws_clients:
            try:
                await ws.send_str(msg)
            except Exception:
                dead.add(ws)
        self.ws_clients -= dead

    async def update(self, state: str, detail: str = ""):
        """Update agent state and broadcast."""
        self.state = state
        self.detail = detail
        await self._broadcast(
            {
                "type": "status_update",
                "state": state,
                "detail": detail,
                "timestamp": self._now(),
            }
        )
        logger.info("[viz] state: %s — %s", state, detail)

    async def add_log(self, role: str, content: str):
        """Add a log entry and broadcast."""
        entry = {"role": role, "content": content, "timestamp": self._now()}
        self.log_entries.append(entry)
        if len(self.log_entries) > 200:
            self.log_entries = self.log_entries[-200:]
        await self._broadcast({"type": "log_entry", "log": entry})

    # --- Rich broadcast methods ---

    async def broadcast_conversation(self, entry: dict):
        """Broadcast a conversation turn (user message or assistant reply)."""
        entry["timestamp"] = entry.get("timestamp", self._now())
        self.conversation_history.append(entry)
        if len(self.conversation_history) > 200:
            self.conversation_history = self.conversation_history[-200:]
        await self._broadcast({"type": "conversation", **entry})

    async def broadcast_thinking(self, entry: dict):
        """Broadcast an agent thinking/reasoning step."""
        entry["timestamp"] = entry.get("timestamp", self._now())
        self.thinking_steps.append(entry)
        if len(self.thinking_steps) > 100:
            self.thinking_steps = self.thinking_steps[-100:]
        await self._broadcast({"type": "thinking_step", **entry})

    async def broadcast_tool_call(self, entry: dict):
        """Broadcast tool call start."""
        entry["timestamp"] = entry.get("timestamp", self._now())
        # Store with placeholder for result
        self.tool_calls.append({**entry, "result": None, "is_error": None})
        if len(self.tool_calls) > 100:
            self.tool_calls = self.tool_calls[-100:]
        await self._broadcast({"type": "tool_call", **entry})

    async def broadcast_tool_result(self, entry: dict):
        """Broadcast tool result and update stored tool call."""
        entry["timestamp"] = entry.get("timestamp", self._now())
        # Find and update matching tool call
        for tc in reversed(self.tool_calls):
            if tc.get("tool_id") == entry.get("tool_id"):
                tc["result"] = entry.get("result")
                tc["is_error"] = entry.get("is_error")
                break
        await self._broadcast({"type": "tool_result", **entry})

    async def broadcast_plan(self, plan_data: dict):
        """Broadcast task plan update."""
        self.current_plan = plan_data
        await self._broadcast({"type": "plan_update", **plan_data})

    async def broadcast_reminders(self, reminders: list[dict]):
        """Broadcast reminders update."""
        await self._broadcast({
            "type": "memory_snapshot",
            "reminders": reminders or [],
        })

    async def broadcast_persona_update(self, persona_data: dict):
        """Broadcast persona file contents."""
        self.persona_files = persona_data
        await self._broadcast({"type": "persona_update", "files": persona_data})

    async def set_deep_research(self, active: bool):
        """Toggle deep research mode and broadcast the change."""
        self.deep_research_active = active
        await self._broadcast({"type": "deep_research_toggle", "active": active})


# Global singleton
agent_status = AgentStatus()
