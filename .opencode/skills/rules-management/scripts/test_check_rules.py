"""Offline checks for check_rules: rule format validation and version log cross-referencing."""

import os
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))

import add_rule
import check_rules
from rules_format import render_rule_file


VALID_RULE_TEXT = render_rule_file("1", "repo wide", "One well-formed rule.", ["Some goal"])
TASK_RULE_TEXT = render_rule_file("1", "task specific: some-task", "Task rule.", ["Some goal"])
EXISTING_ENTRY = "- 2026-11-11 — existing-rule v1"


def set_file_date(path, day):
    timestamp = datetime(day.year, day.month, day.day, 12, 0, 0).timestamp()
    os.utime(path, (timestamp, timestamp))


class CheckRulesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.skills_dir = self.root / ".opencode" / "skills"

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_skill(self, task):
        skill_dir = self.skills_dir / task
        skill_dir.mkdir(parents=True)
        skill_dir.joinpath("SKILL.md").write_text(f"---\nname: {task}\ndescription: Does something.\n---\n")

    def build_framework(self, rule_texts, log_lines, manifest_lines=None):
        rules_dir = self.root / "rules"
        rules_dir.mkdir()
        for filename, text in rule_texts.items():
            rule_path = rules_dir / filename
            rule_path.write_text(text)
            set_file_date(rule_path, date(2026, 11, 11))
        manifest_path = self.root / "rules.md"
        if manifest_lines is None:
            manifest_lines = ["## Rules version log"] + log_lines
        manifest_path.write_text("\n".join(manifest_lines) + "\n")
        return rules_dir, manifest_path

    def assert_problem(self, problems, expected_fragment):
        self.assertTrue(any(expected_fragment in problem for problem in problems), problems)

    def test_valid_framework_has_no_problems(self):
        rules_dir, manifest_path = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, [EXISTING_ENTRY])
        self.assertEqual(check_rules.collect_problems(rules_dir, manifest_path), [])

    def test_rule_with_update_history_has_no_problems(self):
        log_lines = [
            EXISTING_ENTRY,
            "- 2026-11-12 — existing-rule v2 — tightened the wording",
        ]
        rules_dir, manifest_path = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, log_lines)
        set_file_date(rules_dir / "existing-rule.md", date(2026, 11, 12))
        self.assertEqual(check_rules.collect_problems(rules_dir, manifest_path), [])

    def test_non_kebab_filename_is_a_problem(self):
        rules_dir, manifest_path = self.build_framework({"Existing_Rule.md": VALID_RULE_TEXT}, [EXISTING_ENTRY])
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "kebab-case")

    def test_rule_with_bad_scope_is_a_problem(self):
        text = render_rule_file("1", "everywhere", "Text.", ["Goal"])
        rules_dir, manifest_path = self.build_framework({"broken-rule.md": text}, ["- 2026-11-11 — broken-rule v1"])
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "scope must be")

    def test_rule_with_bad_strictness_is_a_problem(self):
        text = render_rule_file("zero", "repo wide", "Text.", ["Goal"])
        rules_dir, manifest_path = self.build_framework({"broken-rule.md": text}, ["- 2026-11-11 — broken-rule v1"])
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "whole number")

    def test_rule_with_missing_section_is_a_problem(self):
        text = "## Strictness\n1\n\n## Description\nText.\n\n## Context\n- Goal\n"
        rules_dir, manifest_path = self.build_framework({"broken-rule.md": text}, ["- 2026-11-11 — broken-rule v1"])
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "sections must be")

    def test_rule_with_empty_description_is_a_problem(self):
        text = render_rule_file("1", "repo wide", "   ", ["Goal"])
        rules_dir, manifest_path = self.build_framework({"broken-rule.md": text}, ["- 2026-11-11 — broken-rule v1"])
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "description must not be empty")

    def test_rule_with_non_bullet_context_is_a_problem(self):
        text = "## Strictness\n1\n\n## Scope\nrepo wide\n\n## Description\nText.\n\n## Context\nGoal\n"
        rules_dir, manifest_path = self.build_framework({"broken-rule.md": text}, ["- 2026-11-11 — broken-rule v1"])
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "list items")

    def test_log_entry_without_rule_file_is_a_problem(self):
        log_lines = [EXISTING_ENTRY, "- 2026-11-12 — ghost-rule v1"]
        rules_dir, manifest_path = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, log_lines)
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "ghost-rule has no rule file")

    def test_rule_file_without_log_entry_is_a_problem(self):
        rule_texts = {"existing-rule.md": VALID_RULE_TEXT, "unlogged-rule.md": VALID_RULE_TEXT}
        rules_dir, manifest_path = self.build_framework(rule_texts, [EXISTING_ENTRY])
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "unlogged-rule.md: no version log entry")

    def test_version_gap_is_a_problem(self):
        log_lines = [EXISTING_ENTRY, "- 2026-11-13 — existing-rule v3"]
        rules_dir, manifest_path = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, log_lines)
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "without gaps or repeats")

    def test_duplicate_version_is_a_problem(self):
        log_lines = [EXISTING_ENTRY, "- 2026-11-12 — existing-rule v1"]
        rules_dir, manifest_path = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, log_lines)
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "without gaps or repeats")

    def test_out_of_order_log_is_a_problem(self):
        rule_texts = {"existing-rule.md": VALID_RULE_TEXT, "second-rule.md": VALID_RULE_TEXT}
        log_lines = [EXISTING_ENTRY, "- 2026-11-10 — second-rule v1"]
        rules_dir, manifest_path = self.build_framework(rule_texts, log_lines)
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "oldest first")

    def test_malformed_log_entry_is_a_problem(self):
        rules_dir, manifest_path = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, ["- 2026-11-11 existing-rule v1"])
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "entry must look like")

    def test_unreal_date_is_a_problem(self):
        rules_dir, manifest_path = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, ["- 2026-13-45 — existing-rule v1"])
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "not a real date")

    def test_missing_version_log_section_is_a_problem(self):
        rules_dir, manifest_path = self.build_framework(
            {"existing-rule.md": VALID_RULE_TEXT}, [], manifest_lines=["# Rules", "", "No version log here."]
        )
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "missing the '## Version log' section")

    def test_missing_manifest_is_a_problem(self):
        rules_dir, manifest_path = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, [EXISTING_ENTRY])
        manifest_path.unlink()
        self.assert_problem(check_rules.collect_problems(rules_dir, manifest_path), "file is missing")

    def test_task_specific_rule_without_its_skill_is_a_problem(self):
        rules_dir, _ = self.build_framework({"task-rule.md": TASK_RULE_TEXT}, ["- 2026-11-11 — task-rule v1"])
        problems = check_rules.task_skill_problems(rules_dir, self.skills_dir)
        self.assert_problem(problems, "task specific 'some-task' has no SKILL.md in .opencode/skills/some-task")

    def test_task_specific_rule_with_its_skill_is_no_problem(self):
        rules_dir, _ = self.build_framework({"task-rule.md": TASK_RULE_TEXT}, ["- 2026-11-11 — task-rule v1"])
        self.create_skill("some-task")
        self.assertEqual(check_rules.task_skill_problems(rules_dir, self.skills_dir), [])

    def test_non_task_rules_are_not_skill_checked(self):
        rules_dir, _ = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, [EXISTING_ENTRY])
        self.assertEqual(check_rules.task_skill_problems(rules_dir, self.skills_dir), [])

    def test_file_edited_after_its_latest_version_is_a_problem(self):
        rules_dir, manifest_path = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, [EXISTING_ENTRY])
        set_file_date(rules_dir / "existing-rule.md", date(2026, 11, 14))
        problems = check_rules.collect_problems(rules_dir, manifest_path)
        self.assert_problem(
            problems,
            "latest logged version v1 is dated 2026-11-11 but the file was last edited 2026-11-14",
        )

    def test_path_specific_rule_outputs_its_agents_md_paths(self):
        text = render_rule_file("1", "path specific: MMM/*", "Path rule.", ["Some goal"])
        rules_dir, _ = self.build_framework({"path-rule.md": text}, ["- 2026-11-11 — path-rule v1"])
        (self.root / "MMM" / "sub").mkdir(parents=True)
        (self.root / "MMM" / "AGENTS.md").write_text("instructions\n")
        (self.root / "MMM" / "sub" / "AGENTS.md").write_text("more instructions\n")
        notes = check_rules.path_verification_notes(rules_dir, self.root)
        self.assertEqual(notes, ["path-rule.md: MMM/AGENTS.md, MMM/sub/AGENTS.md"])

    def test_path_specific_rule_without_agents_md_points_at_the_root_fallback(self):
        text = render_rule_file("1", "path specific: nowhere/*", "Path rule.", ["Some goal"])
        rules_dir, _ = self.build_framework({"path-rule.md": text}, ["- 2026-11-11 — path-rule v1"])
        notes = check_rules.path_verification_notes(rules_dir, self.root)
        self.assertEqual(notes, ["path-rule.md: no AGENTS.md inside nowhere/* — verify in the root AGENTS.md"])

    def test_root_agents_md_is_never_listed_as_a_path_implementation(self):
        text = render_rule_file("1", "path specific: *", "Path rule.", ["Some goal"])
        rules_dir, _ = self.build_framework({"path-rule.md": text}, ["- 2026-11-11 — path-rule v1"])
        (self.root / "AGENTS.md").write_text("root instructions\n")
        notes = check_rules.path_verification_notes(rules_dir, self.root)
        self.assertEqual(notes, ["path-rule.md: no AGENTS.md inside * — verify in the root AGENTS.md"])

    def test_non_path_rules_produce_no_verification_notes(self):
        rule_texts = {"existing-rule.md": VALID_RULE_TEXT, "task-rule.md": TASK_RULE_TEXT}
        rules_dir, _ = self.build_framework(rule_texts, [EXISTING_ENTRY, "- 2026-11-11 — task-rule v1"])
        self.assertEqual(check_rules.path_verification_notes(rules_dir, self.root), [])

    def test_framework_stays_valid_after_adding_a_task_rule(self):
        rules_dir, manifest_path = self.build_framework({"existing-rule.md": VALID_RULE_TEXT}, [EXISTING_ENTRY])
        self.create_skill("fresh-task")
        add_rule.add_rule(
            "fresh-rule",
            "1",
            "task specific: fresh-task",
            "New rule text.",
            ["Fresh goal"],
            rules_dir,
            manifest_path,
            date(2026, 11, 12),
        )
        set_file_date(rules_dir / "fresh-rule.md", date(2026, 11, 12))
        self.assertEqual(check_rules.collect_problems(rules_dir, manifest_path), [])
        self.assertEqual(check_rules.task_skill_problems(rules_dir, self.skills_dir), [])


if __name__ == "__main__":
    unittest.main()
