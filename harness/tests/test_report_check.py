from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "orchestrate_run.py"


class ReportCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name)
        self.repo = self.workspace / "repo"
        self.repo.mkdir()
        self.addCleanup(self._tmpdir.cleanup)

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=self.workspace,
        )

    def _write_brief(
        self,
        run_id: str,
        *,
        allowed_paths: list[str] | None = None,
        verification: list[str] | None = None,
    ) -> Path:
        allowed_paths = allowed_paths or ["harness/orchestrate_run.py", "harness/tests/**"]
        verification = verification or ["python -m unittest discover -s harness/tests -v"]
        allowed_block = "\n".join(f"  - {path}" for path in allowed_paths)
        verification_block = "\n".join(f"  - {cmd}" for cmd in verification)
        brief = (
            "---\n"
            "orchestrate_version: 0.2\n"
            f"task_id: {run_id}\n"
            "task_class: scaffold\n"
            "risk: low\n"
            "executor_mode: agentic\n"
            "preferred_executor: codex\n"
            "allowed_paths:\n"
            f"{allowed_block}\n"
            "forbidden_paths:\n"
            "  - .env*\n"
            "  - references/**\n"
            "  - templates/**\n"
            "verification:\n"
            f"{verification_block}\n"
            "max_revisions: 2\n"
            "requires_operator_approval: false\n"
            "data_sensitivity: public\n"
            "---\n\n"
            f"# Brief: {run_id}\n"
        )
        path = self.workspace / f"{run_id}.md"
        path.write_text(brief, encoding="utf-8")
        return path

    def _write_run_files(
        self,
        run_id: str,
        *,
        report: dict[str, object] | None = None,
        touched_files: list[str] | None = None,
    ) -> Path:
        run_dir = self.repo / ".orchestrate" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if touched_files is not None:
            touched_text = "\n".join(touched_files) + ("\n" if touched_files else "")
            (run_dir / "touched-files.txt").write_text(touched_text, encoding="utf-8")
        if report is not None:
            (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return run_dir

    def _run_report_check(self, run_id: str, brief_path: Path) -> subprocess.CompletedProcess[str]:
        return self._run_cli(
            "report-check",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
            "--brief",
            str(brief_path),
        )

    def test_report_check_happy_path_reports_ok(self) -> None:
        run_id = "run-ok"
        brief_path = self._write_brief(run_id)
        self._write_run_files(
            run_id,
            touched_files=["harness/orchestrate_run.py", "harness/tests/sub/x.py"],
            report={
                "runId": run_id,
                "executor": "codex",
                "status": "completed",
                "scopeCheck": "pass",
                "verification": [
                    {"cmd": "python -m unittest discover -s harness/tests -v", "status": "pass"},
                ],
                "touchedFiles": ["harness/orchestrate_run.py", "harness/tests/sub/x.py"],
                "diffPath": "diff.patch",
                "logsPath": "logs.txt",
            },
        )

        result = self._run_report_check(run_id, brief_path)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            result.stdout.strip().splitlines(),
            [
                f"REPORT-OK {run_id}",
                "NOTE: pass means claims are consistent — the brain still re-runs verification and reviews the diff.",
            ],
        )

    def test_report_check_missing_report_is_terminal(self) -> None:
        run_id = "missing-report"
        brief_path = self._write_brief(run_id)

        result = self._run_report_check(run_id, brief_path)
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertIn("REPORT-FAIL report-missing: report.json absent or unparseable JSON", result.stdout)
        self.assertIn("REPORT-BLOCKED (1 failures)", result.stdout)
        self.assertTrue(
            result.stdout.strip().endswith(
                "NOTE: pass means claims are consistent — the brain still re-runs verification and reviews the diff."
            ),
            result.stdout,
        )

    def test_report_check_bad_schema_is_reported(self) -> None:
        run_id = "bad-schema"
        brief_path = self._write_brief(run_id)
        self._write_run_files(
            run_id,
            touched_files=["harness/orchestrate_run.py"],
            report={
                "runId": run_id,
                "executor": "codex",
                "status": "completed",
                "scopeCheck": "pass",
                "verification": [{"cmd": "python -m unittest discover -s harness/tests -v", "status": "pass"}],
                "touchedFiles": ["harness/orchestrate_run.py"],
                "diffPath": "diff.patch",
            },
        )

        result = self._run_report_check(run_id, brief_path)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("REPORT-FAIL report-schema:", result.stdout)
        self.assertIn("missing required keys: logsPath", result.stdout)
        self.assertIn("REPORT-BLOCKED (1 failures)", result.stdout)

    def test_report_check_flags_overclaim_and_underclaim(self) -> None:
        run_id = "claim-gap"
        brief_path = self._write_brief(
            run_id,
            allowed_paths=["harness/orchestrate_run.py", "actual-only.py", "claimed-only.py"],
        )
        self._write_run_files(
            run_id,
            touched_files=["actual-only.py", "harness/orchestrate_run.py"],
            report={
                "runId": run_id,
                "executor": "codex",
                "status": "completed",
                "scopeCheck": "pass",
                "verification": [{"cmd": "python -m unittest discover -s harness/tests -v", "status": "pass"}],
                "touchedFiles": ["claimed-only.py", "harness/orchestrate_run.py"],
                "diffPath": "diff.patch",
                "logsPath": "logs.txt",
            },
        )

        result = self._run_report_check(run_id, brief_path)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("REPORT-FAIL claim-vs-ground-truth:", result.stdout)
        self.assertIn("overclaimed: ['claimed-only.py']", result.stdout)
        self.assertIn("underclaimed (dangerous): ['actual-only.py']", result.stdout)
        self.assertIn("REPORT-BLOCKED (1 failures)", result.stdout)

    def test_report_check_scope_violation_uses_ground_truth(self) -> None:
        run_id = "scope-violation"
        brief_path = self._write_brief(run_id)
        self._write_run_files(
            run_id,
            touched_files=["docs/notes.md"],
            report={
                "runId": run_id,
                "executor": "codex",
                "status": "completed",
                "scopeCheck": "pass",
                "verification": [{"cmd": "python -m unittest discover -s harness/tests -v", "status": "pass"}],
                "touchedFiles": ["docs/notes.md"],
                "diffPath": "diff.patch",
                "logsPath": "logs.txt",
            },
        )

        result = self._run_report_check(run_id, brief_path)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("REPORT-FAIL scope-violation:", result.stdout)
        self.assertIn("ground truth outside allowed_paths: ['docs/notes.md']", result.stdout)
        self.assertIn("REPORT-BLOCKED (1 failures)", result.stdout)

    def test_report_check_verification_set_mismatch_is_reported(self) -> None:
        run_id = "verification-mismatch"
        brief_path = self._write_brief(
            run_id,
            verification=[
                "python -m unittest discover -s harness/tests -v",
                "python -m unittest discover -s harness/tests -v --dry-run",
            ],
        )
        self._write_run_files(
            run_id,
            touched_files=["harness/orchestrate_run.py"],
            report={
                "runId": run_id,
                "executor": "codex",
                "status": "completed",
                "scopeCheck": "pass",
                "verification": [
                    {"cmd": "python -m unittest discover -s harness/tests -v", "status": "pass"},
                ],
                "touchedFiles": ["harness/orchestrate_run.py"],
                "diffPath": "diff.patch",
                "logsPath": "logs.txt",
            },
        )

        result = self._run_report_check(run_id, brief_path)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("REPORT-FAIL verification-mismatch:", result.stdout)
        self.assertIn("REPORT-BLOCKED (1 failures)", result.stdout)

    def test_report_check_claimed_fail_is_surfaced(self) -> None:
        run_id = "claimed-fail"
        brief_path = self._write_brief(run_id)
        self._write_run_files(
            run_id,
            touched_files=["harness/orchestrate_run.py"],
            report={
                "runId": run_id,
                "executor": "codex",
                "status": "partial",
                "scopeCheck": "pass",
                "verification": [{"cmd": "python -m unittest discover -s harness/tests -v", "status": "pass"}],
                "touchedFiles": ["harness/orchestrate_run.py"],
                "diffPath": "diff.patch",
                "logsPath": "logs.txt",
            },
        )

        result = self._run_report_check(run_id, brief_path)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("REPORT-FAIL claimed-fail:", result.stdout)
        self.assertIn("body itself reports status=partial", result.stdout)
        self.assertIn("REPORT-BLOCKED (1 failures)", result.stdout)


if __name__ == "__main__":
    unittest.main()
