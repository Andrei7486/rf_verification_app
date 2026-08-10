"""RF verification checks: flatness, power accuracy, IQ validation."""

from .flatness import FlatnessCheck
from .power_accuracy import PowerAccuracyCheck
from .iq_validation import IqValidationCheck

# Registry used by the session/app to look a check up by its key.
CHECKS = {
    FlatnessCheck.key: FlatnessCheck,
    PowerAccuracyCheck.key: PowerAccuracyCheck,
    IqValidationCheck.key: IqValidationCheck,
}


def get_check(key):
    """Return a check class by key, or raise KeyError with a clear message."""
    if key not in CHECKS:
        raise KeyError("Unknown check '%s'. Known: %s" % (key, ", ".join(CHECKS)))
    return CHECKS[key]
