#!/usr/bin/env python3
"""Validate the rule files in rules/ using the version log in rules.md.

Checks that every rule file follows the rule format, that every version log
entry is well-formed and oldest first, that the log and rules/ agree, that
every rule's latest logged version is dated the same day the file was last
edited, and that every task-specific rule's skill exists. Implementations
never follow a strict structure, so their content is verified manually: for
every path-specific rule the script prints the AGENTS.md files found inside
the rule's path, or the root AGENTS.md fallback.

Usage:
    python3 .opencode/skills/rules-management/scripts/check_rules.py
"""

import sys
from datetime import date

from rules_format import find_repo_root, parse_rule_file, parse_version_entry, read_version_log, title_problem

REPO_ROOT = find_repo_root()
RULES_DIR = REPO_ROOT / "rules"
MANIFEST_PATH = REPO_ROOT / "rules.md"
SKILLS_DIR = REPO_ROOT / ".opencode" / "skills"


def rule_file_problems(rule_path):
    problems = []
    title = title_problem(rule_path.stem)
    if title:
        problems.append(f"{rule_path.name}: {title}")
    try:
        parse_rule_file(rule_path.read_text())
    except ValueError as problem:
        problems.append(f"{rule_path.name}: {problem}")
    return problems


def rule_scopes(rules_dir):
    scopes = {}
    for rule_path in sorted(rules_dir.glob("*.md")):
        try:
            scopes[rule_path.name] = parse_rule_file(rule_path.read_text())["scope"]
        except ValueError:
            continue
    return scopes


def parsed_log_entries(manifest_text):
    entries = []
    problems = []
    for line in read_version_log(manifest_text):
        try:
            entries.append(parse_version_entry(line))
        except ValueError as problem:
            problems.append(f"rules.md: {line}: {problem}")
    return entries, problems


def version_log_problems(entries, rule_stems):
    problems = []
    entry_dates = [entry["date"] for entry in entries]
    if entry_dates != sorted(entry_dates):
        problems.append("rules.md: version log entries must be oldest first")
    versions_by_title = {}
    for entry in entries:
        versions_by_title.setdefault(entry["title"], []).append(entry["version"])
    for title, versions in sorted(versions_by_title.items()):
        if sorted(versions) != list(range(1, len(versions) + 1)):
            found = ", ".join(f"v{version}" for version in sorted(versions))
            problems.append(f"rules.md: {title}: versions must run from v1 without gaps or repeats, found {found}")
        if title not in rule_stems:
            problems.append(f"rules.md: {title} has no rule file in rules/")
    for stem in sorted(rule_stems):
        if stem not in versions_by_title:
            problems.append(f"{stem}.md: no version log entry in rules.md")
    return problems


def version_date_problems(rules_dir, entries):
    latest_by_title = {}
    for entry in entries:
        latest = latest_by_title.get(entry["title"])
        if latest is None or entry["version"] > latest["version"]:
            latest_by_title[entry["title"]] = entry
    problems = []
    for title, latest in sorted(latest_by_title.items()):
        rule_path = rules_dir / f"{title}.md"
        if not rule_path.exists():
            continue
        edited_date = date.fromtimestamp(rule_path.stat().st_mtime)
        if edited_date != latest["date"]:
            problems.append(
                f"{title}.md: latest logged version v{latest['version']} is dated "
                f"{latest['date'].isoformat()} but the file was last edited {edited_date.isoformat()}"
            )
    return problems


def task_skill_problems(rules_dir, skills_dir):
    problems = []
    for rule_name, scope in rule_scopes(rules_dir).items():
        prefix = "task specific: "
        if not scope.startswith(prefix):
            continue
        task = scope[len(prefix):].strip()
        if not (skills_dir / task / "SKILL.md").exists():
            problems.append(f"{rule_name}: task specific '{task}' has no SKILL.md in .opencode/skills/{task}")
    return problems


def path_verification_notes(rules_dir, repo_root):
    notes = []
    for rule_name, scope in rule_scopes(rules_dir).items():
        prefix = "path specific: "
        if not scope.startswith(prefix):
            continue
        path_scope = scope[len(prefix):].strip()
        directory = repo_root / path_scope.split("*")[0].rstrip("/")
        agents_files = []
        if directory.is_dir():
            agents_files = sorted(
                path for path in directory.rglob("AGENTS.md") if path != repo_root / "AGENTS.md"
            )
        if agents_files:
            locations = ", ".join(str(path.relative_to(repo_root)) for path in agents_files)
            notes.append(f"{rule_name}: {locations}")
        else:
            notes.append(f"{rule_name}: no AGENTS.md inside {path_scope} — verify in the root AGENTS.md")
    return notes


def collect_problems(rules_dir, manifest_path):
    problems = []
    rule_paths = sorted(rules_dir.glob("*.md"))
    rule_stems = {path.stem for path in rule_paths}
    for rule_path in rule_paths:
        problems.extend(rule_file_problems(rule_path))
    try:
        manifest_text = manifest_path.read_text()
    except FileNotFoundError:
        problems.append("rules.md: file is missing")
        return problems
    try:
        entries, entry_problems = parsed_log_entries(manifest_text)
        problems.extend(entry_problems)
        problems.extend(version_log_problems(entries, rule_stems))
        problems.extend(version_date_problems(rules_dir, entries))
    except ValueError as problem:
        problems.append(f"rules.md: {problem}")
    return problems


def main():
    problems = collect_problems(RULES_DIR, MANIFEST_PATH) + task_skill_problems(RULES_DIR, SKILLS_DIR)
    notes = path_verification_notes(RULES_DIR, REPO_ROOT)
    if problems:
        print(f"{len(problems)} problem(s) found:")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print(f"{len(list(RULES_DIR.glob('*.md')))} rule(s) valid and consistent with the rules.md version log.")
    if notes:
        print("Verify these path-specific implementations manually (see the rules-management skill):")
        for note in notes:
            print(f"  - {note}")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
