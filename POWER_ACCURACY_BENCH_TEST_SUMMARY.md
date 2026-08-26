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

## IF-band run (2026-08-26, same day, cable moved to IF)

Log: `results/power_accuracy_NS330_20260826-125507.log`
Run: 49 points (7 IF frequencies × 7 power steps: 70/90/100/120/140/145/180 MHz), unit connected to
the IF cable with a 5.7 dB attenuator (matching `power_accuracy.if_atten_db` already in config, no
change needed).

**Navigation fix holds here too**: zero `command not found` across all 49 points.

**Results are tight — much closer than L-band, still FAIL on tolerance.** Deviation across the
entire IF band is remarkably flat and consistent: ~1.4 to ~3.0 dB, with almost no frequency
dependence (steady-state mean 2.56 dB at 70 MHz vs. 2.34 dB at 180 MHz — essentially flat, unlike
L-band's smooth 9.4→5.3 dB slope). All 49 points still FAIL against the ±0.8 dB tolerance, but the
spread is much smaller than what L-band showed.

**No first-point-of-block outlier here.** Unlike the L-band run (where the artifact reached
-16.3 dB at 2150 MHz), every IF frequency's first point lands right in line with the rest of its
block. That settling issue appears specific to L-band, more pronounced at higher frequencies — this
IF data supports that (it's absent at 70-180 MHz, present and growing from ~1900 MHz up).

**One consistent, repeatable pattern worth noting.** Within every single frequency block, deviation
dips to its lowest (~1.4-2.0 dB) at `Set_dBm` = -5/-10, then climbs to ~2.5-3.0 dB from -15 down to
-30. This exact shape repeats at all 7 frequencies — looks like a real, systematic characteristic
(likely a small non-linearity in the DUT's IF-band level control), not noise. Flagged, not chased -
consistent with the operator's calibration note.

## Status at end of session

App and hardware connection cleaned up after both runs (process stopped each time, no live
connection left open). PR #10 (the two menu-navigation fixes) and PR #11 (this document's initial
version) are both merged.
