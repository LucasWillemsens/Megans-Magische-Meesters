#!/usr/bin/env python
"""CI script that automates the devops workflow:
  1. Pull latest changes from origin
  2. Check git status and current changes
  3. Analyze recent source code changes against roadmap descriptions
  4. Update done/ directory for newly completed items
  5. Run tests
  6. Run update readme script
  7. Commit, push to a unique goal-named feature branch, and open a PR

Usage:
    python scripts/ci.py
    python scripts/ci.py --branch my-feature
    python scripts/ci.py --dry-run
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP_DIR = REPO_ROOT / "roadmap"
DONE_DIR = REPO_ROOT / "done"
README_PATH = REPO_ROOT / "README.md"
UPDATE_SCRIPT = REPO_ROOT / "scripts" / "update_roadmap.py"

DJANGO_DIRS = [REPO_ROOT / "MMM", REPO_ROOT / "mysite"]
STATIC_DIR = REPO_ROOT / "var" / "www" / "static"

# Minimum matcher score to auto-add a roadmap item to done/. Set at the HIGH
# confidence boundary: observed false positives (filename-stem and partial
# keyword matches) topped out at 0.333. Matches in the LOW_MATCH_FLOOR..
# MATCH_THRESHOLD band are only reported, and can be force-added with --match.
MATCH_THRESHOLD = 0.4
LOW_MATCH_FLOOR = 0.15

# ---------------------------------------------------------------------------
# Self-improvement: path to recorded corrections and learned blocklists
# ---------------------------------------------------------------------------
CI_FIXES_DIR = REPO_ROOT / "ci_fixes"
FALSE_POSITIVE_BLOCKLIST = CI_FIXES_DIR / "false_positive_blocklist.json"
# Dynamic threshold adjustment: track how many corrections were recorded
# and tighten the threshold slightly with each correction.
FIX_PENALTY_PER_CORRECTION = 0.02
MAX_THRESHOLD_PENALTY = 0.10


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


def pull_latest(dry_run=False):
    """Fetch origin and fast-forward the current branch when the tree is clean.

    The script usually runs with uncommitted implementation changes, where a
    pull would fail; in that case we still fetch so the new feature branch can
    be based on the fresh origin/main (see commit_and_push).
    """
    print("=" * 60)
    print("STEP 1: Pull Latest Changes")
    print("=" * 60)

    if dry_run:
        print("  (dry-run: would run 'git fetch origin' and fast-forward pull)")
        return

    rc, _, err = run("git fetch origin", check=False)
    if rc != 0:
        print(f"  WARN: git fetch failed ({err}); continuing with local state.")
        return
    print("  Fetched origin.")

    rc, branch, _ = run("git branch --show-current")
    if not branch:
        print("  Detached HEAD; skipping pull.")
        return

    rc, dirty, _ = run("git status --porcelain", check=False)
    if dirty:
        print(f"  Uncommitted changes present; skipping pull on '{branch}'.")
        print("  (The feature branch will be based on the fetched origin/main.)")
        return

    rc, out, err = run(f"git pull --ff-only origin {branch}", check=False)
    if rc != 0:
        print(f"  WARN: could not fast-forward '{branch}': {err}")
    else:
        print(f"  {out or 'Already up to date.'}")


def git_status():
    """Run git status and return structured info."""
    print("=" * 60)
    print("STEP 2: Git Status")
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


# ---------------------------------------------------------------------------
# Self-improvement helpers
# ---------------------------------------------------------------------------

def load_false_positive_blocklist():
    """Load the persistent false-positive keyword blocklist.

    Returns a dict with:
      - 'keywords': set of keyword strings that have caused false matches
      - 'paths':    set of roadmap path prefixes to suppress
      - 'pairs':    set of (keyword, path_prefix) tuples for context-sensitive blocks
    """
    if FALSE_POSITIVE_BLOCKLIST.exists():
        try:
            data = json.loads(FALSE_POSITIVE_BLOCKLIST.read_text())
            return {
                "keywords": set(data.get("keywords", [])),
                "paths": set(data.get("paths", [])),
                "pairs": set(tuple(p) for p in data.get("pairs", [])),
            }
        except (json.JSONDecodeError, KeyError):
            pass
    return {"keywords": set(), "paths": set(), "pairs": set()}


def save_false_positive_blocklist(blocklist):
    """Persist the false-positive blocklist to disk."""
    CI_FIXES_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "keywords": sorted(blocklist["keywords"]),
        "paths": sorted(blocklist["paths"]),
        "pairs": sorted(list(blocklist["pairs"])),
    }
    FALSE_POSITIVE_BLOCKLIST.write_text(json.dumps(data, indent=2) + "\n")


def record_correction(roadmap_path, false_positive_keywords, description_excerpt, notes=""):
    """Record a manual correction so the CI can learn from it.

    Called by the devops agent (or user) after they manually remove a falsely
    matched done/ entry. The CI will use this to adjust its matching in future
    runs.
    """
    CI_FIXES_DIR.mkdir(parents=True, exist_ok=True)

    # Generate a unique filename from the path and timestamp
    slug = re.sub(r"[^a-z0-9]+", "-", roadmap_path.lower()).strip("-")[:60]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{slug}-{stamp}.json"
    fix_path = CI_FIXES_DIR / filename

    record = {
        "timestamp": stamp,
        "roadmap_path": roadmap_path,
        "false_positive_keywords": sorted(set(false_positive_keywords)),
        "description_excerpt": description_excerpt,
        "notes": notes,
    }
    fix_path.write_text(json.dumps(record, indent=2) + "\n")
    print(f"  Recorded correction: {fix_path.relative_to(REPO_ROOT)}")

    # Update the global blocklist with this correction
    blocklist = load_false_positive_blocklist()
    for kw in false_positive_keywords:
        blocklist["keywords"].add(kw.lower())
    # Add a path-specific block to prevent future matches on this exact path
    clean_path = roadmap_path.replace("/description.txt", "").strip("/")
    blocklist["paths"].add(clean_path)
    # Add keyword+path pairs for context-sensitive blocking
    for kw in false_positive_keywords:
        blocklist["pairs"].add((kw.lower(), clean_path))
    save_false_positive_blocklist(blocklist)

    # Also append to a running log
    log_path = CI_FIXES_DIR / "corrections_log.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")

    print(f"  Updated false-positive blocklist ({len(blocklist['keywords'])} keywords, "
          f"{len(blocklist['paths'])} paths).")
    return fix_path


def list_corrections():
    """List all recorded corrections from ci_fixes/."""
    CI_FIXES_DIR.mkdir(parents=True, exist_ok=True)
    fixes = []
    for f in sorted(CI_FIXES_DIR.glob("*.json")):
        if f.name == "false_positive_blocklist.json":
            continue
        try:
            data = json.loads(f.read_text())
            fixes.append((f, data))
        except json.JSONDecodeError:
            continue
    return fixes


def compute_dynamic_threshold():
    """Compute an adjusted MATCH_THRESHOLD based on past correction count.

    Each recorded false positive slightly raises the bar, forcing the matcher
    to be more confident before auto-adding a done/ entry.
    """
    corrections = list_corrections()
    num_fixes = len(corrections)
    penalty = min(num_fixes * FIX_PENALTY_PER_CORRECTION, MAX_THRESHOLD_PENALTY)
    adjusted = round(MATCH_THRESHOLD + penalty, 3)
    return adjusted, num_fixes


def suppress_false_positive_matches(results):
    """Apply the learned blocklist to filter out previously-false matches.

    Uses three mechanisms:
    1. Keyword blocklist — if a matched keyword is known to cause false
       positives, reduce its contribution weight.
    2. Path blocklist — never auto-match a roadmap path that was previously
       falsely added to done/.
    3. Pair blocklist — if (keyword, path_prefix) matches a known false pair,
       suppress that specific match.
    """
    blocklist = load_false_positive_blocklist()
    if not any([blocklist["keywords"], blocklist["paths"], blocklist["pairs"]]):
        return results  # No learned corrections yet

    blocked_kws = blocklist["keywords"]
    blocked_paths = blocklist["paths"]
    blocked_pairs = blocklist["pairs"]

    filtered = []
    suppressed = []
    for m in results:
        rel_path = m["roadmap_path"].replace("/description.txt", "").strip("/")

        # 1. Direct path block
        if rel_path in blocked_paths:
            suppressed.append((rel_path, "blocked path"))
            continue

        # 2. Path prefix block (any parent dir that was a false positive)
        path_prefix_blocked = False
        for blocked in blocked_paths:
            if rel_path.startswith(blocked + "/") or rel_path == blocked:
                suppressed.append((rel_path, f"path prefix '{blocked}'"))
                path_prefix_blocked = True
                break
        if path_prefix_blocked:
            continue

        # 3. Keyword de-boosting: reduce score for matches that rely on
        #    blocklisted keywords
        matched_kws = [kw.lower() for kw in m.get("matched_keywords", [])]
        blocked_match_kws = [kw for kw in matched_kws if kw in blocked_kws]

        if blocked_match_kws:
            # Check if any (keyword, path) pair is blocked
            pair_blocked = any(
                (kw, rel_path) in blocked_pairs for kw in blocked_match_kws
            )
            kw_blocked = any(kw in blocked_kws for kw in blocked_match_kws)

            if pair_blocked:
                suppressed.append(
                    (rel_path, f"blocked pair {blocked_match_kws[0]}")
                )
                continue

            if kw_blocked:
                # De-boost: reduce score proportionally to how many matched
                # keywords are known false positives
                total_matched = len(matched_kws) if matched_kws else 1
                penalty_ratio = len(blocked_match_kws) / total_matched
                m["score"] = round(m["score"] * (1.0 - penalty_ratio * 0.5), 3)
                m["_adjusted_by_blocklist"] = True
                m["_suppressed_keywords"] = blocked_match_kws

        filtered.append(m)

    if suppressed:
        print(f"\n  [self-improvement] Suppressed {len(suppressed)} false-positive "
              f"match(es) using learned blocklist:")
        for path, reason in suppressed[:10]:
            print(f"    - {path} ({reason})")
        if len(suppressed) > 10:
            print(f"    ... and {len(suppressed) - 10} more")

    return filtered


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

    # Skip analysis if no Django app/static files changed (e.g. only
    # scripts/ci.py or other tooling changed) — matching against tooling
    # diffs produces false-positive roadmap matches.
    django_file_prefixes = ("MMM/", "mysite/", "var/www/static/")
    if not any(f.startswith(django_file_prefixes) for f in changed_files):
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

    if not done_target.exists() and not done_target.suffix:
        print(f"  Creating: {done_target.relative_to(REPO_ROOT)}/")
        if not dry_run:
            done_target.mkdir(parents=True, exist_ok=True)

    return done_target


def analyze_and_update_done(matched_items, done_descs, dry_run=False):
    """For matched roadmap items, cross-check against done/, then write descriptions.

    Double-checks that items aren't already in done/ before writing.
    Ensures folder structure exists before writing.
    """
    print("\n" + "=" * 60)
    print("STEP 4: Updating Done Directory")
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
    print("STEP 5: Running Tests")
    print("=" * 60)

    rc, out, err = run(f'"{sys.executable}" manage.py test', check=False)
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
    print("STEP 6: Updating README Roadmap")
    print("=" * 60)

    rc, out, err = run(f'"{sys.executable}" {UPDATE_SCRIPT}', check=False)
    if out:
        print(f"  {out}")
    if err:
        print(f"  {err}")

    if rc != 0:
        print(f"\n  WARN: update_roadmap.py exited with code {rc}")
        return False

    return True


def derive_goal_branch(matches, fallback="roadmap-sync"):
    """Build a branch name from the top matched roadmap goal.

    Format: ci/<goal-slug>-<timestamp>. The timestamp keeps re-runs of the
    same goal from colliding with earlier branches/PRs.
    Returns (branch_name, goal_slug).
    """
    goal = fallback
    if matches:
        top = matches[0]["roadmap_path"].replace("/description.txt", "")
        parts = [p for p in top.split("/") if p]
        if parts:
            goal = parts[-1]
    slug = re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-")[:48] or fallback
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"ci/{slug}-{stamp}", slug


def ensure_unique_branch(branch):
    """Append a counter if the branch already exists locally or on origin."""
    candidate = branch
    n = 2
    while True:
        _, local, _ = run(f"git branch --list {candidate}", check=False)
        _, remote, _ = run(f"git ls-remote --heads origin {candidate}", check=False)
        if not local and not remote:
            return candidate
        candidate = f"{branch}-{n}"
        n += 1


def commit_and_push(branch, goal, dry_run=False):
    """Commit all changes, push to feature branch, and open a PR."""
    print("\n" + "=" * 60)
    print("STEP 7: Commit, Push, and Open PR")
    print("=" * 60)

    rc, status_out, _ = run("git status --short")
    if not status_out:
        print("  Nothing to commit.")
        return

    print(f"  Changes to commit:\n{status_out}")

    rc, current_branch, _ = run("git branch --show-current")
    if current_branch != branch:
        # Base the new branch on the fetched origin/main when possible so the
        # PR includes the latest changes; fall back to the current HEAD.
        start_point = "origin/main" if current_branch == "main" else ""
        label = f" (from {start_point})" if start_point else ""
        print(f"\n  Creating and switching to branch: {branch}{label}")
        if not dry_run:
            rc, _, err = run(f"git checkout -b {branch} {start_point}".strip(), check=False)
            if rc != 0:
                print(f"  WARN: checkout{label} failed ({err}); branching from current HEAD.")
                run(f"git checkout -b {branch}", check=True)

    print("  Staging all changes...")
    if not dry_run:
        run("git add -A", check=True)

    commit_msg = f"{branch} + auto ci changes"
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
            f"{commit_msg}"
        )
        rc, pr_out, pr_err = run(
            f'gh pr create --title "ci: {goal}" --body "{pr_body}" --base main --assignee LucasWillemsens',
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
    parser = argparse.ArgumentParser(
        description="CI script for MMM project — with self-improvement"
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Feature branch name (default: auto-derived from the top matched "
        "roadmap goal, e.g. ci/enemy-action-cookies-20260101-120000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--match",
        action="append",
        default=[],
        metavar="ROADMAP_PATH",
        help="Explicitly mark a roadmap item as done (repeatable, e.g. "
        "--match battle-page-polish/enemy-turn-indicators/enemy-action-cookies). "
        "When given, auto-matching is bypassed for the done/ update.",
    )
    parser.add_argument(
        "--record-fix",
        nargs=2,
        metavar=("ROADMAP_PATH", "KEYWORDS"),
        default=None,
        help="Record a manual correction: the roadmap path that was falsely "
        "matched and a comma-separated list of keywords that caused the "
        "false positive. E.g. "
        "--record-fix battle-page-polish/hologram-row 'hologram,row,dedicated'",
    )
    parser.add_argument(
        "--list-fixes",
        action="store_true",
        help="List all recorded corrections (false-positive records that the "
        "CI has learned from)",
    )
    parser.add_argument(
        "--reset-blocklist",
        action="store_true",
        help="Reset the learned false-positive blocklist (keeps raw fix "
        "records, removes the compiled blocklist)",
    )
    args = parser.parse_args()

    os.chdir(REPO_ROOT)

    # -----------------------------------------------------------------------
    # Self-improvement commands (record/list/reset corrections; no pipeline)
    # -----------------------------------------------------------------------
    if args.record_fix:
        path, keywords_str = args.record_fix
        keywords = [kw.strip() for kw in keywords_str.split(",") if kw.strip()]
        # Try to read the description that was falsely matched
        desc = read_full_description(ROADMAP_DIR, path)
        if not desc:
            # Fall back: look in done/
            desc = read_full_description(DONE_DIR, path)
        excerpt = (desc or path).split("\n")[0][:120]
        record_correction(path, keywords, excerpt)
        print("\nCorrection recorded. The CI will apply this learning on next run.")
        return

    if args.list_fixes:
        fixes = list_corrections()
        if not fixes:
            print("No corrections recorded yet.")
            return
        print(f"Recorded corrections ({len(fixes)}):\n")
        for fpath, data in fixes:
            print(f"  {fpath.name}")
            print(f"    Path:     {data.get('roadmap_path', '?')}")
            print(f"    Keywords: {', '.join(data.get('false_positive_keywords', []))}")
            print(f"    Desc:     {data.get('description_excerpt', '?')[:80]}")
            print()
        print(f"Total: {len(fixes)} correction(s) filed.")
        return

    if args.reset_blocklist:
        if FALSE_POSITIVE_BLOCKLIST.exists():
            FALSE_POSITIVE_BLOCKLIST.unlink()
            print("False-positive blocklist reset. (Raw fix records preserved.)")
        else:
            print("No blocklist to reset.")
        return

    print("Megans Magische Meesters - CI Pipeline")
    print("=" * 60)

    # Step 1: Pull latest changes from origin
    pull_latest(dry_run=args.dry_run)

    # Step 2: Git status
    current_branch = git_status()

    # Step 3: Get changed files and diff
    print("\n" + "=" * 60)
    print("STEP 3: Source Code Change Analysis")
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

    if args.match:
        # Manual override: only the explicitly named items are candidates
        # for the done/ update, regardless of the auto-match results.
        new_matches = []
        for path in args.match:
            clean = path.strip().strip("/").replace("/description.txt", "")
            desc = read_full_description(ROADMAP_DIR, clean)
            if desc is None and (DONE_DIR / clean / "description.txt").exists():
                # Already moved to done/ — still list it so the skip is visible
                desc = ""
            if desc is None:
                print(f"  WARN: --match target not found in roadmap/ or done/: {clean}")
                continue
            new_matches.append({
                "roadmap_path": clean,
                "description": desc.split("\n")[0] if desc else clean,
                "category": get_description_category(clean),
                "matched_keywords": ["manual"],
                "total_keywords": 1,
                "score": 1.0,
            })
        print(f"\n  Manual --match override: {len(new_matches)} item(s) selected:")
        for m in new_matches:
            print(f"    - {m['roadmap_path']}")
    elif changed_files or diff_text:
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

        # ------------------------------------------------------------------
        # Self-improvement: apply learned blocklist from past corrections
        # ------------------------------------------------------------------
        adjusted_threshold, num_fixes = compute_dynamic_threshold()
        if adjusted_threshold != MATCH_THRESHOLD:
            print(f"\n  [self-improvement] Dynamic threshold: {adjusted_threshold} "
                  f"(base {MATCH_THRESHOLD} + {num_fixes} fix(es) × "
                  f"{FIX_PENALTY_PER_CORRECTION})")

        new_matches = suppress_false_positive_matches(new_matches)

        significant_matches = [
            m for m in new_matches if m["score"] >= adjusted_threshold
        ]
        low_matches = [
            m for m in new_matches
            if LOW_MATCH_FLOOR <= m["score"] < adjusted_threshold
        ]

        if significant_matches:
            print(f"\n  Matched {len(significant_matches)} roadmap items to code changes:\n")
            for m in significant_matches:
                conf = "HIGH" if m["score"] >= 0.4 else "MED" if m["score"] >= 0.25 else "LOW"
                adjusted = " [adjusted]" if m.get("_adjusted_by_blocklist") else ""
                sup_kws = m.get("_suppressed_keywords", [])
                sup_info = f" (suppressed: {', '.join(sup_kws[:3])})" if sup_kws else ""
                print(f"  [{conf:4s}]{adjusted} {m['roadmap_path']}")
                print(f"    Score: {m['score']} | Keywords: {', '.join(m['matched_keywords'][:6])}{sup_info}")
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

    # Resolve the feature branch: explicit --branch wins, otherwise derive a
    # unique name from the top matched roadmap goal.
    if args.branch:
        branch = args.branch
        goal = args.branch
        print(f"\n  Branch: {branch} (from --branch)")
    else:
        branch, goal = derive_goal_branch(new_matches)
        branch = ensure_unique_branch(branch)
        print(f"\n  Branch: {branch} (auto-derived from goal '{goal}')")

    # Step 4: Update done directory
    analyze_and_update_done(new_matches, done_descs, dry_run=args.dry_run)

    # Step 5: Run tests
    tests_passed = run_tests()

    if not tests_passed:
        print("\n" + "=" * 60)
        print("ABORT: Tests failed. Fix issues and re-run.")
        print("=" * 60)
        sys.exit(1)

    # Step 6: Update README roadmap
    run_update_readme()

    # Step 7: Commit and push
    commit_and_push(branch, goal, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("CI PIPELINE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
