---
name: Deployment
description: Operate the paintedpillars.com deployment managers for Megans Magische Meesters — authorization rules for scripts/production.py (deploy [--force] | status | stop) and scripts/pr_environments.py (sync | status | rebuild | stop), --force semantics, and the post-run smoke-test checklist, pointing to scripts/production.md and scripts/pr_environments.md as the source of truth. Use when the user asks to deploy production, check or stop the live site, or sync, rebuild, or stop the per-PR test environments.
---

# Deployment

`scripts/production.py` serves production at https://www.paintedpillars.com/
from the canonical `main` branch; `scripts/pr_environments.py` builds and
serves one environment per eligible PR at
`https://pr-<number>.paintedpillars.com/`. Both work inside gitignored
`var/deployments/` runtime state, which must never be committed. Their docs
are the source of truth — gates, environment, runtime layout, security
boundary, routing, and full smoke-test procedures live there and are never
restated here:

- `scripts/production.md` — read before running `scripts/production.py`
- `scripts/pr_environments.md` — read before running `scripts/pr_environments.py`

## Authorization

These managers touch the live production server and its SQLite database, and
`sync` publishes PR comments. Every invocation requires an explicit user
request: `deploy`, `stop`, `sync`, and `rebuild` run only when the user asks
for that outcome; `status` runs when the user asks for the current deployment
state or while handling their deployment request. Never run a manager on your
own initiative. The one standing exception is the fixed finishing step of
implementation work: after implementing and verifying a change, the coder and
build agents push its branch and run `scripts/pr_environments.py sync` so the
PR test environment serves the new head; production (`scripts/production.py`)
is never part of that step.

`deploy` skips the rebuild when `main`'s head is already deployed and
serving; `--force` re-runs the gates and swaps the server anyway. Pass
`--force` only when the user explicitly asks for a forced redeploy.

## Commands

```
python3 scripts/production.py deploy [--force]   # fetch main, run gates, swap the server
python3 scripts/production.py status            # head commit, deploy time, pid/port, failures
python3 scripts/production.py stop              # stop the gunicorn process
```

```
python3 scripts/pr_environments.py sync           # discover PRs, rebuild changed ones, publish, rewrite routes
python3 scripts/pr_environments.py status         # list recorded environments
python3 scripts/pr_environments.py rebuild <pr>  # force one PR's environment back up (evicting if needed)
python3 scripts/pr_environments.py stop <pr>     # stop one environment, retained for rebuild
```

## Smoke-test checklist

Verify before reporting success — a command's clean exit is not proof:

- **After `deploy`:** `status` shows `ready` with the expected head sha and a
  running pid; the title page returns 200 (curl the production port with the
  `Host: www.paintedpillars.com` header, or the public URL). Static checks
  through Cloudflare need a cache-busting query string and a read of
  `cf-cache-status` — cached 200s and 404s can mask the real origin state
  for hours. A failed gate leaves the old server serving: report the
  recorded failure from `status`; do not fix or retry without the user.
- **After `sync` or `rebuild <pr>`:** `status` lists the PR `ready` on its
  port and its title page returns 200. A failed build records `failed` and
  publishes no URL — report the failure message. A fork PR must come back
  `rejected` with no checkout and no PR comment; anything else breaks the
  security boundary — stop and report.

The exact commands and full end-to-end procedures — the local-mirror
production smoke test and the Windows/WSL proxy-and-tunnel test — are in the
Smoke test sections of the two docs above.
