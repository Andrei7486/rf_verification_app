"""Configuration store.

Loads and saves the externalized JSON configuration (config/config.json) and the
per-unit frequency lists (config/freq_lists/<UNIT>.txt). Nothing in the application
should hard-code lab values - everything is read from here so the same build serves
different units and benches.
"""

import json
import os
import shutil
import threading

from . import paths

# Config and frequency lists live in an EXTERNAL folder next to the executable (in a
# frozen build) or in the project root (in development), so operator edits persist.
CONFIG_DIR = os.path.join(paths.external_dir(), "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
FREQ_LIST_DIR = os.path.join(CONFIG_DIR, "freq_lists")

# The default config bundled inside the app (used to seed the external copy on the very
# first run of a frozen build). In development this equals CONFIG_DIR, so nothing copies.
_BUNDLED_CONFIG_DIR = os.path.join(paths.resource_dir(), "config")

# A single lock protects config file writes from concurrent request handlers.
_lock = threading.Lock()


def _ensure_external_config():
    """On first run of a frozen exe, seed config/ next to the exe from the bundled copy."""
    if not os.path.isdir(CONFIG_DIR) and os.path.isdir(_BUNDLED_CONFIG_DIR):
        # abspath compare guards the dev case where the two are the same folder.
        if os.path.abspath(CONFIG_DIR) != os.path.abspath(_BUNDLED_CONFIG_DIR):
            shutil.copytree(_BUNDLED_CONFIG_DIR, CONFIG_DIR)


# Seed once at import so every entry point sees a populated external config folder.
_ensure_external_config()


def load_config():
    """Return the full configuration dictionary from config.json."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_config(cfg):
    """Persist the full configuration dictionary back to config.json.

    The file is written atomically (temp file + replace) so an interrupted write
    cannot leave a half-written, unparseable config on the station.
    """
    with _lock:
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_FILE)


def list_units():
    """Return the list of unit names that have a frequency list file."""
    if not os.path.isdir(FREQ_LIST_DIR):
        return []
    units = []
    for name in sorted(os.listdir(FREQ_LIST_DIR)):
        if name.lower().endswith(".txt"):
            units.append(name[:-4])
    return units


def load_freq_list(unit):
    """Return the list of frequencies (MHz, float) for a given unit.

    Comment lines (starting with '#') and blank lines are ignored. A malformed
    numeric line raises ValueError so the operator gets a clear message instead
    of a silently skipped frequency.
    """
    path = os.path.join(FREQ_LIST_DIR, unit + ".txt")
    if not os.path.isfile(path):
        raise FileNotFoundError("No frequency list for unit '%s'" % unit)
    freqs = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                freqs.append(float(line))
            except ValueError:
                raise ValueError(
                    "Bad frequency on line %d of %s.txt: %r" % (lineno, unit, line)
                )
    return freqs


def save_freq_list(unit, text):
    """Overwrite the raw text of a unit's frequency list file.

    'text' is stored verbatim (comments preserved) so operators can keep notes
    inside the list. Validation happens on load.
    """
    with _lock:
        os.makedirs(FREQ_LIST_DIR, exist_ok=True)
        path = os.path.join(FREQ_LIST_DIR, unit + ".txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def resolve_log_dir(cfg):
    """Return an absolute path to the results/log directory, creating it if needed.

    A relative log_dir (default 'results') is placed next to the executable (frozen) or
    in the project root (dev) so logs land beside the app, not inside a temp folder.
    """
    log_dir = cfg.get("general", {}).get("log_dir", "results")
    if not os.path.isabs(log_dir):
        log_dir = os.path.join(paths.external_dir(), log_dir)
    os.makedirs(log_dir, exist_ok=True)
    return log_dir
