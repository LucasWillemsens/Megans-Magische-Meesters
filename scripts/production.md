# Production deployment

`scripts/production.py` is the on-demand production deployment manager for
https://www.paintedpillars.com/. It builds `var/deployments/production/`
from the canonical repository's `main` branch and serves it on port 8000
through gunicorn, with the same gate philosophy as the per-PR environments:
`manage.py migrate`, `add_deck_cards`, `manage.py check`, `manage.py test`,
and `manage.py collectstatic --noinput` must all pass before the server
process is swapped. A failing gate aborts the deploy, records the failure
in `state.json`, and leaves the currently running server untouched.

The game itself is mounted at `/MMM/` in the URLconf — identical to local
development and the PR environments — so production serves the title page at
`https://www.paintedpillars.com/MMM/title/` and its APIs under
`/MMM/api/...`. The band site owns the domain root, and the allauth account
routes (Google sign-in, sign out) are served below `/accounts/`.

Everything under `var/deployments/` is gitignored runtime state and must
never be committed. The manager never writes the working repository and
never touches its `db.sqlite3`: every gate and the server itself run from
the isolated checkout under `production/repo/` against
`production/db.sqlite3`. Beyond resolving its `origin` remote, the only
thing the manager reads from the working repository is the downloaded-art
directory it copies into the static tree.

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
2. Load the deployment configuration from `production/env.json`: the Django
   secret key, generated once when the file is missing, and the optional
   Google OAuth client credentials (see the Google sign-in section below).
   Neither is ever printed or committed.
3. Ensure the host Python has `django-allauth` — installed on demand by pip
   when the import fails, exactly like gunicorn. Note that
   `django-allauth` requires a current Django, so the install may upgrade
   a host Django older than 4.2.16.
4. Run the gates in order with the production environment below:
   `manage.py migrate` → `manage.py add_deck_cards` (an idempotent seed: it
   refreshes Lucas's 52 cards and creates only what is missing) →
   `manage.py check` → `manage.py test` (Django's test runner uses a
   throwaway test database, never `production/db.sqlite3`) →
   `manage.py collectstatic --noinput`, which builds the served static
   tree in `production/staticfiles/` (see the static tree section below).
   A failing gate records `failure` in `state.json` and aborts before
   anything is stopped, so the old server keeps serving and no broken
   static tree is ever swapped in.
5. Copy the contents of `MMM_PRODUCTION_EXTRA_STATIC` (default: the
   working repository's `assets/downloaded/`) into
   `production/staticfiles/`. That directory is gitignored, so it never
   exists inside the checkout — this step injects the downloaded card art
   without polluting the checkout. A missing directory only warns in the
   deploy output; the deploy continues without the extra art.
6. Install gunicorn with pip when `python3 -c "import gunicorn"` fails.
7. Stop the old server and start
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
| `MMM_STATIC_ROOT` | `production/staticfiles` |
| `MMM_GOOGLE_CLIENT_ID` | from `production/env.json`, only when stored |
| `MMM_GOOGLE_CLIENT_SECRET` | from `production/env.json`, only when stored |

Without stored Google credentials a deploy still completes — it prints a
warning and serves the site with Google sign-in unconfigured (the login
page renders; the Google hop fails) until the credentials are added.

Public TLS ends at Cloudflare while the Django process behind Caddy sees
plain HTTP, so allauth builds its OAuth callback URI with the public
scheme: `MMM_ACCOUNT_HTTP_PROTOCOL` defaults to `https` and needs no
override in production (or on the PR hosts, which are also served through
Cloudflare TLS).

## Google sign-in and the admin account

Signing in runs through django-allauth's Google provider, served at
`https://www.paintedpillars.com/accounts/login/` and linked from the band
contact page. Accounts are Google-only: local signups and password logins
are switched off (`SOCIALACCOUNT_ONLY`). The one account that may open the
game's admin pages is the one whose verified email is `paintedpillars@gmail.com`
(`MMM_ADMIN_EMAIL`, default that address); every other signed-in account is
denied there, server-side.

Configuration, once per host:

1. **OAuth client.** Using the `paintedpillars@gmail.com` Google account,
   create an OAuth client in Google Cloud (APIs & Services → Credentials)
   and add the production callback URI to its authorized redirect URIs:
   `https://www.paintedpillars.com/accounts/google/login/callback/`.
2. **Credential injection.** Store the resulting client ID and secret in
   `production/env.json` — the same gitignored file that holds the Django
   secret key — and deploy:

   ```json
   {
     "secret_key": "...",
     "google_client_id": "<client id>.apps.googleusercontent.com",
     "google_client_secret": "<client secret>"
   }
   ```

   The manager reads them on every deploy, passes them to the gates and
   the server as `MMM_GOOGLE_CLIENT_ID` / `MMM_GOOGLE_CLIENT_SECRET`, and
   never prints them. They are never committed and never generated.

3. **One-time player link.** The admin account plays as the existing
   `lucas` player. Linking is a controlled operation against
   `production/db.sqlite3` — no web form can create or claim a link. Sign
   in once with `paintedpillars@gmail.com` through the contact page's
   login link (the first sign-in creates the account), then from the
   production checkout run:

   ```
   cd var/deployments/production/repo
   env \
     MMM_SECRET_KEY="$(python3 -c "import json; print(json.load(open('../env.json'))['secret_key'])')" \
     MMM_DEBUG=false \
     MMM_ALLOWED_HOSTS=www.paintedpillars.com \
     MMM_CSRF_TRUSTED_ORIGINS=https://www.paintedpillars.com \
     MMM_SECURE_COOKIES=true \
     MMM_DB_PATH="$(cd .. && pwd)/db.sqlite3" \
     MMM_STATIC_ROOT="$(cd .. && pwd)/staticfiles" \
     python3 manage.py link_account paintedpillars@gmail.com lucas
   ```

   The command links the existing player, never creates a duplicate, and
   reports or refuses clearly: an account that has not signed in yet, an
   unknown player name, or either side of the one-to-one link already
   being taken are all refused. Re-running it after a successful link is
   safe and reports that the link exists.

4. **Verification.** Open `https://www.paintedpillars.com/MMM/admin/`
   signed in as `paintedpillars@gmail.com`: the page must list the players
   (including Lucas) and the band navigation must show the Admin entry.
   Signed out, the same URL must redirect to the login; any other signed-in
   account must get HTTP 403 and see no Admin entry.

**Which environments can exercise live Google sign-in.** Production (after
step 2) and a local checkout: for local development, add
`http://127.0.0.1:8000/accounts/google/login/callback/` to the OAuth
client's authorized redirect URIs (Google accepts plain http only for
loopback addresses) and export
`MMM_GOOGLE_CLIENT_ID` / `MMM_GOOGLE_CLIENT_SECRET` and
`MMM_ACCOUNT_HTTP_PROTOCOL=http` before `python3 manage.py runserver`
(the default `https` matches the Cloudflare-fronted production and PR
hosts, not a local runserver). The per-PR environments deliberately never
receive the OAuth credentials — their checkouts run unmerged code — so
their login pages render with Google sign-in unconfigured; the
automated tests (gate `manage.py test`) cover the account flows without
real credentials.

## Database and secret persistence

`production/db.sqlite3` survives every rebuild: the checkout reset and
`git clean` never leave `production/repo/`, and no code path deletes the
database. Migrations are applied to it on every deploy and
`add_deck_cards` only adds or refreshes the seed cards, so deploying never
loses game state. The secret key likewise persists in
`production/env.json`, so sessions survive deploys; the Google OAuth
credentials stored in the same file persist with it.

## The static tree

`mysite/settings.py` parameterizes `STATIC_ROOT` over `MMM_STATIC_ROOT`
(default: `staticfiles/` beside the repository root, which is gitignored);
the deploy passes `production/staticfiles/`, so the collectstatic gate
builds the served tree beside the database and the secret key, never
inside `repo/`. The checkout reset and `git clean` can never touch it, and
its contents are regenerated by every deploy. Under the same
`/static/...` URLs the site already uses, the tree holds:

- `MMM/static/MMM/` — tracked app static (`profile.jpg` and the other app
  images), collected into `staticfiles/MMM/` by Django's app finder;
- `var/www/static/` — the board's tracked CSS/JS, collected into the root
  of the tree;
- `assets/downloaded/` — the gitignored downloaded card art, which a fresh
  checkout never contains. collectstatic simply skips the missing
  directory (`manage.py check` warns `staticfiles.W004` for it without
  failing the gate), and the copy step after the gate injects the art from
  `MMM_PRODUCTION_EXTRA_STATIC`.

Gunicorn itself serves no static files with `DEBUG=false`:
`mysite/urls.py` registers no static URL pattern and the middleware stack
has no whitenoise, so every `/static/...` request that reaches gunicorn
returns 404. Serving the tree is Caddy's job: its `file_server` block must
point its root at `production/staticfiles/` (configured outside this
manager). Until that root is repointed, pages deploy and render but
`/static/...` URLs keep 404ing.

## Configuration

| Variable | Default |
| --- | --- |
| `MMM_PRODUCTION_ORIGIN_URL` | the working repository's `origin` remote (`git@github.com:LucasWillemsens/Megans-Magische-Meesters.git`) |
| `MMM_PRODUCTION_HOSTNAME` | `www.paintedpillars.com` |
| `MMM_PRODUCTION_PORT` | `8000` |
| `MMM_PRODUCTION_BRANCH` | `main` |
| `MMM_PRODUCTION_DEPLOYMENTS_DIR` | `<repo>/var/deployments` |
| `MMM_PRODUCTION_EXTRA_STATIC` | `<repo>/assets/downloaded` |

`MMM_PRODUCTION_ORIGIN_URL` exists for smoke tests against a local mirror.
`MMM_PRODUCTION_EXTRA_STATIC` names the directory whose contents are
copied into `production/staticfiles/` after the collectstatic gate; the
default is the working repository's gitignored downloaded art.

## Runtime layout

```
var/deployments/production/
  repo/            # checkout of main, reset on every deploy
  db.sqlite3       # production database; survives rebuilds
  staticfiles/     # the collected static tree, regenerated on every deploy
  env.json         # the Django secret key and the optional Google OAuth credentials
  state.json       # status, head sha, pid, port, gate failures, built_at
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
has Django installed, and pip can install gunicorn (and installs
`django-allauth` on demand the same way).

1. **Mirror.** `git clone --bare <working repo> /tmp/opencode/mmm-mirror.git`
   and note the head sha of `main` (`git rev-parse main`). The mirror holds
   committed state only, so the working repository's untracked files and
   `db.sqlite3` are never part of it.
2. **Deploy.**
   `MMM_PRODUCTION_ORIGIN_URL=/tmp/opencode/mmm-mirror.git MMM_PRODUCTION_PORT=8200 MMM_PRODUCTION_DEPLOYMENTS_DIR=/tmp/opencode/production-smoke python3 scripts/production.py deploy`.
   Expect a `ready` line with the mirror's sha; `status` shows
   `production: ready`, the sha, the deploy time, and `pid ..., running`;
   `production/env.json` exists; the working repository's `db.sqlite3` is
   untouched. The deploy output warns that no Google OAuth credentials are
   in `env.json` — expected for a mirror without them.
3. **Serving and the static tree.**
   `curl -s -H "Host: www.paintedpillars.com" -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8200/`
   must return 302 (the bare root redirects to the game mount), and
   `curl -sL -H "Host: www.paintedpillars.com" -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8200/MMM/`
   must follow it to the title page and return 200 (the `Host` header is
   required because `MMM_ALLOWED_HOSTS` holds only `www.paintedpillars.com`).
   `production/staticfiles/` must hold the collected tree: `MMM/profile.jpg`
   from the app static, `cards.css` from `var/www/static/`, and the
   downloaded art from the working repository's `assets/downloaded/` — or
   the deploy output warns `extra static files not found` when
   `MMM_PRODUCTION_EXTRA_STATIC` points nowhere. `/static/...` URLs still
   return 404 under gunicorn directly: the tree is served by Caddy's
   `file_server` block, which this smoke test does not include.
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
