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
