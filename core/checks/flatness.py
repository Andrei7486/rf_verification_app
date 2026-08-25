"""Check 1 - Flatness (fixed 950-2150/50; L-band atten; on-screen Peak Table)."""
import time
from . import base
class FlatnessCheck:
    key = "flatness"
    title = "Flatness"
    final_only = True
    uses_freq_list = False
    manual_fields = [{"name": "measured_dbm", "label": "Carrier level (dBm)", "step": "0.01"}]
    csv_columns = ["Frequency_MHz", "Measured_dBm", "Dev_from_mean_dB", "Result"]
    def __init__(self):
        # The MAX HOLD trace covering the whole band is reset once, in analyzer_setup(),
        # before the DUT has been tuned to the first point. Reading the trace before it
        # has swept at least once since that first tune returns stale/noise-floor data -
        # most visible at the low edge of the span (the first point, e.g. 950 MHz), which
        # is why only that point looked wrong while the rest of the run was fine. These
        # track whether that first post-tune sweep has actually happened yet.
        self._sweep_time_s = None
        self._first_point_settled = False
    def fixed_freqs(self, cfg):
        fc = cfg["flatness"]
        start = float(fc.get("flat_band_start_mhz", 950))
        stop = float(fc.get("flat_band_stop_mhz", 2150))
        step = float(fc.get("flat_step_mhz", 50)) or 50.0
        # start + i*step (not a += accumulator) so float error can't drift the grid
        # over a long run - each point is computed fresh from start, never chained.
        n = max(1, int(round((stop - start) / step)) + 1)
        return [round(start + i * step, 3) for i in range(n)]
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
        # Best-effort: know how long one full sweep across this (wide) span actually
        # takes, so prepare_point() can tell whether the fixed per-point dwell is
        # enough for that first, still-empty sweep to have covered it. A read failure
        # here must never break the run - the check just falls back to dwell_s alone.
        try:
            self._sweep_time_s = cxa.get_sweep_time()
            cxa.log.info("Flatness: CXA coupled sweep time = %.3f s over %.1f-%.1f MHz",
                         self._sweep_time_s, start / 1e6, stop / 1e6)
        except Exception as exc:
            self._sweep_time_s = None
            cxa.log.warning("Flatness: could not read sweep time (%s); "
                            "first-point settle falls back to dwell_s only", exc)
    def prepare_point(self, mod, cxa, cfg, point):
        fc = cfg["flatness"]
        dwell = float(fc["dwell_s"])
        try:
            mod.send("freq %s" % point["freq_mhz"], wait=dwell)
        except Exception as exc:
            # Tuning the DUT failed - record it on the point and let measure_point()
            # turn it into a FAIL below, instead of raising out of prepare_point() and
            # aborting session._auto_loop()'s whole run over one bad point.
            point["_prepare_error"] = str(exc)
            cxa.log.error("Flatness: prepare failed at %.3f MHz: %s", point["freq_mhz"], exc)
            return
        if not self._first_point_settled:
            self._first_point_settled = True
            if self._sweep_time_s:
                margin = float(fc.get("sweep_settle_margin", 1.15))
                extra = self._sweep_time_s * margin - dwell
                if extra > 0:
                    cxa.log.info("Flatness: first point (%.3f MHz) - waiting %.2fs more so a "
                                 "full sweep completes with the carrier already tuned "
                                 "(sweep time %.2fs, dwell %.2fs)",
                                 point["freq_mhz"], extra, self._sweep_time_s, dwell)
                    time.sleep(extra)
    def measure_point(self, cxa, cfg, point, mode, manual):
        fc = cfg["flatness"]; atten = float(fc.get("lband_atten_db", 0))
        if point.get("_prepare_error"):
            return {"error": point["_prepare_error"]}
        if mode == "auto":
            try:
                level = cxa.marker_level_at(point["freq_mhz"] * 1e6)
            except Exception as exc:
                # A bad CXA read must not kill the rest of the run (matches the
                # error-in-meas isolation pattern power_accuracy/iq_validation use) -
                # this point is reported as FAIL and the loop continues.
                cxa.log.error("Flatness: measurement failed at %.3f MHz: %s",
                              point["freq_mhz"], exc)
                return {"error": str(exc)}
            if bool(fc.get("enable_peak_table_logging", False)):
                # Diagnostics only - never allowed to fail the point itself.
                try:
                    table = cxa.get_peak_table()
                    cxa.log.info("Flatness: peak table @ %.3f MHz: %s",
                                 point["freq_mhz"], table)
                except Exception as exc:
                    cxa.log.warning("Flatness: peak table read failed at %.3f MHz: %s",
                                    point["freq_mhz"], exc)
        else:
            level = float(manual["measured_dbm"])
        return {"measured_dbm": round(level + atten, 2)}
    def evaluate_point(self, cfg, point, meas):
        if meas.get("error"):
            return {"result": "FAIL", "flag": True, "note": meas["error"]}
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
