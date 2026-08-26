"""Shared building blocks for the checks.

Keeps the two signal paths strictly separate (a key lab lesson):

  * Clean-carrier path (flatness, power)  : -modulator-config -> line -> sine on ->
    power -> tx enable -> freq. No dac-* commands.
  * DAC test-tone path (IQ only)          : ... top -> debug -> calib -> Init, then
    freq / dac-freq / dac-i / dac-q, staying inside the -calib- menu.

Mixing the two within one measurement is not allowed, so each check calls only the
helper that matches its path.
"""

import re


def enter_expert(mod):
    """Enter expert mode on the modulator CLI (shared by all checks)."""
    mod.send("-u expert-login")


def clean_carrier_setup(mod, power_dbm):
    """One-time setup for a clean main carrier (flatness / power accuracy).

    Leaves the modulator with TX enabled at the requested power. Frequency is set
    later, per point, by the check.
    """
    enter_expert(mod)
    mod.send("-modulator-config")
    mod.send("line")
    mod.send("sine on")
    mod.send("power %s" % power_dbm)
    mod.send("tx enable")


def clean_carrier_cleanup(mod):
    """Turn the clean carrier off so nothing carries into the next test."""
    mod.send("tx disable")
    mod.send("sine off")


def iq_setup(mod, power_dbm):
    """One-time setup for the IQ DAC test-tone path.

    After 'Init' returns OK the CLI stays inside the -calib- menu and blocks other
    input, so the per-frequency commands (freq / dac-*) must be sent from there - we
    do NOT navigate out with top/up between points.
    """
    enter_expert(mod)
    mod.send("-modulator-config")
    mod.send("line")
    mod.send("sine on")
    mod.send("power %s" % power_dbm)
    mod.send("tx enable")
    mod.send("top")
    mod.send("debug")
    mod.send("calib")
    # Init can take a moment; give it extra time before continuing.
    mod.send("Init", wait=2.0)


def iq_cleanup(mod):
    """Zero the DAC and turn the carrier off - prevents the +1 MHz artifact next run."""
    mod.send("dac-i 0")
    mod.send("dac-q 0")
    mod.send("tx disable")
    mod.send("sine off")


# Matches a plain or exponential number anywhere in a CLI reply (same shape as
# iq_validation.py's _NUM_RE - kept local rather than shared to avoid coupling two
# otherwise-independent checks over a private regex).
_ADC_NUM_RE = re.compile(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?")


def read_adc_power(mod):
    """DUT-side ADC power cross-check (legacy: '-adc-power' / 'get-power', logged as
    'adc: <value>'). Diagnostic only - independent of whatever the CXA reports, so it
    lets the operator tell DUT-side from measurement-side drift apart.

    Returns the parsed value as a string, or None if the CLI reply couldn't be parsed.
    Callers must treat a read failure as non-fatal - never let this break a measurement.
    """
    mod.send("-adc-power")
    reply = mod.send("get-power") or ""
    match = re.search(r"power\s*[:=]\s*(\S+)", reply, re.I)
    if match:
        return match.group(1).strip().rstrip(",;")
    nums = _ADC_NUM_RE.findall(reply)
    return nums[-1] if nums else None
