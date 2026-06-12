# Decision: run-history storage stays flat-file (v0.3.5 / #13)

**Decision: keep `.orchestrate/runs/<runId>/` flat files. Do not adopt SQLite.** Borrow two cheap patterns from OpenCode's flat-file layer if/when the need appears: a `runs/index.json` for listing, and a lock-sentinel for concurrent writers.

## What OpenCode actually does

Researched at `sst/opencode` HEAD `4ddfa7c` (2026-06-12):

- **Two concurrent layers**: SQLite (`~/.local/share/opencode/opencode.db`; Windows `%LOCALAPPDATA%\opencode\opencode.db`) for structured data — sessions, messages, parts in a 6+ table Drizzle schema with cascade deletes — plus **flat JSON files** under `storage/**/*.json` for unstructured blobs (diffs, summaries, tool output).
- **It started flat-file and migrated to SQLite** in phases, driven by needs it actually had: cross-session queries (token-cost aggregation, time filtering), referential integrity, and a multi-process desktop+CLI architecture needing WAL-mode concurrency (`journal_mode=WAL`, `busy_timeout=5000`).
- Crash-safety on its flat-file layer is a per-key reentrant lock — no atomic rename-swap, so a crash mid-write can still corrupt a JSON file.
- No automatic pruning anywhere; sessions soft-delete via `time_archived`.

Key sources: `packages/core/src/database/database.ts` (WAL pragmas), `packages/core/src/session/sql.ts` (schema), `packages/opencode/src/storage/storage.ts` (flat layer + migrations), `specs/storage/remove-opencode-db.md`.

## Why the harness doesn't follow

Every force that pushed OpenCode to SQLite is absent here:

| OpenCode's reason | Harness reality |
|---|---|
| Cross-session aggregate queries | Query needs are "list runs, find by task" — directory listing answers both |
| 6-table relational schema, cascade deletes | Fixed 4-artifact schema per run: `report.json`, `diff.patch`, `logs.txt`, `touched-files.txt` |
| Multi-process desktop + CLI writers | Single writer per run (the dispatching brain); concurrent dispatches write to *different* run dirs by construction |
| Long-lived accumulating sessions | Runs are an audit trail, gitignored, disposable |

Flat files additionally keep properties the harness explicitly values: human-readable audit trail (the operator can open any artifact), zero schema/migration ownership, and full Windows portability (OpenCode has had Windows SQLite-path bugs, e.g. anomalyco#26207).

Python's stdlib `sqlite3` would not violate the zero-dependency rule, but it would buy schema versioning, WAL tuning, and migration code that solve no current problem.

## Borrowed patterns (deferred until needed)

1. **`runs/index.json`** — append one `{runId, task_id, executor, date, status}` line-record per run if "list runs" ever outgrows directory listing. Trigger: when runs number in the hundreds or a UI wants them.
2. **Lock sentinel + migration marker** — OpenCode's `storage/migration` plain-int counter and per-key write locks are the right shape if the v0.5 parallel runtime ever has two writers near the same path. Not needed while run dirs are disjoint by runId.

## Revisit when

- v0.5 parallel attempts introduce genuinely concurrent writers outside disjoint run dirs, or
- an operator-facing "run history" view needs sorting/filtering beyond what `ls` + `index.json` gives.

Until either happens, flat files win on auditability, portability, and code we don't have to own.
