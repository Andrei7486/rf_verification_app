"""Analyzer layer - Keysight CXA (N9000B) SCPI control over a raw socket (port 5025)."""
import re
import time
from .transport import LineSocket
_NUM_RE = re.compile(r"[-+]?\d+\.?\d*[eE][-+]?\d+|[-+]?\d+\.?\d+|[-+]?\d+")
class Analyzer:
    def __init__(self, cfg, log):
        self.cfg = cfg; self.log = log
        self.timeout = float(cfg.get("scpi_timeout_s", 15))
        self.io = LineSocket(cfg["cxa_ip"], cfg["cxa_scpi_port"], timeout=self.timeout)
    def connect(self):
        self.io.connect()
        # Verify the analyzer is actually responding (not just a socket that opened).
        self.io.send("*IDN?")
        self.io.read_until("\n", timeout=self.timeout, require=True)
        self.log.info("CXA connected at %s:%s", self.cfg["cxa_ip"], self.cfg["cxa_scpi_port"])
    def close(self):
        self.io.close()
    def command(self, scpi):
        self.log.info("CXA >> %s", scpi)
        self.io.send(scpi)
    def command_sync(self, scpi):
        self.log.info("CXA >> %s", scpi)
        self.io.send(scpi)
        self.io.send("*OPC?")
        self.io.read_until("\n", timeout=self.timeout, require=True)
    def query(self, scpi):
        self.log.info("CXA ?? %s", scpi)
        self.io.send(scpi)
        reply = self.io.read_until("\n", timeout=self.timeout, require=True)
        return reply.strip()
    def query_number(self, scpi):
        reply = self.query(scpi)
        match = _NUM_RE.search(reply)
        if not match:
            raise ValueError("No numeric value in CXA reply: %r" % reply)
        return float(match.group(0))
    def preset(self):
        self.command_sync(":SYST:PRES")
    def preset_swept_sa(self):
        self.command(":CONF:SAN")
    def apply_ext_gain(self):
        if self.cfg.get("apply_ext_gain", False):
            scpi = self.cfg.get("ext_gain_scpi", ":CORR:SA:GAIN {db}").format(
                db=self.cfg.get("ext_gain_db", 0.0))
            self.command_sync(scpi)
        else:
            self.log.info("Ext Gain not pushed by app; expected %.2f dB set on instrument",
                          self.cfg.get("ext_gain_db", 0.0))
    def set_ref_level(self, dbm):
        self.command(":DISP:WIND:TRAC:Y:RLEV %s" % dbm)
    def set_scale_div(self, db):
        self.command(":DISP:WIND:TRAC:Y:PDIV %s" % db)
    def set_center_span(self, center_hz, span_hz):
        self.command(":FREQ:CENT %d" % int(center_hz))
        self.command_sync(":FREQ:SPAN %d" % int(span_hz))
    def set_start_stop(self, start_hz, stop_hz):
        self.command(":FREQ:STAR %d" % int(start_hz))
        self.command_sync(":FREQ:STOP %d" % int(stop_hz))
    def set_bw(self, rbw_hz, vbw_hz):
        self.command_sync(":BWID %d" % int(rbw_hz))
        self.command_sync(":BWID:VID %d" % int(vbw_hz))
    def set_detector_peak(self):
        self.command(":DET:TRACE1 POS")
    def set_max_hold(self):
        self.command(":TRAC1:TYPE MAXH")
    def set_write_trace(self):
        self.command(":TRAC1:TYPE WRIT")
    def restart_max_hold(self):
        self.command(":TRAC1:TYPE MAXH")
        self.command_sync(":INIT:REST")
    def enable_peak_table(self, scpi=":CALC:MARK:PEAK:TABL:STAT ON"):
        # Sent with *OPC? sync so a lost/rejected enable does not pass silently.
        self.command_sync(scpi)
    def set_sweep_time(self, seconds):
        self.command_sync(":SWE:TIME %s" % seconds)
    def get_sweep_time(self):
        """Read back the (possibly auto-coupled) sweep time actually in effect, in seconds."""
        return self.query_number(":SWE:TIME?")
    def get_peak_table(self):
        """Read back the on-screen peak table contents (diagnostic only, comma-separated)."""
        return self.query(":CALC:MARK:PEAK:TABL?")
    def set_attenuation(self, db):
        self.command_sync(":POW:ATT:AUTO OFF")
        self.command_sync(":POW:ATT %s" % db)
    def set_attenuation_auto(self, on=True):
        self.command_sync(":POW:ATT:AUTO %s" % ("ON" if on else "OFF"))
    def set_ext_gain(self, db):
        self.command_sync(":CORR:SA:GAIN %s" % db)
    def find_peak(self):
        """Marker 1 to the global max; return (freq_hz, level_dbm)."""
        self.command(":CALC:MARK1:MODE POS")
        self.command(":CALC:MARK1:MAX")
        x = self.query_number(":CALC:MARK1:X?")
        y = self.query_number(":CALC:MARK1:Y?")
        return x, y
    def marker_to_delta(self):
        """Switch marker 1 to DELTA mode; reference stays at its current position."""
        self.command_sync(":CALC:MARK:MODE DELT")
    def marker_delta_y_at_offset(self, offset_hz, settle_s=0.15):
        """Move the delta marker by offset_hz from the reference peak and return dBc."""
        self.command(":CALC:MARK1:X %d" % int(offset_hz))
        time.sleep(settle_s)
        return self.query_number(":CALC:MARK1:Y?")
    def marker_delta_y_at(self, freq_hz, settle_s=0.15):
        """Move the delta marker to freq_hz and return the delta amplitude (dBc)."""
        self.command(":CALC:MARK1:X %d" % int(freq_hz))
        time.sleep(settle_s)
        return self.query_number(":CALC:MARK1:Y?")
    def read_chp(self):
        return self.query_number(":READ:CHP:CHP?")
    def marker_peak_level(self):
        self.command(":CALC:MARK1:MODE POS")
        self.command(":CALC:MARK1:MAX")
        return self.query_number(":CALC:MARK1:Y?")
    def marker_level_at(self, freq_hz, settle_s=0.15):
        self.command(":CALC:MARK1:MODE POS")
        self.command(":CALC:MARK1:CPS OFF")
        self.command(":CALC:MARK1:X %d" % int(freq_hz))
        time.sleep(settle_s)
        return self.query_number(":CALC:MARK1:Y?")
