"""Line-oriented TCP transport.

Both the Keysight CXA (SCPI over telnet, port 5023) and the NovelSat modulator CLI
(telnet, port 23) are simple line protocols with a text prompt. Rather than depend on
telnetlib (deprecated in Python 3.11, removed in 3.13) we talk raw sockets. This keeps
the app working on whatever Python version the lab PCs ship with.
"""

import socket
import time


class TransportError(Exception):
    """Raised for connection or read/write failures on the socket transport."""


class LineSocket:
    """Minimal blocking TCP client that sends text lines and reads until a prompt."""

    def __init__(self, host, port, timeout=15.0, newline="\n"):
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.newline = newline
        self._sock = None

    def connect(self):
        """Open the TCP connection. Raises TransportError on failure."""
        try:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
            # Per-recv timeout is short; overall waits are bounded by read_until().
            self._sock.settimeout(1.0)
        except OSError as exc:
            raise TransportError(
                "Cannot connect to %s:%d (%s)" % (self.host, self.port, exc)
            )

    def send(self, line):
        """Send a single command line, appending the configured newline."""
        if self._sock is None:
            raise TransportError("Socket is not connected")
        data = (line + self.newline).encode("ascii", errors="ignore")
        try:
            self._sock.sendall(data)
        except OSError as exc:
            raise TransportError("Send failed: %s" % exc)

    def _read_loop(self, matches, deadline):
        """Pull bytes until matches(buf) is true or 'deadline' passes.

        Shared by read_until() (literal substrings) and read_until_regex()
        (caller-supplied pattern) - both are just "read until X", parameterized
        by what X is; the byte-level loop is identical either way.
        """
        buf = ""
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue  # no data this slice - keep waiting until the deadline
            except OSError as exc:
                raise TransportError("Read failed: %s" % exc)
            if not chunk:
                break  # remote closed the connection
            buf += chunk.decode("ascii", errors="ignore")
            if matches(buf):
                return buf
        return buf

    def read_until(self, patterns, timeout=None, require=False):
        """Read until any string in 'patterns' appears, or 'timeout' elapses.

        Returns everything read so far (even on timeout) so the caller can inspect
        partial output. 'patterns' may be a single string or a list of strings.
        """
        if self._sock is None:
            raise TransportError("Socket is not connected")
        if isinstance(patterns, str):
            patterns = [patterns]
        deadline = time.time() + (self.timeout if timeout is None else timeout)
        buf = self._read_loop(lambda b: any(p in b for p in patterns), deadline)
        if require and not any(p in buf for p in patterns):
            raise TransportError("Timeout: expected %r, got %r" % (patterns, buf[-120:]))
        return buf

    def read_until_regex(self, pattern, timeout=None, require=False):
        """Read until a compiled regex matches the buffer, or 'timeout' elapses.

        Same contract as read_until(), matched by regex instead of a literal
        substring - lets a caller (e.g. modulator.py) detect a structured prompt
        without this module knowing what that prompt looks like. 'pattern' must
        be pre-compiled (e.g. with re.DOTALL if the prompt can span a line break).
        """
        if self._sock is None:
            raise TransportError("Socket is not connected")
        deadline = time.time() + (self.timeout if timeout is None else timeout)
        buf = self._read_loop(lambda b: bool(pattern.search(b)), deadline)
        if require and not pattern.search(buf):
            raise TransportError(
                "Timeout: expected pattern %r, got %r" % (pattern.pattern, buf[-120:]))
        return buf

    def drain(self, wait=0.3):
        """Read and discard whatever is currently available; return it as text.

        Used for the modulator CLI where we do not need to parse the echo but want
        to keep the receive buffer clear between commands.
        """
        if self._sock is None:
            raise TransportError("Socket is not connected")
        deadline = time.time() + wait
        buf = ""
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            buf += chunk.decode("ascii", errors="ignore")
        return buf

    def close(self):
        """Close the socket, ignoring errors (best effort on teardown)."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
