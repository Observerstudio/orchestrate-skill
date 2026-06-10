# Executors — transport adapters & field guide

How to actually drive each body model headlessly, what breaks, and how to add a new one. These invocations were verified on the operator's environment (Windows / PowerShell 7). Confirm, don't assume — a different machine may differ.

## Config: `executors.local.md`

Lives at `~/.claude/skills/orchestrate/executors.local.md`. Records this operator's toolbox so you don't re-probe or re-ask. Create it on first run (after discovery/asking), read it thereafter. Shape:

```markdown
---
executors:
  - name: codex
    mode: agentic          # agentic = edits files | advisory = returns text
    role: primary-code
    invoke: 'Get-Content brief.md -Raw | codex exec --skip-git-repo-check'  # run from inside the worktree
    isolate: worktree       # required for agentic — cd into the worktree first
    notes: gpt-5.5 backend; ~4s start; approval:never, workspace-write
  - name: gpt-5.5
    mode: advisory
    role: high-quality-text
    invoke: 'opencode run -m opencode/gpt-5.5 --print-logs "<PROMPT>"'
    notes: 60s+ latency; cold-loads project each call
  - name: deepseek
    mode: advisory
    role: cheap-volume
    invoke: 'opencode run -m opencode/deepseek-v4-flash-free --print-logs "<PROMPT>"'
    notes: free tier, slowest; off the critical path
---

Free-text notes about this operator's preferences, limits, billing, etc.
```

When discovery finds nothing, ask the operator for each executor's `name`, `mode`, and exact headless `invoke` string, then write this file.

## Known adapter: codex (agentic)

- **Binary:** `codex` (codex-cli). On the operator's box: `C:\Program Files\nodejs\codex.ps1`.
- **Invoke — feed the brief via STDIN from a file, never as a bare arg:**
  ```powershell
  Get-Content brief.md -Raw | codex exec --skip-git-repo-check
  ```
  Two reasons. (1) Bare-arg form (`codex exec "prompt"`) **hangs** in a non-TTY shell: it prints `Reading additional input from stdin...` and blocks forever waiting on stdin that never closes — piping is what makes it headless. (2) Real briefs are multi-line markdown with backticks, `$`, quotes, and `[ ]`; inlining one as a double-quoted PowerShell arg interpolates `$…` and breaks on embedded quotes. Always write the brief to a file and pipe it in.
- **Latency:** ~4s to start producing output when healthy.
- **Sandbox reality:** defaults to `approval: never` + `sandbox: workspace-write` scoped to its **current working directory**. It *will* edit files with no confirmation, and the sandbox stops at file edits — it does **not** isolate the database (the worktree inherits the same `.env`/`DATABASE_URL`), the network, package installs, or the git remote. → **Always run it inside an isolated worktree (cd into it — see recipe)** *and* put hard Do-NOT constraints in the brief: no migrations/`db push`/seeds/DB writes, no `git push`/`commit`, no installs, no network. If codex exposes a tighter sandbox (`-c sandbox_permissions=...` / read-only modes), prefer it for review-style runs.
- **Timeout it.** A wedged codex run should be killed and treated as down, same as opencode — don't let an agentic call hang the session.
- **Backend:** runs `gpt-5.5` via `openai` provider by default.
- **Usage-limit signature (treat as "down"):**
  ```
  ERROR: You've hit your usage limit. Upgrade to Pro ... try again at 8:12 PM.
  ```
  When you see this, don't retry — apply the availability rule (ask operator / go solo).

## Known adapter: opencode (advisory)

- **Binary:** `opencode`. On the operator's box: `C:\Users\A store\.bun\bin\opencode.exe` (installed via bun; not always on PATH — use the full path or confirm PATH).
- **Invoke — non-interactive `run` subcommand:**
  ```powershell
  opencode run -m opencode/gpt-5.5 --print-logs "Your full brief here"
  ```
  - `-m provider/model` — e.g. `opencode/gpt-5.5`, `opencode/gpt-5.5-pro`, `opencode/deepseek-v4-flash-free`, `opencode-go/deepseek-v4-pro`. List with `opencode models`.
  - `--print-logs` streams diagnostics to stderr so you can confirm it's alive.
  - `--format json` for machine-parseable events instead of formatted text.
  - `-f <file>` attaches files to the message. **Gotcha:** `-f` is a greedy array flag — if the positional message follows it (`... -f a.md -f b.md "$prompt"`), opencode swallows the prompt as another filename and dies with `Error: File not found: <your prompt text>`. Put the message **first** (`opencode run "$prompt" -m … -f a.md`) or pass the prompt itself via `-f`. **Never `-f` a secret-bearing file** (`.env*`, anything with keys/PII) — attaching sends it straight to the provider.
- **Latency:** **high — 60s+.** Each call cold-bootstraps: creates an instance, loads the project at the cwd, loads plugins, inits providers (~4s), *then* calls the model (the bulk of the wait), and may run a snapshot prune. Free DeepSeek is the slowest.
- **Critical gotcha — never pipe through `Select-Object`/`Select-String`:** `opencode run ... | Select-Object -Last N` makes PowerShell buffer the entire stream and *looks* like an indefinite hang. Redirect to a file or let it stream raw instead.
- **Advisory only:** it returns text to stdout; it does not edit your repo. You apply whatever it returns.

## Async dispatch pattern

Because opencode is 60s+, **always background body calls** and keep doing brain-work while they run. PowerShell, writing to a file you can poll:

```powershell
$prompt = Get-Content brief.md -Raw
opencode run -m opencode/gpt-5.5 --print-logs $prompt *> .orchestrate/<ts>/gpt55.out
```

Run this via the background-task mechanism, then poll the output file. Set a generous timeout (≥120s for opencode). Treat empty output past the timeout as an availability failure.

## Worktree isolation (mandatory for agentic executors)

Never let codex edit the live branch. The load-bearing step everyone gets wrong: codex roots its `workspace-write` sandbox at **its current working directory**, so creating a worktree does nothing unless you actually *run codex from inside it*. Run it from the worktree, capture the diff, then merge deliberately — and clean up even on failure:

```powershell
$wt = "../orchestrate-wt-$(Get-Random)"          # collision-proof; one per dispatch
git worktree add $wt HEAD                          # isolated copy at current commit
try {
    Push-Location $wt                              # <-- codex's cwd MUST be the worktree
    try   { Get-Content ..\<repo>\brief.md -Raw | codex exec --skip-git-repo-check }
    finally { Pop-Location }
    git -C $wt diff                                 # review what it actually did
    git -C $wt status --porcelain                   # confirm it wrote HERE, not in the live repo
}
finally {
    git worktree remove $wt --force                 # runs even on crash/abort — AFTER you've captured the diff
}
```

**Verify isolation worked:** if `git status` in your *live* repo shows unexpected changes, codex escaped the worktree (wrong cwd) — discard and fix the invocation before trusting anything. If your harness exposes a worktree-isolation primitive for subagents, prefer it. The invariant: **the body's writes land somewhere you inspect before they touch the operator's branch.**

At session start or after any crash, sweep leftovers: `git worktree list` then `git worktree prune` and remove stale `orchestrate-wt-*` — but only after capturing any diff you still care about, since `--force` discards uninspected work.

## Integrate — getting approved work onto the branch

Reviewing the worktree diff is not the end; you still have to land the approved subset. Be explicit, never hand-copy:

- **Approve everything:** apply the whole diff to the live tree —
  `git -C $wt diff | git -C <live-repo> apply --index`
- **Approve a subset** (e.g. 6 of 8 files passed review): restrict by path —
  `git -C <live-repo> checkout $wt-branch -- path/a.ts path/b.ts`  *(or `git diff -- <paths> | git apply`)* — and leave the rejected files behind.
- **Advisory output (opencode text):** apply as an **all-or-nothing batch from a clean tree**. For a returned unified diff, `git apply --check` first; if it doesn't apply cleanly, don't force it. **Reject any returned file outside the brief's scope before applying** — advisory transport has no scope enforcement, so a careless write lands an out-of-scope file. If application fails partway, `git checkout -- <paths>` to reset and re-apply cleanly.

After integrating, **re-run `typecheck`/`lint`/`test` on the live tree yourself** — the worktree's green is not your branch's green.

## Failure signatures → action

| Signature | Meaning | Action |
|-----------|---------|--------|
| `Reading additional input from stdin...` (codex, hangs) | prompt passed as arg, not stdin | re-invoke with `Get-Content brief.md -Raw \| codex exec` |
| `Error: File not found: <your prompt text>` (opencode) | `-f` greedily ate the trailing positional message | put the message before `-f`, or pass it via `-f` |
| `You've hit your usage limit` (codex) | quota exhausted | don't retry; ask operator / go solo; note reset time |
| empty output past timeout (either) | model slow/throttled or stuck | kill, treat as down; ask operator / go solo |
| non-empty but truncated/incomplete (agentic died mid-run) | partial edit (e.g. usage limit hit at file 4 of 8) | **discard, don't revise**; re-brief from clean HEAD |
| apparent infinite hang with `Select-Object` in pipe | PowerShell buffering, not a real hang | redirect to file instead of piping |
| live repo shows changes after an agentic run | codex ran in wrong cwd, escaped the worktree | discard; fix cwd (run from inside the worktree) |
| binary not found on PATH | not installed / different env | discover + ask operator; update `executors.local.md` |

## Onboarding a new executor

When an operator has something else (Ollama, Cursor CLI, aider, a hosted API, etc.):

1. Get its **headless one-shot invocation** (the analog of `codex exec` / `opencode run`) — confirm it doesn't require a TTY and accepts the prompt via arg, stdin, or file.
2. Classify its **mode**: does it *edit files* (agentic — needs worktree isolation) or *return text* (advisory — you apply output)?
3. Assign a **role** by capability/cost (primary-code / high-quality-text / cheap-volume / reviewer).
4. Smoke-test with a trivial prompt ("reply with exactly: PONG"), note latency and any stdin/TTY/buffering quirks.
5. Record all of it in `executors.local.md`.
