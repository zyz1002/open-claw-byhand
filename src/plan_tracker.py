"""Extract and track task plans from agent responses for visualization."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass
class SubTask:
    name: str
    status: str = "todo"  # todo, in_progress, done, abandoned


@dataclass
class TaskPlan:
    name: str
    description: str = ""
    subtasks: list[dict] = field(default_factory=list)
    progress: float = 0.0


_PLAN_MARKERS = ("目标", "时间块安排", "优先级", "提醒建议", "备注")


def extract_plan(text: str) -> dict | None:
    """Try to extract a structured plan from agent text response.

    Returns a dict suitable for JSON serialization, or None if no plan detected.
    """
    found = [m for m in _PLAN_MARKERS if m in text]
    if len(found) < 2:
        return None

    # Extract plan name from 目标 section
    name = "任务计划"
    goal_match = re.search(r"目标[：:]\s*(.+)", text)
    if goal_match:
        name = goal_match.group(1).strip()[:60]

    # Extract subtasks from bullet points
    subtasks: list[dict] = []
    for line in text.split("\n"):
        line = line.strip()
        if re.match(r"^[-*•]\s+", line) or re.match(r"^\d+[.、)]\s+", line):
            content = re.sub(r"^[-*•]\s+", "", line)
            content = re.sub(r"^\d+[.、)]\s+", "", content)
            if content and len(content) > 2:
                status = "todo"
                if any(kw in content for kw in ("完成", "done", "已完成")):
                    status = "done"
                elif any(kw in content for kw in ("进行中", "in_progress", "正在")):
                    status = "in_progress"
                subtasks.append({"name": content[:80], "status": status})

    if not subtasks:
        return None

    done_count = sum(1 for s in subtasks if s["status"] == "done")
    progress = round(done_count / len(subtasks), 2) if subtasks else 0.0

    return {
        "name": name,
        "description": text[:200],
        "subtasks": subtasks,
        "progress": progress,
    }
