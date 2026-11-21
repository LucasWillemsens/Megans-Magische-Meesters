# band-site-rebuild scratchpad

## 2026-11-21 — PR #32 review
- State: The description's archive scope and visual interpretation need correction; the implementation follow-up is not yet applied.
- Discovered: Archive research must span all Wayback snapshots and follow links to actual per-post pages. WordPress admin content may be recoverable by Google login as `paintedpillars@gmail.com`. The stage photo (`bandHeroPhoto`) is the page background; white text remains readable because `<p>` elements have black backgrounds.
- Decided: Rewrite the goal for one page per archived post, not a frozen four-page scope; remove the hero image element, use the photo as the CSS background, add black paragraph backgrounds, update hero assertions, and reconsider the parent `[x]` checkbox.
- Next: Rewrite `description.txt`; follow up in `MMM/jinja2/MMM/band/home.jinja2`, `var/www/static/band.css`, and `MMM/tests.py` test `test_home_shows_the_archived_hero_listen_cta_and_news_feed`.
