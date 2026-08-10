"""Core package for the RF Verification App.

Layers:
  config_store  - load/save externalized config and per-unit frequency lists
  transport     - raw-socket line client (SCPI / CLI)
  analyzer      - Keysight CXA SCPI control
  modulator     - NS modulator (telnet or serial)
  checks/       - one module per check (flatness, power accuracy, IQ validation)
  session       - the run state machine that drives a check
  logger        - per-run .log / .csv / .json output
"""
