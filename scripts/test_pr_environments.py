"""Offline checks for the per-PR test-environment manager."""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).with_name("pr_environments.py")


def load_manager():
    spec = importlib.util.spec_from_file_location("pr_environments", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pull(number=9, owner="LucasWillemsens", repository="Megans-Magische-Meesters", sha="abcdef1234567890"):
    return {
        "number": number,
        "title": f"PR {number}",
        "url": f"https://github.com/LucasWillemsens/Megans-Magische-Meesters/pull/{number}",
        "headRefName": f"branch-{number}",
        "head_sha": sha,
        "headRepositoryOwner": {"login": owner},
        "headRepository": {"name": repository},
    }


class ForkIdentityTests(unittest.TestCase):
    def setUp(self):
        self.manager = load_manager()

    def test_same_repository_pull_is_accepted(self):
        self.assertTrue(self.manager.is_same_repository_pull(pull(), self.manager.CANONICAL_REPO))

    def test_fork_pull_is_rejected(self):
        fork_pull = pull(owner="someone-else")
        self.assertFalse(self.manager.is_same_repository_pull(fork_pull, self.manager.CANONICAL_REPO))

    def test_pull_without_head_repository_identity_is_rejected(self):
        without_owner = pull()
        without_owner["headRepositoryOwner"] = {}
        without_repository = pull()
        without_repository["headRepository"] = {}
        self.assertFalse(self.manager.is_same_repository_pull(without_owner, self.manager.CANONICAL_REPO))
        self.assertFalse(self.manager.is_same_repository_pull(without_repository, self.manager.CANONICAL_REPO))
        self.assertIsNone(self.manager.same_repository_identity(without_owner))

    def test_identity_match_ignores_case(self):
        mixed_case_pull = pull(owner="lucaswillemsens", repository="megans-magische-meesters")
        self.assertTrue(self.manager.is_same_repository_pull(mixed_case_pull, self.manager.CANONICAL_REPO))


class PortAllocationTests(unittest.TestCase):
    def setUp(self):
        self.manager = load_manager()

    def test_ports_are_the_lowest_unused_and_distinct_per_pr(self):
        state = {"environments": {}}
        first_port = self.manager.allocate_port(state)
        state["environments"]["9"] = {"port": first_port}
        second_port = self.manager.allocate_port(state)
        state["environments"]["10"] = {"port": second_port}
        self.assertEqual(first_port, 8100)
        self.assertEqual(second_port, 8101)

    def test_allocated_ports_skip_used_ones(self):
        state = {"environments": {
            "1": {"port": 8100},
            "2": {"port": 8101},
        }}
        self.assertEqual(self.manager.allocate_port(state), 8102)


class EvictionChoiceTests(unittest.TestCase):
    def setUp(self):
        self.manager = load_manager()

    def ready_entry(self, number, activity):
        entry = self.manager.new_environment_entry(number)
        entry.update(status="ready", pid=4242, port=8100 + number, last_activity=activity)
        return entry

    def test_least_recently_active_ready_environment_is_chosen(self):
        state = {"environments": {
            "1": self.ready_entry(1, "2026-10-01T00:00:00+00:00"),
            "2": self.ready_entry(2, "2026-11-10T00:00:00+00:00"),
            "3": self.ready_entry(3, "2026-11-12T00:00:00+00:00"),
        }}
        victim = self.manager.least_recently_active_environment(state, set())
        self.assertEqual(victim["number"], 1)

    def test_non_ready_environments_are_never_chosen(self):
        stopped_entry = self.manager.new_environment_entry(1)
        stopped_entry.update(status="stopped", last_activity="2026-09-01T00:00:00+00:00")
        failed_entry = self.manager.new_environment_entry(2)
        failed_entry.update(status="failed", last_activity="2026-09-02T00:00:00+00:00")
        state = {"environments": {
            "1": stopped_entry,
            "2": failed_entry,
            "3": self.ready_entry(3, "2026-11-12T00:00:00+00:00"),
        }}
        victim = self.manager.least_recently_active_environment(state, set())
        self.assertEqual(victim["number"], 3)

    def test_protected_environments_are_skipped_and_none_means_no_victim(self):
        state = {"environments": {
            "1": self.ready_entry(1, "2026-10-01T00:00:00+00:00"),
            "2": self.ready_entry(2, "2026-10-02T00:00:00+00:00"),
        }}
        victim = self.manager.least_recently_active_environment(state, {1})
        self.assertEqual(victim["number"], 2)
        self.assertIsNone(self.manager.least_recently_active_environment(state, {1, 2}))


class PlayNoteTests(unittest.TestCase):
    def setUp(self):
        self.manager = load_manager()

    def test_ready_note_carries_url_and_diff_derived_areas(self):
        areas = self.manager.changed_file_areas(
            ["MMM/views.py", "MMM/jinja2/MMM/board.jinja2", "var/www/static/board.js", "roadmap/x/description.txt"]
        )
        note = self.manager.ready_play_note(pull(9), "https://pr-9.paintedpillars.com/", areas)
        self.assertIn("https://pr-9.paintedpillars.com/", note)
        self.assertIn("- game flow and page interaction (1 file)", note)
        self.assertIn("- page templates (1 file)", note)
        self.assertIn("- board styling and interaction scripts (1 file)", note)
        self.assertNotIn("roadmap", note)

    def test_ready_note_without_play_areas_skips_the_area_list(self):
        note = self.manager.ready_play_note(pull(9), "https://pr-9.paintedpillars.com/", {})
        self.assertIn("https://pr-9.paintedpillars.com/", note)
        self.assertNotIn("What to play and look at", note)

    def test_failed_note_carries_no_environment_url(self):
        note = self.manager.failed_play_note(
            pull(9), "test failed with exit status 1\ntraceback tail"
        )
        self.assertIn("no playable environment", note)
        self.assertIn("test failed with exit status 1", note)
        self.assertNotIn("traceback tail", note)
        self.assertNotIn("https://", note)

    def test_area_rules_match_exact_files_and_prefixed_paths(self):
        areas = self.manager.changed_file_areas(["MMM/views.py", "MMM/views.py.extra"])
        self.assertEqual(areas, {"game flow and page interaction": 2})


class ProxyRouteTests(unittest.TestCase):
    def setUp(self):
        self.manager = load_manager()
        deployment_root = Path(tempfile.mkdtemp(prefix="pr-environments-"))
        self.addCleanup(shutil.rmtree, deployment_root, ignore_errors=True)
        self.deployment_root = deployment_root
        self.manager.DEPLOYMENTS_DIR = deployment_root

    def environment_entry(self, number, status):
        entry = self.manager.new_environment_entry(number)
        entry.update(status=status, port=8100 + number)
        return entry

    def test_ready_environments_map_hostnames_to_ports(self):
        state = {"environments": {
            "9": self.environment_entry(9, "ready"),
            "10": self.environment_entry(10, "ready"),
        }}
        self.manager.write_proxy_routes(state)
        routes = json.loads((self.deployment_root / "proxy_routes.json").read_text())
        self.assertEqual(routes, {
            "pr-9.paintedpillars.com": 8109,
            "pr-10.paintedpillars.com": 8110,
        })
        caddy_routes = (self.deployment_root / "routes.caddy").read_text()
        self.assertIn("http://pr-9.paintedpillars.com {\n    reverse_proxy 127.0.0.1:8109\n}", caddy_routes)
        self.assertIn("http://pr-10.paintedpillars.com {\n    reverse_proxy 127.0.0.1:8110\n}", caddy_routes)

    def test_non_ready_environments_are_not_routed(self):
        state = {"environments": {
            "9": self.environment_entry(9, "ready"),
            "10": self.environment_entry(10, "stopped"),
            "11": self.environment_entry(11, "failed"),
            "12": self.environment_entry(12, "rejected"),
        }}
        self.manager.write_proxy_routes(state)
        routes = json.loads((self.deployment_root / "proxy_routes.json").read_text())
        self.assertEqual(routes, {"pr-9.paintedpillars.com": 8109})


class StateTests(unittest.TestCase):
    def setUp(self):
        self.manager = load_manager()
        deployment_root = Path(tempfile.mkdtemp(prefix="pr-environments-"))
        self.addCleanup(shutil.rmtree, deployment_root, ignore_errors=True)
        self.manager.DEPLOYMENTS_DIR = deployment_root

    def test_missing_state_file_starts_empty(self):
        self.assertEqual(self.manager.load_state(), {"environments": {}})

    def test_state_round_trips_through_disk(self):
        entry = self.manager.new_environment_entry(9)
        entry.update(status="ready", head_sha="abcdef1234567890")
        self.manager.save_state({"environments": {"9": entry}})
        reloaded = self.manager.load_state()
        self.assertEqual(reloaded["environments"]["9"]["status"], "ready")
        self.assertEqual(reloaded["environments"]["9"]["head_sha"], "abcdef1234567890")
        self.assertEqual(reloaded["environments"]["9"]["secret_key"], entry["secret_key"])

    def test_environment_entries_get_distinct_secret_keys(self):
        first_entry = self.manager.new_environment_entry(9)
        second_entry = self.manager.new_environment_entry(10)
        self.assertTrue(first_entry["secret_key"])
        self.assertNotEqual(first_entry["secret_key"], second_entry["secret_key"])


class ManagerHarness(unittest.TestCase):
    def setUp(self):
        self.manager = load_manager()
        deployment_root = Path(tempfile.mkdtemp(prefix="pr-environments-"))
        self.addCleanup(shutil.rmtree, deployment_root, ignore_errors=True)
        self.deployment_root = deployment_root
        self.manager.DEPLOYMENTS_DIR = deployment_root
        self.manager.time = SimpleNamespace(sleep=lambda seconds: None)
        self.pulls = []
        self.gate_calls = []
        self.gate_exit_statuses = {}
        self.started = []
        self.stopped = []
        self.published = []
        self.manager.open_pull_requests = lambda: self.pulls
        self.manager.pull_request = lambda number: next(
            pull_entry for pull_entry in self.pulls if pull_entry["number"] == number
        )
        self.manager.pull_changed_files = lambda number: ["MMM/views.py", "MMM/jinja2/MMM/board.jinja2"]
        self.manager.publish_pull_request_comment = self.record_publish
        self.manager.run_command = self.run_command
        self.manager.stop_server = self.record_stop
        self.manager.start_server = self.record_start
        self.manager.environment_server_running = lambda entry: True
        self.manager.origin_url = lambda: "git@github.com:LucasWillemsens/Megans-Magische-Meesters.git"

    def run_command(self, command, cwd, env=None):
        self.gate_calls.append((command, env))
        if "manage.py" in command:
            exit_status = self.gate_exit_statuses.get(command[2], 0)
        else:
            exit_status = 0
        return exit_status, "simulated output"

    def record_start(self, entry):
        self.started.append(entry["number"])
        return 4242

    def record_stop(self, entry):
        self.stopped.append(entry["number"])

    def record_publish(self, number, body):
        self.published.append((number, body))

    def ready_entry(self, number, activity, port, sha="abcdef1234567890"):
        entry = self.manager.new_environment_entry(number)
        entry.update(
            status="ready",
            pid=4242,
            port=port,
            head_sha=sha,
            published_sha=sha,
            published_status="ready",
            last_activity=activity,
        )
        return entry


class SyncFlowTests(ManagerHarness):
    def test_two_same_repository_prs_get_gated_environments_and_published_urls(self):
        self.pulls = [pull(number=9), pull(number=10, sha="1234567890abcdef")]
        self.manager.sync()
        state = self.manager.load_state()
        self.assertEqual(state["environments"]["9"]["status"], "ready")
        self.assertEqual(state["environments"]["10"]["status"], "ready")
        self.assertEqual(state["environments"]["9"]["port"], 8100)
        self.assertEqual(state["environments"]["10"]["port"], 8101)
        manage_gate_names = [command[2] for command, _ in self.gate_calls if "manage.py" in command]
        self.assertEqual(
            manage_gate_names, ["migrate", "add_deck_cards", "check", "test"] * 2
        )
        gate_environments = [env for _, env in self.gate_calls if env]
        db_paths = {env["MMM_DB_PATH"] for env in gate_environments}
        allowed_hosts = {env["MMM_ALLOWED_HOSTS"] for env in gate_environments}
        self.assertEqual(len(db_paths), 2)
        self.assertEqual(len(allowed_hosts), 2)
        for env in gate_environments:
            self.assertTrue(env["MMM_DB_PATH"].startswith(str(self.deployment_root)))
            self.assertEqual(env["MMM_DEBUG"], "false")
            self.assertEqual(env["MMM_SECURE_COOKIES"], "true")
            self.assertTrue(env["MMM_SECRET_KEY"])
        self.assertEqual([number for number, _ in self.published], [9, 10])
        for number, body in self.published:
            self.assertIn(f"https://pr-{number}.paintedpillars.com/", body)
        routes = json.loads((self.deployment_root / "proxy_routes.json").read_text())
        self.assertEqual(routes, {
            "pr-9.paintedpillars.com": 8100,
            "pr-10.paintedpillars.com": 8101,
        })

    def test_fork_prs_are_rejected_before_checkout_or_execution(self):
        self.pulls = [pull(number=77, owner="someone-else")]
        self.manager.sync()
        state = self.manager.load_state()
        entry = state["environments"]["77"]
        self.assertEqual(entry["status"], "rejected")
        self.assertIsNone(entry["port"])
        self.assertIn("someone-else/Megans-Magische-Meesters", entry["reject_reason"])
        self.assertFalse((self.deployment_root / "pr-77" / "repo").exists())
        self.assertEqual(self.gate_calls, [])
        self.assertEqual(self.published, [])

    def test_a_pull_without_a_head_sha_is_skipped_without_build(self):
        self.pulls = [pull(number=9)]
        self.pulls[0]["head_sha"] = None
        self.manager.sync()
        state = self.manager.load_state()
        self.assertNotIn("9", state["environments"])
        self.assertEqual(self.gate_calls, [])
        self.assertEqual(self.published, [])

    def test_a_new_push_rebuilds_and_republishes_the_pr(self):
        self.pulls = [pull(number=9, sha="1111111111111111")]
        old_entry = self.ready_entry(9, "2026-11-01T00:00:00+00:00", 8100, sha="0000000000000000")
        self.manager.save_state({"environments": {"9": old_entry}})
        self.manager.sync()
        state = self.manager.load_state()
        entry = state["environments"]["9"]
        self.assertEqual(entry["status"], "ready")
        self.assertEqual(entry["head_sha"], "1111111111111111")
        self.assertEqual(entry["published_sha"], "1111111111111111")
        self.assertEqual(entry["port"], 8100)
        self.assertEqual(self.started, [9])
        self.assertEqual(self.stopped, [9])
        self.assertIn("1111111", self.published[0][1])

    def test_capacity_evicts_the_least_recently_active_environment(self):
        entries = {
            1: self.ready_entry(1, "2026-10-01T00:00:00+00:00", 8101),
            2: self.ready_entry(2, "2026-11-10T00:00:00+00:00", 8102),
            3: self.ready_entry(3, "2026-11-12T00:00:00+00:00", 8103),
        }
        self.manager.save_state({"environments": {str(number): entry for number, entry in entries.items()}})
        self.pulls = [
            pull(number=1, sha=entries[1]["head_sha"]),
            pull(number=2, sha=entries[2]["head_sha"]),
            pull(number=3, sha=entries[3]["head_sha"]),
            pull(number=4, sha="4444444444444444"),
        ]
        self.manager.sync()
        state = self.manager.load_state()
        self.assertEqual(state["environments"]["1"]["status"], "stopped")
        self.assertEqual(state["environments"]["1"]["port"], 8101)
        self.assertEqual(state["environments"]["2"]["status"], "ready")
        self.assertEqual(state["environments"]["3"]["status"], "ready")
        self.assertEqual(state["environments"]["4"]["status"], "ready")
        self.assertEqual(state["environments"]["4"]["port"], 8100)
        self.assertEqual(self.stopped, [1])
        self.assertEqual([number for number, _ in self.published], [4])

    def test_a_new_pr_waits_when_every_slot_is_protected_by_rebuilds(self):
        entries = {
            1: self.ready_entry(1, "2026-10-01T00:00:00+00:00", 8101, sha="0000000000000001"),
            2: self.ready_entry(2, "2026-10-02T00:00:00+00:00", 8102, sha="0000000000000002"),
            3: self.ready_entry(3, "2026-10-03T00:00:00+00:00", 8103, sha="0000000000000003"),
        }
        self.manager.save_state({"environments": {str(number): entry for number, entry in entries.items()}})
        self.pulls = [
            pull(number=1, sha="aaaaaaaaaaaaaaa1"),
            pull(number=2, sha="aaaaaaaaaaaaaaa2"),
            pull(number=3, sha="aaaaaaaaaaaaaaa3"),
            pull(number=4, sha="aaaaaaaaaaaaaaa4"),
        ]
        self.manager.sync()
        state = self.manager.load_state()
        for number in (1, 2, 3):
            self.assertEqual(state["environments"][str(number)]["status"], "ready")
        self.assertNotIn("4", state["environments"])
        self.assertEqual(self.stopped, [1, 2, 3])

    def test_environments_of_closed_prs_keep_running(self):
        closed_entry = self.ready_entry(2, "2026-11-10T00:00:00+00:00", 8102)
        self.manager.save_state({"environments": {"2": closed_entry}})
        self.pulls = []
        self.manager.environment_server_running = lambda entry: True
        self.manager.sync()
        state = self.manager.load_state()
        self.assertEqual(state["environments"]["2"]["status"], "ready")
        routes = json.loads((self.deployment_root / "proxy_routes.json").read_text())
        self.assertEqual(routes, {"pr-2.paintedpillars.com": 8102})
        self.assertEqual(self.stopped, [])

    def test_a_dead_server_of_a_closed_pr_is_marked_stopped_and_retained(self):
        dead_entry = self.ready_entry(5, "2026-11-10T00:00:00+00:00", 8105)
        self.manager.save_state({"environments": {"5": dead_entry}})
        self.pulls = []
        self.manager.environment_server_running = lambda entry: False
        self.manager.sync()
        state = self.manager.load_state()
        self.assertEqual(state["environments"]["5"]["status"], "stopped")
        self.assertEqual(state["environments"]["5"]["port"], 8105)

    def test_a_dead_server_of_an_open_pr_rebuilds(self):
        dead_entry = self.ready_entry(6, "2026-11-10T00:00:00+00:00", 8106)
        self.manager.save_state({"environments": {"6": dead_entry}})
        self.pulls = [pull(number=6)]
        self.manager.environment_server_running = lambda entry: 6 in self.started
        self.manager.sync()
        state = self.manager.load_state()
        self.assertEqual(state["environments"]["6"]["status"], "ready")
        self.assertEqual(self.started, [6])

    def test_a_failing_gate_blocks_ready_and_publishes_failure_without_url(self):
        self.pulls = [pull(number=9)]
        self.gate_exit_statuses["test"] = 1
        self.manager.environment_server_running = lambda entry: True
        self.manager.sync()
        state = self.manager.load_state()
        entry = state["environments"]["9"]
        self.assertEqual(entry["status"], "failed")
        self.assertIn("test failed with exit status 1", entry["failure"])
        self.assertEqual(self.started, [])
        number, body = self.published[0]
        self.assertEqual(number, 9)
        self.assertIn("failed", body)
        self.assertNotIn("https://pr-9.paintedpillars.com/", body)
        routes = json.loads((self.deployment_root / "proxy_routes.json").read_text())
        self.assertEqual(routes, {})

    def test_a_repeated_sync_without_pushes_builds_and_publishes_nothing(self):
        self.pulls = [pull(number=9)]
        self.manager.sync()
        first_gate_call_count = len(self.gate_calls)
        first_publish_count = len(self.published)
        self.manager.sync()
        self.assertEqual(len(self.gate_calls), first_gate_call_count)
        self.assertEqual(len(self.published), first_publish_count)


class RebuildCommandTests(ManagerHarness):
    def test_rebuild_forces_a_stopped_environment_back_up(self):
        stopped_entry = self.ready_entry(2, "2026-10-01T00:00:00+00:00", 8102)
        stopped_entry.update(status="stopped", pid=None, published_sha=None, published_status=None)
        self.manager.save_state({"environments": {"2": stopped_entry}})
        self.pulls = [pull(number=2)]
        exit_status = self.manager.main(["rebuild", "2"])
        state = self.manager.load_state()
        self.assertEqual(exit_status, 0)
        self.assertEqual(state["environments"]["2"]["status"], "ready")
        self.assertEqual(state["environments"]["2"]["port"], 8102)
        self.assertEqual(self.started, [2])
        self.assertIn("https://pr-2.paintedpillars.com/", self.published[0][1])

    def test_rebuild_refuses_a_fork_pr_before_checkout_or_execution(self):
        self.pulls = [pull(number=77, owner="someone-else")]
        exit_status = self.manager.main(["rebuild", "77"])
        state = self.manager.load_state()
        self.assertEqual(exit_status, 1)
        self.assertEqual(state["environments"]["77"]["status"], "rejected")
        self.assertFalse((self.deployment_root / "pr-77" / "repo").exists())
        self.assertEqual(self.gate_calls, [])
        self.assertEqual(self.published, [])


class StopCommandTests(ManagerHarness):
    def test_stop_retains_the_environment_for_rebuild(self):
        running_entry = self.ready_entry(2, "2026-11-10T00:00:00+00:00", 8102)
        self.manager.save_state({"environments": {"2": running_entry}})
        exit_status = self.manager.main(["stop", "2"])
        state = self.manager.load_state()
        self.assertEqual(exit_status, 0)
        self.assertEqual(state["environments"]["2"]["status"], "stopped")
        self.assertEqual(state["environments"]["2"]["port"], 8102)
        routes = json.loads((self.deployment_root / "proxy_routes.json").read_text())
        self.assertEqual(routes, {})


if __name__ == "__main__":
    unittest.main()
