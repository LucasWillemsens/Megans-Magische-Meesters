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

## 2026-11-21 — Google accounts
- For allauth Google sign-in where TLS terminates upstream of Django, configure `ACCOUNT_DEFAULT_HTTP_PROTOCOL` to the public scheme so generated OAuth callback URIs match the provider registration; allow a local override for direct HTTP testing.
- With `SOCIALACCOUNT_ONLY = True`, allauth requires `ACCOUNT_EMAIL_VERIFICATION = 'none'`; admin authorization should independently require a verified `EmailAddress` matching the configured admin email.
- Account-to-player linking should be a controlled, idempotent operation against existing records, refuse already-linked endpoints, and never create users or players. Document and prepare production linking without claiming it is complete until it has actually run against the production database.
- Keep external OAuth credentials out of source and PR environments; optional deployment configuration can pass secrets through to the application without printing or generating them.

## 2026-11-21 — Archived band posts
- Wayback's linked post pages can expose content absent from home-page snapshots; enumerate historical post URLs across feeds/category pages and preserve only text actually captured, including title-only pages where no body was archived.
- Generate individual post URL patterns from the news data to keep historical URLs and content in one source of truth, and test full feed-to-post traversal plus literal captured text.
- Archived visual structure may place the stage image as a page-background layer rather than a hero element; contract tests can pin both the absence of hero markup and the CSS background/paragraph treatment.
