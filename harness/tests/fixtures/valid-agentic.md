---
orchestrate_version: 0.2
task_id: scaffold-validate-command
task_class: scaffold
risk: low
executor_mode: agentic
preferred_executor: codex
allowed_paths:
  - harness/orchestrate_run.py
  - harness/tests/test_validate.py
forbidden_paths:
  - .env*
  - references/**
  - templates/**
verification:
  - python -m unittest discover -s harness/tests -v
max_revisions: 2
requires_operator_approval: false
data_sensitivity: public
---

# Brief: Scaffold the validate command

## Objective
Create a frontmatter validator CLI and test suite for the v0.2 harness brief contract.

## Scope
Create / edit ONLY these files:
- `harness/orchestrate_run.py` — add the `validate` command and pure validator.
- `harness/tests/test_validate.py` — add fixture-driven CLI coverage.

## Do NOT
- Do not modify any other files.
- Do not shell out to git, run executors, or call network services.
- Do not add dependencies beyond Python stdlib and PyYAML.

## Contract
- `validate_frontmatter(data: dict)` must stay pure and separate from CLI parsing.
- The validator must flag dispatch blockers with stable rule ids and allow warnings for version drift.

## Conventions to follow
- Keep the checks deterministic and fixture-driven.
- Prefer small helper functions over classes.

## Pattern-match these existing files
- `templates/brief-template.md`

## Acceptance criteria
- [ ] The CLI accepts a valid agentic brief and prints `DISPATCHABLE`.
- [ ] The test suite exercises the intended validation rules.

## Output format
Return a summary of changed files plus the run report JSON.

## Review notes for the brain
- Re-run discovery after the validator lands.
- Confirm the validator remains pure and the CLI is only a wrapper.
