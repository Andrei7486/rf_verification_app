# RF Verification App — technical documentation

Audience: whoever maintains or extends the app. For install/operation see `README.md`.

---

## 1. Design goals

- **One tool, three checks** — replace scattered Tera Term TTL macros with a single app
  that auto-drives the modulator + CXA and records what it did.
- **Nothing hard-coded** — every lab value lives in `config/config.json`; every
  frequency list lives in `config/freq_lists/<UNIT>.txt`. The same build serves every
  unit and bench.
- **Traceable** — each run writes a `.log` (parameters + every device command), a `.csv`
  (results), and a `.json` (summary). Deviations are visible per point.
- **Safe on real hardware** — read-only-first ordering, explicit Max Hold restart, strict
  separation of the two modulator signal paths, and a conservative default for the one
  SCPI command whose form varies by firmware (external gain).

---

## 2. Architecture

```
                         Browser (HTML/CSS/JS)
                                 |  fetch() JSON
                                 v
  app.py (Flask)  --- routes: pages + /api/config, /api/freqlist, /api/run/*
                                 |
                                 v
  core/session.py  (RunSession, SESSION singleton) -- the run state machine
        |                        |                         |
        v                        v                         v
  core/checks/*          core/analyzer.py          core/modulator.py
  (flatness,             (CXA SCPI wrapper)        (telnet / serial NS CLI)
   power_accuracy,               |                         |
   iq_validation)                +------ core/transport.py (raw-socket LineSocket)
        |
        v
  core/config_store.py (JSON config + freq lists)   core/logger.py (.log/.csv/.json)
```

The backend is thin: Flask validates requests and delegates to `SESSION`. All device
behaviour is in the `core` package. All parameters are read from `config/`.

---

## 3. Module responsibilities

| Module | Responsibility |
|--------|----------------|
| `app.py` | Flask routes; serves the two pages and the JSON API; converts `SessionError`/`ValueError`/`KeyError` into HTTP 400 with a message. |
| `core/config_store.py` | Load/save `config.json` (atomic write); list units; load/save per-unit frequency lists; resolve the results directory. Paths are resolved relative to the package, so the launch CWD does not matter. |
| `core/transport.py` | `LineSocket` — raw-socket line client (`connect`, `send`, `read_until`, `drain`, `close`). Deliberately **not** `telnetlib` (removed in Python 3.13). Used by both the analyzer and the telnet modulator. |
| `core/analyzer.py` | `Analyzer` — one method per CXA SCPI transaction; `query_number` pulls a float out of a reply with `_NUM_RE`. |
| `core/modulator.py` | `TelnetModulator` / `SerialModulator` behind `make_modulator(cfg)`; both expose `connect` / `send(cmd, wait) `/ `close`. pyserial is imported lazily so telnet users need not install it. |
| `core/checks/base.py` | Shared modulator command sequences: `clean_carrier_setup/cleanup` (flatness, power) and `iq_setup/iq_cleanup` (IQ). Encodes the signal-path discipline in one place. |
| `core/checks/*.py` | One class per check implementing the check interface (below). |
| `core/checks/__init__.py` | `CHECKS` registry + `get_check(key)`. |
| `core/session.py` | `RunSession` state machine + `SESSION` singleton; owns device connections for a run; lock-guarded. |
| `core/logger.py` | `RunLogger` — per-run logger and the `.log`/`.csv`/`.json` writers. |

---

## 4. The check interface

Each check is a plain class with these attributes/methods; the session calls them by
duck typing, so adding a check needs no changes to the session.

| Member | Purpose |
|--------|---------|
| `key`, `title` | Identifier and display name. |
| `final_only` | `True` if the verdict is computed once at the end (flatness) rather than per point. |
| `manual_fields` | List of `{name, label, step}` describing the operator inputs in manual mode. |
| `csv_columns` | Ordered CSV/table column names. |
| `build_points(cfg, freqs, params)` | Return the ordered list of point descriptors (dicts). Flatness/IQ → one per frequency; power → one per power level at `params['freq_mhz']`. |
| `modulator_setup(mod, cfg)` | One-time DUT setup (chooses the correct signal path). |
| `analyzer_setup(cxa, cfg, points)` | One-time CXA setup (freq view, BW, trace type, Max Hold). |
| `prepare_point(mod, cxa, cfg, point)` | Put the devices in the state for this point (set freq / power / DAC tone; re-center + restart Max Hold for IQ). |
| `measure_point(cxa, cfg, point, mode, manual)` | Read the CXA (`auto`) or take the operator values (`manual`); return a measurements dict. |
| `evaluate_point(cfg, point, meas)` | Per-point verdict dict `{result, flag}` (or `{}` for flatness). |
| `finalize(cfg, results)` | Compute the overall verdict; may annotate rows (flatness tags MAX/MIN + dev-from-mean). |
| `cleanup(mod, cfg)` | Return the DUT to a safe idle state. |
| `row_for(result)` | Map a stored result to a CSV/table row keyed by `csv_columns`. |

A stored `result` is `{"index", "point", "meas", "eval"}`.

---

## 5. Run state machine and data flow

`SESSION` (module-level singleton in `session.py`) holds one run. All public methods take
a lock, so concurrent requests from a second browser tab serialize and a second run is
refused with “a run is already in progress”.

```
start(check, unit, mode, freqs, params)
    load config snapshot -> build points -> open RunLogger -> log header
    connect CXA -> connect modulator -> modulator_setup -> analyzer_setup
    idx=0 -> prepare_current()           # returns first point + manual_fields + columns

measure(manual)   -> measure_point + evaluate_point -> store/replace row -> {row, flag, has_next}
next()            -> idx++ -> prepare_current()   (or {done:true} at the end)
skip()            -> log skip -> idx++ -> prepare_current()
stop()            -> cleanup -> finalize -> write .log/.csv/.json -> close devices -> {verdict, rows, flags, summary}
```

Re-measuring the current point replaces its row (rows are keyed by `index`), so an
operator can correct a mis-typed value before moving on.

**Frontend flow** (`static/js/app.js`): the start response defines `columns`,
`manual_fields`, and `mode`, from which the UI builds the manual inputs and the live
table header. Rows append on each `measure`. On `stop`, the table is rebuilt from the
authoritative finalized rows (this is when flatness fills in dev-from-mean and MAX/MIN),
and the verdict banner is drawn from `summary`.

---

## 6. Device command mapping

### 6.1 CXA — SCPI over TCP (telnet, port 5023, prompt `SCPI>`)

| App method | SCPI sent |
|------------|-----------|
| `preset_swept_sa` | `:CONF:SAN` |
| `apply_ext_gain` | `ext_gain_scpi` template (default `:CORR:SA:GAIN {db}`) — only if `apply_ext_gain` is true |
| `set_ref_level` | `:DISP:WIND:TRAC:Y:RLEV <dBm>` |
| `set_scale_div` | `:DISP:WIND:TRAC:Y:PDIV <dB>` |
| `set_center_span` | `:FREQ:CENT <Hz>` ; `:FREQ:SPAN <Hz>` |
| `set_start_stop` | `:FREQ:STAR <Hz>` ; `:FREQ:STOP <Hz>` |
| `set_bw` | `:BWID <Hz>` ; `:BWID:VID <Hz>` |
| `set_detector_peak` | `:DET:TRACE1 POS` |
| `set_max_hold` / `restart_max_hold` | `:TRAC1:TYPE MAXH` ( + `:INIT:REST` to restart ) |
| `set_write_trace` | `:TRAC1:TYPE WRIT` (power accuracy — fresh read per level) |
| `marker_peak_level` | `:CALC:MARK1:MAX` ; `:CALC:MARK1:Y?` |
| `marker_level_at` | `:CALC:MARK1:X <Hz>` ; `:CALC:MARK1:Y?` |

Replies are parsed by `_NUM_RE`, which matches scientific or decimal notation and returns
the first number (e.g. `-2.53100000E+01` → `-25.31`).

### 6.2 Modulator — NS CLI (telnet port 23 or serial), login `admin` / `novelsat`

**Clean-carrier path** (flatness, power) — `clean_carrier_setup`:
```
-u expert-login → -modulator-config → line → sine on → power <dBm> → tx enable
per point:  freq <MHz>            (flatness steps freq; power steps 'power <dBm>')
cleanup:    tx disable → sine off
```

**DAC test-tone path** (IQ) — `iq_setup`:
```
-u expert-login → -modulator-config → line → sine on → power <dBm> → tx enable
→ top → debug → calib → Init          (stays inside -calib-; do NOT navigate out)
per point:  freq <MHz> → dac-freq <Hz> → dac-i <val> → dac-q <val>
cleanup:    dac-i 0 → dac-q 0 → tx disable → sine off
```

These two sequences live only in `checks/base.py`; a check calls exactly one of them, so
the paths are never mixed within a measurement.

---

## 7. Configuration schema (`config/config.json`)

Grouped by section; the Settings UI renders each key with a type-appropriate control and
preserves types on save.

- **analyzer** — `cxa_ip`, `cxa_scpi_port`, `scpi_prompt`, `scpi_timeout_s`,
  `ext_gain_db`, `apply_ext_gain`, `ext_gain_scpi`, `cxa_web_password`, plus peak-search
  hints (`peak_excursion_db`, `peak_threshold_dbm`, `max_peaks`) reserved for a future
  peak-table read.
- **modulator** — `dut_conn_type` (`telnet`|`serial`), `dut_ip`, `dut_telnet_port`,
  `dut_com_port`, `dut_baud`, `dut_user`, `dut_password`, `cmd_delay_s`,
  `connect_timeout_s`.
- **flatness** — `flat_power_dbm`, `flat_tolerance_db`, `dwell_s`, `ref_level_dbm`,
  `scale_div_db`, `res_bw_hz`, `video_bw_hz`, `span_margin_mhz` (start/stop = min/max of
  the selected frequencies ± this margin). `flat_step_mhz`/`flat_band_*` are informational
  seeds for the list.
- **power_accuracy** — `pwr_start_dbm`, `pwr_stop_dbm`, `pwr_step_db`, `pwr_tolerance_db`,
  `dwell_s`, `ref_level_dbm`, `span_hz`, `res_bw_hz`, `video_bw_hz`.
- **iq_validation** — `iq_power_dbm`, `iq_dac_freq_hz`, `iq_dac_i`, `iq_dac_q`,
  `iq_spur_limit_dbc`, `dwell_s`, `ref_level_dbm`, `span_hz`, `res_bw_hz`, `video_bw_hz`,
  `loft_offset_hz`.
- **general** — `verification_mode`, `log_dir`, `restart_maxhold_on_start`,
  `default_unit`.

---

## 8. Extending

**Add a unit** — drop `config/freq_lists/<UNIT>.txt` (one MHz per line, `#` comments).
It appears in the Unit dropdown automatically. If the unit needs different tolerances,
either edit the shared values in Settings per run, or (if it needs its own permanent set)
add a per-unit override mechanism — currently config is global.

**Add a check** — create `core/checks/<name>.py` with a class implementing the interface
in §4, then register it in `core/checks/__init__.py` (`CHECKS`). Add an `<option>` to the
check `<select>` in `templates/index.html`. No session or app changes are required; the
UI is driven by the start response (`columns`, `manual_fields`, `mode`).

**Change a SCPI command** — edit the single method in `core/analyzer.py`. Because each
method is one transaction, firmware differences are localized.

---

## 9. Concurrency and lifecycle notes

- Flask runs with `threaded=True` so static assets load while a device call is in flight.
- `RunSession` serializes all state transitions with a lock; only one run proceeds per
  process. This matches the deployment (2–3 fixed single-operator stations).
- Device connections are opened in `start` and held for the whole run; `stop`
  (and any setup failure) closes them best-effort. If the app is killed mid-run, the DUT
  may be left with TX enabled — start a new run and Stop it, or power-cycle, to clear it.
- Each run gets its own `logging.Logger` (name includes the timestamp), so handlers are
  never shared between runs and the `.log` file is flushed on `stop`.

---

## 10. Safety notes (why the code is shaped this way)

- **External gain is not force-pushed.** The X-Series SCPI for external gain varies by
  firmware, so sending a guessed command to a live analyzer risks a silent offset. Default
  `apply_ext_gain = false`: the app logs the expected −3.50 dB and relies on the
  instrument setting. Enable it only after confirming `ext_gain_scpi` on your CXA.
- **Max Hold is restarted at run start** (`:INIT:REST`) so a stale carrier from a previous
  run cannot read as a false high peak. IQ also restarts Max Hold per frequency because
  the center moves.
- **Power accuracy uses a write trace, not Max Hold**, so stepping the commanded power
  down reads the actual current level rather than the highest ever seen.
- **Signal-path discipline**: DAC commands (`dac-*`) only ever run in the IQ path inside
  `-calib-`; the clean-carrier path never touches them. Encoded once in `checks/base.py`.
- **IQ cleanup zeroes the DAC** so the +1 MHz test tone does not leak into the next test.

---

## 11. Known limitations

- **Auto IQ marker placement** reads the wanted/image/LOFT peaks at fixed offsets
  (`+dac`, `−dac`, `+loft_offset`) from the carrier center. If a particular setup puts
  LOFT elsewhere (e.g. ≈ −2 MHz), set `loft_offset_hz` accordingly. For unusual spectra,
  Manual mode (operator reads the delta markers) is the reliable path.
- **Auto reads assume a single sweep has settled**; `dwell_s` and the marker settle time
  are conservative but bench-dependent — increase them if readings look early.
- **Config is global**, not per-unit. Different units share tolerances unless changed in
  Settings for the run.
- **No peak-table read yet.** Flatness reads a marker per frequency (equivalent and more
  explicit for logging). The `peak_*` config keys are reserved for a future `:CALC:DATA`
  peak-table implementation if a faster single-read sweep is wanted.
- **Not tested against live hardware in this build** — the SCPI/CLI transactions follow
  the existing project scripts and the spec, but validate on the bench before relying on
  auto verdicts, especially the ext-gain command and the IQ marker offsets.
