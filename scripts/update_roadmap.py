#!/usr/bin/env python3
"""Update the README roadmap section based on roadmap/ and done/ directories.

Status rules:
  - Only in roadmap/  → todo         [ ]
  - In both           → in progress  [~]
  - Only in done/     → complete     [x]

Usage:
    python scripts/update_roadmap.py
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP_DIR = REPO_ROOT / "roadmap"
DONE_DIR = REPO_ROOT / "done"
README_PATH = REPO_ROOT / "README.md"

SECTION_ORDER = [
    "current-state",
    "prototype-target",
    "battle-page-polish",
    "pre-battle-deck-flow",
    "tests-and-reliability",
    "multiplayer-account",
    "low-prio",
    "later-actions",
]

SECTION_TITLES = {
    "current-state": "Current state",
    "prototype-target": "Prototype target",
    "battle-page-polish": "Top priority: Battle page polish",
    "pre-battle-deck-flow": "Pre-battle and deck flow",
    "tests-and-reliability": "Tests and reliability",
    "multiplayer-account": "Multiplayer and account model",
    "low-prio": "Low priority",
    "later-actions": "Later actions",
    "deck-page": "Deck page",
    "game-page-metadata": "Game page metadata",
    "customization-card-systems": "Customization and card systems",
    "sound-design": "Sound design",
}


def kebab_to_title(name):
    return name.replace("-", " ").title()


def get_section_title(name):
    return SECTION_TITLES.get(name, kebab_to_title(name))


def read_first_paragraph(path):
    desc_file = path / "description.txt"
    if not desc_file.exists():
        return None
    content = desc_file.read_text().strip()
    paragraphs = content.split("\n\n")
    return paragraphs[0].strip()


def read_full_description(path):
    desc_file = path / "description.txt"
    if not desc_file.exists():
        return None
    return desc_file.read_text().strip()


def get_children(path):
    return sorted(
        item
        for item in path.iterdir()
        if item.is_dir() and not item.name.startswith(".")
    )


def build_tree(base_dir):
    result = {}
    for item in base_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            result[item.name] = build_node(item, base_dir)
    return result


def build_node(path, base_dir):
    rel_path = str(path.relative_to(base_dir))
    children_dirs = get_children(path)
    desc = read_first_paragraph(path)

    if not children_dirs:
        return {"type": "leaf", "name": path.name, "rel_path": rel_path, "description": desc}
    else:
        children = {}
        for child in children_dirs:
            children[child.name] = build_node(child, base_dir)
        return {
            "type": "category",
            "name": path.name,
            "rel_path": rel_path,
            "description": desc,
            "children": children,
        }


def merge_trees(roadmap_tree, done_tree):
    merged = dict(roadmap_tree)
    for name, node in done_tree.items():
        if name not in merged:
            merged[name] = node
        elif merged[name]["type"] == "category" and node["type"] == "category":
            merged[name]["children"] = merge_trees(
                merged[name].get("children", {}), node.get("children", {})
            )
    return merged


def collect_item_paths(tree, prefix=""):
    paths = {}
    for name, node in tree.items():
        rel = f"{prefix}/{name}" if prefix else name
        paths[rel] = node
        if node["type"] == "category":
            paths.update(collect_item_paths(node.get("children", {}), rel))
    return paths


def status(rel_path, roadmap_set, done_set):
    r = rel_path in roadmap_set
    d = rel_path in done_set
    if r and d:
        return "in_progress"
    elif r:
        return "todo"
    elif d:
        return "done"
    return "unknown"


def render_leaf(name, description, st, done_desc=None):
    checkbox = {"todo": "[ ]", "in_progress": "[~]", "done": "[x]"}[st]
    text = description if description else kebab_to_title(name)
    line = f"- {checkbox} {text}"
    if st == "in_progress" and done_desc:
        note = done_desc.split("\n")[0]
        line += f" _({note})_"
    return line


def render_category(name, node, rset, dset, indent=0):
    lines = []
    prefix = "  " * indent
    title = get_section_title(name)
    lines.append(f"{prefix}### {title}")
    lines.append("")

    if node.get("description"):
        lines.append(f"{prefix}{node['description']}")
        lines.append("")

    for child_name, child_node in sorted(node.get("children", {}).items()):
        if child_node["type"] == "leaf":
            st = status(child_node["rel_path"], rset, dset)
            done_desc = DONE_DIR / child_node["rel_path"] / "description.txt"
            done_text = None
            if st == "in_progress" and done_desc.exists():
                done_text = done_desc.read_text().strip()
            lines.append(f"{prefix}{render_leaf(child_name, child_node['description'], st, done_text)}")
        elif child_node["type"] == "category":
            lines.extend(render_category(child_name, child_node, rset, dset, indent + 1))

    lines.append("")
    return lines


def render_roadmap_section(merged, rset, dset):
    lines = ["## Roadmap", ""]

    for section_name in SECTION_ORDER:
        if section_name not in merged:
            continue
        node = merged[section_name]
        if node["type"] == "leaf":
            title = get_section_title(section_name)
            lines.append(f"### {title}")
            lines.append("")
            if node.get("description"):
                lines.append(node["description"])
                lines.append("")
        else:
            lines.extend(render_category(section_name, node, rset, dset))

    for section_name, node in merged.items():
        if section_name in SECTION_ORDER:
            continue
        if node["type"] == "leaf":
            title = get_section_title(section_name)
            lines.append(f"### {title}")
            lines.append("")
            if node.get("description"):
                lines.append(node["description"])
                lines.append("")
        else:
            lines.extend(render_category(section_name, node, rset, dset))

    return "\n".join(lines)


def collect_flat_items(base_dir):
    items = {}
    for root, _dirs, _files in os.walk(base_dir):
        root_path = Path(root)
        rel = str(root_path.relative_to(base_dir))
        if rel == ".":
            continue
        desc_file = root_path / "description.txt"
        if desc_file.exists():
            items[rel] = desc_file.read_text().strip()
    return items


def update_readme(section_text):
    content = README_PATH.read_text()
    lines = content.split("\n")
    start = None
    end = None

    for i, line in enumerate(lines):
        if line.startswith("## Roadmap"):
            start = i
        elif start is not None and line.startswith("## ") and i > start:
            end = i
            break

    if start is None:
        print("ERROR: Could not find roadmap section in README.md", file=sys.stderr)
        sys.exit(1)

    if end is None:
        end = len(lines)

    new_lines = lines[:start]
    new_lines.extend(section_text.split("\n"))
    new_lines.extend(lines[end:])

    README_PATH.write_text("\n".join(new_lines))
    return start, end


def main():
    roadmap_tree = build_tree(ROADMAP_DIR)
    done_tree = build_tree(DONE_DIR) if DONE_DIR.exists() else {}

    rset = set(collect_flat_items(ROADMAP_DIR).keys())
    dset = set(collect_flat_items(DONE_DIR).keys()) if DONE_DIR.exists() else set()

    merged = merge_trees(roadmap_tree, done_tree)
    section = render_roadmap_section(merged, rset, dset)
    s, e = update_readme(section)

    in_progress = len(rset & dset)
    done_only = len(dset - rset)
    todo = len(rset - dset)
    print(f"README.md updated (lines {s+1}-{e})")
    print(f"  {todo} todo | {in_progress} in progress | {done_only} done")


if __name__ == "__main__":
    main()
