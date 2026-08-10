"""Per-run logging, live-log ring buffer, and result files."""
import csv
import json
import logging
import os
import threading
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
    def log_header(self, check_title, unit, mode, params):
        self.logger.info("=" * 70)
        self.logger.info("RF Verification run: %s", check_title)
        self.logger.info("Unit: %s   Mode: %s", unit, mode)
        self.logger.info("-" * 70)
        self.logger.info("Parameters used for this run:")
        for key in sorted(params):
            self.logger.info("    %-22s = %s", key, params[key])
        self.logger.info("=" * 70)
    def write_results(self, columns, rows, summary):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({c: row.get(c, "") for c in columns})
        with open(self.json_path, "w", encoding="utf-8") as fh:
            json.dump({"columns": columns, "rows": rows, "summary": summary},
                      fh, indent=2, ensure_ascii=False)
        self.logger.info("Results written: %s", os.path.basename(self.csv_path))
    def close(self):
        for handler in self._handlers:
            try:
                handler.close(); self.logger.removeHandler(handler)
            except Exception:
                pass
