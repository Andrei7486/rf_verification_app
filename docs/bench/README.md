# Bench logs

Archived run logs referenced by the roadmap, journal or an ADR. Each entry below states what the
log is a baseline for and any caveat on the numbers in it.

---

## `power_accuracy_freqs_20260826-153750.{log,csv,json}`

**S-M0 pre-optimisation baseline** (spec §M7, journal 2026-08-26). 50 MHz / 0..−30 dBm / step 2
(16-point block), part of a larger 432-point sweep.

- **Operator-aborted at point ~18 of 432**, not crashed — the log ends cleanly with
  `Verdict: PASS` and normal cleanup (`tx disable`, `sine off`).
- **Unit calibration state at capture time was pre-P0.1** (`NsPowerCalibrationV6.2.jar` had not
  yet been run). Absolute `Actual_dBm` values in this log are **not** representative of a
  calibrated unit and must not be used to judge measurement accuracy on their own.
- What this log *is* used for: per-point timing structure (the ~13.4 s/point overhead
  breakdown) and the Point 1 → Point 16 `Measured:` elapsed time (219.141 s), both of which are
  timing/sequencing facts independent of calibration state.
- Point-by-point `Actual_dBm` values from this same log remain the basis for S-M0 acceptance
  criterion 3 (parity within 0.1 dB against the optimised run) — parity there means "the
  optimised code reproduces what the unoptimised code reported", not "the values are absolutely
  correct".

---

## `power_accuracy_NS330_20260827-130957_serial-runA.{log,csv,json}` and
## `power_accuracy_NS330_20260827-131303_serial-runB.{log,csv,json}`

**S-M0 partial bench test, run over `SerialModulator` (COM5), not `TelnetModulator`** — the
telnet path was unreachable at the time (unrelated station configuration issue, per the operator).
Same-session A/B per spec §M7 criterion 3, 50 MHz / 0..−30 dBm / step 2 (16 points):

- Run A (`...130957`, `13:10:13`–`13:12:10`): `enable_adc_power_check=true`,
  `use_prompt_read=false`. Verdict PASS.
- Run B (`...131303`, `13:13:19`–`13:14:13`): `enable_adc_power_check=false`,
  `use_prompt_read=true`. Verdict PASS. Max point-by-point `|A−B|` = 0.07 dB.

**Operator-unconfirmed at the time it was run** — recorded here as what happened and what the
files show, not as an operator-witnessed bench acceptance. `use_prompt_read` has no effect on
`SerialModulator` (it only branches `TelnetModulator._read_until_prompt()`), so this run bears on
items 1 and 2 only — it does **not** exercise item 3 (the prompt-based read) and does not close
criterion 3's telnet case. See `docs/JOURNAL.md` 2026-08-27 and 2026-09-07.
