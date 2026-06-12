from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "orchestrate_run.py"


def _run_smoke_status(config_path: Path, now: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "smoke-status", "--config", str(config_path), "--now", now],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def _run_smoke_record(config_path: Path, executor: str, now: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "smoke-record",
            "--config",
            str(config_path),
            "--executor",
            executor,
            "--now",
            now,
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def _extract_body(text: str) -> str:
    lines = text.splitlines(keepends=True)
    closing_markers = 0
    for index, line in enumerate(lines):
        if line.strip() == "---":
            closing_markers += 1
            if closing_markers == 2:
                return "".join(lines[index + 1 :])
    raise AssertionError("frontmatter body not found")


class SmokeWindowTests(unittest.TestCase):
    def test_smoke_status_reports_fresh_stale_unverified_and_deferred(self) -> None:
        config = textwrap.dedent(
            """\
            ---
            executors:
              - name: fresh
                last_verified: 2026-06-11T13:00:00Z
              - name: stale
                last_verified: 2026-06-10T10:00:00Z
              - name: unverified
              - name: deferred
                status: deferred
                last_verified: 2026-06-11T00:00:00Z
            ---

            Operator notes should stay untouched.
            """
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "executors.local.md"
            config_path.write_text(config, encoding="utf-8")

            result = _run_smoke_status(config_path, "2026-06-12T12:00:00Z")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout.strip().splitlines(),
            [
                "FRESH fresh (verified 23h ago)",
                "STALE stale (verified 2d 2h ago)",
                "UNVERIFIED unverified",
                "DEFERRED deferred",
                "PROBE-NEEDED 2",
            ],
        )

    def test_smoke_status_missing_config_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "missing.executors.local.md"
            result = _run_smoke_status(config_path, "2026-06-12T12:00:00Z")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ERROR:", result.stdout)

    def test_smoke_record_updates_last_verified_without_mangling_body(self) -> None:
        config = textwrap.dedent(
            """\
            ---
            executors:
              - name: fresh
                role: primary-code
              - name: other
                status: deferred
            ---

            # Operator notes

            Keep this section byte-for-byte stable.
            """
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "executors.local.md"
            config_path.write_text(config, encoding="utf-8")
            original_text = config_path.read_text(encoding="utf-8")
            original_body = _extract_body(original_text)

            record_result = _run_smoke_record(config_path, "fresh", "2026-06-12T12:00:00Z")
            updated_text = config_path.read_text(encoding="utf-8")
            updated_body = _extract_body(updated_text)
            status_result = _run_smoke_status(config_path, "2026-06-12T12:30:00Z")

        self.assertEqual(record_result.returncode, 0, record_result.stdout + record_result.stderr)
        self.assertEqual(record_result.stdout.strip(), "RECORDED fresh 2026-06-12T12:00:00Z")
        self.assertEqual(original_body, updated_body)
        self.assertEqual(status_result.returncode, 0, status_result.stdout + status_result.stderr)
        self.assertIn("FRESH fresh (verified 30m ago)", status_result.stdout)

    def test_smoke_record_missing_executor_exits_one(self) -> None:
        config = textwrap.dedent(
            """\
            ---
            executors:
              - name: fresh
            ---

            Notes.
            """
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "executors.local.md"
            config_path.write_text(config, encoding="utf-8")
            result = _run_smoke_record(config_path, "missing", "2026-06-12T12:00:00Z")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ERROR executor not found: missing", result.stdout)


if __name__ == "__main__":
    unittest.main()
