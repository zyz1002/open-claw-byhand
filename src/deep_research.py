"""Deep Research module — plan generation, subtask tracking, and progress detection."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import TextBlock, AssistantMessage

from settings import Settings

logger = logging.getLogger(__name__)

# ---- Prompt template for plan generation ----

DEEP_RESEARCH_PLAN_PROMPT = """\
You are a research planning assistant. Given the user's question below, create a detailed research plan.

Output ONLY valid JSON in this exact format, nothing else:
{{
  "title": "<研究计划的简短中文标题>",
  "description": "<1-2句话中文描述这个研究要达成什么目标>",
  "subtasks": [
    {{"name": "<中文子任务名称>", "description": "<这个子任务涉及什么，中文描述>"}},
    ...
  ]
}}

Rules:
- Create 2-3 subtasks, ordered by execution sequence. Keep it concise.
- Each subtask should be a distinct, actionable research step.
- Use specific subtask names (not generic like "Step 1").
- The first subtask should be about understanding/framing the question.
- The last subtask should be about synthesizing and summarizing findings.
- Subtasks in between should cover different aspects or sources to investigate.
- Output ONLY the JSON, no explanation, no markdown.
- **ALL text in title, description, subtask name and description MUST be in Chinese (中文).**

User's question:
{question}
"""


@dataclass
class SubTaskProgress:
    name: str
    description: str
    status: str = "todo"  # todo, in_progress, done, abandoned
    completed_at_step: int | None = None


@dataclass
class ResearchPlan:
    title: str
    description: str
    subtasks: list[SubTaskProgress] = field(default_factory=list)
    current_subtask_index: int = 0

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "subtasks": [
                {"name": st.name, "description": st.description, "status": st.status}
                for st in self.subtasks
            ],
            "progress": self.progress(),
        }

    def progress(self) -> float:
        if not self.subtasks:
            return 0.0
        done = sum(1 for s in self.subtasks if s.status == "done")
        return round(done / len(self.subtasks), 2)

    def advance_to_next(self) -> SubTaskProgress | None:
        """Mark current subtask as done and move to next. Returns the new current subtask or None."""
        if self.current_subtask_index < len(self.subtasks):
            self.subtasks[self.current_subtask_index].status = "done"
            self.current_subtask_index += 1
        if self.current_subtask_index < len(self.subtasks):
            self.subtasks[self.current_subtask_index].status = "in_progress"
            return self.subtasks[self.current_subtask_index]
        return None

    def mark_remaining_done(self):
        for st in self.subtasks:
            if st.status in ("todo", "in_progress"):
                st.status = "done"


def parse_plan_json(raw_text: str) -> ResearchPlan | None:
    """Parse Claude's JSON response into a ResearchPlan object."""
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]

    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError:
        logger.warning("Failed to parse plan JSON: %s", text[:200])
        return None

    if "title" not in data or "subtasks" not in data:
        return None

    subtasks = [
        SubTaskProgress(name=st.get("name", ""), description=st.get("description", ""))
        for st in data.get("subtasks", [])
    ]
    if subtasks:
        subtasks[0].status = "in_progress"

    return ResearchPlan(
        title=data.get("title", "Research"),
        description=data.get("description", ""),
        subtasks=subtasks,
    )


async def generate_research_plan(question: str, settings: Settings) -> ResearchPlan | None:
    """Call Claude once to generate a research plan. Returns None on failure."""
    prompt = DEEP_RESEARCH_PLAN_PROMPT.format(question=question)

    options = ClaudeAgentOptions(
        model=settings.model,
        system_prompt="You are a research planning assistant. Output only valid JSON.",
        permission_mode="bypassPermissions",
        env={
            "ANTHROPIC_API_KEY": settings.anthropic_api_key,
            "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
        },
        max_turns=1,
        cwd=".",
        mcp_servers={},
        allowed_tools=[],
    )

    try:
        collected_text = ""
        message_stream = query(prompt=prompt, options=options)
        async for message in message_stream:
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and block.text:
                        collected_text += block.text
            elif isinstance(message, ResultMessage) and message.result:
                collected_text = message.result

        return parse_plan_json(collected_text)
    except Exception as exc:
        logger.error("Research plan generation failed: %s", exc)
        return None


def build_plan_context_injection(plan: ResearchPlan) -> str:
    """Build the text to inject into the ReAct prompt so the agent knows its research plan."""
    lines = [
        "=== DEEP RESEARCH PLAN ===",
        f"Title: {plan.title}",
        f"Description: {plan.description}",
        "",
        "Subtasks:",
    ]
    for i, st in enumerate(plan.subtasks):
        status_icon = {"todo": "[ ]", "in_progress": "[>]", "done": "[x]", "abandoned": "[-]"}.get(st.status, "[ ]")
        lines.append(f"  {i + 1}. {status_icon} {st.name} -- {st.description} (status: {st.status})")

    lines.append("")
    lines.append("IMPORTANT INSTRUCTIONS:")
    lines.append("- Follow the subtasks in order. Focus on completing the current in_progress subtask.")
    lines.append("- After completing a subtask, explicitly say '接下来进入下一步' or similar transition phrase.")
    lines.append("- After completing ALL subtasks, provide a comprehensive final summary in Chinese.")
    lines.append("=== END PLAN ===")
    return "\n".join(lines)


# Completion detection keywords
_COMPLETION_KEYWORDS = [
    "接下来进入下一步", "完成了", "接下来", "现在来看", "下一步",
    "已收集", "现在进行", "已获得", "已经了解", "已完成调查",
    "completed", "next step", "moving on", "now let's",
]


def detect_subtask_completion(thinking_text: str, plan: ResearchPlan) -> bool:
    """Heuristic check: does the agent's thinking indicate the current subtask is done?"""
    if plan.current_subtask_index >= len(plan.subtasks):
        return False

    text_lower = thinking_text.lower()

    for keyword in _COMPLETION_KEYWORDS:
        if keyword in text_lower:
            return True

    current = plan.subtasks[plan.current_subtask_index]
    name_words = [w for w in current.name.split() if len(w) > 1]
    for word in name_words:
        if word in text_lower and ("完成" in text_lower or "done" in text_lower):
            return True

    return False


# ---- QQ message formatting ----

_STATUS_ICONS = {"todo": "[ ]", "in_progress": "[>]", "done": "[x]", "abandoned": "[-]"}


def format_plan_overview_qq(plan: ResearchPlan) -> str:
    lines = [f"[Deep Research] {plan.title}", "---"]
    for st in plan.subtasks:
        icon = _STATUS_ICONS.get(st.status, "[ ]")
        lines.append(f"{icon} {st.name}")
    lines.append("\nStarting research...")
    return "\n".join(lines)


def format_plan_progress_qq(plan: ResearchPlan) -> str:
    done = sum(1 for s in plan.subtasks if s.status == "done")
    total = len(plan.subtasks)
    lines = [f"[Deep Research] Progress {done}/{total}", "---"]
    for st in plan.subtasks:
        icon = _STATUS_ICONS.get(st.status, "[ ]")
        lines.append(f"{icon} {st.name}")
    return "\n".join(lines)
