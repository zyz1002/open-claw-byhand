"""获取当前时间的 MCP 工具"""
import datetime
from zoneinfo import ZoneInfo

from claude_agent_sdk import tool

# 使用中国标准时间
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


@tool(
    name="get_current_time",
    description="获取当前的日期和时间，当用户问现在几点、今天几号时使用此工具。设置提醒时请参考此时间。",
    input_schema={"timezone": str},
)
async def get_current_time(args):
    now = datetime.datetime.now(LOCAL_TZ)
    return {"content": [{"type": "text", "text": f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Shanghai, UTC+8)"}]}
