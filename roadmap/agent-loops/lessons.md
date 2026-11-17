# agent-loops lessons

## 2026-11-16 — PR #28 review insights (agent/skill framework refactor)
- Inline narrative of another artefact's contract rots: agent bodies that restate a script's output shape, errors, or semantics duplicate its docstring; point to the source instead (pr-comment-analyst.md, PR #28).
- Redundant restatement of a skill's content in an agent body wastes always-loaded tokens; keep a bare pointer bullet and let the skill carry the detail (devops.md CI section, PR #28).
- Small, fully specified, verifiable work belongs in a dedicated subagent even for orchestrators; memory consolidation is such a task (devops.md, PR #28).
- Skills should demand one named style exemplar, not a wholesale read of a whole directory; a distilled bullet list plus "copy the closest role" beats "read every file" (agent skill, PR #28).
- Broad `resource: "*"` permissions on a narrowly scoped orchestrator let it wander off-protocol; scope subagent launches and edit/read targets to exactly what the workflow touches (pr-investigator.md, PR #28).
- Converting a per-run delegation worker into a skill breaks its isolation and model routing; only extract stable know-how needed "sometimes", not the agent's core job (pr-comment-analyst.md, PR #28).

## 2026-11-17 — PR #28 candidates absorbed into the evolving-agent rule
- A candidate is ripe for promotion only when no existing rule already covers its substance — check the rule set first and extend the covering rule instead of proposing a near-duplicate. All three PR #28 candidates (point-don't-duplicate, scoped-agent-permissions, delegate-substantive-work) were substance of the agents-evolve-cleverly rule and were absorbed into its v2 description and the .opencode/AGENTS.md implementation (candidates and the PR #28 scratchpad thread cleaned 2026-11-17).
