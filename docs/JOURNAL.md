# Journal

Append-only. Newest entry at the bottom. One entry per working session: what was done, what was
decided, what was measured, what is open. Written at the end of the session, while the detail is
still available.

---

## 2026-08-26 — Specification, rules and roadmap established

**Context.** Power Accuracy parity Stages 1–5 are implemented; PRs #10, #11, #13 merged and
bench-verified. NS330 calibration with `NsPowerCalibrationV6.2.jar` in progress. A pool of 11
improvement proposals was raised and needed to be turned into an agreed plan rather than a chat
thread.

**Done.**
- `docs/VALIDATION_APP_SPEC.md` — the 11 proposals plus the open measurement items converted into
  numbered requirements M1–M6 (measurement) and U1–U8 (interface), each with rationale, acceptance
  criteria, risk class and config keys.
- `docs/DEVELOPMENT_RULES.md` — process, architecture and testing rules. Architecture principles
  (Open/Closed, config as single source of truth, 10–12 line functions, readability without
  explanation), ADR practice, agent rules and the UI prototype/screenshot method were carried over
  from the BelSystem Platform project, where they are already proven.
- `docs/ROADMAP.md` — P0 gates plus stages S0–S13, with the IQ track preempting the queue once the
  legacy `.class` files arrive.
- `CLAUDE.md`, `CHANGELOG.md`, this journal.

**Decided.**
- Release contract: `master` always deployable, one stage per PR, every stage bench-accepted and
  tagged before the next starts, behaviour changes behind flags defaulting to current behaviour.
- Risk classes R0/R1/R2 determine the acceptance procedure per requirement.
- Release Smoke Test defined: 14-point Power Accuracy (950/2150 MHz) + 25-point Flatness, under
  10 minutes, run after every merged stage.

**Environment change.** The app now runs from Andrei's laptop (`DESKTOP-A5D0TD9`, Windows 11 x64,
i5-13420H, 16 GB) connected to the lab network, not from NSLAB04-PC. NSLAB04-PC (Windows 7 Pro SP1
32-bit) remains a possible future deployment, so the Python 3.8 / win32 / no-installer
compatibility floor is retained for all code. Recorded as D17.

**Correction recorded.** The bench report's claim that `ext_gain_db = 0` is correct for all three
checks in validation mode is unsupported and contradicts D5. It was inferred from the config, never
decided. `iq_validation` runs at −3.5 dB.

**Decisions D6–D17 closed** the same day, all accepted as proposed: SSE with polling fallback for
live logs; overload warns and marks the point suspect; ETA structural first and statistics later;
analyzer screen via the CXA web UI iframe; insufficient licence warns and requires confirmation;
the speed work may reduce overhead only and may not reopen parity; Run page selections persist
server-side across restart; the IQ tolerance is set from the first comparison run; config stays
JSON; ADRs and this journal are adopted; minimal CI folded into S1; the Python 3.8 / win32
compatibility floor is retained indefinitely.

**Tracker.** `docs/progress.html` plus `docs/tracker.bat` added. It parses `ROADMAP.md`,
`VALIDATION_APP_SPEC.md` and `JOURNAL.md` live in the browser — there is no intermediate data file,
so it cannot go stale. Ownership recorded in `DEVELOPMENT_RULES.md` §10: CC runs the close-phase
routine at the end of every stage and updates the source documents; the HTML itself is not
regenerated.

**Open.** Awaiting the BelSystem tracker
materials and the `/close-phase` definition, to align the close-phase routine with what already
works there, and to decide whether stage hour estimates are wanted alongside the S/M/L weights.
P0 gates (calibration, front-panel
`:CORR:SA:GAIN` read, `pwr_calibration.csv` presence, short post-calibration run and its archived
baseline) block S9 onward. Legacy IQ `.class` files block the M-track.
