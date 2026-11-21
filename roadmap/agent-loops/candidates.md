# agent-loops rule candidates


## Verify static assets before deleting references
- Pattern: An asset absent from Git may still exist in the owner's deployment; removing its references can silently remove a live feature.
- Evidence: PR #31's phantom-asset cleanup removed deck-indicator faces (`extradeck.png`) and the wood-texture board backdrop, even though the reviewer reported deployment assets present; the PR restored `titlepageartWIP.png` from the same deployment.
- Proposed-rule: Before deleting static-asset references as dead code, verify the deployed environment or ask the owner; restore/commit the asset when it is still part of the product.

## Test rendered visual features, not just markup shells
- Pattern: Contract tests that assert only structural shells can pass after the visual content vanishes.
- Evidence: PR #31 left empty deck-indicator `<li>` elements while layout machinery and shell assertions stayed green.
- Proposed-rule: For user-visible template features, assert that the feature's visual face/content exists, not only its outer markup.

## Cover Windows platform junk in ignore lists
- Pattern: Ignore lists can omit OS-specific artifacts when they focus only on Mac/IDE clutter.
- Evidence: PR #31 committed `assets/DownloadedAssests - Shortcut.lnk`; `.gitignore` had no Windows entries.
- Proposed-rule: Include platform-junk patterns for the OS used by maintainers, including Windows `*.lnk`, `Thumbs.db`, and `desktop.ini`.

## Ship operational scripts with platform wiring
- Pattern: Operational scripts can be added without the discoverable skill and agent wiring needed to safely invoke them.
- Evidence: PR #32 reviewer requested a deployment skill authorizing the production and PR-environment commands, a dedicated deployment agent, and devops delegation for existing `scripts/production.md` and `scripts/pr_environments.md` workflows.
- Proposed-rule: Ship consequential operational tooling with an on-demand skill that points to its canonical docs and a dedicated judgment-capable agent wired into the orchestrator; do not duplicate the docs' contract.
