# Changelog

One entry per tagged, bench-accepted release. Newest first.
Format: `## <tag> — <date> — <stage ID>: <title>` followed by what changed, what did not, and the
bench acceptance that closed it.

---

## Unreleased

- `docs/VALIDATION_APP_SPEC.md`, `docs/DEVELOPMENT_RULES.md`, `docs/ROADMAP.md` added as the
  project's source of truth for scope, process and ordering.
- `CLAUDE.md` added as the agent entry point; `docs/JOURNAL.md` started.
- `docs/progress.html` and `docs/tracker.bat` added — development tracker, parsed live from the
  source documents, launched from the repository.
- Decisions D6–D17 recorded and closed.

---

## Baseline — 2026-08-26

State at the point these documents were written:

- Power Accuracy parity Stages 1–5 implemented.
- PR #10 — menu-navigation fixes (`-channel-1`, `-adc-power-`) — merged.
- PR #11 — bench test summary doc — merged.
- PR #13 — per-check external gain, analyzer state-leakage fix — merged, bench-verified.
- IQ Validation blocked: no per-check external gain key yet, two known defects open.
- NS330 calibration with `NsPowerCalibrationV6.2.jar` in progress.
