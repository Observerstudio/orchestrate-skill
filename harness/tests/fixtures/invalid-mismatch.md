---
orchestrate_version: 0.2
task_id: invalid-mismatch-brief
task_class: review-diff
risk: low
executor_mode: agentic
preferred_executor: codex-readonly
allowed_paths:
  - harness/orchestrate_run.py
  - harness/tests/test_validate.py
forbidden_paths:
  - .env*
verification:
  - python -m unittest discover -s harness/tests -v
max_revisions: 0
requires_operator_approval: false
data_sensitivity: public
---

# Brief: Invalid executor mode mismatch

## Objective
Trigger the mode-mismatch validation rule.

## Scope
Create / edit ONLY these files:
- `harness/orchestrate_run.py`

## Do NOT
- Do not change any other file.

## Contract
- `codex-readonly` is advisory-only, so this brief intentionally disagrees with the declared mode.

## Conventions to follow
- Keep the fixture minimal.

## Pattern-match these existing files
- `templates/brief-template.md`

## Acceptance criteria
- [ ] The validator reports a mode-mismatch blocker.

## Output format
Return the blocker report only.

## Review notes for the brain
- This fixture should fail before any body work starts.
