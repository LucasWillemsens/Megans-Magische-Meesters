#!/usr/bin/env python3
"""Production deployment manager for Megans Magische Meesters.

Serves www.paintedpillars.com from var/deployments/production/, a checkout of
the canonical repository's main branch, on port 8000 through gunicorn. Every
deploy is gated by migrate, the deck seed, manage.py check, manage.py test,
and collectstatic; a failing gate aborts before the running server is
touched and records the failure in state.json. The collectstatic gate builds
the served static tree in production/staticfiles/ from the checkout, and the
working repository's gitignored downloaded art (MMM_PRODUCTION_EXTRA_STATIC)
is copied in after it, so the tree never depends on untracked files inside
the checkout. The production database and the Django secret key live beside
the checkout, never inside it, so both survive every rebuild. The manager
never writes the working repository and never touches its db.sqlite3;
beyond resolving its origin remote it only reads from the extra static
directory.

Usage:
    python3 scripts/production.py deploy [--force]
    python3 scripts/production.py status
    python3 scripts/production.py stop
"""

import argparse
import fcntl
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENTS_DIR = Path(os.environ.get("MMM_PRODUCTION_DEPLOYMENTS_DIR", REPO_ROOT / "var" / "deployments"))
PRODUCTION_HOSTNAME = os.environ.get("MMM_PRODUCTION_HOSTNAME", "www.paintedpillars.com")
PRODUCTION_PORT = int(os.environ.get("MMM_PRODUCTION_PORT", "8000"))
PRODUCTION_BRANCH = os.environ.get("MMM_PRODUCTION_BRANCH", "main")
EXTRA_STATIC_DIR = Path(os.environ.get("MMM_PRODUCTION_EXTRA_STATIC", REPO_ROOT / "assets" / "downloaded"))

GATES = (
    ("manage.py", "migrate"),
    ("manage.py", "add_deck_cards"),
    ("manage.py", "check"),
    ("manage.py", "test"),
    ("manage.py", "collectstatic", "--noinput"),
)
GUNICORN_APPLICATION = "mysite.wsgi:application"


class BuildFailure(Exception):
    """A checkout or gate step failed; the message is safe to record."""


def production_directory():
    return DEPLOYMENTS_DIR / "production"


def production_checkout():
    return production_directory() / "repo"


def production_database():
    return production_directory() / "db.sqlite3"


def production_static_root():
    return production_directory() / "staticfiles"


def production_log_path():
    return production_directory() / "server.log"


def production_env_path():
    return production_directory() / "env.json"


def production_state_path():
    return production_directory() / "state.json"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def short_sha(sha):
    return (sha or "")[:7]


def output_tail(text, limit=2000):
    return text.strip()[-limit:]


def new_deployment_entry():
    return {
        "status": None,
        "pid": None,
        "port": None,
        "head_sha": None,
        "failure": None,
        "built_at": None,
    }


def load_state():
    state_path = production_state_path()
    if not state_path.exists():
        return {"deployment": new_deployment_entry()}
    return json.loads(state_path.read_text())


def save_state(state):
    production_directory().mkdir(parents=True, exist_ok=True)
    temp_path = production_state_path().with_name("state.json.tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    temp_path.replace(production_state_path())


@contextmanager
def deploy_lock():
    production_directory().mkdir(parents=True, exist_ok=True)
    lock_handle = open(production_directory() / "deploy.lock", "w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()


def run_command(command, cwd, env=None):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def origin_url():
    configured = os.environ.get("MMM_PRODUCTION_ORIGIN_URL")
    if configured:
        return configured
    exit_status, output = run_command(("git", "remote", "get-url", "origin"), cwd=REPO_ROOT)
    if exit_status:
        raise RuntimeError("could not read the origin remote URL of the working repository")
    return output.strip()


def main_head_sha():
    url = origin_url()
    exit_status, output = run_command(
        ("git", "ls-remote", url, f"refs/heads/{PRODUCTION_BRANCH}"), cwd=REPO_ROOT
    )
    if exit_status:
        raise RuntimeError(f"git ls-remote against {url} failed; cannot resolve {PRODUCTION_BRANCH}")
    head_sha = output.partition("\t")[0].strip()
    if not head_sha:
        raise RuntimeError(f"refs/heads/{PRODUCTION_BRANCH} not found on {url}")
    return head_sha


def git_in_checkout(command, checkout):
    exit_status, output = run_command(("git", *command), cwd=checkout)
    if exit_status:
        raise BuildFailure(f"git {' '.join(command)} failed with exit status {exit_status}\n{output_tail(output)}")


def update_checkout(checkout):
    if not (checkout / ".git").exists():
        exit_status, output = run_command(("git", "clone", origin_url(), str(checkout)), cwd=DEPLOYMENTS_DIR)
        if exit_status:
            raise BuildFailure(f"git clone failed with exit status {exit_status}\n{output_tail(output)}")
    git_in_checkout(("fetch", "origin", PRODUCTION_BRANCH), checkout)
    git_in_checkout(("reset", "--hard", "FETCH_HEAD"), checkout)
    git_in_checkout(("clean", "-fdx"), checkout)


def load_or_create_secret_key():
    """The production secret key is generated once into gitignored env.json
    beside the database and reused by every later deploy, so sessions
    survive rebuilds; it is never printed."""
    env_path = production_env_path()
    if env_path.exists():
        secret_key = json.loads(env_path.read_text()).get("secret_key")
        if secret_key:
            return secret_key
    env_path.parent.mkdir(parents=True, exist_ok=True)
    secret_key = secrets.token_urlsafe(50)
    temp_path = env_path.with_name("env.json.tmp")
    temp_path.write_text(json.dumps({"secret_key": secret_key}, indent=2) + "\n")
    temp_path.replace(env_path)
    return secret_key


def deployment_environment(secret_key):
    return {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "mysite.settings",
        "MMM_SECRET_KEY": secret_key,
        "MMM_DEBUG": "false",
        "MMM_ALLOWED_HOSTS": PRODUCTION_HOSTNAME,
        "MMM_CSRF_TRUSTED_ORIGINS": f"https://{PRODUCTION_HOSTNAME}",
        "MMM_SECURE_COOKIES": "true",
        "MMM_DB_PATH": str(production_database()),
        "MMM_STATIC_ROOT": str(production_static_root()),
    }


def process_command_line(pid):
    command_file = Path(f"/proc/{pid}/cmdline")
    if not command_file.exists():
        return None
    return command_file.read_bytes().decode(errors="replace")


def process_working_directory(pid):
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return None


def production_server_running(entry):
    """A recorded pid counts as the production server only while /proc still
    shows a gunicorn process bound to the production port and working out of
    the production checkout; gunicorn's command line never names the
    checkout, so the working directory is what ties the pid to it. An
    unreadable /proc entry fails closed, so a reused pid is never mistaken
    for the server and never signaled."""
    pid = entry.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    command = process_command_line(pid)
    if command is None:
        return False
    return (
        "gunicorn" in command
        and str(PRODUCTION_PORT) in command
        and process_working_directory(pid) == str(production_checkout())
    )


def ensure_gunicorn():
    exit_status, _ = run_command((sys.executable, "-c", "import gunicorn"), cwd=REPO_ROOT)
    if not exit_status:
        return
    exit_status, output = run_command((sys.executable, "-m", "pip", "install", "gunicorn"), cwd=REPO_ROOT)
    if exit_status:
        raise BuildFailure(f"pip install gunicorn failed with exit status {exit_status}\n{output_tail(output)}")


def start_server(secret_key):
    log_handle = open(production_log_path(), "ab")
    try:
        process = subprocess.Popen(
            (
                sys.executable, "-m", "gunicorn",
                "--bind", f"0.0.0.0:{PRODUCTION_PORT}",
                GUNICORN_APPLICATION,
            ),
            cwd=production_checkout(),
            env=deployment_environment(secret_key),
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
        )
    finally:
        log_handle.close()
    return process.pid


def stop_server(entry):
    pid = entry.get("pid")
    if not pid or not production_server_running(entry):
        entry["pid"] = None
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        if not production_server_running(entry):
            break
        time.sleep(0.1)
    if production_server_running(entry):
        os.kill(pid, signal.SIGKILL)
    entry["pid"] = None


def deploy_production(state, head_sha):
    """Rebuild production from main's current head and swap the gunicorn
    process only after every gate passes; a failing gate records the failure
    and leaves the running server untouched."""
    entry = state.setdefault("deployment", new_deployment_entry())
    entry.update(status="building", head_sha=head_sha, failure=None)
    entry.pop("static_failure", None)
    if not entry.get("port"):
        entry["port"] = PRODUCTION_PORT
    save_state(state)
    checkout = production_checkout()
    try:
        update_checkout(checkout)
        secret_key = load_or_create_secret_key()
        gate_environment = deployment_environment(secret_key)
        for command in GATES:
            exit_status, output = run_command((sys.executable, *command), cwd=checkout, env=gate_environment)
            if exit_status:
                raise BuildFailure(f"{command[1]} failed with exit status {exit_status}\n{output_tail(output)}")
        if not EXTRA_STATIC_DIR.is_dir():
            print(f"production: extra static files not found at {EXTRA_STATIC_DIR}; deploying without them")
        else:
            try:
                shutil.copytree(EXTRA_STATIC_DIR, production_static_root(), dirs_exist_ok=True)
            except OSError as error:
                raise BuildFailure(f"copying extra static files from {EXTRA_STATIC_DIR} failed\n{error}") from error
        ensure_gunicorn()
        stop_server(entry)
        entry.update(status="ready", built_at=utc_now_iso(), pid=start_server(secret_key))
        time.sleep(1)
        if not production_server_running(entry):
            entry["pid"] = None
            raise BuildFailure(f"gunicorn on port {entry['port']} exited during startup")
        print(f"production: ready from {short_sha(head_sha)} on port {entry['port']}")
    except BuildFailure as failure:
        entry.update(status="failed", failure=str(failure))
        print(f"production: deploy failed; {str(failure).splitlines()[0]}")
    save_state(state)
    return entry


def deploy_command(force):
    with deploy_lock():
        state = load_state()
        entry = state.get("deployment")
        head_sha = main_head_sha()
        if (
            not force
            and entry is not None
            and entry.get("status") == "ready"
            and entry.get("head_sha") == head_sha
            and production_server_running(entry)
        ):
            print(
                f"production: already serving {short_sha(head_sha)} on port {entry.get('port')}; "
                "deploy again with --force to rebuild"
            )
            return 0
        entry = deploy_production(state, head_sha)
    return 0 if entry.get("status") == "ready" else 1


def status_lines(state):
    entry = state.get("deployment") or new_deployment_entry()
    parts = [f"production: {entry.get('status') or 'undeployed'}"]
    if entry.get("port"):
        parts.append(f"port {entry['port']}")
    if entry.get("head_sha"):
        parts.append(short_sha(entry["head_sha"]))
    if entry.get("built_at"):
        parts.append(f"deployed {entry['built_at']}")
    if entry.get("pid"):
        parts.append(f"pid {entry['pid']}, " + ("running" if production_server_running(entry) else "not running"))
    if entry.get("failure"):
        parts.append(entry["failure"].splitlines()[0])
    return [" | ".join(parts)]


def status_command():
    print("\n".join(status_lines(load_state())))
    return 0


def stop_command():
    with deploy_lock():
        state = load_state()
        entry = state.setdefault("deployment", new_deployment_entry())
        stop_server(entry)
        entry["status"] = "stopped"
        save_state(state)
        print("production: stopped; checkout, database, and secret key retained for the next deploy")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Manage the production deployment of Megans Magische Meesters"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    deploy_parser = subparsers.add_parser(
        "deploy", help="rebuild production from main and swap the server when every gate passes"
    )
    deploy_parser.add_argument(
        "--force", action="store_true", help="rebuild even when main's head is already deployed and serving"
    )
    subparsers.add_parser("status", help="show the production deployment state")
    subparsers.add_parser("stop", help="stop the production gunicorn process")
    args = parser.parse_args(argv)
    DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    command_functions = {
        "deploy": lambda: deploy_command(force=args.force),
        "status": status_command,
        "stop": stop_command,
    }
    try:
        return command_functions[args.command]()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
