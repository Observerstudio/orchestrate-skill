from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "orchestrate_run.py"


class DispatchCommandTests(unittest.TestCase):
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
        allowed_paths = allowed_paths or ["harness/orchestrate_run.py", "harness/tests/test_dispatch.py"]
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

    def _parse_worktree_path(self, stdout: str) -> Path:
        return Path(self._line_value(stdout, "WORKTREE ")).resolve()

    def _parse_run_dir(self, stdout: str) -> Path:
        diff_path = Path(self._line_value(stdout, "DIFF ")).resolve()
        return diff_path.parent

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

    def test_dispatch_happy_path_writes_stub_output_and_keeps_worktree(self) -> None:
        brief_path = self._write_brief(
            "dispatch-happy.md",
            self._base_brief(
                task_id="dispatch-happy-path",
                body_note="stdin-piped-marker",
            ),
        )
        script = (
            "import pathlib,sys; "
            "pathlib.Path('created-by-stub.txt').write_text('from stub\\n', encoding='utf-8'); "
            "data = sys.stdin.read(); "
            "print('STDIN-BEGIN'); "
            "print(data, end='')"
        )
        invoke_cmd = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"

        result = self._run_dispatch(brief_path, "--invoke-cmd", invoke_cmd)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        self.assertTrue(worktree_path.exists(), worktree_path)

        run_dir = self._parse_run_dir(result.stdout)
        expected_date = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.assertEqual(run_dir.name, f"{expected_date}-dispatch-happy-path")
        self.assertTrue((run_dir / "logs.txt").exists(), run_dir / "logs.txt")
        self.assertTrue((run_dir / "diff.patch").exists(), run_dir / "diff.patch")
        self.assertTrue((worktree_path / "created-by-stub.txt").exists())

        logs_text = (run_dir / "logs.txt").read_text(encoding="utf-8")
        diff_text = (run_dir / "diff.patch").read_text(encoding="utf-8")
        self.assertIn("STDIN-BEGIN", logs_text)
        self.assertIn("stdin-piped-marker", logs_text)
        self.assertIn("created-by-stub.txt", diff_text)
        self.assertIn("new file mode", diff_text)

        self.assertEqual(
            result.stdout.strip().splitlines()[-4:],
            [
                f"DISPATCHED {run_dir.name}",
                f"WORKTREE {worktree_path}",
                f"LOGS {run_dir / 'logs.txt'}",
                f"DIFF {run_dir / 'diff.patch'}",
            ],
        )

    def test_dispatch_validation_blocker_aborts_before_worktree_creation(self) -> None:
        brief_path = self._write_brief(
            "dispatch-invalid.md",
            """\
---
orchestrate_version: 0.2
task_id: dispatch-invalid
task_class: scaffold
risk: low
executor_mode: agentic
preferred_executor: codex
forbidden_paths:
  - .env*
verification:
  - python -m unittest discover -s harness/tests -v
max_revisions: 2
requires_operator_approval: false
data_sensitivity: public
---

# Brief: Invalid dispatch brief
""",
        )

        result = self._run_dispatch(brief_path)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("BLOCKER empty-allowed-paths:", result.stdout)
        self.assertIn("DISPATCH-ABORTED validation", result.stdout)
        self.assertEqual(list(self.workspace.glob("orchestrate-wt-*")), [])
        self.assertFalse((self.repo / ".orchestrate").exists())

    def test_dispatch_without_builtin_invoke_command_exits_five(self) -> None:
        brief_path = self._write_brief(
            "dispatch-no-invoke.md",
            self._base_brief(
                task_id="dispatch-no-invoke",
                task_class="cheap-exploration",
                executor_mode="advisory",
                preferred_executor="claude-haiku-native",
                title="Dispatch needs explicit invoke command",
            ),
        )

        result = self._run_dispatch(brief_path)
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("DISPATCH-ABORTED no-invoke-command", result.stdout)
        self.assertEqual(list(self.workspace.glob("orchestrate-wt-*")), [])
        self.assertFalse((self.repo / ".orchestrate").exists())

    def test_dispatch_timeout_still_captures_diff(self) -> None:
        brief_path = self._write_brief(
            "dispatch-timeout.md",
            self._base_brief(
                task_id="dispatch-timeout",
                body_note="timeout-marker",
            ),
        )
        script = (
            "import pathlib,time; "
            "pathlib.Path('timeout-file.txt').write_text('timeout\\n', encoding='utf-8'); "
            "print('before-sleep', flush=True); "
            "time.sleep(2)"
        )
        invoke_cmd = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"

        result = self._run_dispatch(brief_path, "--invoke-cmd", invoke_cmd, "--timeout", "1")
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("DISPATCH-TIMEOUT after 1s", result.stdout)

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        self.assertTrue(worktree_path.exists(), worktree_path)

        run_dir = self._parse_run_dir(result.stdout)
        self.assertTrue((run_dir / "logs.txt").exists(), run_dir / "logs.txt")
        self.assertTrue((run_dir / "diff.patch").exists(), run_dir / "diff.patch")

        logs_text = (run_dir / "logs.txt").read_text(encoding="utf-8")
        diff_text = (run_dir / "diff.patch").read_text(encoding="utf-8")
        self.assertIn("before-sleep", logs_text)
        self.assertIn("timeout-file.txt", diff_text)
        self.assertIn("new file mode", diff_text)

    def test_dispatch_dry_run_only_reports_command_and_pattern(self) -> None:
        brief_path = self._write_brief(
            "dispatch-dry-run.md",
            self._base_brief(
                task_id="dispatch-dry-run",
                title="Dispatch dry run",
            ),
        )
        result = self._run_dispatch(brief_path, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

        expected_date = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.assertIn("DRY-RUN codex exec --skip-git-repo-check --sandbox workspace-write", result.stdout)
        self.assertIn(f"orchestrate-wt-{expected_date}-dispatch-dry-run-*", result.stdout)
        self.assertEqual(list(self.workspace.glob("orchestrate-wt-*")), [])
        self.assertFalse((self.repo / ".orchestrate").exists())


if __name__ == "__main__":
    unittest.main()
