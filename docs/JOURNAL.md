# Journal

Append-only. Newest entry at the bottom. One entry per working session: what was done, what was
decided, what was measured, what is open. Written at the end of the session, while the detail is
still available.

---

## 2026-08-26 — Specification, rules and roadmap established

**Context.** Power Accuracy parity Stages 1–5 are implemented; PRs #10, #11, #13 merged and
bench-verified. NS330 calibration with `NsPowerCalibrationV6.2.jar` in progress. A pool of 11
improvement proposals was raised and needed to be turned into an agreed plan rather than a chat
thread.

**Done.**
- `docs/VALIDATION_APP_SPEC.md` — the 11 proposals plus the open measurement items converted into
  numbered requirements M1–M6 (measurement) and U1–U8 (interface), each with rationale, acceptance
  criteria, risk class and config keys.
- `docs/DEVELOPMENT_RULES.md` — process, architecture and testing rules. Architecture principles
  (Open/Closed, config as single source of truth, 10–12 line functions, readability without
  explanation), ADR practice, agent rules and the UI prototype/screenshot method were carried over
  from the BelSystem Platform project, where they are already proven.
- `docs/ROADMAP.md` — P0 gates plus stages S0–S13, with the IQ track preempting the queue once the
  legacy `.class` files arrive.
- `CLAUDE.md`, `CHANGELOG.md`, this journal.

**Decided.**
- Release contract: `master` always deployable, one stage per PR, every stage bench-accepted and
  tagged before the next starts, behaviour changes behind flags defaulting to current behaviour.
- Risk classes R0/R1/R2 determine the acceptance procedure per requirement.
- Release Smoke Test defined: 14-point Power Accuracy (950/2150 MHz) + 25-point Flatness, under
  10 minutes, run after every merged stage.

**Environment change.** The app now runs from Andrei's laptop (`DESKTOP-A5D0TD9`, Windows 11 x64,
i5-13420H, 16 GB) connected to the lab network, not from NSLAB04-PC. NSLAB04-PC (Windows 7 Pro SP1
32-bit) remains a possible future deployment, so the Python 3.8 / win32 / no-installer
compatibility floor is retained for all code. Recorded as D17.

**Correction recorded.** The bench report's claim that `ext_gain_db = 0` is correct for all three
checks in validation mode is unsupported and contradicts D5. It was inferred from the config, never
decided. `iq_validation` runs at −3.5 dB.

**Decisions D6–D17 closed** the same day, all accepted as proposed: SSE with polling fallback for
live logs; overload warns and marks the point suspect; ETA structural first and statistics later;
analyzer screen via the CXA web UI iframe; insufficient licence warns and requires confirmation;
the speed work may reduce overhead only and may not reopen parity; Run page selections persist
server-side across restart; the IQ tolerance is set from the first comparison run; config stays
JSON; ADRs and this journal are adopted; minimal CI folded into S1; the Python 3.8 / win32
compatibility floor is retained indefinitely.

**Tracker.** `docs/progress.html` plus `docs/tracker.bat` added. It parses `ROADMAP.md`,
`VALIDATION_APP_SPEC.md` and `JOURNAL.md` live in the browser — there is no intermediate data file,
so it cannot go stale. Ownership recorded in `DEVELOPMENT_RULES.md` §10: CC runs the close-phase
routine at the end of every stage and updates the source documents; the HTML itself is not
regenerated.

**Open.** Awaiting the BelSystem tracker
materials and the `/close-phase` definition, to align the close-phase routine with what already
works there, and to decide whether stage hour estimates are wanted alongside the S/M/L weights.
P0 gates (calibration, front-panel
`:CORR:SA:GAIN` read, `pwr_calibration.csv` presence, short post-calibration run and its archived
baseline) block S9 onward. Legacy IQ `.class` files block the M-track.

---

## 2026-08-26 — S-M0: Power Accuracy per-point overhead

**Context.** Operator reported Power Accuracy running ~5.5x slower than the legacy Java tool.
Measured against the archived bench log `results/power_accuracy_freqs_20260826-153750.log`
(now `docs/bench/power_accuracy_freqs_20260826-153750.log`) — run ended cleanly ("Verdict: PASS",
normal `tx disable`/`sine off` cleanup) at point 18/432, operator-aborted, not crashed. Unit
calibration state at capture time was **pre-P0.1** (calibration JAR not yet run), so absolute
`Actual_dBm` values in that log are not representative of a calibrated unit — only relative timing
and point-to-point structure were used from it.

**Measured.** Per-point budget ≈13.4 s: 7 modulator commands ≈10.7 s (flat ~1.4 s/command
regardless of command content — `top`/`line` included — the modulator prompt returns well before
the fixed post-send wait elapses, but the transport always sleeps the full fixed interval instead
of watching for it), `:READ:CHP:CHP?` ≈2.0 s (correct — CHP-scoped, D11, untouched),
`:INIT:REST` ≈0.4 s (correct — untouched). Point 1 → point 16 `Measured:` line on the archived
50 MHz/16-point block: **219.141 s** measured directly from log timestamps, independently confirming
the operator's ~219 s figure. The "legacy tool ≈40 s" figure is operator-reported; it could not be
independently corroborated against any file in this repository and is recorded as such, not as a
verified number.

**Done — S-M0 (spec §M7, D18).**
- Item 1 (R1): DUT-side ADC power cross-check gated behind
  `power_accuracy.enable_adc_power_check`, default **off** (renamed from `read_adc_power`, which
  defaulted **on**). When off, the modulator never leaves `-line-` and `top`/`-adc-power`/
  `get-power`/`-modulator-config`/`line` are not sent. `ADC_Power_dBm` stays a CSV column, empty
  when the check is off. Code path not deleted.
- Item 2 (R1): `freq` sent only when it changes within a block — the DUT stays tuned across a
  power sweep at one frequency, so resending it every point was a pure round-trip with no effect.
  Analyzer-side `:FREQ:CENT` is unchanged (cheap, and the analyzer has no menu-navigation state to
  lose).
- Item 3 (R2): transport read on the telnet modulator path changed from a fixed post-command sleep
  to reading until the NS CLI prompt (`root@Modem ... *<N>`, N incrementing per accepted command)
  is seen, bounded by `dut_prompt_wait_timeout_s` (default 3.0 s) so a missing prompt degrades to a
  bounded wait instead of hanging. Mandatory companion:
  `power_accuracy.dut_settle_after_power_s` (default 0.5 s, the legacy `modSettings.txt` value) —
  an explicit dwell after `power <dbm>` and before `:INIT:REST`, since prompt-return only means the
  command was accepted, not that the RF output has settled. Serial modulator path unchanged
  (fixed sleep retained — only the telnet path had the overhead being fixed).
- New generic `LineSocket.read_until_regex()` in `transport.py` (no NS-specific pattern — the
  pattern is caller-supplied), with the NS prompt regex owned by `modulator.py`. Resolves the
  module-boundary question opened during planning (`DEVELOPMENT_RULES.md` §4: transport.py carries
  no instrument semantics) — see `docs/adr/0001-prompt-based-transport-read.md`.
- Offline tests added (synthetic fixtures only): prompt-regex matcher (recognises the real prompt
  shape, tolerates `\r\r\n` framing and a "Configuring device...Done." interlude, does not
  false-match on command echo) and the freq-change tracker (resends on change, suppresses on
  repeat, resends at a block boundary). Existing ADC cross-check test rewritten for the new
  default-off gate. All offline tests pass.
- Constraint held: `chp_average_count`, the `INIT:REST` wait, sweep-time AUTO and all CHP-scoped
  SCPI nodes untouched — D11 not reopened. Verified by grep that `flatness.py` and
  `iq_validation.py` have zero references to any new S-M0 identifier and zero diff on this branch.

**Decided.** D18 — items 1–2 (R1) and item 3 (R2) ship in one PR by operator decision, with a
stated per-item rollback: if bench acceptance criterion 3 (value parity) fails, item 3 alone
reverts; items 1–2 stay since neither changes what the instrument reports. Acceptance criterion 1
redefined during planning to measure from the `--- Point 1/N ---` log line to the last `Measured:`
line (excludes one-time setup), threshold under 60 s, baseline 219.1 s; setup-phase time reported
separately with no threshold (criterion 1b).

**Open.** Bench acceptance (spec §M7, redefined criteria 1–6) not yet run against real hardware —
pending lab network access. `docs/adr/0001-prompt-based-transport-read.md` and the bench-log
archive under `docs/bench/` are part of this same entry's close-phase routine.

---

## 2026-08-27 — S-M0: pre-merge correction on PR #16

**Found.** As first implemented, `use_prompt_read` (item 3) was decided at `TelnetModulator` class
level, shared by all three checks through one modulator instance — Flatness and IQ Validation would
have silently inherited the new timing despite zero diff in their own files. Flagged as a
`DEVELOPMENT_RULES.md` §4.2 blast-radius violation (a check's blast radius stays inside that check)
and a §2.4 violation (a new key's default must reproduce today's behaviour for a check that has not
explicitly opted in).

**Fixed.** `use_prompt_read` is now a per-check config key, resolved by `base.resolve_use_prompt_read()`
the same way `ext_gain_db` is resolved (D5): the check's own section wins, absent key falls back to
`False`. `TelnetModulator` supports both the fixed-sleep and prompt-based reads but decides neither
itself — `session.py` calls `mod.set_prompt_mode(...)` once per run, generically, right after
`connect()`. `flatness.py` and `iq_validation.py` needed zero changes (grep-verified, zero diff).
Defaults: `power_accuracy.use_prompt_read=true`, `flatness.use_prompt_read=false`,
`iq_validation.use_prompt_read=false`. `use_prompt_read` added to the run log params snapshot for
every check. `docs/adr/0001-prompt-based-transport-read.md` annotated (not rewritten) with this
correction.

**Also fixed.** Acceptance criterion 3 rewritten from "compare against the archived pre-P0.1 log"
to a same-session A/B on the same unit (`DEVELOPMENT_RULES.md` §7.3, compare like with like — the
archived log's calibration state does not match whatever the unit is at merge time). Criteria 7
(settle-time distinguishing test, run B at `dut_settle_after_power_s=0.5` vs `1.5` — §7.4, a
null-valued test proves nothing) and 8 (Flatness regression guard) added.

**Recorded, not acted on.** Item 2 (`freq` sent only on change) assumes `power <dbm>` does not
disturb the DUT's tuned frequency. Untested assumption — criterion 3's A/B is also the check for
this.

**Rebase.** PR #15 (S0) is still unmerged at the time of this correction — the rebase of this
branch onto updated `master` is pending the operator merging #15 first; noted here so it is not
forgotten once that happens.

**Status.** `ROADMAP.md` S-M0 row set to `in-review` (not `done`), tag column stays `—`. No
annotated tag, no `CHANGELOG.md` entry — §2.6 is deferred, not waived.

**Standing warning, recorded verbatim as instructed:**

> S-M0 merged without bench acceptance; acceptance criteria 1-8 outstanding.
> Bench access unavailable at merge time. Power Accuracy results are not to be
> trusted for production until the A/B in criterion 3 has been run.
> Flatness and IQ Validation are unaffected by default (use_prompt_read=false).

---

## 2026-08-27 — PR #15 and PR #16 merged

**Merged.** PR #15 (S0) merged into `master` on operator instruction. `stage/s-m0-power-accuracy-overhead`
rebased onto the updated `master` — clean, no conflicts, re-verified afterward (compile clean, all
20 offline tests pass, grep against `flatness.py`/`iq_validation.py` still empty). PR #16 retargeted
from `stage/s0-documentation-scaffolding` to `master` and, on explicit operator instruction, merged
the same day — **before bench acceptance criteria 1–8 were run.**

Before merging, the operator was shown the standing warning above (PR #16's own description said
"do not merge until acceptance criteria 1–8 have been run") and confirmed merging anyway. This is
recorded as an explicit operator override, not an oversight: `power_accuracy.use_prompt_read=true`
is now the default on `master`, so the next Power Accuracy run on the laptop uses the unverified
prompt-based read and freq-on-change logic in production. `flatness.use_prompt_read` and
`iq_validation.use_prompt_read` stay `false`, so Flatness and IQ Validation are unaffected.

**The standing warning above still applies and is not superseded by the merge** — merging to
`master` is not the same as bench acceptance under this project's Definition of Done (§5): no
annotated tag was applied, no `CHANGELOG.md` entry was written, and `ROADMAP.md`'s S-M0 row stays
`in-review`, not `done`. Criteria 1–8 remain outstanding and should be run at the next bench
session; if criterion 3 fails, item 3 (the prompt-based read, `use_prompt_read`) is the one to
revert — flip `power_accuracy.use_prompt_read` back to `false`, no code change required.

**Housekeeping.** Both stage branches (`stage/s0-documentation-scaffolding`,
`stage/s-m0-power-accuracy-overhead`) deleted, locally and on `origin`, per `DEVELOPMENT_RULES.md`
§6 (merge to `master`, delete after merge).

---

## 2026-08-27 — Partial bench test: serial-only A/B, S-M0 items 1 and 2

**Operator-unconfirmed at the time it was run.** This test was performed by CC during the session
and was not witnessed, reviewed, or agreed by the operator at the time. It is recorded here as
what the archived files show — a claim about what happened, not an operator-witnessed bench
acceptance. Same treatment as the "legacy 40 s" figure in the M7 entry above: attributed, not
asserted as fact beyond what the artifact supports.

Session narrative: CXA (192.168.0.5:5025) reachable after a reconnect. The modulator's telnet path
(192.168.0.50:23) accepted the TCP connection but the DUT's CLI never produced a banner or replied
to any command — `Actual_dBm` came back flat (~−67 dBm) across a full 16-point sweep, tracking
nothing. **Operator confirmed this is a configuration issue on a different station, unrelated to
this app** — to be re-verified separately, on telnet, by the operator.

To unblock testing what could be tested that session, switched `modulator.dut_conn_type` to
`serial` (COM5). Ran the spec §M7 criterion-3 recipe over serial. Evidence, archived in-repo (not
`results/`, which is `.gitignore`d and local-only) at
`docs/bench/power_accuracy_NS330_20260827-130957_serial-runA.{log,csv,json}` (Run A,
`13:10:13`–`13:12:10`) and `docs/bench/power_accuracy_NS330_20260827-131303_serial-runB.{log,csv,json}`
(Run B, `13:13:19`–`13:14:13`); transport confirmed by grep — both logs read
`Modulator connected via serial COM5 @ 115200`, not telnet:

- Run A (`enable_adc_power_check=true`, `use_prompt_read=false`): PASS, 16/16, `Actual_dBm`
  correctly tracked `Set_dBm` (max deviation 0.21 dB, within `pwr_tolerance_db=0.8`) — the flat
  −67 dBm reading on the dead telnet session was the dead session, not a hardware or calibration
  problem.
- Run B (`enable_adc_power_check=false`, `use_prompt_read=true`): PASS, 16/16.
- Point-by-point `|A−B|`: max **0.07 dB**, tolerance 0.1 dB.
- Criteria 2, 4, 5, 6 also observed in Run B's log: `MOD freq` sent once (Point 1, not resent);
  `top`/`-modulator-config`/`line` appear only in `modulator_setup()`, never between points;
  `:CORR:SA:GAIN?` read-back present.

**What this test can and cannot support.** It bears on items 1 and 2 (the ADC gate and
freq-on-change) only — including the untested assumption flagged in spec §M7, that `power <dbm>`
does not itself disturb the DUT's tuned frequency. It does **not** exercise item 3:
`SerialModulator` always uses the legacy fixed sleep, and `use_prompt_read` only branches
`TelnetModulator._read_until_prompt()` — the key had no effect on this run regardless of its
value. Criterion 1 (Point 1 → last `Measured:`, target under 60 s) measured 54.5 s on this serial
run; that number says nothing about item 3 — it reflects only items 1 and 2 on an already-fast
serial link. Criterion 3's telnet case, and criteria 1, 7 and 8 in full, remain unrun and
unconfirmed — this entry does not close any of them, and S-M0-V (opened 2026-09-07) still owns
that debt.

---

## 2026-09-07 — S-M0 closed, acceptance DEFERRED

S-M0 closed 2026-09-07 by operator decision without bench acceptance.
Criteria 1-8 outstanding, in particular the same-session A/B (criterion 3) and the
settle-time distinguishing test (criterion 7).
dut_settle_after_power_s = 0.5 is carried over from legacy modSettings.txt and has
never been verified on this unit. If Power Accuracy levels later read low across
all points, this key is the first suspect.
Operator intends to verify by other means.
Revert without a code change: power_accuracy.use_prompt_read = false and
power_accuracy.enable_adc_power_check = true.

Recorded in `docs/ROADMAP.md`: S-M0 status `done-unverified`, accepted `deferred`, tag `v0.7.0`
reserved. Follow-up stage **S-M0-V** opened (track M, weight 1, status `planned`) to close this
verification debt when instruments are available again — it runs spec §M7's criteria 1–8 in full,
including a telnet re-run of criterion 3 (2026-08-27's A/B above used serial, which does not
exercise item 3).

---

## 2026-09-07 — Correction on the S-M0 closure, pre-push review

Two issues found before this closure's docs branch was pushed.

**1. Tag applied on the wrong commit.** `v0.7.0` was created as an annotated tag pointing at the
closure branch's own tip, before the branch was even merged — per `DEVELOPMENT_RULES.md` §6, tags
go on `master` after the merge, not on a feature branch before it. If the PR were not fast-forwarded,
the tag would sit on a commit absent from `master`'s history. Fixed: `git tag -d v0.7.0` (local
only, never pushed). The tag will be recreated on `master`, pointing at the actual merge commit,
once the operator merges this closure's PR — not before.

**2. The 2026-08-27 serial-test journal entry needed sourcing, not deletion.** The operator had no
record of that test and asked for concrete, deterministic evidence (§9.6) before letting an
unsourced claim stand in an append-only file. Evidence produced: `ls`/`grep` against the actual
result files on disk (`results/power_accuracy_NS330_20260827-{130957,131303}.{log,csv,json}`,
`.gitignore`d and therefore local-only — not previously visible to `git log`/`git status`),
confirming the Point 1/Point 16 timestamps and, by grep for `Modulator connected via`, that both
runs used `SerialModulator`, not `TelnetModulator`. The files themselves were never in the repo.
Fixed, per operator instruction: copied both runs into `docs/bench/` (not `.gitignore`d, so the
evidence now lives in the repo rather than only on the operator's disk) as
`power_accuracy_NS330_20260827-130957_serial-runA.{log,csv,json}` and
`..._131303_serial-runB.{log,csv,json}`; added a `docs/bench/README.md` entry; the 2026-08-27
journal entry above, and every other reference to that test (spec §M7 status note, `ROADMAP.md`
Current position and S-M0/S-M0-V narrative), now marked **operator-unconfirmed** and re-pointed
at the archived path instead of the local-only one.

PR #18 (this closure) reviewed and merged. Tag `v0.7.0` created for real afterward, on `master`,
pointing at the actual merge commit (`3e88ba1`) — not the branch tip it was mistakenly created on
before the fix above. Pushed. Branch `docs/s-m0-close-deferred` deleted, local and `origin`.

---

## 2026-09-07 — S1: config integrity and drift detection (M6), D16 CI folded in

**Context.** Spec §M6, roadmap stage S1 — next in the ordering, S0/S-M0/S-M0's closure all merged.
Real, confirmed precedent for what this stage exists to catch: `chp_integ_bw_hz` read
8 000 000 on the bench instead of 5 000 000 (span mistaken for integration bandwidth,
`POWER_ACCURACY_HANDOFF.md` §8) — recorded as "the first confirmed instance of bench config
drift". A second, unconfirmed suspect (an unexplained 5–6 dB level difference) is still an open
hypothesis, not something this stage claims to resolve.

**Plan reviewed before implementation**, per the established process. Two decisions needed before
code:
- Fix the three pre-existing `.get(key, 0)` fallbacks (`flatness.py`'s `lband_atten_db`;
  `power_accuracy.py`'s `if_atten_db`, `lband_atten_db`) as part of this stage, or leave as a known
  debt? **Operator: fix now.**
- D16 (CI) in the same PR as M6, or split? **Operator: same PR, per the roadmap's own text.**

**Done.**
- New `config/config.defaults.json` — committed, bundled (`paths.resource_dir()`, same location
  already used to seed a frozen build's first-run config), read-only. Same six sections as
  `config.json`, snapshotted from `master`'s committed values (not the bench-drifted working
  copy), plus `_config_version: 1`.
- `config_store.load_config()` now merges the live file over `config.defaults.json` — a key
  missing on disk resolves to the shipped default, never `KeyError`, never a silent `0`. No check
  module needed a change to benefit from this.
- New `config_store.diff_against_defaults()` (pure, offline-testable) classifies every key as
  `missing` / `unknown` / `changed`; `compute_config_diff()` wraps it with real file reads.
  `session.py` calls it at `start()`, before anything else in the run header.
- `logger.py`: `log_header()` gained a "Config drift vs repo defaults (version N)" block (or
  `(none)`); `write_results()` stamps `config_version` — `# config_version: N` as the CSV's first
  line, a `"config_version"` field in the JSON. Nothing in the app re-reads its own CSVs (checked
  by grep), so the leading comment line is safe.
- Fixed the three `.get(key, 0)` spots (operator decision above) — `flatness.py`,
  `power_accuracy.py`. Grepped the whole codebase for the same pattern first: these were the only
  three; `iq_validation.py` has none and was not touched.
- D16: `.github/workflows/ci.yml` — `ruff check .` + `python -m tests.test_sequences`, on push,
  under Python 3.8 (to catch 3.9+-only syntax a newer local interpreter would silently accept).
  `ruff.toml` scoped to pyflakes only (`select = ["F"]`), not pycodestyle — a first full-repo lint
  run found 192 pycodestyle hits (119 line-length, 73 semicolon-joined statements), all of them
  this codebase's established compact style, not bugs; enabling pycodestyle would mean either
  reformatting the whole repo (`DEVELOPMENT_RULES.md` §9.7: no tidying outside scope) or permanent
  noise. The one genuine pyflakes hit (`core/modulator.py`: `TransportError` imported, never used)
  was fixed so CI's first run on this branch is green, not red for an unrelated pre-existing issue.
- Design record: `docs/adr/0002-config-defaults-and-drift-detection.md`.
- Offline tests added: `diff_against_defaults()` status classification (missing/unknown/changed/
  matching), underscore-prefixed sections skipped, `config_store.load_config()` +
  `compute_config_diff()` exercised end-to-end via temporary scratch files (not the operator's real
  config files), and a sanity check that `config.defaults.json` itself parses and is versioned.
  24/24 offline tests pass.
- Manually exercised `logger.py`'s new rendering (drift block, CSV/JSON version stamp, the
  `(none)`-drift case) against synthetic data — `RunSession.start()` needs live hardware and is not
  covered by the offline suite, so this wiring was checked by direct invocation, not an automated
  test. Also manually confirmed `compute_config_diff()` against the real, currently bench-drifted
  `config.json` — correctly flagged five real drifted keys (`flat_power_dbm`, `dut_com_port`,
  `dut_telnet_port`, `lband_atten_db`, `pwr_step_db`), a live demonstration of the mechanism working
  before any test was written for it.

**Not chased.** Spec §M6 cites "Source: handoff §4", but `POWER_ACCURACY_HANDOFF.md` §4 is the
legacy modulator sequence, not config drift (§9's open-items table is the actual match). Minor,
pre-existing, not part of this stage's scope — noted, not corrected.

**Open.** `config.defaults.json` is kept in sync by hand; a new config key added without a
matching defaults entry will show as `unknown` forever until someone adds it there too — a
deliberate visible nudge, not an enforced check. `_config_version` bumps are also manual. Full
rationale in ADR 0002.

PR #19 reviewed and merged. Live CI ran green on both the `push` and `pull_request` events
(`ruff check .` + the offline test suite), confirmed via the GitHub Actions API before reporting
the stage done. `master` fast-forwarded; branch `stage/s1-config-integrity-drift` deleted, local
and `origin`.

---

## 2026-09-08 — S2: immediate response after Start Run

**Context.** Spec §U2, next in the ordering after S1. `startRun()` (`static/js/app.js`) `await`ed
the full `/api/run/start` round-trip — server-side `SESSION.start()` connects to the CXA, connects
to the modulator, and runs the whole `modulator_setup()`/`analyzer_setup()` sequence (real seconds
of wall-clock time) — before the UI changed at all. Exactly the problem spec §U2 names: "the test
is already running in the terminal while the UI still looks idle."

**Design note worth recording.** The server already writes every log line into the same
process-wide live-log ring buffer (`core/logger.py`'s `_LIVE` deque) that `/api/run/logs` reads
from, and does so *during* `SESSION.start()`'s connect/setup sequence — well before the HTTP
response for `/api/run/start` returns. This meant "the first log lines appear immediately" (one of
§U2's four bullets) was achievable without building any of U3's real-time streaming — just by
having the client start polling `/api/run/logs` *before* the start call resolves, not after.
Verified this directly, without touching hardware: a synthetic `RunLogger` sequence with small
delays standing in for real instrument I/O, polled concurrently by a second thread — confirmed
`live_tail()` surfaces each line as it's written, mid-sequence, not only after the sequence ends.

**Plan reviewed before implementation.** One structural choice: transition immediately into a
stripped "Starting …" run panel with the log visible (delivers all four §U2 bullets, including the
live log during connect) vs. a lighter inline indicator left on the setup panel (simpler, but
doesn't surface log lines during connect at all, since the log view lives inside the run panel).
**Operator: transition immediately (recommended option).**

**Done.**
- `static/js/app.js` only. `startRun()` now calls a new `enterStartingUi(auto)` synchronously,
  before firing the `/api/run/start` request — disables `startBtn`, hides the setup panel, shows
  the run panel in a "Starting …" state (log cleared, `stopBtn`/`measureBtn`/`nextBtn`/`skipBtn`
  disabled — a click on `Stop` during the connect window would otherwise hit `session.py`'s "No
  run in progress", since `active` isn't set `True` until setup finishes), and starts log polling.
- New `finishEnteringRunUi(info)` — runs once the start call resolves, does what the old
  `enterRunUi(info)` used to do minus the parts already handled immediately: fills in the real
  title/columns, re-enables the mode-appropriate buttons, switches auto mode from log-only polling
  to the full status-polling loop.
- New `exitStartingUi(message)` — the error path: stops polling, reverts to the setup panel,
  re-enables `startBtn`, shows the error. Symmetric with the old behavior, just reached via a
  different route.
- Bug caught while writing this: neither old code nor a naive port ever re-enabled `startBtn`
  after a *successful* start — it would have stayed disabled forever once a run finished, since
  nothing set it back. Fixed by re-enabling it in `newRun()`, the only path back to the setup
  panel after a completed/stopped run.
- "A second click … says so" (§U2 acceptance): read as the disabled/dimmed button state itself
  being the signal, matching this app's existing pattern (`nextBtn` in manual mode) rather than a
  separate toast/message. Not re-confirmed with the operator before implementing — flagged in the
  spec note; revisit if a more explicit signal is wanted.
- `session.py`/`app.py`'s `/api/run/start` route: **untouched**. No SCPI/DUT sequencing, timing,
  or reordering — pure R0.

**Not done — recorded, not silently skipped.** `DEVELOPMENT_RULES.md` §11.2 asks for
screenshot-based before/after review on UI stages. No browser automation tool is available in
this environment (no `chromium-cli`, no local Playwright install) and installing one is a
nontrivial side task nobody asked for. Verified instead by full code-path tracing (traced both the
success and error flows by hand) plus the hardware-free live-log-buffer check above, and by
`node --check` for JS syntax. No JS test infrastructure exists in this repo (no Jest/jsdom) to
write an automated test against either — this is consistent with how every other JS-only change in
this repo has been verified so far, not a gap introduced by this stage.

**Open.** Actual visual confirmation (does it *look* right, does 200 ms actually feel instant) is
the operator's job at the bench, same as every R0 stage's Release Smoke Test. If a real
screenshot-based UI review loop is wanted for future UI stages (S3–S13 are mostly `U`-track), it
would need Playwright or an equivalent installed in this environment first.
