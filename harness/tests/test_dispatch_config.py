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


class DispatchConfigCommandTests(unittest.TestCase):
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

    def _run_cli(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=self.workspace,
            env=env,
        )

    def _run_dispatch(
        self,
        brief_path: Path,
        *extra_args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self._run_cli(
            "dispatch",
            "--repo",
            str(self.repo),
            "--brief",
            str(brief_path),
            *extra_args,
            env=env,
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
        allowed_paths = allowed_paths or ["harness/orchestrate_run.py", "harness/tests/test_dispatch_config.py"]
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

    def _write_config(self, name: str, executors: list[dict[str, object]]) -> Path:
        path = self.workspace / name
        frontmatter = yaml.safe_dump({"executors": executors}, sort_keys=False)
        path.write_text(f"---\n{frontmatter}---\n", encoding="utf-8")
        return path

    def _python_command(self, code: str) -> str:
        return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"

    def _cmd_python_command(self, code: str) -> str:
        return f"\"{sys.executable}\" -c \"{code}\""

    def _make_codex_stub(self, marker_name: str = "builtin-marker.txt") -> dict[str, str]:
        bin_dir = self.workspace / "bin"
        bin_dir.mkdir(exist_ok=True)
        marker_literal = repr(marker_name)
        code = (
            "import pathlib, sys; "
            f"pathlib.Path({marker_literal}).write_text('builtin\\n', encoding='utf-8'); "
            "data = sys.stdin.read(); "
            "print('BUILTIN-BEGIN'); "
            "print(data, end='')"
        )
        script = f"@echo off\r\n\"{sys.executable}\" -c \"{code}\" %*\r\n"
        (bin_dir / "codex.cmd").write_text(script, encoding="utf-8")

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        return env

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

    def test_dispatch_uses_config_invoke_over_builtin(self) -> None:
        brief_path = self._write_brief(
            "dispatch-config-override.md",
            self._base_brief(
                task_id="dispatch-config-override",
                body_note="config-override-marker",
            ),
        )
        env = self._make_codex_stub()
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "codex",
                    "invoke": self._python_command(
                        "import pathlib,sys; "
                        "pathlib.Path('config-marker.txt').write_text('config\\n', encoding='utf-8'); "
                        "data = sys.stdin.read(); "
                        "print('CONFIG-BEGIN'); "
                        "print(data, end='')"
                    ),
                    "mode": "agentic",
                }
            ],
        )

        result = self._run_dispatch(brief_path, "--config", str(config_path), env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        run_dir = self._parse_run_dir(result.stdout)

        self.assertTrue((worktree_path / "config-marker.txt").exists())
        self.assertFalse((worktree_path / "builtin-marker.txt").exists())

        logs_text = (run_dir / "logs.txt").read_text(encoding="utf-8")
        self.assertIn("CONFIG-BEGIN", logs_text)
        self.assertIn("config-override-marker", logs_text)

    def test_dispatch_invoke_cmd_wins_over_config(self) -> None:
        brief_path = self._write_brief(
            "dispatch-invoke-wins.md",
            self._base_brief(
                task_id="dispatch-invoke-wins",
                body_note="invoke-wins-marker",
            ),
        )
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "codex",
                    "invoke": self._python_command(
                        "import pathlib,sys; "
                        "pathlib.Path('config-marker.txt').write_text('config\\n', encoding='utf-8'); "
                        "print('CONFIG-BEGIN')"
                    ),
                    "mode": "agentic",
                }
            ],
        )
        invoke_cmd = self._python_command(
            "import pathlib,sys; "
            "pathlib.Path('invoke-marker.txt').write_text('invoke\\n', encoding='utf-8'); "
            "data = sys.stdin.read(); "
            "print('INVOKE-BEGIN'); "
            "print(data, end='')"
        )

        result = self._run_dispatch(
            brief_path,
            "--config",
            str(config_path),
            "--invoke-cmd",
            invoke_cmd,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        run_dir = self._parse_run_dir(result.stdout)

        self.assertTrue((worktree_path / "invoke-marker.txt").exists())
        self.assertFalse((worktree_path / "config-marker.txt").exists())

        logs_text = (run_dir / "logs.txt").read_text(encoding="utf-8")
        self.assertIn("INVOKE-BEGIN", logs_text)
        self.assertIn("invoke-wins-marker", logs_text)

    def test_dispatch_deferred_config_record_aborts(self) -> None:
        brief_path = self._write_brief(
            "dispatch-deferred.md",
            self._base_brief(
                task_id="dispatch-deferred",
                body_note="deferred-marker",
            ),
        )
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "codex",
                    "invoke": self._python_command("print('SHOULD-NOT-RUN')"),
                    "mode": "agentic",
                    "status": "deferred",
                }
            ],
        )

        result = self._run_dispatch(brief_path, "--config", str(config_path))
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("DISPATCH-ABORTED executor-deferred", result.stdout)
        self.assertEqual(list(self.workspace.glob("orchestrate-wt-*")), [])
        self.assertFalse((self.repo / ".orchestrate").exists())

    def test_dispatch_empty_config_invoke_aborts_with_brain_message(self) -> None:
        brief_path = self._write_brief(
            "dispatch-brain-executor.md",
            self._base_brief(
                task_id="dispatch-brain-executor",
                preferred_executor="claude-sonnet-native",
                body_note="brain-executor-marker",
            ),
        )
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "claude-sonnet-native",
                    "invoke": "",
                    "mode": "agentic",
                }
            ],
        )

        result = self._run_dispatch(brief_path, "--config", str(config_path))
        self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
        self.assertIn(
            "DISPATCH-ABORTED brain-executor: claude-sonnet-native is dispatched by the brain via the Agent tool, not the harness",
            result.stdout,
        )
        self.assertEqual(list(self.workspace.glob("orchestrate-wt-*")), [])
        self.assertFalse((self.repo / ".orchestrate").exists())

    def test_dispatch_missing_config_record_falls_back_to_builtin(self) -> None:
        brief_path = self._write_brief(
            "dispatch-fallback.md",
            self._base_brief(
                task_id="dispatch-fallback",
                body_note="builtin-fallback-marker",
            ),
        )
        env = self._make_codex_stub()
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "claude-haiku-native",
                    "invoke": self._python_command("print('IRRELEVANT')"),
                    "mode": "advisory",
                }
            ],
        )

        result = self._run_dispatch(brief_path, "--config", str(config_path), env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        run_dir = self._parse_run_dir(result.stdout)

        self.assertTrue((worktree_path / "builtin-marker.txt").exists())
        self.assertFalse((worktree_path / "irrelevant.txt").exists())

        logs_text = (run_dir / "logs.txt").read_text(encoding="utf-8")
        self.assertIn("BUILTIN-BEGIN", logs_text)
        self.assertIn("builtin-fallback-marker", logs_text)

    def test_invoke_template_treats_redirects_and_cmd_wrapper_as_shell(self) -> None:
        from harness.orchestrate_run import _dispatch_resolve_invoke_template

        self.assertIsInstance(_dispatch_resolve_invoke_template('cmd /c "opencode run --pure -m x \\"p\\" < NUL"'), str)
        self.assertIsInstance(_dispatch_resolve_invoke_template("opencode run x < NUL > out.log"), str)
        self.assertIsInstance(_dispatch_resolve_invoke_template("a | b"), str)
        self.assertIsInstance(_dispatch_resolve_invoke_template("codex exec --sandbox read-only"), list)

    def test_dispatch_shell_pipeline_config_invoke_runs_via_shell(self) -> None:
        brief_path = self._write_brief(
            "dispatch-shell-pipeline.md",
            self._base_brief(
                task_id="dispatch-shell-pipeline",
                body_note="pipeline-input-marker",
            ),
        )
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "codex",
                    "invoke": (
                        self._cmd_python_command(
                            "import sys; data = sys.stdin.read(); print(data, end='')"
                        )
                        + " | "
                        + self._cmd_python_command(
                            "import pathlib,sys; "
                            "data = sys.stdin.read(); "
                            "pathlib.Path('pipeline-input.txt').write_text(data, encoding='utf-8'); "
                            "print('PIPELINE-OK')"
                        )
                    ),
                    "mode": "agentic",
                }
            ],
        )

        result = self._run_dispatch(brief_path, "--config", str(config_path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

        worktree_path = self._parse_worktree_path(result.stdout)
        self.addCleanup(self._force_remove_worktree, worktree_path)
        run_dir = self._parse_run_dir(result.stdout)

        self.assertTrue((worktree_path / "pipeline-input.txt").exists())
        self.assertIn("pipeline-input-marker", (worktree_path / "pipeline-input.txt").read_text(encoding="utf-8"))

        logs_text = (run_dir / "logs.txt").read_text(encoding="utf-8")
        self.assertIn("PIPELINE-OK", logs_text)

    def test_dispatch_dry_run_reports_config_resolved_command(self) -> None:
        brief_path = self._write_brief(
            "dispatch-dry-run-config.md",
            self._base_brief(
                task_id="dispatch-dry-run-config",
                body_note="dry-run-config-marker",
            ),
        )
        config_invoke = self._python_command(
            "import pathlib,sys; "
            "pathlib.Path('dry-run-config.txt').write_text('dry\\n', encoding='utf-8'); "
            "print('DRY-RUN-CONFIG-BEGIN')"
        )
        config_path = self._write_config(
            "executors.local.md",
            [
                {
                    "name": "codex",
                    "invoke": config_invoke,
                    "mode": "agentic",
                }
            ],
        )

        result = self._run_dispatch(brief_path, "--config", str(config_path), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

        self.assertIn("DRY-RUN", result.stdout)
        self.assertIn("dry-run-config.txt", result.stdout)
        self.assertNotIn("codex exec", result.stdout)
        self.assertIn("WORKTREE", result.stdout)
        self.assertEqual(list(self.workspace.glob("orchestrate-wt-*")), [])
        self.assertFalse((self.repo / ".orchestrate").exists())


if __name__ == "__main__":
    unittest.main()
