import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from intents import MEMORY_WRITE, QUESTION, REMINDER_CREATE, TASK_PLANNING, detect_intent, needs_reminder_clarification


class IntentTests(unittest.TestCase):
    def test_detects_reminder_requests(self):
        text = "\u660e\u5929\u4e0b\u53483\u70b9\u63d0\u9192\u6211\u5f00\u4f1a"
        self.assertEqual(detect_intent(text), REMINDER_CREATE)

    def test_detects_task_planning_requests(self):
        text = "\u5e2e\u6211\u89c4\u5212\u660e\u5929\u7684\u5b66\u4e60\u5b89\u6392"
        self.assertEqual(detect_intent(text), TASK_PLANNING)

    def test_detects_memory_write_requests(self):
        text = "\u8bb0\u4f4f\u6211\u559c\u6b22\u7b80\u6d01\u7684\u56de\u7b54"
        self.assertEqual(detect_intent(text), MEMORY_WRITE)

    def test_detects_questions(self):
        text = "\u73b0\u5728\u51e0\u70b9\uff1f"
        self.assertEqual(detect_intent(text), QUESTION)

    def test_reminder_clarification_needed_when_no_time(self):
        text = "\u63d0\u9192\u6211\u559d\u6c34"
        self.assertTrue(needs_reminder_clarification(text))

    def test_reminder_clarification_not_needed_with_time(self):
        text = "\u4eca\u5929\u665a\u4e0a8\u70b9\u63d0\u9192\u6211\u8dd1\u6b65"
        self.assertFalse(needs_reminder_clarification(text))


if __name__ == "__main__":
    unittest.main()
