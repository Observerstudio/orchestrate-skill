from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "orchestrate_run.py"


class SmokeProbeCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name)
        self.addCleanup(self._tmpdir.cleanup)

    def _run_cli(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=self.workspace,
            env=env,
        )

    def _python_command(self, code: str) -> str:
        return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"

    def _write_config(self, name: str, executors: list[dict[str, object]]) -> Path:
        path = self.workspace / name
        content = yaml.safe_dump({"executors": executors}, sort_keys=False)
        path.write_text(f"---\n{content}---\n", encoding="utf-8")
        return path

    def _read_config_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_smoke_probe_success_records_last_verified_and_passes_stdin_prompt(self) -> None:
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "alpha",
                    "invoke": self._python_command(
                        "import pathlib,sys; "
                        "data = sys.stdin.read(); "
                        "pathlib.Path('stdin.txt').write_text(data, encoding='utf-8'); "
                        "print('PONG')"
                    ),
                }
            ],
        )

        result = self._run_cli("smoke-probe", "--config", str(config_path), "--now", "2026-06-12T12:00:00Z")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PROBE-OK alpha (", result.stdout)
        self.assertIn("PROBED 1 OK 1 FAIL 0", result.stdout)

        config_text = self._read_config_text(config_path)
        self.assertEqual(config_text.count("last_verified:"), 1)
        self.assertIn("last_verified:", config_text)
        self.assertEqual((self.workspace / "stdin.txt").read_text(encoding="utf-8"), "reply with exactly: PONG")

    def test_smoke_probe_missing_pong_does_not_update_last_verified(self) -> None:
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "beta",
                    "invoke": self._python_command(
                        "import pathlib,sys; "
                        "data = sys.stdin.read(); "
                        "pathlib.Path('stdin.txt').write_text(data, encoding='utf-8'); "
                        "print('NOPE')"
                    ),
                }
            ],
        )

        result = self._run_cli("smoke-probe", "--config", str(config_path), "--now", "2026-06-12T12:00:00Z")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("PROBE-FAIL beta: missing PONG", result.stdout)
        self.assertIn("PROBED 1 OK 0 FAIL 1", result.stdout)
        self.assertNotIn("last_verified:", self._read_config_text(config_path))
        self.assertEqual((self.workspace / "stdin.txt").read_text(encoding="utf-8"), "reply with exactly: PONG")

    def test_smoke_probe_timeout_reports_failure_and_does_not_update_config(self) -> None:
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "slow",
                    "invoke": self._python_command(
                        "import pathlib,sys,time; "
                        "sys.stdin.read(); "
                        "time.sleep(2); "
                        "pathlib.Path('timeout.txt').write_text('done', encoding='utf-8'); "
                        "print('PONG')"
                    ),
                }
            ],
        )

        result = self._run_cli(
            "smoke-probe",
            "--config",
            str(config_path),
            "--timeout",
            "0.2",
            "--now",
            "2026-06-12T12:00:00Z",
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("PROBE-FAIL slow: timeout after 0.2s", result.stdout)
        self.assertIn("PROBED 1 OK 0 FAIL 1", result.stdout)
        self.assertNotIn("last_verified:", self._read_config_text(config_path))
        self.assertFalse((self.workspace / "timeout.txt").exists())

    def test_smoke_probe_default_selection_skips_deferred_brain_and_fresh_records(self) -> None:
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "deferred",
                    "status": "deferred",
                    "invoke": self._python_command("print('SHOULD-NOT-RUN')"),
                },
                {
                    "name": "brain",
                    "invoke": "",
                },
                {
                    "name": "fresh",
                    "last_verified": "2026-06-12T11:30:00Z",
                    "invoke": self._python_command(
                        "import pathlib,sys; "
                        "pathlib.Path('fresh.txt').write_text('ran', encoding='utf-8'); "
                        "print('PONG')"
                    ),
                },
            ],
        )

        result = self._run_cli("smoke-probe", "--config", str(config_path), "--now", "2026-06-12T12:00:00Z")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DEFERRED deferred", result.stdout)
        self.assertIn("SKIPPED brain (brain-executor)", result.stdout)
        self.assertIn("FRESH fresh (verified 30m ago)", result.stdout)
        self.assertIn("PROBED 0 OK 0 FAIL 0", result.stdout)
        self.assertFalse((self.workspace / "fresh.txt").exists())
        self.assertEqual(self._read_config_text(config_path).count("last_verified:"), 1)

    def test_smoke_probe_explicit_executor_targets_only_one_record(self) -> None:
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "other",
                    "invoke": self._python_command(
                        "import pathlib,sys; "
                        "pathlib.Path('other.txt').write_text(sys.stdin.read(), encoding='utf-8'); "
                        "print('PONG')"
                    ),
                },
                {
                    "name": "target",
                    "invoke": self._python_command(
                        "import pathlib,sys; "
                        "pathlib.Path('target.txt').write_text(sys.stdin.read(), encoding='utf-8'); "
                        "print('PONG')"
                    ),
                },
            ],
        )

        result = self._run_cli(
            "smoke-probe",
            "--config",
            str(config_path),
            "--executor",
            "target",
            "--now",
            "2026-06-12T12:00:00Z",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PROBE-OK target (", result.stdout)
        self.assertIn("PROBED 1 OK 1 FAIL 0", result.stdout)
        self.assertFalse((self.workspace / "other.txt").exists())
        self.assertTrue((self.workspace / "target.txt").exists())
        self.assertEqual(self._read_config_text(config_path).count("last_verified:"), 1)


if __name__ == "__main__":
    unittest.main()
