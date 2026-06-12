---
name: Agent task
about: A bounded task intended for Claude/Codex/OpenCode execution
title: ""
labels: ["agent-task"]
assignees: ""
---

<!-- This issue must be self-contained: an agent with no chat history should be able to execute it. -->

## Objective

<!-- One or two sentences: exactly what to produce. -->

## Task class

<!-- Choose ONE from references/task-classes.md. Most restrictive matching class wins. -->

- [ ] mechanical-refactor
- [ ] scaffold
- [ ] test-generation
- [ ] bugfix-isolated
- [ ] docs-prose
- [ ] review-diff
- [ ] second-opinion
- [ ] cheap-exploration
- [ ] domain-sensitive
- [ ] db-sensitive
- [ ] security-sensitive
- [ ] money-sensitive
- [ ] architecture-decision

## Risk

- [ ] Low
- [ ] Medium
- [ ] High

## Preferred executor

<!-- Must be consistent with the task class per references/executor-capabilities.md. -->

- [ ] Claude only (brain)
- [ ] Codex agentic (isolated worktree)
- [ ] Codex read-only advisory
- [ ] Native Haiku subagent (exploration)
- [ ] Cheap/free advisory model (non-sensitive content only)

## Scope

Allowed paths:

```txt
(list exact files/globs the agent may create or edit)
```

Forbidden paths:

```txt
.env*
prisma/migrations/**
```

## Do NOT

- Do not modify unrelated files.
- Do not install dependencies.
- Do not run migrations, seeds, or db push.
- Do not commit or push.
- Do not use secrets, `.env*`, or live customer data.

## Contract

<!-- Signatures, types, I/O shapes, schemas the output must match. -->

## Acceptance criteria

- [ ] Diff touches only allowed paths.
- [ ] Existing safety rules remain intact.
- [ ] Verification commands below pass (re-run by the brain, not trusted from the agent's report).
- [ ] Brain review is required before integration.

## Verification commands

<!-- Concrete commands DERIVED from this repo (lockfile / package.json scripts / task runner). Never assumed. -->

```bash

```

## Agent brief

<!-- The complete handoff brief, self-contained, following templates/brief-template.md (including YAML frontmatter). -->
