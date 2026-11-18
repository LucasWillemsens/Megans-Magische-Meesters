---
name: Agent
description: Engineer OpenCode agent definitions — read a closely related example, apply the frontmatter and body contract, validate the result. Use when creating or reworking an agent in .opencode/agents/ or deciding what belongs in an agent file versus a skill.
---

# Agent

How agent definitions in this repo are engineered: read a closely related example, apply the contract, validate the result.

## Read a closely related example first

Before creating a new agent, read a closely related example — the existing agent in `.opencode/agents/` with the closest role, picked from a filename listing — and understand its details before writing anything. One close example is the style reference, not a wholesale directory read.

Interpret the example field by field: ask what each choice accomplishes for that role, carry the choice over when the reason still holds for the new agent, and re-decide it when the new role flips the reason.

- `description` — how it states the role and its "use when" triggers so the agent is pickable by description alone
- `mode` — entry point, delegated worker, or both, and the wiring that follows from it
- `model` and `temperature` — the role's economics: routing and verifying runs cheap and cold, authoring runs strong and steady
- `permissions` — every grant traces to a verb in the body, every deny is protective, and grants the body never uses are cut
- `body` — the line between inlined identity and operational steps, the exact delegation invocations, the pointers to skills and to files it reads at runtime, and the hard rules that keep decisions with the user

Worked example — the task: create a platform agent, an agent owning this repo's OpenCode platform (`.opencode/` agents and skills, `rules/`, `opencode.json`). The closely related example is `devops.md`, the repo's primary orchestrator; reading its details teaches:

- Its `description` names the project, the role, and the exact user triggers — implement a roadmap goal, make a direct code change, run the CI pipeline. The platform agent states its own scope and triggers the same way.
- Its `mode: primary` plus `default_agent` in `opencode.json` shows how a session entry point is wired. The platform agent runs both ways, invoked directly and delegated to, so it takes `mode: all` — and making any agent the session default needs the user's approval to change `default_agent`.
- Its model and temperature follow the work, not the domain: devops routes and verifies, so it runs cheap and cold (`glm-5.3-flash#low`, `0.1`); the platform agent authors files itself, so it flips strong and steady — the repo's platform agent `agent-engineer.md` lands on `glm-5.3#max`, `0.4`.
- Its permissions answer its body's verbs — `subagent` to the planner/build/memory delegations, `todowrite` for subgoal tracking, `shell` for the `git status` check, `read`/`grep`/`glob` for finding goal files. The same test on the platform agent's verbs yields `edit` for agent and rules files, `shell` for validation commands, `read`/`grep`/`glob` for exploring the platform — and no `subagent` grant, because it works directly.
- Its body shows the shape to reuse: identity paragraph, the routed workflows as a numbered list, per-workflow steps with exact `Task(...)` snippets and a verification step after every delegation, product decisions handed back to the user, and know-how needed only sometimes kept as bare skill pointers (CI, memory). The platform agent reuses the shape and ends with a pointer to the `agent` skill, which carries this contract so the file stays small.

Then read every rule whose scope covers the work — the `rules-management` skill documents scopes and where implementations live.

## Frontmatter

- `description` — one or two sentences stating what the agent does and when to use it. It is the selection interface: OpenCode, the devops orchestrator, and the user pick agents by description alone.
- `mode` — `primary` for user-facing entry agents, `subagent` for delegated workers, `all` when the agent must work both ways.
- `model` and `request.body.temperature` — copy the existing agent whose work the new agent's work most resembles, unless the user specifies otherwise.
- `permissions` — grant every tool the body instructs the agent to use, deny the tools it must never use, and grant nothing the instructions never mention.

## Body

- Open with the identity: the project and the agent's role in one paragraph.
- Follow with the shortest instruction set that makes the agent succeed: operational steps, the files or entry points it must read itself, and its hard rules.
- Make the agent explore the repository at runtime; never inline codebase facts that will rot.
- Prefer skills over inline text for stable know-how the agent needs only sometimes — on-demand loading keeps the file small.
- One agent, one purpose — if the request describes two jobs, propose two agents.
- Every rework leaves the file smaller or cleverer: extract to skills, replace inline text with local context, delete dead instructions.

## Validate

1. The frontmatter parses and uses only documented fields:
   ```
   python3 -c "import sys,yaml; yaml.safe_load(open(sys.argv[1]).read().split('---',2)[1])" .opencode/agents/<name>.md
   ```
2. Someone who has never seen the file could pick this agent from the list by its description alone.
3. Every tool the body uses is allowed by the permissions, and every allowed tool is either used or explicitly protective.
4. The mode matches the invocation: a new subagent needs no wiring — parents discover subagents by description — but a new session default requires `default_agent` in `opencode.json`; ask the user before changing that.
5. After reworking an agent, reread the final file top to bottom and remove leftovers that contradict the new instructions.
6. Any rule written or updated passes `python3 .opencode/skills/rules-management/scripts/check_rules.py`, and its substance is implemented where its scope implies.
7. Every skill created or referenced is discoverable: correct path form under `.opencode/skills/` with a frontmatter description.
