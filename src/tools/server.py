"""MCP Server — 注册所有自定义工具"""
from claude_agent_sdk import create_sdk_mcp_server

from .time_tool import get_current_time
from .calculator_tool import calculate
from .memory_tool import save_memory, recall_memories, update_memory_status
from .reminder_tool import create_reminder, list_reminders, cancel_reminder

mcp_server = create_sdk_mcp_server(
    name="nanoclaw-tools",
    version="1.0.0",
    tools=[get_current_time, calculate, save_memory, recall_memories, update_memory_status, create_reminder, list_reminders, cancel_reminder],
)
