"""Offline checks for the production deployment manager."""

import contextlib
import importlib.util
import io
import json
import shutil
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).with_name("production.py")


def load_manager():
    spec = importlib.util.spec_from_file_location("production", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TemporaryDeploymentDirectory(unittest.TestCase):
    def setUp(self):
        self.manager = load_manager()
        deployment_root = Path(tempfile.mkdtemp(prefix="production-"))
        self.addCleanup(shutil.rmtree, deployment_root, ignore_errors=True)
        self.deployment_root = deployment_root
        self.manager.DEPLOYMENTS_DIR = deployment_root


class EnvironmentTests(TemporaryDeploymentDirectory):
    def test_the_deployment_environment_carries_the_production_settings(self):
        environment = self.manager.deployment_environment("secret-value")
        self.assertEqual(environment["DJANGO_SETTINGS_MODULE"], "mysite.settings")
        self.assertEqual(environment["MMM_SECRET_KEY"], "secret-value")
        self.assertEqual(environment["MMM_DEBUG"], "false")
        self.assertEqual(environment["MMM_ALLOWED_HOSTS"], "www.paintedpillars.com")
        self.assertEqual(environment["MMM_CSRF_TRUSTED_ORIGINS"], "https://www.paintedpillars.com")
        self.assertEqual(environment["MMM_SECURE_COOKIES"], "true")
        self.assertEqual(environment["MMM_DB_PATH"], str(self.manager.production_database()))
        self.assertTrue(environment["MMM_DB_PATH"].startswith(str(self.deployment_root)))

    def test_the_database_and_secret_key_live_outside_the_checkout(self):
        checkout = self.manager.production_checkout()
        self.assertEqual(self.manager.production_database().parent, checkout.parent)
        self.assertEqual(self.manager.production_env_path().parent, checkout.parent)


class StateTests(TemporaryDeploymentDirectory):
    def test_missing_state_file_starts_undeployed(self):
        state = self.manager.load_state()
        self.assertIsNone(state["deployment"]["status"])
        self.assertIsNone(state["deployment"]["pid"])

    def test_state_round_trips_through_disk(self):
        entry = self.manager.new_deployment_entry()
        entry.update(
            status="failed",
            head_sha="abcdef1234567890",
            failure="test failed with exit status 1\ntraceback tail",
            static_failure="collectstatic failed with exit status 1\ntraceback tail",
        )
        self.manager.save_state({"deployment": entry})
        reloaded = self.manager.load_state()
        self.assertEqual(reloaded["deployment"]["status"], "failed")
        self.assertEqual(reloaded["deployment"]["head_sha"], "abcdef1234567890")
        self.assertEqual(reloaded["deployment"]["failure"], "test failed with exit status 1\ntraceback tail")
        self.assertEqual(
            reloaded["deployment"]["static_failure"], "collectstatic failed with exit status 1\ntraceback tail"
        )


class SecretKeyTests(TemporaryDeploymentDirectory):
    def test_the_secret_key_is_generated_once_and_then_reused(self):
        first_key = self.manager.load_or_create_secret_key()
        stored_key = json.loads(self.manager.production_env_path().read_text())["secret_key"]
        self.assertEqual(first_key, stored_key)
        self.assertEqual(self.manager.load_or_create_secret_key(), first_key)

    def test_an_existing_secret_key_is_kept(self):
        env_path = self.manager.production_env_path()
        env_path.parent.mkdir(parents=True)
        env_path.write_text(json.dumps({"secret_key": "stored-key"}))
        self.assertEqual(self.manager.load_or_create_secret_key(), "stored-key")


class ServerVerificationTests(TemporaryDeploymentDirectory):
    def setUp(self):
        super().setUp()
        self.manager.os = SimpleNamespace(kill=self.fake_kill)
        self.manager.time = SimpleNamespace(sleep=lambda seconds: None)
        self.manager.process_command_line = lambda pid: self.command_lines.get(pid)
        self.manager.process_working_directory = lambda pid: self.working_directories.get(pid)
        self.live_pids = set()
        self.command_lines = {}
        self.working_directories = {}
        self.signals = []
        self.sigterm_ends_the_process = True

    def fake_kill(self, pid, signal_number):
        if pid not in self.live_pids:
            raise OSError(f"no such process {pid}")
        if signal_number == 0:
            return
        self.signals.append((pid, signal_number))
        if signal_number == signal.SIGTERM and self.sigterm_ends_the_process:
            self.live_pids.discard(pid)

    def gunicorn_entry(self, pid=4242):
        self.live_pids = {pid}
        self.command_lines[pid] = (
            f"{sys.executable}\x00-m\x00gunicorn\x00--bind\x00"
            f"0.0.0.0:{self.manager.PRODUCTION_PORT}\x00{self.manager.GUNICORN_APPLICATION}"
        )
        self.working_directories[pid] = str(self.manager.production_checkout())
        return {"pid": pid}

    def test_a_gunicorn_pid_in_the_production_checkout_is_running(self):
        self.assertTrue(self.manager.production_server_running(self.gunicorn_entry()))

    def test_a_reused_pid_of_another_process_is_not_the_production_server(self):
        entry = self.gunicorn_entry()
        self.command_lines[4242] = (
            f"{sys.executable} manage.py runserver 0.0.0.0:8100 --noreload --insecure"
        )
        self.assertFalse(self.manager.production_server_running(entry))

    def test_a_gunicorn_pid_on_another_port_is_not_the_production_server(self):
        entry = self.gunicorn_entry()
        self.command_lines[4242] = (
            f"{sys.executable}\x00-m\x00gunicorn\x00--bind\x000.0.0.0:8100\x00"
            f"{self.manager.GUNICORN_APPLICATION}"
        )
        self.assertFalse(self.manager.production_server_running(entry))

    def test_a_gunicorn_pid_outside_the_production_checkout_is_not_the_server(self):
        entry = self.gunicorn_entry()
        self.working_directories[4242] = "/somewhere/else/repo"
        self.assertFalse(self.manager.production_server_running(entry))

    def test_a_dead_pid_is_not_running(self):
        entry = self.gunicorn_entry()
        self.live_pids.clear()
        self.assertFalse(self.manager.production_server_running(entry))

    def test_a_pid_without_a_readable_proc_entry_fails_closed(self):
        entry = self.gunicorn_entry()
        self.command_lines[4242] = None
        self.assertFalse(self.manager.production_server_running(entry))

    def test_an_entry_without_a_pid_is_not_running(self):
        self.assertFalse(self.manager.production_server_running({"pid": None}))

    def test_stop_signals_only_a_verified_pid_and_clears_it(self):
        entry = self.gunicorn_entry()
        self.manager.stop_server(entry)
        self.assertEqual(self.signals, [(4242, signal.SIGTERM)])
        self.assertIsNone(entry["pid"])

    def test_stop_never_signals_a_reused_pid(self):
        entry = self.gunicorn_entry()
        self.command_lines[4242] = "some other process entirely"
        self.manager.stop_server(entry)
        self.assertEqual(self.signals, [])
        self.assertIsNone(entry["pid"])

    def test_stop_escalates_to_sigkill_when_sigterm_is_ignored(self):
        entry = self.gunicorn_entry()
        self.sigterm_ends_the_process = False
        self.manager.stop_server(entry)
        self.assertEqual(self.signals, [(4242, signal.SIGTERM), (4242, signal.SIGKILL)])
        self.assertIsNone(entry["pid"])


class ManagerHarness(TemporaryDeploymentDirectory):
    def setUp(self):
        super().setUp()
        self.manager.time = SimpleNamespace(sleep=lambda seconds: None)
        self.head_sha = "abcdef1234567890"
        self.real_main_head_sha = self.manager.main_head_sha
        self.live_server_pids = set()
        self.start_pids_are_live = True
        self.command_calls = []
        self.exit_statuses = {}
        self.started = []
        self.stopped = []
        self.manager.origin_url = lambda: "git@github.com:LucasWillemsens/Megans-Magische-Meesters.git"
        self.manager.main_head_sha = lambda: self.head_sha
        self.manager.run_command = self.run_command
        self.manager.start_server = self.record_start
        self.manager.stop_server = self.record_stop
        self.manager.production_server_running = lambda entry: entry.get("pid") in self.live_server_pids

    def run_command(self, command, cwd, env=None):
        self.command_calls.append((command, cwd, env))
        exit_status = self.exit_statuses.get(" ".join(command[1:]), 0)
        return exit_status, "simulated output"

    def record_start(self, secret_key):
        self.started.append(secret_key)
        if self.start_pids_are_live:
            self.live_server_pids.add(4242)
        return 4242

    def record_stop(self, entry):
        self.stopped.append(entry.get("pid"))
        self.live_server_pids.discard(entry.get("pid"))
        entry["pid"] = None

    def command_names(self):
        return [" ".join(command[1:]) for command, _, _ in self.command_calls]

    def gate_calls(self):
        return [
            (command, cwd, env)
            for command, cwd, env in self.command_calls
            if command[1:2] == ("manage.py",)
        ]

    def ready_entry(self, sha="abcdef1234567890"):
        entry = self.manager.new_deployment_entry()
        entry.update(
            status="ready",
            pid=4242,
            port=8000,
            head_sha=sha,
            built_at="2026-11-01T00:00:00+00:00",
        )
        self.live_server_pids.add(4242)
        return entry


class DeployFlowTests(ManagerHarness):
    def test_a_first_deploy_clones_gates_collects_and_starts_gunicorn(self):
        exit_status = self.manager.main(["deploy"])
        state = self.manager.load_state()
        entry = state["deployment"]
        self.assertEqual(exit_status, 0)
        self.assertEqual(entry["status"], "ready")
        self.assertEqual(entry["head_sha"], "abcdef1234567890")
        self.assertEqual(entry["port"], 8000)
        self.assertEqual(entry["pid"], 4242)
        self.assertEqual(len(self.started), 1)
        self.assertTrue(self.started[0])
        self.assertTrue(self.command_names()[0].startswith("clone "))
        self.assertEqual(
            self.command_names()[1:4],
            ["fetch origin main", "reset --hard FETCH_HEAD", "clean -fdx"],
        )
        self.assertEqual(
            [" ".join(command[1:]) for command, _, _ in self.gate_calls()],
            [
                "manage.py migrate",
                "manage.py add_deck_cards",
                "manage.py check",
                "manage.py test",
                "manage.py collectstatic --noinput",
            ],
        )
        self.assertIn("-c import gunicorn", self.command_names())
        self.assertNotIn("-m pip install gunicorn", self.command_names())

    def test_every_gate_runs_in_the_production_checkout_against_the_production_database(self):
        self.manager.main(["deploy"])
        checkout = self.manager.production_checkout()
        for command, cwd, env in self.gate_calls():
            self.assertEqual(cwd, checkout)
            self.assertEqual(env["MMM_DB_PATH"], str(self.manager.production_database()))
            self.assertEqual(env["MMM_DEBUG"], "false")
            self.assertEqual(env["MMM_ALLOWED_HOSTS"], "www.paintedpillars.com")
            self.assertEqual(env["MMM_CSRF_TRUSTED_ORIGINS"], "https://www.paintedpillars.com")
            self.assertEqual(env["MMM_SECURE_COOKIES"], "true")
            self.assertEqual(env["DJANGO_SETTINGS_MODULE"], "mysite.settings")
            self.assertTrue(env["MMM_SECRET_KEY"])

    def test_rebuilds_reset_only_the_checkout_and_keep_the_database_and_secret_key(self):
        production = self.manager.production_directory()
        production.mkdir(parents=True)
        database = self.manager.production_database()
        database.write_text("production game data")
        checkout = self.manager.production_checkout()
        checkout.mkdir(parents=True)
        (checkout / ".git").mkdir()
        self.manager.main(["deploy"])
        first_secret = json.loads(self.manager.production_env_path().read_text())["secret_key"]
        self.head_sha = "1234567890abcdef"
        exit_status = self.manager.main(["deploy"])
        self.assertEqual(exit_status, 0)
        self.assertEqual(database.read_text(), "production game data")
        self.assertEqual(
            json.loads(self.manager.production_env_path().read_text())["secret_key"], first_secret
        )
        self.assertEqual(self.started, [first_secret, first_secret])
        self.assertEqual(self.manager.load_state()["deployment"]["head_sha"], "1234567890abcdef")
        self.assertFalse(any(name.startswith("clone ") for name in self.command_names()))
        for command, cwd, _ in self.command_calls:
            if " ".join(command[1:]) == "clean -fdx":
                self.assertEqual(cwd, checkout)

    def test_a_missing_checkout_is_cloned_once_then_updated_in_place(self):
        self.manager.main(["deploy"])
        (self.manager.production_checkout() / ".git").mkdir(parents=True)
        self.head_sha = "1234567890abcdef"
        self.manager.main(["deploy"])
        clone_names = [name for name in self.command_names() if name.startswith("clone ")]
        self.assertEqual(len(clone_names), 1)
        self.assertEqual(self.command_names().count("fetch origin main"), 2)
        self.assertEqual(self.command_names().count("reset --hard FETCH_HEAD"), 2)

    def test_an_unchanged_head_with_a_running_server_skips_the_rebuild(self):
        self.manager.main(["deploy"])
        first_command_count = len(self.command_calls)
        exit_status = self.manager.main(["deploy"])
        self.assertEqual(exit_status, 0)
        self.assertEqual(len(self.command_calls), first_command_count)
        self.assertEqual(len(self.started), 1)
        self.assertEqual(self.manager.load_state()["deployment"]["status"], "ready")

    def test_force_rebuilds_an_unchanged_head(self):
        self.manager.main(["deploy"])
        first_gate_count = len(self.gate_calls())
        exit_status = self.manager.main(["deploy", "--force"])
        self.assertEqual(exit_status, 0)
        self.assertEqual(len(self.gate_calls()), first_gate_count * 2)
        self.assertEqual(len(self.started), 2)

    def test_a_dead_server_with_an_unchanged_head_is_rebuilt(self):
        self.manager.main(["deploy"])
        self.live_server_pids.clear()
        first_gate_count = len(self.gate_calls())
        exit_status = self.manager.main(["deploy"])
        self.assertEqual(exit_status, 0)
        self.assertEqual(len(self.gate_calls()), first_gate_count * 2)
        self.assertEqual(len(self.started), 2)
        self.assertEqual(self.manager.load_state()["deployment"]["status"], "ready")

    def test_a_failing_gate_aborts_and_leaves_the_running_server_untouched(self):
        self.manager.save_state({"deployment": self.ready_entry(sha="0000000000000000")})
        self.exit_statuses["manage.py test"] = 1
        exit_status = self.manager.main(["deploy"])
        state = self.manager.load_state()
        entry = state["deployment"]
        self.assertEqual(exit_status, 1)
        self.assertEqual(entry["status"], "failed")
        self.assertIn("test failed with exit status 1", entry["failure"])
        self.assertEqual(entry["pid"], 4242)
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.started, [])
        self.assertIn(4242, self.live_server_pids)
        self.assertFalse(any(name.startswith("-m pip install") for name in self.command_names()))

    def test_a_gunicorn_startup_failure_is_recorded_after_the_old_server_was_stopped(self):
        self.manager.save_state({"deployment": self.ready_entry(sha="0000000000000000")})
        self.start_pids_are_live = False
        exit_status = self.manager.main(["deploy"])
        state = self.manager.load_state()
        entry = state["deployment"]
        self.assertEqual(exit_status, 1)
        self.assertEqual(entry["status"], "failed")
        self.assertIn("gunicorn on port 8000 exited during startup", entry["failure"])
        self.assertEqual(self.stopped, [4242])
        self.assertIsNone(entry["pid"])

    def test_a_collectstatic_failure_is_recorded_without_blocking_the_deploy(self):
        self.exit_statuses["manage.py collectstatic --noinput"] = 1
        exit_status = self.manager.main(["deploy"])
        state = self.manager.load_state()
        entry = state["deployment"]
        self.assertEqual(exit_status, 0)
        self.assertEqual(entry["status"], "ready")
        self.assertIn("collectstatic failed with exit status 1", entry["static_failure"])
        self.assertIn("collectstatic failed with exit status 1", "\n".join(self.manager.status_lines(state)))

    def test_gunicorn_is_installed_only_when_the_import_fails(self):
        self.manager.main(["deploy"])
        self.assertIn("-c import gunicorn", self.command_names())
        self.assertNotIn("-m pip install gunicorn", self.command_names())
        self.exit_statuses["-c import gunicorn"] = 1
        self.head_sha = "1234567890abcdef"
        self.manager.main(["deploy"])
        self.assertIn("-m pip install gunicorn", self.command_names())
        self.assertEqual(self.manager.load_state()["deployment"]["status"], "ready")

    def test_an_unresolvable_main_head_fails_the_command_without_touching_state(self):
        self.manager.main_head_sha = self.real_main_head_sha
        self.exit_statuses[
            "ls-remote git@github.com:LucasWillemsens/Megans-Magische-Meesters.git refs/heads/main"
        ] = 1
        exit_status = self.manager.main(["deploy"])
        self.assertEqual(exit_status, 1)
        self.assertEqual(self.started, [])
        self.assertFalse(self.manager.production_state_path().exists())

    def test_deploy_and_status_output_never_contain_the_secret_key(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.manager.main(["deploy"])
        secret_key = json.loads(self.manager.production_env_path().read_text())["secret_key"]
        with contextlib.redirect_stdout(output):
            self.manager.main(["status"])
        self.assertNotIn(secret_key, output.getvalue())


class StatusTests(ManagerHarness):
    def test_status_shows_commit_time_pid_and_gate_failure(self):
        entry = self.ready_entry()
        entry.update(status="failed", failure="test failed with exit status 1\ntraceback tail")
        self.manager.save_state({"deployment": entry})
        line = "\n".join(self.manager.status_lines(self.manager.load_state()))
        self.assertIn("production: failed", line)
        self.assertIn("port 8000", line)
        self.assertIn("abcdef1", line)
        self.assertIn("deployed 2026-11-01", line)
        self.assertIn("pid 4242, running", line)
        self.assertIn("test failed with exit status 1", line)
        self.assertNotIn("traceback tail", line)

    def test_status_of_an_undeployed_state_says_so(self):
        line = "\n".join(self.manager.status_lines(self.manager.load_state()))
        self.assertIn("production: undeployed", line)

    def test_status_reports_a_dead_recorded_pid(self):
        entry = self.ready_entry()
        self.live_server_pids.clear()
        self.manager.save_state({"deployment": entry})
        line = "\n".join(self.manager.status_lines(self.manager.load_state()))
        self.assertIn("pid 4242, not running", line)


class StopCommandTests(ManagerHarness):
    def test_stop_stops_the_server_and_retains_the_database_and_secret_key(self):
        self.manager.main(["deploy"])
        exit_status = self.manager.main(["stop"])
        state = self.manager.load_state()
        entry = state["deployment"]
        self.assertEqual(exit_status, 0)
        self.assertEqual(entry["status"], "stopped")
        self.assertIsNone(entry["pid"])
        self.assertEqual(self.stopped, [None, 4242])
        self.assertTrue(self.manager.production_env_path().exists())

    def test_stop_without_a_deployment_records_a_stopped_state(self):
        exit_status = self.manager.main(["stop"])
        state = self.manager.load_state()
        self.assertEqual(exit_status, 0)
        self.assertEqual(state["deployment"]["status"], "stopped")
        self.assertIsNone(state["deployment"]["pid"])


if __name__ == "__main__":
    unittest.main()
