"""Run session - state machine with manual and auto (self-running) modes."""
import threading
from . import config_store
from .analyzer import Analyzer
from .modulator import make_modulator
from .logger import RunLogger, live_clear
from .checks import get_check
from .checks import base as check_base
class SessionError(Exception):
    pass
class RunSession:
    def __init__(self):
        self._lock = threading.Lock()
        self._reset()
    def _reset(self):
        self.active = False; self.finished = False
        self.check = None; self.cfg = None; self.mode = "manual"; self.unit = None
        self.points = []; self.idx = -1; self.results = []; self.summary = None
        self.mod = None; self.cxa = None; self.rlog = None; self._finalized = False
        self.worker = None
        self.stop_event = threading.Event(); self.resume_event = threading.Event()
        self.paused = False; self.pause_msg = ""; self.error = None
    def is_active(self):
        return self.active
    def _params_snapshot(self, params):
        snap = dict(params)
        for key, val in self.cfg.get(self.check.key, {}).items():
            snap[key] = val
        # Per-check resolved value (falls back to the global analyzer.ext_gain_db when
        # the check has no override of its own), not just the global number - each
        # check now pushes/verifies its own external gain in analyzer_setup()
        # (base.apply_check_ext_gain()); this mirrors that same resolution so the run
        # header reports what will actually be on the instrument, not a value that
        # might differ from it (e.g. power_accuracy's own ext_gain_db=0 override).
        snap["ext_gain_db"] = check_base.resolve_ext_gain(self.cfg, self.check.key)
        snap["dut_conn_type"] = self.cfg["modulator"].get("dut_conn_type")
        snap["mode"] = self.mode
        return snap
    def _point_view(self):
        if self.idx < 0 or self.idx >= len(self.points):
            return None
        point = self.points[self.idx]
        view = {"index": self.idx, "total": len(self.points), "freq_mhz": point.get("freq_mhz")}
        if "set_dbm" in point:
            view["set_dbm"] = point["set_dbm"]
        return view
    def _band(self, freq_mhz):
        thr = float(self.cfg.get(self.check.key, {}).get("if_max_mhz", 180))
        return "IF" if float(freq_mhz) <= thr else "L-band"
    def _rows(self):
        return [self.check.row_for(r) for r in self.results]
    def _flags(self):
        return [bool(r["eval"].get("flag", False)) for r in self.results]
    def start(self, check_key, unit, mode, freqs, params):
        with self._lock:
            if self.active:
                raise SessionError("A run is already in progress. Stop it first.")
            live_clear()
            self.cfg = config_store.load_config()
            self.check = get_check(check_key)()
            self.unit = unit; self.mode = mode
            self.results = []; self.summary = None; self.finished = False
            self._finalized = False; self.paused = False; self.pause_msg = ""; self.error = None
            self.stop_event.clear(); self.resume_event.clear()
            self.points = self.check.build_points(self.cfg, freqs, params)
            if not self.points:
                raise SessionError("No points to run (empty frequency/level list).")
            log_dir = config_store.resolve_log_dir(self.cfg)
            self.rlog = RunLogger(log_dir, check_key, unit)
            self.rlog.log_header(self.check.title, unit, mode, self._params_snapshot(params))
            try:
                self.cxa = Analyzer(self.cfg["analyzer"], self.rlog.logger)
                self.cxa.connect()
                self.mod = make_modulator(self.cfg["modulator"], self.rlog.logger)
                self.mod.connect()
                self.check.modulator_setup(self.mod, self.cfg)
                self.check.analyzer_setup(self.cxa, self.cfg, self.points)
            except Exception as exc:
                self.rlog.logger.error("Setup failed: %s", exc)
                self._teardown_devices(); self.rlog.close(); self._reset()
                raise SessionError("Setup failed: %s" % exc)
            self.active = True
            info = {"check": self.check.key, "title": self.check.title, "unit": unit,
                    "mode": mode, "final_only": getattr(self.check, "final_only", False),
                    "manual_fields": self.check.manual_fields,
                    "columns": self.check.csv_columns, "log_base": self.rlog.base}
            if mode == "auto":
                self.idx = -1
                self.worker = threading.Thread(target=self._auto_loop, daemon=True)
                self.worker.start()
                info["point"] = {"index": 0, "total": len(self.points)}
            else:
                self.idx = 0; self._prepare_current(); info["point"] = self._point_view()
            return info
    def _prepare_current(self):
        point = self.points[self.idx]
        self.rlog.logger.info("--- Point %d/%d  freq=%s MHz ---",
                              self.idx + 1, len(self.points), point.get("freq_mhz"))
        self.check.prepare_point(self.mod, self.cxa, self.cfg, point)
    def _auto_loop(self):
        try:
            prev_band = None
            for i in range(len(self.points)):
                if self.stop_event.is_set():
                    break
                point = self.points[i]; band = self._band(point.get("freq_mhz"))
                if prev_band is not None and band != prev_band:
                    self.pause_msg = ("Reconnect the RF cable to the %s output, then press Continue." % band)
                    self.paused = True; self.resume_event.clear()
                    self.rlog.logger.info("PAUSED: %s", self.pause_msg)
                    while not self.resume_event.wait(timeout=0.3):
                        if self.stop_event.is_set():
                            break
                    self.paused = False; self.pause_msg = ""
                    if self.stop_event.is_set():
                        break
                    self.rlog.logger.info("Resumed by operator")
                prev_band = band
                self.idx = i; self._prepare_current()
                meas = self.check.measure_point(self.cxa, self.cfg, point, "auto", {})
                ev = self.check.evaluate_point(self.cfg, point, meas)
                result = {"index": i, "point": point, "meas": meas, "eval": ev}
                self.results.append(result)
                self.rlog.logger.info("Measured: %s", self.check.row_for(result))
        except Exception as exc:
            self.error = str(exc); self.rlog.logger.error("Auto run failed: %s", exc)
        finally:
            self._finalize_and_write()
    def confirm(self):
        with self._lock:
            if not self.active:
                raise SessionError("No run in progress.")
            self.resume_event.set()
            return {"ok": True}
    def measure(self, manual_values):
        with self._lock:
            self._require_active_manual()
            point = self.points[self.idx]
            try:
                meas = self.check.measure_point(self.cxa, self.cfg, point, self.mode, manual_values or {})
                ev = self.check.evaluate_point(self.cfg, point, meas)
            except Exception as exc:
                self.rlog.logger.error("Measurement failed: %s", exc)
                raise SessionError("Measurement failed: %s" % exc)
            result = {"index": self.idx, "point": point, "meas": meas, "eval": ev}
            self.results = [r for r in self.results if r["index"] != self.idx]
            self.results.append(result); self.results.sort(key=lambda r: r["index"])
            row = self.check.row_for(result); self.rlog.logger.info("Measured: %s", row)
            return {"row": row, "flag": bool(ev.get("flag", False)),
                    "has_next": self.idx < len(self.points) - 1}
    def next(self):
        with self._lock:
            self._require_active_manual()
            if self.idx >= len(self.points) - 1:
                return {"done": True}
            self.idx += 1; self._prepare_current()
            return {"done": False, "point": self._point_view()}
    def skip(self):
        with self._lock:
            self._require_active_manual()
            self.rlog.logger.info("Point %d skipped by operator", self.idx + 1)
            if self.idx >= len(self.points) - 1:
                return {"done": True}
            self.idx += 1; self._prepare_current()
            return {"done": False, "point": self._point_view()}
    def status(self):
        return {"active": self.active, "finished": self.finished, "mode": self.mode,
                "paused": self.paused, "pause_msg": self.pause_msg, "error": self.error,
                "idx": len(self.results), "total": len(self.points),
                "columns": self.check.csv_columns if self.check else [],
                "rows": self._rows(), "flags": self._flags(),
                "verdict": (self.summary or {}).get("verdict") if self.finished else None,
                "summary": self.summary if self.finished else None,
                "log_base": self.rlog.base if self.rlog else None}
    def _finalize_and_write(self):
        with self._lock:
            if self._finalized:
                return
            self._finalized = True
            try:
                self.check.cleanup(self.mod, self.cfg)
            except Exception as exc:
                if self.rlog:
                    self.rlog.logger.error("Cleanup command failed: %s", exc)
            self.summary = self.check.finalize(self.cfg, self.results)
            rows = self._rows()
            if self.rlog:
                self.rlog.logger.info("Verdict: %s", self.summary.get("verdict"))
                self.rlog.write_results(self.check.csv_columns, rows, self.summary)
            self._teardown_devices()
            if self.rlog:
                self.rlog.close()
            self.finished = True; self.active = False
    def stop(self):
        with self._lock:
            if not self.active and not self.finished:
                raise SessionError("No run in progress.")
        self.stop_event.set(); self.resume_event.set()
        if self.worker is not None and self.worker.is_alive():
            self.worker.join(timeout=15)
        self._finalize_and_write()
        return {"verdict": (self.summary or {}).get("verdict"), "summary": self.summary,
                "columns": self.check.csv_columns, "rows": self._rows(),
                "flags": self._flags(), "log_base": self.rlog.base if self.rlog else None}
    def _teardown_devices(self):
        for dev in (self.mod, self.cxa):
            if dev is not None:
                try:
                    dev.close()
                except Exception:
                    pass
        self.mod = None; self.cxa = None
    def _require_active_manual(self):
        if not self.active:
            raise SessionError("No run in progress.")
        if self.mode == "auto":
            raise SessionError("Auto run is controlled automatically.")
SESSION = RunSession()
