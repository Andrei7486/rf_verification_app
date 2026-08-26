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


def resolve_ext_gain(cfg, check_key):
    """This check's external gain: its own <check>.ext_gain_db if configured, else the
    global analyzer.ext_gain_db. An absent per-check key falls back to the global
    number (not 0), so an old config without it reproduces today's configured value.

    Resolution only - does not touch the instrument. See apply_check_ext_gain() for
    the version that also pushes and verifies it; this half is split out so
    session.py can log the same resolved value in the run header before
    analyzer_setup() (which does the actual push) has run.
    """
    section = cfg.get(check_key, {}) or {}
    if "ext_gain_db" in section:
        return float(section["ext_gain_db"])
    return float(cfg.get("analyzer", {}).get("ext_gain_db", 0.0))


def apply_check_ext_gain(cxa, cfg, check_key):
    """Resolve and push this check's external gain, independent of any other check's
    analyzer state.

    Three checks now share one CXA in turn; none may rely on inherited CORR:SA:GAIN
    left by whichever check ran before it (see
    POWER_ACCURACY_STATE_LEAKAGE_INVESTIGATION.md - power_accuracy's Stage 3 baseline
    init pushed CORR:SA:GAIN 0 and never restored it, and flatness/iq_validation's old
    apply_ext_gain() call was a no-op under the documented default
    analyzer.apply_ext_gain=false, so the correct value was never reasserted). Pushed
    unconditionally here - the global apply_ext_gain flag and its gated
    Analyzer.apply_ext_gain() method are left exactly as they were, just no longer
    consulted by any check; each check now owns its own instrument state instead.

    Reads back :CORR:SA:GAIN? after pushing and logs it - the investigation relied on
    documented Keysight preset behaviour (amplitude correction persists across
    :SYST:PRES) rather than a live query; this verifies it on every run instead of
    assuming it. A mismatch beyond 0.01 dB is logged as a warning, not raised - the
    run should not abort over what both this app's code and the investigation expect
    to be quiet, exact instrument behaviour, but that expectation is now checked
    rather than assumed. A read-back failure (e.g. a malformed reply) is likewise
    logged and swallowed, matching the non-fatal-diagnostics pattern used elsewhere
    in the checks - the gain push itself already happened and stands regardless.

    Returns the resolved (pushed) value.
    """
    resolved = resolve_ext_gain(cfg, check_key)
    cxa.set_ext_gain(resolved)
    try:
        readback = cxa.query_number(":CORR:SA:GAIN?")
        cxa.log.info("%s: ext gain set to %.2f dB, instrument reads back %.2f dB",
                     check_key, resolved, readback)
        if abs(readback - resolved) > 0.01:
            cxa.log.warning("%s: ext gain read-back mismatch - pushed %.2f dB, "
                            "instrument reports %.2f dB", check_key, resolved, readback)
    except Exception as exc:
        cxa.log.warning("%s: could not read back CORR:SA:GAIN (%s)", check_key, exc)
    return resolved
