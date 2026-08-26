# Power Accuracy — Staged Parity Plan (Legacy `NsPowerCalibration`)

Date: 2026-08-25/26 (Stage 3 correction + all 5 decisions resolved 08-25; Stages 2–4 implemented)
Scope: `core/checks/power_accuracy.py`, `core/analyzer.py`, `core/modulator.py`, `core/session.py`,
`core/checks/base.py`, `config/config.json`.
Status: **Plan approved. Stages 1–4 are implemented; Stages 1–3 merged, Stage 4 in PR (this
document is the source of truth for Stages 1–5); Stage 5 remains analysis-only until its own
implementation pass.**

**Config fix (2026-08-25):** `power_accuracy.chp_integ_bw_hz` corrected on the live config from
`8000000` to `5000000` — the value flagged as drift in the Stage 1/2 PRs (#5, #6). Integration
bandwidth must match the occupied bandwidth of the signal: symbol-rate × (1 + roll-off) =
4 MSPS × 1.25 = 5 MHz. The `8000000` on the bench was span, not integration BW. This resolves
that drift; decision 1 below is otherwise unchanged (the value was always meant to be `5000000`,
now it actually is on disk).

## Context

Operator decision (final): we are **not** running further bench diagnostics and **not** investigating
the 1465→1500 MHz discontinuity as a separate root-cause question (see `POWER_ACCURACY_INVESTIGATION.md`
for that earlier analysis). The decision is to bring `power_accuracy.py` into parity with the legacy
Java tool (`NsPowerCalibration`), which is the known-good reference implementation. The legacy sequence
below is treated as the specification.

**Resolved — not open questions:**
- Measurement backend: the reference results file was produced via `SpectrumComm` (CXA), not the power
  sensor. Confirmed by file dates: `exaSettings` modified 21-Jul-2026, reference results file
  22-Jul-2026, `powerSensorSettings` untouched since 25-Mar-2019. The legacy SCPI sequence below is the
  one that produced the known-good numbers.
- DUT state inheritance: confirmed. With the app sending only `sine off / symbol-rate 4 / tx enable`,
  the unit was observed in: Line Mode NS4, Roll Off 0.25, Dual Channel Mode = Single channel,
  Spectrum Invert OFF, NS4 NLC OFF, Output Level Mode = Constant-Power. The DUT inherits state from the
  previous session rather than falling back to a documented default.

## Legacy specification (target behaviour)

Extracted from decompiled `SpectrumComm.class` / `startValidate.class` / `ModComm.class`.

```
SpectrumComm.InitValidation():
      CONF:CHP
      CHP:BAND:INT <n> MHz
      CHP:FREQ:SPAN <span>
      CHP:BAND:AUTO ON
      CHP:BAND <rbw> HZ
      CHP:BAND:VID:AUTO ON
      CHP:BAND:VID <vbw>
      CHP:SWE:TIME:AUTO ON        <-- sweep time left on AUTO
      CHP:SWE:TIME?               <-- queried, parsed (ParseSweep), used to compute wait
      CHP:AVER 10
      CHP:AVER ON
      CHP:AVER:COUN <averageCount>

SpectrumComm.BasicInit():        :conf:san

SpectrumComm.InitCalibration():  <-- belongs to startCalibrate, a DIFFERENT legacy tool.
                                      startValidate calls BasicInit + InitValidation only,
                                      NOT this method. Kept here for reference/traceability,
                                      but RLEV/POW:ATT/CORR:SA:GAIN below are NOT part of the
                                      validation-path spec. See Stage 3 correction.
      :SYS:PRES
      FREQ:SPAN <span> Hz
      BAND <rbw>
      BAND:VID <vbw>
      SWE:TIME <sweep>
      POW:ATT:AUTO ON
      CORR:SA:GAIN 0
      DISP:WIND:TRAC:Y:RLEV 15 dBm

SpectrumComm.SetFreq():          FREQ:CENT <freq>

SpectrumComm.GetValidationPower():
      INIT:REST
      sleep( <derived from queried sweep time> x count )
      :READ:CHPower:CHPower?
      wrapped in a retry loop (channelPowerTriesCount)

startValidate modulator setup:
      top / modulator-config / line
      tx enable / sine off
      symbol-rate <n> / roll-off <n>
      dual-channel-mode single-ch
      -channel-1
      state enable / source test-pattern
      modulation qpsk / frame-zise normal / fec-rate 2/3 / pilot yes
      (note: legacy does NOT set Output Level Mode explicitly - it relies on inherited unit state.
       See decision 4 below.)

startValidate DUT ADC cross-check:
      -adc-power / get-power       (logged as "adc: <value>")
```

`startValidate`'s link attenuation is FREQUENCY-INTERPOLATED, not constant
(fields: `ifLinkSettings`, `rfLinkSettings`, `startAttn`, `stopAttn`, `ifAttnSlop`, `rfAttnSlop`, `linkAttn`).
Anchors from the reference results file:

```
IF band:  50 MHz -> 5.80 dB ... 180 MHz -> 5.89 dB
L band:  950 MHz -> 3.37 dB ... 2150 MHz -> 3.59 dB
```

Our app currently uses flat constants 5.7 / 3.5.

`startValidate` prompts the operator at the IF↔L-band boundary:
`"Moved from IF to L-BAND. Change link settings and press OK."` (and the reverse). Our app already has
an equivalent cable-switch pause — verified at parity below, not duplicated.

Legacy settings files for reference:
```
exaSettings.txt : 192.168.0.5 / 500000 / 10000 / 1000 / 0.04 / 10 / 0.5
modSettings.txt : 192.168.0.50 / "0,-30,2" / 0.5
```
**Resolved (see decision 1/2 below): we are not porting these legacy numeric values at all.**
We want the legacy *method* (CHP-scoped nodes, AUTO sweep + query, averaging, `INIT:REST` +
computed wait + retry) — not the legacy *numbers*, which are tied to legacy's own signal
configuration. `span_hz`, `res_bw_hz`, `video_bw_hz`, `chp_integ_bw_hz` all stay at our own
existing values. The one exception: `10` from `exaSettings.txt` is taken as the
`chp_average_count` default (Stage 2).

**Important correction to the legacy call graph** (changes the reading of `InitCalibration()`
below): `startValidate` calls `BasicInit()` + `InitValidation()`. It does **not** call
`InitCalibration()` — that belongs to a different legacy tool, `startCalibrate`. `RLEV 15 dBm`,
`POW:ATT:AUTO ON`, and `CORR:SA:GAIN 0` are therefore **not** part of the validation-path
specification; legacy validation simply inherits whatever instrument state the calibration tool
(or the operator) left behind. This matters for Stage 3 — see the correction there.

## What the app currently does (to be replaced)

```
:SYST:PRES
:CONF:CHP
:CHP:BAND:INT 5000000
:CHP:SWE:TIME:AUTO OFF
:CHP:SWE:TIME 0.04
:DISP:WIND:TRAC:Y:RLEV 0
:BWID 41000            <-- generic node, wrong scope for CHP measurement
:BWID:VID 1000         <-- generic node, wrong scope for CHP measurement
(per point)  :FREQ:CENT <hz>
             :FREQ:SPAN 8000000   <-- generic node, wrong scope for CHP measurement
             <modulator freq / power>
             :READ:CHP:CHP?       <-- no INIT:REST, no computed wait, no retry
```

Config: `dwell_s=0.3`, `ext_gain_db=0` (`apply_ext_gain=false`), `if_atten_db=5.7`,
`lband_atten_db=3.5`, `if_max_mhz=180`, `span_hz=8000000`, `res_bw_hz=41000`,
`video_bw_hz=1000`, `sweep_time_s=0.04`, `chp_integ_bw_hz=5000000`,
`ref_level_dbm=0`, pwr 0→-30 step 2, tolerance 0.8 dB.

Modulator setup: `-modulator-config` / `line` / `sine off` / `symbol-rate 4` / `tx enable`.

---

## 2. Element-by-element: current vs legacy vs required change

| Legacy element | We currently do | Legacy does | Required change |
|---|---|---|---|
| Measurement class entry | `:CONF:CHP` (`power_accuracy.py:35`) | `CONF:CHP` | Already matches. |
| Integration BW | `:CHP:BAND:INT <n>` (`:36`) — CHP-scoped, correct | same | Already matches; keep. |
| Span | `:FREQ:SPAN 8000000` generic, sent via `cxa.set_center_span()` (`analyzer.py:54-56`, called from `power_accuracy.py:44` every point) | `CHP:FREQ:SPAN <span>` | New `Analyzer.set_chp_span()` sending `:CHP:FREQ:SPAN`; call it from `power_accuracy.py` instead of the generic span half of `set_center_span()`. |
| RBW | `:BWID 41000` generic, via `cxa.set_bw()` (`analyzer.py:60-62`) | `CHP:BAND:AUTO ON` then `CHP:BAND <rbw> HZ` | New `Analyzer.set_chp_bw()` sending both, in that order, replacing the `set_bw()` call in `power_accuracy.py:41`. |
| VBW | `:BWID:VID 1000` generic, same call | `CHP:BAND:VID:AUTO ON` then `CHP:BAND:VID <vbw>` | Same `set_chp_bw()` extension, both AUTO+explicit pairs sent in legacy order. |
| Sweep time (CHP) | `:CHP:SWE:TIME:AUTO OFF` + `:CHP:SWE:TIME 0.04` (`:37-38`) | `CHP:SWE:TIME:AUTO ON`, then `CHP:SWE:TIME?` queried and parsed, used to compute the post-`INIT:REST` wait | New `Analyzer.get_chp_sweep_time()`; `power_accuracy.py` switches to AUTO ON + query, drops the forced 0.04 s write. |
| Averaging | none | `CHP:AVER 10`, `CHP:AVER ON`, `CHP:AVER:COUN <n>` | New `Analyzer` calls; `power_accuracy.py::analyzer_setup()` sends them. |
| Ref level | `:DISP:WIND:TRAC:Y:RLEV 0` (via `cxa.set_ref_level()`, `:40`) | Not part of the validation path — `RLEV 15` belongs to `InitCalibration()` (`startCalibrate`, a different legacy tool never called by `startValidate`) | **No change.** `RLEV 15 dBm` is a swept-SA calibration-path setting, not a Channel Power validation setting — dropped from this plan. Keep our own configurable `power_accuracy.ref_level_dbm` (still `0`, or whatever the operator tunes). |
| Attenuation | not touched at all (relies on preset default) | Not part of the validation path either, same reasoning | **Keep** — but reframed: not "legacy parity," but **deterministic baseline initialization**. `startValidate` gets away with inheriting instrument state left by the calibration tool; our app can't assume that (three checks share one instrument, each must leave it in a known state for the next). Add `cxa.set_attenuation_auto(True)` (existing method, `analyzer.py:86-87`, unused by this check today) to `analyzer_setup()`, applied *before* the CHP-specific setup block. |
| Ext gain / correction | `apply_ext_gain=false` → nothing pushed, only logged | Same — not part of the validation path, but worth keeping as deterministic baseline | **Keep** `CORR:SA:GAIN 0`, same reframing as attenuation above — baseline init, not legacy parity. Per decision 5: pushed as a **`power_accuracy`-local call**, not by flipping the global `analyzer.apply_ext_gain` flag (that flag must stay `false` globally so `iq_validation`'s `ext_gain_db=-3.5` path, tied to its own reference calibration, is unaffected). |
| Init/read | `:READ:CHP:CHP?` only, no explicit restart (`analyzer.py:110-111`, called from `power_accuracy.py:54`) | `INIT:REST`, `sleep(computed)`, `:READ:CHPower:CHPower?`, wrapped in a retry loop | New `Analyzer.chp_restart_and_settle()` (or fold into `read_chp()`): explicit `:INIT:REST`, sleep for `sweep_time × average_count × margin`, then read; `power_accuracy.py::measure_point()` wraps it in a bounded retry loop. This is also the fix for the "first point of every block" outlier — same class of bug already fixed in `flatness.py`. |
| Frequency retune | `:FREQ:CENT <hz>` per point via `set_center_span()` (`:44`), resent even when unchanged within a power block | `FREQ:CENT <freq>` | Keep the call, but only actually needed once per frequency block; harmless to keep resending (matches current flatness/power_accuracy pattern), no change required here beyond what Stages 1/2 already restructure. |
| Modulator setup | `-modulator-config` / `line` / `sine off` / `symbol-rate 4` / `tx enable` (`power_accuracy.py:26-31`) | `top` / `modulator-config` / `line` / `tx enable` / `sine off` / `symbol-rate` / `roll-off` / `dual-channel-mode single-ch` / `-channel-1` / `state enable` / `source test-pattern` / `modulation qpsk` / `frame-size normal` / `fec-rate 2/3` / `pilot yes` | Full sequence replicated in `power_accuracy.py::modulator_setup()`, new config keys for the values (`roll_off`, `modulation`, `fec_rate`, `frame_size`, `pilot`). |
| Link attenuation | flat constants `if_atten_db`/`lband_atten_db` (`power_accuracy.py:47-50`) | frequency-interpolated slope (`startAttn`/`stopAttn`/slope per band) | `_atten()` rewritten to linearly interpolate between per-band start/stop constants instead of a flat value. |
| IF↔L-band operator prompt | Already implemented: `session.py::_auto_loop()` (`:99-111`) pauses and shows "Reconnect the RF cable to the %s output..." whenever `_band()` changes between consecutive points | "Moved from IF to L-BAND. Change link settings and press OK." (and reverse) | **Already at parity, functionally** — same trigger condition (`if_max_mhz` boundary crossing), same block-until-operator-confirms behavior, just different wording. No change needed; confirmed by reading `session.py`, not assumed. |
| DUT ADC cross-check | none | `-adc-power` / `get-power`, logged as `adc: <value>` | New `Modulator`/`base.py` helper to send the CLI command and parse the reply; new CSV column `ADC_Power_dBm`, diagnostic only, not part of pass/fail. |

## 3–4. Staged plan

**Stage 1 — CHP-scoped SCPI nodes**
- Files: `core/analyzer.py` (new `set_chp_bw(rbw_hz, vbw_hz)`, `set_chp_span(span_hz)` — separate methods, generic `set_bw()`/`set_center_span()` left untouched), `core/checks/power_accuracy.py` (`analyzer_setup()`, `prepare_point()` call the new methods instead of the generic ones).
- Config keys: none new — reuses existing `res_bw_hz`, `video_bw_hz`, `span_hz`.
- Backward compatibility: zero impact on `flatness.py`/`iq_validation.py` — confirmed via grep that `set_bw()`/`set_center_span()` are called only from those two checks plus `power_accuracy.py`; the new CHP-scoped methods are additive, only `power_accuracy.py` switches to them.
- Risk: **Low** — additive methods, single call-site swap.
- Bench check: query `:CHP:BAND?` / `:CHP:BAND:VID?` / `:CHP:FREQ:SPAN?` right after setup and confirm they now read back the configured values (they previously would not have, per the earlier investigation).

**Stage 2 — measurement timing + averaging — IMPLEMENTED (2026-08-25)**
- Files: `core/analyzer.py` (new `set_chp_sweep_time_auto(on)`, `get_chp_sweep_time()`, `set_chp_average(on, count)`, `chp_restart()`), `core/checks/power_accuracy.py` (`analyzer_setup()` sends the AUTO-sweep-time/averaging setup and queries the effective sweep time; new `_read_chp_with_retry()` wraps `:INIT:REST` + computed settle wait + `read_chp()` in a bounded retry loop, called from `measure_point()` instead of a bare `read_chp()`; `evaluate_point()` turns an exhausted-retry failure into a FAIL row instead of raising).
- Config keys (additive, fallback to current values): `chp_sweep_time_auto` (default `true`), `chp_average_on` (default `true`), `chp_average_count` (default `10` — the one value taken from `exaSettings.txt` per decision 1/2, nothing else from that file), `chp_read_retries` (default `1` = no retry, preserves current behavior if left at default; retry triggers only on a transport/SCPI exception per decision 3, no value-sanity retry), `chp_settle_margin` (default `1.1`, same pattern as flatness's `sweep_settle_margin`). `sweep_time_s` kept as fallback when `chp_sweep_time_auto=false`.
- **Deviation from the literal legacy sequence, disclosed rather than silently decided**: legacy's decompiled `InitValidation()` has a bare `CHP:AVER 10` line immediately before `CHP:AVER ON` / `CHP:AVER:COUN <n>`. `:CHP:AVER` is a documented boolean SCPI node; `10` is not a valid SCPI boolean, so this line either duplicates `:CHP:AVER:COUN` (a decompilation artifact) or would be rejected by the instrument. Per decision 1's "legacy method, not legacy numbers," a fixed un-parameterized value that isn't clearly meaningful isn't something to blindly replicate — `set_chp_average()` sends only the two well-defined nodes (`:CHP:AVER:COUN`, `:CHP:AVER`). Flagging this for the operator in case there's a hardware reason for that third line that isn't visible from the decompiled bytecode.
- Per-point fault isolation added as a natural extension of the retry-loop work (not explicitly in the original Stage 2 wording, but directly wraps the same code path): `power_accuracy.py` had **no** per-point isolation before this stage — a single `read_chp()` exception used to abort the entire run (the same class of bug already fixed in `flatness.py`). Now, after `chp_read_retries` is exhausted, the point is reported as `{"error": ...}` and `evaluate_point()` returns `FAIL`/`flag=True`, matching `flatness.py`'s pattern; the run continues to the next point.
- Backward compatibility: fully additive; an old config without these keys runs with sane defaults matching legacy intent, not the prior behavior — flagged explicitly since it's a real behavior change, not a no-op default. `flatness.py`/`iq_validation.py` untouched (grep-confirmed no shared call sites with the new methods).
- Risk: **Low** — same proven mechanism as the flatness settle fix; averaging is a pure-instrument-side addition. New regression tests: `test_power_chp_scoped_nodes()` (extended) and `test_power_chp_read_retry()` in `tests/test_sequences.py` — all 10 tests pass via `python -m tests.test_sequences`.
- Bench check: confirm `:CHP:SWE:TIME:AUTO?` reads `ON`, `:CHP:AVER?` reads `ON`, `:CHP:AVER:COUN?` reads the configured count (default `10`); confirm the first-point-of-block outliers are gone (950 MHz block's first point should sit near the rest of that block, not diverge by several dB).

**Stage 3 — deterministic baseline init: attenuation + ext gain (corrected — not "ref level parity") — IMPLEMENTED (2026-08-25)**
- **Correction (resolved 2026-08-25):** the original draft of this stage conflated two different
  legacy methods. `RLEV`/`POW:ATT`/`CORR:SA:GAIN` come from `InitCalibration()`, which belongs to
  `startCalibrate` — a different legacy tool. `startValidate` (our actual reference) calls
  `BasicInit()` + `InitValidation()` only, which contains **no** `RLEV`, **no** `POW:ATT`, **no**
  `CORR:SA:GAIN`. Legacy validation inherits whatever instrument state the calibration tool left
  behind; it never sets this itself. So:
  - **Dropped**: the `ref_level_dbm` 0 → 15 change. There is no legacy-validation basis for it —
    keep our own configurable value.
  - **Kept**, but reframed: `POW:ATT:AUTO ON` and `CORR:SA:GAIN 0` are not "legacy parity" — they're
    **deterministic baseline initialization** that `analyzer_setup()` must do on its own, because
    unlike the single-purpose legacy tool, our app can't rely on inheriting undefined instrument
    state between three different checks sharing one CXA.
- Files: `core/checks/power_accuracy.py::analyzer_setup()` — `cxa.set_attenuation_auto(True)` (gated by new `atten_auto`, default `true`) and an unconditional `cxa.set_ext_gain(0)` (`:CORR:SA:GAIN 0`), both sent right after `preset()`, *before* `:CONF:CHP` and the CHP-specific setup block (Stage 1/2's CHP-scoped nodes) — earlier than the plan draft's "before the CHP setup block" wording strictly required, since attenuation/correction are analyzer-level, not measurement-class-scoped, settings; placing them before even entering CHP mode is the cleanest read of "baseline init." The old `cxa.apply_ext_gain()` call (gated by the global `analyzer.apply_ext_gain` flag, previously a no-op log line since that flag is `false`) was **removed** from this check — superseded by the unconditional local push, avoiding two different code paths that could disagree about what `CORR:SA:GAIN` ends up as.
- Config keys: new `power_accuracy.atten_auto` (default `true`). No `apply_ext_gain`/`ext_gain_db` override needed at the analyzer-config level — per decision 5, `power_accuracy.py` pushes `CORR:SA:GAIN 0` directly, independent of the global `analyzer.apply_ext_gain` flag.
- Backward compatibility: `flatness.py`/`iq_validation.py` fully untouched (grep-confirmed no shared call sites) — the global `analyzer.apply_ext_gain` flag stays `false`, so `iq_validation`'s `ext_gain_db=-3.5` path (tied to its own reference calibration) is unaffected. `power_accuracy.ref_level_dbm` is not changing at all, removing what was previously the highest-uncertainty part of this stage.
- Risk: **Low-Medium** (downgraded from the original draft's Medium, since the ref-level change — the part with the least certain effect on other signal levels — is dropped). Attenuation auto-coupling and a zeroed correction are both well-understood, low-surprise instrument states. New regression assertions in `test_power_chp_scoped_nodes()` cover both calls firing and firing before the CHP-scoped setup — all 10 tests pass via `python -m tests.test_sequences`.
- Bench check: confirm `:POW:ATT:AUTO?` reads `ON` and `:CORR:SA:GAIN?` reads `0` right after `analyzer_setup()`; rerun the full sweep and check whether the systematic block-level (not just first-point) deviation shrinks.

**Stage 4 — modulator setup parity — IMPLEMENTED (2026-08-26)**
- Files: `core/checks/power_accuracy.py::modulator_setup()` — full sequence sent in legacy order: `-u expert-login` (existing `base.enter_expert()`) / `top` / `-modulator-config` / `line` / `tx enable` / `sine off` / `symbol-rate 4` / `roll-off` / `dual-channel-mode single-ch` / `-channel-1` / `state enable` / `source test-pattern` / `modulation` / `frame-size` / `fec-rate` / `pilot` / (conditionally) the Output Level Mode command. Kept scoped to `power_accuracy.py` only, no shared `base.py` helper added — neither `flatness.py` nor `iq_validation.py` use this signal path.
- Two order changes from the pre-Stage-4 code, both intentional, both matching legacy: `top` added as the very first navigation step (starts from the CLI root regardless of what menu a prior check, e.g. `iq_validation`'s `-calib-` path, left the modulator in); `tx enable` now sent *before* `sine off`, reversed from the old order, because legacy's bench-tested reference results were produced with the carrier enabled first — replicated as given rather than kept in the old order.
- Config keys (additive, code-defaulted only - consistent with Stages 2/3, not added to `config/config.json`): `power_accuracy.roll_off` (default `0.25`), `modulation` (default `qpsk`), `fec_rate` (default `2/3`), `frame_size` (default `normal`), `pilot` (default `yes`) — all matching legacy's literal values. Plus, per decision 4: `power_accuracy.set_output_level_mode` (default **`true`**, not opt-in) and `power_accuracy.output_level_mode_cmd` (default `output-level-mode constant-power`).
- **Flag for the operator — genuinely unverified, not a guess dressed up as fact:** legacy *never* sets Output Level Mode at all — it only ever inherits whatever the unit was last left in (that's the entire basis of decision 4's "our app can't rely on inherited state" rationale). There is therefore **no decompiled legacy string to copy** for this one command, unlike every other line in this stage. `output-level-mode constant-power` is a best-effort guess following the same kebab-case `<setting> <value>` pattern as the sibling commands (e.g. `dual-channel-mode single-ch`) — not confirmed against the DUT's actual CLI. `modulator_setup()` logs a warning every time it sends this command, precisely so a wrong guess is visible in the run log rather than silently swallowed. The command text is a config key (`output_level_mode_cmd`) specifically so the operator can correct it without a code change once the real syntax is confirmed on the bench.
- Backward compatibility: only this check's `modulator_setup()` changes; `flatness.py`/`iq_validation.py` use `base.clean_carrier_setup()`/`base.iq_setup()`, untouched.
- Risk: **Medium** — direct behavior change to DUT signal generation (modulation format, FEC, pilot, tx-enable/sine-off order), should be bench-verified independently of Stages 1–3 so any effect on the numbers is attributable to this stage specifically, not conflated with the CXA-side fixes. The Output Level Mode line specifically carries **added** risk (unverified syntax) beyond the rest of the stage, which is a faithful legacy-string replication.
- New regression test: `test_power_modulator_setup()` in `tests/test_sequences.py` — asserts the full sequence and order, config-driven substitution for all five parameterized commands, and that `set_output_level_mode=false` skips that command entirely. All 11 tests pass via `python -m tests.test_sequences`.
- Bench check: with Stages 1–3 in place, confirm the DUT reports the expected modulation/FEC/pilot state (e.g. via its own CLI query) matches what legacy configured; **specifically check the run log for the Output Level Mode warning and confirm on the DUT's own UI/CLI whether `output-level-mode constant-power` was actually accepted** (vs. rejected/ignored) — correct `power_accuracy.output_level_mode_cmd` in config if not; then check whether any residual deviation changes.

**Stage 5 — frequency-interpolated attenuation + ADC cross-check**
- Files: `core/checks/power_accuracy.py::_atten()` (linear interpolation between per-band start/stop constants instead of a flat value), `core/modulator.py` or `core/checks/base.py` (new helper to send `-adc-power` / `get-power` and parse the reply), `power_accuracy.py::measure_point()`/`row_for()` (new `ADC_Power_dBm` column, diagnostic only — does not feed `evaluate_point()`'s pass/fail).
- Config keys (additive): `if_atten_start_db`/`if_atten_stop_db` (default both = current `if_atten_db`, i.e. flat = today's behavior if left unset), `lband_atten_start_db`/`lband_atten_stop_db` (default both = current `lband_atten_db`). This makes the flat-constant behavior the exact fallback when the new keys are absent — true zero-impact default.
- Backward compatibility: `csv_columns` gains one column — the results-table/report rendering (`static/js/app.js`, `templates/index.html`) iterates `info.columns`/`res.columns` generically, so this should be a non-issue, but worth eyeballing on the first run.
- Risk: **Low** — attenuation change is a small numeric correction (~0.2 dB per the reference anchors); ADC cross-check is purely additive/diagnostic, doesn't touch pass/fail logic.
- Bench check: confirm interpolated attenuation matches the reference anchors at 50/180/950/2150 MHz; confirm the ADC column's values track sensibly with the CXA reading on a known-good run.

## 6. Decisions — RESOLVED (2026-08-25)

All five decisions below are final. Recorded here so this document stays the source of truth for
Stage 2 onward; not open questions anymore.

1. **`exaSettings.txt` / `modSettings.txt` field mapping: DROPPED, not resolved, not ported.**
   We are not porting legacy's numeric values at all — they're tied to legacy's own signal
   configuration, not ours. We want the legacy *method* (CHP-scoped nodes, AUTO sweep + query,
   averaging, `INIT:REST` + computed wait + retry), not the legacy *numbers*. `span_hz`,
   `res_bw_hz`, `video_bw_hz` stay at our existing values, unchanged. `chp_integ_bw_hz` stays
   `5000000` — already correctly derived (symbol-rate 4 MSPS × (1 + roll-off 0.25) = 5 MHz), not
   to be touched. From `exaSettings.txt`, exactly **one** value is taken: `10` → `chp_average_count`
   default. Everything else in both files is out of scope; do not guess at field order, do not
   add config keys derived from them, do not raise this again.

   > **Flag for the operator** (found while implementing, not re-litigating the above): the live
   > `config/config.json` on disk currently has `power_accuracy.chp_integ_bw_hz = 8000000`, not
   > `5000000`. Since this decision explicitly says the value is "already correctly derived" at
   > 5 MHz and "do not touch it," I have **not** changed it — but the live value doesn't currently
   > match that description. Worth a look; not touched by Stage 1 either way (Stage 1 doesn't
   > modify `chp_integ_bw_hz`).

2. *(folded into 1 above — was the `modSettings.txt` third-field question; also dropped, not ported.)*

3. **Retry trigger: ACCEPTED as proposed.** Retry only on a transport/SCPI exception, capped at a
   small `chp_read_retries` count. Matches the per-point fault-isolation pattern already shipped
   in `flatness.py` and `iq_validation.py`. No value-sanity retry.

4. **Output Level Mode: Option B, default ON.** Set it explicitly in `modulator_setup()`, not
   opt-in. Rationale: documented evidence the DUT carries state across sessions — that's exactly
   how it was found in NS4 / Roll Off 0.25 / Single channel / Constant-Power without the app
   setting any of it. Legacy could rely on inheritance because it was a single-purpose tool; our
   app runs three checks that each reconfigure the unit, so determinism outweighs literal parity
   here. The config key stays present so it can be disabled, but defaults to `true`.

5. **Ext gain scope: per-check override only.** `power_accuracy.py` pushes `CORR:SA:GAIN 0`
   locally, for itself. The global `analyzer.apply_ext_gain` flag is **not** flipped. Reason:
   `iq_validation` runs with ext gain `-3.5 dB`, matching the value used when its reference
   calibration was taken — flipping the global flag to `true` with `ext_gain_db=0` would shift IQ
   results by 3.5 dB. Blast radius stays inside `power_accuracy`.
