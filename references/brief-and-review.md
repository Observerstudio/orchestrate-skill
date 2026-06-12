# The brief and the review (one artifact, two ends)

The brief is the contract you hand the body; the review is you holding it to that contract. They share the same acceptance criteria, so writing a good brief *is* writing your review rubric. Spend effort here — it's cheaper than re-rolling a 60s body cycle.

## Why briefs fail

The body re-loads the repo cold and shares none of your conversation. It does not know your conventions, your prior decisions, or what's out of scope. Left underspecified it will: invent its own patterns, refactor things you didn't ask about, drop the return-type contract, and confidently hand back something plausible and wrong. Every part of the template below exists to close one of those gaps.

## Machine-readable frontmatter

For v0.2+, every delegated task starts with YAML frontmatter so the brain, a future harness, and GitHub issues share the same contract — the canonical schema, field semantics, and worked examples live in `templates/brief-template.md`. Frontmatter is a **routing and enforcement layer, not a replacement for the human brief**: the prose sections below remain what the body actually works from.

Frontmatter review rules (checked before dispatch):

- `allowed_paths` must match the human Scope section exactly — a mismatch means the brief is internally inconsistent; fix it before sending.
- `verification` commands must be concrete **and derived from the target repo** (lockfile → package manager, actual script names, or the repo's own task runner — see the derivation rule in `templates/brief-template.md`). An assumed or templated command is a dispatch blocker.
- `risk` and `task_class` must be set (single literal values, per `references/task-classes.md`) before dispatch.
- `requires_operator_approval` must be `true` for irreversible, DB, security, money, or product-behavior-sensitive changes.

## Brief template

The prose skeleton below predates v0.2 and remains valid; for new work, prefer the full v0.2 template in `templates/brief-template.md` (this skeleton plus frontmatter and the run report).

````markdown
# Brief: <one-line title>

## Objective
<Exactly what to produce, in one sentence. No backstory.>

## Scope
Create / edit ONLY these files:
- path/to/file.ts — <what goes here>
- path/to/other.ts — <what goes here>

## Do NOT
- Do not modify any other files.
- Do not refactor, rename, or "improve" existing code.
- Do not add dependencies.
- <Any task-specific landmines.>
<For an AGENTIC executor (codex), always include these standing constraints —
the worktree does not sandbox them:>
- Do not run migrations, `prisma db push`, seeds, or anything that writes to a database.
- Do not `git push`, `git commit`, install packages, or make network calls.
- Do not spawn other agents or executors (no recursive `codex exec`, no `opencode run`).
- Edit files and run only read-only checks (`typecheck`, `lint`, tests that don't hit a live DB).

## Contract
<Signatures, types, I/O shapes the output must match. Paste the actual
interface / return type / schema. e.g.:>
- Every action returns `ActionResult<T>` ({ ok: true, data } | { ok: false, error }).
- Inputs validated with the Zod schema in `schemas/index.ts` via `.safeParse`.

## Conventions to follow
<The repo rules the body can't infer. Be concrete. e.g.:>
- Module shape: index.ts (public API) / data.ts (reads) / schemas / actions / components.
- Permissions: call `hasPermission(role, Permission.X)` — never branch on role directly.
- Tenancy: every query scoped by `workspaceId` from `requireMembership()`.
- No `as any`, `@ts-ignore`, `@ts-expect-error`. No commented-out code.

Pattern-match these existing files:
- path/to/exemplar1.ts
- path/to/exemplar2.ts

## Acceptance criteria  (← these are also the review checklist)
- [ ] `pnpm web typecheck` clean on touched files.
- [ ] `pnpm web test <scope>` passes.
- [ ] <objective, checkable behavior — e.g. "POST returns 403 for CLIENT role">
- [ ] Diff touches only the files listed in Scope.

## Output format
<For agentic (codex):> Edit only inside the worktree. Run `pnpm web typecheck`
before finishing. End with a one-paragraph summary of the diff.
<For advisory (opencode):> Return only the full file contents (or a unified
diff). No commentary, no explanation.
````

## Worked example (advisory, opencode)

> **Objective:** Add `loading`, `empty`, and `error` UI states to the 6 list components in `src/components/lists/`.
> **Scope:** edit only those 6 `*.tsx` files.
> **Do NOT:** change the data-fetching hooks, change props, or touch anything outside `src/components/lists/`.
> **Contract:** each component already receives `{ data, isLoading, error }`; render `<ListSkeleton/>` while loading, `<EmptyState/>` when `data.length === 0`, `<ErrorState error={error}/>` on error — all three already exist in `src/components/ui/`.
> **Conventions:** match `src/components/lists/ProjectsList.tsx`, which already has all three states. No `as any`.
> **Acceptance:** typecheck clean; each file imports and renders all three states; diff limited to the 6 files.
> **Output:** return each file's full contents under a `// FILE: <path>` header. No prose.

That brief is tight enough that grading the result is mechanical: open each of the 6 files, confirm the three states, run typecheck, confirm nothing else changed.

## The review checklist (apply in order; stop at first hard fail)

**Step zero — validate the run report against the frontmatter (before reading any code).** v0.2 runs return a machine-readable report (schema in `templates/brief-template.md`). Check: `touchedFiles` ⊆ `allowed_paths` — re-verified against the *actual diff*, not the report; every frontmatter `verification` command has a result — which you re-run yourself; `status`/`scopeCheck` treated as claims, never conclusions. A report that fails validation is rejected before implementation review begins. (Exit codes are not success signals — codex exits 0 on runs whose writes were all blocked; the touched-files check is the ground truth.)

**Precondition — did the run complete?** Clean exit, summary present, every in-scope file actually touched. A partial/truncated run (the body died mid-transform, hit a usage limit at file 4 of 8) is a **discard**, not a revise — re-brief from a clean state. Never grade or integrate half a transform.

1. **Scope** — did the diff touch *only* the files in Scope? Any extra file is an automatic revise. This catches the body's most common failure: helpful over-reach. (Note: "matches this diff shape" is a *scope* check — it never substitutes for correctness.)
2. **Spec adherence** — every acceptance criterion met? Anything in "Do NOT" violated?
3. **Correctness** — logic right, edge cases covered, no obvious bugs.
4. **Pattern-match** — matches the named exemplars and stated conventions, not the body's generic defaults.
5. **Verification evidence** — *you* ran `typecheck`/`lint`/`test` and saw green. The body's "tests pass" is a claim, not evidence — re-run it yourself (for advisory output, after you apply it). Not "looks fine," not "it said it passed" — green you observed.
6. **Safety** — for anything touching auth, permissions, tenancy, money, data deletion, or the database/schema: scrutinize line by line, and pause for the operator. The body does not understand your threat model.

**Pass** → integrate, tell the operator what landed. **Fail** → write *specific* revision feedback naming the exact violation and the fix, re-dispatch. **Second fail** → stop; finish it yourself or escalate. Two misses means the spec was the problem, and the brain fixes specs faster than the body re-guesses.

## When the contract runs out

Two situations end delegation for a chunk; in both, the answer is **never to loosen the constraints so the output passes**:

- **`max_revisions` exhausted** (non-converging on the same criteria): the brain takes the chunk back and finishes it itself, or escalates to the operator with what was attempted and why it failed. The declared task class, allowed paths, and verification commands stand as written.
- **`requires_operator_approval: true`**: the brain prepares the change and the review evidence, then stops and waits for the operator. Approval is a human verdict for these classes — the body cannot grant it, and neither can the brain on the body's behalf.

## Revision feedback that works

Vague feedback ("this isn't right, try again") wastes a cycle. Name the violation, quote the rule, state the fix:

> Revise: (1) You edited `src/lib/db.ts` — that's outside scope; revert it entirely. (2) `createProject` returns a bare object; it must return `ActionResult<Project>` per the contract — wrap success in `{ ok: true, data }`. (3) You branched on `role === 'ADMIN'`; replace with `hasPermission(role, Permission.ProjectCreate)`. Everything else is correct — change only these three things.
