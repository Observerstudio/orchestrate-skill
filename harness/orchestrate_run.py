from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


CURRENT_ORCHESTRATE_VERSION = "0.2"

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


def _load_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    frontmatter_block = _extract_frontmatter_block(text)
    if frontmatter_block is None:
        raise ValueError("missing or unparseable YAML frontmatter")

    try:
        parsed = yaml.safe_load(frontmatter_block)
    except yaml.YAMLError as exc:  # pragma: no cover - parser errors are exercised through CLI tests
        raise ValueError("missing or unparseable YAML frontmatter") from exc

    if not isinstance(parsed, dict):
        raise ValueError("missing or unparseable YAML frontmatter")

    return parsed


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
        print(f"ERROR: unsupported command: {args.command}")
        print(parser.format_usage().strip())
        return 1

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
