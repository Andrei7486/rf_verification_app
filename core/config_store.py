"""Configuration store.

Loads and saves the externalized JSON configuration (config/config.json) and the
per-unit frequency lists (config/freq_lists/<UNIT>.txt). Nothing in the application
should hard-code lab values - everything is read from here so the same build serves
different units and benches.

M6 / S1 (config integrity and drift detection): config.defaults.json is a second,
bundled, read-only file - the repo's reference values. load_config() merges it under
whatever is on disk, so an absent key falls back to the shipped default rather than
raising or silently reading as 0. diff_against_defaults() reports what actually
differs, for the run log (see session.py / logger.py).
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

# Reference values, always read from the bundled (read-only) location, never the
# externalized one - so a frozen build's own copy can't itself drift.
DEFAULTS_FILE = os.path.join(_BUNDLED_CONFIG_DIR, "config.defaults.json")

# Sentinel for "this key is absent", distinct from any real config value (None,
# False and 0 are all valid config values and must not be confused with absence).
_ABSENT = object()

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


def _read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_defaults():
    """Return the repo-shipped reference config (config.defaults.json).

    Read-only, bundled with the app - the source of truth for load_config()'s
    fallback values and diff_against_defaults()'s comparison (M6).
    """
    return _read_json(DEFAULTS_FILE)


def _merge_section(defaults_section, live_section):
    """One section merged: defaults filled in, live overrides where present."""
    merged = dict(defaults_section)
    merged.update(live_section)
    return merged


def load_config():
    """Return the full configuration dictionary from config.json.

    Any key missing on disk is filled in from config.defaults.json instead of
    raising or reading as 0 (M6 / CLAUDE.md: "an absent key falls back to the
    configured value, never to 0"). Sections not in the reference are passed
    through unchanged, so an operator-added section is not silently dropped.
    Deliberately does not include _config_version - that stays a property of
    config.defaults.json alone, never round-tripped into the editable config.json
    by a settings-page save (see get /api/config in app.py, static/js/settings.js).
    """
    live = _read_json(CONFIG_FILE)
    defaults = load_defaults()
    sections = [s for s in defaults if not s.startswith("_")]
    sections += [s for s in live if s not in sections and not s.startswith("_")]
    return {s: _merge_section(defaults.get(s, {}), live.get(s, {})) for s in sections}


def _diff_key(section, key, default_val, live_val):
    """One key's drift status: 'unknown' (on disk, not in defaults), 'missing'
    (in defaults, absent on disk - falls back to the default) or 'changed'
    (present in both, values differ). Returns None when the values agree.
    """
    if default_val is _ABSENT:
        return {"section": section, "key": key, "status": "unknown",
                "live": live_val, "default": None}
    if live_val is _ABSENT:
        return {"section": section, "key": key, "status": "missing",
                "live": None, "default": default_val}
    if default_val != live_val:
        return {"section": section, "key": key, "status": "changed",
                "live": live_val, "default": default_val}
    return None


def _diff_section(section, defaults_section, live_section):
    out = []
    for key in sorted(set(defaults_section) | set(live_section)):
        entry = _diff_key(section, key, defaults_section.get(key, _ABSENT),
                          live_section.get(key, _ABSENT))
        if entry:
            out.append(entry)
    return out


def diff_against_defaults(live_raw, defaults):
    """Compare raw (unmerged) live config against the shipped defaults, section by
    section, key by key. Returns a list of {section, key, status, live, default}
    dicts, sorted by section then key. Pure function, no file I/O - offline
    testable against synthetic dicts (DEVELOPMENT_RULES.md Sec.7.6/7.7).
    """
    out = []
    for section in sorted(set(defaults) | set(live_raw)):
        if section.startswith("_"):
            continue
        out.extend(_diff_section(section, defaults.get(section, {}), live_raw.get(section, {})))
    return out


def compute_config_diff():
    """Read config.json and config.defaults.json fresh from disk and return
    (diff_list, config_version) - what session.py needs at run start to log drift
    and stamp results with the version of the shipped reference they were run
    against.
    """
    defaults = load_defaults()
    diff = diff_against_defaults(_read_json(CONFIG_FILE), defaults)
    return diff, defaults.get("_config_version", 0)


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
