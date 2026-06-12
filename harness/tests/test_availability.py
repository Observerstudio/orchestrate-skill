import json
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "orchestrate_run.py"


class DispatchAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name)
        self.repo = self.workspace / "repo"
        self.repo.mkdir()
        self._run_git(["init"], cwd=self.repo)
        self._run_git(["config", "user.email", "test@example.com"], cwd=self.repo)
        self._run_git(["config", "user.name", "Test User"], cwd=self.repo)
        (self.repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        self._run_git(["add", "tracked.txt"], cwd=self.repo)
        self._run_git(["commit", "-m", "initial"], cwd=self.repo)
        self.addCleanup(self._tmpdir.cleanup)

    def _run_git(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=self.workspace,
        )

    def _write_brief(self, name: str, content: str) -> Path:
        path = self.workspace / name
        path.write_text(content, encoding="utf-8")
        return path

    def _base_brief(
        self,
        *,
        task_id: str,
        task_class: str = "scaffold",
        risk: str = "low",
        executor_mode: str = "agentic",
        preferred_executor: str = "codex",
        allowed_paths: list[str] | None = None,
        title: str = "Dispatch brief",
        body_note: str = "",
    ) -> str:
        allowed_paths = allowed_paths or ["harness/orchestrate_run.py", "harness/tests/test_availability.py"]
        allowed_block = "\n".join(f"  - {path}" for path in allowed_paths)
        note_block = f"\n\n{body_note}" if body_note else ""
        return (
            "---\n"
            "orchestrate_version: 0.2\n"
            f"task_id: {task_id}\n"
            f"task_class: {task_class}\n"
            f"risk: {risk}\n"
            f"executor_mode: {executor_mode}\n"
            f"preferred_executor: {preferred_executor}\n"
            "allowed_paths:\n"
            f"{allowed_block}\n"
            "forbidden_paths:\n"
            "  - .env*\n"
            "  - references/**\n"
            "  - templates/**\n"
            "verification:\n"
            "  - python -m unittest discover -s harness/tests -v\n"
            "max_revisions: 2\n"
            "requires_operator_approval: false\n"
            "data_sensitivity: public\n"
            "---\n\n"
            f"# Brief: {title}{note_block}\n"
        )

    def _run_dispatch(self, brief_path: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
        return self._run_cli(
            "dispatch",
            "--repo",
            str(self.repo),
            "--brief",
            str(brief_path),
            *extra_args,
        )

    def _line_value(self, stdout: str, prefix: str) -> str:
        for line in stdout.splitlines():
            if line.startswith(prefix):
                return line.removeprefix(prefix)
        self.fail(f"missing line with prefix {prefix!r}:\n{stdout}")

    def _parse_run_dir(self, stdout: str) -> Path:
        diff_path = Path(self._line_value(stdout, "DIFF ")).resolve()
        return diff_path.parent

    def _parse_worktree_path(self, stdout: str) -> Path:
        for prefix in ("WORKTREE ", "CREATE-WORKTREE "):
            for line in stdout.splitlines():
                if line.startswith(prefix):
                    return Path(line.removeprefix(prefix)).resolve()
        self.fail(f"missing worktree line:\n{stdout}")

    def _force_remove_worktree(self, worktree_path: Path) -> None:
        if not worktree_path.exists():
            return

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "worktree-remove",
                "--repo",
                str(self.repo),
                "--worktree",
                str(worktree_path),
                "--force",
            ],
            capture_output=True,
            text=True,
            cwd=self.workspace,
        )

    def _python_command(self, code: str) -> str:
        return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"

    def test_dispatch_codex_usage_limit_parses_reset_hint_and_writes_availability(self) -> None:
        brief_path = self._write_brief(
            "dispatch-availability-reset.md",
            self._base_brief(
                task_id="dispatch-availability-reset",
                body_note="availability-reset-marker",
            ),
        )
        script = (
            "import pathlib,sys; "
            "pathlib.Path('availability-reset.txt').write_text('reset\\n', encoding='utf-8'); "
            "print('You hit your usage limit. Please try again at 2026-06-13 10:00 UTC.')"
        )

        result = self._run_dispatch(brief_path, "--invoke-cmd", self._python_command(script))
        self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
        self.assertIn("DISPATCH-ABORTED usage-limit (codex-usage-limit, reset 2026-06-13 10:00 UTC)", result.stdout)

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        run_dir = self._parse_run_dir(result.stdout)

        availability_path = run_dir / "availability.json"
        self.assertTrue((run_dir / "logs.txt").exists(), run_dir / "logs.txt")
        self.assertTrue((run_dir / "diff.patch").exists(), run_dir / "diff.patch")
        self.assertTrue(availability_path.exists(), availability_path)

        availability = json.loads(availability_path.read_text(encoding="utf-8"))
        self.assertEqual(
            availability,
            {
                "executor": "codex",
                "signature": "codex-usage-limit",
                "reset_hint": "2026-06-13 10:00 UTC",
                "observed_at": availability["observed_at"],
            },
        )
        self.assertTrue(availability["observed_at"].endswith("Z"))
        datetime.fromisoformat(availability["observed_at"].replace("Z", "+00:00"))

        logs_text = (run_dir / "logs.txt").read_text(encoding="utf-8")
        diff_text = (run_dir / "diff.patch").read_text(encoding="utf-8")
        self.assertIn("You hit your usage limit", logs_text)
        self.assertIn("availability-reset.txt", diff_text)
        self.assertEqual(
            result.stdout.strip().splitlines()[-4:],
            [
                "DISPATCH-ABORTED usage-limit (codex-usage-limit, reset 2026-06-13 10:00 UTC)",
                f"WORKTREE {worktree_path}",
                f"LOGS {run_dir / 'logs.txt'}",
                f"DIFF {run_dir / 'diff.patch'}",
            ],
        )

    def test_dispatch_codex_usage_limit_without_reset_hint_uses_unknown(self) -> None:
        brief_path = self._write_brief(
            "dispatch-availability-unknown.md",
            self._base_brief(
                task_id="dispatch-availability-unknown",
                body_note="availability-unknown-marker",
            ),
        )
        script = (
            "import pathlib,sys; "
            "pathlib.Path('availability-unknown.txt').write_text('unknown\\n', encoding='utf-8'); "
            "print('You hit your usage limit.')"
        )

        result = self._run_dispatch(brief_path, "--invoke-cmd", self._python_command(script))
        self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
        self.assertIn("DISPATCH-ABORTED usage-limit (codex-usage-limit, reset unknown)", result.stdout)

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        run_dir = self._parse_run_dir(result.stdout)

        availability = json.loads((run_dir / "availability.json").read_text(encoding="utf-8"))
        self.assertEqual(availability["executor"], "codex")
        self.assertEqual(availability["signature"], "codex-usage-limit")
        self.assertEqual(availability["reset_hint"], "unknown")
        self.assertIn("availability-unknown.txt", (run_dir / "diff.patch").read_text(encoding="utf-8"))

    def test_dispatch_opencode_balance_signature_writes_unknown_reset_hint(self) -> None:
        brief_path = self._write_brief(
            "dispatch-opencode-balance.md",
            self._base_brief(
                task_id="dispatch-opencode-balance",
                task_class="cheap-exploration",
                executor_mode="advisory",
                preferred_executor="opencode-free-tier",
                body_note="opencode-balance-marker",
            ),
        )
        script = (
            "import pathlib,sys; "
            "pathlib.Path('opencode-balance.txt').write_text('balance\\n', encoding='utf-8'); "
            "print('Insufficient balance')"
        )

        result = self._run_dispatch(brief_path, "--invoke-cmd", self._python_command(script))
        self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
        self.assertIn("DISPATCH-ABORTED usage-limit (opencode-balance, reset unknown)", result.stdout)

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        run_dir = self._parse_run_dir(result.stdout)

        availability = json.loads((run_dir / "availability.json").read_text(encoding="utf-8"))
        self.assertEqual(availability["executor"], "opencode-free-tier")
        self.assertEqual(availability["signature"], "opencode-balance")
        self.assertEqual(availability["reset_hint"], "unknown")
        self.assertIn("Insufficient balance", (run_dir / "logs.txt").read_text(encoding="utf-8"))

    def test_dispatch_no_match_keeps_happy_path_and_skips_availability_file(self) -> None:
        brief_path = self._write_brief(
            "dispatch-no-match.md",
            self._base_brief(
                task_id="dispatch-no-match",
                body_note="no-match-marker",
            ),
        )
        script = (
            "import pathlib,sys; "
            "pathlib.Path('happy-path.txt').write_text('happy\\n', encoding='utf-8'); "
            "print('All clear, nothing to see here.')"
        )

        result = self._run_dispatch(brief_path, "--invoke-cmd", self._python_command(script))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DISPATCHED", result.stdout)

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        run_dir = self._parse_run_dir(result.stdout)

        self.assertTrue((run_dir / "logs.txt").exists(), run_dir / "logs.txt")
        self.assertTrue((run_dir / "diff.patch").exists(), run_dir / "diff.patch")
        self.assertFalse((run_dir / "availability.json").exists(), run_dir / "availability.json")
        self.assertIn("happy-path.txt", (run_dir / "diff.patch").read_text(encoding="utf-8"))
        self.assertEqual(
            result.stdout.strip().splitlines()[-4:],
            [
                f"DISPATCHED {run_dir.name}",
                f"WORKTREE {worktree_path}",
                f"LOGS {run_dir / 'logs.txt'}",
                f"DIFF {run_dir / 'diff.patch'}",
            ],
        )

    def test_dispatch_usage_limit_overrides_timeout_and_keeps_evidence(self) -> None:
        brief_path = self._write_brief(
            "dispatch-usage-limit-timeout.md",
            self._base_brief(
                task_id="dispatch-usage-limit-timeout",
                body_note="usage-limit-timeout-marker",
            ),
        )
        script = (
            "import pathlib,time; "
            "pathlib.Path('timeout-limit.txt').write_text('timeout\\n', encoding='utf-8'); "
            "print('hit your usage limit', flush=True); "
            "time.sleep(2)"
        )

        result = self._run_dispatch(brief_path, "--invoke-cmd", self._python_command(script), "--timeout", "1")
        self.assertEqual(result.returncode, 9, result.stdout + result.stderr)
        self.assertIn("DISPATCH-TIMEOUT after 1s", result.stdout)
        self.assertIn("DISPATCH-ABORTED usage-limit (codex-usage-limit, reset unknown)", result.stdout)

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        run_dir = self._parse_run_dir(result.stdout)

        self.assertTrue((run_dir / "logs.txt").exists(), run_dir / "logs.txt")
        self.assertTrue((run_dir / "diff.patch").exists(), run_dir / "diff.patch")
        self.assertTrue((run_dir / "availability.json").exists(), run_dir / "availability.json")
        self.assertIn("hit your usage limit", (run_dir / "logs.txt").read_text(encoding="utf-8"))
        self.assertIn("timeout-limit.txt", (run_dir / "diff.patch").read_text(encoding="utf-8"))

    def test_dispatch_isolation_breach_overrides_usage_limit(self) -> None:
        brief_path = self._write_brief(
            "dispatch-isolation-precedence.md",
            self._base_brief(
                task_id="dispatch-isolation-precedence",
                body_note="isolation-precedence-marker",
            ),
        )
        script = (
            "import pathlib,sys; "
            "pathlib.Path('tracked.txt').write_text('worktree breach\\n', encoding='utf-8'); "
            f"pathlib.Path({repr(str(self.repo / 'tracked.txt'))}).write_text('repo breach\\n', encoding='utf-8'); "
            "print('You hit your usage limit. Please try again at 2026-06-13 10:00 UTC.')"
        )

        result = self._run_dispatch(brief_path, "--invoke-cmd", self._python_command(script))
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("ISOLATION-BREACH tracked.txt", result.stdout)
        self.assertNotIn("DISPATCH-ABORTED usage-limit", result.stdout)

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d')}-dispatch-isolation-precedence"
        self.assertFalse((self.repo / ".orchestrate" / "runs" / run_id / "availability.json").exists())


if __name__ == "__main__":
    unittest.main()
