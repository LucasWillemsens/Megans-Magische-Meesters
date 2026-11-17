# agent-loops rule candidates

## agent-bodies-point-dont-duplicate
- Pattern: Three separate review comments in one PR flagged agent files duplicating know-how that already lives in a skill or script docstring (CI workflow, pick_pr_comment contract, style reference).
- Evidence: PR #28 (devops.md ln 37, pr-comment-analyst.md ln 22, agent/SKILL.md ln 12)
- Proposed rule: Agent bodies reference skills, docstrings, and exemplars instead of restating their content inline.
- Status: candidate

## scoped-agent-permissions
- Pattern: Orchestrator agents granted `resource: "*"` on edit/read/subagent far exceed what their workflow needs.
- Evidence: PR #28 (pr-investigator.md ln 7)
- Proposed rule: An agent's permissions list exactly the resources its workflow touches; no wildcard grants on narrowly scoped agents.
- Status: candidate

## delegate-substantive-work
- Pattern: A primary orchestrator performing judgment-heavy, fully-specified editing work inline contradicts its own "use a subagent for each task" rule.
- Evidence: PR #28 (devops.md ln 87)
- Proposed rule: When an orchestrator does substantive file-editing work, it delegates to a dedicated subagent and verifies the result.
- Status: candidate
