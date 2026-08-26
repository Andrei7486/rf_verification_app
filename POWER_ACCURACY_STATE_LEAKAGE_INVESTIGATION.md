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

## Status

No code changed, no tests run, no PR opened — this was a read-only investigation per the request.
