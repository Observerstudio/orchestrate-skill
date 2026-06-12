---
orchestrate_version: 0.2
task_id: review-validate-command
task_class: review-diff
risk: low
executor_mode: advisory
preferred_executor: codex-readonly
allowed_paths:
  - harness/orchestrate_run.py
  - harness/tests/test_validate.py
forbidden_paths:
  - .env*
  - references/**
  - templates/**
verification:
  - python -m unittest discover -s harness/tests -v
max_revisions: 0
requires_operator_approval: false
data_sensitivity: public
---

# Brief: Review the validate command

## Objective
Review the validator contract and return a text-only assessment of whether it stays within the brief rules.

## Scope
Create / edit ONLY these files:
- `harness/orchestrate_run.py`
- `harness/tests/test_validate.py`

## Do NOT
- Do not modify any other files.
- Do not write code outside the validator path.

## Contract
- The advisory path must remain read-only.
- The brief must still be dispatchable after validation.

## Conventions to follow
- Match the example advisory brief in `templates/brief-template.md`.

## Pattern-match these existing files
- `templates/brief-template.md`

## Acceptance criteria
- [ ] The brief is syntactically valid YAML frontmatter.
- [ ] The validator accepts the advisory mode combination.

## Output format
Return a brief text assessment only.

## Review notes for the brain
- Ensure the executor mode and executor capability matrix stay aligned.
