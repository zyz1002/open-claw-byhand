"""aiohttp Web server — static files + WebSocket + REST API."""
import json
import logging
import os

from aiohttp import web

import db
from .status import agent_status

logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


# --- Static & WebSocket handlers ---


async def handle_index(request: web.Request):
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))


async def handle_ws(request: web.Request):
    """WebSocket endpoint — client receives real-time status + rich data push."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    agent_status.ws_clients.add(ws)
    logger.info("[viz] WebSocket client connected, total %d", len(agent_status.ws_clients))

    # Send current state + all rich data history
    await ws.send_json(
        {
            "type": "init",
            "state": agent_status.state,
            "detail": agent_status.detail,
            "logs": agent_status.log_entries[-50:],
            "conversations": agent_status.conversation_history[-50:],
            "thinking_steps": agent_status.thinking_steps[-30:],
            "tool_calls": agent_status.tool_calls[-30:],
            "plan": agent_status.current_plan,
            "persona": agent_status.persona_files,
            "deep_research_active": agent_status.deep_research_active,
        }
    )

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if data.get("type") == "toggle_deep_research":
                        await agent_status.set_deep_research(data.get("active", False))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    finally:
        agent_status.ws_clients.discard(ws)
        logger.info("[viz] WebSocket client disconnected, remaining %d", len(agent_status.ws_clients))

    return ws


# --- REST API handlers ---


async def handle_get_persona(request: web.Request):
    """GET /api/persona — Return all persona file contents."""
    from persona import list_persona_files

    return web.json_response({"files": list_persona_files()})


async def handle_save_persona(request: web.Request):
    """POST /api/persona — Save a persona file (hot-update)."""
    data = await request.json()
    filename = data.get("filename", "")
    content = data.get("content", "")
    if filename not in ("SOUL.md", "AGENTS.md", "USER.md", "tool_catalog.md"):
        return web.json_response({"error": "invalid filename"}, status=400)
    from persona import list_persona_files, save_persona_file

    save_persona_file(filename, content)
    persona_data = list_persona_files()
    await agent_status.broadcast_persona_update(persona_data)
    return web.json_response({"ok": True})


async def handle_get_conversations(request: web.Request):
    """GET /api/conversations?user_id=xxx — Return recent conversation history."""
    user_id = request.query.get("user_id", "")
    if not user_id:
        return web.json_response({"messages": []})
    messages = await db.get_recent_messages(user_id, limit=50)
    return web.json_response({"messages": messages})


async def handle_get_tasks(request: web.Request):
    """GET /api/tasks?user_id=xxx — Return recent task runs with steps."""
    user_id = request.query.get("user_id", "")
    if not user_id:
        return web.json_response({"tasks": []})
    tasks = await db.get_recent_task_runs(user_id, limit=10)
    return web.json_response({"tasks": tasks})


async def handle_get_memories(request: web.Request):
    """GET /api/memories?user_id=xxx&status=active — Return long-term memories.
    If user_id is omitted, returns memories for all users (single-user default)."""
    user_id = request.query.get("user_id", "").strip() or None
    status_filter = request.query.get("status", "active")
    memories = await db.get_all_memories_with_ids(user_id, status_filter=status_filter)
    return web.json_response({"memories": memories})


async def handle_delete_memory(request: web.Request):
    """DELETE /api/memories/:id — Delete a memory by ID."""
    memory_id = int(request.match_info["id"])
    ok = await db.delete_memory_by_id_no_user(memory_id)
    return web.json_response({"ok": ok})


async def handle_update_memory_status(request: web.Request):
    """PATCH /api/memories/:id/status — Update a memory's status."""
    memory_id = int(request.match_info["id"])
    data = await request.json()
    new_status = data.get("status", "")
    if new_status not in ("active", "outdated", "completed"):
        return web.json_response({"error": "invalid request"}, status=400)
    ok = await db.update_memory_status_by_id_no_user(memory_id, new_status)
    return web.json_response({"ok": ok})


async def handle_toggle_deep_research(request: web.Request):
    """POST /api/deep-research — Toggle deep research mode."""
    data = await request.json()
    active = data.get("active", False)
    await agent_status.set_deep_research(active)
    return web.json_response({"deep_research_active": active})


# --- Server startup ---


async def start_viz_server(host: str = "localhost", port: int = 8080):
    """Start the visualization web server."""
    app = web.Application()
    # Static and WebSocket routes (specific paths first)
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", handle_ws)
    # REST API routes
    app.router.add_get("/api/persona", handle_get_persona)
    app.router.add_post("/api/persona", handle_save_persona)
    app.router.add_get("/api/conversations", handle_get_conversations)
    app.router.add_get("/api/tasks", handle_get_tasks)
    app.router.add_get("/api/memories", handle_get_memories)
    app.router.add_delete("/api/memories/{id:\d+}", handle_delete_memory)
    app.router.add_patch("/api/memories/{id:\d+}/status", handle_update_memory_status)
    app.router.add_post("/api/deep-research", handle_toggle_deep_research)
    # Static files (catch-all, must be last)
    app.router.add_static("/", STATIC_DIR, name="static")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    # Ensure DB tables exist (in case viz starts before bot's init_db)
    await db.init_db()
    logger.info("[viz] visualization server started: http://%s:%d", host, port)
