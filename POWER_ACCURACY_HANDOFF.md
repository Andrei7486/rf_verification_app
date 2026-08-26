# Power Accuracy — Legacy Reference and Parity Handoff

Status: **reconstructed 2026-08-26**
Repo: `Andrei7486/rf_verification_app`
Referenced by: `CLAUDE.md`, `docs/VALIDATION_APP_SPEC.md` §7

> **Provenance warning.** The original file was lost. This document was reconstructed from the
> session records of the parity work. The legacy SCPI and DUT sequences below were extracted from
> the decompiled Java class files via `strings` (no `javap` was available), so they are a **string
> pool reading**, not a decompiled control flow. Where that distinction matters it is stated
> inline. Decisions D1–D5 are restated verbatim in intent and remain binding.
>
> If the original file resurfaces, it supersedes this one and this reconstruction is deleted.

---

## 1. What this document is for

The legacy Java tool `NsPowerCalibration` is the **known-good reference**. Where the app disagrees
with it, the app is wrong. This file records what the legacy tool actually does, so that parity
work argues from the reference rather than from the current code.

It covers Power Accuracy only. IQ Validation parity is specified in `docs/VALIDATION_APP_SPEC.md`
M2 and is blocked on the IQ `.class` files (P0.6).

---

## 2. Legacy source files

| File | Role |
|---|---|
| `SpectrumComm.class` | All CXA / SCPI traffic |
| `startValidate.class` | The validation run — modulator setup, point loop, operator prompts |
| `ModComm.class` | Modulator CLI traffic |
| `exaSettings.txt` | Analyzer settings (values **not** ported — see D1) |
| `modSettings.txt` | Modulator settings (values **not** ported except as noted) |
| `powerSensorSettings` | Unused — see §6 |

---

## 3. Legacy analyzer sequence

### 3.1 Validation path — what `startValidate` actually calls

`startValidate` calls **`BasicInit`** then **`InitValidation`**. It does **not** call
`InitCalibration` — that belongs to `startCalibrate`. This distinction is load-bearing; the parity
plan got it wrong once and had to be corrected.

```
SpectrumComm.BasicInit():
      :conf:san

SpectrumComm.InitValidation():
      CONF:CHP
      CHP:BAND:INT <n> MHz
      CHP:FREQ:SPAN <span>
      CHP:BAND:AUTO ON
      CHP:BAND <rbw> HZ
      CHP:BAND:VID:AUTO ON
      CHP:BAND:VID <vbw>
      CHP:SWE:TIME:AUTO ON        <-- sweep time left on AUTO
      CHP:SWE:TIME?               <-- queried, parsed (ParseSweep), used to compute the wait
      CHP:AVER ON
      CHP:AVER:COUN <averageCount>

SpectrumComm.SetFreq():
      FREQ:CENT <freq>

SpectrumComm.GetValidationPower():
      INIT:REST
      sleep( <derived from the queried sweep time> x count )
      :READ:CHPower:CHPower?
      wrapped in a retry loop (channelPowerTriesCount)
```

**Note on `CHP:AVER 10`.** The decompiled string pool contains a bare `CHP:AVER 10` line. This is a
decompilation artifact: `:AVER` takes only a boolean on X-Series, and the adjacent `CHP:AVER:COUN `
literal carries a trailing space (a StringBuilder template). Not replicated. Decision confirmed.

### 3.2 Calibration path — NOT part of validation

```
SpectrumComm.InitCalibration():
      :SYS:PRES
      FREQ:SPAN <span> Hz
      BAND <rbw>
      BAND:VID <vbw>
      SWE:TIME <sweep>
      POW:ATT:AUTO ON
      CORR:SA:GAIN 0
      DISP:WIND:TRAC:Y:RLEV 15 dBm
```

`RLEV 15 dBm`, `POW:ATT:AUTO ON` and `CORR:SA:GAIN 0` belong **here**, not to validation. The
`CORR:SA:GAIN 0` line is why P0.2 exists: `InitCalibration` pushes `0` per the string pool, and this
must be confirmed empirically off the front panel, because the app now pushes its own per-check
value.

### 3.3 The scoping defect this exposed

On Keysight X-Series each measurement class holds its own copy of bandwidth, span and sweep time.
The app used the **generic** nodes (`:BWID`, `:BWID:VID`, `:FREQ:SPAN`) after `:CONF:CHP`, so they
acted on the Spectrum measurement while the Channel Power measurement kept its own values. Confirmed
on the bench: the CXA front panel showed values completely different from what the app believed it
had set. The legacy tool uses the **CHP-scoped** nodes throughout.

This was the root cause of the up-to-+9 dB deviation in the 950–1465 MHz range with near-zero
deviation above 1500 MHz.

---

## 4. Legacy modulator sequence

### 4.1 Setup — once, before the point loop

```
top / modulator-config / line
tx enable / sine off
symbol-rate <n> / roll-off <n>
dual-channel-mode single-ch
-channel-1
state enable / source test-pattern
modulation qpsk / frame-zise normal / fec-rate 2/3 / pilot yes
```

(`frame-zise` is the legacy tool's own typo, preserved here as found in the string pool. The app
uses the correct `frame-size`.)

Legacy does **not** set Output Level Mode explicitly — it relies on inherited unit state. We diverge
deliberately: see D4.

### 4.2 Per point

```
power <n>
FREQ:CENT <freq>        (analyzer; only when the frequency changes)
INIT:REST
sleep(...)
:READ:CHPower:CHPower?
```

That is the whole per-point cost. **One modulator command per point.** This is the reference against
which the S-M0 overhead work (spec M7) is measured.

### 4.3 DUT ADC cross-check

```
-adc-power / get-power        (logged as "adc: <value>")
```

Present in `startValidate`. The string pool does not establish **how often** it runs — per point,
per frequency, or once. Our app ran it per point, which cost 7.05 s per point including the
navigation back into `-line-`. Gated off by default under M7 (`enable_adc_power_check = false`).

### 4.4 Link attenuation — frequency-interpolated, not constant

Legacy fields: `ifLinkSettings`, `rfLinkSettings`, `startAttn`, `stopAttn`, `ifAttnSlop`,
`rfAttnSlop`, `linkAttn`.

Anchors from the reference results file:

```
IF band:   50 MHz -> 5.80 dB  ...  180 MHz -> 5.89 dB
L band:   950 MHz -> 3.37 dB  ...  2150 MHz -> 3.59 dB
```

The app uses flat constants `if_atten_db = 5.7` / `lband_atten_db = 3.5`. **This is a known,
unclosed divergence.** It is worth at most ~0.1–0.2 dB across a band and has not been raised as a
requirement. Recorded here so it is not rediscovered as a surprise.

### 4.5 IF ↔ L-band operator prompt

```
"Moved from IF to L-BAND. Change link settings and press OK."
"Moved from L-BAND to IF. Change link settings and press OK."
```

The app already has an equivalent cable-switch pause in `session.py::_auto_loop()`. **Already at
parity — verified by reading the code. Do not duplicate.**

---

## 5. Legacy settings files — reference only

```
exaSettings.txt : 192.168.0.5 / 500000 / 10000 / 1000 / 0.04 / 10 / 0.5
modSettings.txt : 192.168.0.50 / "0,-30,2" / 0.5
```

Mapping: analyzer IP, span, RBW, VBW, sweep time, average count, delay; modulator IP, power sweep
`from,to,step`, delay.

Only the average count `10` is taken (D2). The trailing `0.5` in `modSettings.txt` is the legacy
per-command modulator delay and is the derivation of `power_accuracy.dut_settle_after_power_s = 0.5`
introduced by M7.

---

## 6. Resolved — do not reopen

**Measurement backend.** The reference results file was produced via `SpectrumComm` (the CXA), not
the power sensor. Confirmed by file dates: `exaSettings` modified 21-Jul-2026, reference results
file 22-Jul-2026, `powerSensorSettings` untouched since 25-Mar-2019.

**DUT state inheritance.** Confirmed empirically. With the app sending only
`sine off / symbol-rate 4 / tx enable`, the unit was observed carrying: Line Mode NS4, Roll Off
0.25, Dual Channel Mode single, Spectrum Invert OFF, NS4 NLC OFF, Output Level Mode Constant-Power.
The DUT inherits state from the previous session rather than falling back to a documented default.
This is why D4 exists.

---

## 7. Decisions D1–D5 — binding

| # | Decision | Rationale |
|---|---|---|
| **D1** | Legacy `exaSettings` / `modSettings` **numbers** are not ported. We port the legacy **method**. | The legacy numbers were tuned for a different link and a different unit population. The sequence, the scoping and the timing model are what make the measurement correct. |
| **D2** | Only `chp_average_count = 10` is taken from the legacy settings. | It is part of the timing model, not an arbitrary tuning value: the post-`INIT:REST` wait is derived from sweep time × count. |
| **D3** | Retry on transport/SCPI **exception only**, small capped count. No value-sanity retry. | A value-sanity retry silently hides a real measurement fault and makes runs non-reproducible. |
| **D4** | Output Level Mode is set explicitly in `modulator_setup()`, default ON. | Determinism over literal parity. The DUT demonstrably carries state across sessions (§6), so relying on inheritance as legacy does would make results depend on whoever used the unit last. |
| **D5** | External gain is a **per-check override**; the global `apply_ext_gain` flag is not flipped. | `iq_validation` runs at −3.5 dB and must not shift when Power Accuracy runs. Flipping a global to make one check work is a blast-radius violation. |

**Correction on record.** The bench-report claim that `ext_gain_db = 0` is correct for all three
checks in validation mode is **unsupported and contradicts D5**. It was inferred from the config
file and presented as a decision; it was never decided. `iq_validation` runs at −3.5 dB. Recorded so
it is not repeated.

---

## 8. Parity work already merged

| Stage | Content | PR |
|---|---|---|
| 1 | CHP-scoped SCPI nodes replacing the generic ones | #5 |
| 2 | Timing model — sweep time AUTO, queried, `INIT:REST` + computed wait, averaging | #6 |
| 3 | `POW:ATT:AUTO ON` / `CORR:SA:GAIN` as a deterministic baseline init; `ref_level_dbm` **not** changed to 15 | #10 |
| 4–5 | Remaining parity items | #10 |
| — | `CORR:SA:GAIN` pushed per-check with read-back, global flag untouched (D5) | #13 |

Config fix applied along the way: `chp_integ_bw_hz` 8 000 000 → 5 000 000. The correct value is the
occupied bandwidth, symbol rate × (1 + roll-off) = 4 MSPS × 1.25 = 5 MHz. The 8 MHz on the bench was
span, not integration bandwidth. This was the first confirmed instance of bench config drift.

---

## 9. Open items carried forward

| Item | Where it now lives |
|---|---|
| First-point-of-block settling artifact | spec M3 / stage S9 |
| Power Accuracy run time | spec M4 / stages S8, S10; and spec M7 / stage S-M0 |
| Unexplained 5–6 dB level difference vs the 25-08 reference run | spec M6 / stage S1 — hypothesis is bench config drift, **recorded as a hypothesis, not a conclusion** |
| The distinguishing ext-gain leak test (PA at 0 → Flatness at −3.5 in sequence) was never run | PR #13 was verified only by the outgoing command in the log. A null-valued test (§7.4 of the rules) |
| Frequency-interpolated link attenuation vs our flat constants | §4.4 above — not raised as a requirement |
| Repeatable intra-block IF shape dipping at `Set_dBm` −5/−10 | spec §6 non-goals — flagged, not chased |
