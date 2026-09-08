# ADR 0002: config.defaults.json — reference config, merge-based fallback, drift detection

**Status:** Accepted
**Date:** 2026-09-07
**Stage:** S1 (spec §M6)

## Context

`config/config.json` is the bench's live, editable configuration. It has drifted from
its intended values between sessions at least once with a confirmed, understood cause
(`chp_integ_bw_hz` read 8 000 000 on the bench instead of the correct 5 000 000 — span
mistaken for integration bandwidth, `POWER_ACCURACY_HANDOFF.md` §8) and is suspected,
unconfirmed, in a second case (an unexplained 5–6 dB level difference,
`POWER_ACCURACY_HANDOFF.md` §9, recorded as a hypothesis, never a conclusion).

Before this stage, `config_store.load_config()` read `config.json` verbatim and
returned it. Every check module indexes into it directly
(`cfg["power_accuracy"]["pwr_start_dbm"]`), which means a key missing from the file on
disk raises `KeyError` — not silent, but also not "the app uses the documented default"
as spec §M6 requires; a few call sites instead used `.get(key, 0)`, which *is* silent
and violates the project's own hard constraint (CLAUDE.md: "An absent per-check config
key falls back to the configured global value, never to 0"). There was also nothing to
compare the live file against — no reference, no way to say "this differs from what it
should be" instead of "this differs from what it used to be" (which nobody can verify
without git archaeology).

## Decision

Introduce a second, bundled, read-only file: **`config/config.defaults.json`**. It is a
committed snapshot of the app's reference configuration — same shape as `config.json`
(the same six sections: `analyzer`, `modulator`, `flatness`, `power_accuracy`,
`iq_validation`, `general`), plus one extra top-level key, `_config_version` (an
integer, bumped by hand whenever the file's content changes). It lives under
`paths.resource_dir()`, the same bundled/read-only location `config_store.py` already
uses to seed a frozen build's first-run config — so a frozen build's own copy of the
defaults can't itself drift, and no change to that seeding logic was needed.

Three functions, `core/config_store.py`:

- **`load_config()`** (existing entry point, behavior changed): reads the live file and
  `config.defaults.json`, merges them section by section — defaults as the base layer,
  live values overriding wherever present — and returns the merged dict. Every check
  module's existing `cfg[section][key]` indexing is untouched and now can't raise or
  silently read 0 for a key that exists in the schema: a missing key resolves to the
  shipped default.
- **`diff_against_defaults(live_raw, defaults)`**: pure function, no file I/O — given
  two raw (unmerged) section trees, returns every key that is `missing` (in defaults,
  absent from live), `unknown` (on disk, not in the reference) or `changed` (present in
  both, different values). Silent where they agree. Offline-testable against synthetic
  dicts.
- **`compute_config_diff()`**: thin wrapper — reads both files fresh from disk, returns
  `(diff_list, config_version)`. What `session.py` calls at the start of every run.

`session.py` logs the diff (via `logger.py`'s `log_header()`) before anything else in
the run header, and stamps every result file with the version: a `# config_version: N`
line prepended to the CSV, a `"config_version"` field in the JSON. `_config_version`
itself is deliberately **not** included in `load_config()`'s merged return value — it
stays a property of `config.defaults.json` alone. Including it in the merged dict would
mean it round-trips into the live, operator-editable `config.json` the next time
someone saves a change from the Settings page (`app.py`'s `/api/config` POST, which
receives back exactly what `/api/config` GET produced), pinning a stale version number
into the bench file and eventually making it lie.

## Consequences

- Every check module — `flatness.py`, `power_accuracy.py`, `iq_validation.py` — needed
  **zero changes** to benefit from the fallback guarantee; the merge happens once,
  below them, in `config_store.load_config()`.
- Two long-standing `.get(key, 0)` call sites (`flatness.py`'s `lband_atten_db`,
  `power_accuracy.py`'s `if_atten_db` and `lband_atten_db`) were changed to plain
  indexing in the same stage, since they are now guaranteed present by the merge and
  the explicit `, 0` was exactly the silent-zero pattern this ADR exists to close.
  Their sibling `.get(key, <in-code default>)` calls for the interpolation start/stop
  keys are unchanged — those are genuinely optional fine-tuning parameters with no
  entry in `config.defaults.json` at all, not schema keys that happen to be missing.
- `config.defaults.json` must be kept in sync by hand whenever a new config key is
  introduced — it is not derived from the checks' own code. A key added to
  `config.json` without a matching entry in `config.defaults.json` will show up as
  `unknown` in every run's drift log forever, which is itself a useful nudge to add it,
  but is a manual step, not an enforced one.
- Bumping `_config_version` is also manual — a deliberate choice (D14: keep the format
  simple, no hidden machinery) over a content hash, which would be harder to reason
  about ("what changed between version `a1b2c3` and `d4e5f6`?") for the same
  correctness guarantee.

## Alternatives considered

- **Keep `load_config()` as a verbatim read, add only the diff/logging.** Rejected —
  this closes the *visibility* half of M6 but not the *safety* half: a removed key
  would still either raise `KeyError` or (worse, at the three known call sites) read
  silently as 0. The acceptance test in spec §M6 explicitly requires the run to
  continue using the documented default, not merely to log that the key vanished.
- **A content hash instead of a hand-bumped integer version.** Rejected for the reason
  above — not more correct, just less legible, and this project has already decided
  (D14) to favor legibility over automation where the two trade off.
- **Fold `_config_version` into the merged config dict.** Rejected — the Settings page
  round-trips whatever `/api/config` GET returns back through POST on every save; a
  version field living there would get silently pinned to a stale value the first time
  anyone saved unrelated settings changes.
