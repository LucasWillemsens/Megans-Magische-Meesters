"""Offline checks for PR comment selection eligibility."""

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("pick_pr_comment.py")
SPEC = importlib.util.spec_from_file_location("pick_pr_comment", SCRIPT)
picker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(picker)


class EligibilityTests(unittest.TestCase):
    def thread(self, **overrides):
        value = {
            "isResolved": False,
            "path": "src/example.py",
            "line": 12,
            "originalLine": None,
            "comments": {"nodes": [{"body": "Please fix"}]},
        }
        value.update(overrides)
        return value

    def test_inline_unresolved_thread_is_eligible(self):
        self.assertTrue(picker.is_eligible(self.thread()))

    def test_general_or_non_inline_comments_are_excluded(self):
        self.assertFalse(picker.is_eligible(self.thread(path=None)))
        self.assertFalse(picker.is_eligible(self.thread(line=None, originalLine=None)))
        self.assertFalse(picker.is_eligible(self.thread(comments={"nodes": []})))

    def test_resolved_thread_is_excluded(self):
        self.assertFalse(picker.is_eligible(self.thread(isResolved=True)))


if __name__ == "__main__":
    unittest.main()
