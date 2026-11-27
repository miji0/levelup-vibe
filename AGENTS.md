# Repository Guidelines

## Project Context & Structure

LevelUp is an owner-only personal website. The first implemented slice provides a Next.js shell, Python FastAPI Google login, and fixed seven-day PostgreSQL sessions. Collection and Gmail delivery remain planned; follow PRD.md and the current approval records in waterfall/08-검토 before implementing them.

Use `apps/web/` for TypeScript UI, `backend/src/levelup/` for Python API and services, `backend/tests/` for backend tests, `db/migrations/` for immutable SQL migrations, and `tests/e2e/` for browser flows. `waterfall/` contains design and review records.

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

Use Python 3.12 with uv and Node.js 24 with pnpm. README.md contains the executable setup and check commands; backend/pyproject.toml and apps/web/package.json define tools. Preserve both lockfiles. Run PostgreSQL tests with TEST_DATABASE_URL; skipped DB tests do not constitute a full pass. Tool configuration defines indentation; follow language conventions for names.

Use saved RSS/HTML fixtures and mocked email. Cover duplicates, initial imports, missing dates, timezone boundaries, late discoveries, collection failures, and delivery retries. Coverage thresholds remain unset.

## Screen Completion

- For every implemented or changed screen, complete this sequence before marking its design done: compare against the current Figma mockup → fix differences → verify dark/light at desktop 1280px and mobile 390px.
- Check layout, spacing, typography, icons, controls, and applicable interaction/error states. Record the Figma reference, screenshots, remaining differences, and verification results in the implementation handoff and UX review.
- Automated functional tests alone do not establish design completion. If Figma comparison or any required theme/viewport check is unavailable, report the screen as design-unverified. Current foundation screens still require Figma comparison.
- Compare Figma read-only; correct application code. Obtain explicit authorization before editing the mockup.

## Git Workflow

- Use Conventional Commits, such as `feat: add blog collector`, `fix: prevent duplicate emails`, and `docs: update repository guidelines`.
- Name branches `feature/<feature-name>` or `fix/<bug-name>`.
- For PRs that change application code, dependencies, or build, deployment, or CI configuration, relevant lint and tests must pass before PR creation. Configure missing checks first.
- For documentation-only PRs, run `git diff --check <base>...HEAD`, verify changed relative links and referenced paths, and review Markdown structure. Report results and any unavailable checks in the PR; application lint and tests are not required, and missing application tooling does not block PR creation.
- Never push directly to `main`; submit changes through a branch and PR.

PRs explain behavior, validation, configuration changes, relevant issues, and UI screenshots when applicable.

### Commit Milestones

- Group commits by the approved implementation plan's major flows: foundation/authentication, subscriptions/collection, reading lists, briefing/Gmail, reports/design completion, and release preparation. Keep supporting code, tests, and relevant records together.
- When a coherent milestone and its required checks are complete, notify the user that it is a commit point and summarize scope, results, and remaining limits. For UI changes, include the screen completion checks above; do not present design-unverified screens as finished.
- Propose commit messages under the approval rules below. A request for commit-point notifications is not authorization to commit or push.

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

## Subagent Coordination

When using subagents for service improvement, follow [.codex/README.md](.codex/README.md) for role definitions, file ownership, delegation, and verification handoffs. The main agent coordinates; use the custom roles in `.codex/agents/` for focused work and keep QA independent of implementation.
