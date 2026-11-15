# AGENTS.md — AI coding agent instructions for PromptMigrate

These rules are mandatory for every AI coding agent (Claude Code, Codex, Cursor, Copilot, Gemini, Hermes or any other) and every change. All rules live here. The tool-specific files `CLAUDE.md`, `CODEX.md`, `GEMINI.md`, `HERMES.md` and `.github/copilot-instructions.md` only point to this file (plus tool-specific orientation such as where plans are saved) and never add to or override a rule; to change a rule, edit this file.

## Mission

**PromptMigrate** is an open-source, Alembic-inspired CLI for **AI prompt and agent configuration migrations**: safe ordered revisions, environment state tracking, reversible changes, integrity/drift checks, and eventually policy-gated immutable release activation. **Do not redefine it as** a prompt editor, LLM workflow orchestrator, SaaS dashboard, observability tool or generic AI agent system.

## Repository map

- Code: `src/promptmigrate/` (ADR-022); tests: `tests/` (suite map in `docs/TESTING_STRATEGY.md`).
- Docs: start with `README.md` and `docs/HANDOFF.md`. Scope and status: `docs/ROADMAP.md`. Decisions: `docs/DECISIONS.md`. Open questions: `docs/OPEN_QUESTIONS.md`.

## Commands

Run from the repository root with Python ≥ 3.10. `pyproject.toml` sets `pythonpath = ["src"]` for pytest, so the editable install is optional for tests.

```bash
python -m pip install -e ".[dev]"                        # dev install: pytest, hypothesis, pytest-cov
python -m pytest -q                                      # whole suite (required before every commit)
python -m pytest tests/unit                              # one suite: unit, integration, contract, security
python -m pytest tests/test_core.py::PromptMigrateTests::test_state_drift_detected   # one test
python -m pytest -k restamp                              # tests matching a name
python -m pytest --cov=promptmigrate                     # coverage (local only, no percentage gate)
PYTHONPATH=src python -m unittest discover -s tests -v   # the original 7 unittest tests
PYTHONPATH=src python -m promptmigrate --project <dir> history   # CLI from source
docker build -f Dockerfile.ci --build-arg PYTHON_VERSION=3.12 -t promptmigrate-ci . && docker run --rm promptmigrate-ci   # Linux CI job, locally
```

- PowerShell: set `$env:PYTHONPATH = 'src'` instead of the `PYTHONPATH=src` prefix.
- WSL or no usable `python`: prefix commands with `uv run --extra dev`, e.g. `uv run --extra dev python -m pytest -q`.
- No linter, formatter or type checker is configured yet (issues #19, #20 and #37). Don't add one outside those issues.

## Architecture

Modules by layer (`docs/LOW_LEVEL_DESIGN.md` §1): `protocol/` (limits, strict JSON, `canonical`/`same`, name rules) → `secretscan.py` (secret rules, allowlist, redaction; no I/O) → `project.py` (workspace, drafts) → `revisions.py` (parse, graph, replay) and `store/` (environments, lock, SQLite) → `draftdiff.py`, `plan.py` (target resolution for `upgrade`/`downgrade`/`plan`), `apply.py` (`_verify`, row+ledger writes), `output.py` (`Result`, text/JSON, exit codes) → `commands/<verb>.py` → `cli.py`. `core.py` is the re-export facade.

State under `.promptmigrate/`: `drafts/<name>.json` (desired config); `versions/<12hex>_<slug>.json` (revisions, `changes: {name: {before, after}}` as full snapshots, `null` = absent); `environments.json` (declared envs, Git tracked; legacy projects adopted on first mutation); `states/<env>.sqlite3` (gitignored; `applied_revisions` ledger + `prompts`; missing = base, incomplete = error). Runtime state is not implemented.

Flow: `load_revisions()` enforces one linear chain and replays it from `{}`. `revision()` diffs drafts against the replayed source head, never an env DB. `upgrade`/`downgrade` run `BEGIN IMMEDIATE` → `_verify()` (ledger is an exact (id, checksum) prefix of history and `prompts` equals `replay(prefix)`, else drift) → `_apply_changes()` re-checks preconditions → rows and ledger commit together. Checksums: v0 files (no `format_version`) hash raw bytes; v1 files hash `"v1:" + sha256(canonical(item))` (ADR-026). `restamp` re-stamps only v0 ledger rows whose file changed in line endings alone (ADR-027). Downgrade deletes ledger rows; there is no audit log yet.

## Verified baseline (2026-11-16)

- Shipped: `init`, `revision`, `history`, `diff`, `current`, `upgrade`, `downgrade`, `plan`, `check`, `restamp`, `get`, `env add`, `env list`; `--output json`; exit codes 0–5.
- Windows 11 / Python 3.11.9: `python -m pytest -q` → `888 passed, 19 skipped, 33 warnings` (host symlink, case-insensitivity and POSIX-permission skips); unittest → `Ran 7 tests ... OK`. CI: Linux Docker plus native Windows and macOS, Python 3.10/3.12/3.13.
- Not shipped (never claim otherwise): `eval`, `export`, `promote`, `reconcile`, cloud adapters, SDK, Postgres, RBAC, signed revisions, real production activation.

## Process

- **Discussing:** restate the goal, find architecture gaps and differentiators, critique assumptions with alternatives and trade-offs, propose ADRs and milestones. Change no code until asked.
- **Implementing:** inspect the repo and state the test baseline; pick a small scope from `docs/IMPLEMENTATION_PLAN.md` or the active spec; follow TDD below; report **actual** test results only; keep shipped and planned behavior clearly separate.
- **Reviews** use: **Verified / Planned / Risks–contradictions (severity) / Proposed ADR updates / Next 3 steps with test acceptance criteria.**

## Hard rules

- Keep source history and applied env state distinct; fail closed on drift, corrupt history, unexpected state or partial writes.
- Config and ledger change in one local SQLite transaction, with no LLM/provider calls inside it. No remote writes disguised as transactional migration.
- Revisions are JSON only; no executable revision code.
- Never change the revision format or checksum semantics without an explicit format version. Applied revision integrity is versioned: for v0, any byte change (including whitespace or CRLF) blocks that env; for v1, formatting-only changes are allowed, but any change to the canonical parsed content blocks that env.
- `--env prod` is a local SQLite file; never claim real production deployment or production readiness from a green suite.
- No secrets, credentials or user data in revisions, logs or fixtures. Tests build token-shaped values at runtime from fragments (`"sk-" + "0" * 24`); never commit a token-shaped literal.
- Runtime stays stdlib-only; dev deps go in `[project.optional-dependencies] dev`. No AI-orchestration frameworks in core.
- `check` is an integrity check, not a prompt-behavior evaluation. Downgrade reverts configuration only, not external agent actions. Future activation = immutable release manifest + atomic pointer switch; never claim distributed ACID across remote APIs.
- No wholesale rewrites without regression coverage.

## Code structure

- `core.py` re-exports and defines nothing; keep its exported names and signatures stable.
- Call collaborators through their module (`project.read_drafts(...)`); in tests, patch the defining module, never `core` or `cli`.
- `cli.py` only parses and dispatches; each verb lives in `commands/<verb>.py` and returns an `output.Result`.
- Imports only point down the layer order above; `tests/unit/test_module_layout.py` enforces it.

## Code style

Match the surrounding code. These conventions are followed across `src/`:

- Every module starts with a one-line docstring saying what it owns; modules with annotations add `from __future__ import annotations`. Public functions get a one-line docstring and full type hints.
- Import within the package by module (`from . import project, revisions`) and call through it (`project.read_drafts(...)`). Import names directly only when a test needs to patch them, and say so in a comment.
- Private helpers use a leading underscore (`_verify`). A trailing underscore avoids shadowing a module name (`revisions_`).
- User-facing failures raise a typed error from `errors.py` (a `MigrationError` subclass, mapped to an exit code in `output.py`); warnings subclass `PromptMigrateWarning`. Never raise bare `ValueError`/`RuntimeError` for them, and never `print` outside `output.py` and `cli.py`.
- Double quotes and f-strings; keep lines within about 120 characters.
- Comments explain *why* (an invariant, a platform quirk, a test hook), not *what*. Keep them sparse.
- Tests: use the `project` fixture (`tests/conftest.py`) and the helpers in `tests/pmtest.py`, put each test in the suite folder it belongs to, and name it after the behavior it checks (`test_check_does_not_create_files`).

## Testing

- **Iron Law:** no production code without a watched-failing test. RED: write a minimal test and see it fail for the expected reason. GREEN: minimal code to pass. REFACTOR: keep it green, then run the **whole** suite. A test written after the code that passes at once proves nothing: delete the code and restart.
- Each PR starts with its full list of failing/characterization tests; earlier PRs' tests stay green. Known unfixed bugs are `@pytest.mark.xfail(strict=True)` with a reason naming the fixing PR.
- Tools: `pytest`, `hypothesis`, `pytest-cov`. The original 7 `unittest` tests in `tests/test_core.py` stay runnable unmodified. Coverage is measured locally with no percentage gate and never quoted as invented numbers.
- **Merge gate:** a PR merges only when all of these hold:
  1. Every CI job in `.github/workflows/ci.yml` is green: Linux (Docker), Windows and macOS on Python 3.10, 3.12 and 3.13. A red or skipped job blocks the merge, and flaky tests are fixed, not re-run until they pass.
  2. The branch is up to date with `main`, so CI ran against the code that will land.
  3. Every review thread is resolved. A maintainer reviews each outside contribution before merging it. GitHub requires no approval while there is a single maintainer, because GitHub does not let an author approve their own PR; raise the required approvals to 1 when a second maintainer joins.
  4. The PR description includes the test command, its real output and the OS/Python version it was run on. Claims about a platform are backed by that platform's CI job, never by a local run on another OS.

## Before every commit

- `CHANGELOG.md`: add an entry under **Unreleased**.
- `docs/ROADMAP.md`: tick finished items and update the status lines and "First next step".
- Behavior changes also update `docs/CLI_SPEC.md`, `docs/MIGRATION_PROTOCOL.md` and `docs/DECISIONS.md` in the same PR.

## Issues and pull requests

- One task per issue and one issue per PR. Link it in the PR body with `Closes #N`. If the work turns out to be two tasks, split the issue instead of widening the PR.
- Issues carry a `phase-N` label and milestone. Newcomers start from `good first issue`.
- `rfc` issues and Phase 2–3 issues need an accepted ADR in `docs/DECISIONS.md` before any implementation code.
- External contributors fork the repository and open a PR against `main`, filling in the PR template.

## Git

- `docs/superpowers/` and `graphify-out/` are local-only; never commit or link to them.
- `.gitattributes` forces LF; byte-exact fixtures need a `-text` rule.
- Branches: `<type>/<short-description>` (feat, fix, refactor, docs, test, chore, perf, build, ci). Changes reach `main` only through a GitHub pull request that passes the merge gate, merged with a merge commit; nobody pushes to `main` directly. AI agents don't push or open PRs unless asked.
- Conventional Commits, authored as the repository owner (repo-local git config). No AI attribution in commits or PRs: no AI `Co-Authored-By`, no "Generated by".
