"""Per-run logging, live-log ring buffer, and result files."""
import csv
import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime
_LIVE_LOCK = threading.Lock()
_LIVE = deque(maxlen=500)
_LIVE_SEQ = 0
def _live_append(text):
    global _LIVE_SEQ
    with _LIVE_LOCK:
        _LIVE_SEQ += 1
        _LIVE.append((_LIVE_SEQ, text))
def live_tail(after_seq=0):
    with _LIVE_LOCK:
        lines = [t for (s, t) in _LIVE if s > after_seq]
        seq = _LIVE[-1][0] if _LIVE else after_seq
    return {"seq": seq, "lines": lines}
def live_clear():
    with _LIVE_LOCK:
        _LIVE.clear()
def stream_live(after_seq=0, poll_interval=0.2):
    """SSE generator: yields one 'id: N\\ndata: <json line>\\n\\n' event per new
    live-log line, starting after 'after_seq'. Polls the same buffer live_tail()
    reads - a short in-process loop, not a new threading primitive - at a fifth
    of the client's own (now fallback-only) 1 s poll interval (D6, U3). The id
    matches _LIVE's own per-line sequence numbers 1:1 (each append increments by
    exactly 1, so this is a safe reconstruction, not a guess), so a browser's
    native EventSource reconnect (Last-Event-ID) resumes without any gap or
    duplicate.
    """
    seq = after_seq
    while True:
        d = live_tail(seq)
        for i, line in enumerate(d["lines"], start=seq + 1):
            yield "id: %d\ndata: %s\n\n" % (i, json.dumps(line))
        seq = d["seq"]
        time.sleep(poll_interval)
class _LiveHandler(logging.Handler):
    def emit(self, record):
        try:
            _live_append(self.format(record))
        except Exception:
            pass
class RunLogger:
    def __init__(self, log_dir, check_key, unit):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.base = "%s_%s_%s" % (check_key, unit, stamp)
        self.log_dir = log_dir
        self.log_path = os.path.join(log_dir, self.base + ".log")
        self.csv_path = os.path.join(log_dir, self.base + ".csv")
        self.json_path = os.path.join(log_dir, self.base + ".json")
        self.logger = logging.getLogger("run." + self.base)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
        fh = logging.FileHandler(self.log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG); fh.setFormatter(fmt); self.logger.addHandler(fh)
        ch = logging.StreamHandler(); ch.setLevel(logging.INFO); ch.setFormatter(fmt)
        self.logger.addHandler(ch)
        lh = _LiveHandler(); lh.setLevel(logging.INFO); lh.setFormatter(fmt)
        self.logger.addHandler(lh)
        self._handlers = [fh, ch, lh]
    def log_header(self, check_title, unit, mode, params, drift=None, config_version=None):
        self.logger.info("=" * 70)
        self.logger.info("RF Verification run: %s", check_title)
        self.logger.info("Unit: %s   Mode: %s", unit, mode)
        self.logger.info("-" * 70)
        self.logger.info("Parameters used for this run:")
        for key in sorted(params):
            self.logger.info("    %-22s = %s", key, params[key])
        self._log_drift(drift, config_version)
        self.logger.info("=" * 70)
    def _log_drift(self, drift, config_version):
        """M6: one line per key that differs from config.defaults.json - missing
        (falls back to the shipped default), unknown (on disk, not in defaults) or
        changed (both present, different values). '(none)' when nothing differs -
        the operator should not have to infer a clean run from an absent section.
        """
        self.logger.info("-" * 70)
        self.logger.info("Config drift vs repo defaults (version %s):", config_version)
        if not drift:
            self.logger.info("    (none)")
            return
        for entry in drift:
            self.logger.info("    %s.%s: %s  (live=%r default=%r)", entry["section"],
                             entry["key"], entry["status"], entry["live"], entry["default"])
    def write_results(self, columns, rows, summary, config_version=None):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as fh:
            fh.write("# config_version: %s\n" % config_version)
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({c: row.get(c, "") for c in columns})
        with open(self.json_path, "w", encoding="utf-8") as fh:
            json.dump({"config_version": config_version, "columns": columns, "rows": rows,
                      "summary": summary}, fh, indent=2, ensure_ascii=False)
        self.logger.info("Results written: %s", os.path.basename(self.csv_path))
    def close(self):
        for handler in self._handlers:
            try:
                handler.close(); self.logger.removeHandler(handler)
            except Exception:
                pass
