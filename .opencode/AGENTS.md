# .opencode guidance

## Agents
- Agent definitions in `.opencode/agents/` evolve cleverly: every engineering pass leaves the file smaller and more effective, never merely longer. Three levers, in order of preference — point the agent at local context it reads itself at runtime (repository files, entry points, existing agents) instead of inlining facts; extract stable know-how the agent needs only sometimes into skills in `.opencode/skills/` that load on demand; delete instructions that no longer earn their tokens. An agent file is done evolving when it works optimally in regards of quality, time and minimal token usage. Small is the outcome of clever evolution, not a target reached by cutting substance.
- OpenCode registers every Markdown file in `.opencode/agents/` as an agent definition, so only agent definitions go there — guidance for this directory lives in this file instead.
