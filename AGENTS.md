# Repository Guidelines

## Project Context & Structure

Only this guide exists; application scaffolding, tooling, tests, and Git history are absent. The planned personal website aggregates Korean corporate technical articles and industry insights, emailing a digest at 08:00 Asia/Seoul. Read originals through source links. Suppress empty digests and initial historical imports. Run collection and delivery server-side.

Proposed directories: `src/` for UI, collection, and delivery; `tests/` for tests and fixtures; `public/` for assets; `docs/` for decisions. Separate source-specific parsers from scheduling and email logic.

## Behavioral Guidelines

These rules favor caution over speed; apply judgment to trivial tasks.

### 1. Think Before Coding

- Inspect relevant code and configuration first. State assumptions explicitly.
- Surface competing interpretations and tradeoffs. Ask about unresolved ambiguity before implementing affected behavior.
- Propose simpler approaches and push back when warranted.

### 2. Simplicity First

- Implement only requested behavior. Avoid speculative features, configuration, and abstractions for single-use code.
- Handle realistic failures rather than impossible scenarios.
- If 200 lines could be 50, simplify.

### 3. Surgical Changes

- Make every changed line traceable to the request; preserve surrounding code, comments, formatting, and unrelated behavior.
- Match existing style. Refactor only where required.
- Remove imports, variables, and functions made unused by your changes. Mention unrelated dead code instead of deleting it.

### 4. Goal-Driven Execution

Define observable success criteria. For multi-step tasks, state a brief plan:

```text
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

For validation, test invalid inputs; for bugs, reproduce with a failing test; for refactors, check tests before and after. Iterate until relevant checks pass. Report results and any verification limits.

## Tooling, Style & Testing

No commands are configured. During scaffolding, select one package manager, formatter, linter, and test framework. Document verified install, development, build, lint, and test commands in `README.md`; commit the lockfile. Tool configuration defines indentation; follow language conventions for names.

Use saved RSS/HTML fixtures and mocked email. Cover duplicates, initial imports, missing dates, timezone boundaries, late discoveries, collection failures, and delivery retries. Coverage thresholds remain unset.

## Commits & Pull Requests

No historical convention exists. Use focused imperative subjects, e.g. `Add blog collector`. PRs explain behavior, validation, configuration changes, relevant issues, and UI screenshots when applicable.

## Security & Configuration

Keep credentials server-side and outside version control; provide placeholder configuration examples. Restrict settings and reading history to the owner account.
