---
orchestrate_version: 0.2
task_id: invalid-missing-brief
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
---

# Brief: Invalid missing field

## Objective
Trigger the missing-field validation rule.

## Scope
Create / edit ONLY these files:
- `harness/orchestrate_run.py`

## Do NOT
- Do not change any other file.

## Contract
- `data_sensitivity` is intentionally omitted from the frontmatter.

## Conventions to follow
- Keep the fixture minimal.

## Pattern-match these existing files
- `templates/brief-template.md`

## Acceptance criteria
- [ ] The validator reports a missing-field blocker.

## Output format
Return the blocker report only.

## Review notes for the brain
- This fixture should fail before any body work starts.
