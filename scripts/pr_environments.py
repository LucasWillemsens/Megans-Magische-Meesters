#!/usr/bin/env python3
"""Loop-owned per-PR test-environment manager for Megans Magische Meesters.

Each open pull request whose head repository is the configured canonical
repository gets its own checkout, SQLite database, and runtime port under
var/deployments/, gated by migrate, a deterministic seed, manage.py check,
and manage.py test. Pull requests from any other repository (forks) are
recorded as rejected before their code is ever checked out or executed, so
no GitHub runner or fork code ever runs on this host.

The loop calls `sync` periodically; every push (new head commit) rebuilds
that PR's environment. Builds are serialized by a file lock, results are
published as PR comments, and routing data for one shared reverse proxy is
rewritten on every sync so no tunnel or proxy change is ever needed per PR.

Usage:
    python3 scripts/pr_environments.py sync
    python3 scripts/pr_environments.py status
    python3 scripts/pr_environments.py rebuild <pr-number>
    python3 scripts/pr_environments.py stop <pr-number>
"""

import argparse
import fcntl
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_REPO = os.environ.get("MMM_PR_CANONICAL_REPO", "LucasWillemsens/Megans-Magische-Meesters")
BASE_DOMAIN = os.environ.get("MMM_PR_BASE_DOMAIN", "paintedpillars.com")
PORT_START = int(os.environ.get("MMM_PR_PORT_START", "8100"))
MAX_RUNNING_ENVIRONMENTS = int(os.environ.get("MMM_PR_MAX_RUNNING", "3"))
DEPLOYMENTS_DIR = Path(os.environ.get("MMM_PR_DEPLOYMENTS_DIR", REPO_ROOT / "var" / "deployments"))

PR_FIELDS = "number,title,url,headRefName,headRepositoryOwner,headRepository"
GATES = (
    ("manage.py", "migrate"),
    ("manage.py", "add_deck_cards"),
    ("manage.py", "check"),
    ("manage.py", "test"),
)


class BuildFailure(Exception):
    """A checkout or gate step failed; the message is safe to publish."""


def pr_hostname(number):
    return f"pr-{number}.{BASE_DOMAIN}"


def pr_directory(number):
    return DEPLOYMENTS_DIR / f"pr-{number}"


def pr_checkout(number):
    return pr_directory(number) / "repo"


def pr_database(number):
    return pr_directory(number) / "db.sqlite3"


def pr_log_path(number):
    return pr_directory(number) / "server.log"


def environment_url(number):
    return f"https://{pr_hostname(number)}/"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_mtime_utc_iso(path):
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")


def short_sha(sha):
    return (sha or "")[:7]


def output_tail(text, limit=2000):
    return text.strip()[-limit:]


def same_repository_identity(pull):
    owner = (pull.get("headRepositoryOwner") or {}).get("login")
    repository = (pull.get("headRepository") or {}).get("name")
    if not owner or not repository:
        return None
    return f"{owner}/{repository}"


def is_same_repository_pull(pull, canonical_repo):
    identity = same_repository_identity(pull)
    return identity is not None and identity.lower() == canonical_repo.lower()


def ready_environment_entries(state):
    return [entry for entry in state["environments"].values() if entry.get("status") == "ready"]


def allocate_port(state, port_start=PORT_START):
    used_ports = {entry["port"] for entry in state["environments"].values() if entry.get("port")}
    port = port_start
    while port in used_ports:
        port += 1
    return port


def least_recently_active_environment(state, protected_numbers):
    candidates = [
        entry for entry in ready_environment_entries(state)
        if entry["number"] not in protected_numbers
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda entry: entry.get("last_activity") or "")


def new_environment_entry(number):
    return {
        "number": number,
        "status": None,
        "port": None,
        "pid": None,
        "secret_key": secrets.token_urlsafe(50),
        "head_sha": None,
        "head_branch": None,
        "title": None,
        "url": None,
        "failure": None,
        "reject_reason": None,
        "built_at": None,
        "last_activity": None,
        "published_sha": None,
        "published_status": None,
    }


def load_state():
    state_path = DEPLOYMENTS_DIR / "state.json"
    if not state_path.exists():
        return {"environments": {}}
    return json.loads(state_path.read_text())


def save_state(state):
    DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    state_path = DEPLOYMENTS_DIR / "state.json"
    temp_path = state_path.with_name("state.json.tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    temp_path.replace(state_path)


@contextmanager
def build_lock():
    DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    lock_handle = open(DEPLOYMENTS_DIR / "build.lock", "w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()


def gh(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown gh error"
        raise RuntimeError(f"gh {args[0]} {args[1]} failed: {detail}")
    return result.stdout


def run_command(command, cwd, env=None):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def origin_url():
    configured = os.environ.get("MMM_PR_ORIGIN_URL")
    if configured:
        return configured
    exit_status, output = run_command(("git", "remote", "get-url", "origin"), cwd=REPO_ROOT)
    if exit_status:
        raise RuntimeError("could not read the origin remote URL of the loop checkout")
    return output.strip()


def pull_head_shas():
    """Resolve the current head commit of every PR ref on the canonical remote.

    Reading refs from the canonical repository only never fetches or executes
    any PR code, so this stays safe to run for fork pull requests too.
    """
    exit_status, output = run_command(("git", "ls-remote", "origin", "refs/pull/*/head"), cwd=REPO_ROOT)
    if exit_status:
        raise RuntimeError("git ls-remote against the canonical remote failed; cannot resolve PR heads")
    head_shas = {}
    for line in output.splitlines():
        sha, _, ref = line.partition("\t")
        number_match = re.search(r"refs/pull/(\d+)/head", ref.strip())
        if number_match:
            head_shas[int(number_match.group(1))] = sha.strip()
    return head_shas


def open_pull_requests():
    pulls = json.loads(gh("pr", "list", "--state", "open", "--limit", "500", "--json", PR_FIELDS))
    head_shas = pull_head_shas()
    for pull in pulls:
        pull["head_sha"] = head_shas.get(pull["number"])
    return pulls


def pull_request(number):
    pull = json.loads(gh("pr", "view", str(number), "--json", PR_FIELDS))
    pull["head_sha"] = pull_head_shas().get(number)
    return pull


def pull_changed_files(number):
    files = json.loads(gh("pr", "view", str(number), "--json", "files"))["files"]
    return [pull_file["path"] for pull_file in files]


def publish_pull_request_comment(number, body):
    body_file = DEPLOYMENTS_DIR / f"pr-{number}-comment.md"
    body_file.write_text(body)
    try:
        gh("pr", "comment", str(number), "--body-file", str(body_file))
    finally:
        body_file.unlink()


AREA_RULES = (
    ("MMM/views.py", "game flow and page interaction"),
    ("MMM/api_views.py", "board action handling"),
    ("MMM/models.py", "game rules and card state"),
    ("MMM/battle_services.py", "battle rules and bot turns"),
    ("MMM/special_timeline.py", "special action animations"),
    ("MMM/demo_flow.py", "demo scenario setup"),
    ("MMM/demo_greetings.py", "title page greetings"),
    ("MMM/jinja2/", "page templates"),
    ("MMM/static/", "game styling and scripts"),
    ("var/www/static/", "board styling and interaction scripts"),
    ("mysite/", "deployment settings"),
    ("scripts/", "repository tooling"),
)


def changed_file_areas(changed_files):
    """Count changed files per play-relevant area; files outside all areas are
    left out of the play note."""
    areas = {}
    for changed_file in changed_files:
        for area_source, area in AREA_RULES:
            if changed_file == area_source or changed_file.startswith(area_source):
                areas[area] = areas.get(area, 0) + 1
                break
    return areas


def ready_play_note(pull, environment_address, areas):
    lines = [
        f"🚀 PR test environment is ready: {environment_address}",
        "",
        f"Built from {pull.get('headRefName')} at {short_sha(pull.get('head_sha'))}. "
        "The database is isolated and deterministically seeded; "
        "manage.py migrate, seed, check and test all passed.",
    ]
    if areas:
        lines.append("")
        lines.append("What to play and look at:")
        lines.extend(
            f"- {area} ({count} file{'s' if count > 1 else ''})"
            for area, count in areas.items()
        )
    lines.append("")
    lines.append("Start a demo battle from the title page Play button and write your play feedback here.")
    return "\n".join(lines)


def failed_play_note(pull, failure):
    return "\n".join([
        "⚠️ PR test environment build failed; no playable environment is published for this push.",
        "",
        f"Attempted from {pull.get('headRefName')} at {short_sha(pull.get('head_sha'))}.",
        failure.splitlines()[0],
        "",
        "Push a fix and the environment rebuilds automatically.",
    ])


def write_proxy_routes(state):
    """Rewrite the hostname-to-port map consumed by the single reverse proxy
    so a new PR never needs a proxy or tunnel change."""
    DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    routes = {
        pr_hostname(entry["number"]): entry["port"]
        for entry in ready_environment_entries(state)
    }
    routes_json_path = DEPLOYMENTS_DIR / "proxy_routes.json"
    routes_json_path.write_text(json.dumps(routes, indent=2, sort_keys=True) + "\n")
    caddy_blocks = []
    for entry in sorted(ready_environment_entries(state), key=lambda entry: entry["number"]):
        caddy_blocks.append("\n".join([
            f"http://{pr_hostname(entry['number'])} {{",
            f"    reverse_proxy 127.0.0.1:{entry['port']}",
            "}",
            "",
        ]))
    (DEPLOYMENTS_DIR / "routes.caddy").write_text("\n".join(caddy_blocks))


def deployment_environment(entry):
    number = entry["number"]
    hostname = pr_hostname(number)
    return {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "mysite.settings",
        "MMM_SECRET_KEY": entry.setdefault("secret_key", secrets.token_urlsafe(50)),
        "MMM_DEBUG": "false",
        "MMM_ALLOWED_HOSTS": f"{hostname},localhost,127.0.0.1",
        "MMM_CSRF_TRUSTED_ORIGINS": f"https://{hostname}",
        "MMM_SECURE_COOKIES": "true",
        "MMM_DB_PATH": str(pr_database(number)),
    }


def environment_server_running(entry):
    pid = entry.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    command_file = Path(f"/proc/{pid}/cmdline")
    if not command_file.exists():
        return True
    command = command_file.read_bytes().decode(errors="replace")
    return "runserver" in command and str(entry.get("port")) in command


def start_server(entry):
    log_handle = open(pr_log_path(entry["number"]), "ab")
    try:
        process = subprocess.Popen(
            (
                sys.executable, "manage.py", "runserver",
                f"0.0.0.0:{entry['port']}", "--noreload", "--insecure",
            ),
            cwd=pr_checkout(entry["number"]),
            env=deployment_environment(entry),
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
        )
    finally:
        log_handle.close()
    return process.pid


def stop_server(entry):
    pid = entry.get("pid")
    if not pid or not environment_server_running(entry):
        entry["pid"] = None
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        if not environment_server_running(entry):
            break
        time.sleep(0.1)
    if environment_server_running(entry):
        os.kill(pid, signal.SIGKILL)
    entry["pid"] = None


def git_in_checkout(command, checkout):
    exit_status, output = run_command(("git", *command), cwd=checkout)
    if exit_status:
        raise BuildFailure(f"git {' '.join(command)} failed with exit status {exit_status}\n{output_tail(output)}")


def update_checkout(pull, checkout):
    git_in_checkout(("fetch", "origin", f"pull/{pull['number']}/head"), checkout)
    git_in_checkout(("reset", "--hard", "FETCH_HEAD"), checkout)
    git_in_checkout(("clean", "-fdx"), checkout)


def build_environment(state, pull):
    """Rebuild one PR's environment from its current head and serve it when
    every gate passes; a failing gate records a failure status and never a
    playable-ready one."""
    number = pull["number"]
    entry = state["environments"].setdefault(str(number), new_environment_entry(number))
    if entry.get("pid"):
        stop_server(entry)
    entry.update(
        number=number,
        status="building",
        head_sha=pull["head_sha"],
        head_branch=pull.get("headRefName"),
        title=pull.get("title"),
        url=pull.get("url"),
        reject_reason=None,
        failure=None,
    )
    if not entry.get("port"):
        entry["port"] = allocate_port(state)
    save_state(state)
    checkout = pr_checkout(number)
    try:
        if not (checkout / ".git").exists():
            exit_status, output = run_command(("git", "clone", origin_url(), str(checkout)), cwd=DEPLOYMENTS_DIR)
            if exit_status:
                raise BuildFailure(f"git clone failed with exit status {exit_status}\n{output_tail(output)}")
        update_checkout(pull, checkout)
        gate_environment = deployment_environment(entry)
        for command in GATES:
            exit_status, output = run_command((sys.executable, *command), cwd=checkout, env=gate_environment)
            if exit_status:
                raise BuildFailure(f"{command[1]} failed with exit status {exit_status}\n{output_tail(output)}")
        entry.update(
            status="ready",
            built_at=utc_now_iso(),
            last_activity=utc_now_iso(),
            pid=start_server(entry),
        )
        time.sleep(1)
        if not environment_server_running(entry):
            raise BuildFailure(f"runserver on port {entry['port']} exited during startup")
        print(f"PR {number}: ready at {environment_url(number)} on port {entry['port']}")
    except BuildFailure as failure:
        entry.update(status="failed", failure=str(failure), pid=None)
        print(f"PR {number}: build failed; {str(failure).splitlines()[0]}")
    save_state(state)
    return entry


def needs_rebuild(entry, pull):
    if entry is None:
        return True
    if entry.get("status") == "rejected":
        return True
    if entry.get("head_sha") != pull["head_sha"]:
        return True
    if entry.get("status") == "ready":
        return not environment_server_running(entry)
    return entry.get("status") == "building"


def refresh_last_activity(state, open_numbers):
    """Record each running environment's last request time from its server
    log, and mark a closed PR's dead server stopped so its slot frees up; an
    open PR's dead server is left to the rebuild plan instead."""
    for entry in state["environments"].values():
        if entry.get("status") != "ready":
            continue
        log_path = pr_log_path(entry["number"])
        if log_path.exists():
            entry["last_activity"] = file_mtime_utc_iso(log_path)
        if entry["number"] not in open_numbers and not environment_server_running(entry):
            entry["status"] = "stopped"
            print(
                f"PR {entry['number']}: server process is gone; marked stopped and "
                "retained for on-demand rebuild"
            )


def ensure_free_slot(state, protected_numbers):
    """Stop the least recently active running environments until one capacity
    slot is free; stopped environments keep their checkout, database, and
    port for on-demand rebuild."""
    while len(ready_environment_entries(state)) >= MAX_RUNNING_ENVIRONMENTS:
        victim = least_recently_active_environment(state, protected_numbers)
        if victim is None:
            print(
                f"no free environment slot: all {MAX_RUNNING_ENVIRONMENTS} running "
                "environments are protected by this round's rebuilds"
            )
            return False
        stop_server(victim)
        victim["status"] = "stopped"
        print(f"PR {victim['number']}: least recently active; stopped for capacity and retained for rebuild")
        save_state(state)
    return True


def publish_environment_statuses(state, pulls):
    for pull in pulls:
        entry = state["environments"].get(str(pull["number"]))
        if entry is None or entry.get("status") not in ("ready", "failed"):
            continue
        if entry.get("published_sha") == entry.get("head_sha") and entry.get("published_status") == entry.get("status"):
            continue
        if entry.get("status") == "ready":
            try:
                areas = changed_file_areas(pull_changed_files(pull["number"]))
            except RuntimeError:
                areas = {}
                print(f"PR {pull['number']}: could not read changed files for the play note")
            body = ready_play_note(pull, environment_url(pull["number"]), areas)
        else:
            body = failed_play_note(pull, entry.get("failure") or "build failed")
        publish_pull_request_comment(pull["number"], body)
        entry["published_sha"] = entry.get("head_sha")
        entry["published_status"] = entry.get("status")
        save_state(state)
        print(f"PR {pull['number']}: published {entry['status']} status")


def finish_deployment(state, pulls):
    publish_environment_statuses(state, pulls)
    write_proxy_routes(state)
    save_state(state)


def deploy_pull_requests(state, pulls):
    refresh_last_activity(state, {pull["number"] for pull in pulls})
    buildable_pulls = []
    for pull in pulls:
        if not pull.get("head_sha"):
            print(f"PR {pull['number']}: no head commit found on {CANONICAL_REPO}; skipped this round")
            continue
        buildable_pulls.append(pull)
    plan = [
        pull for pull in buildable_pulls
        if needs_rebuild(state["environments"].get(str(pull["number"])), pull)
    ]
    protected_numbers = {pull["number"] for pull in plan}
    for pull in plan:
        entry = state["environments"].get(str(pull["number"]))
        if not entry or entry.get("status") != "ready":
            if not ensure_free_slot(state, protected_numbers):
                continue
        build_environment(state, pull)
    finish_deployment(state, pulls)


def sync():
    with build_lock():
        state = load_state()
        pulls = open_pull_requests()
        eligible_pulls, rejected_pulls = [], []
        for pull in pulls:
            if is_same_repository_pull(pull, CANONICAL_REPO):
                eligible_pulls.append(pull)
            else:
                rejected_pulls.append(pull)
        for pull in rejected_pulls:
            entry = state["environments"].setdefault(
                str(pull["number"]), new_environment_entry(pull["number"])
            )
            identity = same_repository_identity(pull) or "an unknown repository"
            entry.update(
                status="rejected",
                reject_reason=f"head repository {identity} is not {CANONICAL_REPO}",
                url=pull.get("url"),
                head_branch=pull.get("headRefName"),
            )
            print(
                f"PR {pull['number']}: rejected; {entry['reject_reason']}. "
                "PR code is not checked out or executed."
            )
        save_state(state)
        deploy_pull_requests(state, sorted(eligible_pulls, key=lambda pull: pull["number"]))
        print("\n".join(status_lines(state)))
    return 0


def status_lines(state):
    lines = []
    for number in sorted(state["environments"], key=int):
        entry = state["environments"][number]
        parts = [f"PR {number}: {entry.get('status') or 'new'}"]
        if entry.get("port"):
            parts.append(f"port {entry['port']}")
        if entry.get("status") == "ready":
            parts.append(environment_url(int(number)))
        if entry.get("head_sha"):
            parts.append(short_sha(entry["head_sha"]))
        if entry.get("last_activity"):
            parts.append(f"active {entry['last_activity']}")
        if entry.get("failure"):
            parts.append(entry["failure"].splitlines()[0])
        if entry.get("reject_reason"):
            parts.append(entry["reject_reason"])
        lines.append(" | ".join(parts))
    return lines or ["no PR environments recorded"]


def status_command():
    print("\n".join(status_lines(load_state())))
    return 0


def rebuild_environment_command(number):
    with build_lock():
        state = load_state()
        pull = pull_request(number)
        if not is_same_repository_pull(pull, CANONICAL_REPO):
            identity = same_repository_identity(pull) or "an unknown repository"
            entry = state["environments"].setdefault(str(number), new_environment_entry(number))
            entry.update(
                status="rejected",
                reject_reason=f"head repository {identity} is not {CANONICAL_REPO}",
                url=pull.get("url"),
            )
            save_state(state)
            print(
                f"PR {number}: rejected; {entry['reject_reason']}. "
                "PR code is not checked out or executed."
            )
            return 1
        if not pull.get("head_sha"):
            print(f"PR {number}: no head commit found on {CANONICAL_REPO}")
            save_state(state)
            return 1
        entry = state["environments"].get(str(number))
        if not entry or entry.get("status") != "ready":
            if not ensure_free_slot(state, {number}):
                save_state(state)
                return 1
        build_environment(state, pull)
        finish_deployment(state, [pull])
        print("\n".join(status_lines(state)))
    return 0


def stop_environment_command(number):
    with build_lock():
        state = load_state()
        entry = state["environments"].get(str(number))
        if entry is None:
            print(f"PR {number}: no environment recorded")
            return 1
        stop_server(entry)
        entry["status"] = "stopped"
        save_state(state)
        write_proxy_routes(state)
        print(f"PR {number}: stopped; checkout and database retained for on-demand rebuild")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Manage per-PR test environments for Megans Magische Meesters"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "sync", help="build and publish environments for open same-repository PRs"
    )
    subparsers.add_parser("status", help="list recorded PR environments")
    rebuild_parser = subparsers.add_parser(
        "rebuild", help="force a rebuild of one PR environment"
    )
    rebuild_parser.add_argument("number", type=int)
    stop_parser = subparsers.add_parser(
        "stop", help="stop one PR environment and retain it for rebuild"
    )
    stop_parser.add_argument("number", type=int)
    args = parser.parse_args(argv)
    DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    command_functions = {
        "sync": sync,
        "status": status_command,
        "rebuild": rebuild_environment_command,
        "stop": stop_environment_command,
    }
    try:
        if hasattr(args, "number"):
            return command_functions[args.command](args.number)
        return command_functions[args.command]()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
