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
        self.io.read_until("\n", timeout=self.timeout)
    def query(self, scpi):
        self.log.info("CXA ?? %s", scpi)
        self.io.send(scpi)
        reply = self.io.read_until("\n", timeout=self.timeout)
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
            self.command(scpi)
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
        self.command(":BWID %d" % int(rbw_hz))
        self.command(":BWID:VID %d" % int(vbw_hz))
    def set_detector_peak(self):
        self.command(":DET:TRACE1 POS")
    def set_max_hold(self):
        self.command(":TRAC1:TYPE MAXH")
    def set_write_trace(self):
        self.command(":TRAC1:TYPE WRIT")
    def restart_max_hold(self):
        self.command(":TRAC1:TYPE MAXH")
        self.command_sync(":INIT:REST")
    def enable_peak_table(self):
        self.command(":CALC:MARK:PEAK:TABL:STAT ON")
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
