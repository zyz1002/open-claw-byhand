# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenClaw Byhand — a manually-built QQ bot ("小龙虾") that acts as an AI agent. The goal is to receive messages via third-party SMS platforms, have the bot reply intelligently via Claude, and execute agent tasks. Long-term memory and user preference tracking are planned features.

## Language & Tooling

- **Python 3.12+** (specified in `.python-version`)
- **Package manager**: [uv](https://docs.astral.sh/uv/) — use `uv` for all dependency operations
- **Linter**: ruff (`line-length = 180`)
- **Build backend**: hatchling

## Common Commands

```bash
# Install dependencies
uv sync

# Run the bot (primary entry point)
uv run python src/bot.py

# Run alternative entry point
uv run python main.py
```

## Architecture

The project is in early development with a minimal codebase:

- **`src/bot.py`** — Main QQ bot implementation. Uses `qq-botpy` framework with an event-driven decorator pattern (`@client.on_command`, `@client.on_message_create`). Reads credentials from `.env` (`QQ_APPID`, `QQ_TOKEN`). Currently has a `/start` command and message echo handler.
- **`main.py`** — Placeholder entry point, not the real bot.
- **`src/nanoclaw/`** — Referenced as the wheel package in `pyproject.toml` (`packages = ["src/nanoclaw"]`) but not yet created. This is where the main package code should go.

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `qq-botpy` | QQ bot framework (event handling, message API) |
| `claude-agent-sdk` | Claude AI agent integration (not yet wired) |
| `aiosqlite` | Async SQLite for planned memory/preferences storage |
| `apscheduler` + `croniter` | Task scheduling (planned) |
| `python-dotenv` | `.env` file loading |

## Configuration

Environment variables are loaded from `.env`:
- `QQ_APPID` — QQ bot application ID
- `QQ_TOKEN` — QQ bot token

## Notes

- The project is primarily documented in Chinese (`readme.txt`). `README.md` is empty.
- `src/bot.py` contains episode-based comments (ep1, ep2, etc.) following a tutorial series pattern.
- The codebase uses `botpy.Client` (not `botpy.Bot`) for the QQ bot client.
