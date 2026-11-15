# ROADMAP — From local prototype to reliable open-source project

> Milestones are **plans**, not shipping promises. Status checked against the code on 2026-11-15.

## Phase 0 — Existing proof of concept

**State:** implemented and 7 tests passed in prior starter; limited assurance.

- [x] Python package and `promptmigrate` CLI entry point.
- [x] Workspace initialization and JSON drafts.
- [x] JSON before/after revision generation.
- [x] Linear `down_revision` chain and history replay.
- [x] Local SQLite per-environment state.
- [x] Upgrade, downgrade, current, check, get, diff.
- [x] Applied checksums and local drift checks.
- [x] Multi-config changes inside one SQLite transaction.
- [ ] Broad fault-injection and cross-platform verification.

## Phase 1 — Harden migration core (first implementation priority)

**Status:** in progress. Phase 1 is delivered in cycles. Cycle 1 is complete; cycle 2 is under way (v0 frozen, ADR-025; protocol v1, ADR-026; `restamp`, ADR-027; no-clobber revis
