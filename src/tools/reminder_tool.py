from claude_agent_sdk import tool

import db
import scheduler


@tool(
    name="create_reminder",
    description="Create a one-time or recurring reminder for the user.",
    input_schema={"user_id": str, "content": str, "trigger_type": str, "trigger_expr": str},
)
async def create_reminder(args):
    user_id = args.get("user_id", "").strip()
    content = args.get("content", "").strip()
    trigger_type = args.get("trigger_type", "date").strip()
    trigger_expr = args.get("trigger_expr", "").strip()
    if not user_id or not content or not trigger_expr:
        return {"content": [{"type": "text", "text": "创建失败：缺少必要参数。"}]}
    if trigger_type not in {"date", "cron"}:
        return {"content": [{"type": "text", "text": "创建失败：trigger_type 只能是 date 或 cron。"}]}
    reminder_id = await db.save_reminder(user_id, content, trigger_type, trigger_expr)
    registered = await scheduler.register_reminder(reminder_id)
    if not registered:
        return {"content": [{"type": "text", "text": f"提醒已写入数据库，但注册失败。请检查时间格式：#{reminder_id} {trigger_expr}"}]}
    label = "单次" if trigger_type == "date" else "循环"
    return {"content": [{"type": "text", "text": f"已创建{label}提醒 #{reminder_id}：{content}，触发规则：{trigger_expr}"}]}


@tool(
    name="list_reminders",
    description="List active reminders for the user.",
    input_schema={"user_id": str},
)
async def list_reminders(args):
    user_id = args.get("user_id", "").strip()
    if not user_id:
        return {"content": [{"type": "text", "text": "查询失败：缺少 user_id。"}]}
    reminders = await db.get_user_reminders(user_id)
    if not reminders:
        return {"content": [{"type": "text", "text": "当前没有活跃提醒。"}]}
    lines = []
    for item in reminders:
        label = "单次" if item["trigger_type"] == "date" else "循环"
        suffix = f" 状态={item['status']}"
        if item.get("last_error"):
            suffix += f" 错误={item['last_error']}"
        lines.append(f"#{item['id']} [{label}] {item['content']} ({item['trigger_expr']}){suffix}")
    return {"content": [{"type": "text", "text": "当前提醒：\n" + "\n".join(lines)}]}


@tool(
    name="cancel_reminder",
    description="Cancel an active reminder by id.",
    input_schema={"user_id": str, "reminder_id": str},
)
async def cancel_reminder(args):
    user_id = args.get("user_id", "").strip()
    reminder_id_str = args.get("reminder_id", "").strip()
    if not user_id or not reminder_id_str:
        return {"content": [{"type": "text", "text": "取消失败：缺少必要参数。"}]}
    try:
        reminder_id = int(reminder_id_str)
    except ValueError:
        return {"content": [{"type": "text", "text": "取消失败：reminder_id 必须是数字。"}]}
    reminders = await db.get_user_reminders(user_id)
    if not any(item["id"] == reminder_id for item in reminders):
        return {"content": [{"type": "text", "text": f"没有找到提醒 #{reminder_id}。"}]}
    await db.cancel_reminder(reminder_id)
    scheduler.remove_job(reminder_id)
    return {"content": [{"type": "text", "text": f"已取消提醒 #{reminder_id}。"}]}


@tool(
    name="complete_reminder",
    description="Mark an active reminder as completed when the user says a task is done.",
    input_schema={"user_id": str, "reminder_id": str},
)
async def complete_reminder(args):
    user_id = args.get("user_id", "").strip()
    reminder_id_str = args.get("reminder_id", "").strip()
    if not user_id or not reminder_id_str:
        return {"content": [{"type": "text", "text": "操作失败：缺少必要参数。"}]}
    try:
        reminder_id = int(reminder_id_str)
    except ValueError:
        return {"content": [{"type": "text", "text": "操作失败：reminder_id 必须是数字。"}]}
    reminders = await db.get_user_reminders(user_id)
    if not any(item["id"] == reminder_id for item in reminders):
        return {"content": [{"type": "text", "text": f"没有找到提醒 #{reminder_id}。"}]}
    await db.complete_reminder(reminder_id)
    scheduler.remove_job(reminder_id)
    return {"content": [{"type": "text", "text": f"已将提醒 #{reminder_id} 标记为完成。"}]}
