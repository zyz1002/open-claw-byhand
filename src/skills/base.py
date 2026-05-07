"""Skill base class — every skill inherits from this."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, Coroutine

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from botpy.message import C2CMessage

logger = logging.getLogger(__name__)


class Skill(ABC):
    """Base class for all bot skills.

    Each skill is a self-contained feature module that can register:
    - Commands (e.g., /news)
    - Scheduled jobs (e.g., daily push at 8:00)
    - Agent tools (optional, callable from ReAct loop)

    Subclass this and implement the methods you need.
    """

    # -- Identity --
    name: str = ""
    description: str = ""

    def __init__(self):
        assert self.name, f"{self.__class__.__name__} must set .name"

    # -- Lifecycle hooks --

    def on_register(self) -> None:
        """Called once when the skill is loaded. Use for one-time setup."""
        pass

    # -- Command registration --

    def get_commands(self) -> dict[str, Callable[[C2CMessage], Coroutine]]:
        """Return a dict of {command_name: handler_async_function}.

        Commands are auto-registered as /command_name in bot.py.
        Handler signature: async def handle_xxx(message: C2CMessage) -> str
        The return string is sent as reply. Return None to skip reply.
        """
        return {}

    # -- Scheduled jobs --

    def register_jobs(self, scheduler: AsyncIOScheduler) -> None:
        """Register cron/date jobs with the APScheduler instance."""
        pass

    # -- Utility --

    def __repr__(self) -> str:
        return f"<Skill {self.name}: {self.description}>"
