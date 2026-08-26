# Power Accuracy — Full Bench Test Summary (2026-08-26)

Log: `results/power_accuracy_NS330_20260826-115748.log`
Run: 175 points (25 L-band frequencies × 7 power steps, `NS330.txt`, 950–2150 MHz), unit connected
to L-Band cable, real Keysight CXA N9000B + NovelSat NS330 modulator.

## Both bug fixes held up perfectly across the entire run

Zero `"command not found"` errors in all 175 points — the `-channel-1` and `-adc-power-`
menu-stranding fixes (see PR #10 / `POWER_ACCURACY_PARITY_PLAN.md`'s "Bench verification" section)
are solid, not just for the earlier 14-point check.

## The result is FAIL — expected, per the operator's note about calibration

0/175 PASS against the ±0.8 dB tolerance. Given the unit isn't calibrated, that's the expected
outcome, not a bug.

## The interesting part: the original discontinuity looks gone

Isolating steady-state deviation (excluding each block's first point) across the whole L-band
sweep:

| Freq (MHz) | 950 | 1250 | 1450 | 1500 | 1850 | 2150 |
|---|---|---|---|---|---|---|
| Steady-state dev (dB) | 9.44 | 8.17 | 7.68 | 7.22 | 6.04 | 5.25 |

This declines smoothly and gradually across the entire band — the largest single 50 MHz step is
only ~0.8 dB, and there's nothing anomalous at all near 1465→1500 MHz specifically, where the
original investigation (`POWER_ACCURACY_INVESTIGATION.md`) found a sharp jump from +9 dB down to
~0 dB. That discontinuity doesn't appear anymore. What's left instead looks like a normal,
uncalibrated-unit style smooth offset/slope — consistent with the operator's comment about
calibration, not a separate hardware/software bug.

Not claiming Stages 1–5 fixed that discontinuity — too many things changed at once (CHP scoping,
timing, baseline init, and the two navigation bugs fixed the same day) to isolate which one
mattered. But it's a striking before/after, worth recording.

## One new thing worth flagging, not fixed yet

The first point of each frequency block increasingly diverges from the rest of its block as
frequency rises — mild at 950 MHz, but by 2150 MHz the first point reads **-16.3 dB** deviation
while the rest of that same block sits around **+5.3 dB**. This is a frequency-retune settling
effect, distinct from the two bugs fixed on 2026-08-26. Flagged here as an open observation, not
acted on.

## Status at end of session

App and hardware connection both cleaned up (process stopped, no live connection left open). PR #10
(the two menu-navigation fixes) was open, unmerged, at the time of this run.
