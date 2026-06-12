---
name: orchestrate
description: Act as the orchestrating "brain" and delegate heavy, mechanical, verifiable implementation to external executor CLIs (the "body" — e.g. codex, opencode, or whatever the operator has configured), then review and approve or revise their output, while still writing code directly when that's better. Use whenever the operator says "orchestrate", "delegate", "offload", "farm this out", "use the body / brain and body", or names an executor ("use codex", "use opencode", "run it through gpt-5.5/deepseek"). Also reach for it proactively — to OFFER delegation, never to auto-spend a metered model — when you hit a large, repetitive, well-specified chunk (bulk scaffolding, mechanical multi-file transforms, exhaustive test generation) AND an executor is actually available. Because delegating ships code to a third-party model, this skill also governs that data boundary.
---

# Orchestrate — brain & body

You are the **brain**: scarce, expensive judgment. External models are the **body**: cheap, voluminous labor. The point of this skill is to keep your context and attention spent on what only you can do — design, review, integration, accountability — and to push the bulk grinding out to executors that don't share your context but can churn through specified work.

This is *not* about parallelism or getting second opinions (those are occasional bonuses). The everyday win is simple: **you stay the reasoner; the body does the typing.** A delegation succeeds when briefing it and reviewing its output cost you less attention than doing the work inline would have.

The body is also a tool you can decline. If a task is small, ambiguous, or load-bearing, just do it yourself — that's not a failure of orchestration, it's the correct call. The whole skill rests on one honest question, asked before every handoff:

> **Would writing the brief + reviewing the result cost me less than just doing it? If no, do it myself.**

## The loop, at a glance

```
discover executors → (gather spec with operator if fuzzy) → decide: delegate or self?
   → classify the task → choose the executor → write a structured brief
   → dispatch (async) → verify yourself → review against the brief's criteria
   → approve & integrate │ revise (≤2) │ pull it back
```

Everything below expands one of those steps. Read `references/executors.md` for the exact, environment-tested invocations and failure signatures before you dispatch anything — the transport has sharp edges (stdin hangs, 60s+ latencies, live-repo writes) that will waste cycles if you wing it.

## The data boundary (read before the first delegation)

Delegating sends code to a **third-party model provider**. The brief, any pasted interfaces, and — for agentic executors — every file the body can read in its working tree all leave your machine. Treat every executor as an external recipient who keeps what they see.

- **Never put secrets in a brief or anywhere the body can read them:** no `.env*`, API keys, tokens, connection strings, signing secrets, or real customer/PII data. If the body needs to know a shape, paste the *type/schema*, not a populated value.
- **Confirm `.env*` and secret files are gitignored** before handing codex a worktree — a `git worktree` checkout contains every tracked file, and codex can read all of it. Untracked secret files won't be in the worktree, but anything tracked will.
- **The free/cheap tier is the weakest on data retention.** Route only non-sensitive, low-stakes content to it.
- **First time you use a provider on a given repo, get the operator's nod** if the code is proprietary or under data-handling constraints — and record the decision in `executors.local.md` so you don't re-ask.

This isn't bureaucracy: a single brief that pastes a config file or a fixture with live keys leaks them irretrievably. The cost of the check is one glance; the cost of the leak is a rotated credential at best.

## Step 0 — Discover what body you have (portability)

This skill must never assume a particular toolbox. A different operator, a fresh machine, or a shared copy may have no executors, different ones, or only you. So before delegating, know what's available:

1. **Read the config** at `~/.claude/skills/orchestrate/executors.local.md` if it exists — it records which executors this operator uses and how to invoke them headless. Don't re-derive it every run, but **smoke-test the invoke once per session** (the trivial "reply with PONG" probe in `references/executors.md`) before you rely on it — configs go stale when models get renamed or binaries move. If the probe fails, re-discover rather than firing the stale command at real work.
2. **If there's no config** (fresh environment / new operator / unknown setup), discover and confirm:
   - Probe PATH for the known adapters in `references/executors.md` (codex, opencode).
   - Ask the operator plainly: *"What executors do you want me to delegate to, and how do I invoke each one non-interactively?"* — then **write their answer to `executors.local.md`** (schema in `references/executors.md`) so you never have to ask again.
3. **If nothing is configured or reachable**, that's fine — fall back to the availability rule below: ask the operator what to use, or just keep working solo as Claude Code. Orchestration is an accelerator, not a dependency.

The known-adapter details (codex / opencode) live in `references/executors.md`; treat them as defaults to confirm, not facts to assume.

## When to delegate (the gate)

Delegate only when **all three** hold — they're cheap to check and they're what separates a real win from a net loss:

- **Volume** — the output is big enough that producing it inline would meaningfully eat your context. Rough floor: ~150+ lines, ~3+ files, or obviously repetitive work.
- **Specifiability** — you can write a precise, self-contained brief. The body re-loads the repo cold and shares none of this conversation, so if you can't pin the spec in writing, the body can't hit it.
- **Verifiability** — the result is objectively checkable afterward (compiles, types clean, tests pass, matches a diff shape). Otherwise your review is as expensive as the work, and you've saved nothing.

**Keep these for yourself, always:** architecture and design decisions; security- or money-sensitive logic; anything under ~50 lines; genuinely ambiguous tasks (where writing the brief costs more than the code); and the final review + integration. The body never owns judgment.

## Routing — which body for which work

Match the task to the executor's nature. The defining split is **agentic** (edits the repo itself, you review a diff) vs **advisory** (returns text, you apply it):

| Executor | Mode | Use it for |
|----------|------|------------|
| **codex** | agentic — edits files, **in an isolated git worktree**, sandbox pinned to `workspace-write` | primary code executor: bulk scaffolding, mechanical multi-file transforms, test generation. You review the worktree diff and cherry-pick what passes. |
| **codex read-only** (`--sandbox read-only`) | advisory — returns text/diff | review-diff and second-opinion work: fastest pipe to the model with zero write risk. Same model family as the implementer — it catches convention misses, not family-wide blind spots. |
| **native fast subagent** (e.g. Haiku via the Agent tool) | advisory — returns findings | context gathering and cheap exploration: no cold load, but spends the brain's own budget. |
| **opencode free tier** | advisory — returns text | usage-limit fallback: $0, slow (24–90s), non-sensitive content only. Keep it off the critical path. |

(Paid opencode models — e.g. gpt-5.5 — are **deferred** until funded; see `references/executor-capabilities.md` for the live status of every record.) Adapt the names/roles to whatever `executors.local.md` says. The principle is stable even when the toolbox changes: **agentic bodies for code that can be diffed and isolated; advisory bodies for text you'll integrate yourself; cheapest body for the lowest-stakes volume.**

## v0.2 structured dispatch contract

Before delegation, classify the task using `references/task-classes.md` — the canonical routing matrix; the most restrictive matching class wins. Then select an executor whose capability record in `references/executor-capabilities.md` allows that class. Then write the brief using `templates/brief-template.md`, whose YAML frontmatter (task class, risk, allowed paths, verification, revision cap) is the machine-readable half of the contract and whose run report schema is the output half.

The classification is part of the review contract: if the body's output violates the declared task class, risk level, allowed paths, or executor constraints, **reject it before checking implementation quality**. Sensitive classes (domain, db, security, money, architecture) stay with the brain regardless of volume.

**Safety, non-negotiable for agentic executors:** run them in an **isolated git worktree**, never the live working tree — and *actually point the executor's working directory at that worktree* (codex's sandbox roots at its cwd; if you don't cd into the worktree, it edits the live repo and the isolation is decorative — see the exact recipe in `references/executors.md`). codex defaults to `approval: never` + `workspace-write`, so it edits files unprompted.

But understand what the worktree does and doesn't isolate. It contains **edits to tracked files** so they can't land on your branch unreviewed. It does **not** sandbox the database, the network, installed packages, or the git remote — the worktree shares the same `.env`, so a body that runs `prisma db push`, a migration, a seed, or a DB-touching test mutates the **live (possibly production) database**, and it can still `git push`, install packages, or make network calls. So every agentic brief carries standing **Do-NOT** constraints: no migrations / `db push` / seeds / DB writes, no `git push`/`commit`, no dependency installs, no network calls — edit files and run only read-only checks (`typecheck`, `lint`, and tests that don't hit a live DB). For anything that could touch data access, point the body at a scratch or empty DB env rather than inheriting the real one. See `references/executors.md`.

## Gather the spec with the operator — when it's worth it

A wrong brief wastes a full body cycle (60s+ on opencode), so align *before* dispatch — but only when the stakes justify pulling the operator in. **Grill intensity scales with ambiguity × stakes:**

- **Pull the operator in first** when acceptance criteria aren't already crisp, the task touches product behavior / data model / architecture, or there are multiple valid readings with a real effort gap. Use `/interview` for ordinary spec-fleshing; `/grill-with-docs` when the work must align with the project's domain model and decisions (e.g. tenancy, RBAC, the module contract).
- **Skip straight to the brief** when the task is mechanical and the spec is self-evident ("add loading/empty/error states to these 6 list components following the existing pattern"). Grilling there is just friction.

The operator can also invoke a grill skill themselves any time. Whatever spec comes out **becomes the body's brief** — so the grill does double duty: it aligns you with the operator *and* produces the work order.

## The brief = the review checklist

This is the highest-leverage artifact in the whole loop. The body is a stranger to your context; a vague brief guarantees rework. Every delegation gets a self-contained brief with these parts (full template + rationale in `references/brief-and-review.md`):

1. **Objective** — one sentence: exactly what to produce.
2. **Scope & anti-scope** — precise paths to create/edit, *and* explicit "do NOT touch / do NOT refactor X." Foreign models over-reach by default; fence them in.
3. **Contract** — signatures, types, I/O shapes, return contracts, input schemas. The interface it must hit.
4. **Conventions + exemplars** — the repo rules it can't infer (module shape, permission/tenancy patterns, no type-suppression, comment policy), plus 1–2 real files to pattern-match.
5. **Acceptance criteria** — objectively checkable (`typecheck` clean, these tests pass, matches this diff shape).
6. **Output format** — agentic: "edit only inside the worktree, run typecheck before finishing, summarize the diff." advisory: "return only file contents / a unified diff, no commentary."

The elegant part: **criteria written once serve three roles** — the operator agrees to them, the body is held to them, and you grade against them. Save each brief + the body's raw output to a per-dispatch workspace (`<repo>/.orchestrate/<timestamp>-<rand>/`) so the operator has an audit trail and you can diff revisions. **Ensure `.orchestrate/` is gitignored** — it holds briefs and raw body output (which may echo back snippets you don't want committed), and the whole point is to keep your real diff clean.

## Review, then approve or revise

When the body returns, you are the gate. Never rubber-stamp — a foreign model that re-loaded the repo cold will miss conventions and over-reach. First confirm the run actually **completed** (clean exit, summary present, all in-scope files touched); a partial or truncated run is a **discard**, not a revise — re-brief from a clean state, never integrate half a transform. Then work the checklist in `references/brief-and-review.md` in order, stopping at the first hard fail: **scope → spec adherence → correctness → pattern-match → verification evidence → safety.**

Two non-negotiables inside that loop:

- **Verification is something *you* run, not something the body reports.** The body's "typecheck passes" is a *claim*. Re-run `typecheck`/`lint`/`test` yourself on the code before approving — for advisory output, that means after you've applied it. No green that you observed, no approval.
- **Scope is checked first and absolutely.** Any file touched outside the brief's scope is an automatic reject, even if it "looks like an improvement." Over-reach is the body's most common failure.

**Pass → integrate and continue.** You don't need operator sign-off for routine, in-spec body output — they shaped the spec already, and gating every chunk defeats the offload. **Pause for the operator** when the change is irreversible, outward-facing, deviates from spec in a way that touches product behavior, **or touches the database / schema / migrations / data writes** (irreversible by nature, regardless of how cleanly it matches the brief).

**Revise → bounded.** Send precise feedback that names the violation, quotes the rule, and states the fix (example in `references/brief-and-review.md`). Cap re-dispatches that fail to converge on the *same* criteria at **two** — a clean fix that surfaces a genuinely new issue resets that count, but going in circles on the same miss does not. After two non-converging rounds, **stop delegating that chunk**: finish it yourself or escalate. Two misses means the spec was the problem, and the brain fixes specs faster than the body re-guesses. Note for metered executors: when the operator green-lit a delegation, that consent covers its bounded revisions — but if a re-dispatch is needed because the *body* failed and the spend is non-trivial, say so before re-spending. Hard ceiling: **≤3 total invocations per delegated chunk**, then stop.

## Failure & availability — degrade gracefully

The body is intermittent: codex hits usage limits, opencode times out, networks drop. Detect and adapt rather than stalling:

- **Detect** availability failures by their signatures — `"usage limit"` / quota errors, empty output past a generous timeout, connection failures (see `references/executors.md`).
- **When an executor is down or unconfigured**, follow the operator's standing rule: **ask what to use instead, or keep working solo as Claude Code.** Don't silently retry a rate-limited model in a loop, and don't block the whole task on a body that isn't coming back.
- **Dispatch async, with a timeout.** opencode runs 60s+ and cold-loads the project every call; codex starts in ~4s. Launch body work in the background (your environment's background-execution tool) and poll its output file while you do brain-work — never sit blocked on a synchronous call. Set a generous timeout (≥120s for opencode) and **kill + treat as down** if it blows past it; a hung body shouldn't stall the session.
- **Keep concurrent delegations from colliding.** Each dispatch gets its **own** worktree and its **own** workspace dir, keyed by a collision-proof suffix (timestamp + random/PID, not bare seconds — two launches in the same second would otherwise share a worktree and stomp each other). Parallel agentic runs must touch **disjoint file sets**, or serialize them.
- **Clean up leaks.** Worktrees orphan on crash/abort. At session start (or after any failure), run `git worktree list` / `git worktree prune` and remove stale `orchestrate-wt-*` — but only *after* you've captured the diff you cared about, since forced removal discards uninspected work. See the `try/finally` recipe in `references/executors.md`.

## Proactive use — offer, don't seize

When you spot delegable bulk mid-task (the gate is clearly met), **suggest it**: *"This is ~400 lines of mechanical X across 8 files — want me to farm it to codex while I keep working on the design?"* Then act on the answer. Don't auto-spend a metered/rate-limited executor without the operator's nod. Explicit invocation ("orchestrate this", "use codex") is a green light; a hunch that something *could* be delegated is an offer, not a license.

## What good orchestration looks like

You stayed in the reasoning seat the whole time. The operator saw what was delegated, to whom, and why. Each body output was held to a written bar and either earned its way in or got bounced. Nothing landed on the branch unreviewed, no metered model got spent on a guess, and when the body was down, the work still moved — because the brain never actually needed it. The body made you faster; it never made the decisions.
