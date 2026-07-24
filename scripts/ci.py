#!/usr/bin/env python3
"""CI script that automates the devops workflow:
  1. Check git status and current changes
  2. Analyze recent source code changes against roadmap descriptions
  3. Update done/ directory for newly completed items
  4. Run tests
  5. Run update readme script
  6. Commit, push to feature branch, and open a PR

Usage:
    python3 scripts/ci.py
    python3 scripts/ci.py --branch my-feature
    python3 scripts/ci.py --dry-run
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP_DIR = REPO_ROOT / "roadmap"
DONE_DIR = REPO_ROOT / "done"
README_PATH = REPO_ROOT / "README.md"
UPDATE_SCRIPT = REPO_ROOT / "scripts" / "update_roadmap.py"

DJANGO_DIRS = [REPO_ROOT / "MMM", REPO_ROOT / "mysite"]
STATIC_DIR = REPO_ROOT / "var" / "www" / "static"


def run(cmd, check=True, cwd=None):
    """Run a shell command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd or REPO_ROOT
    )
    if check and result.returncode != 0:
        print(f"  Command failed: {cmd}")
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()}")
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def git_status():
    """Run git status and return structured info."""
    print("=" * 60)
    print("STEP 1: Git Status")
    print("=" * 60)

    rc, branch, _ = run("git branch --show-current")
    print(f"  Branch: {branch}")

    rc, log, _ = run("git log --oneline -10")
    print(f"\n  Recent commits:\n{log}")

    rc, status_out, _ = run("git status --short")
    if status_out:
        print(f"\n  Uncommitted changes:\n{status_out}")
    else:
        print("\n  Working tree clean.")

    rc, diff_stat, _ = run("git diff --stat")
    if diff_stat:
        print(f"\n  Diff stat:\n{diff_stat}")

    return branch


def get_staged_diff():
    """Get the full diff of staged changes in Django/static files."""
    rc, diff, _ = run("git diff --cached", check=False)
    if not diff:
        # Fall back to unstaged diff + untracked files
        rc, diff, _ = run("git diff HEAD", check=False)
    return diff


def get_changed_django_files():
    """Get list of Django-related files that have uncommitted changes."""
    rc, output, _ = run("git diff --name-only HEAD", check=False)
    rc2, output2, _ = run("git diff --cached --name-only", check=False)
    rc3, output3, _ = run("git ls-files --others --exclude-standard", check=False)

    all_changed = set()
    for out in [output, output2, output3]:
        for line in out.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Match Django-relevant files
            if any(line.endswith(ext) for ext in [".py", ".jinja2", ".js", ".css"]):
                all_changed.add(line)
    return sorted(all_changed)


def read_changed_files_content(changed_files):
    """Read the current content of changed files for matching."""
    parts = []
    for rel_path in changed_files:
        full = REPO_ROOT / rel_path
        if full.exists():
            try:
                content = full.read_text(errors="replace")
                parts.append(f"# FILE: {rel_path}\n{content}")
            except Exception:
                pass
    return "\n".join(parts)


def collect_descriptions(base_dir):
    """Recursively collect all description.txt contents from a directory."""
    descriptions = {}
    for desc_file in base_dir.rglob("description.txt"):
        rel_path = str(desc_file.relative_to(base_dir))
        content = desc_file.read_text().strip()
        if content:
            descriptions[rel_path] = content
    return descriptions


def read_full_description(base_dir, rel_path):
    """Read the full description.txt for a roadmap item."""
    desc_file = base_dir / rel_path
    if desc_file.is_file() and desc_file.name == "description.txt":
        return desc_file.read_text().strip()
    # Try as directory
    desc_file = base_dir / rel_path / "description.txt"
    if desc_file.exists():
        return desc_file.read_text().strip()
    return None


def extract_keywords(text):
    """Extract meaningful keywords from description text, excluding generic words."""
    stopwords = {
        "the", "and", "for", "that", "this", "with", "from", "are", "was",
        "were", "been", "have", "has", "had", "but", "not", "you", "all",
        "can", "her", "his", "its", "our", "out", "who", "get", "how",
        "may", "new", "now", "old", "see", "way", "did", "let", "say",
        "she", "too", "use", "make", "like", "just", "over", "such",
        "take", "than", "them", "then", "what", "when", "your", "will",
        "each", "more", "also", "back", "into", "only", "very", "some",
        "most", "well", "here", "help", "they", "being", "does", "done",
        "doing", "even", "after", "before", "could", "would", "should",
        "about", "other", "which", "there", "their", "these", "those",
        "where", "while", "both", "much", "many", "first", "last", "long",
        "adds", "added", "support", "dedicated", "cleanly", "smoother",
        "natural", "meaningful", "earned", "satisfying", "transparent",
        "complete", "distinct", "easier", "intuitive", "efficient",
        "accurately", "instantly", "consistency", "improve",
    }
    words = re.findall(r"[a-z]{4,}", text.lower())
    return [w for w in words if w not in stopwords]


def get_description_category(rel_path):
    """Extract the top-level category from a roadmap path."""
    parts = rel_path.split("/")
    return parts[0] if parts else ""


def match_changed_code_to_descriptions(diff_text, changed_files, roadmap_descs):
    """Match recent code changes against roadmap descriptions.

    Strategy:
    1. Extract identifiers (function names, class names, template names, CSS classes)
        from the changed files and diff
    2. For each roadmap description, check if its key concepts map to those identifiers
    3. Score by relevance

    Returns list of matched items sorted by score.
    """
    # Extract identifiers from diff (added/changed lines only)
    added_lines = []
    for line in diff_text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])

    added_text = "\n".join(added_lines)

    # Extract meaningful identifiers from the code changes
    code_identifiers = set()

    # Python identifiers: class names, function names, variable names
    for match in re.finditer(r"\b(?:class|def)\s+(\w+)", added_text):
        code_identifiers.add(match.group(1).lower())

    # Django model names
    for match in re.finditer(r"class\s+(\w+)\s*\(", added_text):
        code_identifiers.add(match.group(1).lower())

    # Django view function names
    for match in re.finditer(r"def\s+(\w+)\s*\(", added_text):
        code_identifiers.add(match.group(1).lower())

    # URL pattern names
    for match in re.finditer(r'name=["\'](\w+)["\']', added_text):
        code_identifiers.add(match.group(1).lower())

    # Template names from render calls
    for match in re.finditer(r'["\']([\w/]+\.jinja2)["\']', added_text):
        tpl_name = match.group(1).split("/")[-1].replace(".jinja2", "")
        code_identifiers.add(tpl_name.lower())

    # CSS class names and IDs
    for match in re.finditer(r'[.#]([a-zA-Z][\w-]*)', added_text):
        code_identifiers.add(match.group(1).lower())

    # JavaScript identifiers
    for match in re.finditer(r"\b(?:function|const|let|var)\s+(\w+)", added_text):
        code_identifiers.add(match.group(1).lower())

    # Also extract from file names of changed files
    for f in changed_files:
        basename = Path(f).stem.lower()
        code_identifiers.add(basename)
        # Extract camelCase/snake_case parts
        for part in re.split(r"[_\-.]", basename):
            if len(part) >= 3:
                code_identifiers.add(part.lower())

    # Skip analysis if only non-Django files changed (e.g. only scripts/ci.py)
    django_extensions = {".py", ".jinja2", ".js", ".css"}
    django_file_prefixes = ["MMM/", "mysite/", "var/www/static/"]
    has_django_changes = any(
        any(f.startswith(p) for p in django_file_prefixes)
        or Path(f).suffix in django_extensions
        for f in changed_files
        if f != "scripts/ci.py"
    )
    if not has_django_changes and not added_text.strip():
        return [], set()

    # Filter out very generic identifiers
    generic = {
        "self", "cls", "request", "response", "context", "args", "kwargs",
        "init", "str", "int", "float", "bool", "list", "dict", "set",
        "none", "true", "false", "return", "import", "from", "class",
        "def", "if", "else", "for", "while", "try", "except", "raise",
        "with", "as", "in", "not", "and", "or", "is", "print", "super",
        "meta", "app", "name", "verbose", "blank", "null", "default",
        "related", "query", "path", "url", "view", "template", "static",
        "models", "admin", "objects", "all", "filter", "get", "create",
        "save", "delete", "exists", "count", "first", "last", "order",
        "values", "fields", "form", "model", "clean", "is_valid",
        "render", "redirect", "http", "json", "post", "get", "put",
        "delete", "patch", "status", "code", "data", "error", "success",
        "message", "result", "value", "type", "key", "item", "name",
        "title", "description", "source", "icon", "text", "label",
        "index", "base", "test", "cases", "battle", "flow",
    }
    code_identifiers -= generic

    # Now match descriptions against these identifiers
    results = []
    for rel_path, content in roadmap_descs.items():
        # Skip category descriptions (contain "Includes:" line)
        if "Includes:" in content:
            continue

        description = content.split("\n")[0].strip()
        category = get_description_category(rel_path)

        # Extract keywords from the description
        desc_keywords = extract_keywords(description)

        # Check overlap between description keywords and code identifiers
        matched_keywords = []
        for kw in desc_keywords:
            # Direct match
            if kw in code_identifiers:
                matched_keywords.append(kw)
                continue
            # Partial match (keyword is part of an identifier or vice versa)
            for ident in code_identifiers:
                if kw in ident or ident in kw:
                    matched_keywords.append(kw)
                    break

        if matched_keywords:
            # Score: number of matched keywords weighted by description length
            score = len(matched_keywords) / max(len(desc_keywords), 1)
            results.append({
                "roadmap_path": rel_path,
                "description": description,
                "category": category,
                "matched_keywords": matched_keywords,
                "total_keywords": len(desc_keywords),
                "score": round(score, 3),
            })

    # Sort by score descending
    results.sort(key=lambda r: r["score"], reverse=True)
    return results, code_identifiers


def ensure_done_structure(rel_path, dry_run=False):
    """Ensure the done/ directory mirrors the roadmap structure for a given path.

    If the done/ directory doesn't include the intermediate folders, add them
    before writing the description.
    """
    done_target = DONE_DIR / rel_path
    parent = done_target.parent

    if not parent.exists():
        print(f"  Creating: {parent.relative_to(REPO_ROOT)}/")
        if not dry_run:
            parent.mkdir(parents=True, exist_ok=True)

    return done_target


def analyze_and_update_done(matched_items, done_descs, dry_run=False):
    """For matched roadmap items, cross-check against done/, then write descriptions.

    Double-checks that items aren't already in done/ before writing.
    Ensures folder structure exists before writing.
    """
    print("\n" + "=" * 60)
    print("STEP 3: Updating Done Directory")
    print("=" * 60)

    if not matched_items:
        print("  No new items to add to done/.")
        return 0

    # Build set of existing done paths (normalized)
    done_paths = set()
    for rel_path in done_descs:
        # Normalize: strip "description.txt" suffix if present
        clean = rel_path.replace("/description.txt", "").replace("description.txt", "")
        done_paths.add(clean)

    # Also collect done directory names for quick lookup
    done_dir_names = set()
    if DONE_DIR.exists():
        for item in DONE_DIR.rglob("*"):
            if item.is_dir() and item.name != ".":
                done_dir_names.add(item.name)

    updated = 0
    skipped = 0
    for item in matched_items:
        rel_path = item["roadmap_path"]
        # Clean the path: remove trailing "description.txt" if present
        clean_path = rel_path.replace("/description.txt", "").replace("description.txt", "")
        leaf_name = clean_path.split("/")[-1]

        # Check if already in done
        if clean_path in done_paths or leaf_name in done_dir_names:
            print(f"  SKIP (already done): {leaf_name}")
            skipped += 1
            continue

        # Read the roadmap description
        description = read_full_description(ROADMAP_DIR, rel_path)
        if not description:
            print(f"  WARN: No description found for {rel_path}")
            continue

        # Ensure directory structure exists in done/
        done_target = ensure_done_structure(clean_path, dry_run)

        # Write the description
        desc_file = done_target / "description.txt" if not done_target.suffix else done_target
        if done_target.is_dir():
            desc_file = done_target / "description.txt"

        print(f"  WRITE: {desc_file.relative_to(REPO_ROOT)}")
        if not dry_run:
            desc_file.write_text(description + "\n")
        updated += 1

    print(f"\n  Added: {updated} | Skipped (already done): {skipped}")
    return updated


def run_tests():
    """Run Django tests."""
    print("\n" + "=" * 60)
    print("STEP 4: Running Tests")
    print("=" * 60)

    rc, out, err = run("python3 manage.py test", check=False)
    if out:
        print(f"  {out}")
    if err:
        print(f"  {err}")

    if rc != 0:
        print(f"\n  FAIL: Tests failed with exit code {rc}")
        return False

    print("\n  PASS: All tests passed.")
    return True


def run_update_readme():
    """Run the update_roadmap.py script to refresh the README."""
    print("\n" + "=" * 60)
    print("STEP 5: Updating README Roadmap")
    print("=" * 60)

    rc, out, err = run(f"python3 {UPDATE_SCRIPT}", check=False)
    if out:
        print(f"  {out}")
    if err:
        print(f"  {err}")

    if rc != 0:
        print(f"\n  WARN: update_roadmap.py exited with code {rc}")
        return False

    return True


def commit_and_push(branch, dry_run=False):
    """Commit all changes, push to feature branch, and open a PR."""
    print("\n" + "=" * 60)
    print("STEP 6: Commit, Push, and Open PR")
    print("=" * 60)

    rc, status_out, _ = run("git status --short")
    if not status_out:
        print("  Nothing to commit.")
        return

    print(f"  Changes to commit:\n{status_out}")

    rc, current_branch, _ = run("git branch --show-current")
    if current_branch != branch:
        print(f"\n  Creating and switching to branch: {branch}")
        if not dry_run:
            run(f"git checkout -b {branch}", check=True)

    print("  Staging all changes...")
    if not dry_run:
        run("git add -A", check=True)

    commit_msg = "ci: auto-sync roadmap and done directory from source analysis"
    print(f"  Commit: {commit_msg}")

    if not dry_run:
        run(f'git commit -m "{commit_msg}"', check=True)
        print("  Committed.")

        print(f"  Pushing to origin/{branch}...")
        rc, _, err = run(f"git push -u origin {branch}", check=False)
        if rc != 0:
            print(f"  Push failed: {err}")
            print("  Try pushing manually.")
            return
        print("  Pushed.")

        print("  Opening PR...")
        pr_body = (
            "Automated CI update:\\n"
            "- Analyzed recent Django source changes against roadmap descriptions\\n"
            "- Updated done/ directory for matched items\\n"
            "- Ran tests and refreshed README roadmap section"
        )
        rc, pr_out, pr_err = run(
            f'gh pr create --title "ci: roadmap sync" --body "{pr_body}" --base main',
            check=False,
        )
        if rc != 0:
            rc2, existing, _ = run(
                f"gh pr list --head {branch} --json url -q '.[0].url'",
                check=False,
            )
            if existing:
                print(f"  PR already exists: {existing}")
            else:
                print(f"  Could not create PR: {pr_err}")
                print("  Create the PR manually.")
        else:
            print(f"  PR created: {pr_out}")
    else:
        print("  (dry-run: skipping git operations)")


def main():
    parser = argparse.ArgumentParser(description="CI script for MMM project")
    parser.add_argument(
        "--branch",
        default="ci/roadmap-sync",
        help="Feature branch name (default: ci/roadmap-sync)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()

    os.chdir(REPO_ROOT)

    print("Megans Magische Meesters - CI Pipeline")
    print("=" * 60)

    # Step 1: Git status
    current_branch = git_status()

    # Step 2: Get changed files and diff
    print("\n" + "=" * 60)
    print("STEP 2: Source Code Change Analysis")
    print("=" * 60)

    changed_files = get_changed_django_files()
    if changed_files:
        print(f"\n  Changed Django/static files ({len(changed_files)}):")
        for f in changed_files:
            print(f"    - {f}")
    else:
        print("\n  No uncommitted Django/static file changes detected.")
        print("  (Will still check for untracked files)")

        # Also check untracked files
        rc, untracked, _ = run("git ls-files --others --exclude-standard", check=False)
        for line in untracked.split("\n"):
            line = line.strip()
            if line and any(line.endswith(ext) for ext in [".py", ".jinja2", ".js", ".css"]):
                changed_files.append(line)
        if changed_files:
            print(f"\n  Found untracked Django/static files ({len(changed_files)}):")
            for f in changed_files:
                print(f"    - {f}")

    diff_text = get_staged_diff()

    # Read roadmap descriptions
    roadmap_descs = collect_descriptions(ROADMAP_DIR)
    done_descs = collect_descriptions(DONE_DIR) if DONE_DIR.exists() else {}

    if changed_files or diff_text:
        matched, identifiers = match_changed_code_to_descriptions(
            diff_text, changed_files, roadmap_descs
        )

        # Filter out items already fully in done
        done_set = set()
        for rp in done_descs:
            clean = rp.replace("/description.txt", "").replace("description.txt", "")
            done_set.add(clean)
            done_set.add(clean.split("/")[-1])

        new_matches = [
            m for m in matched
            if m["roadmap_path"].replace("/description.txt", "") not in done_set
            and m["roadmap_path"].split("/")[0] not in done_set
        ]

        # Filter to meaningful matches (score >= 0.15)
        significant_matches = [m for m in new_matches if m["score"] >= 0.15]
        low_matches = [m for m in new_matches if m["score"] < 0.15]

        if significant_matches:
            print(f"\n  Matched {len(significant_matches)} roadmap items to code changes:\n")
            for m in significant_matches:
                conf = "HIGH" if m["score"] >= 0.4 else "MED" if m["score"] >= 0.25 else "LOW"
                print(f"  [{conf:4s}] {m['roadmap_path']}")
                print(f"    Score: {m['score']} | Keywords: {', '.join(m['matched_keywords'][:6])}")
                print(f"    Desc:  {m['description'][:75]}...")
                print()
            new_matches = significant_matches
        else:
            print("\n  No significant roadmap items matched the code changes.")
            if low_matches:
                print(f"  ({len(low_matches)} low-confidence matches filtered out)")
            new_matches = []

        if low_matches:
            print(f"\n  Low-confidence matches (not auto-added to done/):")
            for m in low_matches[:5]:
                print(f"    - {m['roadmap_path']} (score: {m['score']})")

        if identifiers:
            print(f"  Extracted code identifiers ({len(identifiers)}):")
            ident_sample = sorted(identifiers)[:20]
            print(f"    {', '.join(ident_sample)}")
            if len(identifiers) > 20:
                print(f"    ... and {len(identifiers) - 20} more")
    else:
        new_matches = []
        print("\n  No changes detected to analyze.")

    # Step 3: Update done directory
    analyze_and_update_done(new_matches, done_descs, dry_run=args.dry_run)

    # Step 4: Run tests
    tests_passed = run_tests()

    if not tests_passed:
        print("\n" + "=" * 60)
        print("ABORT: Tests failed. Fix issues and re-run.")
        print("=" * 60)
        sys.exit(1)

    # Step 5: Update README roadmap
    run_update_readme()

    # Step 6: Commit and push
    commit_and_push(args.branch, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("CI PIPELINE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
