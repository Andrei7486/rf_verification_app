"""Shared building blocks for the checks.

Keeps the two signal paths strictly separate (a key lab lesson):

  * Clean-carrier path (flatness, power)  : -modulator-config -> line -> sine on ->
    power -> tx enable -> freq. No dac-* commands.
  * DAC test-tone path (IQ only)          : ... top -> debug -> calib -> Init, then
    freq / dac-freq / dac-i / dac-q, staying inside the -calib- menu.

Mixing the two within one measurement is not allowed, so each check calls only the
helper that matches its path.
"""


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
