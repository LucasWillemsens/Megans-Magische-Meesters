"""Offline checks for add_rule: input validation, file creation, and log appending."""

import sys
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))

import add_rule
from rules_format import parse_rule_file, read_version_log


MANIFEST_TEXT = """## Rules version log

- 2026-11-11 — existing-rule v1
"""


class AddRuleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.rules_dir = self.root / "rules"
        self.rules_dir.mkdir()
        self.manifest_path = self.root / "rules.md"
        self.manifest_path.write_text(MANIFEST_TEXT)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_rule(self, **overrides):
        fields = {
            "title": "tests-pass-before-every-push",
            "strictness": "2",
            "scope": "repo wide",
            "description": "The full test suite passes before every push.",
            "context_items": ["Tests and reliability"],
        }
        fields.update(overrides)
        add_rule.add_rule(
            fields["title"],
            fields["strictness"],
            fields["scope"],
            fields["description"],
            fields["context_items"],
            self.rules_dir,
            self.manifest_path,
            date(2026, 11, 12),
        )

    def test_created_rule_file_follows_the_documented_format(self):
        self.create_rule()
        parsed = parse_rule_file((self.rules_dir / "tests-pass-before-every-push.md").read_text())
        self.assertEqual(parsed["strictness"], 2)
        self.assertEqual(parsed["scope"], "repo wide")
        self.assertEqual(parsed["description"], "The full test suite passes before every push.")
        self.assertEqual(parsed["context_items"], ["Tests and reliability"])

    def test_created_v1_entry_is_appended_after_existing_entries(self):
        self.create_rule()
        log_lines = read_version_log(self.manifest_path.read_text())
        self.assertEqual(
            log_lines,
            [
                "- 2026-11-11 — existing-rule v1",
                "- 2026-11-12 — tests-pass-before-every-push v1",
            ],
        )

    def test_first_entry_lands_directly_below_the_heading(self):
        self.manifest_path.write_text("## Rules version log\n")
        self.create_rule()
        log_lines = read_version_log(self.manifest_path.read_text())
        self.assertEqual(log_lines, ["- 2026-11-12 — tests-pass-before-every-push v1"])

    def test_existing_rule_title_is_rejected(self):
        self.create_rule()
        with self.assertRaises(ValueError) as raised:
            self.create_rule()
        self.assertIn("already exists", str(raised.exception))

    def test_invalid_input_is_rejected_without_writing_anything(self):
        invalid_inputs = [
            {"title": "Not Kebab"},
            {"title": "not_kebab"},
            {"strictness": "high"},
            {"strictness": "0"},
            {"scope": "everywhere"},
            {"description": "   "},
            {"context_items": []},
            {"context_items": [""]},
            {"context_items": ["one goal\nanother goal"]},
        ]
        for overrides in invalid_inputs:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self.create_rule(**overrides)
        self.assertEqual(list(self.rules_dir.glob("*.md")), [])

    def test_manifest_without_version_log_is_rejected_without_writing_anything(self):
        self.manifest_path.write_text("# Rules\n\nNo log section here.\n")
        with self.assertRaises(ValueError) as raised:
            self.create_rule()
        self.assertIn("## Rules version log", str(raised.exception))
        self.assertEqual(list(self.rules_dir.glob("*.md")), [])


if __name__ == "__main__":
    unittest.main()
