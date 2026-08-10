"""Check 3 - IQ validation (preset; marker position fix for Image/LOFT)."""
from . import base
class IqValidationCheck:
    key = "iq_validation"
    title = "IQ validation"
    final_only = False
    uses_freq_list = True
    manual_fields = [
        {"name": "image_dbc", "label": "Image (dBc, e.g. -60)", "step": "0.1"},
        {"name": "loft_dbc", "label": "LOFT (dBc, e.g. -60)", "step": "0.1"},
    ]
    csv_columns = ["Frequency_MHz", "Image_dBc", "LOFT_dBc", "Result"]
    def build_points(self, cfg, freqs, params):
        return [{"index": i, "freq_mhz": float(f)}
                for i, f in enumerate(sorted(float(x) for x in freqs))]
    def modulator_setup(self, mod, cfg):
        base.iq_setup(mod, cfg["iq_validation"]["iq_power_dbm"])
    def analyzer_setup(self, cxa, cfg, points):
        iq = cfg["iq_validation"]
        cxa.preset()
        cxa.preset_swept_sa()
        cxa.apply_ext_gain()
        cxa.set_ref_level(iq["ref_level_dbm"])
        cxa.set_bw(iq["res_bw_hz"], iq["video_bw_hz"])
        cxa.set_detector_peak()
    def prepare_point(self, mod, cxa, cfg, point):
        iq = cfg["iq_validation"]
        cxa.set_center_span(point["freq_mhz"] * 1e6, iq["span_hz"])
        cxa.restart_max_hold()
        mod.send("freq %s" % point["freq_mhz"])
        mod.send("dac-freq %s" % iq["iq_dac_freq_hz"])
        mod.send("dac-i %s" % iq["iq_dac_i"])
        mod.send("dac-q %s" % iq["iq_dac_q"], wait=iq["dwell_s"])
    def measure_point(self, cxa, cfg, point, mode, manual):
        iq = cfg["iq_validation"]
        if mode == "auto":
            center = point["freq_mhz"] * 1e6; dac = float(iq["iq_dac_freq_hz"])
            loft_off = float(iq.get("loft_offset_hz", 0))
            wanted = cxa.marker_level_at(center + dac)
            image = cxa.marker_level_at(center - dac)
            loft = cxa.marker_level_at(center + loft_off)
            return {"wanted_dbm": round(wanted, 2),
                    "image_dbc": round(image - wanted, 2),
                    "loft_dbc": round(loft - wanted, 2)}
        return {"image_dbc": float(manual["image_dbc"]),
                "loft_dbc": float(manual["loft_dbc"])}
    def evaluate_point(self, cfg, point, meas):
        limit = float(cfg["iq_validation"]["iq_spur_limit_dbc"])
        ok = (meas["image_dbc"] <= limit) and (meas["loft_dbc"] <= limit)
        return {"result": "PASS" if ok else "FAIL", "flag": not ok}
    def finalize(self, cfg, results):
        any_fail = any(r["eval"].get("result") == "FAIL" for r in results)
        return {"verdict": "FAIL" if any_fail else "PASS",
                "spur_limit_dbc": float(cfg["iq_validation"]["iq_spur_limit_dbc"]),
                "points": len(results)}
    def cleanup(self, mod, cfg):
        base.iq_cleanup(mod)
    def row_for(self, result):
        return {"Frequency_MHz": result["point"]["freq_mhz"],
                "Image_dBc": result["meas"].get("image_dbc", ""),
                "LOFT_dBc": result["meas"].get("loft_dbc", ""),
                "Result": result["eval"].get("result", "")}
