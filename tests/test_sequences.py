"""Hardware-free checks against the current analyzer.py / core/checks/*.py logic.

Uses fake Analyzer / fake Modulator that just record calls and return canned values -
no CXA/DUT needed. Covers:
  - flatness.fixed_freqs() / power_accuracy._levels() drift-free stepping
  - flatness per-point fault isolation (a bad CXA read or DUT tune -> FAIL, loop continues)
  - flatness peak-table diagnostic gated by enable_peak_table_logging
  - iq_validation delta-marker sequence (find_peak -> delta -> LOFT/Image at configured
    absolute offsets)

Run from the app root:  python -m tests.test_sequences   (or: python tests/test_sequences.py)
"""
import copy
import json
import os
import sys

# Allow running both as a module and as a plain script.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.checks import get_check
from core.checks import base as check_base


class FakeLog:
    """Stand-in for the RunLogger.logger the checks call cxa.log.* on - records the
    formatted messages (not just swallowing them) so tests can assert on what was
    logged, e.g. that a warning-level mismatch actually fired.
    """
    def __init__(self):
        self.infos = []; self.warnings = []; self.errors = []
    @staticmethod
    def _fmt(msg, a):
        try:
            return msg % a if a else msg
        except Exception:
            return msg
    def info(self, msg, *a, **k): self.infos.append(self._fmt(msg, a))
    def warning(self, msg, *a, **k): self.warnings.append(self._fmt(msg, a))
    def error(self, msg, *a, **k): self.errors.append(self._fmt(msg, a))
    def debug(self, *a, **k): pass


class FakeModulator:
    """Records every command sent; can be told to raise on a given call index and/or
    a specific command text, and/or return a canned reply for a specific command
    (default "" for anything unlisted).
    """
    def __init__(self, fail_on_call=None, fail_on_cmd=None, replies=None):
        self.sent = []
        self.fail_on_call = fail_on_call
        self.fail_on_cmd = fail_on_cmd
        self.log = FakeLog()
        self.replies = replies or {}
    def send(self, cmd, wait=None):
        idx = len(self.sent)
        self.sent.append(cmd)
        if self.fail_on_call is not None and idx == self.fail_on_call:
            raise RuntimeError("simulated modulator failure")
        if self.fail_on_cmd is not None and cmd == self.fail_on_cmd:
            raise RuntimeError("simulated modulator failure")
        return self.replies.get(cmd, "")


class FakeAnalyzer:
    """Records commands; returns canned numbers for queries."""
    def __init__(self, sweep_time_s=0.0, chp_sweep_time_s=0.0,
                 peak_table="peak1,-10dB\npeak2,-50dB",
                 fail_marker_at=None, fail_chp_reads=0, ext_gain_readback=None):
        self.log = FakeLog()
        self.cmds = []          # raw SCPI via command/command_sync
        self.calls = []         # (method, args)
        self.peak_hz = 1_000_000_000.0
        self._sweep_time_s = sweep_time_s
        self._chp_sweep_time_s = chp_sweep_time_s
        self._peak_table = peak_table
        self._fail_marker_at = fail_marker_at   # freq_hz that marker_level_at() should raise on
        self.peak_table_reads = 0
        self._fail_chp_reads = fail_chp_reads   # remaining read_chp() calls that should raise
        self.chp_restarts = 0
        self._ext_gain = None                   # last value pushed via set_ext_gain()
        # If set, :CORR:SA:GAIN? returns this instead of the pushed value - lets a
        # test simulate a read-back mismatch independent of what was actually sent.
        self._ext_gain_readback = ext_gain_readback
    def _rec(self, name, *a):
        self.calls.append((name, a))
    # low level
    def command(self, scpi): self.cmds.append(scpi)
    def command_sync(self, scpi): self.cmds.append(scpi)
    def query(self, scpi): return self._peak_table
    def query_number(self, scpi):
        if scpi == ":CORR:SA:GAIN?":
            return self._ext_gain_readback if self._ext_gain_readback is not None else self._ext_gain
        return -5.0
    # setup helpers
    def preset(self): self._rec("preset")
    def preset_swept_sa(self): self._rec("preset_swept_sa")
    def apply_ext_gain(self): self._rec("apply_ext_gain")
    def set_ext_gain(self, db):
        self._rec("set_ext_gain", db)
        self._ext_gain = float(db)
    def set_ref_level(self, v): self._rec("set_ref_level", v)
    def set_scale_div(self, v): self._rec("set_scale_div", v)
    def set_center_span(self, c, s): self._rec("set_center_span", c, s)
    def set_center_freq(self, c): self._rec("set_center_freq", c)
    def set_start_stop(self, a, b): self._rec("set_start_stop", a, b)
    def set_bw(self, r, v): self._rec("set_bw", r, v)
    def set_chp_span(self, s): self._rec("set_chp_span", s)
    def set_chp_bw(self, r, v): self._rec("set_chp_bw", r, v)
    def set_chp_sweep_time_auto(self, on=True): self._rec("set_chp_sweep_time_auto", on)
    def get_chp_sweep_time(self): self._rec("get_chp_sweep_time"); return self._chp_sweep_time_s
    def set_chp_average(self, on, count): self._rec("set_chp_average", on, count)
    def chp_restart(self): self._rec("chp_restart"); self.chp_restarts += 1
    def set_sweep_time(self, s): self._rec("set_sweep_time", s)
    def get_sweep_time(self): self._rec("get_sweep_time"); return self._sweep_time_s
    def get_peak_table(self):
        self._rec("get_peak_table"); self.peak_table_reads += 1
        return self._peak_table
    def set_attenuation(self, db): self._rec("set_attenuation", db)
    def set_attenuation_auto(self, on=True): self._rec("set_attenuation_auto", on)
    def set_detector_peak(self): self._rec("set_detector_peak")
    def restart_max_hold(self): self._rec("restart_max_hold")
    def enable_peak_table(self, scpi=None): self._rec("enable_peak_table", scpi)
    # measurement
    def read_chp(self):
        self._rec("read_chp")
        if self._fail_chp_reads > 0:
            self._fail_chp_reads -= 1
            raise RuntimeError("simulated CHP read failure")
        return -5.0
    def marker_level_at(self, hz, settle_s=0.15):
        self._rec("marker_level_at", hz)
        if self._fail_marker_at is not None and hz == self._fail_marker_at:
            raise RuntimeError("simulated CXA read failure")
        return -10.0
    def marker_peak_level(self): self._rec("marker_peak_level"); return -5.0
    def find_peak(self): self._rec("find_peak"); return (self.peak_hz, -5.0)
    def marker_to_delta(self): self._rec("marker_to_delta")
    def marker_delta_y_at_offset(self, hz, settle_s=0.15):
        self._rec("marker_delta_y_at_offset", hz); return -60.0
    def marker_delta_y_at(self, hz, settle_s=0.15):
        self._rec("marker_delta_y_at", hz); return -60.0


def load_cfg():
    p = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
    return json.load(open(p, encoding="utf-8"))


def names(fa):
    return [c[0] for c in fa.calls]


# ---------------------------------------------------------------- flatness

def test_flatness_fixed_freqs():
    """start + i*step stepping: exact grid, no accumulated float drift."""
    cfg = load_cfg(); chk = get_check("flatness")()
    freqs = chk.fixed_freqs(cfg)
    assert len(freqs) == 25, freqs
    assert freqs[0] == 950.0 and freqs[-1] == 2150.0, freqs
    assert freqs == [950.0 + i * 50.0 for i in range(25)], freqs
    print("flatness: fixed_freqs OK (25 points, 950..2150/50, no drift)")


def test_flatness_per_point_isolation():
    """A bad CXA read on one point must not abort the rest of the run."""
    cfg = load_cfg(); chk = get_check("flatness")()
    pts = chk.build_points(cfg, [], {})
    bad_freq_hz = pts[3]["freq_mhz"] * 1e6
    fa = FakeAnalyzer(sweep_time_s=0.0, fail_marker_at=bad_freq_hz)
    fm = FakeModulator()
    chk.modulator_setup(fm, cfg)
    chk.analyzer_setup(fa, cfg, pts)
    results = []
    for pt in pts[:5]:
        chk.prepare_point(fm, fa, cfg, pt)
        meas = chk.measure_point(fa, cfg, pt, "auto", {})
        ev = chk.evaluate_point(cfg, pt, meas)
        results.append({"index": pt["index"], "point": pt, "meas": meas, "eval": ev})
    bad, good_after = results[3], results[4]
    assert bad["meas"].get("error"), bad
    assert bad["eval"]["result"] == "FAIL" and bad["eval"]["flag"] is True, bad
    assert good_after["meas"].get("error") is None, good_after   # loop kept going past point 3
    assert "measured_dbm" in good_after["meas"], good_after
    # finalize() must tolerate the mix of error/ok results (pk-pk stat skips the error one)
    summary = chk.finalize(cfg, results)
    assert summary["verdict"] in ("PASS", "FAIL"), summary
    rows = [chk.row_for(r) for r in results]
    assert rows[3]["Result"] == "FAIL" and rows[3]["Measured_dBm"] == "", rows[3]
    print("flatness: per-point isolation OK (bad CXA read -> FAIL row, loop continues, finalize OK)")


def test_flatness_prepare_error_isolation():
    """A DUT tune failure short-circuits measure_point() instead of touching the CXA."""
    cfg = load_cfg(); chk = get_check("flatness")()
    pts = chk.build_points(cfg, [], {})
    fa = FakeAnalyzer(sweep_time_s=0.0)
    fm = FakeModulator(fail_on_call=0)   # the first mod.send() (freq tune) raises
    chk.prepare_point(fm, fa, cfg, pts[0])
    meas = chk.measure_point(fa, cfg, pts[0], "auto", {})
    assert meas.get("error"), meas
    assert not any(c[0] == "marker_level_at" for c in fa.calls), fa.calls
    print("flatness: prepare-failure isolation OK (tune failure short-circuits the CXA read)")


def test_flatness_peak_table_gate():
    """enable_peak_table_logging gates the diagnostic-only peak table read."""
    cfg = load_cfg()
    pt = {"index": 0, "freq_mhz": 950.0}

    cfg_off = copy.deepcopy(cfg)
    cfg_off["flatness"]["enable_peak_table_logging"] = False
    fa_off = FakeAnalyzer()
    get_check("flatness")().measure_point(fa_off, cfg_off, pt, "auto", {})
    assert fa_off.peak_table_reads == 0, "peak table must stay off by default"

    cfg_on = copy.deepcopy(cfg)
    cfg_on["flatness"]["enable_peak_table_logging"] = True
    fa_on = FakeAnalyzer()
    get_check("flatness")().measure_point(fa_on, cfg_on, pt, "auto", {})
    assert fa_on.peak_table_reads == 1, "peak table must be read exactly once per point when enabled"
    print("flatness: peak table gate OK (off by default, one read per point when enabled)")


# ------------------------------------------------------------ power accuracy

def test_power_levels():
    """start - i*step stepping: exact grid, no accumulated float drift."""
    cfg = load_cfg(); chk = get_check("power_accuracy")()
    pa = cfg["power_accuracy"]
    levels = chk._levels(pa)
    step = abs(pa["pwr_step_db"])
    # Derived from config, not hardcoded - the step/range are tunable and must not
    # silently drift the test out of sync with whatever config.json actually ships.
    n = int(round((pa["pwr_start_dbm"] - pa["pwr_stop_dbm"]) / step)) + 1
    assert len(levels) == n, levels
    assert levels[0] == pa["pwr_start_dbm"] and levels[-1] == pa["pwr_stop_dbm"], levels
    assert levels == [round(pa["pwr_start_dbm"] - i * step, 3) for i in range(n)], levels
    print("power: _levels OK (%d steps, %s..%s/%s, no drift)"
          % (n, pa["pwr_start_dbm"], pa["pwr_stop_dbm"], step))


def test_power_chp_scoped_nodes():
    """Stage 1 parity: power_accuracy must use the CHP-scoped span/RBW/VBW nodes, not the
    generic ones the swept-SA checks (flatness/iq_validation) use - the Channel Power
    measurement keeps its own copy of these, so the generic nodes are silently ignored
    while :CONF:CHP is active. Regression guard for that exact bug.
    """
    cfg = load_cfg(); chk = get_check("power_accuracy")()
    pa = cfg["power_accuracy"]
    fa = FakeAnalyzer()
    chk.analyzer_setup(fa, cfg, [{"index": 0, "freq_mhz": 950.0}])
    assert ("set_chp_span", (pa["span_hz"],)) in fa.calls, fa.calls
    assert ("set_chp_bw", (pa["res_bw_hz"], pa["video_bw_hz"])) in fa.calls, fa.calls
    assert not any(c[0] in ("set_bw", "set_center_span") for c in fa.calls), fa.calls
    # Stage 2: sweep time left on AUTO (queried, not forced) and averaging configured.
    assert ("set_chp_sweep_time_auto", (True,)) in fa.calls, fa.calls
    assert ("get_chp_sweep_time", ()) in fa.calls, fa.calls
    assert ("set_chp_average", (True, pa.get("chp_average_count", 10))) in fa.calls, fa.calls
    assert chk._chp_sweep_time_s == fa._chp_sweep_time_s
    # Stage 3: deterministic baseline init - attenuation auto-coupled, ext gain zeroed
    # power_accuracy-local (not via the generic apply_ext_gain() global-flag path) -
    # and sent before the CHP-scoped measurement setup, not mixed in after it.
    assert ("set_attenuation_auto", (True,)) in fa.calls, fa.calls
    assert ("set_ext_gain", (0,)) in fa.calls, fa.calls
    assert not any(c[0] == "apply_ext_gain" for c in fa.calls), fa.calls
    assert fa.calls.index(("set_attenuation_auto", (True,))) < fa.calls.index(("set_chp_span", (pa["span_hz"],))), fa.calls
    assert fa.calls.index(("set_ext_gain", (0,))) < fa.calls.index(("set_chp_span", (pa["span_hz"],))), fa.calls

    fa2 = FakeAnalyzer()
    chk.prepare_point(FakeModulator(), fa2, cfg, {"index": 0, "freq_mhz": 950.0, "set_dbm": 0})
    assert ("set_center_freq", (950.0 * 1e6,)) in fa2.calls, fa2.calls
    assert not any(c[0] in ("set_bw", "set_center_span") for c in fa2.calls), fa2.calls
    print("power: CHP-scoped nodes OK (set_chp_span/set_chp_bw/set_center_freq/sweep-auto/"
          "averaging/baseline-init used, generic set_bw/set_center_span/apply_ext_gain not called)")


def test_power_chp_read_retry():
    """Stage 2: a transient CHP read failure retries (via :INIT:REST + settle) instead of
    aborting the point; exhausting chp_read_retries turns the point into a FAIL and lets
    the run continue - same per-point isolation pattern as flatness.py/iq_validation.py.
    """
    cfg = load_cfg(); chk = get_check("power_accuracy")()
    pa = dict(cfg["power_accuracy"]); pa["chp_read_retries"] = 3
    cfg2 = dict(cfg); cfg2["power_accuracy"] = pa
    point = {"index": 0, "freq_mhz": 950.0, "set_dbm": 0}

    # Fails twice, succeeds on the 3rd attempt (within the retry budget).
    fa_ok = FakeAnalyzer(chp_sweep_time_s=0.0, fail_chp_reads=2)
    meas_ok = chk.measure_point(fa_ok, cfg2, point, "auto", {})
    assert meas_ok.get("error") is None, meas_ok
    assert "measured_dbm" in meas_ok, meas_ok
    assert fa_ok.chp_restarts == 3, fa_ok.chp_restarts  # one INIT:REST per attempt

    # Fails on every attempt -> exhausts the retry budget -> reported as a point error,
    # not raised (measure_point() must never let this abort the whole run).
    fa_fail = FakeAnalyzer(chp_sweep_time_s=0.0, fail_chp_reads=99)
    meas_fail = chk.measure_point(fa_fail, cfg2, point, "auto", {})
    assert meas_fail.get("error"), meas_fail
    assert fa_fail.chp_restarts == 3, fa_fail.chp_restarts
    ev = chk.evaluate_point(cfg2, point, meas_fail)
    assert ev["result"] == "FAIL" and ev["flag"] is True, ev
    print("power: CHP read retry OK (transient failure recovers, exhausted retries -> FAIL)")


def test_power_modulator_setup():
    """Stage 4 parity + bench-confirmed fix (2026-08-26): full legacy modulator
    sequence, config-driven values, the Output Level Mode command gated OFF by
    default (bench-confirmed 'command not found'), and - critically - navigation
    back to -line- at the end, since prepare_point()'s freq/power commands are only
    valid there and were bench-confirmed to fail with 'command not found' when the
    CLI was left parked in -channel-1-.
    """
    cfg = load_cfg(); chk = get_check("power_accuracy")()
    fm = FakeModulator()
    chk.modulator_setup(fm, cfg)
    # Legacy order: top first, tx enable before sine off, full channel/modulation
    # chain, then back to top/-modulator-config/line so freq/power work afterward.
    expected = ["-u expert-login", "top", "-modulator-config", "line",
                "tx enable", "sine off", "symbol-rate 4", "roll-off 0.25",
                "dual-channel-mode single-ch", "-channel-1", "state enable",
                "source test-pattern", "modulation qpsk", "frame-size normal",
                "fec-rate 2/3", "pilot yes", "top", "-modulator-config", "line"]
    assert fm.sent == expected, fm.sent  # output-level-mode NOT sent by default
    assert fm.sent[-3:] == ["top", "-modulator-config", "line"], fm.sent

    # Config-driven values actually get substituted, not hardcoded.
    cfg2 = json.loads(json.dumps(cfg))
    cfg2["power_accuracy"].update({"roll_off": 0.35, "modulation": "8psk",
                                   "fec_rate": "3/4", "frame_size": "short", "pilot": "no"})
    fm2 = FakeModulator()
    chk.modulator_setup(fm2, cfg2)
    for expected_cmd in ("roll-off 0.35", "modulation 8psk", "fec-rate 3/4",
                         "frame-size short", "pilot no"):
        assert expected_cmd in fm2.sent, fm2.sent

    # set_output_level_mode=true opts back in explicitly (now off by default).
    cfg3 = json.loads(json.dumps(cfg))
    cfg3["power_accuracy"]["set_output_level_mode"] = True
    fm3 = FakeModulator()
    chk.modulator_setup(fm3, cfg3)
    assert "output-level-mode constant-power" in fm3.sent, fm3.sent
    # Still returns to -line- afterward regardless.
    assert fm3.sent[-3:] == ["top", "-modulator-config", "line"], fm3.sent
    print("power: modulator setup OK (legacy sequence/order, config-driven values, "
          "output-level-mode off by default, returns to -line- for freq/power)")


def test_power_atten_interpolation():
    """Stage 5: link attenuation interpolates linearly between per-band start/stop
    anchors instead of a flat constant; default config (no *_start_db/*_stop_db keys)
    falls back to the exact flat behaviour (both endpoints equal); values outside the
    anchor range clamp to the nearer endpoint rather than extrapolating.
    """
    cfg = load_cfg(); chk = get_check("power_accuracy")()
    pa = dict(cfg["power_accuracy"])
    pa.update({
        "if_atten_start_mhz": 50.0, "if_atten_stop_mhz": 180.0,
        "if_atten_start_db": 5.80, "if_atten_stop_db": 5.89,
        "lband_atten_start_mhz": 950.0, "lband_atten_stop_mhz": 2150.0,
        "lband_atten_start_db": 3.37, "lband_atten_stop_db": 3.59,
    })
    # Reference-anchor endpoints match exactly.
    assert abs(chk._atten(pa, 50.0) - 5.80) < 1e-9
    assert abs(chk._atten(pa, 180.0) - 5.89) < 1e-9
    assert abs(chk._atten(pa, 950.0) - 3.37) < 1e-9
    assert abs(chk._atten(pa, 2150.0) - 3.59) < 1e-9
    # Midpoint interpolates linearly.
    mid_if = chk._atten(pa, 115.0)  # halfway between 50 and 180 MHz
    assert abs(mid_if - (5.80 + 5.89) / 2) < 1e-6, mid_if
    # Outside the calibrated range clamps to the nearer endpoint, doesn't extrapolate.
    assert chk._atten(pa, 10.0) == chk._atten(pa, 50.0)
    assert chk._atten(pa, 2500.0) == chk._atten(pa, 2150.0)
    # Default config (new keys absent) must be an EXACT flat fallback.
    pa_default = cfg["power_accuracy"]
    assert chk._atten(pa_default, 60.0) == chk._atten(pa_default, 170.0) == float(pa_default["if_atten_db"])
    assert chk._atten(pa_default, 1000.0) == chk._atten(pa_default, 2100.0) == float(pa_default["lband_atten_db"])
    print("power: attenuation interpolation OK (matches reference anchors, clamps outside range, flat fallback exact)")


def test_power_adc_cross_check():
    """Stage 5: DUT-side ADC power cross-check is read per point (diagnostic only,
    independent of the CXA reading), flows through to the CSV column, is gated by
    read_adc_power (default on), and - bench-confirmed 2026-08-26 - always navigates
    back to -line- afterward (even on a read failure), since -adc-power leaves the CLI
    parked in a submenu where the *next* point's freq/power would otherwise fail.
    """
    cfg = load_cfg(); chk = get_check("power_accuracy")()
    fa = FakeAnalyzer()
    point = {"index": 0, "freq_mhz": 950.0, "set_dbm": 0}
    fm = FakeModulator(replies={"get-power": "power: -12.34 dBm"})
    chk.prepare_point(fm, fa, cfg, point)
    assert "-adc-power" in fm.sent and "get-power" in fm.sent, fm.sent
    assert point["adc_power_dbm"] == "-12.34", point
    assert fm.sent[-3:] == ["top", "-modulator-config", "line"], fm.sent

    # Navigation back happens even when the ADC read itself fails.
    fm_fail = FakeModulator(fail_on_cmd="get-power")
    point_fail = {"index": 0, "freq_mhz": 950.0, "set_dbm": 0}
    chk.prepare_point(fm_fail, fa, cfg, point_fail)
    assert point_fail.get("adc_power_dbm") is None, point_fail
    assert fm_fail.sent[-3:] == ["top", "-modulator-config", "line"], fm_fail.sent

    meas = chk.measure_point(fa, cfg, point, "auto", {})
    assert meas.get("adc_power_dbm") == "-12.34", meas
    row = chk.row_for({"point": point, "meas": meas, "eval": {}})
    assert row["ADC_Power_dBm"] == "-12.34", row

    # Gated off -> no DUT-side read at all.
    cfg_off = json.loads(json.dumps(cfg))
    cfg_off["power_accuracy"]["read_adc_power"] = False
    fm2 = FakeModulator(replies={"get-power": "power: -12.34 dBm"})
    point2 = {"index": 0, "freq_mhz": 950.0, "set_dbm": 0}
    chk.prepare_point(fm2, fa, cfg_off, point2)
    assert not any(c in ("-adc-power", "get-power") for c in fm2.sent), fm2.sent
    assert point2.get("adc_power_dbm") is None, point2
    print("power: ADC cross-check OK (read per point, flows to CSV column, gate skips it when off)")


def test_power_atten_and_points():
    cfg = load_cfg(); chk = get_check("power_accuracy")()
    pa = cfg["power_accuracy"]
    pts = chk.build_points(cfg, [950, 60], {})
    levels = chk._levels(pa)
    assert len(pts) == 2 * len(levels)
    fa = FakeAnalyzer()
    # Feed a manual reading that exactly cancels each band's configured attenuator, so a
    # correct compensation always nets to 0 dBm regardless of what the atten values are.
    if_atten, lb_atten = float(pa["if_atten_db"]), float(pa["lband_atten_db"])
    m_if = chk.measure_point(fa, cfg, {"freq_mhz": 60, "set_dbm": 0}, "manual", {"measured_dbm": -if_atten})
    m_lb = chk.measure_point(fa, cfg, {"freq_mhz": 950, "set_dbm": 0}, "manual", {"measured_dbm": -lb_atten})
    assert abs(m_if["measured_dbm"]) < 1e-6 and abs(m_lb["measured_dbm"]) < 1e-6
    print("power: OK (multi-freq points, IF/L-band attenuator compensation)")


# ------------------------------------------------------------- iq validation

def test_iq_analyzer_setup():
    cfg = load_cfg(); chk = get_check("iq_validation")()
    fa = FakeAnalyzer()
    chk.analyzer_setup(fa, cfg, [{"index": 0, "freq_mhz": 957.0}])
    n = names(fa)
    # apply_ext_gain() (the old gated call) is no longer used by any check - replaced
    # by the per-check resolved+verified push, base.apply_check_ext_gain().
    assert "preset" in n and "preset_swept_sa" in n and "set_ext_gain" in n
    assert "apply_ext_gain" not in n, n
    assert ("set_ref_level", (cfg["iq_validation"]["ref_level_dbm"],)) in fa.calls
    assert ("set_bw", (cfg["iq_validation"]["res_bw_hz"], cfg["iq_validation"]["video_bw_hz"])) in fa.calls
    print("iq: analyzer_setup OK (preset/gain/ref-level/bw applied)")


def test_iq_marker_delta_sequence():
    cfg = load_cfg(); chk = get_check("iq_validation")()
    fa = FakeAnalyzer()
    m = chk.measure_point(fa, cfg, {"index": 0, "freq_mhz": 957.0}, "auto", {})
    seq = names(fa)
    assert seq[:2] == ["find_peak", "marker_to_delta"], seq
    # marker_to_delta() re-zeroes the reference to the main CW peak, so LOFT/Image are
    # read at the configured *absolute* offsets from that reference - not peak-relative.
    deltas = [c[1][0] for c in fa.calls if c[0] == "marker_delta_y_at_offset"]
    assert deltas == [cfg["iq_validation"]["loft_offset_hz"],
                      cfg["iq_validation"]["image_offset_hz"]], deltas
    assert "loft_dbc" in m and "image_dbc" in m
    print("iq: OK (find_peak -> delta, LOFT/Image read at configured offsets)")


# --------------------------------------------------- per-check external gain

def test_ext_gain_resolution_and_fallback():
    """Per-check ext_gain_db, falling back to the global analyzer.ext_gain_db when a
    check has no override of its own - NOT to 0. power_accuracy has its own key
    (0, per Decision 5); flatness/iq_validation deliberately do not, so they must
    resolve to whatever the global value is, even when that's non-zero.
    """
    cfg = load_cfg()
    assert "ext_gain_db" in cfg["power_accuracy"], "power_accuracy must have its own key"
    assert "ext_gain_db" not in cfg["flatness"], "flatness must NOT have its own key"
    assert "ext_gain_db" not in cfg["iq_validation"], "iq_validation must NOT have its own key"

    assert check_base.resolve_ext_gain(cfg, "power_accuracy") == cfg["power_accuracy"]["ext_gain_db"]
    # Default global is 0 here, so exercise the fallback with a non-zero global too -
    # otherwise "falls back to 0" and "falls back to global" would be indistinguishable.
    cfg2 = json.loads(json.dumps(cfg))
    cfg2["analyzer"]["ext_gain_db"] = -3.5
    assert check_base.resolve_ext_gain(cfg2, "flatness") == -3.5
    assert check_base.resolve_ext_gain(cfg2, "iq_validation") == -3.5
    # power_accuracy's own key still wins over the (now different) global.
    assert check_base.resolve_ext_gain(cfg2, "power_accuracy") == cfg["power_accuracy"]["ext_gain_db"]
    print("ext gain: resolution OK (per-check key wins; absent key falls back to "
          "global, not to 0)")


def test_ext_gain_pushed_per_check():
    """Each of the three checks' analyzer_setup() actually pushes its resolved ext
    gain via set_ext_gain(), independent of the others - the state-leakage fix. Also
    confirms the push is read back and logged (verification requirement).
    """
    cfg = json.loads(json.dumps(load_cfg()))
    cfg["analyzer"]["ext_gain_db"] = -3.5  # non-zero global, so flatness/iq's push is
                                            # distinguishable from a stale 0 default.
    # flatness/iq_validation have no override of their own -> resolve to the global.
    # power_accuracy has its own key -> resolves to that instead, ignoring the global.
    for check_key, expected in (("flatness", -3.5), ("iq_validation", -3.5),
                                ("power_accuracy", cfg["power_accuracy"]["ext_gain_db"])):
        chk = get_check(check_key)()
        fa = FakeAnalyzer()
        if check_key == "flatness":
            chk.analyzer_setup(fa, cfg, chk.build_points(cfg, [], {}))
        elif check_key == "iq_validation":
            chk.analyzer_setup(fa, cfg, [{"index": 0, "freq_mhz": 957.0}])
        else:
            chk.analyzer_setup(fa, cfg, [{"index": 0, "freq_mhz": 950.0}])
        assert ("set_ext_gain", (expected,)) in fa.calls, (check_key, fa.calls)
        assert any("ext gain" in m for m in fa.log.infos), (check_key, fa.log.infos)
    print("ext gain: pushed per-check OK (flatness/power_accuracy/iq_validation each "
          "push their own resolved value, read back and logged)")


def test_ext_gain_readback_mismatch_warns():
    """A read-back that differs from the pushed value by more than 0.01 dB logs a
    WARNING; a matching (or near-matching, within 0.01 dB) read-back does not.
    """
    cfg = load_cfg()
    fa_mismatch = FakeAnalyzer(ext_gain_readback=1.23)  # pushed value will be 0
    resolved = check_base.apply_check_ext_gain(fa_mismatch, cfg, "power_accuracy")
    assert resolved == cfg["power_accuracy"]["ext_gain_db"]
    assert any("mismatch" in m for m in fa_mismatch.log.warnings), fa_mismatch.log.warnings

    fa_match = FakeAnalyzer()  # no override -> query_number reflects exactly what was pushed
    check_base.apply_check_ext_gain(fa_match, cfg, "power_accuracy")
    assert not fa_match.log.warnings, fa_match.log.warnings

    fa_close = FakeAnalyzer(ext_gain_readback=0.005)  # within the 0.01 dB tolerance
    check_base.apply_check_ext_gain(fa_close, cfg, "power_accuracy")
    assert not fa_close.log.warnings, fa_close.log.warnings
    print("ext gain: read-back mismatch OK (warns beyond 0.01 dB, silent within tolerance)")


if __name__ == "__main__":
    test_flatness_fixed_freqs()
    test_flatness_per_point_isolation()
    test_flatness_prepare_error_isolation()
    test_flatness_peak_table_gate()
    test_power_levels()
    test_power_chp_scoped_nodes()
    test_power_chp_read_retry()
    test_power_modulator_setup()
    test_power_atten_interpolation()
    test_power_adc_cross_check()
    test_power_atten_and_points()
    test_iq_analyzer_setup()
    test_iq_marker_delta_sequence()
    test_ext_gain_resolution_and_fallback()
    test_ext_gain_pushed_per_check()
    test_ext_gain_readback_mismatch_warns()
    print("\nALL TESTS PASSED")
