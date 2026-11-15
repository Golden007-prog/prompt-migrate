# Changelog

All notable changes to PromptMigrate. Before 1.0, CLI and file contracts may change; such changes are marked **Contract**.

## Unreleased

- Added Programming Language :: Python :: 3.10, 3.12 and 3.13 classifiers to pyproject.toml to match the CI matrix (Python 3.10, 3.12, 3.13) and requires-python >=3.10.
- Clarified that applied v0 revisions are checked by raw bytes, while v1 revisions allow formatting-only changes and are checked by canonical parsed content; aligned the integrity test guidance.
- Added an SVG banner to the README showing PromptMigrate's ordered revision flow and verified local environment state.
- Corrected README and handoff documentation to include the shipped `plan` command and native Windows/macOS CI coverage; refreshed the documented test baseline and suite location. Brought `PRD.md`, `ROADMAP.md` and `LOW_LEVEL_DESIGN.md` up to date with the shipped `plan`, exit codes, JSON output, typed errors and strict loader. Moved all agent rules and the architecture overview from `CLAUDE.md` into `AGENTS.md`.
- Compacted `AGENTS.md` without dropping rules, and added a "Before every commit" rule: each commit updates `CHANGELOG.md` and `docs/ROADMAP.md`.

### Phase 1 cycle 2 — atomic revision writes and collision handling (PR 10)

- Added `project.write_new_file`: writes to a hidden `.tmp` file in the target directory, fsyncs it, then publishes
  with a hard link that never overwrites an existing file; where hard links are supported, nothing partial is left
  on failure. Filesystems without hard links fall back to an exclusive create (still no-clobber, but a crash
  mid-write can leave a partial file).
- `revision` generation now uses the atomic writer.
