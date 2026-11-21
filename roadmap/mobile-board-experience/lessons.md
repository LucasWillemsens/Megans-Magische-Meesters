# mobile-board-experience lessons

## 2026-11-21 — Mobile board experience
- `runserver --insecure` serves static URLs through Django's staticfiles finders, not `STATIC_ROOT`; PR environments must place art in a finder-visible directory (such as a `STATICFILES_DIRS` entry), while production's Caddy serves its collected tree. See also `roadmap/agent-loops/lessons.md`.
- Native HTML5 drag-and-drop does not fire on touch. Mobile drag should route touch lift/move/release into the existing drop handlers so the established staging, allowance, and cookie-payload behavior remains the single source of truth.
- Mobile layout regression checks can verify the CSS/template contract, but geometry needs browser-level viewport measurements; a CSS-only assertion cannot establish that enemy, player, and hand regions are visible and non-overlapping.
- For a constrained board layout, scale both em-based offsets and layout-critical rem dimensions from one board-scale variable; otherwise card art, rows, and controls drift relative to one another on short screens.
- Mobile CSS overrides must match the specificity of the base rules they replace; placing an equal-specificity override at the end of the stylesheet avoids later base rules undoing it.
- Card artwork should preserve intrinsic aspect ratio with `object-fit: contain`; reserve an explicit height for the card footer so its label remains within the clipped face at scaled sizes. Viewport-filling decorative backgrounds are the exception and should retain `cover`.
