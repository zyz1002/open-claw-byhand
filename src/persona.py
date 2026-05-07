"""Persona hot-reload system — loads Markdown prompt files with mtime caching."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

PERSONA_DIR = os.path.join(os.path.dirname(__file__), "prompts")

# filename -> (content, mtime)
_cache: dict[str, tuple[str, float]] = {}


def _read_persona_file(filename: str) -> str:
    filepath = os.path.join(PERSONA_DIR, filename)
    try:
        mtime = os.path.getmtime(filepath)
    except OSError:
        logger.warning("persona file not found: %s", filepath)
        return ""
    cached = _cache.get(filename)
    if cached and cached[1] == mtime:
        return cached[0]
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read().strip()
    _cache[filename] = (content, mtime)
    return content


def load_soul(assistant_name: str) -> str:
    text = _read_persona_file("SOUL.md")
    return text.replace("{assistant_name}", assistant_name)


def load_agents() -> str:
    return _read_persona_file("AGENTS.md")


def load_user_profile() -> str:
    return _read_persona_file("USER.md")


def build_system_prompt(assistant_name: str) -> str:
    parts = [
        load_soul(assistant_name),
        load_agents(),
        _read_persona_file("tool_catalog.md"),
    ]
    return "\n\n".join(p for p in parts if p)


def list_persona_files() -> dict[str, str]:
    result: dict[str, str] = {}
    for filename in ("SOUL.md", "AGENTS.md", "USER.md", "tool_catalog.md"):
        result[filename] = _read_persona_file(filename)
    return result


def save_persona_file(filename: str, content: str) -> None:
    if filename not in ("SOUL.md", "AGENTS.md", "USER.md", "tool_catalog.md"):
        raise ValueError(f"invalid persona filename: {filename}")
    os.makedirs(PERSONA_DIR, exist_ok=True)
    filepath = os.path.join(PERSONA_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    _cache.pop(filename, None)
    logger.info("persona file updated: %s", filename)
