from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import aiosqlite


logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "conversations.db")


async def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'fact',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                trigger_type TEXT NOT NULL DEFAULT 'date',
                trigger_expr TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                last_error TEXT,
                last_triggered_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                source_memory_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                intent TEXT NOT NULL,
                status TEXT NOT NULL,
                input_text TEXT NOT NULL,
                route TEXT,
                plan TEXT,
                pending_field TEXT,
                context_json TEXT,
                result_text TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS task_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_run_id INTEGER NOT NULL,
                step_name TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        await _run_migration(db, "ALTER TABLE memories ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        await _run_migration(db, "ALTER TABLE reminders ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        await _run_migration(db, "ALTER TABLE reminders ADD COLUMN last_error TEXT")
        await _run_migration(db, "ALTER TABLE reminders ADD COLUMN last_triggered_at TEXT")
        await _run_migration(db, "ALTER TABLE task_runs ADD COLUMN pending_field TEXT")
        await _run_migration(db, "ALTER TABLE task_runs ADD COLUMN context_json TEXT")
        await _run_migration(db, "ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'consolidated'")
        await _run_migration(db, "ALTER TABLE memories ADD COLUMN consolidated_at TEXT")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS consolidation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                target_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                raw_count INTEGER NOT NULL DEFAULT 0,
                new_count INTEGER NOT NULL DEFAULT 0,
                dedup_count INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        await db.commit()


async def _run_migration(db: aiosqlite.Connection, sql: str) -> None:
    try:
        await db.execute(sql)
    except aiosqlite.OperationalError:
        pass


async def save_message(session_id: str, role: str, content: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO conversations (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, _now()),
        )
        await db.commit()


async def get_recent_messages(session_id: str, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT role, content, created_at FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]


async def clear_session(session_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        await db.commit()


async def save_memory(user_id: str, content: str, category: str = "fact", source: str = "raw") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO memories (user_id, content, category, status, source, created_at) VALUES (?, ?, ?, 'active', ?, ?)",
            (user_id, content, category, source, _now()),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def get_memories(user_id: str, limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT content, category, status, created_at FROM memories WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]


async def get_all_memories_for_sync(user_id: str) -> list[dict]:
    """Get all active memories for syncing to RAG (used by /sync_memories command)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, content, category, status FROM memories WHERE user_id = ? AND status = 'active' ORDER BY id",
            (user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_all_memories_with_ids(user_id: str | None = None, status_filter: str | None = None) -> list[dict]:
    """Get all memories with IDs for the management panel. Optionally filter by status.
    If user_id is None, returns memories for all users."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        has_user = user_id is not None
        has_status = status_filter and status_filter in ("active", "outdated", "completed")

        if has_user and has_status:
            cursor = await db.execute(
                "SELECT id, content, category, status, created_at FROM memories WHERE user_id = ? AND status = ? ORDER BY id DESC",
                (user_id, status_filter),
            )
        elif has_user:
            cursor = await db.execute(
                "SELECT id, content, category, status, created_at FROM memories WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            )
        elif has_status:
            cursor = await db.execute(
                "SELECT id, content, category, status, created_at FROM memories WHERE status = ? ORDER BY id DESC",
                (status_filter,),
            )
        else:
            cursor = await db.execute(
                "SELECT id, content, category, status, created_at FROM memories ORDER BY id DESC",
            )
        return [dict(row) for row in await cursor.fetchall()]


async def delete_memory_by_id(memory_id: int, user_id: str) -> bool:
    """Delete a memory by its ID. Returns True if deleted."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM memories WHERE id = ? AND user_id = ?",
            (memory_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def update_memory_status_by_id(memory_id: int, user_id: str, status: str) -> bool:
    """Update a memory's status by its ID. Returns True if updated."""
    if status not in ("active", "outdated", "completed"):
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE memories SET status = ? WHERE id = ? AND user_id = ?",
            (status, memory_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_memory_by_id_no_user(memory_id: int) -> bool:
    """Delete a memory by its ID without user_id check (for viz panel)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        await db.commit()
        return cursor.rowcount > 0


async def update_memory_status_by_id_no_user(memory_id: int, status: str) -> bool:
    """Update a memory's status without user_id check (for viz panel)."""
    if status not in ("active", "outdated", "completed"):
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE memories SET status = ? WHERE id = ?",
            (status, memory_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def search_memories(user_id: str, keyword: str, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, content, category, status, created_at FROM memories WHERE user_id = ? AND content LIKE ? AND status = 'active' ORDER BY id DESC LIMIT ?",
            (user_id, f"%{keyword}%", limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]


async def update_memory_status(user_id: str, keyword: str, status: str) -> int:
    if status not in ("outdated", "completed", "active"):
        return 0
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE memories SET status = ? WHERE user_id = ? AND content LIKE ? AND status = 'active'",
            (status, user_id, f"%{keyword}%"),
        )
        await db.commit()
        return int(cursor.rowcount)


async def refresh_user_profile_summary(user_id: str) -> str:
    memories = await get_memories(user_id, limit=50)
    summary = build_profile_summary(memories)
    memory_count = len(memories)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_profiles (user_id, summary, source_memory_count, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                summary = excluded.summary,
                source_memory_count = excluded.source_memory_count,
                updated_at = excluded.updated_at
            """,
            (user_id, summary, memory_count, _now()),
        )
        await db.commit()
    return summary


async def get_user_profile_summary(user_id: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT summary FROM user_profiles WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
    if row:
        return str(row["summary"])
    return await refresh_user_profile_summary(user_id)


def build_profile_summary(memories: list[dict]) -> str:
    if not memories:
        return "No durable profile yet."
    grouped: dict[str, list[str]] = {}
    for item in memories:
        grouped.setdefault(item["category"], []).append(item["content"])
    parts: list[str] = []
    for category, values in grouped.items():
        parts.append("{0}: {1}".format(category, " | ".join(values[-3:])))
    return "\n".join(parts)


async def cleanup_old_data(days: int = 7) -> None:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversations WHERE created_at < ?", (cutoff,))
        await db.commit()


async def save_reminder(user_id: str, content: str, trigger_type: str, trigger_expr: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO reminders (user_id, content, trigger_type, trigger_expr, status, created_at)
            VALUES (?, ?, ?, ?, 'active', ?)
            """,
            (user_id, content, trigger_type, trigger_expr, _now()),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def get_active_reminders() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, user_id, content, trigger_type, trigger_expr, status, last_error, last_triggered_at FROM reminders WHERE status = 'active'"
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_user_reminders(user_id: str, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, content, trigger_type, trigger_expr, status, last_error, last_triggered_at, created_at
            FROM reminders WHERE user_id = ? ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def complete_reminder(reminder_id: int) -> None:
    await _set_reminder_state(reminder_id, "completed", last_error=None, mark_trigger=True)


async def cancel_reminder(reminder_id: int) -> None:
    await _set_reminder_state(reminder_id, "cancelled", last_error=None)


async def fail_reminder(reminder_id: int, error: str) -> None:
    await _set_reminder_state(reminder_id, "failed", last_error=error)


async def touch_reminder_trigger(reminder_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE reminders SET last_triggered_at = ?, last_error = NULL WHERE id = ?",
            (_now(), reminder_id),
        )
        await db.commit()


async def _set_reminder_state(reminder_id: int, status: str, last_error: str | None, mark_trigger: bool = False) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE reminders
            SET status = ?, last_error = ?, last_triggered_at = COALESCE(?, last_triggered_at)
            WHERE id = ?
            """,
            (status, last_error, _now() if mark_trigger else None, reminder_id),
        )
        await db.commit()


async def create_task_run(
    user_id: str,
    intent: str,
    status: str,
    input_text: str,
    route: str | None = None,
    plan: str | None = None,
    pending_field: str | None = None,
    context_json: dict[str, Any] | None = None,
) -> int:
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO task_runs (
                user_id, intent, status, input_text, route, plan, pending_field, context_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, intent, status, input_text, route, plan, pending_field, _dump_json(context_json), now, now),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def update_task_run(
    task_id: int,
    *,
    status: str | None = None,
    route: str | None = None,
    plan: str | None = None,
    pending_field: str | None = None,
    context_json: dict[str, Any] | None = None,
    result_text: str | None = None,
    error: str | None = None,
    input_text: str | None = None,
    clear_error: bool = False,
) -> None:
    fields: list[str] = ["updated_at = ?"]
    values: list[object] = [_now()]
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if route is not None:
        fields.append("route = ?")
        values.append(route)
    if plan is not None:
        fields.append("plan = ?")
        values.append(plan)
    if pending_field is not None:
        fields.append("pending_field = ?")
        values.append(pending_field)
    if context_json is not None:
        fields.append("context_json = ?")
        values.append(_dump_json(context_json))
    if result_text is not None:
        fields.append("result_text = ?")
        values.append(result_text)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if input_text is not None:
        fields.append("input_text = ?")
        values.append(input_text)
    if clear_error:
        fields.append("error = NULL")
    values.append(task_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE task_runs SET {0} WHERE id = ?".format(", ".join(fields)), tuple(values))
        await db.commit()


async def get_latest_needs_input_task(user_id: str, intent: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM task_runs WHERE user_id = ? AND status = 'needs_input'"
    params: list[object] = [user_id]
    if intent is not None:
        query += " AND intent = ?"
        params.append(intent)
    query += " ORDER BY id DESC LIMIT 1"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, tuple(params))
        row = await cursor.fetchone()
    return _row_to_task_dict(row) if row else None


async def get_task_run(task_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM task_runs WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
    return _row_to_task_dict(row) if row else None


async def log_task_step(task_run_id: int, step_name: str, status: str = "completed", detail: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO task_steps (task_run_id, step_name, status, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (task_run_id, step_name, status, detail, _now()),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def get_task_steps(task_run_id: int) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT task_run_id, step_name, status, detail, created_at FROM task_steps WHERE task_run_id = ? ORDER BY id",
            (task_run_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


def _row_to_task_dict(row: aiosqlite.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["context_json"] = _load_json(payload.get("context_json"))
    return payload


def _dump_json(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _load_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("failed to decode task context json")
        return None


async def get_recent_task_runs(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM task_runs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            task = _row_to_task_dict(row)
            task["steps"] = await get_task_steps(task["id"])
            results.append(task)
        return results


def _now() -> str:
    return datetime.now().isoformat()


# ---------------------------------------------------------------------------
# Memory consolidation functions
# ---------------------------------------------------------------------------


async def get_distinct_user_ids() -> list[str]:
    """Get all distinct user_ids that have memories."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT user_id FROM memories")
        return [row[0] for row in await cursor.fetchall()]


async def get_conversations_for_date(user_id: str, target_date: str) -> list[dict]:
    """Get all conversation messages for a specific date (YYYY-MM-DD)."""
    next_day = (datetime.fromisoformat(target_date) + timedelta(days=1)).isoformat()[:10]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT role, content, created_at FROM conversations WHERE session_id = ? AND created_at >= ? AND created_at < ? ORDER BY id",
            (user_id, target_date, next_day),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_conversation_user_ids_for_date(target_date: str) -> list[str]:
    """Get distinct session_ids that have conversations on a given date."""
    next_day = (datetime.fromisoformat(target_date) + timedelta(days=1)).isoformat()[:10]
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT session_id FROM conversations WHERE created_at >= ? AND created_at < ?",
            (target_date, next_day),
        )
        return [row[0] for row in await cursor.fetchall()]


async def get_raw_memories_since(user_id: str, since: str) -> list[dict]:
    """Get all raw active memories created since a given ISO timestamp."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, content, category, created_at FROM memories WHERE user_id = ? AND source = 'raw' AND status = 'active' AND created_at >= ? ORDER BY id",
            (user_id, since),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_active_memories_content_set(user_id: str) -> list[dict]:
    """Get all active memories (id + content) for dedup comparison."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, content, category, source FROM memories WHERE user_id = ? AND status = 'active' ORDER BY id",
            (user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def save_consolidated_memory(user_id: str, content: str, category: str) -> int:
    """Save a consolidated (curated) memory."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO memories (user_id, content, category, status, source, consolidated_at, created_at) VALUES (?, ?, ?, 'active', 'consolidated', ?, ?)",
            (user_id, content, category, _now(), _now()),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def get_consolidated_memories(user_id: str) -> list[dict]:
    """Get all consolidated (curated) active memories for RAG sync."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, content, category, status FROM memories WHERE user_id = ? AND source = 'consolidated' AND status = 'active' ORDER BY id",
            (user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def bulk_mark_outdated(memory_ids: list[int]) -> int:
    """Mark a list of memory IDs as outdated. Returns count updated."""
    if not memory_ids:
        return 0
    placeholders = ",".join("?" for _ in memory_ids)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"UPDATE memories SET status = 'outdated' WHERE id IN ({placeholders}) AND status = 'active'",
            tuple(memory_ids),
        )
        await db.commit()
        return int(cursor.rowcount)


async def has_consolidation_run(user_id: str, target_date: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM consolidation_runs WHERE user_id = ? AND target_date = ? AND status = 'completed' LIMIT 1",
            (user_id, target_date),
        )
        return await cursor.fetchone() is not None


async def create_consolidation_run(user_id: str, target_date: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO consolidation_runs (user_id, target_date, status, started_at) VALUES (?, ?, 'running', ?)",
            (user_id, target_date, _now()),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def complete_consolidation_run(run_id: int, raw_count: int, new_count: int, dedup_count: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE consolidation_runs SET status = 'completed', raw_count = ?, new_count = ?, dedup_count = ?, finished_at = ? WHERE id = ?",
            (raw_count, new_count, dedup_count, _now(), run_id),
        )
        await db.commit()


async def fail_consolidation_run(run_id: int, error: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE consolidation_runs SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
            (error, _now(), run_id),
        )
        await db.commit()
