# Executors — transport adapters & field guide

How to actually drive each body model headlessly, what breaks, and how to add a new one. These invocations were verified on the operator's environment (Windows / PowerShell 7). Confirm, don't assume — a different machine may differ.

For *which* executor may take *which* class of work, see `references/executor-capabilities.md` (capability records) and `references/task-classes.md` (the canonical routing matrix). This file covers transport only.

## The stdin rule (read first — both adapters)

Both codex and opencode **hang forever in a non-TTY shell when stdin is left open**, even when the prompt is passed as a positional argument. The run bootstraps (~3-4s), then goes silent at the model step with zero further output — at any log level. This looks like a model/network failure; it is not.

- **codex:** pipe the brief in — `Get-Content brief.md -Raw | codex exec --skip-git-repo-check`. Piping closes stdin.
- **opencode:** redirect stdin from the null device. PowerShell has no native `< NUL`, so wrap in `cmd /c`:
  ```powershell
  cmd /c "opencode run --pure --model opencode/<model> \"<PROMPT>\" < NUL > out.log 2>&1"
  ```
  Verified working form (returned PONG, exit 0). Always background the call with a timeout and read the out file.

## Config: `executors.local.md`

Lives at `~/.claude/skills/orchestrate/executors.local.md`. Records this operator's toolbox so you don't re-probe or re-ask. Create it on first run (after discovery/asking), read it thereafter. Shape:

```markdown
---
executors:
  - name: codex
    mode: agentic          # agentic = edits files | advisory = returns text
    role: primary-code
    invoke: 'Get-Content brief.md -Raw | codex exec --skip-git-repo-check --sandbox workspace-write'  # run from inside the worktree
    isolate: worktree       # required for agentic — cd into the worktree first
    notes: gpt-5.5 backend; ~4s start; approval:never. Sandbox MUST be pinned — untrusted dirs default to read-only and the run fails with exit 0
  - name: codex-readonly
    mode: advisory
    role: second-opinion        # same model as codex, write-disabled
    invoke: 'Get-Content brief.md -Raw | codex exec --skip-git-repo-check --sandbox read-only'
    notes: fastest pipe to gpt-5.5-class review; returns text only; must be a separate invocation from the implementing run
  - name: gpt-5.5
    mode: advisory
    role: high-quality-text
    status: deferred            # paid OpenCode Zen model — fails with "Insufficient balance" until the workspace is funded
    invoke: 'cmd /c "opencode run --pure --model opencode/gpt-5.5 \"<PROMPT>\" < NUL > out.log 2>&1"'
    notes: 60s+ latency; cold-loads project each call; re-enable when funded
  - name: opencode-gpt55-serve
    mode: advisory
    role: high-quality-text-warm
    status: deferred            # same billing gate as gpt-5.5; inherits its routing verbatim — only transport differs
    invoke: 'opencode run --attach http://localhost:4096 --model opencode/gpt-5.5 --print-logs "<PROMPT>"'
    requires:
      - opencode-server-running
    notes: warm OpenCode server; avoids repeated cold boot; still model-latency bound
  - name: claude-haiku-native
    mode: advisory
    role: context-gathering     # not a CLI — the harness's own fast subagent tier
    invoke: 'Agent tool — subagent_type: Explore, model: haiku'
    notes: native Claude Code subagent, ~2s, no cold-load; costs Claude usage — swap to opencode-free when near the limit
  - name: opencode-free
    mode: advisory
    role: usage-limit-fallback
    invoke: 'cmd /c "opencode run --pure --model opencode/north-mini-code-free \"<PROMPT>\" < NUL > out.log 2>&1"'
    notes: $0 models, 24-90s; non-sensitive data only; fallback when the primary budget runs low
---

Free-text notes about this operator's preferences, limits, billing, etc.
```

### `last_verified`

Add `last_verified` to an executor record when you want the harness to skip a fresh smoke probe for 24 hours. Use an ISO-8601 UTC timestamp such as `2026-06-12T15:53:00Z`.

- Present and within 24h: `smoke-status` reports `FRESH`
- Present and older than 24h: `smoke-status` reports `STALE`
- Absent: `smoke-status` reports `UNVERIFIED`, which keeps the old behavior of probing every session

Example:

```markdown
  - name: codex
    mode: agentic
    last_verified: 2026-06-12T15:53:00Z
```

When discovery finds nothing, ask the operator for each executor's `name`, `mode`, and exact headless `invoke` string, then write this file.

## Known adapter: codex (agentic)

- **Binary:** `codex` (codex-cli). On the operator's box: `C:\Program Files\nodejs\codex.ps1`.
- **Invoke — feed the brief via STDIN from a file, never as a bare arg, and pin the sandbox:**
  ```powershell
  Get-Content brief.md -Raw | codex exec --skip-git-repo-check --sandbox workspace-write
  ```
  Two reasons. (1) Bare-arg form (`codex exec "prompt"`) **hangs** in a non-TTY shell: it prints `Reading additional input from stdin...` and blocks forever waiting on stdin that never closes — piping is what makes it headless. (2) Real briefs are multi-line markdown with backticks, `$`, quotes, and `[ ]`; inlining one as a double-quoted PowerShell arg interpolates `$…` and breaks on embedded quotes. Always write the brief to a file and pipe it in.
- **Latency:** ~4s to start producing output when healthy.
- **Pin the sandbox explicitly — the default is per-directory trust, not a stable global.** In an untrusted directory (e.g. a freshly created worktree), codex silently falls back to a **read-only sandbox**: it burns the full token cost producing content, fails every write with `patch rejected: writing is blocked by read-only sandbox`, and still **exits 0**. Always pass the mode you mean: `--sandbox workspace-write` for agentic runs, `--sandbox read-only` for advisory/review runs (this is the natural "codex as reviewer" invocation — same model, zero write risk). Never trust codex's exit code as a success signal; check that the brief's in-scope files were actually touched.
- **Sandbox reality:** when writable, runs `approval: never` + `sandbox: workspace-write` scoped to its **current working directory**. It *will* edit files with no confirmation, and the sandbox stops at file edits — it does **not** isolate the database (the worktree inherits the same `.env`/`DATABASE_URL`), the network, package installs, or the git remote. → **Always run it inside an isolated worktree (cd into it — see recipe)** *and* put hard Do-NOT constraints in the brief: no migrations/`db push`/seeds/DB writes, no `git push`/`commit`, no installs, no network. If codex exposes a tighter sandbox (`-c sandbox_permissions=...` / read-only modes), prefer it for review-style runs.
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
- **Use `--pure` for headless runs:** skips external plugins (and their network calls) — faster, fewer moving parts.
- **Model availability is a billing fact, not a config fact.** Paid gateway models (e.g. `opencode/gpt-5.5`, `opencode/claude-haiku-4-5`) fail with `Error: Insufficient balance` unless the OpenCode Zen workspace is funded — only the `*-free` models run on an unfunded workspace. Until funded: GPT-5.5-class advisory work routes through codex (read-only invocation or throwaway worktree, diff only), and fast cheap exploration routes through the harness's native subagents if available. Verify with the PONG probe before relying on any paid model.
- **Measured free-tier latencies** (single-run, cold-load dominated, ±a few s): `north-mini-code-free` ~24s, `deepseek-v4-flash-free` ~27s, `mimo-v2.5-free` ~32s, `nemotron-3-ultra-free` ~90s (avoid). Free models are the usage-limit fallback, not the default tier.

## Known adapter: opencode serve / warm advisory mode

Optional optimization for **repeated free-tier calls** when the per-call cold boot (instance + project + plugins + providers) is hurting iteration speed. This is not the primary advisory path — see the routing note above.

Start the server once:

```powershell
opencode serve --port 4096 --hostname 127.0.0.1
```

Then each call attaches instead of cold-booting:

```powershell
opencode run --attach http://localhost:4096 --model opencode/<model> --print-logs "<PROMPT>"
```

Notes:

- This avoids repeated MCP/plugin cold boot. **It does not remove model latency** — free-tier inference is the dominant cost (24-90s) regardless.
- Smoke-test the attached path with the PONG probe before relying on it.
- Bind to localhost (as above) by default. Do not expose the server publicly without explicit auth configuration.
- The stdin rule still applies to the `run` client side.

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
| bootstraps ~3s then silent forever, no output at any log level (opencode) | stdin left open in a non-TTY shell | re-invoke with the `cmd /c "... < NUL ..."` form (see stdin rule) |
| `Error: Insufficient balance` (opencode paid models) | OpenCode Zen workspace unfunded | don't retry; route to `*-free` models, codex, or solo; mark the executor `status: deferred` |
| `Error: File not found: <your prompt text>` (opencode) | `-f` greedily ate the trailing positional message | put the message before `-f`, or pass it via `-f` |
| `You've hit your usage limit` (codex) | quota exhausted | don't retry; ask operator / go solo; note reset time |
| `patch rejected: writing is blocked by read-only sandbox` (codex, exits 0) | untrusted dir defaulted to read-only sandbox | re-invoke with `--sandbox workspace-write`; never trust exit 0 — verify in-scope files were touched |
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
