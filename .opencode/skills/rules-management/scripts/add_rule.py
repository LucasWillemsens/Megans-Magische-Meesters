#!/usr/bin/env python3
"""Create a new rule in rules/ and note its v1 in the rules.md version log.

Usage:
    python3 .opencode/skills/rules-management/scripts/add_rule.py \
        --title <kebab-case-title> --strictness <number> \
        --scope "<scope>" --description "<text>" --context "<goal>" [--context "<goal>" ...]

Example:
    python3 .opencode/skills/rules-management/scripts/add_rule.py \
        --title tests-pass-before-every-push \
        --strictness 2 \
        --scope "repo wide" \
        --description "The full test suite passes before every push." \
        --context "Tests and reliability"
"""

import argparse
import sys
from datetime import date

from rules_format import (
    append_version_log_entry,
    context_items_problem,
    find_repo_root,
    read_version_log,
    render_rule_file,
    render_version_entry,
    scope_problem,
    strictness_problem,
    title_problem,
)

REPO_ROOT = find_repo_root()
RULES_DIR = REPO_ROOT / "rules"
MANIFEST_PATH = REPO_ROOT / "rules.md"


def rule_input_problems(title, strictness, scope, description, context_items):
    problems = []
    for problem in (
        title_problem(title),
        strictness_problem(strictness),
        scope_problem(scope),
        context_items_problem(context_items),
    ):
        if problem:
            problems.append(problem)
    if not description.strip():
        problems.append("description must not be empty")
    return problems


def add_rule(title, strictness, scope, description, context_items, rules_dir, manifest_path, entry_date=None):
    if entry_date is None:
        entry_date = date.today()
    problems = rule_input_problems(title, strictness, scope, description, context_items)
    rule_path = rules_dir / f"{title}.md"
    if rule_path.exists():
        problems.append(f"rules/{title}.md already exists — edit it and note its next version in rules.md instead")
    if manifest_path.exists():
        manifest_text = manifest_path.read_text()
        try:
            read_version_log(manifest_text)
        except ValueError as problem:
            problems.append(f"rules.md: {problem}")
    else:
        problems.append("rules.md is missing")
    if problems:
        raise ValueError("\n".join(problems))
    rule_path.write_text(
        render_rule_file(
            strictness.strip(),
            scope.strip(),
            description.strip(),
            [item.strip() for item in context_items],
        )
    )
    manifest_path.write_text(
        append_version_log_entry(manifest_text, render_version_entry(entry_date, title, 1))
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Create a new rule and note its v1 in the rules.md version log."
    )
    parser.add_argument("--title", required=True, help="kebab-case rule title; becomes the filename in rules/")
    parser.add_argument("--strictness", required=True, help="whole number 1 or higher; priority when rules conflict")
    parser.add_argument("--scope", required=True, help="'repo wide', 'path specific: {PATH}', or 'task specific: {TASK}'")
    parser.add_argument("--description", required=True, help="what the rule says")
    parser.add_argument(
        "--context",
        required=True,
        action="append",
        help="goal that revealed the need for the rule; repeat the flag for several goals",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args()
    try:
        add_rule(args.title, args.strictness, args.scope, args.description, args.context, RULES_DIR, MANIFEST_PATH)
    except ValueError as problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        sys.exit(1)
    print(f"Created rules/{args.title}.md and noted its v1 in the rules.md version log")
    print("Implement the rule's substance at the location its scope implies")


if __name__ == "__main__":
    main()
