# Changelog

One entry per tagged, bench-accepted release. Newest first.
Format: `## <tag> — <date> — <stage ID>: <title>` followed by what changed, what did not, and the
bench acceptance that closed it.

---

## Unreleased

- `docs/VALIDATION_APP_SPEC.md`, `docs/DEVELOPMENT_RULES.md`, `docs/ROADMAP.md` added as the
  project's source of truth for scope, process and ordering.
- `CLAUDE.md` added as the agent entry point; `docs/JOURNAL.md` started.
- `docs/progress.html` and `docs/tracker.bat` added — development tracker, parsed live from the
  source documents, launched from the repository.
- Decisions D6–D17 recorded and closed.
- **S1 (M6): config integrity and drift detection, in review.** New `config/config.defaults.json`
  (committed reference config); `config_store.load_config()` merges the live file over it, so a
  missing key falls back to the shipped default, never `KeyError`, never a silent `0`. New
  `diff_against_defaults()` logs every `missing`/`unknown`/`changed` key at run start; results are
  stamped with `config_version`. Two pre-existing `.get(key, 0)` fallbacks fixed
  (`flatness.py`/`power_accuracy.py`, attenuation keys). D16 (minimal CI — `ruff` + the offline
  test suite on push) folded in per the roadmap. See `docs/adr/0002-config-defaults-and-drift-detection.md`.
- **S2 (U2): immediate response after Start Run, in review.** `static/js/app.js` only — the Start
  button, running indicator and log view now update synchronously on click, before
  `/api/run/start`'s network round-trip; log polling begins immediately, surfacing the connect/
  setup sequence the server already writes to the live-log buffer during that call. No server-side
  change — pure R0.

---

## v0.7.0 — 2026-09-07 — S-M0: Power Accuracy per-point overhead

**NOT BENCH-VERIFIED. Acceptance criteria 1-8 were not executed; no instrument access at release
time.**

Cuts Power Accuracy's modulator-side per-point overhead (measured ~13.4 s/point, dominated by a
flat ~1.4 s/command fixed wait) via three items, gated per config key with safe defaults:

- DUT-side ADC power cross-check gated off by default — `power_accuracy.enable_adc_power_check`
  (default `false`, was `read_adc_power` default `true`). Code path retained, not deleted.
- `freq` sent to the modulator only when it changes within a frequency block, not resent per point.
- Prompt-based transport read on the telnet modulator path, replacing a fixed post-command sleep —
  gated **per check** by `use_prompt_read` (`power_accuracy`: `true`; `flatness`,
  `iq_validation`: `false`), resolved the same way as `ext_gain_db` (D5). `flatness.py` and
  `iq_validation.py` have zero diff and are unaffected. Mandatory companion dwell:
  `power_accuracy.dut_settle_after_power_s` (default `0.5`, legacy `modSettings.txt` value,
  **itself unverified on this unit** — see the journal).

Does not change `chp_average_count`, the `INIT:REST` wait, sweep-time AUTO, or any CHP-scoped
node (D11 not reopened).

**Closed `done-unverified`, accepted `deferred`** — merged and closed for workflow purposes so
S1 could proceed. A partial serial-only A/B (2026-08-27) bench-confirmed items 1 and 2; item 3
(the prompt-based read, telnet-only) and the full criteria 1–8 in spec §M7 remain outstanding,
tracked as roadmap stage S-M0-V. See `docs/JOURNAL.md` 2026-09-07.

**Revert without a code change, if needed:** set `power_accuracy.use_prompt_read = false` and
`power_accuracy.enable_adc_power_check = true`.

---

## Baseline — 2026-08-26

State at the point these documents were written:

- Power Accuracy parity Stages 1–5 implemented.
- PR #10 — menu-navigation fixes (`-channel-1`, `-adc-power-`) — merged.
- PR #11 — bench test summary doc — merged.
- PR #13 — per-check external gain, analyzer state-leakage fix — merged, bench-verified.
- IQ Validation blocked: no per-check external gain key yet, two known defects open.
- NS330 calibration with `NsPowerCalibrationV6.2.jar` in progress.
