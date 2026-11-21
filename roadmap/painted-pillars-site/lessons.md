# Painted Pillars Site lessons

## 2026-11-20 — URL prefix and band-site rebuild

- Mounting a Django app at a URL prefix should rely on URL reversing for redirects, links, API schema locations, and cookie paths; root-relative static URLs can remain at `/static/` when the deployment serves static assets separately.
- Client-side behavior that derives paths from `window.location.pathname` can often inherit a URL prefix naturally, but verify staged-cookie scope and deletion at the prefixed route.
- Smoke-test documentation and PR-environment URLs are part of a URL-prefix change; update operational examples and test assumptions alongside application routes.
- When restoring an archived site, distinguish captured content from unavailable archive assets and make missing imagery explicit; use local minimal recreations for missing service icons rather than silently referencing broken remote URLs.
- Preserve distinct archived routes such as `/music/` and `/songs/` when both existed; serving the same releases content on both routes avoids a needless redirect and keeps historical links usable.
- A static social-links contact page is preferable to presenting a nonfunctional archived third-party form when no working submission destination has been supplied.

## 2026-11-21 — PR #32 review
- Planning must preserve user intent rather than turn an agent's assumptions into narrower specifications: archive research should follow the full snapshot history and linked post pages, page scope should not be frozen without instruction, and visual descriptions should not reinterpret the requested composition.
- Once a roadmap subgoal is materially planned but implementation remains outstanding, reopen its parent checkbox and state the new scope; leave implementation actions visible as the next thread rather than marking the work complete.
