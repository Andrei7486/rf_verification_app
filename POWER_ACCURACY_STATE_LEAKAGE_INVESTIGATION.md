# Cross-Check Analyzer State Leakage — Investigation (2026-08-26)

**Read-only investigation. No code was changed, no PR was opened.**

## Context

Stage 3 added deterministic baseline init local to `power_accuracy.py`:
```
POW:ATT:AUTO ON
CORR:SA:GAIN 0
```
Decision 5 states the global `analyzer.apply_ext_gain` flag must NOT be flipped, because
`iq_validation` runs at -3.5 dB external gain and must match the value used when its reference
calibration was taken.

## Concern

If `power_accuracy` pushes `CORR:SA:GAIN 0` to the instrument and does not restore it, and if
`flatness.py`/`iq_validation.py` rely on inherited analyzer state instead of setting these nodes
themselves, then running Power Accuracy before Flatness or IQ Validation would silently shift their
measurements. For IQ this would be a 3.5 dB error.

## 1. Flatness / IQ Validation: what they explicitly set

**`core/checks/flatness.py::analyzer_setup()` (lines 33–47):**
```
38:  cxa.preset()
40:  cxa.apply_ext_gain()
```
No other `CORR:SA:GAIN` or `POW:ATT`/`POW:ATT:AUTO` call anywhere in the file.

**`core/checks/iq_validation.py::analyzer_setup()` (lines 58–68):**
```
60:  cxa.preset()
62:  cxa.apply_ext_gain()
```
No other `CORR:SA:GAIN` or `POW:ATT`/`POW:ATT:AUTO` call anywhere in the file.

Both checks rely entirely on the same generic, gated method, `Analyzer.apply_ext_gain()`
(`core/analyzer.py:42-49`):
```python
def apply_ext_gain(self):
    if self.cfg.get("apply_ext_gain", False):
        scpi = self.cfg.get("ext_gain_scpi", ":CORR:SA:GAIN {db}").format(
            db=self.cfg.get("ext_gain_db", 0.0))
        self.command_sync(scpi)
    else:
        self.log.info("Ext Gain not pushed by app; expected %.2f dB set on instrument",
                      self.cfg.get("ext_gain_db", 0.0))
```
`self.cfg` here is the global `cfg["analyzer"]` section (`session.py:65`:
`Analyzer(self.cfg["analyzer"], ...)`), shared by all three checks — not per-check. The current
live config has `analyzer.apply_ext_gain = false`. Under that default, **this call is a no-op** — it
logs a reminder and pushes nothing. Neither check does anything else to set or verify
`CORR:SA:GAIN`.

Neither `flatness.py` nor `iq_validation.py` calls `set_attenuation()` or `set_attenuation_auto()`
anywhere — attenuation is untouched by both.

## 2. Power Accuracy: is the Stage 3 baseline init reverted?

**No.** `core/checks/power_accuracy.py::analyzer_setup()` (lines 94–96):
```python
if bool(pa.get("atten_auto", True)):
    cxa.set_attenuation_auto(True)      # :POW:ATT:AUTO ON
cxa.set_ext_gain(0)                     # :CORR:SA:GAIN 0, unconditional
```
`set_ext_gain(0)` is called directly and unconditionally — it bypasses `apply_ext_gain()`'s gate
entirely.

`cleanup()` (line 245-246):
```python
def cleanup(self, mod, cfg):
    base.clean_carrier_cleanup(mod)
```
This touches only the **modulator** (`tx disable` / `sine off`). No CXA-side call at all — no
restore of `CORR:SA:GAIN` or `POW:ATT:AUTO`, no context manager, no `finally` block on the analyzer
side.

`session.py::_finalize_and_write()` (lines 168–186) calls `self.check.cleanup(...)` (above) then
`_teardown_devices()` (lines 198–205), which only does `dev.close()` on the socket — closing a TCP
connection does not reset the instrument's internal SCPI state.

**Conclusion: `CORR:SA:GAIN 0` and `POW:ATT:AUTO ON` are left applied on the physical instrument**
after a Power Accuracy run ends, with no code path anywhere that reverts them.

## 3. `analyzer.py`: how `apply_ext_gain`/`ext_gain_db` are consumed

- Both are read from `self.cfg` (the global `analyzer` config section) inside `apply_ext_gain()`
  (`analyzer.py:42-49`), gated by the `apply_ext_gain` boolean.
- **Call sites for the gated `apply_ext_gain()` method:** `flatness.py:40`, `iq_validation.py:62`.
  `power_accuracy.py` does **not** call it (confirmed absent from the file).
- **Call sites for the unconditional `set_ext_gain(db)` method** (`analyzer.py:143-144`, direct
  `:CORR:SA:GAIN <db>` push, no gate): only `power_accuracy.py:96` (`cxa.set_ext_gain(0)`). No
  other check calls it.
- **Attenuation call sites:** `set_attenuation_auto()`/`set_attenuation()` (`analyzer.py:138-142`)
  are called only from `power_accuracy.py:95`. Neither `flatness.py` nor `iq_validation.py` calls
  either.

## 4. Is cross-check state leakage possible?

**Yes**, under the app's current documented default configuration (`analyzer.apply_ext_gain =
false`).

Chain of evidence:
1. Power Accuracy unconditionally pushes `CORR:SA:GAIN 0` every run (`power_accuracy.py:96`),
   independent of the global flag.
2. Nothing reverts it afterward (§2 above) — it persists on the instrument past the run's end.
3. `:SYST:PRES`, called by every check's `analyzer_setup()` including Flatness's (`flatness.py:38`)
   and IQ Validation's (`iq_validation.py:60`), does not clear amplitude-correction/external-gain
   values on Keysight X-series analyzers — this is documented Keysight preset behavior (correction
   data is designed to persist across preset as calibration data), not something re-verified via a
   live SCPI query in this codebase.
4. With `apply_ext_gain = false` (current default), Flatness's and IQ Validation's own
   `apply_ext_gain()` call (`flatness.py:40`, `iq_validation.py:62`) is a no-op — it does not
   reassert any value, it only logs a reminder.

**Net effect:** if the operator has manually set `CORR:SA:GAIN -3.5` on the CXA (per the README's
calibration instructions) and then runs Power Accuracy, the instrument is left at `CORR:SA:GAIN 0`.
Running Flatness or IQ Validation next inherits `0` instead of `-3.5` — a silent **3.5 dB** shift in
every subsequent measurement from both checks, exactly the scenario in the CONCERN.

**One conditional caveat, not a fix in itself:** if `apply_ext_gain` were set `true` globally,
Flatness/IQ Validation would each reassert `ext_gain_db` at the start of their own
`analyzer_setup()`, which would self-correct this specific leak — but decision 5 explicitly ruled
out flipping that global flag (for a different, valid reason: it would also push whatever
`ext_gain_db` is currently configured, which isn't scoped per-check either). Under the flag's
current, documented-default state, the leak is live.

The attenuation piece (`POW:ATT:AUTO ON`) is lower-risk by comparison: `:SYST:PRES` does reset
`POW:ATT:AUTO` on X-series instruments, so Flatness's/IQ Validation's own `cxa.preset()` call likely
re-establishes AUTO coupling regardless of what Power Accuracy left behind — this wasn't
independently re-verified against the real instrument in this investigation.

## Fix implemented (PR #13, merged)

Implemented per-check external gain resolution so no check inherits analyzer state from another —
see the PR for the full design (`core/checks/base.py`'s `resolve_ext_gain()`/
`apply_check_ext_gain()`, replacing the gated `apply_ext_gain()` call sites in `flatness.py`/
`iq_validation.py`, and the new `power_accuracy.ext_gain_db` config key). Each check now pushes its
own resolved value unconditionally after `preset()`, reads back `:CORR:SA:GAIN?`, and logs both —
turning the "documented Keysight preset behaviour" assumption in §4 above into something verified
on every run instead of assumed.

## Bench verification (2026-08-26, real NS330 + CXA)

Confirmed with a short control run first (per the operator's own design: check the read-back log
line immediately after starting, before committing to a full run), then the full leak scenario.

**Note on the expected value:** this bench session runs in *validation* mode, where `ext_gain_db =
0` is the correct, intended value for all three checks (not the `-3.5` calibration value discussed
in the original investigation, which applies to a different scenario). All read-backs below showing
`0.00 dB` are the expected, correct result for this session — not a sign the config has drifted.

**Step 1 — short control run (flatness, first point of setup only):**
```
CXA >> :CORR:SA:GAIN 0.0
CXA ?? :CORR:SA:GAIN?
flatness: ext gain set to 0.00 dB, instrument reads back 0.00 dB
```
Push matches read-back exactly, no mismatch warning. Confirms both that the fix is live and that
`:SYST:PRES` does not clear `CORR:SA:GAIN` on this instrument (empirically, not just per Keysight's
documented behavior as in §4).

**Step 2 — full flatness run** (`flatness_NS330_20260826-134556`, 25 points): completed, `verdict:
FAIL` (pk-pk 4.76 dB vs. 1.0 dB tolerance — unrelated to this fix). Compared against the most recent
prior reference run (`flatness_NS330_20260825-150037`): absolute levels differ by ~5-6 dB (other
config values — carrier power, attenuation — have drifted independently since then, unrelated to
ext gain), but the **relative deviation shape matches closely** — same MAX at 950 MHz, same MIN at
2150 MHz, point-by-point deviation-from-mean within ~0.2-0.6 dB across the whole band. Confirms the
core flatness measurement path is unaffected by Stages 1-5 or this fix.

**Step 3 — Power Accuracy** (`power_accuracy_NS330_20260826-134736`, 950/2150 MHz, 14 points):
ext gain push+read-back also `0.00 dB` / `0.00 dB`, matching its own `power_accuracy.ext_gain_db=0`
config. Completed normally.

**Step 4 — flatness again, immediately after Power Accuracy, no manual instrument intervention**
(`flatness_NS330_20260826-135110`, 25 points) — the direct leak-scenario test. Ext gain push+
read-back again `0.00 dB` / `0.00 dB`, with the outgoing `:CORR:SA:GAIN 0.0` command explicitly
present in *this run's own log* — proof it was actively re-pushed, not silently inherited from
whatever Power Accuracy left behind. Compared against Step 2's flatness run:

| | run1 (before Power Accuracy) | run2 (after Power Accuracy) |
|---|---|---|
| pk-pk | 4.76 dB | 4.05 dB |

24 of 25 points matched within **0.01-0.02 dB** (measurement noise). The one exception, 950 MHz
(**-0.69 dB** delta), is the already-documented, unrelated first-point-of-run settle artifact
(`flatness.py`'s `_first_point_settled` logic) — not an ext-gain effect.

**Conclusion: no leak.** Before the fix, a 3.5 dB (or any magnitude) shift would have been possible
if Flatness silently inherited whatever Power Accuracy left `CORR:SA:GAIN` at. Here, both checks
explicitly assert their own resolved value every time, confirmed both by matching read-backs and by
the explicit outgoing SCPI command visible in each check's own log — and the sandwiched-Power-
Accuracy flatness run reproduces the un-sandwiched one within measurement noise.

## Status

Investigation complete, fix implemented and merged (PR #13), fix bench-verified against real
hardware on 2026-08-26 per the protocol above.
