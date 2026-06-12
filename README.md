# orchestrate — Claude Code skill

A production-grade brain & body orchestration skill for [Claude Code](https://claude.ai/code). Keeps Claude as the scarce reasoner (the **brain**) while delegating bulk mechanical work to external executor CLIs (the **body** — codex, opencode/gpt-5.5, opencode/deepseek).

[![skills.sh](https://img.shields.io/badge/skills.sh-orchestrate-blue)](https://skills.sh/Observerstudio/orchestrate-skill)

```bash
npx skills add Observerstudio/orchestrate-skill
```

---

## What it does

When you hit a large, repetitive, well-specified chunk of work, `orchestrate` lets Claude:

1. Write a precise, self-contained **brief** (= the work order + the review rubric)
2. **Dispatch** it to the right executor asynchronously
3. **Review** the output against the brief's acceptance criteria
4. **Integrate** only what passes — nothing lands on your branch unreviewed

Claude stays in the reasoning seat throughout. The body never makes decisions; it does the typing.

### The delegation gate

Work only gets delegated when **all three** hold:

| Check | Why |
|-------|-----|
| **Volume** — ~150+ lines / 3+ files / obviously repetitive | Saves meaningful context |
| **Specifiability** — you can write a complete brief | The body re-loads the repo cold — it needs everything in writing |
| **Verifiability** — result is objectively checkable (compiles, tests pass) | Otherwise review costs as much as the work |

Anything below the gate — small tasks, ambiguous work, security-sensitive logic — Claude keeps and handles itself.

### The data boundary

Every delegation sends code to a third-party model provider. The skill enforces:

- No secrets, `.env*` files, API keys, or PII in any brief
- No `prisma db push`, migrations, or DB writes by the body
- Operator consent before the first delegation on a proprietary repo

---

## Prerequisites

You need **Claude Code** and at least one executor:

| Executor | Install | Role |
|----------|---------|------|
| [codex CLI](https://github.com/openai/codex) | `npm i -g @openai/codex` | Primary code executor — edits files in an isolated git worktree |
| [opencode](https://opencode.ai) | `bun i -g opencode@latest` | Advisory — returns text (gpt-5.5 for quality, deepseek-v4-flash-free for volume) |

You need at least one of the two. Neither is hard-required — if nothing is configured, the skill asks what you have or falls back to working solo as Claude Code.

---

## Installation

**Via the skills CLI (recommended):**

```bash
npx skills add Observerstudio/orchestrate-skill
```

**Via git clone:**

```bash
# macOS / Linux
git clone https://github.com/Observerstudio/orchestrate-skill ~/.claude/skills/orchestrate

# Windows (PowerShell)
git clone https://github.com/Observerstudio/orchestrate-skill "$env:USERPROFILE\.claude\skills\orchestrate"
```

Only `SKILL.md` and `references/` are required at runtime; `evals/` is optional. Claude Code picks up skills from `~/.claude/skills/` automatically.

### Updating

```bash
# skills CLI
npx skills update            # or re-run: npx skills add Observerstudio/orchestrate-skill

# git clone install
git -C ~/.claude/skills/orchestrate pull
# Windows (PowerShell)
git -C "$env:USERPROFILE\.claude\skills\orchestrate" pull
```

Updates never touch your local state: `executors.local.md` (your executor config) is untracked and `.orchestrate/` (briefs, run logs, diffs) is gitignored, so both survive every update. The harness (`harness/orchestrate_run.py`, Python 3 + PyYAML) is optional — the skill works without it; new harness fields like `last_verified` degrade gracefully on configs that don't have them.

---

## Configuration — `executors.local.md`

On first run the skill performs **Step 0 discovery**: it looks for `~/.claude/skills/orchestrate/executors.local.md`. If absent, it probes your PATH and asks which executors you have.

Create the file yourself to skip the prompt:

```
~/.claude/skills/orchestrate/executors.local.md
```

```yaml
---
executors:
  - name: codex
    mode: agentic
    role: primary-code
    invoke: 'Get-Content brief.md -Raw | codex exec --skip-git-repo-check'
    isolate: worktree
    notes: gpt-5.5 backend; ~4s start; approval:never workspace-write

  - name: gpt-5.5
    mode: advisory
    role: high-quality-text
    invoke: 'opencode run -m opencode/gpt-5.5 --print-logs "<PROMPT>"'
    notes: 60s+ latency; cold-loads project each call

  - name: deepseek
    mode: advisory
    role: cheap-volume
    invoke: 'opencode run -m opencode/deepseek-v4-flash-free --print-logs "<PROMPT>"'
    notes: free tier; slowest; keep off critical path
---
```

Adjust the `invoke` strings to match your OS (the examples above are for PowerShell/Windows; macOS/Linux uses plain shell syntax). See [`references/executors.md`](references/executors.md) for the exact adapter details, latencies, and known gotchas — there are sharp edges (stdin hangs, `-f` flag ordering, `Select-Object` buffering) that will waste cycles if you wing it.

---

## Usage

### Explicit invocation

Use any of these triggers in your message to Claude:

```
orchestrate this
delegate to codex
farm this out to opencode
use the brain and body
use codex / use gpt-5.5 / use deepseek
```

### What Claude does

1. **Discovers** executors from `executors.local.md` (or asks/probes on first run)
2. **Checks the gate** — volume + specifiability + verifiability
3. **Writes a self-contained brief** with objective, scope, anti-scope, contract, conventions, acceptance criteria, and output format
4. **Dispatches async** to the right executor (agentic → worktree isolation; advisory → applies output itself)
5. **Reviews the result** against the brief's acceptance criteria — re-runs typecheck/tests itself, never trusts the body's self-report
6. **Integrates** only what passes; bounces or fixes the rest

### Proactive offers

When Claude notices delegable bulk mid-task, it **offers** rather than auto-spends:

> "This is ~400 lines of mechanical transforms across 8 files — want me to farm it to codex while I keep working on the design?"

You answer; it acts. Explicit invocation is a green light; Claude spotting an opportunity is an offer.

### Fallback behavior

If an executor is rate-limited, unavailable, or unconfigured:
- Claude asks what to use instead, **or**
- Continues working solo as Claude Code

It never loops retrying a rate-limited model. On a shared/new machine, it asks which executors you want to use and records them in `executors.local.md` — so each operator configures their own toolbox.

---

## v0.2 structured workflow

The skill now uses a structured dispatch contract:

1. **Classify** the task against the canonical task-class matrix.
2. **Pick an executor** whose capability record allows that class.
3. **Write a frontmatter brief** — machine-readable contract in, machine-readable run report out.
4. **Dispatch** in the correct mode (agentic → isolated worktree; advisory → diff/text the brain applies).
5. **Verify deterministically** — the brain re-runs verification; the body's report is a claim, not evidence.
6. **Review and integrate** only what passes; sensitive classes never leave the brain.

See:
- [`references/task-classes.md`](references/task-classes.md) — 13 task classes + routing rules (canonical)
- [`references/executor-capabilities.md`](references/executor-capabilities.md) — capability records per executor
- [`templates/brief-template.md`](templates/brief-template.md) — frontmatter brief + run report schema
- [`docs/v0.2-roadmap.md`](docs/v0.2-roadmap.md) — where this is heading (v0.3 harness and beyond)

---

## Reference files

| File | Purpose |
|------|---------|
| [`SKILL.md`](SKILL.md) | The full skill — Claude reads this when orchestrate is invoked |
| [`references/task-classes.md`](references/task-classes.md) | Canonical task-class routing matrix |
| [`references/executor-capabilities.md`](references/executor-capabilities.md) | Executor capability records and routing rules |
| [`references/executors.md`](references/executors.md) | Adapter field guide: exact headless invocations, latencies, failure signatures, worktree recipe |
| [`references/brief-and-review.md`](references/brief-and-review.md) | Brief template + worked example + review checklist |
| [`templates/brief-template.md`](templates/brief-template.md) | v0.2 frontmatter brief + run report contract |
| [`evals/evals.json`](evals/evals.json) | 7 behavioral evals covering the key rules |

---

## Behavioral evals

Seven cases covering the most important behaviors:

| ID | Name | Tests |
|----|------|-------|
| 0 | `decline-small-ambiguous` | Below-gate task stays with Claude; no delegation |
| 1 | `delegate-bulk-with-brief` | Full brief + worktree isolation when gate is met |
| 2 | `refuse-secret-and-db` | Data boundary enforced; no `.env` in brief, no `db push` |
| 3 | `fallback-executor-down` | Graceful degrade when codex is rate-limited |
| 4 | `proactive-offer-not-seize` | Offer vs auto-dispatch when operator didn't ask |
| 5 | `fresh-machine-discovery` | Step-0 discovery on a new machine |
| 6 | `revision-cap-non-converging` | Stop at 2 non-converging rounds; don't re-spin endlessly |

Run them with the Claude Code SDK or a harness of your choice. The schema is in [`evals/evals.json`](evals/evals.json).

---

## Mental model

```
You (operator)
  └── Claude (brain) — design, review, integration, judgment
        └── Executor (body) — bulk typing, in a sandboxed worktree
```

The brain writes the brief, reviews the diff, and owns accountability. The body never owns judgment. When the body is down, the brain keeps working.

---

## License

MIT — see [LICENSE](LICENSE).
