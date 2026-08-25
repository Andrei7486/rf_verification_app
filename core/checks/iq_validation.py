"""Check 3 - IQ validation (LOFT / Image), aligned with the legacy StartValidation flow.

Sequence per frequency point (mirrors the old Java IQ Cal tool):

    CXA : center = F, span, write trace (legacy did not use MAX HOLD here)
    DUT : top -> modulator-config -> line -> freq F -> -dac -> freq <DAC tone> -> dac-i/dac-q
    DUT : -direct -> get dac phase_control / get dac output_offset   (diagnostics only)
    CXA : peak search -> main CW level, sanity-checked against F + DAC tone
    CXA : marker -> DELTA, delta X = loft_offset_hz                 => LOFT  (dBc)
    CXA : center = F - image_center_shift_hz
    CXA : delta X = image_offset_hz                                 => IMAGE (dBc)

Everything test-specific stays here; analyzer.py / modulator.py remain generic layers.
Every tunable is read from cfg["iq_validation"] with a code-side default, so an external
config written before these keys existed keeps working unchanged.
"""

import re
import time

from . import base

# Matches a plain or exponential number anywhere in a CLI reply.
_NUM_RE = re.compile(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?")


def _num(iq, key, default):
    """Read a numeric config value, falling back to the code default if absent/bad."""
    try:
        return float(iq.get(key, default))
    except (TypeError, ValueError):
        return float(default)


class IqValidationCheck:
    key = "iq_validation"
    title = "IQ validation"
    final_only = False
    uses_freq_list = True
    manual_fields = [
        {"name": "image_dbc", "label": "Image (dBc, e.g. -60)", "step": "0.1"},
        {"name": "loft_dbc", "label": "LOFT (dBc, e.g. -60)", "step": "0.1"},
    ]
    csv_columns = ["Frequency_MHz", "Main_CW_dBm", "Phase_Correction", "LOFT_Correction",
                   "Image_dBc", "LOFT_dBc", "Result"]

    def __init__(self):
        # Reference level is adapted to the real DUT level once, on the first point.
        self._ref_done = False

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
        cxa.set_ref_level(_num(iq, "ref_level_dbm", 0))
        cxa.set_bw(iq["res_bw_hz"], iq["video_bw_hz"])
        cxa.set_detector_peak()
        loft_limit, image_limit = self._limits(cfg)
        cxa.log.info("IQ limits: LOFT <= %.2f dBc, IMAGE <= %.2f dBc, main CW >= %.2f dBm",
                     loft_limit, image_limit, _num(iq, "main_cw_min_dbm", -20.0))

    # ------------------------------------------------------------------ per point

    def prepare_point(self, mod, cxa, cfg, point):
        iq = cfg["iq_validation"]
        center_hz = float(point["freq_mhz"]) * 1e6
        dac_hz = _num(iq, "iq_dac_freq_hz", 1e6)
        dwell = _num(iq, "dwell_s", 1.0)

        cxa.set_center_span(center_hz, _num(iq, "span_hz", 2.5e6))
        # Legacy StartValidation measured on a live (write) trace. MAX HOLD accumulates
        # noise peaks and can turn a passing spur into a failing one, so it is opt-in.
        if bool(iq.get("use_max_hold", False)):
            cxa.restart_max_hold()
        else:
            cxa.set_write_trace()

        if bool(iq.get("use_legacy_nav", True)):
            # Legacy navigation: full path from the CLI root on every point, because the
            # NS CLI interprets a command relative to the menu it is currently in.
            mod.send("top")
            mod.send("modulator-config")
            mod.send("line")
            mod.send("freq %s" % point["freq_mhz"])
            mod.send("-dac")
            mod.send("freq %d" % int(dac_hz))
            mod.send("dac-i %s" % iq["iq_dac_i"])
            mod.send("dac-q %s" % iq["iq_dac_q"], wait=dwell)
        else:
            # Pre-legacy path: stay inside the -calib- menu opened by base.iq_setup().
            mod.send("freq %s" % point["freq_mhz"])
            mod.send("dac-freq %d" % int(dac_hz))
            mod.send("dac-i %s" % iq["iq_dac_i"])
            mod.send("dac-q %s" % iq["iq_dac_q"], wait=dwell)

        phase, loft_corr = self._read_corrections(mod, iq)
        point["phase_correction"] = phase
        point["loft_correction"] = loft_corr
        self._auto_ref_level(cxa, iq, point)

    def _read_corrections(self, mod, iq):
        """Fetch the DAC phase / LOFT correction the DUT applied at this point.

        Diagnostics only - a CLI that does not answer must never break the measurement.
        """
        if not bool(iq.get("read_corrections", True)):
            return None, None
        try:
            mod.send("-direct")
            phase = self._parse_correction(mod.send("get dac phase_control"), "phase_control")
            loft_corr = self._parse_correction(mod.send("get dac output_offset"), "output_offset")
        except Exception as exc:  # transport hiccup on a non-critical read
            mod.log.warning("Corrections not read: %s", exc)
            return None, None
        if phase is None:
            mod.log.warning("Phase correction not parsed from DUT reply (stored as N/A)")
        if loft_corr is None:
            mod.log.warning("LOFT correction not parsed from DUT reply (stored as N/A)")
        return phase, loft_corr

    @staticmethod
    def _parse_correction(text, name):
        """Pull '<name> = <value>' out of a CLI reply; fall back to its last number."""
        if not text:
            return None
        match = re.search(re.escape(name) + r"\s*[:=]\s*(\S+)", text, re.I)
        if match:
            return match.group(1).strip().rstrip(",;")
        # Drop the echoed command lines, then take the last number that remains.
        body = "\n".join(ln for ln in text.splitlines() if name.lower() not in ln.lower())
        nums = _NUM_RE.findall(body)
        return nums[-1] if nums else None

    def _auto_ref_level(self, cxa, iq, point):
        """Legacy behaviour: set RLEV = main peak + margin, once, on the first point."""
        if self._ref_done or not bool(iq.get("auto_ref_level_from_peak", True)):
            return
        lo = _num(iq, "ref_level_peak_min_dbm", -12.0)
        hi = _num(iq, "ref_level_peak_max_dbm", 10.0)
        tries = max(1, int(_num(iq, "ref_level_peak_retries", 3)))
        peak = None
        for attempt in range(1, tries + 1):
            _, peak = cxa.find_peak()
            if lo <= peak <= hi:
                break
            cxa.log.info("Ref-level peak search %d/%d: %.2f dBm outside %.1f..%.1f dBm",
                         attempt, tries, peak, lo, hi)
            time.sleep(0.2)
        self._ref_done = True
        if peak is None:
            return
        if not lo <= peak <= hi:
            cxa.log.warning("Main peak %.2f dBm still outside the expected %.1f..%.1f dBm "
                            "window; reference level follows the measured peak anyway",
                            peak, lo, hi)
        rlev = round(peak + _num(iq, "ref_level_margin_db", 1.0), 2)
        cxa.log.info("Reference level from peak at %.3f MHz: %.2f dBm",
                     float(point["freq_mhz"]), rlev)
        cxa.set_ref_level(rlev)

    # ------------------------------------------------------------------ measure

    def measure_point(self, cxa, cfg, point, mode, manual):
        iq = cfg["iq_validation"]
        if mode != "auto":
            meas = {"image_dbc": float(manual["image_dbc"]),
                    "loft_dbc": float(manual["loft_dbc"])}
            meas.update(self._corrections_of(point))
            return meas

        log = cxa.log
        center_hz = float(point["freq_mhz"]) * 1e6
        dac_hz = _num(iq, "iq_dac_freq_hz", 1e6)
        span_hz = _num(iq, "span_hz", 2.5e6)
        expected_hz = center_hz + dac_hz

        pk_hz, wanted = cxa.find_peak()
        diff_hz = pk_hz - expected_hz
        tol_hz = _num(iq, "peak_freq_tolerance_hz", 200000.0)
        log.info("IQ point: F=%.3f MHz | expected CW=%.6f MHz | measured CW=%.6f MHz "
                 "@ %.2f dBm | diff=%.1f kHz (tolerance %.1f kHz)",
                 point["freq_mhz"], expected_hz / 1e6, pk_hz / 1e6, wanted,
                 diff_hz / 1e3, tol_hz / 1e3)

        meas = {"wanted_dbm": round(wanted, 2),
                "peak_hz": round(pk_hz, 1),
                "peak_diff_hz": round(diff_hz, 1)}
        meas.update(self._corrections_of(point))

        if abs(diff_hz) > tol_hz:
            msg = ("Peak search did not land on the expected CW: expected %.6f MHz, "
                   "measured %.6f MHz, difference %.1f kHz, tolerance %.1f kHz"
                   % (expected_hz / 1e6, pk_hz / 1e6, diff_hz / 1e3, tol_hz / 1e3))
            if str(iq.get("peak_frequency_mismatch_action", "warning")).lower() == "fail":
                log.error(msg)
                meas["error"] = msg
                return meas
            log.warning(msg)

        min_cw = _num(iq, "main_cw_min_dbm", -20.0)
        if wanted < min_cw:
            # Against a too-weak reference the dBc figures are formally correct and
            # physically meaningless, so the point is rejected instead of measured.
            msg = ("Main CW level too low: frequency=%.6f MHz, measured=%.2f dBm, "
                   "minimum allowed=%.2f dBm" % (pk_hz / 1e6, wanted, min_cw))
            log.error(msg)
            if str(iq.get("main_cw_low_action", "fail")).lower() == "abort":
                raise ValueError(msg)
            meas["error"] = msg
            return meas

        # LOFT: delta marker referenced to the main CW, analyzer left where it is.
        cxa.marker_to_delta()
        loft_off = _num(iq, "loft_offset_hz", -1e6)
        loft = cxa.marker_delta_y_at_offset(loft_off)
        log.info("LOFT: delta offset=%+.3f MHz -> %.2f dBc", loft_off / 1e6, loft)

        # IMAGE: legacy retunes the analyzer below the carrier first, then reads -2 MHz.
        image_center = center_hz - _num(iq, "image_center_shift_hz", dac_hz)
        cxa.set_center_span(image_center, span_hz)
        image_off = _num(iq, "image_offset_hz", -2e6)
        image = cxa.marker_delta_y_at_offset(image_off)
        log.info("IMAGE: center=%.6f MHz, delta offset=%+.3f MHz -> %.2f dBc",
                 image_center / 1e6, image_off / 1e6, image)

        meas["loft_dbc"] = round(loft, 2)
        meas["image_dbc"] = round(image, 2)
        return meas

    @staticmethod
    def _corrections_of(point):
        return {"phase_correction": point.get("phase_correction"),
                "loft_correction": point.get("loft_correction")}

    # ------------------------------------------------------------------ verdict

    @staticmethod
    def _limits(cfg):
        """LOFT and Image limits, each falling back to the common iq_spur_limit_dbc."""
        iq = cfg["iq_validation"]
        common = _num(iq, "iq_spur_limit_dbc", -55.0)
        return _num(iq, "loft_limit_dbc", common), _num(iq, "image_limit_dbc", common)

    def evaluate_point(self, cfg, point, meas):
        loft_limit, image_limit = self._limits(cfg)
        base_eval = {"loft_limit_dbc": loft_limit, "image_limit_dbc": image_limit}
        if meas.get("error") or "loft_dbc" not in meas or "image_dbc" not in meas:
            base_eval.update({"result": "FAIL", "flag": True,
                              "note": meas.get("error", "Measurement incomplete")})
            return base_eval
        loft_ok = meas["loft_dbc"] <= loft_limit
        image_ok = meas["image_dbc"] <= image_limit
        ok = loft_ok and image_ok
        base_eval.update({"result": "PASS" if ok else "FAIL", "flag": not ok,
                          "loft_ok": loft_ok, "image_ok": image_ok})
        return base_eval

    def finalize(self, cfg, results):
        loft_limit, image_limit = self._limits(cfg)
        any_fail = any(r["eval"].get("result") == "FAIL" for r in results)
        return {"verdict": "FAIL" if any_fail else "PASS",
                # Kept for older result readers that only know the common limit.
                "spur_limit_dbc": _num(cfg["iq_validation"], "iq_spur_limit_dbc", -55.0),
                "loft_limit_dbc": loft_limit,
                "image_limit_dbc": image_limit,
                "points": len(results)}

    def cleanup(self, mod, cfg):
        base.iq_cleanup(mod)

    def row_for(self, result):
        meas = result["meas"]
        phase = meas.get("phase_correction")
        loft_corr = meas.get("loft_correction")
        return {"Frequency_MHz": result["point"]["freq_mhz"],
                "Main_CW_dBm": meas.get("wanted_dbm", ""),
                "Phase_Correction": phase if phase is not None else "N/A",
                "LOFT_Correction": loft_corr if loft_corr is not None else "N/A",
                "Image_dBc": meas.get("image_dbc", ""),
                "LOFT_dBc": meas.get("loft_dbc", ""),
                "Result": result["eval"].get("result", "")}
