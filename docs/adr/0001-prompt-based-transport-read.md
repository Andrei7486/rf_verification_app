# ADR 0001: Prompt-based transport read for the NS modulator CLI

**Status:** Accepted
**Date:** 2026-08-26
**Stage:** S-M0 (spec §M7, decision D18)

## Context

Power Accuracy sends 7 modulator commands per point. Each one previously paid a fixed
post-command sleep (`cmd_delay_s`, ~1.4 s in practice) before reading whatever the socket
had buffered — regardless of how quickly the NS CLI actually finished the command. Bench
measurement (`docs/bench/power_accuracy_freqs_20260826-153750.log`) showed the modulator's
own prompt, `root@Modem -<menu>- *<N>` (N incrementing per accepted command), typically
returning well before the fixed sleep elapsed. The fixed wait was the dominant cost in the
per-point budget (~10.7 s of ~13.4 s).

The natural fix — read until the prompt appears instead of sleeping a fixed interval — runs
into a module-boundary rule from `DEVELOPMENT_RULES.md` §4: `transport.py` is link-layer
only and must carry no instrument semantics, while `modulator.py` owns DUT-specific
behaviour. The NS prompt shape (`root@Modem ... *<N>`, tolerant of `\r\r\n` framing and a
"Configuring device, Please wait ........Done." interlude between the anchor and the
counter) is instrument semantics. A literal reading of the stage's own instruction ("prompt
detection in transport.py") would have put that pattern in the link-layer module, breaking
the boundary the rest of the codebase already relies on (the CXA's SCPI reads have no
prompt at all and must not gain one).

## Decision

Split the primitive from the pattern:

- `transport.py` gains a **generic** `LineSocket.read_until_regex(pattern, timeout, require)`,
  parameterized entirely by a caller-supplied compiled regex. It has no default pattern and
  no knowledge of what a "prompt" looks like — same contract as the existing
  `read_until()` (literal substrings), just matched by regex instead. Both share a new
  private `_read_loop()` helper so the byte-level read loop exists once.
- `modulator.py` owns the NS-specific prompt regex (`_PROMPT_RE`) and calls
  `read_until_regex()` with it. `TelnetModulator._read_until_prompt()` overrides the base
  class's fixed-sleep default; `SerialModulator` keeps the fixed-sleep default unchanged
  (serial has no equivalent prompt-return signal available cheaply, and was out of this
  stage's scope).
- A bounded fallback is mandatory: `dut_prompt_wait_timeout_s` (default 3.0 s, config key
  `modulator.dut_prompt_wait_timeout_s`) caps the read, so a prompt that never appears (link
  drop, unexpected CLI state) degrades to a bounded wait rather than hanging the run.
- A second, independent config key was required alongside this one:
  `power_accuracy.dut_settle_after_power_s` (default 0.5 s). Prompt-return only means the
  `power <dbm>` command was *accepted*, not that the RF output has settled — the fixed sleep
  this change removes was accidentally also serving as a settle dwell. The legacy
  `modSettings.txt` value (0.5 s) is now an explicit, named dwell between `power` and
  `:INIT:REST`, not a side effect of unrelated per-command overhead.

## Consequences

- `transport.py` stays instrument-agnostic; the CXA's SCPI path is untouched and gains no
  prompt-matching behaviour it doesn't need.
- `modulator.py` is touched (not "transport.py only", per the stage's literal wording) —
  this was an explicit operator decision during planning (decision 2 = A) made precisely to
  avoid violating the module boundary.
- `SerialModulator` does not benefit from this stage; its per-command cost is unchanged.
  Revisiting it is a new decision, not a silent extension of this one.
- The settle dwell is now visible and tunable in config and in the run log's params
  snapshot, instead of being an unlabelled side effect of a sleep that existed for an
  unrelated reason.

## Alternatives considered

- **Prompt regex inside `transport.py` as a module-level default.** Rejected — puts NS-CLI
  knowledge in the shared link-layer module used by both the CXA and the modulator; the
  next instrument added would either inherit an irrelevant pattern or force a rewrite here.
- **No bounded fallback (wait for the prompt indefinitely).** Rejected — a missing prompt
  (dropped connection, CLI wedged) would hang the run with no recovery; the existing
  transport/SCPI retry policy (D3) assumes bounded operations.
