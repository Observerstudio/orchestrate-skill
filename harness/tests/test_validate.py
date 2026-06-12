from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from harness.orchestrate_run import validate_frontmatter


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "orchestrate_run.py"
FIXTURES = ROOT / "harness" / "tests" / "fixtures"


def _run_validate(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


class ValidateBriefTests(unittest.TestCase):
    def test_valid_briefs_dispatch_and_exit_zero(self) -> None:
        for fixture_name in ("valid-agentic.md", "valid-advisory.md"):
            with self.subTest(fixture=fixture_name):
                result = _run_validate(FIXTURES / fixture_name)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip().splitlines()[-1], "DISPATCHABLE")

    def test_invalid_fixtures_report_expected_rule_ids(self) -> None:
        expectations = {
            "invalid-enum.md": "uninstantiated-enum",
            "invalid-missing.md": "missing-field",
            "invalid-mismatch.md": "mode-mismatch",
        }
        for fixture_name, rule_id in expectations.items():
            with self.subTest(fixture=fixture_name):
                result = _run_validate(FIXTURES / fixture_name)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(f"BLOCKER {rule_id}:", result.stdout)
                self.assertTrue(result.stdout.strip().endswith("BLOCKED (1 blockers)"), result.stdout)

    def test_version_mismatch_warns_without_blocking(self) -> None:
        brief = """\
---
orchestrate_version: 0.3
task_id: version-warning
task_class: scaffold
risk: low
executor_mode: agentic
preferred_executor: codex
allowed_paths:
  - harness/orchestrate_run.py
forbidden_paths:
  - .env*
verification:
  - python -m unittest discover -s harness/tests -v
max_revisions: 2
requires_operator_approval: false
data_sensitivity: public
---

# Brief: Version warning
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            brief_path = Path(tmpdir) / "brief.md"
            brief_path.write_text(brief, encoding="utf-8")
            result = _run_validate(brief_path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WARNING version-mismatch:", result.stdout)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "DISPATCHABLE")

    def test_sonnet_native_is_valid_agentic_fallback_for_codex_classes(self) -> None:
        findings = validate_frontmatter(
            {
                "orchestrate_version": "0.2",
                "task_id": "sonnet-fallback",
                "task_class": "bugfix-isolated",
                "risk": "low",
                "executor_mode": "agentic",
                "preferred_executor": "claude-sonnet-native",
                "allowed_paths": ["src/fix.ts"],
                "forbidden_paths": [".env*"],
                "verification": ["npm run typecheck"],
                "max_revisions": 2,
                "requires_operator_approval": False,
                "data_sensitivity": "public",
            }
        )

        self.assertFalse(any(finding["severity"] == "BLOCKER" for finding in findings), findings)

    def test_pipe_in_verification_command_is_not_an_enum_blocker(self) -> None:
        findings = validate_frontmatter(
            {
                "orchestrate_version": "0.2",
                "task_id": "pipe-in-command",
                "task_class": "scaffold",
                "risk": "low",
                "executor_mode": "agentic",
                "preferred_executor": "codex",
                "allowed_paths": ["harness/orchestrate_run.py"],
                "forbidden_paths": [".env*"],
                "verification": ["Get-Content brief.md -Raw | codex exec --sandbox read-only"],
                "max_revisions": 2,
                "requires_operator_approval": False,
                "data_sensitivity": "public",
            }
        )

        self.assertFalse(any(finding["rule_id"] == "uninstantiated-enum" for finding in findings), findings)

    def test_null_optional_is_blocker_in_pure_function(self) -> None:
        findings = validate_frontmatter(
            {
                "orchestrate_version": "0.2",
                "task_id": "null-optional",
                "task_class": "scaffold",
                "risk": "low",
                "executor_mode": "agentic",
                "preferred_executor": "codex",
                "fallback_executor": "",
                "allowed_paths": ["harness/orchestrate_run.py"],
                "forbidden_paths": [".env*"],
                "verification": ["python -m unittest discover -s harness/tests -v"],
                "max_revisions": 2,
                "requires_operator_approval": False,
                "data_sensitivity": "public",
            }
        )

        self.assertTrue(any(finding["rule_id"] == "null-optional" for finding in findings), findings)


if __name__ == "__main__":
    unittest.main()
