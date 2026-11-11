---
name: Agent
description: Engineer OpenCode agent definitions — study the house style, apply the frontmatter and body contract, validate the result. Use when creating or reworking an agent in .opencode/agents/ or deciding what belongs in an agent file versus a skill.
---

# Agent

How agent definitions in this repo are engineered: study the house style, apply the contract, validate the result.

## Study the house style first

Read every file in `.opencode/agents/`, the skills in `.opencode/skills/`, and the root `opencode.json` before writing anything — they are the style reference:

- Descriptions state what the agent does and when to use it
- Model and temperature follow the role: orchestrators run cheap and cold, builders strong and steady
- Permissions grant exactly the tools the agent's own instructions use; a tool it must never touch is denied explicitly
- Bodies open with an identity paragraph, then short operational sections, and stay out of implementation detail that rots

Then read every rule whose scope covers the work — the `rules-management` skill documents scopes and where implementations live.

## Frontmatter

- `description` — one or two sentences stating what the agent does and when to use it. It is the selection interface: OpenCode, the devops orchestrator, and the user pick agents by description alone.
- `mode` — `primary` for user-facing entry agents, `subagent` for delegated workers, `all` when the agent must work both ways.
- `model` and `request.body.temperature` — copy the existing agent with the closest role unless the user specifies otherwise.
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
