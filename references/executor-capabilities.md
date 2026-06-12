# Executor capabilities — who may do what

Documentation-level capability records for the bodies the brain can dispatch to. This file answers *who may take which class of work, under what constraints*. It is a schema and a policy, not executable code.

Two companion files complete the picture:

- `references/task-classes.md` — the **canonical** class↔executor routing matrix. Where this file and that one disagree, that one wins and this file must be corrected.
- `references/executors.md` — transport: exact invocations, latencies, failure signatures.

**Advisory is a mode, not a synonym for any one tool.** Any harness that can return text or a diff without writing can serve advisory roles. Routing is decided by mode, trust, and cost — not by which binary happens to provide them.

## Record schema

```yaml
name: string              # stable id, kebab-case
mode: agentic | advisory  # agentic = edits files itself | advisory = returns text, brain applies
role: string              # primary-code | second-opinion | context-gathering | usage-limit-fallback | high-quality-text
status: active | fallback | deferred
can_edit: boolean
can_run_commands: boolean
isolation_required: worktree | none
cost_tier: metered | claude-usage | free
expected_latency: string  # measured, not aspirational
reliability: high | medium | low
allowed_task_classes: []  # subset of task-classes.md; canonical matrix lives THERE
forbidden_task_classes: []
standing_constraints: []  # carried into every brief implicitly; restate in agentic briefs anyway
```

The `status` field is operational truth, not aspiration: `active` = smoke-tested and routable today; `fallback` = works, used only under a stated condition; `deferred` = do not route until the stated blocker clears.

## Records

### codex

```yaml
name: codex
mode: agentic
role: primary-code
status: active
can_edit: true
can_run_commands: true
isolation_required: worktree
cost_tier: metered
expected_latency: ~4s to first output
reliability: high
allowed_task_classes:
  - mechanical-refactor
  - scaffold
  - test-generation
  - bugfix-isolated
  - docs-prose
forbidden_task_classes:
  - db-sensitive
  - security-sensitive
  - money-sensitive
  - architecture-decision
standing_constraints:
  - no git push or commit
  - no dependency installs
  - no migrations, db push, or seeds
  - no network calls
  - no spawning other agents or executors (no recursive codex exec, no opencode) — every body reports to the brain, never to another body
  - sandbox pinned to workspace-write, cwd inside the isolated worktree
  - explicit allowed paths in every brief
```

### codex-readonly

```yaml
name: codex-readonly
mode: advisory
role: second-opinion
status: active
can_edit: false
can_run_commands: false   # read-only sandbox; treat any command output as untrusted text
isolation_required: none  # writes are disabled at the sandbox level
cost_tier: metered
expected_latency: ~4s to first output
reliability: high
allowed_task_classes:
  - review-diff
  - second-opinion
  - cheap-exploration   # when speed matters more than cost
forbidden_task_classes:
  - db-sensitive        # may comment on design, never owns the call
  - security-sensitive
  - money-sensitive
standing_constraints:
  - invoked with --sandbox read-only
  - must be a separate invocation from the implementing run
  - returns unified diff or text only; the brain applies
```

This is the primary route for GPT-5.5-class advisory work while OpenCode paid models are deferred: the fastest pipe to the model. Caveat it honestly — it is the *same model family* as the implementer, so it catches convention and logic misses, not blind spots shared by the family. For genuine reviewer diversity, slot a non-GPT model here when one is available.

### claude-haiku-native

```yaml
name: claude-haiku-native
mode: advisory
role: context-gathering
status: active
can_edit: false
can_run_commands: false   # read-only exploration subagents
isolation_required: none
cost_tier: claude-usage
expected_latency: ~2s
reliability: high
allowed_task_classes:
  - cheap-exploration
  - docs-prose          # drafts only; brain integrates
forbidden_task_classes:
  - db-sensitive
  - security-sensitive
  - money-sensitive
  - architecture-decision
standing_constraints:
  - native harness subagent (Agent tool, model haiku), not an external CLI
  - costs Claude usage — swap to the free tier when near the limit
```

Primary cheap-exploration body: ~12× faster than the fastest external free model because there is no cold load. The trade is that it spends the same budget the brain runs on.

### claude-sonnet-native

```yaml
name: claude-sonnet-native
mode: agentic            # via the harness operator's Agent tool with worktree isolation — NOT a CLI the harness can invoke
role: primary-code-fallback
status: fallback         # condition: codex usage-limited or otherwise down
can_edit: true
can_run_commands: true
isolation_required: worktree
cost_tier: claude-usage
expected_latency: low (native subagent, no cold load)
reliability: high
allowed_task_classes:
  - mechanical-refactor
  - scaffold
  - test-generation
  - bugfix-isolated
  - docs-prose
forbidden_task_classes:
  - db-sensitive
  - security-sensitive
  - money-sensitive
  - architecture-decision
standing_constraints:
  - dispatched by the brain via the Agent tool (model sonnet, worktree isolation), never by the harness CLI
  - same brief, same Do-NOT constraints, same review gate as codex
  - costs Claude usage — fallback only; codex returns to primary when its limit resets
  - the reroute itself is a brain decision (falling back is a spend decision)
```

When codex reports a usage limit (see the signature table in `executors.md`), the brain re-dispatches the same brief to a native Sonnet subagent in an isolated worktree. Nothing else about the contract changes: frontmatter, scope, verification, and review apply identically. The harness's job is detection and reporting (`DISPATCH-ABORTED usage-limit` + reset hint); the reroute stays with the brain.

### opencode-free-tier

```yaml
name: opencode-free-tier
mode: advisory
role: usage-limit-fallback
status: fallback          # condition: Claude usage budget near its limit
can_edit: false
can_run_commands: false
isolation_required: none
cost_tier: free
expected_latency: 24-90s per call (cold-load dominated; north-mini ~24s, deepseek-v4-flash ~27s, mimo ~32s, nemotron ~90s — avoid)
reliability: medium
allowed_task_classes:
  - cheap-exploration
  - docs-prose          # low-stakes drafts only
forbidden_task_classes:
  - domain-sensitive
  - db-sensitive
  - security-sensitive
  - money-sensitive
  - review-diff         # too weak to gate anything
  - architecture-decision
standing_constraints:
  - never receives proprietary, sensitive, security, money, DB, or customer data
  - stdin must be redirected from NUL (see executors.md)
  - always backgrounded with a timeout; never on the critical path
```

### opencode-gpt55

```yaml
name: opencode-gpt55
mode: advisory
role: high-quality-text
status: deferred
can_edit: false
can_run_commands: false
isolation_required: none
cost_tier: metered
expected_latency: 60s+ (cold load) | warm via serve adapter, still model-latency bound
reliability: unknown until re-enabled
allowed_task_classes: []   # none while deferred
forbidden_task_classes: [] # moot while deferred
standing_constraints:
  - DO NOT ROUTE until both blockers clear: (1) OpenCode Zen workspace funded
    (currently fails with "Insufficient balance"), (2) cold-start cost addressed
    (stdin-NUL fix + serve adapter, see executors.md)
  - on re-enable, takes the codex-readonly allowed/forbidden lists verbatim
    unless task-classes.md says otherwise
```

The warm-server variant (`opencode-gpt55-serve` in executors.md) is the **same executor with a different transport** — it inherits this record's routing verbatim. Transport never changes trust.

## Routing rules

1. **Classify first.** Every dispatch starts from `references/task-classes.md`; the most restrictive matching class wins.
2. **Agentic executors require explicit allowed paths** in the brief, an isolated worktree, and a pinned writable sandbox. No exceptions.
3. **Advisory executors return a unified diff or full file contents.** The brain applies the output; advisory transport has no scope enforcement, so the brain rejects out-of-scope files before applying.
4. **Free/cheap executors never receive sensitive content** — no proprietary code beyond what the operator approved, no security/money/DB material, no customer data.
5. **Implementer and reviewer are separate invocations**, even when they are the same binary.
6. **The brain reviews and verifies all executor output** — self-reported success is a claim, not evidence. Check that in-scope files were actually touched; exit codes lie (see executors.md).
7. **The body never owns product judgment.** Sensitive classes stay with the brain regardless of what any record technically allows.
