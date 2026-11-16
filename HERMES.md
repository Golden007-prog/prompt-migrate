# HERMES.md (Hermes Agent) — PromptMigrate

**Read [`AGENTS.md`](AGENTS.md) in full before any change.** It holds every rule for this repository: mission, commands, architecture, hard rules, code style, testing, issue and Git workflow. This file only points there and never adds to or overrides it. If something here seems to conflict with `AGENTS.md`, `AGENTS.md` wins.

PromptMigrate is an Alembic-inspired, local-first, stdlib-only Python (≥ 3.10) CLI for declarative migrations of AI prompt and agent configuration. Design docs start at `docs/HANDOFF.md`.

Hermes loads only one project context file (`HERMES.md` before `AGENTS.md`), so `AGENTS.md` is **not** loaded automatically: open and read it yourself at the start of every session.

Tool-specific orientation: save implementation plans to `.hermes/plans/YYYY-MM-DD_HHMMSS-<slug>.md`, and run Python through `uv run --extra dev` (see the Commands section of `AGENTS.md`).
