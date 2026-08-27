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

---

## 2026-08-26 — S-M0: Power Accuracy per-point overhead

**Context.** Operator reported Power Accuracy running ~5.5x slower than the legacy Java tool.
Measured against the archived bench log `results/power_accuracy_freqs_20260826-153750.log`
(now `docs/bench/power_accuracy_freqs_20260826-153750.log`) — run ended cleanly ("Verdict: PASS",
normal `tx disable`/`sine off` cleanup) at point 18/432, operator-aborted, not crashed. Unit
calibration state at capture time was **pre-P0.1** (calibration JAR not yet run), so absolute
`Actual_dBm` values in that log are not representative of a calibrated unit — only relative timing
and point-to-point structure were used from it.

**Measured.** Per-point budget ≈13.4 s: 7 modulator commands ≈10.7 s (flat ~1.4 s/command
regardless of command content — `top`/`line` included — the modulator prompt returns well before
the fixed post-send wait elapses, but the transport always sleeps the full fixed interval instead
of watching for it), `:READ:CHP:CHP?` ≈2.0 s (correct — CHP-scoped, D11, untouched),
`:INIT:REST` ≈0.4 s (correct — untouched). Point 1 → point 16 `Measured:` line on the archived
50 MHz/16-point block: **219.141 s** measured directly from log timestamps, independently confirming
the operator's ~219 s figure. The "legacy tool ≈40 s" figure is operator-reported; it could not be
independently corroborated against any file in this repository and is recorded as such, not as a
verified number.

**Done — S-M0 (spec §M7, D18).**
- Item 1 (R1): DUT-side ADC power cross-check gated behind
  `power_accuracy.enable_adc_power_check`, default **off** (renamed from `read_adc_power`, which
  defaulted **on**). When off, the modulator never leaves `-line-` and `top`/`-adc-power`/
  `get-power`/`-modulator-config`/`line` are not sent. `ADC_Power_dBm` stays a CSV column, empty
  when the check is off. Code path not deleted.
- Item 2 (R1): `freq` sent only when it changes within a block — the DUT stays tuned across a
  power sweep at one frequency, so resending it every point was a pure round-trip with no effect.
  Analyzer-side `:FREQ:CENT` is unchanged (cheap, and the analyzer has no menu-navigation state to
  lose).
- Item 3 (R2): transport read on the telnet modulator path changed from a fixed post-command sleep
  to reading until the NS CLI prompt (`root@Modem ... *<N>`, N incrementing per accepted command)
  is seen, bounded by `dut_prompt_wait_timeout_s` (default 3.0 s) so a missing prompt degrades to a
  bounded wait instead of hanging. Mandatory companion:
  `power_accuracy.dut_settle_after_power_s` (default 0.5 s, the legacy `modSettings.txt` value) —
  an explicit dwell after `power <dbm>` and before `:INIT:REST`, since prompt-return only means the
  command was accepted, not that the RF output has settled. Serial modulator path unchanged
  (fixed sleep retained — only the telnet path had the overhead being fixed).
- New generic `LineSocket.read_until_regex()` in `transport.py` (no NS-specific pattern — the
  pattern is caller-supplied), with the NS prompt regex owned by `modulator.py`. Resolves the
  module-boundary question opened during planning (`DEVELOPMENT_RULES.md` §4: transport.py carries
  no instrument semantics) — see `docs/adr/0001-prompt-based-transport-read.md`.
- Offline tests added (synthetic fixtures only): prompt-regex matcher (recognises the real prompt
  shape, tolerates `\r\r\n` framing and a "Configuring device...Done." interlude, does not
  false-match on command echo) and the freq-change tracker (resends on change, suppresses on
  repeat, resends at a block boundary). Existing ADC cross-check test rewritten for the new
  default-off gate. All offline tests pass.
- Constraint held: `chp_average_count`, the `INIT:REST` wait, sweep-time AUTO and all CHP-scoped
  SCPI nodes untouched — D11 not reopened. Verified by grep that `flatness.py` and
  `iq_validation.py` have zero references to any new S-M0 identifier and zero diff on this branch.

**Decided.** D18 — items 1–2 (R1) and item 3 (R2) ship in one PR by operator decision, with a
stated per-item rollback: if bench acceptance criterion 3 (value parity) fails, item 3 alone
reverts; items 1–2 stay since neither changes what the instrument reports. Acceptance criterion 1
redefined during planning to measure from the `--- Point 1/N ---` log line to the last `Measured:`
line (excludes one-time setup), threshold under 60 s, baseline 219.1 s; setup-phase time reported
separately with no threshold (criterion 1b).

**Open.** Bench acceptance (spec §M7, redefined criteria 1–6) not yet run against real hardware —
pending lab network access. `docs/adr/0001-prompt-based-transport-read.md` and the bench-log
archive under `docs/bench/` are part of this same entry's close-phase routine.

---

## 2026-08-27 — S-M0: pre-merge correction on PR #16

**Found.** As first implemented, `use_prompt_read` (item 3) was decided at `TelnetModulator` class
level, shared by all three checks through one modulator instance — Flatness and IQ Validation would
have silently inherited the new timing despite zero diff in their own files. Flagged as a
`DEVELOPMENT_RULES.md` §4.2 blast-radius violation (a check's blast radius stays inside that check)
and a §2.4 violation (a new key's default must reproduce today's behaviour for a check that has not
explicitly opted in).

**Fixed.** `use_prompt_read` is now a per-check config key, resolved by `base.resolve_use_prompt_read()`
the same way `ext_gain_db` is resolved (D5): the check's own section wins, absent key falls back to
`False`. `TelnetModulator` supports both the fixed-sleep and prompt-based reads but decides neither
itself — `session.py` calls `mod.set_prompt_mode(...)` once per run, generically, right after
`connect()`. `flatness.py` and `iq_validation.py` needed zero changes (grep-verified, zero diff).
Defaults: `power_accuracy.use_prompt_read=true`, `flatness.use_prompt_read=false`,
`iq_validation.use_prompt_read=false`. `use_prompt_read` added to the run log params snapshot for
every check. `docs/adr/0001-prompt-based-transport-read.md` annotated (not rewritten) with this
correction.

**Also fixed.** Acceptance criterion 3 rewritten from "compare against the archived pre-P0.1 log"
to a same-session A/B on the same unit (`DEVELOPMENT_RULES.md` §7.3, compare like with like — the
archived log's calibration state does not match whatever the unit is at merge time). Criteria 7
(settle-time distinguishing test, run B at `dut_settle_after_power_s=0.5` vs `1.5` — §7.4, a
null-valued test proves nothing) and 8 (Flatness regression guard) added.

**Recorded, not acted on.** Item 2 (`freq` sent only on change) assumes `power <dbm>` does not
disturb the DUT's tuned frequency. Untested assumption — criterion 3's A/B is also the check for
this.

**Rebase.** PR #15 (S0) is still unmerged at the time of this correction — the rebase of this
branch onto updated `master` is pending the operator merging #15 first; noted here so it is not
forgotten once that happens.

**Status.** `ROADMAP.md` S-M0 row set to `in-review` (not `done`), tag column stays `—`. No
annotated tag, no `CHANGELOG.md` entry — §2.6 is deferred, not waived.

**Standing warning, recorded verbatim as instructed:**

> S-M0 merged without bench acceptance; acceptance criteria 1-8 outstanding.
> Bench access unavailable at merge time. Power Accuracy results are not to be
> trusted for production until the A/B in criterion 3 has been run.
> Flatness and IQ Validation are unaffected by default (use_prompt_read=false).
