# Brief template (v0.2) — frontmatter contract + run report

This template defines the canonical v0.2 brief format. The frontmatter is a routing and enforcement layer shared by the brain, GitHub issues, and a future harness; it is not a replacement for the human brief that explains the work. Classification comes from `references/task-classes.md`, and executor selection comes from `references/executor-capabilities.md`; stay consistent with both, and treat the class matrix as canonical when they appear to differ. Use this format to make dispatch, review, and run reporting machine-checkable while keeping the human brief operational and specific.

## Frontmatter Schema

```yaml
---
orchestrate_version: 0.2
task_id: short-kebab-case-id
task_class: bugfix-isolated        # one of the 13 in references/task-classes.md
risk: low | medium | high
executor_mode: agentic | advisory
preferred_executor: codex | codex-readonly | claude-haiku-native | opencode-free-tier
fallback_executor: codex-readonly  # OPTIONAL — omit the key entirely when unused
allowed_paths:
  - path/to/file.ts
forbidden_paths:
  - .env*
  - prisma/migrations/**
verification:
  - pnpm typecheck   # EXAMPLE ONLY — derive from target repo
  - pnpm test        # EXAMPLE ONLY — derive from target repo
max_revisions: 2
requires_operator_approval: false
data_sensitivity: public | proprietary | sensitive
---
```

Field semantics:

- `orchestrate_version` pins the brief contract version. The brain uses it to decide whether the brief matches the current docs set before dispatch.
- `task_id` is a short kebab-case identifier that also becomes part of the run directory name.
- `task_class` must be one concrete class from `references/task-classes.md`. Do not guess a class by vibe; choose the most restrictive match.
- `risk` is a coarse escalation hint for the brain and reviewer. It does not override `task_class`.
- `executor_mode` chooses whether the executor edits files (`agentic`) or only returns text/diff (`advisory`).
- `preferred_executor` names the primary body that may receive the brief.
- `fallback_executor` is optional and must be omitted entirely when unused; an empty or null value is not allowed.
- `allowed_paths` lists the only repo-relative paths the body may touch in an agentic run.
- `forbidden_paths` lists concrete paths or glob patterns that must stay untouched even if they fall inside a broader allowed tree.
- `verification` lists concrete commands the brain will later rerun against the target repo. These are part of the dispatch contract, not a free-form note.
- `max_revisions` caps how many body retries the brain will tolerate before it takes over or escalates.
- `requires_operator_approval` marks cases where the brain must pause before dispatching or accepting the result.
- `data_sensitivity` tells the routing layer how carefully to treat the task payload and any repo excerpts.

Mandatory semantics to state explicitly:

- Enum fields shown as `a | b | c` list ALLOWED VALUES. An instantiated brief contains exactly ONE literal value. A leftover `a | b` in a real brief is a dispatch blocker.
- Optional fields such as `fallback_executor` are OMITTED when unused. Never set an optional field to `null`.
- Version handling: if `orchestrate_version` does not match the current docs version, the brain warns and re-validates the brief against current docs before dispatch.
- `requires_operator_approval` must be `true` for irreversible, DB, security, money, or product-behavior-sensitive changes.

Frontmatter discipline:

- Keep `allowed_paths` narrow and explicit. Prefer file-level paths over broad directories when the task can be bounded that way.
- Put every path that matters to the run in `allowed_paths`; do not rely on the executor to infer scope from prose.
- Use `forbidden_paths` for landmines that should remain untouched even if they are nearby or named in the task.
- Treat the frontmatter as a machine-readable contract. The prose brief explains intent; the frontmatter routes and constrains execution.

## Verification Derivation Rule

Verification commands are concrete and derived from the target repo, never assumed and never templated with substitution variables.

- Lockfile detection:
  - `pnpm-lock.yaml` -> `pnpm`
  - `bun.lockb` or `bun.lock` -> `bun`
  - `yarn.lock` -> `yarn`
  - `package-lock.json` -> `npm`
- Use the repo's actual `package.json` script names. If the repo defines `typecheck`, run that script; if it defines `test:unit`, run that script. Do not invent script names.
- For non-JS repos, use the repo's own task runner, such as `Makefile`, `cargo`, `go test`, or `pytest`.
- Derived verification should be specific enough to rerun without interpretation.
- If no verification command can be derived, that is a dispatch blocker. Ask the operator; never guess.
- If the repo has multiple plausible test commands, prefer the narrowest command that covers the touched area and the observed failure mode.
- A command like `pnpm test` is acceptable only when the repository actually exposes that script and it is the right level of coverage for the task.
- Do not substitute path variables into the command string. The command in the brief must be the exact command the brain will rerun.

Practical derivation notes:

- For a small TypeScript fix in a pnpm repo, a good pair is often a typecheck script and one focused test script.
- For a Python library, the derived verification might be `pytest tests/test_widget.py` plus a package-specific lint or type check.
- For a Rust crate, the derived verification might be `cargo test widget` or `cargo test --lib` if that is the repo's standard scope.
- The brief should show the concrete command strings the body can execute and the brain can rerun.

## Human Brief Sections

After the frontmatter, keep the human brief in this order:

```markdown
# Brief: <title>
## Objective
## Scope
## Do NOT
## Contract
## Conventions to follow
## Pattern-match these existing files
## Acceptance criteria
## Output format
## Review notes for the brain
```

Section guidance:

- `Objective` answers what the body must produce, in one sentence.
- `Scope` lists only the files the body may edit, with a short note for each.
- `Do NOT` names the standing constraints and any task-specific landmines.
- `Contract` states the input/output shapes, invariants, or behavioral requirements the work must preserve.
- `Conventions to follow` captures repo-local rules the body cannot infer safely.
- `Pattern-match these existing files` names the exemplars the body should mirror.
- `Acceptance criteria` is the review checklist and should be checkable without interpretation.
- `Output format` tells the body exactly what to return when it finishes.
- `Review notes for the brain` marks anything the body cannot be trusted to judge, including approval gates and edge-risk areas.

## Run Report Schema

Every executor run produces a machine-readable run report:

```json
{
  "runId": "20260612-short-task-id",
  "executor": "codex",
  "status": "completed | failed | partial",
  "scopeCheck": "pass | fail",
  "verification": [
    { "cmd": "pnpm typecheck", "status": "pass | fail" }
  ],
  "touchedFiles": ["src/server/admin/invite.ts"],
  "diffPath": ".orchestrate/runs/<runId>/diff.patch",
  "logsPath": ".orchestrate/runs/<runId>/logs.txt"
}
```

Mandatory semantics:

- Report fields map 1:1 to the frontmatter fields they answer. `verification` answers `verification`; `touchedFiles` answers `allowed_paths`.
- All fields are body-claimed, not brain-verified. The brain reruns verification and re-checks scope against the actual diff.
- The report tells the brain where to look, never what to conclude.
- `status: completed` is not approval. Approval is a brain verdict after review and may still fail on scope or correctness.
- Exit codes are not success signals. Codex can exit 0 on failed runs, so the touched-files check against the brief's scope is the ground truth.
- `runId` convention: `YYYYMMDD-<task_id>`, matching `.orchestrate/runs/<runId>/`.
- `diffPath` and `logsPath` should point at artifacts inside the run directory, not at ad hoc scratch locations.
- `scopeCheck` is a claimed result from the body, not a substitute for the brain's own scope review.

Report hygiene:

- Keep `verification` entries aligned with the commands listed in the frontmatter.
- Keep `touchedFiles` limited to files that actually changed.
- If the body could not complete verification, it should say so in the report rather than inventing a pass.
- If the body had to stop early, the report should surface partial status instead of laundering the failure into completion.

## Worked Examples

### Example A — agentic codex task

````markdown
---
orchestrate_version: 0.2
task_id: fix-invite-subject-fallback
task_class: bugfix-isolated
risk: low
executor_mode: agentic
preferred_executor: codex
fallback_executor: codex-readonly
allowed_paths:
  - src/server/admin/invite.ts
  - src/server/admin/invite.test.ts
forbidden_paths:
  - .env*
  - prisma/migrations/**
verification:
  - pnpm typecheck
  - pnpm test src/server/admin/invite.test.ts
max_revisions: 2
requires_operator_approval: false
data_sensitivity: proprietary
---

# Brief: Fix invite subject fallback

## Objective
Patch the invite email subject so the admin invite flow falls back to the default subject when a custom subject is missing.

## Scope
Create / edit ONLY these files:
- `src/server/admin/invite.ts` — update the subject selection logic.
- `src/server/admin/invite.test.ts` — add the regression case for a missing custom subject.

## Do NOT
- Do not modify any other files.
- Do not refactor unrelated invite flow code.
- Do not run migrations, `prisma db push`, seeds, or anything that writes to a database.
- Do not `git push`, `git commit`, install packages, or make network calls.

## Contract
- `sendInviteEmail()` must keep the same call signature and return shape.
- When `customSubject` is empty or undefined, the message subject must use the repository default.
- The regression test must fail before the fix and pass after the fix.

## Conventions to follow
- Keep the change local to the invite module.
- Preserve existing error handling and logging.
- Match the existing test style in the file.

## Pattern-match these existing files
- `src/server/admin/invite.ts`
- `src/server/admin/reset-password.ts`
- `src/server/admin/invite.test.ts`

## Acceptance criteria
- [ ] Scope check passes: only the two listed files change.
- [ ] `pnpm typecheck` passes.
- [ ] `pnpm test src/server/admin/invite.test.ts` passes.
- [ ] The invite subject falls back correctly when no custom subject is provided.

## Output format
Edit only inside the assigned worktree; do not commit; do not push; do not install packages; do not run migrations; return a summary of changed files plus the run report JSON.

## Review notes for the brain
- Re-run the focused test and typecheck yourself.
- Confirm the diff stays inside `allowed_paths`.
- Confirm the test asserts the behavior, not an implementation detail.
````

Example A notes:

- The frontmatter is fully instantiated with single enum values.
- The `verification` commands are concrete and repo-derived in form, not templated.
- The `Output format` line is the exact body contract required for an agentic codex task.

### Example B — advisory codex-readonly task

````markdown
---
orchestrate_version: 0.2
task_id: review-invite-diff
task_class: review-diff
risk: low
executor_mode: advisory
preferred_executor: codex-readonly
allowed_paths:
  - src/server/admin/invite.ts
  - src/server/admin/invite.test.ts
forbidden_paths:
  - .env*
  - prisma/migrations/**
verification:
  - pnpm typecheck
  - pnpm test src/server/admin/invite.test.ts
max_revisions: 0
requires_operator_approval: false
data_sensitivity: proprietary
---

# Brief: Review invite fallback diff

## Objective
Review the proposed invite fallback change and return only the diff if it stays within scope and preserves the existing invite behavior.

## Scope
Create / edit ONLY these files:
- `src/server/admin/invite.ts`
- `src/server/admin/invite.test.ts`

## Do NOT
- Do not modify any other files.
- Do not expand the patch into unrelated cleanup.
- Do not add commentary, summaries, or extra files.

## Contract
- The reviewed patch must preserve the existing function signatures and response shapes.
- The only accepted behavioral change is the fallback subject logic and its corresponding regression test.

## Conventions to follow
- Compare against the current invite implementation, not against a preferred style.
- Reject any diff that broadens the scope beyond the two files.
- Keep the review read-only.

## Pattern-match these existing files
- `src/server/admin/invite.ts`
- `src/server/admin/invite.test.ts`

## Acceptance criteria
- [ ] Diff touches only files in `allowed_paths`.
- [ ] The fallback subject behavior is correct.
- [ ] The regression test covers the missing-subject case.
- [ ] The patch does not introduce unrelated formatting or cleanup.

## Output format
Return a unified diff only; no commentary; no files outside `allowed_paths`.

## Review notes for the brain
- Re-check scope against the diff, not the claim.
- Re-run verification after applying the diff if you choose to apply it.
- Reject the patch if it changes anything beyond the two files or if the behavior is only implied rather than asserted.
````

Example B notes:

- This example uses `codex-readonly` in advisory mode for a `review-diff` task.
- The `Output format` line constrains the body to a diff-only response with no commentary.
- The `verification` commands are still concrete so the brain has a rerun target after review.
