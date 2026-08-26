"""Check 2 - Power accuracy (multi-frequency; attenuator compensation; CHP)."""
import time
from . import base
class PowerAccuracyCheck:
    key = "power_accuracy"
    title = "Power accuracy"
    final_only = False
    uses_freq_list = True
    manual_fields = [{"name": "measured_dbm", "label": "Measured level (dBm)", "step": "0.01"}]
    csv_columns = ["Frequency_MHz", "Set_dBm", "Actual_dBm", "Deviation_dB",
                   "ADC_Power_dBm", "Result"]
    def __init__(self):
        # Actual (possibly auto-coupled) CHP sweep time, queried once in analyzer_setup()
        # and used by _read_chp_with_retry() to size the settle wait after each
        # :INIT:REST - same "query, don't assume" pattern as flatness.py's sweep-time fix.
        self._chp_sweep_time_s = None
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
        pa = cfg["power_accuracy"]
        base.enter_expert(mod)
        # 'top' first, unlike the old minimal setup - starts from the CLI root menu
        # regardless of what menu another check (e.g. iq_validation's -calib- path) left
        # the modulator in, matching legacy startValidate's own navigation.
        mod.send("top")
        mod.send("-modulator-config")
        mod.send("line")
        # Legacy order: tx enable before sine off - replicated as given rather than kept
        # in our old order, since legacy's bench-tested reference results were produced
        # with the carrier enabled first.
        mod.send("tx enable")
        mod.send("sine off")
        mod.send("symbol-rate 4")
        mod.send("roll-off %s" % pa.get("roll_off", 0.25))
        mod.send("dual-channel-mode single-ch")
        mod.send("-channel-1")
        mod.send("state enable")
        mod.send("source test-pattern")
        mod.send("modulation %s" % pa.get("modulation", "qpsk"))
        mod.send("frame-size %s" % pa.get("frame_size", "normal"))
        mod.send("fec-rate %s" % pa.get("fec_rate", "2/3"))
        mod.send("pilot %s" % pa.get("pilot", "yes"))
        if bool(pa.get("set_output_level_mode", False)):
            # Decision 4 originally defaulted this True (determinism over literal legacy
            # parity). Defaulted to False here instead: bench-confirmed on 2026-08-26 that
            # 'output-level-mode constant-power' - the best-effort guess this sent, since
            # legacy never sets this at all and there was no decompiled string to copy -
            # gets 'command not found' from the real CLI. Sending a known-wrong command
            # achieves nothing, so it's off by default until the correct syntax is known;
            # the mechanism stays in place, opt back in via config once
            # power_accuracy.output_level_mode_cmd is corrected to something the unit
            # actually accepts.
            cmd = pa.get("output_level_mode_cmd", "output-level-mode constant-power")
            mod.log.warning("Power accuracy: Output Level Mode CLI syntax is unverified "
                            "(no legacy reference exists for it) - sending %r; confirm on "
                            "the bench and fix power_accuracy.output_level_mode_cmd if wrong",
                            cmd)
            mod.send(cmd)
        # Return to the -line- menu the per-point freq/power commands expect. Bench-
        # confirmed on 2026-08-26: without this, prepare_point()'s "freq"/"power" commands
        # are sent while the CLI is still parked in -channel-1- (entered above to configure
        # state/source/modulation/frame-size/fec-rate/pilot) and get rejected with
        # "command not found" on every single point - the DUT never actually retunes or
        # releveled, so every measurement in a run was silently invalid. Same proven
        # navigation already used at the top of this function.
        mod.send("top")
        mod.send("-modulator-config")
        mod.send("line")
    def analyzer_setup(self, cxa, cfg, points):
        pa = cfg["power_accuracy"]
        cxa.preset()
        # Deterministic baseline init - NOT legacy parity. RLEV/POW:ATT/CORR:SA:GAIN come
        # from InitCalibration(), which belongs to startCalibrate, a different legacy tool
        # never called by startValidate (our actual reference). Legacy validation just
        # inherits whatever instrument state the calibration tool left behind; our app
        # can't rely on that the same way, since three checks share one CXA - this check
        # brings attenuation and external-gain correction to a known state on its own,
        # before entering the Channel Power measurement setup below. Sent power_accuracy-
        # local and unconditional (not gated by the global analyzer.apply_ext_gain flag,
        # which stays untouched so iq_validation's ext_gain_db=-3.5 path is unaffected).
        if bool(pa.get("atten_auto", True)):
            cxa.set_attenuation_auto(True)
        cxa.set_ext_gain(0)
        cxa.command(":CONF:CHP")
        cxa.command(":CHP:BAND:INT %d" % int(pa["chp_integ_bw_hz"]))
        # Sweep time left on AUTO (queried below) and averaging enabled, mirroring legacy
        # InitValidation() - stage 2 of the parity plan. chp_sweep_time_auto=false falls
        # back to the old forced-value behaviour for anyone who needs it.
        if bool(pa.get("chp_sweep_time_auto", True)):
            cxa.set_chp_sweep_time_auto(True)
        else:
            cxa.set_chp_sweep_time_auto(False)
            cxa.command_sync(":CHP:SWE:TIME %s" % pa["sweep_time_s"])
        cxa.set_chp_average(bool(pa.get("chp_average_on", True)),
                            int(pa.get("chp_average_count", 10)))
        # ref_level_dbm is NOT changed to 15 here - that value came from InitCalibration()
        # (startCalibrate), not the validation-path spec. Kept as our own configurable value.
        cxa.set_ref_level(pa["ref_level_dbm"])
        # CHP-scoped span/RBW/VBW, not the generic :FREQ:SPAN/:BWID/:BWID:VID nodes - the
        # Channel Power measurement keeps its own copy of these, separate from the Spectrum
        # measurement's state that the generic setters (used by flatness/iq_validation) write
        # to. Span is constant for the whole run, so it's set once here rather than resent
        # every point (see prepare_point()'s set_center_freq()).
        cxa.set_chp_span(pa["span_hz"])
        cxa.set_chp_bw(pa["res_bw_hz"], pa["video_bw_hz"])
        # Query the actual (possibly auto-coupled) CHP sweep time so _read_chp_with_retry()
        # can size the settle wait after each :INIT:REST. A read failure must never break
        # the run - falls back to no settle wait (pre-Stage-2 behaviour).
        try:
            self._chp_sweep_time_s = cxa.get_chp_sweep_time()
            cxa.log.info("Power accuracy: CHP sweep time = %.4f s (average count %d)",
                         self._chp_sweep_time_s, int(pa.get("chp_average_count", 10)))
        except Exception as exc:
            self._chp_sweep_time_s = None
            cxa.log.warning("Power accuracy: could not read CHP sweep time (%s); "
                            "settle wait before each read is skipped", exc)
    def prepare_point(self, mod, cxa, cfg, point):
        pa = cfg["power_accuracy"]
        cxa.set_center_freq(point["freq_mhz"] * 1e6)
        mod.send("freq %s" % point["freq_mhz"])
        mod.send("power %s" % point["set_dbm"], wait=pa["dwell_s"])
        point["adc_power_dbm"] = self._read_adc_power(mod, pa)
    def _read_adc_power(self, mod, pa):
        """DUT-side ADC power cross-check (legacy: -adc-power / get-power), gated by
        read_adc_power (default on). Diagnostic only, independent of the CXA reading -
        a failure here must never break the point, so any exception is swallowed and
        logged rather than propagated.

        base.read_adc_power() enters the -adc-power- submenu and leaves the CLI there -
        bench-confirmed on 2026-08-26: without navigating back to -line- afterward, the
        *next* point's freq/power commands (sent from -line-, per modulator_setup()) get
        rejected with 'command not found', exactly the same class of bug the Stage 4 fix
        addressed for modulator_setup() itself. Always navigate back, even on failure
        (try/finally), so a bad read doesn't strand every subsequent point too.
        """
        if not bool(pa.get("read_adc_power", True)):
            return None
        try:
            return base.read_adc_power(mod)
        except Exception as exc:
            mod.log.warning("Power accuracy: ADC power read failed: %s", exc)
            return None
        finally:
            mod.send("top")
            mod.send("-modulator-config")
            mod.send("line")
    @staticmethod
    def _interp(x, x0, x1, y0, y1):
        """Linear interpolation of y between (x0,y0) and (x1,y1), clamped to [y0,y1]'s
        endpoints outside [x0,x1] - a frequency outside the calibrated link range holds
        the nearer endpoint's attenuation rather than extrapolating past what's known.
        """
        if x1 == x0:
            return y0
        t = (x - x0) / (x1 - x0)
        t = max(0.0, min(1.0, t))
        return y0 + t * (y1 - y0)
    def _atten(self, pa, freq_mhz):
        """Link attenuation compensation, frequency-interpolated per band rather than a
        flat constant - startValidate's link attenuation varies with frequency (slope
        fields: startAttn/stopAttn per band). *_start_db/*_stop_db default to the old
        flat *_atten_db value (both endpoints equal -> constant, exact fallback when the
        new keys are absent). *_start_mhz/*_stop_mhz anchor the interpolation to this
        app's own established band ranges (if_max_mhz for the IF upper edge, 950-2150 for
        L-band, matching flatness.py's defaults) rather than to whatever specific
        frequency list happens to be loaded for a given run - the link's attenuation
        curve is a property of the physical cabling across its full designed range, not
        of which subset of frequencies get tested in one session.
        """
        if_max = float(pa.get("if_max_mhz", 180))
        if freq_mhz <= if_max:
            flat = float(pa.get("if_atten_db", 0))
            return self._interp(freq_mhz,
                                float(pa.get("if_atten_start_mhz", 50.0)),
                                float(pa.get("if_atten_stop_mhz", if_max)),
                                float(pa.get("if_atten_start_db", flat)),
                                float(pa.get("if_atten_stop_db", flat)))
        flat = float(pa.get("lband_atten_db", 0))
        return self._interp(freq_mhz,
                            float(pa.get("lband_atten_start_mhz", 950.0)),
                            float(pa.get("lband_atten_stop_mhz", 2150.0)),
                            float(pa.get("lband_atten_start_db", flat)),
                            float(pa.get("lband_atten_stop_db", flat)))
    def _read_chp_with_retry(self, cxa, pa):
        """Restart the CHP sweep/average cycle, settle, then read.

        Mirrors legacy's INIT:REST + computed wait + retry-on-failure pattern. A
        transport/SCPI exception (not a value-sanity check - accepted decision) triggers
        a retry, capped at chp_read_retries. Returns (level, None) on success or
        (None, error_message) after retries are exhausted, so the caller can turn a
        persistent failure into a FAIL point instead of aborting the whole run - same
        per-point isolation pattern flatness.py/iq_validation.py already use.
        """
        retries = max(1, int(pa.get("chp_read_retries", 1)))
        settle = self._chp_sweep_time_s
        margin = float(pa.get("chp_settle_margin", 1.1))
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                cxa.chp_restart()
                if settle:
                    time.sleep(settle * margin)
                return cxa.read_chp(), None
            except Exception as exc:  # transport/SCPI failure only, not a value check
                last_exc = exc
                cxa.log.warning("Power accuracy: CHP read failed (attempt %d/%d): %s",
                                attempt, retries, exc)
        return None, str(last_exc)
    def measure_point(self, cxa, cfg, point, mode, manual):
        pa = cfg["power_accuracy"]
        adc = point.get("adc_power_dbm")
        if mode == "auto":
            level, err = self._read_chp_with_retry(cxa, pa)
            if err is not None:
                return {"error": err, "adc_power_dbm": adc}
        else:
            level = float(manual["measured_dbm"])
        level = round(level + self._atten(pa, point["freq_mhz"]), 2)
        deviation = round(level - point["set_dbm"], 2)
        return {"measured_dbm": level, "deviation_db": deviation, "adc_power_dbm": adc}
    def evaluate_point(self, cfg, point, meas):
        if meas.get("error"):
            return {"result": "FAIL", "flag": True, "note": meas["error"]}
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
        adc = result["meas"].get("adc_power_dbm")
        return {"Frequency_MHz": result["point"]["freq_mhz"],
                "Set_dBm": result["point"]["set_dbm"],
                "Actual_dBm": result["meas"].get("measured_dbm", ""),
                "Deviation_dB": result["meas"].get("deviation_db", ""),
                "ADC_Power_dBm": adc if adc is not None else "",
                "Result": result["eval"].get("result", "")}
