"""Skill registry — auto-discovers and loads skills from src/skills/*/."""
from __future__ import annotations

import importlib
import logging
import os
from typing import TYPE_CHECKING

from .base import Skill

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# Look for skill subdirectories under src/skills/
_SKILLS_DIR = os.path.dirname(__file__)


class SkillRegistry:
    """Central registry for all loaded skills."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._commands: dict[str, callable] = {}  # command_name -> handler

    def load_all(self) -> None:
        """Auto-discover and instantiate all skills in src/skills/*/."""
        for entry in sorted(os.listdir(_SKILLS_DIR)):
            skill_path = os.path.join(_SKILLS_DIR, entry)
            if not os.path.isdir(skill_path):
                continue
            # Skip dunder directories
            if entry.startswith("_"):
                continue
            # Try to import src.skills.<name>.skill
            module_name = f"skills.{entry}.skill"
            try:
                mod = importlib.import_module(module_name)
            except ImportError:
                logger.debug("skipping %s: no skill module found", entry)
                continue

            # Find the Skill subclass in the module
            skill_cls = None
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if isinstance(attr, type) and issubclass(attr, Skill) and attr is not Skill:
                    skill_cls = attr
                    break

            if skill_cls is None:
                logger.warning("skills/%s/skill.py has no Skill subclass, skipping", entry)
                continue

            # Instantiate and register
            skill = skill_cls()
            skill.on_register()

            # Collect commands
            commands = skill.get_commands()
            for cmd_name, handler in commands.items():
                cmd_key = cmd_name.lstrip("/")
                self._commands[cmd_key] = handler
                logger.info("registered command /%s from skill '%s'", cmd_key, skill.name)

            self._skills[skill.name] = skill
            logger.info("loaded skill: %s — %s", skill.name, skill.description)

    def register_jobs(self, scheduler: AsyncIOScheduler) -> None:
        """Register scheduled jobs for all loaded skills."""
        for skill in self._skills.values():
            skill.register_jobs(scheduler)
            logger.info("registered jobs for skill '%s'", skill.name)

    def get_command_handler(self, command_name: str):
        """Look up a command handler by name (without leading /)."""
        return self._commands.get(command_name)

    @property
    def all_commands(self) -> dict[str, callable]:
        return dict(self._commands)

    @property
    def all_skills(self) -> dict[str, Skill]:
        return dict(self._skills)


# Global singleton
skill_registry = SkillRegistry()
