# Power Accuracy Verdict — Analysis Only (No Code Changes)

Date: 2026-08-25
Scope: `core/checks/power_accuracy.py`, `core/analyzer.py`, `core/modulator.py`, `core/session.py`, `config/config.json`.
Status: **Analysis only — no code was changed, no commit/branch/PR was created for this investigation.**

## Context

The Power Accuracy check produces readings that do not match manual bench measurement.

**Observed symptom** (bench run 2026-08-25 13:11:35 → 13:28:19, 304 points, no errors/warnings):

- Level tracking is CORRECT: `Actual_dBm` follows `Set_dBm` in clean 2 dB steps. Modulator comms fine.
- Deviation is NOT constant — it is strongly frequency-dependent:
  - 950–1465 MHz: +7.4 … +9.3 dB (wrong)
  - 1500–2150 MHz: ≈ 0 ± 1 dB (essentially correct)
  - Sharp discontinuity between 1465 and 1500 MHz.
- The FIRST power point of every frequency block is an outlier vs the rest of that block
  (e.g. 950 MHz: first = 5.65 while the rest sit ~9.3; 2150 MHz: first = -22.18 while rest ~-0.8).
  Same class of settle problem already fixed in `flatness.py`.
- Manual cross-check at 950 MHz / 0 dBm: CXA Channel Power reads -3.49 dBm, which with the
  3.5 dB link attenuator equals ~0 dBm at the DUT output. So the HARDWARE PATH IS CORRECT.
  The app reported 5.65 dBm for the same condition.
- CXA front panel during manual check showed: Atten 20 dB, RBW 68 kHz, VBW 680 kHz,
  Span 7.5 MHz, Sweep 40 ms (1001 pts), Avg|Hold >10/10, External Preamp 0.00 dB, Align: Off.

**What the app currently sends** (from the run log):

```
:SYST:PRES
:CONF:CHP
:CHP:BAND:INT 5000000
:CHP:SWE:TIME:AUTO OFF
:CHP:SWE:TIME 0.04
:DISP:WIND:TRAC:Y:RLEV 0
:BWID 41000
:BWID:VID 1000
(per point)  :FREQ:CENT <hz>
             :FREQ:SPAN 8000000
             <modulator freq / power>
             :READ:CHP:CHP?
```

Config: `dwell_s=0.3`, `ext_gain_db=0` (not pushed to instrument),
`if_atten_db=5.7`, `lband_atten_db=3.5`, `if_max_mhz=180`,
`span_hz=8000000`, `res_bw_hz=41000`, `video_bw_hz=1000`, `sweep_time_s=0.04`,
`chp_integ_bw_hz=5000000`, `ref_level_dbm=0`, pwr 0→-30 step 2, tolerance 0.8 dB.

Modulator setup sent by the app: `-modulator-config` / `line` / `sine off` / `symbol-rate 4` / `tx enable`.

**Reference: legacy Java tool** (known-good, `NsPowerCalibration`), extracted from decompiled class files
(`SpectrumComm.class`, `startValidate.class`, `ModComm.class`):

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
      CHP:SWE:TIME?               <-- queried, result parsed (ParseSweep)
      CHP:AVER 10
      CHP:AVER ON
      CHP:AVER:COUN <averageCount>

SpectrumComm.BasicInit():        :conf:san

SpectrumComm.InitCalibration():
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
      sleep( <derived from the queried sweep time> x count )
      :READ:CHPower:CHPower?
      (wrapped in a retry loop, channelPowerTriesCount)

startValidate modulator setup:
      top / modulator-config / line
      tx enable / sine off
      symbol-rate <n> / roll-off <n>
      dual-channel-mode single-ch
      -channel-1
      state enable / source test-pattern
      modulation qpsk / frame-zise normal / fec-rate 2/3 / pilot yes

startValidate also reads the DUT's own ADC power as a cross-check:
      -adc-power / get-power     (logged as "adc: <value>")
```

`startValidate`'s link attenuation is FREQUENCY-INTERPOLATED, not constant
(fields: `ifLinkSettings`, `rfLinkSettings`, `startAttn`, `stopAttn`, `ifAttnSlop`, `rfAttnSlop`, `linkAttn`).
Evidence from the reference results file:

```
 50 MHz -> 5.80 dB ... 180 MHz -> 5.89 dB   (IF band)
950 MHz -> 3.37 dB ... 2150 MHz -> 3.59 dB  (L band)
```

The app instead uses flat constants 5.7 / 3.5.

`startValidate` prompts the operator at the IF↔L-band boundary:
`"Moved from IF to L-BAND. Change link settings and press OK."`

**Note — possible measurement-backend ambiguity**: `PowerBaseComm` is an abstract base; `SpectrumComm` is one
implementation. There is also a `powerSensorSettings` file pointing at `192.168.0.49`, implying a power-sensor
backend may exist. It is **not confirmed** which backend produced the reference results file. This is flagged
rather than assumed to be CXA-derived.

---

## 1–2. Divergence-by-divergence assessment

**(a) Sweep time forced (`AUTO OFF` + 0.04 s) vs legacy `AUTO ON` + query + wait**
Plausible contributor to *noise/repeatability*, not to a systematic multi-dB offset. A sweep too fast for the RBW filter to fully charge causes the filter to under-report (amplitude *loss*, not gain) — wrong direction to explain a **+7…+9 dB high** reading. Also has no mechanism to produce a hard frequency threshold (RBW/sweep-time settings are frequency-independent in this app). **Correct fix regardless of the discontinuity**: match legacy — `CHP:SWE:TIME:AUTO ON`, query the coupled value, compute wait from it (same pattern as the flatness `get_sweep_time()` fix already shipped).

**(b) No averaging vs legacy `CHP:AVER ON` + `COUN`**
Averaging reduces *variance*, not *mean bias*, for a steady-state signal. Doesn't explain a consistent +7…+9 dB block-wide offset or a sharp band boundary. Worth adding for parity/repeatability, low expected impact on this specific bug.

**(c) No `INIT:REST` before read; fixed `dwell_s=0.3` vs legacy restart + computed wait**
This **does** plausibly explain the *first-point-of-every-block outlier* flagged in the symptom — same mechanism already root-caused and fixed in `flatness.py`. Mechanistically: `prepare_point()` resends `:FREQ:CENT` on *every* point (even when the value is unchanged within a power sweep at one frequency), but the analyzer only physically re-locks when the value actually changes — i.e., only on the first point of each frequency block. `:READ:CHP:CHP?` is a SCPI `READ:` query, which does implicitly `INIT` + block-until-complete + `FETCH`, so it's *not* fundamentally broken — but nothing guarantees the analyzer's PLL has finished settling **before** that first post-retune `READ:` fires relative to `dwell_s=0.3`. **This explains the outlier-first-point symptom only** — it does not explain why the *steady-state* (already-settled) points 2–7 in the 950–1465 MHz blocks are still ~+9 dB high. Confirm with a fix identical in spirit to the flatness one: explicit `INIT:REST` + computed settle wait before the first read of each new frequency.

**(d) Generic `:BWID` / `:BWID:VID` / `:FREQ:SPAN` vs CHP-scoped `:CHP:BAND` / `:CHP:BAND:VID` / `:CHP:FREQ:SPAN`**
This is a **real architectural bug**, not a style nit. On Keysight X-Series (CXA/EXA/MXA), each Measurement class (Channel Power, ACP, Spectrum, etc.) keeps its **own independent copy** of RBW/VBW/Span/Sweep-Time ("Meas Setup" state is per-measurement, not global instrument state). Once `:CONF:CHP` switches the analyzer into the Channel Power measurement, the generic `:BWID`, `:BWID:VID`, `:FREQ:SPAN` nodes act on the *Spectrum* measurement's state, which is not the active one — they are effectively no-ops for what `:READ:CHP:CHP?` actually integrates over. The app *does* get this right for the one CHP-scoped node it does send (`:CHP:BAND:INT`), but not for RBW/VBW/Span. Net effect: the CHP measurement almost certainly runs with whatever RBW/VBW/Span was left over from `:SYST:PRES`'s auto-coupled CHP defaults — **not** 41 kHz/1 kHz/8 MHz as the operator believes. This is consistent with the legacy tool explicitly using `CHP:BAND`, `CHP:BAND:VID`, `CHP:FREQ:SPAN`. **Fix**: replace the generic nodes with CHP-scoped ones in `power_accuracy.py`'s `analyzer_setup()`/`prepare_point()` (a new `Analyzer` method, e.g. `set_chp_bw()`/`set_chp_span()`, distinct from the existing `set_bw()`/`set_center_span()` used by the swept-SA checks). Cannot fully confirm from code alone whether the *effective* RBW ends up being drastically wrong or just moderately wrong — see the bench diagnostic in §3.

**(e) Ref level 0 dBm, no explicit `POW:ATT`/`CORR:SA:GAIN` handling vs legacy `RLEV 15 dBm` + `POW:ATT:AUTO ON` + `CORR:SA:GAIN 0`**
Two separate issues bundled here:
- Attenuation: the app never calls `set_attenuation()`/`set_attenuation_auto()` for this check at all — it relies on whatever `:SYST:PRES` leaves (auto-coupled to ref level). At `RLEV=0dBm` that auto-coupled attenuation is likely well below the 20 dB the operator used for the manual crosscheck. A lower attenuator setting is not inherently wrong, but *if* there's meaningful external gain ahead of the CXA (see next point) it raises overload/compression risk.
- `apply_ext_gain` is currently `false` in config, so the app **never verifies or pushes** `:CORR:SA:GAIN` — it just assumes "already set on instrument." Two things the app has zero visibility into: (1) whether an **amplitude correction table** (`:CORRECTION:CSET`, a frequency-segmented cal curve — a very standard way to compensate a lab's external LNA/converter/cable response) is loaded and active, and (2) the state of the analyzer's **External Preamp** field the operator explicitly noted at "0.00 dB" during the manual check. Neither `:SYST:PRES` nor the app touches correction tables or the preamp state — by Keysight design, correction data and preamp settings are **not** cleared by preset, precisely because they're meant to persist as calibration data. This means the automated run and the manual crosscheck could easily have been executed under **different, invisible instrument gain-correction/preamp states**, and the app has no code path that would ever detect that.
This is the strongest candidate mechanism for a frequency-*dependent* error: external preamps/LNAs used for L-band satellite test commonly have a hard operating-band boundary or an internal low/high-band switchover, often placed somewhere in the 1–2 GHz region. If such a device (or a segmented correction table compensating one) is in the signal path and its state differs from what the operator's manual check assumed, that would explain both the magnitude and the frequency-selectivity of the discontinuity — but this is app-invisible instrument/hardware state, not a bug fixable in code without first confirming it exists.

**(f) Flat link-attenuation constants vs legacy frequency-interpolated slope**
Real gap, low magnitude: the reference data shows the L-band slope is 3.37→3.59 dB across 950–2150 MHz — a spread of ~0.2 dB. Cannot explain a 7–9 dB error. Worth fixing for general accuracy/parity, but ruled out for this specific bug.

**(g) Minimal modulator setup vs legacy full channel/modulation/FEC/pilot/roll-off setup**
Cannot confidently rule in or out from code alone. The app sends `sine off` + `symbol-rate 4` + `tx enable` and nothing else — no explicit `modulation`, `fec-rate`, `pilot`, `roll-off`, or channel/state configuration. If the DUT falls back to a manufacturing-default or previous-run-inherited modulation/FEC state in the absence of explicit configuration, and if that default's behavior (occupied bandwidth, power leveling accuracy) varies by internal synthesizer sub-band, this could plausibly interact with the CHP-scoping bug (d) — a wrong/uncontrolled integration window matters more or less depending on how wide the actual emitted signal is. This needs operator/DUT documentation to assess (see open questions).

**(h) No DUT ADC power cross-check**
Doesn't explain the CXA-side reading itself, but is a cheap, valuable *diagnostic* — reading the DUT's own reported output power independent of the CXA is the fastest way to determine whether the discontinuity is DUT-side or measurement-side. Worth adding as a permanent diagnostic column, not framed as a fix.

---

## 3. The 1465→1500 MHz discontinuity — plain statement

**None of (a)–(h) provides a software mechanism for a hard threshold at a fixed frequency.** Every one of the app's SCPI/config choices (sweep time, averaging, RBW/span scoping, ref level, attenuation constants, modulator setup) is applied identically across the whole 950–2150 MHz sweep — there is no frequency-conditional logic anywhere in this codebase except the unrelated `if_max_mhz=180` IF/L-band attenuator switch, nowhere near 1465–1500 MHz. A code-only explanation for a sharp step at a specific frequency would have to be invented, not derived, so none is proposed here.

The two most physically coherent candidates are **hardware/instrument-state**, not app-logic:

1. An external preamp/LNA/converter (or a loaded amplitude-correction table compensating one) with a band-switch or operating-range boundary near 1.5 GHz, in a state that differs between the automated run and the manual crosscheck — supported directly by the operator's own note of "External Preamp 0.00 dB" during the manual check, a field the app never touches or verifies.
2. A DUT-internal synthesizer/output-path characteristic (e.g., a sub-band filter or leveling-table boundary) that happens to sit near 1.5 GHz, affecting the *modulated* carrier's actual emitted spectrum differently on each side.

Both are testable without touching code:

- **Diagnostic 1 (isolates the CHP-scoping question, item d):** After running the app's exact `analyzer_setup()`/`prepare_point()` SCPI sequence at a low-band point (e.g. 1400 MHz) and a high-band point (e.g. 1600 MHz), query `:CHP:BAND?`, `:CHP:BAND:VID?`, `:CHP:FREQ:SPAN?`, `:CHP:SWE:TIME?` directly and compare against what the app believes it configured (41 kHz/1 kHz/8 MHz/0.04 s). If they don't match, (d) is confirmed as live and in effect identically at both frequencies — which would argue the discontinuity is *not* purely a (d) artifact (since the misconfiguration would be equally wrong on both sides), redirecting suspicion toward preamp/correction state.
- **Diagnostic 2 (isolates the preamp/correction-table question, item e):** Query `:CORR:SA:GAIN?` (or the front-panel-equivalent preamp/gain node) and list loaded correction tables (`:CORRECTION:CSET:CATalog?` or the front-panel Corrections menu) both before and after the app's `:SYST:PRES`, to confirm whether anything survives preset. Then repeat the manual crosscheck methodology (fixed 20 dB atten, Avg/Hold 10/10, Align off) at a low-band point (e.g. 1400 MHz) *and* a high-band point (e.g. 1600–2000 MHz), forcing the *same* preamp/correction state at both, to see whether the discontinuity persists, shifts, or disappears when hardware state is held constant.
- **Diagnostic 3 (isolates DUT vs measurement, item h):** Read the DUT's own reported/ADC output power at a low-band and a high-band point and compare its flatness independently of the CXA.

---

## 4. Staged plan

**Stage 1 — measurement timing/averaging correctness (a, b, c)**
- Files: `core/analyzer.py` (new `get_chp_sweep_time()`/attenuation-aware helpers as needed), `core/checks/power_accuracy.py` (`analyzer_setup`/`prepare_point`/`measure_point`), `config/config.json` (new keys: `chp_sweep_time_auto`, `chp_average_on`, `chp_average_count`, replacing/supplementing `sweep_time_s`).
- Backward compatibility: keep `sweep_time_s` as a fallback default when `chp_sweep_time_auto=false`, same pattern used for flatness's `enable_peak_table_logging`.
- Risk: **Low** — same well-understood, already-proven mechanism as the flatness fix.
- Verification: rerun the full 304-point sweep; confirm the first-point-of-block outliers disappear (950 MHz: first point should land near the block's other values, not diverge by several dB).

**Stage 2 — correct SCPI node scoping + ref-level/attenuation parity (d, e)**
- Files: `core/analyzer.py` (add CHP-scoped setters, e.g. `set_chp_bw()`, `set_chp_span()`, keep the generic `set_bw()`/`set_center_span()` for the swept-SA checks untouched), `core/checks/power_accuracy.py`, `config/config.json` (possibly `ref_level_dbm` raised toward legacy's 15 dBm, explicit `atten_db`/`atten_auto` keys).
- Backward compatibility: additive, other checks unaffected since they use the swept-SA (`:CONF:SAN`) measurement where the generic nodes are already correct.
- Risk: **Medium** — this is the highest-expected-impact stage (manual crosscheck with correctly-scoped, well-attenuated settings gave the right answer), but the corrected effect size can't be predicted without the bench diagnostics above; also the resolved RBW/atten values need to be re-validated against the tolerance budget.
- Verification: rerun Diagnostic 1 first to confirm the actual effective RBW/span before vs after the fix; then rerun the full sweep and check whether the systematic block-level (not just first-point) error in 950–1465 MHz shrinks or disappears.

**Stage 3 — modulator setup parity (g)**
- Files: `core/checks/power_accuracy.py::modulator_setup()`, possibly `core/checks/base.py` if a shared "full channel setup" helper is warranted, `config/config.json` (new keys: `roll_off`, `modulation`, `fec_rate`, `pilot`, `frame_size`, `dual_channel_mode`).
- Backward compatibility: additive; needs DUT CLI syntax confirmation from the operator/NovelSat docs before implementing (see open questions).
- Risk: **Medium** — behavior change to DUT signal generation, should be bench-verified independently of the CXA-side fixes (Stages 1–2) so any effect is attributable.
- Verification: with Stages 1–2 in place, toggle the new modulator setup on/off and confirm whether it changes the residual error, if any remains.

**Stage 4 — attenuation model + ADC cross-check (f, h)**
- Files: `core/checks/power_accuracy.py::_atten()` (interpolated slope instead of flat constant), `core/modulator.py`/`base.py` (ADC power read helper), `config/config.json` (new keys: `if_atten_start_db`, `if_atten_stop_db`, `lband_atten_start_db`, `lband_atten_stop_db`, or a small lookup table), new CSV column `ADC_Power_dBm`.
- Backward compatibility: additive; falls back to the existing flat constants if new keys absent.
- Risk: **Low** — small numeric correction (~0.2 dB per the reference data) plus a pure-diagnostic addition, no behavior-changing risk to the pass/fail logic.
- Verification: confirm interpolated values match the reference results file at the quoted anchor frequencies; confirm ADC readback correlates sensibly with CXA readings on a known-good run.

---

## 5. Open questions before Stage 1

1. **Measurement backend ambiguity (unresolved):** was the legacy reference results file produced via `SpectrumComm` (CXA) or the power-sensor backend at `192.168.0.49`? If it's power-sensor-derived, the legacy SCPI sequence compared against above may not be the one that actually produced the "known-good" numbers, and some of the analysis (RBW/span/CHP-scoping relevance) would need re-scoping around whatever backend actually generated the reference data.
2. **Preamp/correction-table state:** what's currently loaded/active on the CXA (`:CORR:SA:GAIN?`, `:CORRECTION:CSET:CATalog?`, preamp on/off)? Was this state the same during the automated 13:11–13:28 run and the manual crosscheck, or could it have changed between them (e.g., operator touched the front panel between the two)?
3. **RF path composition:** is there any external LNA, converter, or gain block between the DUT and the CXA (beyond the passive link attenuator already modeled in config), and if so, does it have a documented band-switch or operating-range boundary anywhere near 1.5 GHz?
4. **DUT modulation defaults:** what modulation/FEC/pilot/roll-off state does the DUT actually run in when the app's `modulator_setup()` sends only `sine off` / `symbol-rate 4` / `tx enable` — does it inherit state from the previous check, or fall back to a manufacturer default? Is that default frequency-band-dependent?
5. Run Diagnostics 1–3 above (or authorize drafting exact SCPI/CLI command sequences for the operator to run manually) before Stage 1 implementation starts, so Stage 2's design targets the confirmed root cause rather than the most-likely one.
