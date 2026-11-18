## Strictness
1

## Scope
path specific: .opencode/agents/*

## Description
Agent definitions evolve cleverly over time: every engineering pass leaves the file smaller and more effective, never merely longer. Three levers, in order of preference — point the agent at local context it reads itself at runtime (repository files, entry points, existing agents) instead of inlining facts; extract stable know-how the agent needs only sometimes into skills in .opencode/skills/ that load on demand; delete instructions that no longer earn their tokens. An agent file is done evolving when it works optimally in regards of quality, time and minimal token usage. Small is the outcome of clever evolution, not a target reached by cutting substance. Concrete manifestations of clever evolution: agent bodies reference skills, docstrings, and exemplars instead of restating their content inline; an agent's permissions list exactly the resources its workflow touches, with no wildcard grants on narrowly scoped agents; when an orchestrator does substantive, judgment-heavy editing work, it delegates it to a dedicated subagent and verifies the result.

## Context
- Introducing the rules framework while engineering the agent-engineer agent (2026-11-11)
- The agent-loops goal's PR #28 review — its three candidates (agent-bodies-point-dont-duplicate, scoped-agent-permissions, delegate-substantive-work) proved to be substance of this rule and were absorbed into it (2026-11-17)
