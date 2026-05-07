from __future__ import annotations


TOOL_CATALOG = [
    {
        "name": "get_current_time",
        "purpose": "Get the current Asia/Shanghai time before answering time-sensitive questions.",
        "when_to_use": "Use for time questions or before creating reminders from natural language.",
        "key_args": ["timezone"],
        "example": '{"timezone": "Asia/Shanghai"}',
        "hitl_risk": "low",
    },
    {
        "name": "calculate",
        "purpose": "Evaluate a simple math expression.",
        "when_to_use": "Use when the user asks for arithmetic or a quick calculation.",
        "key_args": ["expression"],
        "example": '{"expression": "(10-3)/7"}',
        "hitl_risk": "low",
    },
    {
        "name": "save_memory",
        "purpose": "Store durable user information such as preferences, identity details, and recurring facts.",
        "when_to_use": "Use when the user says something worth remembering later.",
        "key_args": ["user_id", "content", "category"],
        "example": '{"user_id": "u1", "content": "Prefers concise answers", "category": "preference"}',
        "hitl_risk": "low",
    },
    {
        "name": "recall_memories",
        "purpose": "Read relevant active memories for the current user.",
        "when_to_use": "Use when prior preferences or facts may help answer better.",
        "key_args": ["user_id", "keyword"],
        "example": '{"user_id": "u1", "keyword": "preference"}',
        "hitl_risk": "low",
    },
    {
        "name": "update_memory_status",
        "purpose": "Mark a memory as outdated or completed when it is no longer current.",
        "when_to_use": "Use when the user corrects or finishes something previously remembered.",
        "key_args": ["user_id", "keyword", "status"],
        "example": '{"user_id": "u1", "keyword": "gym plan", "status": "completed"}',
        "hitl_risk": "low",
    },
    {
        "name": "create_reminder",
        "purpose": "Create a one-time or recurring reminder for the user.",
        "when_to_use": "Use when the user clearly asks to be reminded at a specific time or schedule.",
        "key_args": ["user_id", "content", "trigger_type", "trigger_expr"],
        "example": '{"user_id": "u1", "content": "Interview prep", "trigger_type": "date", "trigger_expr": "2026-04-16 20:00:00"}',
        "hitl_risk": "low",
    },
    {
        "name": "list_reminders",
        "purpose": "List active reminders for the user.",
        "when_to_use": "Use when the user asks what reminders are active.",
        "key_args": ["user_id"],
        "example": '{"user_id": "u1"}',
        "hitl_risk": "low",
    },
    {
        "name": "cancel_reminder",
        "purpose": "Cancel an active reminder by id.",
        "when_to_use": "Use when the user explicitly wants to cancel a reminder.",
        "key_args": ["user_id", "reminder_id"],
        "example": '{"user_id": "u1", "reminder_id": "3"}',
        "hitl_risk": "low",
    },
    {
        "name": "complete_reminder",
        "purpose": "Mark an active reminder as completed when the user says a task is done.",
        "when_to_use": "Use when the user says a reminder task is finished or completed.",
        "key_args": ["user_id", "reminder_id"],
        "example": '{"user_id": "u1", "reminder_id": "5"}',
        "hitl_risk": "low",
    },
    {
        "name": "query_knowledge_hub",
        "purpose": "Search the RAG knowledge base for relevant documents using hybrid search (semantic + keyword).",
        "when_to_use": "Use when the user asks about specific project knowledge, technical documentation, or any question that may benefit from stored documents.",
        "key_args": ["query", "top_k", "collection"],
        "example": '{"query": "混合搜索是怎么实现的", "top_k": 5}',
        "hitl_risk": "low",
    },
    {
        "name": "list_collections",
        "purpose": "List all available document collections in the RAG knowledge base.",
        "when_to_use": "Use when the user wants to know what knowledge bases or document collections are available.",
        "key_args": ["include_stats"],
        "example": '{"include_stats": true}',
        "hitl_risk": "low",
    },
    {
        "name": "get_document_summary",
        "purpose": "Get summary and metadata for a specific document in the knowledge base.",
        "when_to_use": "Use when the user wants details about a specific document after a search result.",
        "key_args": ["doc_id", "collection"],
        "example": '{"doc_id": "doc_abc123"}',
        "hitl_risk": "low",
    },
]


def render_tool_catalog() -> str:
    lines: list[str] = []
    for item in TOOL_CATALOG:
        lines.append(
            "- {name}: {purpose} When to use: {when_to_use} Key args: {args}. Example: {example}".format(
                name=item["name"],
                purpose=item["purpose"],
                when_to_use=item["when_to_use"],
                args=", ".join(item["key_args"]),
                example=item["example"],
            )
        )
    return "\n".join(lines)


def allowed_tool_names() -> list[str]:
    return [item["name"] for item in TOOL_CATALOG]


def guarded_tool_names() -> set[str]:
    """Return names of tools that require HITL confirmation."""
    return {item["name"] for item in TOOL_CATALOG if item.get("hitl_risk") == "high"}
