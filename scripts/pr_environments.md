# Per-PR test environments

`scripts/pr_environments.py` is the loop-owned deployment manager. There is no
GitHub runner: the loop itself builds and serves every eligible pull request on
this host, so fork PR code never runs here.

Each eligible PR gets `https://pr-<number>.paintedpillars.com/MMM/`, backed by its
own checkout, SQLite database, and runtime port under `var/deployments/`.
Everything under `var/deployments/` is gitignored runtime state and must never
be committed. The game app itself is mounted at `/MMM/` in the URLconf, so
the PR environment serves exactly the same paths as local development and
production; the bare host root redirects there until the band site exists.

## Security boundary

- A PR is eligible only when its head repository identity equals the canonical
  repository (`MMM_PR_CANONICAL_REPO`, default
  `LucasWillemsens/Megans-Magische-Meesters`). The identity is read from
  `gh pr list` output and compared case-insensitively; a PR with missing or
  unknown head-repository fields is rejected as well (fail closed).
- Fork PRs are recorded as `rejected` in the deployment state before any
  checkout or command execution. The manager never fetches, checks out, or
  runs a fork PR's code.
- PR head commits are resolved through `git ls-remote origin refs/pull/*/head`
  against the canonical remote and checked out via
  `git fetch origin pull/<n>/head` in the isolated per-PR checkout.
- The manager only works inside its own deployments directory. It never reads
  or writes the Windows-hosted production checkout or the production SQLite
  database, and it never touches this repository's own `db.sqlite3`.

## Commands

```
python3 scripts/pr_environments.py sync              # discover PRs, rebuild changed ones, publish, rewrite routes
python3 scripts/pr_environments.py status            # list recorded environments
python3 scripts/pr_environments.py rebuild <pr>     # force one PR's environment back up (evicting if needed)
python3 scripts/pr_environments.py stop <pr>        # stop one environment, retained for rebuild
```

The loop calls `sync` periodically (for example from a 5-minute timer inside
the continuous loop). Builds are serialized by a file lock, so concurrent
syncs wait for each other.

One sync does, in order:

1. Read open PRs and resolve their current head commits.
2. Record fork PRs as rejected; print one line per rejection; do nothing else
   with them.
3. Refresh each running environment's last-activity time from its server log;
   mark a closed PR's dead server `stopped` so its slot frees up.
4. Plan a rebuild for every open PR with a new head commit, a missing
   environment, a crashed build, or a dead server.
5. Make capacity for new slots by stopping the least recently active running
   environments; a slot needed by a planned rebuild is never taken from it.
6. Build each planned PR: clone/update the checkout, then
   `manage.py migrate` → `manage.py add_deck_cards` (the deterministic seed of
   Lucas's 52-card playing deck) → `manage.py check` → `manage.py test` →
   `manage.py collectstatic --noinput` into `pr-<n>/staticfiles/`, then copy
   the working repository's gitignored downloaded art into the checkout's
   `assets/downloaded/` (the static directory runserver serves) and merge it
   into the same collected tree, and only then start
   `manage.py runserver --noreload --insecure` on the PR's port. A failing
   gate records status `failed` with the failure message and never starts the
   server; a missing art directory warns and builds the CSS-cards
   environment, while a copy error fails the build.
7. Publish one PR comment per newly built push: the ready URL plus a
   diff-derived "what to play and look at" note, or a failure note without an
   environment URL.
8. Rewrite the proxy route map from all `ready` environments.

## Capacity and lifecycle

- At most `MMM_PR_MAX_RUNNING` (default 3) PR environments run at once,
  production is separate.
- Capacity is made only when a new environment needs a slot: the least
  recently active running environment is stopped, its checkout, database, and
  port are retained, and it is rebuildable on demand via `rebuild <pr>`.
- Merging or closing a PR stops nothing. Closed PR environments keep running
  and serving until capacity is needed elsewhere.
- Rebuilds happen on every push (a new head commit) and when a server process
  died; a failed or stopped environment with an unchanged head stays as is
  until pushed again or rebuilt on demand.

## Configuration

Django settings in `mysite/settings.py` are environment-parameterized with
local development defaults; unset variables behave exactly as before.

| Variable | Default | Used for |
| --- | --- | --- |
| `MMM_SECRET_KEY` | dev key in settings.py | per-environment secret |
| `MMM_DEBUG` | `true` | debug pages off in deployments |
| `MMM_ALLOWED_HOSTS` | empty | `pr-<n>.<domain>`, localhost |
| `MMM_CSRF_TRUSTED_ORIGINS` | empty | `https://pr-<n>.<domain>` |
| `MMM_SECURE_COOKIES` | `false` | `Secure` session + CSRF cookies |
| `MMM_DB_PATH` | `BASE_DIR/db.sqlite3` | per-PR database file |
| `MMM_STATIC_ROOT` | `BASE_DIR/staticfiles` | per-PR collected static tree |

The manager itself reads:

| Variable | Default |
| --- | --- |
| `MMM_PR_CANONICAL_REPO` | `LucasWillemsens/Megans-Magische-Meesters` |
| `MMM_PR_BASE_DOMAIN` | `paintedpillars.com` |
| `MMM_PR_PORT_START` | `8100` |
| `MMM_PR_MAX_RUNNING` | `3` |
| `MMM_PR_DEPLOYMENTS_DIR` | `<repo>/var/deployments` |
| `MMM_PR_EXTRA_STATIC` | `<repo>/assets/downloaded` |
| `MMM_PR_ORIGIN_URL` | the loop checkout's `origin` remote |

`MMM_PR_ORIGIN_URL` exists for smoke tests against a local mirror; production
use keeps the default, which is the canonical GitHub remote. PR cookies are
host-only because no cookie domain is ever set: `pr-12.paintedpillars.com`,
`pr-13.paintedpillars.com`, and `www.paintedpillars.com` never share a cookie.

## Runtime layout

```
var/deployments/
  state.json           # lifecycle, readiness, last-activity, rebuild metadata, per-PR secret keys
  build.lock           # serializes builds across sync invocations
  proxy_routes.json    # hostname -> port map for the reverse proxy
  routes.caddy         # generated Caddy site blocks importing into the main Caddyfile
  pr-<n>/
    repo/              # isolated checkout of the PR head
    staticfiles/       # per-PR collectstatic target beside the checkout, merged with the downloaded art
    db.sqlite3         # isolated, deterministically seeded database
    server.log         # runserver output; its mtime is the last-activity signal
```

## One-time routing setup

Production stays at `https://www.paintedpillars.com/` and PR environments sit
one level below at `pr-<n>.paintedpillars.com`. Public TLS ends at Cloudflare;
the proxy and Django see plain HTTP, so no per-PR certificate exists.

1. Caddy in WSL, listening on localhost:8080, with a main Caddyfile like:

   ```
   {
       admin off
       auto_https off
       http_port 8080
   }

   import /home/<user>/MMM/repo/var/deployments/routes.caddy

   http://www.paintedpillars.com {
       handle_path /static/* {
           root * /home/<user>/MMM/repo/var/deployments/production/staticfiles
           file_server
       }
       reverse_proxy 127.0.0.1:8000
   }
   ```

   The `www` block is production's — the deployment managed by
   `scripts/production.py` (see `scripts/production.md`); PR routes never
   touch it. The manager rewrites `routes.caddy` on every sync, so Caddy
   needs a reload only when routes change (`caddy reload --config <main
   Caddyfile>`, or run Caddy with `--watch`).

2. Cloudflare Tunnel (outbound, no port forwarding), one wildcard ingress, no
   per-PR changes ever:

   ```yaml
   tunnel: <tunnel-id>
   credentials-file: /home/<user>/.cloudflared/<tunnel-id>.json
   ingress:
     - hostname: "*.paintedpillars.com"
       service: http://localhost:8080
     - service: http_status:404
   ```

   Route the DNS once: an `A`/`CNAME` for `paintedpillars.com` and a proxied
   `*.paintedpillars.com` CNAME to `<tunnel-id>.cfargotunnel.com`
   (`cloudflared tunnel route dns <tunnel-id> paintedpillars.com` and the
   wildcard record in the Cloudflare dashboard). Cloudflare's Universal SSL
   certificate covers the apex and one-level subdomains, which is exactly the
   `pr-<n>` shape.

3. Secrets live outside the repository: the gh token in the user's profile,
   the tunnel credentials under `~/.cloudflared`, and the per-PR Django secret
   keys in gitignored `var/deployments/state.json`. The manager never prints
   secret values, and PR comments contain only the failure message line.

## Smoke test: Windows/WSL, proxy, and tunnel

Run this on the Windows machine inside the WSL workspace. Every step lists
what must be observed before moving on. Prerequisites: `gh auth status` is
authenticated, pushes to the canonical repo work, the host Python has Django
installed (the same interpreter the loop uses), Caddy and `cloudflared` are
installed in WSL.

1. **Local build.** With one open same-repository PR (create a throwaway PR
   with a trivial change if none exists), run
   `python3 scripts/pr_environments.py sync`. Expect a `ready` line with the
   environment URL and port, and a PR comment carrying the URL and play note.
   `python3 scripts/pr_environments.py status` lists the environment.
2. **Direct server.** `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:<port>/MMM/title/`
   must return 200 (the PR environment binds its own port; the bare `/`
   redirects to the game mount).
3. **Proxy routing.** `curl -s -H "Host: pr-<n>.paintedpillars.com" -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/MMM/title/`
   must return 200 through Caddy, served by the PR environment's port, while
   `curl -s -H "Host: www.paintedpillars.com" -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/MMM/title/`
   stays on production's block. No Caddy or tunnel change was made per PR.
4. **Tunnel end to end.** On a phone or another network, open
   `https://pr-<n>.paintedpillars.com/MMM/`: the title page renders with its
   downloaded background art (`/static/woodtextureorangedark2.jpg` returns
   200), static CSS and JS load, and starting the demo battle works. In the
   browser devtools the `sessionid` Set-Cookie has no `Domain` attribute and
   carries `Secure`.
   `https://www.paintedpillars.com/MMM/` (or its 502 while production is absent)
   is unaffected by PR environments.
5. **Isolation.** Open a second PR and sync. `status` shows two distinct
   ports; `var/deployments/pr-<a>/db.sqlite3` and `pr-<b>/db.sqlite3` are two
   files. Play both in separate tabs: each tab has its own host-only session
   cookie and its own seeded database; a move in one environment does not
   appear in the other.
6. **Push rebuild.** Push a new commit to the first PR and sync. Expect a
   rebuild (gates re-run), a fresh PR comment naming the new commit, and the
   same URL serving the new head. The database stays with that environment.
7. **Capacity and on-demand rebuild.** With three environments ready, sync a
   fourth PR. Expect one line stopping the least recently active environment,
   the fourth PR `ready`, and the stopped one still listed with its port,
   checkout, and database intact. Run
   `python3 scripts/pr_environments.py rebuild <stopped-pr>`: it evicts
   whoever is now least recently active and brings the stopped environment
   back up.
8. **Merge/close retention.** Merge or close any PR and sync. Its environment
   stays `ready`, still routed, still playable; nothing is torn down.
9. **Fork safety.** From a second GitHub account, open a fork PR against the
   repository and sync. Expect a `rejected` line, no `var/deployments/pr-<n>/`
   directory for it, no gate output for it, and no PR comment. Its code was
   never fetched, checked out, or executed.
10. **Failure visibility.** Push a commit with a failing test to an eligible
    PR and sync. Expect status `failed` with the failing gate message, no
    running server on that port, no route in `proxy_routes.json`, and a PR
    comment that says the build failed and publishes no environment URL. Fix
    and push: the next sync rebuilds and publishes the ready URL again.
11. **Production safety.** Throughout, the Windows production checkout and its
    SQLite database are untouched: PR databases live only under
    `var/deployments/pr-<n>/`, and the manager never references the
    production paths.

## Limitations

- Environments are served by `runserver --noreload --insecure`. That is
  single-host, loop-owned serving of a test environment; production serving is
  a separate concern.
- `assets/downloaded/` is untracked, so a fresh PR checkout does not contain
  it. Every build therefore copies the working repository's downloaded art
  (`MMM_PR_EXTRA_STATIC`) into the checkout's `assets/downloaded/`, which
  runserver serves through its static finders, and merges it into
  `pr-<n>/staticfiles/`, which `git clean -fdx` cannot touch. When the art
  directory is absent the build warns and the 52 seeded CSS playing cards
  render instead.
- A PR whose head predates the settings parameterization (old branches) does
  not read `MMM_DB_PATH` or `MMM_STATIC_ROOT`: such an environment keeps its
  database inside its own checkout and collects static into it as well. It is
  still fully isolated per PR, and `git clean` on the next rebuild resets both
  to a freshly seeded state, which matches the "seeded fresh" rule. The art
  copies still land in the checkout and in `pr-<n>/staticfiles/`; whether
  that revision serves them depends on its own static configuration.
- A recorded pid is verified against `/proc/<pid>/cmdline` before any signal
  is sent, so a reused pid after a host reboot is never killed; the stale
  environment is simply rebuilt on the next sync.
- The manager is Linux/WSL-only (`fcntl`, `/proc`).
