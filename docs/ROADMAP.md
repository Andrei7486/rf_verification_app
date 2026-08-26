# RF Verification App — Roadmap

Status: **v1.0** — pending operator sign-off on ordering
Last updated: 2026-08-26
Companion: `docs/VALIDATION_APP_SPEC.md` (what), `docs/DEVELOPMENT_RULES.md` (how)

Every stage below is a single PR and a single deployable increment. After each one the operator can
run all three checks on the bench and continue production work. See spec §2 (release contract).

---

## Current position

```
[P0 gates] ──► S0 ──► S1 ──► S2 ──► S3 ──► S4 ──► S5 ──► S6 ──► S7 ──► S8 ──► S9 ──► S10 ──► S11 ──► S12 ──► S13
    ▲                                             │
    │                                             └── M-track (IQ) preempts when its inputs arrive
 you are here
```

**Now:** P0 — NS330 calibration in progress, `NsPowerCalibrationV6.2.jar` running. **S-M0 preempts
the queue** (operator-directed, out of stage order): Power Accuracy's per-point overhead measured at
5.5x the legacy tool, root-caused and fixed against the archived bench log while P0.1 is still
running — see the stage entry below. Stacked on the still-unmerged S0 branch/PR.

**Runtime:** the app currently runs from Andrei's laptop (Windows 11 x64), on the lab network with
the CXA and the DUT. NSLAB04-PC (Windows 7 32-bit) remains a possible future deployment, so the
Python 3.8 / win32 compatibility floor holds for all stages. See `DEVELOPMENT_RULES.md` §2.

---

## P0 — Gates before any new code

Not development stages. Operator actions that unblock everything else.

| # | Action | Why it matters |
|---|---|---|
| P0.1 | Finish NS330 calibration with `NsPowerCalibrationV6.2.jar` | Every deviation recorded so far mixes an uncalibrated unit with possible app defects. After calibration, what remains is real. |
| P0.2 | Read `:CORR:SA:GAIN` off the CXA front panel when the JAR finishes | `InitCalibration` pushes `0` per the decompiled strings — confirm empirically. The app now pushes its own value; if they differ, post-calibration validation shifts by the difference. |
| P0.3 | Confirm `pwr_calibration.csv` is in `/data/var` on the unit (`shell` / `cd /data/var` / `ls`) | Confirms the calibration table actually landed, as `checkCalibration.pl` does. |
| P0.4 | **Short** Power Accuracy run: 950 and 2150 MHz, 7 power steps (14 points) — not 175 | If calibration took, deviations collapse toward zero within a minute. 2150 MHz immediately shows whether the first-point settling artifact survived. |
| P0.5 | Archive that run as the **post-calibration baseline** in `docs/bench/` | Every R2 stage from here compares against it. |
| P0.6 | Supply the legacy IQ calibration `.class` files | Unblocks the whole M-track (S-M1/S-M2). |

**Exit criteria:** P0.1–P0.5 done and the baseline log committed. P0.6 unblocks the IQ track
independently and can arrive at any time.

---

## Ordering principle

1. **Zero-risk first.** R0 stages that cannot touch the measurement path go early — they deliver
   daily-workflow value while the calibration situation settles.
2. **Instrumentation before optimisation.** You cannot speed up what you have not measured, and you
   cannot compare runs whose config you cannot reconstruct. Hence config integrity and timing
   instrumentation precede the speed work.
3. **The IQ track preempts.** IQ Validation is currently unusable and blocking real work. The
   moment the `.class` files arrive, S-M1/S-M2 jump ahead of whatever UI stage is next in the queue.
4. **UI restructure last.** Reworking the menu before U1–U5 land would mean doing it twice.

---

## Stage list

### S0 — Documentation and repository scaffolding
Risk: R0 · Est: small · Needs: **D15**
`CLAUDE.md`, `docs/VALIDATION_APP_SPEC.md`, `docs/DEVELOPMENT_RULES.md`, `docs/ROADMAP.md`,
`CHANGELOG.md`, `docs/progress.html` (development tracker), plus `docs/JOURNAL.md` and `docs/adr/`
if D15 is accepted. No application code.
**Why:** from this point the repository is the source of truth and the chat is not. Also gives CC a
single entry point so that every future session starts from the same state.

### S-M0 — Power Accuracy per-point overhead (preempts the queue)
Req: **M7** · Risk: R1 + R2 · Est: medium · Needs: **D18**
Modulator-side per-point overhead cut from a measured ~13.4 s/point (7 commands at a flat
~1.4 s/command fixed wait) via: (1) DUT-side ADC power cross-check gated behind
`power_accuracy.enable_adc_power_check`, default off; (2) `freq` sent only on change within a block,
not resent every point; (3) prompt-based transport read (`root@Modem ... *<N>`) replacing the fixed
post-command sleep, with a bounded timeout fallback and a mandatory explicit post-`power` settle
dwell. Does not touch `chp_average_count`, the `INIT:REST` wait, sweep-time AUTO, or any CHP-scoped
node (D11 not reopened).
**Why out of order:** operator-directed; the 5.5x-vs-legacy gap was blocking bench work independently
of the P0 calibration gate, and the fix does not depend on P0 completing.
**Accept:** see spec §M7 — Point-1-to-last-`Measured:` time under 60 s (baseline 219.1 s) for the
50 MHz/16-point block; setup phase reported separately, no threshold; value parity within 0.1 dB;
no ADC/nav commands between points; `MOD freq` once per block, not once per point;
`:CORR:SA:GAIN?` read-back unchanged. If value parity fails, item 3 alone reverts.

### S1 — Config integrity and drift detection
Req: **M6** · Risk: R0 · Est: small
Full parameter block in the run log, effective-vs-default diff at run start, config version stamp.
**Why first:** it is the prerequisite for trusting every comparison made in later stages, and it
closes a standing open item that has already cost one unexplained 5–6 dB discrepancy.
**Accept:** remove a key on the bench — the log names it and the documented default is used.

### S2 — Immediate response after Start Run
Req: **U2** · Risk: R0 · Est: small
Instant status change, running indicator, double-start lock, first log lines immediately.
**Why here:** smallest possible visible win, and it establishes the run-state model that S3 and S5
build on.

### S3 — Real-time logs
Req: **U3** · Risk: R0 · Est: medium · Needs: **D6**
Streaming of DUT and analyzer traffic to the UI as it happens.
**Note:** decide D6 (SSE vs polling) before this stage opens.

### S4 — Scrollable results area
Req: **U4** · Risk: R0 · Est: small
Fixed-height results block with its own scrollbar; header stays visible; colour coding and the
failed-frequency summary block preserved.

### S5 — Progress and remaining time
Req: **U5** · Risk: R0 · Est: medium · Needs: **D8**
Progress, elapsed, ETA, points done/left, for all checks including future ones.
**Bonus:** the per-point timing this requires is exactly the instrumentation S8 needs.

### S6 — Run page state persistence
Req: **U1** · Risk: R0 · Est: small · Needs: **D12**
Selection survives Run → Settings → Run.

### S7 — Analyzer warnings in the UI
Req: **M5** (detection only) · Risk: R1 · Est: medium · Needs: **D7**
`:SYST:ERR?` and status polling after each point; overload/overrange surfaced immediately; affected
point marked suspect in the table and CSV. **Auto-retry is not in this stage.**
**Accept:** induce an overload — it appears within one point, the point is flagged, the run
continues.

### S8 — Power Accuracy timing instrumentation
Req: **M4** (investigation half) · Risk: R0 · Est: small
Per-point and per-phase timing in the log, total run time reported. **No optimisation yet.**
Produces the numbers that make the D11 conversation factual instead of speculative.

### S9 — First-point-of-block settling fix
Req: **M3** · Risk: R2 · Est: small · Needs: P0 complete
Dummy read or extra dwell before each block's first read, behind config keys.
**Accept:** at 2150 MHz the first point sits within its block's spread. A/B against the
post-calibration baseline.

### S10 — Power Accuracy speed optimisation
Req: **M4** (optimisation half) · Risk: R2 · Est: medium · Needs: S8, S9, **D11**
Only reductions that do not change what the instrument reports, unless D11 is explicitly reopened.
**Accept:** documented before/after total run time on the same matrix, with point-by-point
agreement within 0.1 dB.

### S11 — Unit auto-discovery and inventory
Req: **U6** · Risk: R1 · Est: medium · Needs: **D10**
Model, serial, SW/HW versions, licence; licence sufficiency warning per check.

### S12 — Embedded analyzer screen
Req: **U7** · Risk: R0 · Est: small · Priority: optional · Needs: **D9**
Toggleable panel showing the analyzer's own remote screen. Off during measurement by default.

### S13 — UI restructure
Req: **U8** · Risk: R0 · Est: large · Needs: design agreed and written into the spec first
Not started until U1–U5 are merged and the concrete design is specified.

---

## M-track — IQ Validation (preempts the queue)

### S-M1 + S-M2 — IQ external gain key and legacy parity
Req: **M1**, **M2** · Risk: R1 + R2 · Est: large · Blocked by: **P0.6** (`.class` files)

Ships as one PR by operator decision, so that `iq_validation.ext_gain_db = -3.5` gets bench-checked
alongside the IQ fixes.

Sub-items: M2.1 centre offset for Image, M2.2 weak-Main-CW guard, M2.3 no MAX HOLD by default,
M2.4 legacy DUT sequence, M2.5 auto reference level, M2.6 expected-frequency check, M2.7 split
LOFT/Image limits, M2.8 corrections in results and CSV, M2.9 VCO only after model support is
confirmed. Plus the delta-marker offset fix.

> **Standing warning:** IQ Validation must not be run before S-M1 lands. It currently falls back to
> the global external gain; if that is 0, every IQ measurement — including the diagnostics used to
> judge the two-peak defect — is off by 3.5 dB.

---

## Dependency summary

| Stage | Blocked by |
|---|---|
| S0 | D14, D15 |
| S-M0 | D18 |
| S3 | D6 |
| S5 | D8 |
| S6 | D12 |
| S7 | D7 |
| S9 | P0.1–P0.5 |
| S10 | S8, S9, D11 |
| S11 | D10 |
| S12 | D9 |
| S13 | U1–U5 merged, design specified |
| S-M1/S-M2 | P0.6, D13 |

Decisions D6–D17 are listed in `docs/VALIDATION_APP_SPEC.md` §7 with a proposed answer for each.
Answering them is cheap now and expensive mid-stage.

If D16 (minimal CI) is accepted, it is folded into S1 — that is the first stage producing
offline-testable logic, so it is the first stage where a CI run means anything.

---

## Stage status — machine-readable

**This table is the single source of truth for progress.** `docs/progress.html` parses it directly
at load time, so the tracker cannot go stale: there is no separate data file to update.

Update the `Status` cell when a stage moves. Allowed values: `planned`, `blocked`, `in-progress`,
`in-review`, `done`. `Weight` drives the percentage: `1` small, `2` medium, `4` large.

<!-- STAGES:BEGIN -->

| ID | Title | Track | Risk | Weight | Status | Tag | Accepted |
|---|---|---|---|---|---|---|---|
| P0.1 | NS330 calibration with the legacy JAR | P0 | — | 1 | in-progress | — | — |
| P0.2 | Read `:CORR:SA:GAIN` off the CXA front panel | P0 | — | 1 | planned | — | — |
| P0.3 | Confirm `pwr_calibration.csv` in `/data/var` | P0 | — | 1 | planned | — | — |
| P0.4 | Short post-calibration run, 950 + 2150 MHz | P0 | — | 1 | planned | — | — |
| P0.5 | Archive the post-calibration baseline | P0 | — | 1 | planned | — | — |
| P0.6 | Supply the legacy IQ `.class` files | P0 | — | 1 | planned | — | — |
| S0 | Documentation and repository scaffolding | infra | R0 | 1 | in-progress | — | — |
| S-M0 | Power Accuracy per-point overhead | M | R1+R2 | 2 | in-progress | — | — |
| S1 | Config integrity and drift detection | M | R0 | 1 | planned | — | — |
| S2 | Immediate response after Start Run | U | R0 | 1 | planned | — | — |
| S3 | Real-time logs | U | R0 | 2 | planned | — | — |
| S4 | Scrollable results area | U | R0 | 1 | planned | — | — |
| S5 | Progress and remaining time | U | R0 | 2 | planned | — | — |
| S6 | Run page state persistence | U | R0 | 1 | planned | — | — |
| S7 | Analyzer warnings in the UI | M | R1 | 2 | planned | — | — |
| S8 | Power Accuracy timing instrumentation | M | R0 | 1 | planned | — | — |
| S9 | First-point-of-block settling fix | M | R2 | 1 | blocked | — | — |
| S10 | Power Accuracy speed optimisation | M | R2 | 2 | blocked | — | — |
| S11 | Unit auto-discovery and inventory | U | R1 | 2 | planned | — | — |
| S12 | Embedded analyzer screen | U | R0 | 1 | planned | — | — |
| S13 | UI restructure | U | R0 | 4 | planned | — | — |
| S-M1 | IQ external gain key | M | R1 | 1 | blocked | — | — |
| S-M2 | IQ Validation legacy parity | M | R2 | 4 | blocked | — | — |

<!-- STAGES:END -->

---

## Progress log

| Date | Stage | Tag | Bench-accepted | Notes |
|---|---|---|---|---|
| 2026-08-26 | Stages 1–5 power accuracy parity, PR #10, #11, #13 | — | yes | Baseline for this roadmap |
| | | | | |
