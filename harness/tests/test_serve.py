from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "orchestrate_run.py"


class ServeCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name)
        self.repo = self.workspace / "repo"
        self.repo.mkdir()
        self.addCleanup(self._tmpdir.cleanup)

    def _run_cli(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=self.workspace,
            env=env,
        )

    def _serve_state_path(self) -> Path:
        return self.repo / ".orchestrate" / "serve" / "opencode-serve.json"

    def _serve_cmd(self, seconds: int = 60) -> str:
        script = f"import time; time.sleep({seconds})"
        return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"

    def _read_state(self) -> dict[str, object]:
        return json.loads(self._serve_state_path().read_text(encoding="utf-8"))

    def _ensure_stopped(self) -> None:
        if self._serve_state_path().exists():
            self._run_cli("serve-stop", "--repo", str(self.repo))

    def test_serve_start_status_stop_lifecycle_uses_stub_process(self) -> None:
        command = self._serve_cmd()
        start = time.monotonic()
        result = self._run_cli(
            "serve-start",
            "--repo",
            str(self.repo),
            "--port",
            "4096",
            "--host",
            "127.0.0.1",
            "--serve-cmd",
            command,
        )
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 5, result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SERVE-STARTED ", result.stdout)
        self.assertIn(" on 127.0.0.1:4096", result.stdout)
        self.assertTrue(self._serve_state_path().exists(), self._serve_state_path())
        self.addCleanup(self._ensure_stopped)

        state = self._read_state()
        self.assertEqual(state["port"], 4096)
        self.assertEqual(state["host"], "127.0.0.1")
        self.assertIn("started_at", state)
        self.assertIn("cmd", state)
        self.assertIn("time.sleep(60)", str(state["cmd"]))

        pid = state["pid"]
        self.assertIsInstance(pid, int)

        second = self._run_cli(
            "serve-start",
            "--repo",
            str(self.repo),
            "--port",
            "4096",
            "--host",
            "127.0.0.1",
            "--serve-cmd",
            command,
        )
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn(f"SERVE-ALREADY-RUNNING {pid} on 127.0.0.1:4096", second.stdout)
        self.assertEqual(self._read_state()["pid"], pid)

        status = self._run_cli("serve-status", "--repo", str(self.repo))
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertIn(f"SERVE-UP {pid} on 127.0.0.1:4096 (since ", status.stdout)

        stop = self._run_cli("serve-stop", "--repo", str(self.repo))
        self.assertEqual(stop.returncode, 0, stop.stdout + stop.stderr)
        self.assertEqual(stop.stdout.strip(), f"SERVE-STOPPED {pid}")
        self.assertFalse(self._serve_state_path().exists())

        down = self._run_cli("serve-status", "--repo", str(self.repo))
        self.assertEqual(down.returncode, 0, down.stdout + down.stderr)
        self.assertEqual(down.stdout.strip(), "SERVE-DOWN")

    def test_serve_status_cleans_stale_pidfile(self) -> None:
        state_path = self._serve_state_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "pid": 99999999,
                    "port": 4096,
                    "host": "127.0.0.1",
                    "started_at": "2026-06-12T00:00:00Z",
                    "cmd": "stub",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        result = self._run_cli("serve-status", "--repo", str(self.repo))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "SERVE-STALE 99999999")
        self.assertFalse(state_path.exists())

    def test_serve_start_without_override_aborts_when_opencode_is_missing(self) -> None:
        env = os.environ.copy()
        env["PATH"] = ""

        result = self._run_cli("serve-start", "--repo", str(self.repo), env=env)
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "SERVE-ABORTED opencode-not-found")
        self.assertFalse(self._serve_state_path().exists())


if __name__ == "__main__":
    unittest.main()
