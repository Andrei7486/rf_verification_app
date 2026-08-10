"""Check 1 - Flatness (fixed 950-2150/50; L-band atten; on-screen Peak Table)."""
from . import base
class FlatnessCheck:
    key = "flatness"
    title = "Flatness"
    final_only = True
    uses_freq_list = False
    manual_fields = [{"name": "measured_dbm", "label": "Carrier level (dBm)", "step": "0.01"}]
    csv_columns = ["Frequency_MHz", "Measured_dBm", "Dev_from_mean_dB", "Result"]
    def fixed_freqs(self, cfg):
        fc = cfg["flatness"]
        start = float(fc.get("flat_band_start_mhz", 950))
        stop = float(fc.get("flat_band_stop_mhz", 2150))
        step = float(fc.get("flat_step_mhz", 50)) or 50.0
        freqs, f = [], start
        while f <= stop + 1e-9:
            freqs.append(round(f, 3)); f += step
        return freqs
    def build_points(self, cfg, freqs, params):
        return [{"index": i, "freq_mhz": f} for i, f in enumerate(self.fixed_freqs(cfg))]
    def modulator_setup(self, mod, cfg):
        base.clean_carrier_setup(mod, cfg["flatness"]["flat_power_dbm"])
    def analyzer_setup(self, cxa, cfg, points):
        fc = cfg["flatness"]
        margin = float(fc.get("span_margin_mhz", 30)) * 1e6
        start = min(p["freq_mhz"] for p in points) * 1e6 - margin
        stop = max(p["freq_mhz"] for p in points) * 1e6 + margin
        cxa.preset()
        cxa.preset_swept_sa()
        cxa.apply_ext_gain()
        cxa.set_ref_level(fc["ref_level_dbm"])
        cxa.set_scale_div(fc["scale_div_db"])
        cxa.set_start_stop(start, stop)
        cxa.set_bw(fc["res_bw_hz"], fc["video_bw_hz"])
        cxa.set_detector_peak()
        cxa.restart_max_hold()
        cxa.enable_peak_table()
    def prepare_point(self, mod, cxa, cfg, point):
        mod.send("freq %s" % point["freq_mhz"], wait=cfg["flatness"]["dwell_s"])
    def measure_point(self, cxa, cfg, point, mode, manual):
        fc = cfg["flatness"]; atten = float(fc.get("lband_atten_db", 0))
        if mode == "auto":
            level = cxa.marker_level_at(point["freq_mhz"] * 1e6)
        else:
            level = float(manual["measured_dbm"])
        return {"measured_dbm": round(level + atten, 2)}
    def evaluate_point(self, cfg, point, meas):
        return {}
    def finalize(self, cfg, results):
        levels = [r["meas"]["measured_dbm"] for r in results if "measured_dbm" in r["meas"]]
        if not levels:
            return {"verdict": "N/A", "note": "No levels captured"}
        max_v, min_v = max(levels), min(levels)
        pk_pk = round(max_v - min_v, 2); mean_v = sum(levels) / len(levels)
        tol = float(cfg["flatness"]["flat_tolerance_db"])
        verdict = "PASS" if pk_pk <= tol else "FAIL"
        for r in results:
            lvl = r["meas"].get("measured_dbm")
            if lvl is None:
                continue
            r["eval"]["dev_from_mean"] = round(lvl - mean_v, 2)
            if lvl == max_v:
                r["eval"]["result"], r["eval"]["flag"] = "MAX", True
            elif lvl == min_v:
                r["eval"]["result"], r["eval"]["flag"] = "MIN", True
            else:
                r["eval"]["result"], r["eval"]["flag"] = "", False
        return {"verdict": verdict, "max_dbm": max_v, "min_dbm": min_v,
                "pk_pk_db": pk_pk, "tolerance_db": tol}
    def cleanup(self, mod, cfg):
        base.clean_carrier_cleanup(mod)
    def row_for(self, result):
        ev = result["eval"]
        return {"Frequency_MHz": result["point"]["freq_mhz"],
                "Measured_dBm": result["meas"].get("measured_dbm", ""),
                "Dev_from_mean_dB": ev.get("dev_from_mean", ""),
                "Result": ev.get("result", "")}
