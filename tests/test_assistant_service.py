import sys
from pathlib import Path
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

fake_sdk = types.ModuleType("claude_agent_sdk")
fake_sdk.AssistantMessage = type("AssistantMessage", (), {})
fake_sdk.ResultMessage = type("ResultMessage", (), {})
fake_sdk.ClaudeAgentOptions = type("ClaudeAgentOptions", (), {"__init__": lambda self, **kwargs: None})


async def _unused_query(*args, **kwargs):
    if False:
        yield None


fake_sdk.query = _unused_query
sys.modules.setdefault("claude_agent_sdk", fake_sdk)

fake_aiosqlite = types.ModuleType("aiosqlite")
fake_aiosqlite.Row = dict
fake_aiosqlite.Connection = object
fake_aiosqlite.OperationalError = Exception
sys.modules.setdefault("aiosqlite", fake_aiosqlite)

fake_tools_package = types.ModuleType("tools")
fake_tools_server = types.ModuleType("tools.server")
fake_tools_server.mcp_server = object()
sys.modules.setdefault("tools", fake_tools_package)
sys.modules.setdefault("tools.server", fake_tools_server)

fake_viz = types.ModuleType("viz")


class _FakeStatus:
    async def add_log(self, *args, **kwargs):
        return None

    async def update(self, *args, **kwargs):
        return None


fake_viz.agent_status = _FakeStatus()
sys.modules.setdefault("viz", fake_viz)

import assistant_service as assistant_module
from assistant_service import AssistantService
from settings import Settings


REMINDER_TEXT = "\u63d0\u9192\u6211\u5f00\u4f1a"
REMINDER_TIME = "\u660e\u5929\u4e0b\u53483\u70b9"


class AssistantServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = AssistantService(
            Settings(
                app_id=None,
                bot_token=None,
                assistant_name="OpenClaw",
                anthropic_api_key=None,
                anthropic_base_url=None,
                model="test-model",
                max_turns=2,
                qq_max_length=2000,
            )
        )
        self.original_db = assistant_module.db
        self.original_run_agent = AssistantService._run_agent

    async def asyncTearDown(self):
        assistant_module.db = self.original_db
        AssistantService._run_agent = self.original_run_agent

    async def test_reminder_without_time_moves_to_needs_input(self):
        fake_db = FakeDb()
        assistant_module.db = fake_db
        AssistantService._run_agent = fake_run_agent
        result = await self.service.handle_message("user-1", REMINDER_TEXT)
        self.assertEqual(result.status, "needs_input")
        self.assertEqual(fake_db.task_run["status"], "needs_input")
        self.assertEqual(fake_db.task_run["pending_field"], "trigger_expr")
        self.assertEqual(fake_db.task_run["context_json"]["original_request"], REMINDER_TEXT)
        self.assertIn("needs_input", [step["step_name"] for step in fake_db.steps])

    async def test_pending_reminder_resumes_when_user_supplies_time(self):
        fake_db = FakeDb(
            pending_task={
                "id": 7,
                "user_id": "user-1",
                "intent": "reminder_create",
                "status": "needs_input",
                "input_text": REMINDER_TEXT,
                "context_json": {"original_request": REMINDER_TEXT, "intent": "reminder_create"},
            }
        )
        assistant_module.db = fake_db
        AssistantService._run_agent = fake_run_agent
        result = await self.service.handle_message("user-1", REMINDER_TIME)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.task_id, 7)
        self.assertEqual(fake_db.updated_task["status"], "completed")
        self.assertIn("Supplemental reminder time", fake_db.saved_messages[0][2])
        step_names = [step["step_name"] for step in fake_db.steps]
        self.assertIn("task_resumed", step_names)
        self.assertIn("task_completed", step_names)


async def fake_run_agent(self, prompt: str, intent: str) -> str:
    return "\u597d\u7684\uff0c\u6211\u5df2\u7ecf\u5e2e\u4f60\u8bb0\u4e0b\u6765\u4e86\u3002"


class FakeDb:
    def __init__(self, pending_task=None):
        self.pending_task = pending_task
        self.task_run = None
        self.updated_task = {}
        self.steps = []
        self.saved_messages = []

    async def get_latest_needs_input_task(self, user_id, intent=None):
        return self.pending_task

    async def create_task_run(self, **kwargs):
        self.task_run = {"id": 1, **kwargs}
        self.updated_task = dict(self.task_run)
        return 1

    async def log_task_step(self, task_run_id, step_name, status="completed", detail=None):
        self.steps.append({"task_run_id": task_run_id, "step_name": step_name, "status": status, "detail": detail})
        return len(self.steps)

    async def update_task_run(self, task_id, **kwargs):
        if self.task_run and self.task_run["id"] == task_id:
            self.updated_task.update(kwargs)
            self.task_run = dict(self.updated_task)
            return
        if self.pending_task and self.pending_task["id"] == task_id:
            self.pending_task.update(kwargs)
            self.updated_task = dict(self.pending_task)

    async def get_recent_messages(self, user_id, limit=12):
        return []

    async def get_memories(self, user_id, limit=20):
        return []

    async def refresh_user_profile_summary(self, user_id):
        return "No durable profile yet."

    async def save_message(self, session_id, role, content):
        self.saved_messages.append((session_id, role, content))


if __name__ == "__main__":
    unittest.main()
