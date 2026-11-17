---
name: PR Comment Pickup
description: Claims exactly one unresolved code review comment from the current PR for analysis via scripts/pick_pr_comment.py — the run-once rule, result shape, and error and no-comment handling. Use when a single PR review comment must be claimed before it can be analyzed.
---

# PR Comment Pickup

Claim your comment — never select one yourself. Run this exactly once, from the repository root of the current PR checkout:

```
python3 scripts/pick_pr_comment.py
```

The script uses authenticated `gh` against the current repository PR, excludes general PR/review comments, and immediately resolves one thread before returning it. Do not implement your own PR/comment selection logic.

The result has the shape `{path} ( ln: {line}): {comment}` — the file, line, and comment to investigate.

- If the script exits unsuccessfully or prints `{"status":"error", ...}` to stderr, report that pickup failed and do not claim a thread was picked up.
- If it prints `{"status":"no_comment"}`, do not investigate or resolve anything; report explicitly that no eligible code comments remain.
