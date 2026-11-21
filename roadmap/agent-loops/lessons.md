# agent-loops lessons

## 2026-11-20 — Production deployment at www.paintedpillars.com
- `STATIC_URL` must be root-relative (`'/static/'`): without the leading slash every `{% static %}` URL is page-relative and 404s on any path deeper than one level — the title page masked the bug because `/title/` happens to resolve correctly.
- `runserver --insecure` serves static URLs through Django's staticfiles finders, not `STATIC_ROOT`; files must be in a finder-visible source such as `STATICFILES_DIRS`, whereas production's Caddy serves the collected static tree (mobile-board-experience).
- Caddy `file_server` keeps the matched URI prefix: with `handle /static/*` the served path is `<root>/static/<file>`, so a root change to a flat collectstatic tree needs `handle_path` (which strips the prefix) or nothing under `/static/` serves at all.
- Cloudflare caches static extensions by URL *and* caches their 404s: an origin fix can be invisible for up to ~4 hours (`cf-cache-status: HIT` on a 404), and stale 200s can mask a fully broken origin — always verify with a cache-busting query string and read `cf-cache-status` before trusting a status code.
- Production static has three sources, not one: `STATICFILES_DIRS` entries (`var/www/static/`, gitignored `assets/downloaded/`) *and* app-level `MMM/static/` — only `collectstatic` into a persistent `STATIC_ROOT` (plus injecting gitignored art at deploy time) covers all of them; serving a single source directory always drops files.
- Runtime state that must survive rebuilds (db, secret, collected static) belongs beside the checkout, never inside it, so `git clean -fdx` cannot destroy it — same isolation principle as the per-PR environments.
- User-level binaries (`~/.local/bin`) plus a high port (8080) avoid sudo entirely in WSL; port 80 needs root, so the tunnel points at the user-owned port instead of the conventional one.
- Caddy started with `admin off` has no reload endpoint — config changes require a process restart, so `caddy reload` failing with "connection refused" means restart, not debug the config.

## 2026-11-18 — PR #31 review: platform junk and static assets
- A static-asset reference missing from Git does not prove the feature is dead: deployment may contain untracked binary assets. Before deleting references, verify the deployed environment or ask the owner; prefer restoring and committing the asset, as with `titlepageartWIP.png` (PR #31).
- A platform-junk ignore list should cover the maintainer's actual development OS, not only Mac/IDE artifacts; Windows cleanup should include `*.lnk`, `Thumbs.db`, and `desktop.ini` (PR #31).

## 2026-11-18 — Per-PR test environments
- Resolve PR head commits with `git ls-remote` against the canonical remote when the installed GitHub CLI lacks the needed head-SHA field; this avoids fetching or executing untrusted PR code just to discover its revision.
- Keep deployment orchestration stdlib-only when it runs on an already-provisioned host, and document host prerequisites rather than adding runtime dependencies for the manager.
- Persist per-environment secrets in gitignored state and never print them; host-only session cookies avoid widening cookie scope across routed test environments.
- Check process liveness after startup before publishing a ready route, so port conflicts and immediate exits cannot appear as healthy deployments.
- Treat stopped/failed environments with unchanged revisions as stable state; rebuild only on a new revision or an explicit request to avoid capacity churn.
- Test deployment state transitions against lowest-unused port allocation, including an environment's own old server appearing among stopped records during rebuild.
- Legacy PR revisions may not contain current deployment settings; keep their databases isolated in their checkout and document that rebuild cleanup resets them.

## 2026-11-16 — PR #28 review insights (agent/skill framework refactor)
- Inline narrative of another artefact's contract rots: agent bodies that restate a script's output shape, errors, or semantics duplicate its docstring; point to the source instead (pr-comment-analyst.md, PR #28).
- Redundant restatement of a skill's content in an agent body wastes always-loaded tokens; keep a bare pointer bullet and let the skill carry the detail (devops.md CI section, PR #28).
- Small, fully specified, verifiable work belongs in a dedicated subagent even for orchestrators; memory consolidation is such a task (devops.md, PR #28).
- Skills should demand one named style exemplar, not a wholesale read of a whole directory; a distilled bullet list plus "copy the closest role" beats "read every file" (agent skill, PR #28).
- Broad `resource: "*"` permissions on a narrowly scoped orchestrator let it wander off-protocol; scope subagent launches and edit/read targets to exactly what the workflow touches (pr-investigator.md, PR #28).
- Converting a per-run delegation worker into a skill breaks its isolation and model routing; only extract stable know-how needed "sometimes", not the agent's core job (pr-comment-analyst.md, PR #28).

## 2026-11-21 — PR #32 review
- Consequential operational scripts should ship with their platform wiring: an on-demand skill should authorize and point to the `scripts/*.md` source of truth, and judgment-heavy deployment work should have a dedicated agent delegated to by devops. Do not duplicate the script documentation in the skill or agent.

## 2026-11-17 — PR #28 candidates absorbed into the evolving-agent rule
- A candidate is ripe for promotion only when no existing rule already covers its substance — check the rule set first and extend the covering rule instead of proposing a near-duplicate. All three PR #28 candidates (point-don't-duplicate, scoped-agent-permissions, delegate-substantive-work) were substance of the agents-evolve-cleverly rule and were absorbed into its v2 description and the .opencode/AGENTS.md implementation (candidates and the PR #28 scratchpad thread cleaned 2026-11-17).
