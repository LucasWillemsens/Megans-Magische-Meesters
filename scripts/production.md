# Production deployment

`scripts/production.py` is the on-demand production deployment manager for
https://www.paintedpillars.com/. It builds `var/deployments/production/`
from the canonical repository's `main` branch and serves it on port 8000
through gunicorn, with the same gate philosophy as the per-PR environments:
`manage.py migrate`, `add_deck_cards`, `manage.py check`, and
`manage.py test` must all pass before the server process is swapped. A
failing gate aborts the deploy, records the failure in `state.json`, and
leaves the currently running server untouched.

Everything under `var/deployments/` is gitignored runtime state and must
never be committed. The manager never reads or writes the working
repository beyond resolving its `origin` remote, and it never touches the
working repository's `db.sqlite3`: every gate and the server itself run
from the isolated checkout under `production/repo/` against
`production/db.sqlite3`.

## Commands

```
python3 scripts/production.py deploy [--force]   # fetch main, run gates, swap the server
python3 scripts/production.py status             # head commit, deploy time, pid/port, failures
python3 scripts/production.py stop               # stop the gunicorn process
```

Deploys are serialized by `production/deploy.lock`, independently of the PR
manager's `build.lock`, so a production deploy never waits behind PR builds
and vice versa; the two managers share no files.

`deploy` resolves `main`'s head with `git ls-remote` against the origin
remote and skips the rebuild when that head is already deployed and
serving, unless `--force` is passed. A recorded-but-dead server with an
unchanged head is rebuilt rather than skipped.

## One deploy, in order

1. Clone `origin` into `production/repo/` when missing; otherwise
   `git fetch origin main`, `git reset --hard FETCH_HEAD`, and
   `git clean -fdx`. Only the checkout is reset; the database, secret key,
   and state live beside it, never inside it.
2. Load the Django secret key from `production/env.json`, generating it
   once when the file is missing. It is never printed and never committed.
3. Run the gates in order with the production environment below:
   `manage.py migrate` → `manage.py add_deck_cards` (an idempotent seed: it
   refreshes Lucas's 52 cards and creates only what is missing) →
   `manage.py check` → `manage.py test` (Django's test runner uses a
   throwaway test database, never `production/db.sqlite3`). A failing gate
   records `failure` in `state.json` and aborts before anything is
   stopped, so the old server keeps serving.
4. Run `manage.py collectstatic --noinput`. Its failure is recorded as
   `static_failure` and shown by `status`; it is not a gate — see the
   known finding below.
5. Install gunicorn with pip when `python3 -c "import gunicorn"` fails.
6. Stop the old server and start
   `python3 -m gunicorn --bind 0.0.0.0:8000 mysite.wsgi:application` from
   the checkout, logging to `production/server.log`. A startup failure is
   recorded and production is then down until the next deploy — there is no
   second server to fall back to.

## Production environment

`mysite/settings.py` is environment-parameterized; the gates and the
server process run with:

| Variable | Value |
| --- | --- |
| `MMM_SECRET_KEY` | generated once, stored in `production/env.json` |
| `MMM_DEBUG` | `false` |
| `MMM_ALLOWED_HOSTS` | `www.paintedpillars.com` |
| `MMM_CSRF_TRUSTED_ORIGINS` | `https://www.paintedpillars.com` |
| `MMM_SECURE_COOKIES` | `true` |
| `MMM_DB_PATH` | `production/db.sqlite3` |

## Database and secret persistence

`production/db.sqlite3` survives every rebuild: the checkout reset and
`git clean` never leave `production/repo/`, and no code path deletes the
database. Migrations are applied to it on every deploy and
`add_deck_cards` only adds or refreshes the seed cards, so deploying never
loses game state. The secret key likewise persists in
`production/env.json`, so sessions survive deploys.

## Known finding: static files with DEBUG=false

The app currently cannot serve or even collect static files with
`DEBUG=false`:

- `mysite/settings.py` sets no `STATIC_ROOT`, so
  `manage.py collectstatic --noinput` fails outright with
  `ImproperlyConfigured: You're using the staticfiles app without having
  set the STATIC_ROOT setting to a filesystem path.`
- With `DEBUG=false`, Django serves static files only through
  `runserver --insecure` (what the PR environments use); gunicorn has no
  equivalent. `mysite/urls.py` registers no static URL pattern, the
  middleware stack has no whitenoise, and no `STORAGES`/staticfiles
  storage is configured, so every `/static/...` request under gunicorn
  returns 404.

Until the settings gain a `STATIC_ROOT` plus a serving strategy (whitenoise,
or a Caddy `file_server` block for the collected directory — Caddy is
configured outside this manager), deploys complete and serve pages, and
`status` reports the `collectstatic` failure. `assets/downloaded/` is also
untracked, so a fresh production checkout does not contain it; copy it in
by hand when production needs the downloaded card art.

## Configuration

| Variable | Default |
| --- | --- |
| `MMM_PRODUCTION_ORIGIN_URL` | the working repository's `origin` remote (`git@github.com:LucasWillemsens/Megans-Magische-Meesters.git`) |
| `MMM_PRODUCTION_HOSTNAME` | `www.paintedpillars.com` |
| `MMM_PRODUCTION_PORT` | `8000` |
| `MMM_PRODUCTION_BRANCH` | `main` |
| `MMM_PRODUCTION_DEPLOYMENTS_DIR` | `<repo>/var/deployments` |

`MMM_PRODUCTION_ORIGIN_URL` exists for smoke tests against a local mirror.

## Runtime layout

```
var/deployments/production/
  repo/            # checkout of main, reset on every deploy
  db.sqlite3       # production database; survives rebuilds
  env.json         # the Django secret key, generated once
  state.json       # status, head sha, pid, port, gate and static failures, built_at
  server.log       # gunicorn output, appended across restarts
  deploy.lock      # serializes deploys
```

## Stopping and pid safety

`stop` (and every swap during `deploy`) signals only a pid that still
verifies as the production server: `/proc/<pid>/cmdline` must contain
`gunicorn` and the production port, and `/proc/<pid>/cwd` must be the
production checkout — gunicorn's command line never names the checkout, so
the working directory is what ties the pid to it. An unreadable or
mismatched `/proc` entry fails closed, so a reused pid after a host reboot
is never signaled; the stale entry is simply replaced by the next deploy.

`stop` marks the deployment `stopped` and keeps the checkout, database,
secret key, and port for the next `deploy`.

## Smoke test: local mirror

Run without touching GitHub or port 8000. Prerequisites: the host Python
has Django installed, and pip can install gunicorn.

1. **Mirror.** `git clone --bare <working repo> /tmp/opencode/mmm-mirror.git`
   and note the head sha of `main` (`git rev-parse main`). The mirror holds
   committed state only, so the working repository's untracked files and
   `db.sqlite3` are never part of it.
2. **Deploy.**
   `MMM_PRODUCTION_ORIGIN_URL=/tmp/opencode/mmm-mirror.git MMM_PRODUCTION_PORT=8200 MMM_PRODUCTION_DEPLOYMENTS_DIR=/tmp/opencode/production-smoke python3 scripts/production.py deploy`.
   Expect a `ready` line with the mirror's sha; `status` shows
   `production: ready`, the sha, the deploy time, and `pid ..., running`;
   `production/env.json` exists; the working repository's `db.sqlite3` is
   untouched.
3. **Serving.**
   `curl -s -H "Host: www.paintedpillars.com" -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8200/`
   must return 200 (the `Host` header is required because
   `MMM_ALLOWED_HOSTS` holds only `www.paintedpillars.com`).
   `/static/...` URLs return 404 while the static finding above is open.
4. **Skip.** Deploy again with the same head: expect `already serving`, no
   rebuild, and no new gate output. Add `--force`: the gates re-run and the
   server is swapped.
5. **Persistence.** Push a new commit to the mirror's `main` and deploy:
   the deploy re-fetches, `production/db.sqlite3` keeps its content,
   `production/env.json` keeps the same secret key, and sessions survive.
6. **Gate failure.** Push a failing change to the mirror's `main` and
   deploy: `status` becomes `failed` with the failing gate message, the
   previously recorded pid keeps serving 200s untouched, and no swap
   happened. Fix the mirror's `main` and deploy again: `ready` returns.
7. **Stop.** `python3 scripts/production.py stop` with the same env vars:
   the curl now fails to connect, `status` shows `stopped`, and the
   database, secret key, and checkout remain for the next deploy.

## Limitations

- Gunicorn runs with its defaults: one worker, no timeout tuning. SQLite
  and a small site make one worker the safe choice; revisit before
  scaling.
- The old server keeps serving while the new checkout is fetched and
  gated, so for the build's duration it serves its loaded Python code but
  the checkout's current templates; a failed gate leaves the checkout at
  the failed head until the next deploy re-fetches. Gates also run against
  the production database while the old server still serves, which holds
  brief SQLite write locks during migration — fine at this site's scale.
- A single gunicorn process means the swap has a stop-then-start gap;
  there is no blue/green pair.
- The manager is Linux/WSL-only (`fcntl`, `/proc`).
