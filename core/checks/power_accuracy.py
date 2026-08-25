"""Check 2 - Power accuracy (multi-frequency; attenuator compensation; CHP)."""
from . import base
class PowerAccuracyCheck:
    key = "power_accuracy"
    title = "Power accuracy"
    final_only = False
    uses_freq_list = True
    manual_fields = [{"name": "measured_dbm", "label": "Measured level (dBm)", "step": "0.01"}]
    csv_columns = ["Frequency_MHz", "Set_dBm", "Actual_dBm", "Deviation_dB", "Result"]
    def _levels(self, pa):
        start = float(pa["pwr_start_dbm"]); stop = float(pa["pwr_stop_dbm"])
        step = abs(float(pa["pwr_step_db"])) or 1.0
        # start - i*step (not a -= accumulator) so float error can't drift the grid
        # over a long run - each level is computed fresh from start, never chained.
        n = max(1, int(round((start - stop) / step)) + 1)
        return [round(start - i * step, 3) for i in range(n)]
    def build_points(self, cfg, freqs, params):
        pa = cfg["power_accuracy"]; levels = self._levels(pa)
        freqs = sorted(float(f) for f in freqs)
        points, i = [], 0
        for f in freqs:
            for lvl in levels:
                points.append({"index": i, "freq_mhz": f, "set_dbm": lvl}); i += 1
        return points
    def modulator_setup(self, mod, cfg):
        base.enter_expert(mod)
        mod.send("-modulator-config")
        mod.send("line")
        mod.send("sine off")
        mod.send("symbol-rate 4")
        mod.send("tx enable")
    def analyzer_setup(self, cxa, cfg, points):
        pa = cfg["power_accuracy"]
        cxa.preset()
        cxa.command(":CONF:CHP")
        cxa.command(":CHP:BAND:INT %d" % int(pa["chp_integ_bw_hz"]))
        cxa.command(":CHP:SWE:TIME:AUTO OFF")
        cxa.command(":CHP:SWE:TIME %s" % pa["sweep_time_s"])
        cxa.apply_ext_gain()
        cxa.set_ref_level(pa["ref_level_dbm"])
        # CHP-scoped span/RBW/VBW, not the generic :FREQ:SPAN/:BWID/:BWID:VID nodes - the
        # Channel Power measurement keeps its own copy of these, separate from the Spectrum
        # measurement's state that the generic setters (used by flatness/iq_validation) write
        # to. Span is constant for the whole run, so it's set once here rather than resent
        # every point (see prepare_point()'s set_center_freq()).
        cxa.set_chp_span(pa["span_hz"])
        cxa.set_chp_bw(pa["res_bw_hz"], pa["video_bw_hz"])
    def prepare_point(self, mod, cxa, cfg, point):
        pa = cfg["power_accuracy"]
        cxa.set_center_freq(point["freq_mhz"] * 1e6)
        mod.send("freq %s" % point["freq_mhz"])
        mod.send("power %s" % point["set_dbm"], wait=pa["dwell_s"])
    def _atten(self, pa, freq_mhz):
        if freq_mhz <= float(pa.get("if_max_mhz", 180)):
            return float(pa.get("if_atten_db", 0))
        return float(pa.get("lband_atten_db", 0))
    def measure_point(self, cxa, cfg, point, mode, manual):
        pa = cfg["power_accuracy"]
        if mode == "auto":
            level = cxa.read_chp()
        else:
            level = float(manual["measured_dbm"])
        level = round(level + self._atten(pa, point["freq_mhz"]), 2)
        deviation = round(level - point["set_dbm"], 2)
        return {"measured_dbm": level, "deviation_db": deviation}
    def evaluate_point(self, cfg, point, meas):
        tol = float(cfg["power_accuracy"]["pwr_tolerance_db"])
        passed = abs(meas["deviation_db"]) <= tol
        return {"result": "PASS" if passed else "FAIL", "flag": not passed}
    def finalize(self, cfg, results):
        any_fail = any(r["eval"].get("result") == "FAIL" for r in results)
        return {"verdict": "FAIL" if any_fail else "PASS",
                "tolerance_db": float(cfg["power_accuracy"]["pwr_tolerance_db"]),
                "steps": len(results)}
    def cleanup(self, mod, cfg):
        base.clean_carrier_cleanup(mod)
    def row_for(self, result):
        return {"Frequency_MHz": result["point"]["freq_mhz"],
                "Set_dBm": result["point"]["set_dbm"],
                "Actual_dBm": result["meas"].get("measured_dbm", ""),
                "Deviation_dB": result["meas"].get("deviation_db", ""),
                "Result": result["eval"].get("result", "")}
