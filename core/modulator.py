"""Modulator (DUT) device layer.

The NovelSat modulator CLI is reached either over telnet (192.168.0.50:23) or over a
serial COM port, selected by 'dut_conn_type' in config. Both transports expose the same
small interface: connect/login, send a command line, close. Higher-level command
sequences (expert login, clean-carrier setup, DAC test tone, cleanup) live in the check
modules and in checks/base.py.
"""

import re
import time

from .transport import LineSocket, TransportError

# Prompt fragments seen on the NS CLI. We match on any of these to know a line was
# accepted; matching is best-effort because the exact prompt depends on the menu level.
_PROMPTS = ["#", ">", "sat", "-"]

# Per-command prompt, e.g. "root@Modem -line- *<7>" - N increments on every accepted
# command. re.DOTALL so it still matches if a "Configuring device, Please wait
# ........Done." interlude (or stray \r\r\n framing) lands between "root@Modem" and
# the trailing "*<N>"; command echo alone (no "root@Modem"/"*<N>") never matches.
_PROMPT_RE = re.compile(r"root@Modem.*?\*<\d+>", re.DOTALL)


class ModulatorError(Exception):
    """Raised on modulator connection or command failure."""


class _BaseModulator:
    """Common command-send behaviour shared by telnet and serial back-ends."""

    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self.delay = float(cfg.get("cmd_delay_s", 0.4))
        self.prompt_timeout = float(cfg.get("dut_prompt_wait_timeout_s", 3.0))

    def send(self, cmd, wait=None):
        """Send a CLI command. Sub-classes implement _write()/_read()/
        _read_until_prompt(); the last defaults to today's fixed sleep+read below.
        """
        self.log.info("MOD >> %s", cmd)
        self._write(cmd)
        echo = self._read_until_prompt(wait)
        if echo:
            self.log.debug("MOD << %s", echo.strip())
        return echo

    def _read_until_prompt(self, wait):
        """Default: fixed sleep then drain - today's behaviour, unchanged for
        Serial. TelnetModulator overrides this with a prompt-based read.
        """
        time.sleep(self.delay if wait is None else wait)
        return self._read()

    # Sub-classes must implement these three.
    def connect(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def _write(self, cmd):
        raise NotImplementedError

    def _read(self):
        raise NotImplementedError


class TelnetModulator(_BaseModulator):
    """NS modulator over raw-socket telnet (port 23), with admin/novelsat login."""

    def __init__(self, cfg, log):
        super().__init__(cfg, log)
        self.io = LineSocket(
            cfg["dut_ip"],
            cfg["dut_telnet_port"],
            timeout=float(cfg.get("connect_timeout_s", 10)),
        )

    def connect(self):
        self.io.connect()
        # Nudge the CLI and log in. We tolerate either an immediate prompt (already
        # logged in) or the login/password sequence.
        self.io.send("")
        banner = self.io.read_until(["login:", "assword", "#", ">"], timeout=8)
        if "login:" in banner:
            self.io.send(self.cfg.get("dut_user", "admin"))
            self.io.read_until(["assword"], timeout=8)
            self.io.send(self.cfg.get("dut_password", "novelsat"))
            self.io.read_until(_PROMPTS, timeout=8)
        elif "assword" in banner:
            self.io.send(self.cfg.get("dut_password", "novelsat"))
            self.io.read_until(_PROMPTS, timeout=8)
        self.log.info("Modulator connected via telnet %s:%s",
                      self.cfg["dut_ip"], self.cfg["dut_telnet_port"])

    def _write(self, cmd):
        self.io.send(cmd)

    def _read(self):
        return self.io.drain(wait=0.2)

    def _read_until_prompt(self, wait):
        """Return as soon as the NS CLI prompt is seen, instead of always
        waiting the full fixed delay - bench-measured at ~1.4 s/command before
        this (S-M0). Bounded by dut_prompt_wait_timeout_s so a prompt that
        never appears degrades to a bounded wait rather than hanging.
        """
        return self.io.read_until_regex(_PROMPT_RE, timeout=self.prompt_timeout)

    def close(self):
        self.io.close()


class SerialModulator(_BaseModulator):
    """NS modulator over a serial COM port. Requires pyserial (imported lazily)."""

    def __init__(self, cfg, log):
        super().__init__(cfg, log)
        self.port_name = cfg.get("dut_com_port", "COM1")
        self.baud = int(cfg.get("dut_baud", 115200))
        self.ser = None

    def connect(self):
        try:
            import serial  # pyserial - only needed for serial back-end
        except ImportError:
            raise ModulatorError(
                "Serial mode needs pyserial. Install it: pip install pyserial"
            )
        try:
            self.ser = serial.Serial(self.port_name, self.baud, timeout=0.3)
        except Exception as exc:  # serial.SerialException and friends
            raise ModulatorError("Cannot open %s: %s" % (self.port_name, exc))
        # Log in over serial the same way as telnet.
        self._write("")
        time.sleep(0.5)
        banner = self._read()
        if "login:" in banner:
            self._write(self.cfg.get("dut_user", "admin"))
            time.sleep(0.5)
            self._read()
            self._write(self.cfg.get("dut_password", "novelsat"))
            time.sleep(0.5)
            self._read()
        elif "assword" in banner:
            self._write(self.cfg.get("dut_password", "novelsat"))
            time.sleep(0.5)
            self._read()
        self.log.info("Modulator connected via serial %s @ %d", self.port_name, self.baud)

    def _write(self, cmd):
        self.ser.write((cmd + "\n").encode("ascii", errors="ignore"))

    def _read(self):
        try:
            data = self.ser.read(4096)
        except Exception:
            return ""
        return data.decode("ascii", errors="ignore")

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None


def make_modulator(cfg, log):
    """Factory: build the right modulator back-end from 'dut_conn_type' in config."""
    conn = cfg.get("dut_conn_type", "telnet").lower()
    if conn == "serial":
        return SerialModulator(cfg, log)
    return TelnetModulator(cfg, log)
