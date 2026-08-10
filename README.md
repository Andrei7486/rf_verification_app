# RF Verification App — user guide

A local web app for the lab PCs that runs the three manual RF checks for NS modulators
against the Keysight CXA (at `192.168.0.5`):

- **Flatness** — carrier level even across the band (pk-pk within tolerance)
- **Power accuracy** — measured level tracks the commanded power per step
- **IQ validation** — Image and LOFT spurs suppressed vs. the wanted tone

It replaces the fragmented Tera Term (TTL) macros. Because the app talks to the CXA
over SCPI, it supports two modes: **Manual** (you read the CXA and type values) and
**Auto** (the app reads the CXA and decides PASS/FAIL). Every run is logged, and any
deviation from spec is highlighted.

---

## 1. What you need

- A Windows PC on the lab bench that can reach the CXA (`192.168.0.5`) and the
  modulator (telnet `192.168.0.50:23`, or a serial COM port).
- **Python 3.9 or newer** (3.11+ recommended). During install, tick
  **“Add Python to PATH”.**

---

## 2. One-time install

Open **Command Prompt** in the app folder (the folder that contains `app.py`) and run:

```
pip install -r requirements.txt
```

That installs Flask (required) and pyserial (only used if you run the modulator over a
serial COM port; telnet mode needs nothing extra).

> Tip: if `pip` is not found, use `py -m pip install -r requirements.txt`.

---

## 3. Start the app

From the same folder:

```
python app.py
```

The server starts and your browser opens at **http://127.0.0.1:5000** automatically.
If it does not open, type that address into the browser yourself. To stop the app,
press **Ctrl+C** in the Command Prompt window.

---

## 4. Before the first run — check Settings

Open the **Settings** page (top-right link) and confirm:

- **Analyzer:** `cxa_ip = 192.168.0.5`, and **`ext_gain_db = -3.50`**. The external
  gain must match the value used during the reference (“golden”) calibration, or all
  absolute levels will be offset. By default the app does **not** push the ext-gain
  command to the instrument (`apply_ext_gain = false`) — set it on the CXA yourself and
  the app will remind you of the expected value. Set `apply_ext_gain = true` only if you
  have confirmed the command in `ext_gain_scpi` works on your CXA firmware.
- **Modulator:** `dut_conn_type` = `telnet` (default, `192.168.0.50:23`) or `serial`
  (then set `dut_com_port`, e.g. `COM168`, and `dut_baud = 115200`).
- **Per-check values** (power range, tolerances, spur limit, RBW/VBW, etc.) — all
  editable here, grouped by check.

Click **Save configuration**. Changes apply to the next run (not a run already in
progress).

### Frequency lists
Each unit has its own list (e.g. `NS330`), one MHz value per line. Edit it in the
**Frequency lists** box on the Settings page. Lines starting with `#` are comments.
Non-uniform steps are fine — the list is explicit. Adding a new unit = add a new list
file `config/freq_lists/<UNIT>.txt`; no code change needed.

---

## 5. Running a check

On the **Run** page:

1. **Check** — Flatness / Power accuracy / IQ validation.
2. **Unit** — picks that unit’s frequency list.
3. **Mode** — Manual or Auto.
4. **Frequencies**
   - Flatness / IQ: tick the frequencies to include (all ticked by default; untick any
     to skip). Use **Select all / none** to speed this up.
   - Power accuracy: pick the single frequency; power is stepped there (levels come
     from Settings).
5. Press **Start run**. The app connects to the CXA and the modulator, does the one-time
   setup, restarts Max Hold clean, and prepares the first point.

For each point:

- The **readout** shows the point number, frequency (and set power for power accuracy).
- **Manual mode:** read the value(s) on the CXA, type them into the input(s), press
  **Measure**. IQ asks for the two spur deltas in dBc (use the CXA delta marker).
- **Auto mode:** just press **Measure** — the app reads the CXA over SCPI.
- The measured row appears in the **Results** table immediately.
- Press **Next** to advance to the next point (it prepares the device), or **Skip** to
  move on without measuring, or **Stop & finish** at any time.

When you press **Stop & finish**, the app runs the modulator cleanup (drops the carrier;
for IQ it also zeroes the DAC so the +1 MHz tone does not leak into the next test),
computes the verdict, and writes the log files.

---

## 6. Reading the results

- A green **PASS** or red **FAIL** banner with a short detail line (pk-pk vs. tolerance,
  or number of steps within tolerance, or spur limit).
- The table lists every point with its measured values. Out-of-spec rows are
  highlighted; for flatness the **MAX** and **MIN** carriers (which define the pk-pk
  spread) are tagged.

Each run saves three files in the **`results/`** folder, named
`<check>_<unit>_<timestamp>`:

| File   | Contents |
|--------|----------|
| `.log` | Human-readable trace: every parameter used and every device command sent |
| `.csv` | The results table (open in Excel) |
| `.json`| Machine-readable summary: parameter snapshot, all rows, verdict |

To share a result with a colleague, send the matching `.csv` (and `.log` if they want to
see the exact parameters and commands).

---

## 7. Pass/fail criteria (defaults, all editable in Settings)

| Check | Rule |
|-------|------|
| Flatness | MAX − MIN of carrier levels ≤ `flat_tolerance_db` (default 1.0 dB pk-pk) |
| Power accuracy | \|measured − set\| ≤ `pwr_tolerance_db` (default 0.8 dB) at every step |
| IQ validation | Image **and** LOFT each ≤ `iq_spur_limit_dbc` (default −55 dBc) at every frequency |

---

## 8. Troubleshooting

| Symptom | Likely cause / fix |
|--------|--------------------|
| “Cannot connect to 192.168.0.5:5023” | CXA off, wrong IP, or SCPI/telnet not enabled on the analyzer. Check `cxa_ip` in Settings and that you can ping it. |
| “Cannot connect to 192.168.0.50:23” | Modulator not reachable over telnet. Check cabling/IP, or switch `dut_conn_type` to `serial`. |
| Serial error “needs pyserial” | Run `pip install pyserial`. |
| “Cannot open COMxx” | Wrong port, or another program (Tera Term/PuTTY) is holding the COM port — close it. |
| Absolute levels look shifted | Ext Gain on the CXA does not match `ext_gain_db` (−3.50). Fix it on the instrument. |
| A stale peak reads too high | Max Hold artifact — the app restarts Max Hold at the start of every run, but confirm nothing else left a tone on the DUT; re-run. |
| “A run is already in progress” | A previous run was not stopped. Press **Stop & finish**, or restart the app. |

The app runs one verification at a time on a station. If two people open the page on the
same PC, only one run proceeds; the other gets a clear “run already in progress” message.
