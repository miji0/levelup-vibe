# Repository Guidelines

## Project Context & Structure

Only this guide exists; application scaffolding, tooling, and tests are absent. The planned personal website aggregates Korean corporate technical articles and industry insights, emailing a digest at 08:00 Asia/Seoul. Read originals through source links. Suppress empty digests and initial historical imports. Run collection and delivery server-side.

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

## Git Workflow

- Use Conventional Commits, such as `feat: add blog collector`, `fix: prevent duplicate emails`, and `docs: update repository guidelines`.
- Name branches `feature/<feature-name>` or `fix/<bug-name>`.
- For PRs that change application code, dependencies, or build, deployment, or CI configuration, relevant lint and tests must pass before PR creation. Configure missing checks first.
- For documentation-only PRs, run `git diff --check <base>...HEAD`, verify changed relative links and referenced paths, and review Markdown structure. Report results and any unavailable checks in the PR; application lint and tests are not required, and missing application tooling does not block PR creation.
- Never push directly to `main`; submit changes through a branch and PR.

PRs explain behavior, validation, configuration changes, relevant issues, and UI screenshots when applicable.

### Branch & Commit Approval

- Before creating a branch, propose 2–3 names with a recommendation and rationale. Wait for the user's selection or approval before creating it.
- Before committing, propose 2–3 commit messages based on the actual changes, with a recommendation and rationale. Wait for the user's selection or approval before committing.
- Use a branch name or commit message explicitly supplied by the user without asking again.
- If the user explicitly delegates candidate selection, generate candidates, choose the one closest to the existing Git style, briefly state the choice and reason, and proceed without another confirmation.
- Infer style primarily from recent branch names and commit history in this repository. When evidence is insufficient, use this guide's naming conventions.
- Explicit Git rules in this guide take precedence over historical style.
- Automatic approval of tool execution does not authorize automatic candidate selection; that requires explicit user delegation.

## Security & Configuration

Keep credentials server-side and outside version control; provide placeholder configuration examples. Restrict settings and reading history to the owner account.
