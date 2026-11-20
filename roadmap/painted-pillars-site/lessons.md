# Painted Pillars Site lessons

## 2026-11-20 — URL prefix and band-site rebuild

- Mounting a Django app at a URL prefix should rely on URL reversing for redirects, links, API schema locations, and cookie paths; root-relative static URLs can remain at `/static/` when the deployment serves static assets separately.
- Client-side behavior that derives paths from `window.location.pathname` can often inherit a URL prefix naturally, but verify staged-cookie scope and deletion at the prefixed route.
- Smoke-test documentation and PR-environment URLs are part of a URL-prefix change; update operational examples and test assumptions alongside application routes.
- When restoring an archived site, distinguish captured content from unavailable archive assets and make missing imagery explicit; use local minimal recreations for missing service icons rather than silently referencing broken remote URLs.
- Preserve distinct archived routes such as `/music/` and `/songs/` when both existed; serving the same releases content on both routes avoids a needless redirect and keeps historical links usable.
- A static social-links contact page is preferable to presenting a nonfunctional archived third-party form when no working submission destination has been supplied.
