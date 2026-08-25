# CHANGELOG — RF Verification (update)

Extract this zip OVER the existing `rf_verification_app` folder on the station.
It contains ONLY the files that changed — your `python\`, `results\`, `config\freq_lists\`
and the unchanged core modules are left untouched. `config\config.json` IS replaced —
re-check your tuned values in Settings after updating.

## analyzer.py
- Fixed the two bugs behind the 15 s pauses: `*OPC?` (was `OPC?`) and `\n` (was `/n`).
- Channel Power via `:READ:CHP:CHP?` (triggers a fresh measurement, no settle sleep).
- Markers forced to POSition + couple-off (fixes IQ Image/LOFT reading 0).
- Added preset(), enable_peak_table(), read_chp().

## power_accuracy.py
- Multi-frequency: walks the operator's list; steps power start→stop at each frequency.
- Attenuator compensation added to the measured value (IF ≤ if_max_mhz → if_atten_db,
  else lband_atten_db).
- CW off (modulated), symbol-rate 4, Channel Power mode, preset before setup.

## flatness.py
- Fixed frequencies 950–2150/50 for every unit (no picker).
- L-band attenuator (3 dB) added to each level; on-screen Peak Table enabled; preset.

## iq_validation.py
- Preset before setup; marker fix makes Image/LOFT correct and fast.
- Measurement sequence realigned with the legacy StartValidation tool:
  peak search -> delta marker -> LOFT at loft_offset_hz -> analyzer re-centred to
  F - image_center_shift_hz -> IMAGE at image_offset_hz.
- Write trace instead of MAX HOLD (use_max_hold = true restores the old behaviour).
- Main CW guard: below main_cw_min_dbm the point is rejected (or the run aborted).
- Reference level follows the first measured peak (auto_ref_level_from_peak).
- Separate loft_limit_dbc / image_limit_dbc, both falling back to iq_spur_limit_dbc.
- DAC phase / LOFT corrections read from the DUT and written to the CSV.

## config.json — new iq_validation fields
- image_offset_hz -2000000, image_center_shift_hz 1000000, loft_offset_hz -1000000
- main_cw_min_dbm -20, main_cw_low_action "fail"
- peak_freq_tolerance_hz 200000, peak_frequency_mismatch_action "warning"
- auto_ref_level_from_peak true, ref_level_margin_db 1,
  ref_level_peak_min_dbm -12, ref_level_peak_max_dbm 10, ref_level_peak_retries 3
- loft_limit_dbc -55, image_limit_dbc -55, use_max_hold false, use_legacy_nav true,
  read_corrections true

## session.py / app.py / index.html / app.js
- Auto mode runs the whole list by itself (no Measure/Next/Skip).
- Pauses to ask for the RF cable switch on the IF↔L-band boundary; Continue resumes.
- Manual mode unchanged. Live log panel in the UI; results update live.

## settings.html / settings.js / style.css
- Collapsible sections; sticky Save button; connection type is a dropdown (telnet/serial).

## config.json — new fields
- flatness.lband_atten_db = 3
- power_accuracy: if_atten_db 5.7, lband_atten_db 3, if_max_mhz 180, sweep_time_s 0.04,
  chp_integ_bw_hz 5000000
