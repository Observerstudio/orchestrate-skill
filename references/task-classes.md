# Task classes — routing matrix

This file is the canonical routing matrix the brain consults before every delegation. Classify the task first, then choose the executor; if a task matches multiple classes, the most restrictive class wins. Sensitivity classes override convenience classes, even when the underlying change looks mechanical.

## `mechanical-refactor`

A bounded change that preserves behavior while reshaping code to match an existing pattern. The work is mostly translation, cleanup, or mechanical replacement with no new product judgment.

- **Definition:** A narrow refactor where the desired end state is already clear and correctness is checkable by comparison to existing behavior.

- **Typical examples:** rename a symbol across a small module set; extract a helper from duplicated code; replace one API call with its current equivalent.

- **Recommended executor type:** agentic code executor (codex) in an isolated worktree.

- **Delegation allowed:** yes

- **Agentic execution allowed:** yes, if the touched files and expected pattern are explicit

- **Required review level:** standard checklist (scope -> pattern -> correctness -> verification -> safety)

- **Required verification:** scope check; typecheck; focused test or compile check for the touched area

- **Hazards:**
  - The refactor drifts into behavior changes.

  - The executor normalizes code into a new pattern without permission.

  - Small mechanical edits hide an unexpected dependency break.

## `scaffold`

A task that creates the initial shape of a feature, module, or workflow from an existing template. The main job is wiring, not design.

- **Definition:** New structure is being added, but the target shape is already known from repo conventions or a template.

- **Typical examples:** add a new route and view shell; create a feature folder with placeholder exports; add test harness files for a planned area.

- **Recommended executor type:** agentic code executor (codex) in an isolated worktree.

- **Delegation allowed:** yes

- **Agentic execution allowed:** yes, if the scaffold follows an existing pattern or approved template

- **Required review level:** standard checklist (structure -> wiring -> defaults -> verification)

- **Required verification:** scope check; typecheck; smoke build or initialization test for the new surface

- **Hazards:**
  - Placeholder code ships as if it were finished.

  - Wiring points to the wrong module, route, or export.

  - New files are created outside the intended surface area.

## `test-generation`

A bounded task that adds or expands tests to capture known behavior. The implementation under test should already be understood well enough to encode assertions directly.

- **Definition:** The goal is to encode expected behavior in tests, not to redesign the behavior itself.

- **Typical examples:** add a regression test for a fixed bug; parameterize a missing edge case; turn a known repro into a stable test.

- **Recommended executor type:** agentic code executor (codex) in an isolated worktree.

- **Delegation allowed:** yes

- **Agentic execution allowed:** yes, if the target behavior and fixtures are already known

- **Required review level:** standard checklist (assertion quality -> fixture realism -> brittleness -> coverage)

- **Required verification:** focused test; typecheck; run the new or updated test file directly if possible

- **Hazards:**
  - The test encodes implementation detail instead of behavior.

  - Fixtures become brittle or unrealistic.

  - The new test passes while missing the actual regression.

## `bugfix-isolated`

A narrow fix where the failing behavior is known, the relevant files are bounded, and success is objectively checkable. The change should stay close to the observed defect.

- **Definition:** A localized defect with a clear symptom, a plausible cause, and a small edit surface.

- **Typical examples:** off-by-one in a date formatter; null guard in a known component; failing assertion with a known root cause.

- **Recommended executor type:** agentic code executor (codex) in an isolated worktree; optional advisory second opinion.

- **Delegation allowed:** yes

- **Agentic execution allowed:** yes, if allowed paths are explicit and the reproduction is stable

- **Required review level:** standard checklist (scope -> spec -> correctness -> pattern -> verification -> safety)

- **Required verification:** typecheck; focused test or reproduction; scope check against allowed paths

- **Hazards:**
  - The executor broadens the fix into unrelated refactors.

  - The symptom is fixed while the root cause stays intact.

  - The patch changes adjacent behavior that was not part of the bug.

## `docs-prose`

Text-first work where the main output is explanatory, procedural, or reference prose. The edit may still land in repo files, but the value is readability and precision rather than code shape.

- **Definition:** The task is to write, rewrite, or tighten prose so the intended meaning is clear and operational.

- **Typical examples:** rewrite a README section; draft a reference page; tighten release-note copy or setup instructions.

- **Recommended executor type:** advisory executor (high-quality text); agentic code executor only if direct file edits are needed in bounded docs paths.

- **Delegation allowed:** yes

- **Agentic execution allowed:** conditional, only when the change stays within bounded docs files and contains no sensitive material

- **Required review level:** editorial checklist (clarity -> accuracy -> completeness -> terminology -> format)

- **Required verification:** render check for the docs format; link check; scope check against the requested files

- **Hazards:**
  - The prose becomes vague, aspirational, or inconsistent with repo terms.

  - A docs edit silently changes policy or behavior.

  - Links, headings, or callouts break the rendered output.

## `review-diff`

A read-only assessment of a concrete diff against a brief, spec, or acceptance checklist. The reviewer must be separate from the implementer.

- **Definition:** The task is to inspect a specific patch and decide whether it satisfies the stated contract.

- **Typical examples:** PR review of a patch; checking a fix against the brief; validating whether a diff stayed in scope.

- **Recommended executor type:** advisory executor (reviewer role), separate invocation from the implementer.

- **Delegation allowed:** advisory-only

- **Agentic execution allowed:** no

- **Required review level:** line-by-line by the reviewer, then brain decision on acceptance

- **Required verification:** scope check; line-by-line diff review; confirm claims against the brief and repo evidence

- **Hazards:**
  - The reviewer mirrors the implementer instead of judging independently.

  - Out-of-scope edits get missed because the diff is only skimmed.

  - A plausible patch is accepted without verifying the contract.

## `second-opinion`

A separate read on a plan, diagnosis, or proposed implementation choice before the brain commits. It is for narrowing uncertainty, not for shipping code.

- **Definition:** The task is to get an independent critique of an approach, assumption set, or likely failure mode.

- **Typical examples:** compare two implementation paths; sanity-check a diagnosis; ask whether a proposed fix is the right class of change.

- **Recommended executor type:** advisory executor (reviewer role), separate invocation from the implementer.

- **Delegation allowed:** advisory-only

- **Agentic execution allowed:** no

- **Required review level:** advisory checklist only; brain keeps ownership of the final decision

- **Required verification:** compare the opinion against the source brief, known constraints, and repository conventions

- **Hazards:**
  - The second opinion becomes a duplicate of the first answer.

  - The critique invents constraints that do not exist in the repo.

  - The brain delegates judgment instead of using the review as input.

## `cheap-exploration`

Low-cost discovery work used to map a problem space before committing stronger resources. This class is for shallow, bounded reconnaissance only.

- **Definition:** The task is to find likely files, patterns, or surface area with minimal spend and no expectation of authoritative final judgment.

- **Typical examples:** locate the most likely implementation file; summarize existing naming patterns; identify which tests touch a feature.

- **Recommended executor type:** cheapest advisory tier.

- **Delegation allowed:** yes

- **Agentic execution allowed:** no

- **Required review level:** brain sanity-checks the findings before any downstream action

- **Required verification:** source trace or file list; scope check; discard if the answer is unsupported or overconfident

- **Hazards:**
  - The cheap tier is asked to make decisions it cannot justify.

  - Sensitive or proprietary data leaks into a low-trust path.

  - Shallow search is mistaken for a complete investigation.

## `domain-sensitive`

Work whose correctness depends on business meaning, product semantics, or operator-confirmed domain rules. The brain may delegate only when the spec is explicit enough to remove interpretation.

- **Definition:** The task touches domain logic where the right answer depends on terminology, policy, or external business rules that are not obvious from code alone.

- **Typical examples:** interpret a product-specific status transition; encode a workflow from an operator-provided spec; apply a domain rule that changes user-facing behavior.

- **Recommended executor type:** agentic code executor only with operator-confirmed spec; otherwise brain only.

- **Delegation allowed:** conditional, only with operator-confirmed spec

- **Agentic execution allowed:** conditional, only when the domain rule is explicit and the implementation surface is bounded

- **Required review level:** brain owns judgment calls and signs off on the interpretation

- **Required verification:** spec trace; focused test covering the confirmed rule; scope check against the approved domain language

- **Hazards:**
  - The executor guesses the meaning of a business rule.

  - A local code pattern overrides the real domain requirement.

  - Ambiguous terminology produces a technically correct but product-wrong result.

## `db-sensitive`

Work that reads, writes, migrates, or reasons directly about persistent data structures. Safety depends on the schema, tenant boundaries, and the blast radius of any query or migration.

- **Definition:** The task can affect database state, schema shape, query semantics, or data integrity.

- **Typical examples:** write a migration; change a query that spans tenant data; adjust a transaction or locking strategy.

- **Recommended executor type:** brain only; optional advisory executor for design review.

- **Delegation allowed:** advisory-only

- **Agentic execution allowed:** no by default; advisory only for design review, not implementation

- **Required review level:** brain owns the final decision and reviews the data-risk path line by line

- **Required verification:** schema or migration diff review; non-destructive test or dry run; scope check for tenant and table coverage

- **Hazards:**
  - A small change cascades into data loss or corruption.

  - The wrong tenant, table, or migration order is touched.

  - Query semantics change without a visible compile failure.

## `security-sensitive`

Work that affects authentication, authorization, secrets, trust boundaries, or attacker-facing surfaces. Default posture is no agentic execution and line-by-line brain review.

- **Definition:** The task can introduce or remove a security control, reveal sensitive material, or expand the attack surface.

- **Typical examples:** change an auth guard; handle secrets or tokens; modify input validation on an attacker-controlled path.

- **Recommended executor type:** brain only; optional advisory second opinion.

- **Delegation allowed:** advisory-only

- **Agentic execution allowed:** no by default; advisory only for second opinion, not implementation

- **Required review level:** brain line-by-line review; the brain owns acceptance

- **Required verification:** targeted auth or permission test; secret-safety check; threat-model check for the changed path

- **Hazards:**
  - An authorization check is weakened or skipped.

  - Secrets, tokens, or PII are exposed in logs or outputs.

  - A boundary change creates an exploit path that normal tests miss.

## `money-sensitive`

Work that can change billing, pricing, invoicing, payouts, credits, or other financial outcomes. The implementation and review stay with the brain.

- **Definition:** The task can alter money movement, money calculation, billing rules, or financial reporting.

- **Typical examples:** update pricing logic; change invoice generation; modify payout calculations or discount application.

- **Recommended executor type:** brain only; advisory second opinion only if needed.

- **Delegation allowed:** advisory-only

- **Agentic execution allowed:** no

- **Required review level:** brain owns implementation and review

- **Required verification:** focused calculation test; sample-case reconciliation; scope check against pricing or billing rules

- **Hazards:**
  - A rounding or unit-conversion bug changes real amounts.

  - The code passes tests while violating the intended financial policy.

  - A small refactor creates customer-visible billing drift.

## `architecture-decision`

A choice about structure, boundaries, or long-lived design where the main work is deciding, not coding. No implementation delegation is allowed for the decision itself.

- **Definition:** The task asks which shape the system should take, which pattern should be adopted, or how responsibilities should be partitioned.

- **Typical examples:** choose between two module boundaries; decide whether to split a service; evaluate a new abstraction or layering model.

- **Recommended executor type:** brain only; optional advisory second opinion.

- **Delegation allowed:** advisory-only

- **Agentic execution allowed:** no

- **Required review level:** brain owns the decision entirely

- **Required verification:** compare options against current constraints; check migration cost; confirm the chosen path fits the repo's existing direction

- **Hazards:**
  - A premature abstraction locks in the wrong boundary.

  - The decision is made without accounting for migration cost.

  - The codebase accumulates parallel patterns instead of one clear direction.

## Precedence

When a task matches multiple classes, the most restrictive class wins. The sensitivity classes (`domain-sensitive`, `db-sensitive`, `security-sensitive`, `money-sensitive`) override convenience classes: a mechanical refactor that touches billing is `money-sensitive`, full stop.

## Canonical source

This file is the canonical class-to-executor routing matrix. `references/executor-capabilities.md` and all templates defer to it; if they disagree, this file wins and the others must be corrected.
