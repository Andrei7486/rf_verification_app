# RF Verification App — Improvement Specification

Status: **Draft v1.0** — pending operator sign-off
Owner: Andrei (BelSystem / AYECKA)
Repo: `Andrei7486/rf_verification_app`
Last updated: 2026-08-26

This document is the **source of truth** for what will be changed and what "done" means for each
change. It does not describe the current implementation — for that see
`POWER_ACCURACY_HANDOFF.md` and `POWER_ACCURACY_SESSION_HANDOFF_20260826.md`.

Companion documents:
- `docs/DEVELOPMENT_RULES.md` — how code is written, reviewed, released and rolled back.
- `docs/ROADMAP.md` — the order of work, gates and current position.

---

## 1. Purpose and scope

The app replaces a set of fragmented Tera Term macros and legacy Java tools with a single Flask
web application that runs Flatness, Power Accuracy and IQ Validation against NovelSat modulators
and a Keysight CXA N9000B.

Scope of this specification: the improvement pool raised on 2026-08-26 (11 items), plus the
measurement-correctness items still open from the Power Accuracy parity work.

Out of scope, explicitly:
- Re-litigating Decisions 1–5 (closed, see §7).
- Porting legacy *numbers*. We port the legacy *method*. This remains binding.
- New check types beyond Flatness / Power Accuracy / IQ Validation.
- Anything that cannot run on the compatibility floor — portable Python 3.8.10 win32 on Windows 7
  32-bit — even though development currently runs on a Windows 11 x64 laptop
  (see `DEVELOPMENT_RULES.md` §2).
- Multi-user features. One operator, one instrument set, one run at a time.

---

## 2. The release contract (non-negotiable)

This is the operator's primary requirement and it constrains every item below.

1. **`master` is always deployable.** At no point does a half-finished feature live on `master`.
2. **One stage = one PR = one usable increment.** After every merged stage the operator can run
   all three checks on the bench and continue production work.
3. **No stage may degrade an existing check.** If a stage cannot be finished safely, it is
   reverted, not left partially applied.
4. **Behaviour changes ship behind a config flag whose default reproduces today's behaviour**,
   unless the change is a straight bug fix agreed in advance.
5. **An absent config key reproduces the previously configured value — never `0`, never a silent
   new default.** (This is the lesson from PR #13.)
6. **Every stage is bench-accepted before it is tagged.** Code review alone does not close a stage.
7. **Rollback is always available**: previous tag on the laptop, previous deployed folder on the
   bench PC.
8. **Open/Closed.** Every requirement below is implemented as a new module plus a config entry.
   A requirement that can only be implemented by adding a branch to an existing chain has been
   specified wrongly — stop and re-specify. See `DEVELOPMENT_RULES.md` §3.1.

---

## 3. Risk classification

Every requirement carries a risk class. The class determines the acceptance procedure.

| Class | Meaning | Acceptance required |
|---|---|---|
| **R0** | UI / server only. No SCPI or DUT command is added, removed, reordered or retimed. | Release smoke test (§4) |
| **R1** | Touches instrument or DUT sequencing, but measured values must be unchanged. | Smoke test + read-back verification + comparison against stored baseline run |
| **R2** | Intentionally changes measured values or timing. | A/B run against a stored baseline, both logs archived, deltas explained point by point |

An R0 change that turns out to touch the measurement path is a specification error — stop, reclassify,
re-plan. Do not proceed "since it is already written".

---

## 4. Release smoke test (RST)

Run after **every** merged stage, before tagging. Target duration under 10 minutes.

1. Power Accuracy, NS330, **950 MHz and 2150 MHz only, 7 power steps** = 14 points.
2. Flatness, 25 points.
3. Checks on the resulting logs:
   - zero `command not found` on any DUT command;
   - `:CORR:SA:GAIN?` read-back matches the intended per-check value within 0.01 dB for each check;
   - the "Parameters used for this run" block is present and lists **every** config key in use;
   - deviations agree with the previous baseline run within 0.1 dB, except where the stage
     intentionally changed them (R2).
4. UI: start a run, observe status change, observe live log, navigate Run → Settings → Run and
   confirm the selection is intact, let the run finish, confirm results are complete.

The RST is the regression net for the whole project. It is deliberately short so that there is no
excuse to skip it.

---

## 5. Requirements

### 5.1 Measurement correctness (track M)

---

**M1 — IQ Validation external gain key**
Risk: **R1** · Blocks: M2 · Source: handoff §4

IQ Validation currently falls back to the global `analyzer.ext_gain_db`. If that is `0`, every IQ
measurement is off by 3.5 dB, including the diagnostics used to judge the two-peak defect.

- Add config key `iq_validation.ext_gain_db = -3.5`.
- Value must match the external gain used when the IQ reference calibration was taken.
- Pushed unconditionally after `preset()` via `apply_check_ext_gain()`, read back, WARNING if the
  delta exceeds 0.01 dB — identical mechanism to PR #13.
- Ships in the same PR as M2 so that it is bench-checked there.

**Acceptance:** IQ run log shows outgoing `:CORR:SA:GAIN -3.5` and a matching read-back.
**Until M1 is merged, IQ Validation must not be run.**

---

**M2 — IQ Validation parity with the legacy Java program**
Risk: **R2** · Blocked by: operator supplying the legacy `.class` files · Source: proposals §1, handoff §4

Two confirmed defects:
- (a) the modulator setup produces two large peaks instead of single-sideband. The fix is to be
  **derived from the legacy IQ calibration `.class` files**, not guessed from the current code.
- (b) delta-marker offset-vs-absolute bug — use `marker_delta_y_at_offset()` with
  `:CALC:MARK:MODE DELT`.

Additional parity items from the proposal pool:

| # | Requirement |
|---|---|
| M2.1 | Restore `CENTER = DUT frequency − 1 MHz` before the Image measurement |
| M2.2 | Guard on weak Main CW — abort/warn below `−20 dBm` (threshold configurable) |
| M2.3 | MAX HOLD not used in IQ Validation by default |
| M2.4 | DUT command sequence aligned to legacy (derived from `.class` files) |
| M2.5 | Automatic reference level = `Main CW + 1 dB` |
| M2.6 | Keep the expected-frequency check on Main CW |
| M2.7 | Separate limits for LOFT and Image |
| M2.8 | Phase Correction and LOFT Correction stored in results and CSV |
| M2.9 | VCO / VCO Band ported **only after** command support is confirmed per model |

Architecture must stay as-is: `transport.py` (link only), `modulator.py` (unit), `analyzer.py`
(SCPI), `iq_validation.py` (sequence and verdict).

**Acceptance:** spectrum shows the expected single-sideband result; LOFT and Image values agree
with the legacy program on the same unit within an agreed tolerance (tolerance to be set from the
first comparison run, D13).

---

**M3 — First-point-of-block settling**
Risk: **R2** · Source: handoff §4

First point of each frequency block diverges from the rest of its block; absent on IF, appears
from ~1900 MHz and grows (−16.3 dB vs ~+5.3 dB at 2150 MHz). Cause is retune settling — either
the modulator not yet at level or the CXA not finished averaging after `INIT:REST`.

- Fix: one discarded dummy read, or extra dwell, before the first read of each block.
- Configurable: `power_accuracy.block_first_point_dummy_read = true`,
  `power_accuracy.block_settle_ms`.
- Cost in run time must be measured and recorded (interacts with M4).

**Acceptance:** at 2150 MHz the first point of the block sits within the spread of the rest of the
block. Note: this artifact is measured *within* a block, so calibration does not cancel it —
it must be verified after calibration, not assumed fixed by it.

---

**M4 — Power Accuracy run time**
Risk: **R2** · Source: proposals §2

Power Accuracy is perceived as too slow. Work is investigative first:

1. Instrument the run — per-point and per-phase timing written to the log; total run time reported.
2. Identify what dominates: sweep time, `chp_average_count`, `INIT:REST` wait, DUT settling,
   per-point retries.
3. Propose reductions **with measured effect on the reading**, not by intuition.

**Constraint — this requirement can collide with parity.** Averaging count and the `INIT:REST`
computed wait came from the legacy method and are covered by the parity plan. Any proposal to
change them reopens that plan and requires an explicit decision (D11). Reductions that do not
change what the instrument reports (removing redundant queries, avoiding repeated setup between
points, not re-presetting per point) are preferred and are not parity changes.

**Acceptance:** documented before/after total run time for the same 175-point matrix, plus a
point-by-point deviation comparison showing agreement within 0.1 dB with the pre-optimisation
baseline. Applies to Power Accuracy only, not IQ Validation.

---

**M5 — Analyzer warnings surfaced in the UI**
Risk: **R1** (detection) / **R2** (retry behaviour) · Source: proposals §7

The app must detect and surface analyzer conditions: `Input Overload`, `ADC Overrange`, and other
errors/warnings.

- Poll `:SYST:ERR?` (and the appropriate status/condition registers) after each measured point.
- **Warning rules are config entries, not code branches.** Each rule: match pattern → severity →
  action. Adding a newly discovered analyzer warning must require one config line and no code
  change (`DEVELOPMENT_RULES.md` §3.1).
- Display immediately in the UI, visually distinct from normal log lines.
- Mark the affected result point as **suspect** in the results table and in the CSV.
- Optional automatic re-measurement of a suspect point after adjusting analyzer settings —
  **off by default**, separate sub-stage, R2. See D7.

**Acceptance:** an intentionally induced overload appears in the UI within one point, the point is
flagged suspect, and the run continues without aborting.

---

**M6 — Config integrity and drift**
Risk: **R0** · Source: handoff §4

`config/config.json` on the bench diverges from the repo between sessions, and this has already
produced one unexplained 5–6 dB level difference.

- The run log "Parameters used for this run" block must cover **every** key actually used,
  including all keys added in Stages 3–5 and PR #13.
- At run start, log a diff of the effective config against the repo defaults; log any key present
  in defaults but missing on the bench, and any unknown key.
- Config version stamp written into the log and into result CSV headers.

**Acceptance:** deliberately remove one key on the bench — the run log names it explicitly and the
app uses the documented default rather than `0`.

---

**M7 — Power Accuracy per-point overhead**
Risk: **R1 + R2 combined in one PR by operator decision (D18)** · Source: bench log
`power_accuracy_freqs_20260826-153750.log` (archived, `docs/bench/`)

Power Accuracy is significantly slower than the legacy Java tool for identical results. One
frequency, 0..−30 dBm step 2 (16 points): the operator reports the legacy tool at ~40 s (not
independently bench-verified against a file in this repository — recorded as reported, not
measured); this app measured, from the same archived baseline run, **219.1 s** (Point 1 start to
the 16th `Measured:` line) for the same 16 points.

Measured per-point budget from the baseline log — most modulator commands cost a flat **~1.4 s**
(n=20, min 1.403 s) regardless of the command, including `top` and `line`; the NS CLI prompt
(`root@Modem -<menu>- *<N>`) is present in the response but the transport does not wait for it, it
sleeps a fixed interval instead. `:READ:CHP:CHP?` (~2.0 s, sweep 0.1874 × average 10) and
`:INIT:REST` (~0.4 s) are correct and untouched — see the constraint below.

Legacy per point (from `POWER_ACCURACY_HANDOFF.md`): `power <n>` only, then `INIT:REST` /
computed sleep / read.

Three items, one PR:

- **Item 1 (R1) — ADC cross-check behind a flag.** New key
  `power_accuracy.enable_adc_power_check`, default **`false`**. When off, `-adc-power` /
  `get-power` / `top` / `-modulator-config` / `line` are never sent — the modulator never leaves
  `-line-` in the first place, so there is nothing to navigate back from. `ADC_Power_dBm` stays a
  CSV/results column, empty when the flag is off. The ADC code path is not deleted, only gated.
  This key **replaces** the previous `power_accuracy.read_adc_power` (default `true`) introduced
  alongside PR #13's Stage 5 — same purpose, renamed and default-flipped; see the D18 note below and
  the S-M0 ADR.
- **Item 2 (R1) — `freq` sent only on change.** The last frequency actually pushed to the
  modulator is tracked; within a frequency block it is not resent. `:FREQ:CENT` on the analyzer is
  unchanged (already cheap, ~2 ms).
- **Item 3 (R2) — prompt-based transport read, per check.** `transport.py` gains a generic,
  instrument-agnostic `read_until_regex()` (the caller supplies the pattern); `modulator.py` — the
  only place that knows the NS CLI's prompt shape, per the module boundary in
  `DEVELOPMENT_RULES.md` §4 — uses it to return as soon as the prompt is seen instead of always
  waiting a fixed delay. **Gated per check** by new key `use_prompt_read`, resolved from the
  check's own config section exactly as `ext_gain_db` is (D5) — `power_accuracy.use_prompt_read`
  default `true`, `flatness.use_prompt_read` and `iq_validation.use_prompt_read` default `false`.
  `TelnetModulator` supports both modes; the mode is set once per check (`set_prompt_mode()`,
  called by `session.py` right after `connect()`) and `TelnetModulator` itself never decides it
  from config. New key `modulator.dut_prompt_wait_timeout_s`, default `3.0` (seconds) — bounds the
  read so a missing prompt degrades to a bounded wait rather than hanging, never blocking
  indefinitely. **Mandatory companion:** new key `power_accuracy.dut_settle_after_power_s`, default
  `0.5` (seconds) — an explicit dwell after `power <dbm>`, before `:INIT:REST`. Rationale: today
  ~9 s elapse between `power` and the read purely as a side effect of the per-command overhead this
  item removes; 0.5 s is the value from the legacy `modSettings.txt`, which produces correct
  readings. Without this the modulator may not have settled and levels read low. Criterion 7 below
  exists specifically to check whether 0.5 s actually holds up once item 3's timing is live, rather
  than being carried over unverified.

**Correction (pre-merge review of PR #16).** As first implemented, the prompt-based read was a
class-level override in `TelnetModulator`, shared by all three checks through one modulator
instance — Flatness and IQ Validation would have silently inherited the new timing despite zero
diff in their own files (`DEVELOPMENT_RULES.md` §4.2: a check's blast radius stays inside that
check). Fixed by making `use_prompt_read` a per-check config key, resolved the same way as
`ext_gain_db`, with `TelnetModulator` supporting both modes but deciding neither — `session.py`
sets the mode once per run, generically, from the active check's own key. Flatness and IQ
Validation remain byte-identical to `master` (grep-verified, see the S-M0 PR).

**Constraint.** Does not change `chp_average_count`, the `INIT:REST` computed wait, sweep time
AUTO, or any CHP-scoped node — D11 is not reopened.

**Assumption to be confirmed, not yet tested (record only, per operator instruction — see the
journal).** Item 2 (`freq` sent only on change) assumes `power <dbm>` does not itself disturb the
DUT's tuned frequency. Untested; criterion 3 below is also the check for this.

**Acceptance (redefined by the operator during planning — see D18; criterion 3 rewritten and 7–8
added in the pre-merge correction, `DEVELOPMENT_RULES.md` §7.3/§7.4):**
1. Time from the `--- Point 1/N ---` log line to the last `Measured:` line, single run, 50 MHz
   only, 0..−30 dBm step 2 (16 points): **under 60 s**. Baseline from the archived log: **219.1 s**
   (timing structure only — see criterion 3 for why this baseline is not used for levels).
2. Setup-phase time (everything before `--- Point 1/N ---`) reported separately, before/after —
   no threshold.
3. **Same-session A/B on the same unit**, 50 MHz, 0..−30 dBm step 2 (16 points) — not a comparison
   against the archived baseline log, which was captured pre-P0.1 on an uncalibrated unit
   (`DEVELOPMENT_RULES.md` §7.3, compare like with like):
   - Run A: `enable_adc_power_check=true`, `use_prompt_read=false` (today's `master` behaviour).
   - Run B: `enable_adc_power_check=false`, `use_prompt_read=true` (this stage).
   - Every `Actual_dBm` in run B within 0.1 dB of run A, point by point.
   - The archived log (`docs/bench/power_accuracy_freqs_20260826-153750.log`) is used for **timing
     structure only** (criterion 1's baseline), never for absolute levels.
4. Log shows no `-adc-power` / `get-power` / `top` / `-modulator-config` / `line` between points.
5. Log shows `MOD freq` once for the block, not 16 times.
6. `:CORR:SA:GAIN?` read-back still present and matching (per PR #13's mechanism, untouched).
7. **Settle-time distinguishing test** (`DEVELOPMENT_RULES.md` §7.4 — a comparison where both sides
   use the same value proves nothing). Repeat run B with `dut_settle_after_power_s = 1.5`. If it
   agrees with run B at `0.5` within 0.1 dB, `0.5` s is sufficient. If they diverge, `0.5` s is too
   short and the default must be raised.
8. **Flatness regression guard.** Run Flatness, 25 points. Confirm the inter-command interval on
   the modulator is still ~1.4 s — Flatness must be unaffected by this stage's default
   (`flatness.use_prompt_read = false`).

If acceptance criterion 3 fails, **Item 3 is reverted on its own** — Items 1 and 2 are R1 and stay,
since they do not change what the instrument reports.

---

### 5.2 User interface and workflow (track U)

---

**U1 — Run page state persistence**
Risk: **R0** · Source: proposals §3

Navigating Run → Settings → Run must not reset the selection. Preserve: selected check, unit model,
mode, and all other entered/selected settings. Scope (browser session vs server-side across
restart) — see D12.

**Acceptance:** select a non-default combination, go to Settings, return — everything intact,
including free-text fields.

---

**U2 — Immediate response after Start Run**
Risk: **R0** · Source: proposals §5

Today the test is already running in the terminal while the UI still looks idle.

- Status changes on click, before any instrument I/O.
- Visible running indicator.
- Start button disabled/locked while a run is active; a second run cannot be launched.
- The first log lines appear immediately.

**Acceptance:** status and indicator change within 200 ms of the click; a second click while
running has no effect and says so.

---

**U3 — Real-time logs**
Risk: **R0** · Source: proposals §6

Commands sent to the DUT and to the analyzer, and their responses, must appear in the UI as they
happen — not batched, not after part of the check completes. Transport mechanism see D6.

**Acceptance:** a line appears in the UI within ~1 s of being written to the console, throughout a
full 175-point run.

The buffer is not bounded. On the laptop this is fine; it is recorded in §9 as a deferred
portability item to be handled in the refactor pass before any Windows 7 deployment.

---

**U4 — Separate scrollable results area**
Risk: **R0** · Source: proposals §10

Results must not extend the page indefinitely.

- Dedicated block with its own vertical scrollbar containing: frequency, set power, measured power,
  PASS/FAIL, and any check-specific parameters.
- Header/controls stay visible while results scroll.
- Existing colour coding kept.
- The existing top summary block listing failed frequencies is kept.

**Acceptance:** at 175 points the page height is unchanged from the empty state; the top of the
interface remains on screen.

---

**U5 — Progress and remaining time**
Risk: **R0** · Source: proposals §9

For every check — Calibration, IQ Validation, Power Accuracy, Flatness and future ones — show:
current progress, elapsed time, estimated time remaining, points done and points left.

Estimate derived from the test structure first; refined from historical run statistics later (D8).

**Acceptance:** on a 175-point run the ETA is within ±20 % after the first 10 points.

---

**U6 — Automatic unit discovery and inventory**
Risk: **R1** · Source: proposals §11

On connection the app queries the unit automatically, without a separate button, and displays:
model, serial number, software version, hardware version, installed licence.

It must also check whether the licence is sufficient for the selected check and warn the operator
if it is not, since results may be invalid otherwise.

R1 because it adds DUT commands at connection time — those commands must not disturb a subsequent
check's setup. Licence semantics and the correct query per model are open (D10).

**Model profiles.** This requirement introduces the model profile table — the single place where
per-model differences live: which query returns the licence, which licence each check needs, VCO
band support (M2.9), attenuator compensation, and any other model-dependent value currently
expressed as a branch. Existing model-dependent logic is migrated into it as it is touched, not in
a bulk refactor.

**Acceptance:** connect an NS330 — inventory appears without operator action; select a check the
licence does not cover — a warning appears before the run can start.

---

**U7 — Embedded analyzer screen**
Risk: **R0** · Priority: optional · Source: proposals §8

An area in the UI showing the analyzer's ready-made remote screen, as it is opened on the laptop
today. **Not** trace data fetched and re-rendered by the app.

- Must not measurably slow the test. Off by default, operator-toggled.
- Source mechanism see D9.

**Acceptance:** with the panel open, total run time for the 14-point RST increases by less than 2 %.

---

**U8 — UI restructure**
Risk: **R0** · Source: proposals §4

The current menu was built quickly and needs rework. **The concrete new design is deliberately not
specified here** — it will be agreed separately, then added to this document as U8.1…U8.n before
any code is written.

Constraints:
- Done **after** U1–U5, so that it is applied to finished behaviour rather than being redone.
- **The existing UI is the baseline.** There is no prototype. Each change is specified as a delta
  against the current screen — what changes and what stays — and reviewed by before/after
  screenshots at a fixed viewport (`DEVELOPMENT_RULES.md` §11).
- The restructure ships in slices, each independently deployable. A half-migrated menu never
  reaches `master`.

---

## 6. Non-goals

- Chasing anomalies that are recorded but not on the plan (e.g. the repeatable intra-block IF shape
  that dips at `Set_dBm` −5/−10). Flagged, not chased.
- Explaining historical deviations measured on an uncalibrated unit.
- Replacing the legacy calibration JAR. The app validates; `NsPowerCalibrationV6.2.jar` calibrates.

---

## 7. Decision log

Decisions 1–5 are closed and recorded in `POWER_ACCURACY_HANDOFF.md`. Summary, binding:

| # | Decision |
|---|---|
| D1 | Legacy `exaSettings` / `modSettings` numbers are **not** ported |
| D2 | Only `chp_average_count = 10` is taken from the legacy settings |
| D3 | Retry on transport/SCPI exception only, small capped count. No value-sanity retry |
| D4 | Output Level Mode set explicitly in `modulator_setup()`, default ON — determinism over literal parity |
| D5 | External gain is a per-check override; the global `apply_ext_gain` flag is not flipped |

**Correction to be applied:** the bench-report claim that `ext_gain_db = 0` is correct for all three
checks in validation mode is **unsupported and contradicts D5**. It was inferred from the config,
never decided. `iq_validation` runs at −3.5 dB. Recorded here so it is not repeated.

### Decisions D6–D17 — closed 2026-08-26

All accepted as proposed. Binding from now on; reopening one is itself a decision.

<!-- DECISIONS:BEGIN -->

| # | Question | Proposal | Status |
|---|---|---|---|
| D6 | Live-log transport: SSE vs polling? | SSE from Flask 2.3.3 with a polling fallback; no new dependencies | accepted |
| D7 | Response to overload: warn only, mark suspect, or auto-retry the point? | Warn + mark suspect in stage one; auto-retry as a later opt-in flag | accepted |
| D8 | ETA source: structural estimate or historical statistics? | Structural first, statistics added once ≥5 runs are archived | accepted |
| D9 | Embedded screen source: CXA web UI iframe (`http://192.168.0.5`) or SCPI screenshot? | iframe, manual toggle, forced off during measurement | accepted |
| D10 | Which query returns the licence, and does an insufficient licence warn or block? | Warn and require explicit confirmation; blocking only if the check cannot produce valid results at all | accepted |
| D11 | May M4 (speed) change `chp_average_count` or the `INIT:REST` wait, reopening parity? | No by default. Reduce only non-measuring overhead; any parity change becomes its own decision with an A/B run | accepted |
| D12 | U1 persistence: browser session only, or server-side across app restart? | Server-side last-used settings, restored on load, overridable | accepted |
| D13 | M2 acceptance tolerance vs the legacy IQ program | Set from the first side-by-side comparison run, then frozen here | accepted |
| D14 | Config format: keep `config.json`, or move to YAML as on BelSystem? | Keep JSON. YAML would add PyYAML to a dependency set we are deliberately keeping minimal, and the Open/Closed benefit comes from the registry pattern, not from the file format. Revisit only if config gains comments or multi-document structure | accepted |
| D15 | Adopt ADRs (`docs/adr/`) and an append-only `docs/JOURNAL.md`, as on BelSystem? | Yes. Decisions D1–D5 have already been re-derived from chat twice; that is exactly what ADRs prevent. Low cost, high value | accepted |
| D16 | Minimal CI (GitHub Actions: ruff + offline unit tests on push)? | Yes, once S1 lands and there is offline-testable logic to run. No Docker, no browser tests — the bench is the integration suite | accepted |
| D17 | Does the laptop become the permanent runtime, or is NSLAB04-PC still the target? | Assume the laptop indefinitely, keep the 3.8/win32 floor. Dropping the floor is a one-way door — it costs nothing to hold and would cost a rewrite to restore | accepted |
| D18 | S-M0 (per-point overhead): ship R1 (items 1–2) and R2 (item 3) in one PR, or split? | One PR, by operator decision, with a stated per-item rollback split — if acceptance criterion 3 (value parity) fails, item 3 alone reverts; items 1–2 stay, since neither changes what the instrument reports | accepted |

<!-- DECISIONS:END -->

---

## 8. Prerequisites currently blocking work

| Item | Owner | Blocks |
|---|---|---|
| NS330 calibration with `NsPowerCalibrationV6.2.jar` | Operator | M3, M4 baselines |
| Read `:CORR:SA:GAIN` off the CXA front panel after the JAR finishes | Operator | interpretation of all post-calibration runs |
| Confirm `pwr_calibration.csv` landed in `/data/var` on the unit | Operator | M3, M4 baselines |
| Legacy IQ calibration `.class` files | Operator | M2 |

Note for the calibration step: `InitCalibration` pushes `0` into `:CORR:SA:GAIN` per the decompiled
strings, but this must be confirmed empirically. The app now pushes its own per-check value, so if
the two differ, validation results after calibration shift by exactly that difference.

---

## 9. Deferred portability list

Choices that rely on the laptop's resources and are acceptable today. They are collected here and
worked through as **one refactor pass** before any deployment to NSLAB04-PC (Windows 7, 32-bit,
older browser). Nothing on this list is a defect; leaving an item off the list would be.

| Item | Introduced by | What the refactor would need |
|---|---|---|
| Unbounded live-log buffer in the browser | U3 | Ring buffer with a configurable cap, plus virtualised rendering of the log list |
| Full result set held in the DOM | U4 | Windowed rendering of the results table |
| (add further items here as they are introduced) | | |

Rule: any PR that adds an item to this list says so in its description. Any PR that removes one
notes it in `CHANGELOG.md`.

---
