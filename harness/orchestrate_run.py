from __future__ import annotations

import argparse
import secrets
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


CURRENT_ORCHESTRATE_VERSION = "0.2"
WORKTREE_PREFIX = "orchestrate-wt-"

# Derived from references/task-classes.md + executor-capabilities.md — those docs are canonical.
EXECUTOR_ALLOWED_TASK_CLASSES: dict[str, set[str]] = {
    "codex": {
        "mechanical-refactor",
        "scaffold",
        "test-generation",
        "bugfix-isolated",
        "docs-prose",
    },
    "codex-readonly": {
        "review-diff",
        "second-opinion",
        "cheap-exploration",
    },
    "claude-haiku-native": {
        "cheap-exploration",
        "docs-prose",
    },
    "opencode-free-tier": {
        "cheap-exploration",
        "docs-prose",
    },
}

KNOWN_EXECUTORS = set(EXECUTOR_ALLOWED_TASK_CLASSES)
EXECUTOR_MODES: dict[str, str] = {
    "codex": "agentic",
    "codex-readonly": "advisory",
    "claude-haiku-native": "advisory",
    "opencode-free-tier": "advisory",
}
VALID_TASK_CLASSES = {
    "mechanical-refactor",
    "scaffold",
    "test-generation",
    "bugfix-isolated",
    "docs-prose",
    "review-diff",
    "second-opinion",
    "cheap-exploration",
    "domain-sensitive",
    "db-sensitive",
    "security-sensitive",
    "money-sensitive",
    "architecture-decision",
}
VALID_RISKS = {"low", "medium", "high"}
VALID_EXECUTOR_MODES = {"agentic", "advisory"}
VALID_DATA_SENSITIVITY = {"public", "proprietary", "sensitive"}
REQUIRED_SCALAR_FIELDS = [
    "orchestrate_version",
    "task_id",
    "task_class",
    "risk",
    "executor_mode",
    "preferred_executor",
    "max_revisions",
    "requires_operator_approval",
    "data_sensitivity",
]


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - exercised through CLI tests
        raise ValueError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:  # pragma: no cover
        if message:
            raise ValueError(message.strip())
        raise ValueError(f"parser exited with status {status}")


def _finding(severity: str, rule_id: str, message: str) -> dict[str, str]:
    return {"severity": severity, "rule_id": rule_id, "message": message}


def _is_empty_scalar(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


# Only these fields use the template's `a | b | c` allowed-values notation.
# Free-form fields (verification commands, paths) may legitimately contain `|`.
ENUM_NOTATION_FIELDS = (
    "task_class",
    "risk",
    "executor_mode",
    "preferred_executor",
    "fallback_executor",
    "data_sensitivity",
)


def _contains_uninstantiated_enum(value: Any) -> bool:
    return isinstance(value, str) and "|" in value


def _normalize_text(value: Any) -> str:
    return str(value).strip()


def _utc_isoformat_seconds(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if not isinstance(value, str):
        raise ValueError(f"invalid ISO-8601 timestamp: {value!r}")

    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_age(delta: timedelta) -> str:
    total_seconds = max(0, int(delta.total_seconds()))
    days, remainder = divmod(total_seconds, 24 * 60 * 60)
    hours, remainder = divmod(remainder, 60 * 60)
    minutes, seconds = divmod(remainder, 60)

    if days:
        return f"{days}d" if hours == 0 else f"{days}d {hours}h"
    if hours:
        return f"{hours}h" if minutes == 0 else f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def _repo_path(value: str) -> Path:
    return Path(value).resolve()


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, cwd=cwd)


def _git_error(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr.strip() or result.stdout.strip() or "git command failed"


def _status_paths(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        path_text = line[3:].strip() if len(line) >= 3 else line.strip()
        if path_text:
            paths.append(path_text)
    return paths


def _worktree_list_paths(output: str) -> list[Path]:
    worktree_paths: list[Path] = []
    for line in output.splitlines():
        if line.startswith("worktree "):
            worktree_paths.append(Path(line.removeprefix("worktree ")).resolve())
    return worktree_paths


def _is_generated_worktree(worktree_path: Path, repo_path: Path) -> bool:
    return worktree_path != repo_path and worktree_path.name.startswith(WORKTREE_PREFIX)


def _create_worktree(repo_path: Path, run_id: str) -> tuple[int, str]:
    worktree_path = repo_path.parent / f"{WORKTREE_PREFIX}{run_id}-{secrets.token_hex(4)}"
    result = _run_git(["git", "-C", str(repo_path), "worktree", "add", str(worktree_path), "HEAD"], cwd=repo_path)
    if result.returncode != 0:
        return 1, f"ERROR {result.stderr.strip()}"

    return 0, f"WORKTREE {worktree_path.resolve()}"


def _capture_worktree(repo_path: Path, worktree_path: Path, run_id: str) -> tuple[int, str]:
    run_dir = repo_path / ".orchestrate" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    add_result = _run_git(["git", "-C", str(worktree_path), "add", "-N", "."], cwd=repo_path)
    if add_result.returncode != 0:
        return 1, f"ERROR {_git_error(add_result)}"

    diff_result = _run_git(["git", "-C", str(worktree_path), "diff"], cwd=repo_path)
    if diff_result.returncode != 0:
        return 1, f"ERROR {_git_error(diff_result)}"

    diff_patch_path = run_dir / "diff.patch"
    diff_patch_path.write_text(diff_result.stdout, encoding="utf-8")

    touched_result = _run_git(["git", "-C", str(worktree_path), "status", "--porcelain"], cwd=repo_path)
    if touched_result.returncode != 0:
        return 1, f"ERROR {_git_error(touched_result)}"

    touched_files = _status_paths(touched_result.stdout)
    touched_files_path = run_dir / "touched-files.txt"
    touched_files_path.write_text("\n".join(touched_files) + ("\n" if touched_files else ""), encoding="utf-8")

    live_result = _run_git(["git", "-C", str(repo_path), "status", "--porcelain"], cwd=repo_path)
    if live_result.returncode != 0:
        return 1, f"ERROR {_git_error(live_result)}"

    live_paths = set(_status_paths(live_result.stdout))
    breached_paths = [path for path in touched_files if path in live_paths]
    if breached_paths:
        return 3, "\n".join(f"ISOLATION-BREACH {path}" for path in breached_paths)

    return 0, f"CAPTURED {len(touched_files)} files -> {diff_patch_path.resolve()}"


def _remove_worktree(repo_path: Path, worktree_path: Path, force: bool) -> tuple[int, str]:
    status_result = _run_git(["git", "-C", str(worktree_path), "status", "--porcelain"], cwd=repo_path)
    if status_result.returncode != 0:
        return 1, f"ERROR {_git_error(status_result)}"

    if status_result.stdout.strip() and not force:
        return 4, "ERROR worktree has uncaptured changes; run worktree-capture first or pass --force"

    remove_args = ["git", "-C", str(repo_path), "worktree", "remove", "--force", str(worktree_path)]
    remove_result = _run_git(remove_args, cwd=repo_path)
    if remove_result.returncode != 0:
        return 1, f"ERROR {_git_error(remove_result)}"

    prune_result = _run_git(["git", "-C", str(repo_path), "worktree", "prune"], cwd=repo_path)
    if prune_result.returncode != 0:
        return 1, f"ERROR {_git_error(prune_result)}"

    return 0, f"REMOVED {worktree_path}"


def _prune_worktrees(repo_path: Path) -> tuple[int, str]:
    list_result = _run_git(["git", "-C", str(repo_path), "worktree", "list", "--porcelain"], cwd=repo_path)
    if list_result.returncode != 0:
        return 1, f"ERROR {_git_error(list_result)}"

    removed = 0
    skipped = 0
    for worktree_path in _worktree_list_paths(list_result.stdout):
        if not _is_generated_worktree(worktree_path, repo_path):
            continue

        status_result = _run_git(["git", "-C", str(worktree_path), "status", "--porcelain"], cwd=repo_path)
        if status_result.returncode != 0:
            return 1, f"ERROR {_git_error(status_result)}"

        if status_result.stdout.strip():
            skipped += 1
            print(f"SKIPPED {worktree_path} (uncaptured changes)")
            continue

        remove_result = _run_git(
            ["git", "-C", str(repo_path), "worktree", "remove", "--force", str(worktree_path)],
            cwd=repo_path,
        )
        if remove_result.returncode != 0:
            return 1, f"ERROR {_git_error(remove_result)}"

        removed += 1

    prune_result = _run_git(["git", "-C", str(repo_path), "worktree", "prune"], cwd=repo_path)
    if prune_result.returncode != 0:
        return 1, f"ERROR {_git_error(prune_result)}"

    return 0, f"PRUNED {removed} SKIPPED {skipped}"


def _get_required_scalar_missing_fields(data: dict[str, Any]) -> list[str]:
    missing_fields: list[str] = []
    for field in REQUIRED_SCALAR_FIELDS:
        if field not in data or _is_empty_scalar(data[field]):
            missing_fields.append(field)
    return missing_fields


def _validate_executor_binding(
    findings: list[dict[str, str]],
    field_name: str,
    executor_name: str,
    task_class: str | None,
    executor_mode: str | None,
) -> None:
    if executor_name not in KNOWN_EXECUTORS:
        findings.append(
            _finding(
                "BLOCKER",
                "unknown-executor",
                f"{field_name} must be one of {', '.join(sorted(KNOWN_EXECUTORS))}; got {executor_name!r}",
            )
        )
        return

    expected_mode = EXECUTOR_MODES[executor_name]
    if executor_mode in VALID_EXECUTOR_MODES and executor_mode != expected_mode:
        findings.append(
            _finding(
                "BLOCKER",
                "mode-mismatch",
                f"{field_name}={executor_name} requires executor_mode={expected_mode}; got {executor_mode}",
            )
        )

    if task_class and task_class in VALID_TASK_CLASSES:
        allowed_classes = EXECUTOR_ALLOWED_TASK_CLASSES[executor_name]
        if task_class not in allowed_classes:
            findings.append(
                _finding(
                    "BLOCKER",
                    "class-not-allowed",
                    f"{field_name}={executor_name} does not allow task_class={task_class}",
                )
            )


def validate_frontmatter(data: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    if not isinstance(data, dict):
        return [
            _finding(
                "BLOCKER",
                "missing-frontmatter",
                "frontmatter must parse to a YAML mapping",
            )
        ]

    for field in ENUM_NOTATION_FIELDS:
        if field in data and _contains_uninstantiated_enum(data[field]):
            findings.append(
                _finding(
                    "BLOCKER",
                    "uninstantiated-enum",
                    f"{field} still contains template enum notation: {_normalize_text(data[field])}",
                )
            )

    missing_fields = _get_required_scalar_missing_fields(data)
    if missing_fields:
        findings.append(
            _finding(
                "BLOCKER",
                "missing-field",
                f"missing required field(s): {', '.join(missing_fields)}",
            )
        )

    risk = data.get("risk")
    risk_text = _normalize_text(risk) if risk is not None else ""
    if risk_text and "|" not in risk_text and risk_text not in VALID_RISKS:
        findings.append(
            _finding(
                "BLOCKER",
                "bad-enum-value",
                f"risk must be one of {', '.join(sorted(VALID_RISKS))}; got {risk_text!r}",
            )
        )

    executor_mode = data.get("executor_mode")
    executor_mode_text = _normalize_text(executor_mode) if executor_mode is not None else ""
    if executor_mode_text and "|" not in executor_mode_text and executor_mode_text not in VALID_EXECUTOR_MODES:
        findings.append(
            _finding(
                "BLOCKER",
                "bad-enum-value",
                f"executor_mode must be one of {', '.join(sorted(VALID_EXECUTOR_MODES))}; got {executor_mode_text!r}",
            )
        )

    data_sensitivity = data.get("data_sensitivity")
    data_sensitivity_text = _normalize_text(data_sensitivity) if data_sensitivity is not None else ""
    if data_sensitivity_text and "|" not in data_sensitivity_text and data_sensitivity_text not in VALID_DATA_SENSITIVITY:
        findings.append(
            _finding(
                "BLOCKER",
                "bad-enum-value",
                f"data_sensitivity must be one of {', '.join(sorted(VALID_DATA_SENSITIVITY))}; got {data_sensitivity_text!r}",
            )
        )

    task_class = data.get("task_class")
    task_class_text = _normalize_text(task_class) if task_class is not None else ""
    if task_class_text and "|" not in task_class_text and task_class_text not in VALID_TASK_CLASSES:
        findings.append(
            _finding(
                "BLOCKER",
                "unknown-task-class",
                f"task_class must be one of {', '.join(sorted(VALID_TASK_CLASSES))}; got {task_class_text!r}",
            )
        )

    preferred_executor = data.get("preferred_executor")
    preferred_executor_text = _normalize_text(preferred_executor) if preferred_executor is not None else ""
    if preferred_executor_text and "|" not in preferred_executor_text:
        _validate_executor_binding(
            findings,
            "preferred_executor",
            preferred_executor_text,
            task_class_text if task_class_text in VALID_TASK_CLASSES else None,
            executor_mode_text if executor_mode_text in VALID_EXECUTOR_MODES else None,
        )

    fallback_executor = data.get("fallback_executor")
    if fallback_executor is not None:
        if _is_empty_scalar(fallback_executor):
            findings.append(
                _finding(
                    "BLOCKER",
                    "null-optional",
                    "fallback_executor is present but empty; optional fields must be omitted entirely",
                )
            )
        else:
            fallback_executor_text = _normalize_text(fallback_executor)
            if "|" not in fallback_executor_text:
                _validate_executor_binding(
                    findings,
                    "fallback_executor",
                    fallback_executor_text,
                    task_class_text if task_class_text in VALID_TASK_CLASSES else None,
                    executor_mode_text if executor_mode_text in VALID_EXECUTOR_MODES else None,
                )

    verification = data.get("verification")
    if not isinstance(verification, list) or not verification:
        findings.append(
            _finding(
                "BLOCKER",
                "empty-verification",
                "verification must be a non-empty list",
            )
        )

    allowed_paths = data.get("allowed_paths")
    if executor_mode_text == "agentic":
        if not isinstance(allowed_paths, list) or not allowed_paths:
            findings.append(
                _finding(
                    "BLOCKER",
                    "empty-allowed-paths",
                    "allowed_paths must be a non-empty list for agentic tasks",
                )
            )
    elif allowed_paths is None or (isinstance(allowed_paths, list) and not allowed_paths):
        findings.append(
            _finding(
                "BLOCKER",
                "missing-field",
                "allowed_paths must be provided for dispatch scope",
            )
        )

    orchestrate_version = data.get("orchestrate_version")
    if orchestrate_version is not None and _normalize_text(orchestrate_version) != CURRENT_ORCHESTRATE_VERSION:
        findings.append(
            _finding(
                "WARNING",
                "version-mismatch",
                f"orchestrate_version {_normalize_text(orchestrate_version)} != {CURRENT_ORCHESTRATE_VERSION}",
            )
        )

    return findings


def _extract_frontmatter_block(text: str) -> str | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    end_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break

    if end_index is None:
        return None

    return "\n".join(lines[1:end_index])


def _split_frontmatter_document(text: str) -> tuple[str, str, str, str] | None:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None

    end_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break

    if end_index is None:
        return None

    opener = lines[0]
    frontmatter = "".join(lines[1:end_index])
    closer = lines[end_index]
    body = "".join(lines[end_index + 1 :])
    return opener, frontmatter, closer, body


def _load_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    document = _split_frontmatter_document(text)
    if document is None:
        raise ValueError("missing or unparseable YAML frontmatter")

    _, frontmatter_block, _, _ = document
    try:
        parsed = yaml.safe_load(frontmatter_block)
    except yaml.YAMLError as exc:  # pragma: no cover - parser errors are exercised through CLI tests
        raise ValueError("missing or unparseable YAML frontmatter") from exc

    if not isinstance(parsed, dict):
        raise ValueError("missing or unparseable YAML frontmatter")

    return parsed


def _load_frontmatter_document(path: Path) -> tuple[dict[str, Any], tuple[str, str, str, str]]:
    text = path.read_text(encoding="utf-8")
    document = _split_frontmatter_document(text)
    if document is None:
        raise ValueError("missing or unparseable YAML frontmatter")

    _, frontmatter_block, _, _ = document
    try:
        parsed = yaml.safe_load(frontmatter_block)
    except yaml.YAMLError as exc:  # pragma: no cover - parser errors are exercised through CLI tests
        raise ValueError("missing or unparseable YAML frontmatter") from exc

    if not isinstance(parsed, dict):
        raise ValueError("missing or unparseable YAML frontmatter")

    return parsed, document


def _dump_frontmatter_document(data: dict[str, Any], document: tuple[str, str, str, str]) -> str:
    opener, _, closer, body = document
    newline = "\r\n" if opener.endswith("\r\n") else "\n"
    dumped = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, width=4096)
    if not dumped.endswith("\n"):
        dumped += "\n"
    dumped = dumped.replace("\n", newline)
    return f"{opener}{dumped}{closer}{body}"


def _smoke_executor_records(data: dict[str, Any], now: datetime) -> tuple[list[str], int]:
    executors = data.get("executors")
    if not isinstance(executors, list):
        raise ValueError("executors.local.md must contain an executors list")

    lines: list[str] = []
    probe_needed = 0
    for record in executors:
        if not isinstance(record, dict) or "name" not in record:
            raise ValueError("executors.local.md contains an invalid executor record")

        name = _normalize_text(record["name"])
        status = _normalize_text(record.get("status")) if record.get("status") is not None else ""
        if status == "deferred":
            lines.append(f"DEFERRED {name}")
            continue

        last_verified = record.get("last_verified")
        if last_verified is None or _is_empty_scalar(last_verified):
            lines.append(f"UNVERIFIED {name}")
            probe_needed += 1
            continue

        verified_at = _parse_iso_datetime(last_verified)
        age = now - verified_at
        age_text = _format_age(age)
        if age <= timedelta(hours=24):
            lines.append(f"FRESH {name} (verified {age_text} ago)")
        else:
            lines.append(f"STALE {name} (verified {age_text} ago)")
            probe_needed += 1

    lines.append(f"PROBE-NEEDED {probe_needed}")
    return lines, probe_needed


def _smoke_status(config_path: Path, now: datetime) -> tuple[int, str]:
    data = _load_frontmatter(config_path)
    lines, _ = _smoke_executor_records(data, now)
    return 0, "\n".join(lines)


def _smoke_record(config_path: Path, executor_name: str, now: datetime) -> tuple[int, str]:
    data, document = _load_frontmatter_document(config_path)
    executors = data.get("executors")
    if not isinstance(executors, list):
        return 1, "ERROR executors.local.md must contain an executors list"

    timestamp = _utc_isoformat_seconds(now)
    for record in executors:
        if not isinstance(record, dict):
            continue
        if _normalize_text(record.get("name")) != executor_name:
            continue
        record["last_verified"] = timestamp
        config_path.write_text(_dump_frontmatter_document(data, document), encoding="utf-8")
        return 0, f"RECORDED {executor_name} {timestamp}"

    return 1, f"ERROR executor not found: {executor_name}"


def _print_findings(findings: list[dict[str, str]]) -> int:
    blockers = 0
    for finding in findings:
        print(f"{finding['severity']} {finding['rule_id']}: {finding['message']}")
        if finding["severity"] == "BLOCKER":
            blockers += 1

    if blockers:
        print(f"BLOCKED ({blockers} blockers)")
        return 2

    print("DISPATCHABLE")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="orchestrate_run.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate a brief frontmatter block")
    validate_parser.add_argument("brief_path", help="path to a markdown brief")

    worktree_create_parser = subparsers.add_parser("worktree-create", help="create a sibling git worktree")
    worktree_create_parser.add_argument("--repo", default=".", help="path to the repository root")
    worktree_create_parser.add_argument("--run-id", required=True, help="run identifier")

    worktree_capture_parser = subparsers.add_parser("worktree-capture", help="capture a worktree diff")
    worktree_capture_parser.add_argument("--repo", default=".", help="path to the repository root")
    worktree_capture_parser.add_argument("--worktree", required=True, help="path to the worktree")
    worktree_capture_parser.add_argument("--run-id", required=True, help="run identifier")

    worktree_remove_parser = subparsers.add_parser("worktree-remove", help="remove a generated worktree")
    worktree_remove_parser.add_argument("--repo", default=".", help="path to the repository root")
    worktree_remove_parser.add_argument("--worktree", required=True, help="path to the worktree")
    worktree_remove_parser.add_argument("--force", action="store_true", help="remove even if dirty")

    worktree_prune_parser = subparsers.add_parser("worktree-prune", help="prune generated worktrees")
    worktree_prune_parser.add_argument("--repo", default=".", help="path to the repository root")

    smoke_status_parser = subparsers.add_parser("smoke-status", help="report executor smoke-test freshness")
    smoke_status_parser.add_argument("--config", required=True, help="path to executors.local.md")
    smoke_status_parser.add_argument("--now", help=argparse.SUPPRESS)

    smoke_record_parser = subparsers.add_parser("smoke-record", help="mark an executor as freshly smoke-tested")
    smoke_record_parser.add_argument("--config", required=True, help="path to executors.local.md")
    smoke_record_parser.add_argument("--executor", required=True, help="executor name to mark verified")
    smoke_record_parser.add_argument("--now", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        print(parser.format_usage().strip())
        return 1

    if args.command != "validate":
        repo_path = _repo_path(getattr(args, "repo", "."))
        if args.command == "worktree-create":
            exit_code, message = _create_worktree(repo_path, args.run_id)
        elif args.command == "worktree-capture":
            exit_code, message = _capture_worktree(repo_path, Path(args.worktree).resolve(), args.run_id)
        elif args.command == "worktree-remove":
            exit_code, message = _remove_worktree(repo_path, Path(args.worktree).resolve(), args.force)
        elif args.command == "worktree-prune":
            exit_code, message = _prune_worktrees(repo_path)
        else:
            if args.command == "smoke-status":
                try:
                    now = _parse_iso_datetime(args.now) if args.now else datetime.now(timezone.utc)
                    exit_code, message = _smoke_status(Path(args.config), now)
                except (OSError, ValueError) as exc:
                    print(f"ERROR: {exc}")
                    return 1
            elif args.command == "smoke-record":
                try:
                    now = _parse_iso_datetime(args.now) if args.now else datetime.now(timezone.utc)
                    exit_code, message = _smoke_record(Path(args.config), args.executor, now)
                except (OSError, ValueError) as exc:
                    print(f"ERROR: {exc}")
                    return 1
            else:
                print(f"ERROR: unsupported command: {args.command}")
                print(parser.format_usage().strip())
                return 1

        print(message)
        return exit_code

    try:
        data = _load_frontmatter(Path(args.brief_path))
    except OSError as exc:
        print(f"ERROR: {exc}")
        return 1
    except ValueError as exc:
        print(f"BLOCKER missing-frontmatter: {exc}")
        print("BLOCKED (1 blockers)")
        return 2

    findings = validate_frontmatter(data)
    return _print_findings(findings)


if __name__ == "__main__":
    raise SystemExit(main())
