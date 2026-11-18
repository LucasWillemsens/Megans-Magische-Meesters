"""Rule file and version log formats shared by the skill's add_rule.py and
check_rules.py, plus repo-root location for the skill's scripts.

The formats are documented in the SKILL.md beside this module.
"""

import re
from datetime import date
from pathlib import Path

RULE_SECTION_NAMES = ("Strictness", "Scope", "Description", "Context")
VERSION_LOG_HEADING = "## Rules version log"
KEBAB_TITLE_SOURCE = r"[a-z0-9]+(?:-[a-z0-9]+)*"
KEBAB_TITLE_PATTERN = re.compile(KEBAB_TITLE_SOURCE)
SCOPE_PATTERN = re.compile(r"repo wide|path specific: \S.*|task specific: \S.*")
STRICTNESS_PATTERN = re.compile(r"[0-9]+")
VERSION_ENTRY_PATTERN = re.compile(
    rf"- (?P<entry_date>\d{{4}}-\d{{2}}-\d{{2}}) — (?P<title>{KEBAB_TITLE_SOURCE})"
    rf" v(?P<version>[0-9]+)(?: — (?P<explanation>.+))?"
)


def find_repo_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("the rules-management scripts must run inside the repository")


def title_problem(title):
    if not KEBAB_TITLE_PATTERN.fullmatch(title):
        return "title must be kebab-case: lowercase words separated by single hyphens"
    return None


def strictness_problem(strictness):
    text = strictness.strip()
    if not STRICTNESS_PATTERN.fullmatch(text) or int(text) < 1:
        return "strictness must be a whole number 1 or higher"
    return None


def scope_problem(scope):
    if not SCOPE_PATTERN.fullmatch(scope.strip()):
        return "scope must be 'repo wide', 'path specific: {PATH}', or 'task specific: {TASK}'"
    return None


def context_items_problem(context_items):
    if not context_items:
        return "context needs at least one goal"
    for item in context_items:
        if not item.strip():
            return "context items must not be empty"
        if "\n" in item:
            return "context items must be single lines"
    return None


def render_rule_file(strictness, scope, description, context_items):
    context = "\n".join(f"- {item}" for item in context_items)
    return (
        f"## Strictness\n{strictness}\n\n"
        f"## Scope\n{scope}\n\n"
        f"## Description\n{description}\n\n"
        f"## Context\n{context}\n"
    )


def parse_rule_file(text):
    section_names = []
    section_lines = {}
    current_section = None
    for line in text.splitlines():
        if line.startswith("## "):
            current_section = line[3:].strip()
            section_names.append(current_section)
            section_lines[current_section] = []
        elif current_section is not None:
            section_lines[current_section].append(line)
    if section_names != list(RULE_SECTION_NAMES):
        expected = ", ".join(RULE_SECTION_NAMES)
        found = ", ".join(section_names) or "none"
        raise ValueError(f"sections must be {expected} in that order, found {found}")
    strictness = "\n".join(section_lines["Strictness"]).strip()
    problem = strictness_problem(strictness)
    if problem:
        raise ValueError(problem)
    scope = "\n".join(section_lines["Scope"]).strip()
    problem = scope_problem(scope)
    if problem:
        raise ValueError(problem)
    description = "\n".join(section_lines["Description"]).strip()
    if not description:
        raise ValueError("description must not be empty")
    context_items = []
    for line in section_lines["Context"]:
        if not line.strip():
            continue
        if not line.startswith("- "):
            raise ValueError("context lines must be '- ' list items")
        context_items.append(line[2:].strip())
    problem = context_items_problem(context_items)
    if problem:
        raise ValueError(problem)
    return {
        "strictness": int(strictness),
        "scope": scope,
        "description": description,
        "context_items": context_items,
    }


def render_version_entry(entry_date, title, version, explanation=None):
    entry = f"- {entry_date.isoformat()} — {title} v{version}"
    if explanation:
        entry += f" — {explanation}"
    return entry


def parse_version_entry(entry_line):
    match = VERSION_ENTRY_PATTERN.fullmatch(entry_line.strip())
    if not match:
        raise ValueError(
            "entry must look like '- YYYY-MM-DD — <rule-title> vN', "
            "optionally followed by ' — <very short explanation>'"
        )
    try:
        entry_date = date.fromisoformat(match.group("entry_date"))
    except ValueError:
        raise ValueError(f"{match.group('entry_date')} is not a real date") from None
    return {
        "date": entry_date,
        "title": match.group("title"),
        "version": int(match.group("version")),
        "explanation": match.group("explanation"),
    }


def find_version_log_heading(lines):
    for index, line in enumerate(lines):
        if line.strip() == VERSION_LOG_HEADING:
            return index
    raise ValueError(f"rules.md is missing the '{VERSION_LOG_HEADING}' section")


def read_version_log(manifest_text):
    lines = manifest_text.splitlines()
    entries = []
    for line in lines[find_version_log_heading(lines) + 1:]:
        if line.startswith("#"):
            break
        if line.strip():
            entries.append(line)
    return entries


def append_version_log_entry(manifest_text, entry_line):
    lines = manifest_text.splitlines()
    heading_index = find_version_log_heading(lines)
    section_end = heading_index + 1
    while section_end < len(lines) and not lines[section_end].startswith("#"):
        section_end += 1
    insert_index = section_end
    while insert_index > heading_index + 1 and not lines[insert_index - 1].strip():
        insert_index -= 1
    if insert_index == heading_index + 1 and insert_index < len(lines) and not lines[insert_index].strip():
        insert_index += 1
    lines.insert(insert_index, entry_line)
    return "\n".join(lines) + "\n"
