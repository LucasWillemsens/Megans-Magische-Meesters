# agent-loops scratchpad

## 2026-11-12 — brainstorm: agent-loops goal created

- State: new top-level goal `roadmap/agent-loops/` with `description.txt` holding the user's spec and captured ideas. No subgoals yet, no code touched.
- User decisions (steering):
  - First priority: a deployed test environment per PR.
  - Dashboard lives on the test environment. It reads existing artefacts (PRs, decision notes, lessons, candidates, rules, done/). No taste or preference files.
  - Integrations: opencode go console, GitHub, Google Calendar, Gmail. Used for pacing and for finding when the user has time.
  - All agent decisions at propose level. The only approval gate is merging a PR.
  - Critic role: an agent that reviews proposals and co-owns the outcome. On failure, agent-engineer improves both agents and records the scenario in the memory ladder.
  - The loop runs continuously. While a PR waits for merge, agents pick up other goals or related improvements on new branches.
  - Dashboard supports drag-and-drop priorities.
- Discoveries relevant to the design:
  - README.md is generated from roadmap/ and done/, so parallel PR branches will conflict on it. done/ entries also move.
  - scripts/ci.py stages all changes, which is unsafe with parallel worktrees.
  - scripts/pick_pr_comment.py resolves the thread before analysis, so a comment can disappear without a fix.
  - devops.md tells the orchestrator to ask the user for open decisions. This conflicts with propose-level decisions.
  - Agents currently run on opencode-go glm-5.3-flash at low or high effort. The critic may need a different or stronger model.
- Open for next session: hosting choice for the test environment, the subgoal split and its order, whether Gmail is needed, and how worktree agents see the live STEERING.md order.
- Next: user answers the open questions. Then split the goal into subgoals, starting with the per-PR test environment.

## 2026-11-12 — priorities moved to STEERING.md

- User decided: dashboard priority lives in STEERING.md. This closes the earlier "where does the priority order live" question.
- Context found: `opencode.json` already lists `STEERING.md` under `instructions`. The opencode-reference skill says edits reach active agents before their next request. The file does not exist yet.
- Description updated: drag-and-drop writes to STEERING.md, which holds the priority order only. Opened a new question about worktrees seeing the live order. STEERING.md is tracked, so dashboard edits become commits.
- Not done: the file is not created. That belongs to the build of the dashboard subgoal.

## 2026-11-12 — STEERING.md is untracked and local

- User clarified: STEERING.md is not tracked. It only needs updating in the directories where agents run.
- Description updated: the dashboard fans the order out to every running directory (main checkout and each worktree). A new worktree is seeded at creation. The open question is now the source of truth and how the active set is found.
- Discovered constraint: `scripts/ci.py` stages all changes. The file must be gitignored or it will be committed. The dashboard subgoal must add it to `.gitignore`.

## 2026-11-12 — summary of remaining work

- Asked to summarize what completes the goal. Nothing new was decided. The goal is still at idea stage, with no subgoals or acceptance criteria.
- Next steps are recorded in the description. Answer the open questions, then hand the goal to the planner to split it and define acceptance criteria.

## 2026-11-16 — hosting decided: this PC, under paintedpillars.com

- User decided: PR test environments run on this PC or a free self-hosted runner, in parallel with production, all under https://www.paintedpillars.com/. The domain belongs to the band site, which is currently offline.
- Checked: the repo is public (`gh repo view` reports isPrivate=false). A self-hosted runner on a public repo runs fork PR workflow code on this PC. Fork PRs must be excluded, or the loop deploys without a runner.
- Description updated: hosting and domain are decided. Constraints added: public repo, PC as single point of failure, and the shared domain with the band site.
- Open: URL shape (subdomains need wildcard DNS and a certificate; paths need an app path prefix), production placement, how the domain reaches the PC (port forwarding or an outbound tunnel behind CGNAT), concurrency cap, cleanup, and runner versus loop-driven deploy. Also how the band site and the game share the domain.
- Next: user answers the open environment questions, then the planner can split the per-PR test environment subgoal.

## 2026-11-16 — environment recommendations accepted

- User said yes to the recommendations. Decided, recorded in description.txt:
  - Production at https://www.paintedpillars.com/. PR environments at https://pr-<number>.paintedpillars.com/. Subdomains, because cookies are host-scoped.
  - Cloudflare Tunnel to reach the PC. The domain's DNS moves to Cloudflare.
  - One local reverse proxy routes *.paintedpillars.com by hostname to each environment's port. The loop maintains the port map.
  - No GitHub runner. The loop deploys PR branches itself, so fork PRs never run on this PC.
  - At most 3 running PR environments plus production. The least recently pushed is stopped and rebuilt on demand. One build at a time.
  - The band site takes the apex when it returns. The game does not sit on the apex.
- Correction: the previous reply said the recommendations and a scratchpad entry had been written. They had not. This entry and the description update are the actual record.
- Still open: teardown after merge or close, and where production backups are stored.
- Next: plan the per-PR test environment as a subgoal, including how the planner handles the one-level subdomain and certificate setup.

## 2026-11-16 — remaining questions answered

- Production: none exists yet. The repo copy on the Windows machine is the primordial production, with the one production SQLite database. It runs this workspace under WSL too. Backups are stored on the Windows machine.
- STEERING.md: used only in the working environment, to steer agents in specific folders. Nothing to do with deployment. Interpretation to confirm: the dashboard priority order still goes there.
- Critic: a new agent.
- Sleep rule: the loop sleeps when the opencode limit is near, and in an emergency when agents are stuck going in circles. Open: what the circle signal is.
- pick_pr_comment.py: no change. Resolving on pickup is intended. Withdrawn from known issues. My earlier note that it could drop comments unfixed was wrong.
- ci.py: must stop staging everything so it works with parallel worktrees. Decided.
- Gmail: dropped. Removed from integrations and open questions.
- Still open: teardown after merge or close, how the primordial production is updated, the circle signal, and hard stops beyond merge for secrets or data deletion.
- Next: plan the per-PR test environment subgoal.

## 2026-11-16 — answers to remaining questions

- Circle signal: agents decide, at propose level, reviewed by the critic.
- Primordial production: the user updates the Windows copy by hand for now.
- Teardown: no teardown on merge or close. An environment is stopped only when all 3 slots are full and a new PR needs one. The one with the least recent activity goes first.
- Loop: runs 24/7, never stops on merge or other events, schedules its own sleeps. No hard stops. Note: this leaves no explicit guard for secrets or data deletion. Revisit if that matters.
- Calendar: deferred.
- STEERING.md: works like AGENTS.md but is applied dynamically. Specificity sets priority: a more specific folder wins, and the repo root applies everywhere. The dashboard priority belongs in the root STEERING.md, fanned out to each worktree root.
- Open: which root copy is the source for fan-out, whether folder-level STEERING.md should be untracked (untracked files do not reach worktrees), and the subgoal split.
- Next: plan the per-PR test environment subgoal.

## 2026-11-16 — STEERING.md scope corrected

- User clarified there is only one working folder, the current one. The user has already answered everything about STEERING.md.
- Removed from the description: fan-out to worktrees, seeding new worktrees, the source-of-truth question, and the folder-level untracked question.
- Kept: priorities in the root STEERING.md, dynamic like AGENTS.md (more specific folder wins), steering for the WSL workspace only, untracked and gitignored.
- Lesson: I kept reopening a settled question. When the user says something is answered, record it and stop asking.
- Next: plan the per-PR test environment subgoal.

## 2026-11-16 — subgoal order

- User: order does not matter. The last open question is closed.
- Description: the split (test environment, continuous loop, decisions and critic, dashboard, priority ordering, integrations) is the planner's starting point.
- Open questions now: only Calendar scopes, deferred by the user.
- Next: planner splits the goal and writes acceptance criteria. Test environment is the only subgoal the user has asked for first.
# 2026-11-16 — planning subgoals

- State: split `agent-loops` into six independently actionable roadmap leaves; `per-pr-test-environment` is first and planned at implementation/test-contract level.
- Discovered: `scripts/ci.py`'s `commit_and_push()` stages with `git add -A`; README is generated and `update_roadmap.py` can move `done/` entries. `mysite/settings.py` has hard-coded DEBUG, empty ALLOWED_HOSTS, and a repo-local SQLite path; deployment must parameterize these and avoid sharing production DB. `opencode.json` loads root `STEERING.md`; devops currently asks users to resolve decisions.
- Decided: deployment plan treats fork exclusion as a hard security boundary; no GitHub runner; sequential builds; per-PR checkout/runtime/database; proxy and tunnel routing; at most three running PR environments; no teardown on PR close/merge. Capacity uses least-recent activity (the final user decision supersedes the earlier scratchpad note about least-recent push).
- Risk: host/proxy/tunnel and Windows/WSL specifics cannot be fully exercised by normal repository tests; require a documented local smoke test. The primordial production copy/database must not be modified by PR deployments.
- Next: build only `per-pr-test-environment` first; later leaves depend on its lifecycle interface where relevant. Calendar scopes remain deferred.

## 2026-11-16 — PR #28 review: all six code comments analyzed
- State: PR #28 (`fixbugs`, agent/skill framework refactor) reviewed; 6 unresolved code comments analyzed, all valid; none remain.
- Fixes reviewers found, for the next build session to start from:
  1. New on-demand coding subagent (`coder.md`, `mode: subagent`, coding-skill-driven), and move generic code-quality guidance out of `build.md` into the `coding` skill (comment on build.md ln 2).
  2. Trim devops.md ln 37 overview bullet to a bare pointer: "Run CI — when the user asks, follow the `ci` skill."
  3. New `memory.md` subagent (`mode: subagent`) to run the consolidation protocol; devops delegates Step 3 to it and verifies the result.
  4. pr-comment-analyst.md: do NOT convert to a skill (breaks delegation/isolation); replace inline `pick_pr_comment.py` contract duplication with a pointer to its docstring; optionally set `mode: subagent`.
  5. pr-investigator.md frontmatter: scope permissions — `subagent` only `pr-comment-analyst`, `skill` only `memory`, `edit` only roadmap scratchpad/lessons/candidates, read/grep only `roadmap/**` and `README.md`; drop wildcard grants.
  6. agent/SKILL.md ln 12: replace "read every file" with one named exemplar (`devops.md`), drop the wholesale skills/opencode.json read.
- Recorded: lessons in `roadmap/agent-loops/lessons.md`; 3 rule candidates in `roadmap/agent-loops/candidates.md` (citing PR #28).
- Next: implement the six fixes, likely via `agent-engineer`.

## 2026-11-17 — fix 1 of the six implemented: on-demand coder decoupled from the planner
- State: coder.md created (`mode: subagent`, build's model/permissions, body driven only by the coding skill); build.md slimmed (73→58 lines, generic guidance out, planner workflow intact, description hands unplanned coding to the coder); coding skill absorbed the verification flow (sanity-check references → `manage.py check` → `manage.py test`) and lost its roadmap-only phrasing ("roadmap goal at hand" → "task at hand"); devops.md gained a third workflow routing direct code changes to the coder, bypassing the planner.
- Decision: devops routing added so the decoupling is real at the orchestration level; coder permissions copy build (broad worker, wildcards match its remit — revisit only if the scoped-agent-permissions candidate is promoted).
- Next: fixes 2–6 of the PR #28 list remain (devops CI bullet trim, memory.md subagent, pr-comment-analyst pointer, pr-investigator permission scoping, agent-skill exemplar).

## 2026-11-17 — fixes 2–5 of the six implemented (user-amended)
- State: devops CI bullet is a bare `ci`-skill pointer and the duplicate CI section is gone; new `memory.md` subagent (`mode: subagent`, planner's model) runs both `memory`-skill protocols; devops Step 3 and pr-investigator Step 2 delegate to it and verify the result; pr-investigator wildcards replaced (subagent only `pr-comment-analyst` + `memory`, read only `roadmap/**`, edit/shell/glob/grep denied); memory agent scoped (edit only `roadmap/**` scratchpad/lessons/candidates, read `roadmap/**` + `README.md`, glob `roadmap/**`, shell only `rm roadmap/**`); pr-comment-analyst's pickup contract extracted into the `pr-comment-pickup` skill, its shell scoped to the pickup script, `gh pr *`, and read-only `git diff/log/show`.
- Decided (user amendments vs the PR #28 notes): fix 4 as a skill instead of a docstring pointer — the analyst stays an agent, so delegation/isolation is preserved; analyst keeps `mode: all` (the "optionally" was not taken); fix 5 became delegation to the memory agent, so the review's edit/read scope moved onto the memory agent.
- Discovered: OpenCode permissions — last matching rule wins, so broad denies must precede narrow allows; the `edit` action covers `write` too; `grep`'s resource is the regex, not the path, so grep cannot be path-scoped and the memory agent's grep stays confined by instruction only. The old inline analyst text also misstated the pickup output — the script really prints `{path} ( ln: {line}): {comment}` and errors go to stderr.
- Next: fix 6 of the six remains — agent/SKILL.md ln 12, replace "read every file" with one named exemplar (`devops.md`), drop the wholesale skills/opencode.json read.
