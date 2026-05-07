from __future__ import annotations

import asyncio
import contextvars
import json
import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    TextBlock,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
)

import db
from guardian import guard
from deep_research import (
    ResearchPlan,
    build_plan_context_injection,
    detect_subtask_completion,
    format_plan_overview_qq,
    format_plan_progress_qq,
    generate_research_plan,
)
from hitl import PendingToolStatus, format_confirmation_message, get_manager
from persona import build_system_prompt
from plan_tracker import extract_plan
from settings import Settings
from summarizer import maybe_summarize
from tool_catalog import allowed_tool_names, guarded_tool_names
from tools.server import mcp_server
from viz import agent_status


logger = logging.getLogger(__name__)

# Context variable to track current user_id during a ReAct loop
_current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("_current_user_id", default="")


@dataclass
class AssistantResult:
    reply_text: str
    intent: str
    task_id: int
    status: str


_SIMPLE_GREETING_PATTERN = re.compile(
    r"^(你好|嗨|hi|hello|hey|哈喽|早上好|下午好|晚上好|早安|晚安|在吗|在不在|hey\s|yo\b)[\s!！。.~～]*$",
    re.IGNORECASE,
)

_SIMPLE_GREETING_REPLIES = [
    "你好呀！有什么我可以帮你的吗？",
    "嗨～有什么想聊的尽管说！",
    "你好！今天有什么需要我帮忙的吗？",
]


class AssistantService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._greeting_index = 0
        self._reply_callback: Callable[[str], Coroutine] | None = None

    def _get_guarded_tools(self) -> set[str]:
        if not self.settings.hitl_enabled:
            return set()
        config_tools = {t.strip() for t in self.settings.hitl_guarded_tools.split(",") if t.strip()}
        catalog_tools = guarded_tool_names()
        return config_tools | catalog_tools

    async def handle_message(
        self,
        user_id: str,
        user_text: str,
        *,
        deep_research: bool = False,
        progress_callback: Callable[[str], Coroutine] | None = None,
        reply_callback: Callable[[str], Coroutine] | None = None,
    ) -> AssistantResult:
        """ReAct entry point: receive message, run multi-step agent loop, return reply."""
        # Store context for HITL can_use_tool callback
        _current_user_id.set(user_id)
        self._reply_callback = reply_callback

        # Respect viz toggle as well as explicit flag
        if not deep_research:
            deep_research = agent_status.deep_research_active

        await agent_status.add_log("user", user_text)

        # Broadcast conversation turn to viz
        await agent_status.broadcast_conversation({"role": "user", "content": user_text})

        # ---- Guardian: prompt injection defense ----
        is_safe, guard_reason = await guard(user_text, self.settings)
        if not is_safe:
            await agent_status.add_log("guardian", f"blocked: {guard_reason}")
            await agent_status.broadcast_conversation({"role": "system", "content": f"[GUARDIAN] blocked: {guard_reason}"})
            return AssistantResult(
                reply_text=self.settings.guardian_block_message,
                intent="blocked",
                task_id=0,
                status="blocked",
            )
        # ---- end Guardian ----

        # ---- Simple greeting short-circuit ----
        if _SIMPLE_GREETING_PATTERN.match(user_text):
            reply = _SIMPLE_GREETING_REPLIES[self._greeting_index % len(_SIMPLE_GREETING_REPLIES)]
            self._greeting_index += 1
            await db.save_message(user_id, "user", user_text)
            await db.save_message(user_id, "assistant", reply)
            await agent_status.broadcast_conversation({"role": "user", "content": user_text})
            await agent_status.broadcast_conversation({"role": "assistant", "content": reply})
            await agent_status.add_log("assistant", reply[:120])
            await agent_status.update("done", "greeting short-circuit")
            return AssistantResult(reply_text=reply, intent="greeting", task_id=0, status="completed")
        # ---- end short-circuit ----

        task_id = await db.create_task_run(
            user_id=user_id,
            intent="deep_research" if deep_research else "react",
            status="running",
            input_text=user_text,
            route="react",
            plan="Deep Research" if deep_research else "ReAct loop",
        )
        await db.log_task_step(task_id, "react_started", detail="ReAct loop initiated")
        await agent_status.update("thinking", "processing message")

        try:
            history, profile_summary, memories = await asyncio.gather(
                db.get_recent_messages(user_id, limit=30),
                db.get_user_profile_summary(user_id),
                db.get_memories(user_id, limit=10),
            )
            history = await maybe_summarize(user_id, history, self.settings)

            # --- Deep Research: generate plan ---
            research_plan: ResearchPlan | None = None
            if deep_research:
                await agent_status.update("thinking", "generating research plan")
                await agent_status.add_log("system", "Deep research mode: generating plan...")
                research_plan = await generate_research_plan(user_text, self.settings)
                if research_plan:
                    await agent_status.broadcast_plan(research_plan.to_dict())
                    await db.log_task_step(task_id, "deep_research_plan", detail=json.dumps(research_plan.to_dict(), ensure_ascii=False)[:500])
                    if progress_callback:
                        await progress_callback(format_plan_overview_qq(research_plan))
                else:
                    await agent_status.add_log("system", "Plan generation failed, proceeding with normal ReAct")

            prompt = build_react_context_prompt(
                history=history,
                user_message=user_text,
                user_id=user_id,
                memories=memories,
                profile_summary=profile_summary,
                research_plan=research_plan,
            )

            reply_text = await self._run_react_loop(
                prompt=prompt, task_id=task_id, user_id=user_id,
                research_plan=research_plan, progress_callback=progress_callback,
            )
            reply_text = truncate_reply(reply_text, self.settings.qq_max_length)

            # Mark remaining subtasks as done
            if research_plan:
                research_plan.mark_remaining_done()
                await agent_status.broadcast_plan(research_plan.to_dict())
                if progress_callback:
                    await progress_callback(format_plan_progress_qq(research_plan))

            await db.save_message(user_id, "user", user_text)
            await db.save_message(user_id, "assistant", reply_text)
            await db.update_task_run(task_id, status="completed", result_text=reply_text, clear_error=True)

            # Broadcast assistant reply
            await agent_status.broadcast_conversation({"role": "assistant", "content": reply_text})
            await agent_status.add_log("assistant", reply_text[:120])

            # Check if reply contains a plan structure (legacy plan_tracker)
            if not research_plan:
                plan = extract_plan(reply_text)
                if plan:
                    await agent_status.broadcast_plan(plan)

            # Broadcast updated reminders
            user_reminders = await db.get_user_reminders(user_id)
            await agent_status.broadcast_reminders(user_reminders)

            await agent_status.update("done", "task completed")
            await db.log_task_step(task_id, "react_completed", detail="completed")
            asyncio.create_task(_reset_viz_idle())
            return AssistantResult(reply_text=reply_text, intent="react", task_id=task_id, status="completed")

        except Exception as exc:
            logger.error("react pipeline failed: %s", exc, exc_info=True)
            fallback = "刚刚出了点问题。你可以再发一次，我会继续帮你。"
            await db.save_message(user_id, "user", user_text)
            await db.save_message(user_id, "assistant", fallback)
            await db.log_task_step(task_id, "react_failed", status="failed", detail=str(exc))
            await db.update_task_run(task_id, status="failed", result_text=fallback, error=str(exc))
            await agent_status.add_log("system", str(exc))
            await agent_status.update("done", "task failed")
            asyncio.create_task(_reset_viz_idle())
            return AssistantResult(reply_text=fallback, intent="react", task_id=task_id, status="failed")

    async def _run_react_loop(
        self,
        prompt: str,
        task_id: int,
        user_id: str,
        *,
        research_plan: ResearchPlan | None = None,
        progress_callback: Callable[[str], Coroutine] | None = None,
    ) -> str:
        """Run the ReAct loop with streaming, broadcasting each step to viz."""
        mcp_servers: dict = {"nanoclaw-tools": mcp_server}
        if self.settings.rag_server_cwd:
            mcp_servers["rag-knowledge"] = {
                "command": self.settings.rag_server_command,
                "args": ["-m", "src.mcp_server.server"],
                "cwd": self.settings.rag_server_cwd,
            }

        guarded = self._get_guarded_tools()

        options = ClaudeAgentOptions(
            model=self.settings.model,
            system_prompt=build_system_prompt(self.settings.assistant_name),
            permission_mode="default" if guarded else "bypassPermissions",
            env={
                "ANTHROPIC_API_KEY": self.settings.anthropic_api_key,
                "ANTHROPIC_BASE_URL": self.settings.anthropic_base_url,
            },
            max_turns=self.settings.max_turns,
            cwd=".",
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tool_names(),
            can_use_tool=self._make_can_use_tool(guarded) if guarded else None,
        )

        final_result = ""
        tool_names: dict[str, str] = {}
        step_counter = 0

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                message_stream = query(prompt=prompt, options=options)
                async for message in message_stream:
                    if isinstance(message, AssistantMessage):
                        step_counter += 1
                        await self._handle_react_step(
                            message, tool_names, step_counter, task_id,
                            research_plan=research_plan, progress_callback=progress_callback,
                        )
                        continue
                    if isinstance(message, ResultMessage) and message.result:
                        final_result = message.result
                if final_result:
                    return final_result
            except asyncio.TimeoutError:
                logger.warning("assistant timed out on attempt %s", attempt + 1)
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue
                raise
            except (ConnectionError, OSError):
                logger.warning("assistant network issue on attempt %s", attempt + 1, exc_info=True)
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue
                raise
            except Exception as exc:
                err_msg = str(exc)
                if "exit code" in err_msg and attempt < max_retries:
                    logger.warning("assistant subprocess crashed on attempt %s: %s", attempt + 1, err_msg)
                    await asyncio.sleep(2)
                    continue
                raise
        raise RuntimeError("empty result from assistant agent")

    async def _handle_react_step(
        self,
        message: AssistantMessage,
        tool_names: dict[str, str],
        step: int,
        task_id: int,
        *,
        research_plan: ResearchPlan | None = None,
        progress_callback: Callable[[str], Coroutine] | None = None,
    ) -> None:
        """Process one step of the ReAct loop and broadcast rich events to viz."""
        saw_tool_activity = False
        saw_text_reply = False

        for block in message.content:
            if isinstance(block, ToolUseBlock):
                saw_tool_activity = True
                tool_names[block.id] = block.name
                await agent_status.update("tool_use", block.name)

                # Rich tool call event
                await agent_status.broadcast_tool_call(
                    {
                        "tool_name": block.name,
                        "tool_id": block.id,
                        "input": block.input,
                        "step": step,
                    }
                )
                await agent_status.add_log("tool", _format_tool_use_log(block))
                await db.log_task_step(task_id, f"tool_call_{block.name}", detail=json.dumps(block.input, ensure_ascii=False)[:500])
                continue

            if isinstance(block, ToolResultBlock):
                saw_tool_activity = True
                tool_name = tool_names.get(block.tool_use_id, "tool")
                await agent_status.update("tool_use", tool_name)

                # Rich tool result event
                await agent_status.broadcast_tool_result(
                    {
                        "tool_name": tool_name,
                        "tool_id": block.tool_use_id,
                        "result": block.content,
                        "is_error": block.is_error,
                        "step": step,
                    }
                )
                await agent_status.add_log("tool", _format_tool_result_log(tool_name, block))
                await db.log_task_step(task_id, f"tool_result_{tool_name}", detail=str(block.content)[:500])
                continue

            text = getattr(block, "text", "")
            if text and text.strip():
                saw_text_reply = True
                # Broadcast thinking/reasoning step
                await agent_status.broadcast_thinking(
                    {
                        "content": text,
                        "step": step,
                    }
                )

                # Deep research: detect subtask completion
                if research_plan and detect_subtask_completion(text, research_plan):
                    next_subtask = research_plan.advance_to_next()
                    await agent_status.broadcast_plan(research_plan.to_dict())
                    if next_subtask:
                        await agent_status.add_log("system", f"Subtask completed. Now working on: {next_subtask.name}")
                        if progress_callback:
                            await progress_callback(format_plan_progress_qq(research_plan))
                    else:
                        await agent_status.add_log("system", "All subtasks completed!")

        if saw_text_reply and not saw_tool_activity:
            await agent_status.update("responding", "generating reply")

    def _make_can_use_tool(self, guarded_tools: set[str]):
        """Create the can_use_tool callback for the SDK, bound to this service instance."""

        async def can_use_tool(
            tool_name: str,
            tool_input: dict,
            context: ToolPermissionContext,
        ):
            # Auto-approve non-guarded tools
            if tool_name not in guarded_tools:
                return PermissionResultAllow()

            user_id = _current_user_id.get("")
            if not user_id:
                logger.warning("HITL: no user_id in context, auto-approving %s", tool_name)
                return PermissionResultAllow()

            manager = get_manager()
            pending = manager.create_pending(
                user_id=user_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_use_id=context.tool_use_id,
            )

            # Send confirmation request to user
            if self._reply_callback:
                confirmation = format_confirmation_message(pending)
                await self._reply_callback(confirmation)
                await agent_status.add_log("hitl", f"Waiting for approval: {tool_name} ({pending.id})")
            else:
                logger.warning("HITL: no reply_callback, auto-rejecting %s", tool_name)
                return PermissionResultDeny(message="No reply channel available for confirmation")

            # Block until user responds or timeout
            decision = await manager.wait_for_decision(pending.id)

            if decision == PendingToolStatus.APPROVED:
                await agent_status.add_log("hitl", f"Approved: {tool_name} ({pending.id})")
                return PermissionResultAllow()
            else:
                reason = pending.reject_reason or decision.value
                await agent_status.add_log("hitl", f"Rejected: {tool_name} ({pending.id}) — {reason}")
                return PermissionResultDeny(message=f"Tool call {tool_name} was rejected: {reason}")

        return can_use_tool


def build_react_context_prompt(
    history: list[dict],
    user_message: str,
    user_id: str,
    memories: list[dict],
    profile_summary: str,
    *,
    research_plan: ResearchPlan | None = None,
) -> str:
    sections = [
        f"Current user_id: {user_id}",
        f"User profile summary:\n{profile_summary or 'No durable profile yet.'}",
    ]
    if memories:
        memory_lines = []
        for item in memories:
            score_str = f" (relevance: {item['score']:.2f})" if "score" in item else ""
            memory_lines.append(f"- [{item['category']}] {item['content']}{score_str}")
        sections.append("Relevant active memories:\n" + "\n".join(memory_lines))
    if history:
        history_lines = []
        for item in history:
            if item["role"] == "system_summary":
                history_lines.append(f"[摘要] {item['content']}")
            else:
                history_lines.append(f"[{item['role']}] {item['content']}")
        sections.append("Recent conversation:\n" + "\n".join(history_lines))
    if research_plan:
        sections.append(build_plan_context_injection(research_plan))
    sections.append(f"Latest user message:\n{user_message}")
    sections.append("Reply in Chinese to the user, but keep tool arguments machine-friendly.")
    return "\n\n".join(sections)


def truncate_reply(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    safe_room = max(0, max_length - 16)
    return text[:safe_room].rstrip() + "\n\n[truncated]"


async def _reset_viz_idle() -> None:
    await asyncio.sleep(4)
    await agent_status.update("idle", "resting")


def _format_tool_use_log(block: ToolUseBlock) -> str:
    payload = _compact_tool_payload(block.input)
    if payload:
        return "Calling {0}({1})".format(block.name, payload)
    return "Calling {0}".format(block.name)


def _format_tool_result_log(tool_name: str, block: ToolResultBlock) -> str:
    prefix = "Tool failed" if block.is_error else "Tool result"
    content = _compact_tool_payload(block.content)
    if content:
        return "{0}: {1} -> {2}".format(prefix, tool_name, content)
    return "{0}: {1}".format(prefix, tool_name)


def _compact_tool_payload(payload: object, *, limit: int = 140) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        text = payload.strip()
    else:
        try:
            text = json.dumps(payload, ensure_ascii=False)
        except TypeError:
            text = str(payload).strip()
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text
