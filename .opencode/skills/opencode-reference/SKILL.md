---
name: OpenCode Reference
description: OpenCode platform specifics for this repo — agent field reference, deprecated V1 fields, skill structure, dynamic STEERING.md steering, instruction precedence. Use when engineering agents, skills, or instructions, or when OpenCode behavior affects the work.
---

# OpenCode Reference

OpenCode know-how for this repo lives in this skill and loads on demand — never inlined into agent files, so it cannot bloat agents or contexts where it is irrelevant. The bundled `opencode` skill covers OpenCode generally (plugins, SDK, V1 migration, troubleshooting); this skill holds the specifics.

## Agent field reference

The authoritative field reference is https://opencode.ai/docs/agents — consult it whenever the existing agents in `.opencode/agents/` do not demonstrate the field you need. Refresh the local copy, then read `references/agents.md`:

```
python3 .opencode/skills/opencode-reference/scripts/fetch_reference.py
```

Deprecated V1 frontmatter fields must never appear in agent files: `temperature`, `top_p`, `prompt`, `permission`, `tools`, `disable`, `maxSteps`.

## Skills

A skill is a directory under `.opencode/skills/` with a `SKILL.md` (frontmatter `name` + `description`), optionally carrying supporting files the instructions reference by path relative to the skill directory:

```
.opencode/skills/<skill-id>/
├── SKILL.md
├── scripts/
└── references/
```

## Dynamic steering instructions

Instructions can be scoped to local STEERING.md files through the `instructions` array in `opencode.json`. When a STEERING.md is updated, the change is signaled to active agents before their next request — an agent orchestrating other agents, in parallel even, can steer them simultaneously by updating the file.

## Instruction precedence

Instructions combine in this order — sources are added, not overridden:

1. Agent or provider system prompt
2. Code Mode tool guidance, when enabled
3. MCP server, reference, and skill guidance
4. Global and project AGENTS.md files, then configured instructions
5. Built-in date and environment context
6. Session-specific instruction entries supplied through the API

## Keeping this current

When new documentation is needed beyond what `references/` holds, fetch the page with the script — `python3 .opencode/skills/opencode-reference/scripts/fetch_reference.py <docs-page>` — and distill the relevant facts into this skill or its `references/`, never into agent files.
