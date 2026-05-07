from claude_agent_sdk import tool

import db
import memory_rag


_ALLOWED_CATEGORIES = {"fact", "preference", "identity", "habit", "goal", "project", "reminder"}


@tool(
    name="save_memory",
    description="Save durable user information for future conversations.",
    input_schema={"user_id": str, "content": str, "category": str},
)
async def save_memory(args):
    user_id = args.get("user_id", "").strip()
    content = args.get("content", "").strip()
    category = args.get("category", "fact").strip() or "fact"
    if not user_id or not content:
        return {"content": [{"type": "text", "text": "保存失败：缺少 user_id 或内容。"}]}
    if category not in _ALLOWED_CATEGORIES:
        category = "fact"

    # 1. Write to SQLite (primary store — instant, source='raw')
    memory_id = await db.save_memory(user_id, content, category, source="raw")

    # 2. Refresh user profile
    await db.refresh_user_profile_summary(user_id)
    return {"content": [{"type": "text", "text": f"已保存记忆：[{category}] {content}"}]}


@tool(
    name="recall_memories",
    description="Recall active memories for the user, optionally filtered by a keyword. Uses semantic search when possible.",
    input_schema={"user_id": str, "keyword": str},
)
async def recall_memories(args):
    user_id = args.get("user_id", "").strip()
    keyword = args.get("keyword", "").strip()
    if not user_id:
        return {"content": [{"type": "text", "text": "查询失败：缺少 user_id。"}]}

    if keyword:
        # Fast path: SQLite LIKE search (instant, always works)
        memories = await db.search_memories(user_id, keyword)
        if not memories:
            # Try RAG semantic search as enrichment (slower, but catches fuzzy matches)
            import asyncio
            rag_results = await asyncio.to_thread(memory_rag.search_memories_in_rag, keyword, user_id, 5)
            if rag_results:
                lines = [f"[{r['category']}] {r['content']} (相关度: {r['score']:.2f})" for r in rag_results]
                return {"content": [{"type": "text", "text": "相关记忆（语义匹配）：\n" + "\n".join(lines)}]}
    else:
        memories = await db.get_memories(user_id)

    if not memories:
        return {"content": [{"type": "text", "text": "没有找到相关记忆。"}]}
    lines = ["[{0}] {1}".format(item["category"], item["content"]) for item in memories]
    return {"content": [{"type": "text", "text": "相关记忆：\n" + "\n".join(lines)}]}


@tool(
    name="update_memory_status",
    description="Mark an active memory as outdated or completed when the user changes or finishes something.",
    input_schema={"user_id": str, "keyword": str, "status": str},
)
async def update_memory_status(args):
    user_id = args.get("user_id", "").strip()
    keyword = args.get("keyword", "").strip()
    status = args.get("status", "").strip()
    if not user_id or not keyword:
        return {"content": [{"type": "text", "text": "更新失败：缺少 user_id 或关键词。"}]}
    if status not in {"outdated", "completed"}:
        return {"content": [{"type": "text", "text": "更新失败：status 只能是 outdated 或 completed。"}]}

    # 1. Update in SQLite
    affected = await db.update_memory_status(user_id, keyword, status)

    # 2. Sync status to RAG ChromaDB
    if affected > 0:
        matched = await db.search_memories(user_id, keyword)
        for m in matched:
            memory_rag.update_memory_status_in_rag(m["id"], status)

    await db.refresh_user_profile_summary(user_id)
    if affected == 0:
        return {"content": [{"type": "text", "text": f"没有找到包含「{keyword}」的活跃记忆。"}]}
    return {"content": [{"type": "text", "text": f"已更新 {affected} 条记忆状态为 {status}。"}]}
