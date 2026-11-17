# Pre-battle deck flow lessons

## 2026-11-17 — Shared styling review
- Shared CSS classes such as `.players`, `.title`, and `.backlink` can affect multiple templates. Enumerate all templates using a shared class before changing its global styling; prefer explicit template-carried page classes (such as `.demoTitle`) for page-specific appearance over structural `:has` exception lists, which can miss pages and create inconsistent components. → rule sequential-side-effecting-wholes-and-rule-execution-state-stay-evident-in-one-function-body v2
- User feedback reported outside formal PR comments is still review evidence worth preserving in memory; it is not visible to the PR-comment pickup loop.
