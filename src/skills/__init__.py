"""Skills plugin framework — base class and public API."""
from .base import Skill
from .registry import skill_registry

__all__ = ["Skill", "skill_registry"]
