# RF Verification App — Development Rules

Status: **v2.0** — binding for all future work
Repo: `Andrei7486/rf_verification_app`
Last updated: 2026-08-26

Consolidated from the working practice of this project and from the architecture and process rules
established on the **BelSystem Platform** project, where they are already proven. Only the portable
parts were taken — the BelSystem technology stack, domain model and multi-user concerns do not
apply here.

These rules apply to the operator, to Claude, and to Claude Code (CC) equally. If a rule here
conflicts with an instruction given in chat, the chat instruction wins **only if it explicitly says
it is changing this document** — otherwise this document wins.

---

## 1. Working process

1. **Language.** Conversation in Russian. Code, comments, commit messages, PR descriptions,
   documentation and CC prompts in **English**. No exceptions.
2. **Read project files at session start.** `docs/JOURNAL.md`, `docs/ROADMAP.md`,
   `docs/VALIDATION_APP_SPEC.md` and any ADR relevant to the stage. Do not reason from chat memory.
3. **Resolve every open question before code.** Claude does **not** produce a CC prompt until all
   questions are answered and the operator has explicitly agreed. One final consolidated prompt —
   no draft prompts mid-discussion that then need patching.
4. **Linear, one thing at a time.** One stage in flight. The next does not start until the current
   one is merged, bench-accepted and tagged.
5. **One stage per PR.** Never bundle stages. A PR that grew beyond its stage is split, not merged.
6. **PR-gated.** CC proposes a plan → Claude reviews and gives go/no-go → CC implements → PR opened
   → operator reviews the diff → operator merges. Nothing reaches `master` unreviewed.
7. **Commits split by concern** — code / config / tests / docs — one at a time.
8. **Read-only investigation before any change.** Locate the code, grep every caller, state what
   will be touched and what will not. Only then write.
9. **Do not touch adjacent checks "while we are here".** If `power_accuracy.py` is the subject,
   `flatness.py` and `iq_validation.py` are verified untouched by grep before commit.
10. **Scope creep is flagged explicitly.** Anything CC adds beyond the stage checklist requires a
    conscious decision before inclusion — never silent adoption.
11. **No unrequested diagnostics.** Do not propose extra bench tests or root-cause hunts beyond
    what the stage's acceptance requires. Anomalies outside the plan are recorded, not chased.
12. **Decision format.** The operator answers by section and item number (e.g. "Раздел A: 1.B, 2.B").
    Structure questions so that this is possible.

---

## 2. Runtime targets and environment constraints

**Two targets. Code is written for the lower one; it is run today on the higher one.**

| Target | Role | Specification |
|---|---|---|
| **Andrei's laptop** — `DESKTOP-A5D0TD9` | **Primary today.** Development and production runs. | Windows 11 x64, Intel i5-13420H, 16 GB RAM, on the lab network alongside the CXA and the DUT |
| **NSLAB04-PC** | Future / secondary deployment | Windows 7 Pro SP1 **32-bit**, portable Python **3.8.10 win32** + Flask 2.3.3 + pyserial, `build_portable.bat` / `run.bat`. Corporate policy blocks installers and PowerShell |

**Compatibility floor — binding regardless of where the app currently runs:**

1. **Python 3.8-compatible syntax only.** No `list[str]` / `dict[str, int]` annotations at runtime,
   no `dict | dict` merge, no `match`, no 3.9+ standard library APIs.
2. **No new third-party dependency** without an explicit decision. A candidate must have a
   `cp38` **win32** wheel and install offline into the portable environment. If it is x64-only or
   needs a compiler, it is rejected — even though the laptop could install it.
3. **No PowerShell** in any script. Batch only.
4. **No frontend build step.** No npm, no bundler, no TypeScript compile. Plain HTML/CSS/JS served
   by Flask. Third-party JS, if ever needed, is vendored into the repo, not fetched from a CDN —
   the bench PC has no reliable internet.
5. **Resource assumptions are allowed, but recorded.** The laptop's 16 GB and modern browser may be
   relied on — an unbounded live log buffer, for example, is acceptable today. Every such choice is
   added to the **deferred portability list** in `docs/VALIDATION_APP_SPEC.md` §9, and that list is
   worked through as one refactor pass before any NSLAB04-PC deployment. What is not acceptable is
   making the assumption silently and discovering it on the bench PC.

Note that items 1–4 are *not* in that category. Syntax level, dependency wheels, PowerShell and
build steps are structural — they cannot be fixed by a later refactor pass without a rewrite, which
is why they stay binding now while resource limits do not.

**Network.** The app reaches the CXA at `192.168.0.5:5025` (raw SCPI, `\n`, no prompt) and the
modulator at `192.168.0.50:23`. When running from the laptop, confirm no VPN or second adapter is
stealing the route to `192.168.0.x` before reporting a connection fault as an app defect.

**Single-instrument assumption.** The instruments accept one controlling client at a time. The app
must not assume it is that client — connection failures and unexpected instrument state are normal
conditions to report, not crashes. If the app is ever installed on both the laptop and NSLAB04-PC,
only one may run a check at a time; this is an operator rule, not something the app enforces.

**Visual theme** fixed: background `#07090D`, teal/cyan accents (AYECKA dark).

---

## 3. Architecture principles (non-negotiable)

Taken directly from BelSystem and applicable here without modification.

### 3.1 Open/Closed

**New functionality is added, never bolted into existing logic.** No `if/elif` or `switch`-style
chain that grows by one branch every time a feature is added.

Adding a new capability must require: **a new module + one config entry** — and zero edits to
existing engine logic. Concretely, in this codebase:

| Extension point | A new one must be | Never |
|---|---|---|
| Check type | a new `<check>.py` deriving from `base.py` + a registry entry | a branch in a check-dispatch `if` |
| Analyzer warning / error rule (M5) | a rule entry (pattern → severity → action) | another `elif "ADC Overrange" in msg` |
| Verdict / limit evaluator | a named evaluator registered by config | inline comparison logic in the check |
| Result exporter (CSV, future formats) | a new exporter module + registry entry | a format flag threaded through the check |
| Progress / ETA estimator (U5) | a per-check estimator resolved by name | a `if check == "power_accuracy"` chain |
| Model-specific behaviour (M2.9 VCO, U6 licence) | a **model profile** in config, resolved by model string | `if model == "NS330"` anywhere in logic |

**Model-specific `if` statements are the single most likely violation in this project** — VCO band
support, attenuator compensation (IF 5.7 dB / L-band 3 dB), licence requirements, server field
applicability. All of these belong in a model profile table, not in code.

### 3.2 Config as single source of truth

Shared lists and per-model values live in configuration only — never duplicated in code. Today that
is `config/config.json`; whether it moves to YAML is open (D14). Either way:

- one place defines a value, everything else reads it;
- a new key ships with a default that reproduces current behaviour;
- an absent per-check key falls back to the configured global value — **never to `0`**;
- every key used in a run appears in the run log's parameters block;
- any key that changes what the instrument measures is documented in the spec with its units and
  derivation (e.g. `chp_integ_bw_hz` = symbol rate × (1 + roll-off) = 4 MSPS × 1.25 = 5 MHz).

### 3.3 Function size and structure

- **New functions: 10–12 lines maximum.** Longer means it is doing more than one thing — split it
  into focused helpers with names that say what they do.
- Existing over-long functions are split **when they are touched for another reason**, not in a bulk
  refactor that destroys diff review.
- Repeatable features follow the same structural template across modules, so that the second one is
  predictable from the first.

### 3.4 Readability as a requirement

Any engineer joining the project must be able to understand the structure **without explanation**.
If a piece of logic needs a verbal briefing to be followed, it is wrong regardless of whether it
works.

---

## 4. Module boundaries

| Module | Responsibility |
|---|---|
| `transport.py` | Link only — telnet / serial / socket. No instrument semantics. |
| `modulator.py` | DUT control. No analyzer knowledge. |
| `analyzer.py` | Analyzer SCPI primitives. No check logic. |
| `base.py` | Shared check scaffolding — setup, ext-gain resolution, result handling. |
| `flatness.py`, `power_accuracy.py`, `iq_validation.py` | Sequence and verdict for one check each. |

Rules:

1. **Checks do not inherit instrument state.** Each check asserts every setting it depends on.
   `:SYST:PRES` has been empirically shown **not** to clear `CORR:SA:GAIN` on this instrument —
   assume nothing is reset.
2. **A check's blast radius stays inside that check.** No global flag is flipped to make one check
   work. Per-check config keys with fallback to the global value (D5).
3. **Read back what you push.** Where a query exists: push, query, log both, WARNING if the delta
   exceeds the tolerance for that quantity (0.01 dB for gains and levels).
4. **New SCPI primitives go into `analyzer.py`**, correctly scoped — CHP-scoped nodes stay separate
   from the generic ones so other checks are unaffected.
5. **Every command sent and every response received is logged**, in order, with timestamps.
6. **Per-point fault isolation.** A point retries on transport/SCPI exception only, capped (D3),
   then is recorded as failed and the run continues. One bad point never aborts a run.
7. **Legacy method, not legacy numbers** (D1/D2). Port the sequence, the scoping and the timing
   model. Values stay ours unless separately decided.

---

## 5. Definition of Done for a stage

- [ ] Code implements exactly the requirement in the spec — no scope added.
- [ ] No new `if/elif` chain on model, check name or feature flag (§3.1).
- [ ] New functions within the 10–12 line limit.
- [ ] Config keys added with safe defaults, documented in the spec.
- [ ] Offline tests written and passing for any pure logic (§7.6).
- [ ] `docs/VALIDATION_APP_SPEC.md`, `docs/ROADMAP.md` and `docs/JOURNAL.md` updated in the same PR;
      an ADR added if an architectural decision was made.
- [ ] PR description states: what changed, what did **not** change, and **the exact bench check the
      operator should run**, including the SCPI queries to confirm.
- [ ] Operator ran the Release Smoke Test (spec §4) plus any risk-class acceptance.
- [ ] Bench logs archived under `docs/bench/` or referenced by filename in the journal.
- [ ] PR merged to `master`.
- [ ] Annotated git tag applied, `CHANGELOG.md` entry written.
- [ ] Close-phase routine run in full (§10), and `docs/progress.html` shows the stage closed.
- [ ] Operator confirms the app is usable for production work on the laptop.

If any box is unchecked, the next stage does not start.

---

## 6. Branching, tagging, release and rollback

**Branches.** `stage/<track><n>-<short-name>`, e.g. `stage/u2-immediate-run-feedback`. Branch from
`master`, merge to `master`, delete after merge.

**Commits.** English, imperative, one logical change, referencing the requirement ID:
`M6: log effective config diff against repo defaults at run start`.

**Tags.** After bench acceptance:

```
git tag -a v0.7.0 -m "Stage U2: immediate run feedback (bench-accepted 2026-09-02)"
git push origin v0.7.0
```

**Deployment.**
- *Laptop (today):* `git pull` on the tag. Keep the previous tag known so `git checkout` reverts in
  seconds.
- *NSLAB04-PC (future):* keep the working folder, rename it `app_prev`, deploy the new tag into
  `app`, run the RST. On failure, rename back and continue on `app_prev` the same day. Roll-forward
  fixes are never attempted on the bench under time pressure.

**Rollback is a first-class outcome, not a failure.** A reverted stage is re-planned, not patched
in place.

---

## 7. Testing rules

1. **The bench is the integration test suite.** There is no substitute for a real run against the
   NS330 and the CXA.
2. **Baselines are archived.** Before any R2 change, the pre-change run log is kept and named, so
   the A/B comparison is possible later.
3. **Compare like with like.** A baseline from an uncalibrated unit is not comparable with a
   post-calibration run. Record the unit's calibration state with every archived baseline.
4. **A null-valued test proves nothing.** If both sides of a comparison use the same value, the test
   cannot distinguish "asserted" from "inherited". Design it with different values. (This is the
   caveat recorded against the PR #13 verification.)
5. **Do not attribute a discrepancy without verifying it.** "Probably config drift" is a hypothesis
   and is written down as one. Guesses recorded as conclusions are how the 5–6 dB level difference
   became an unexplained open item.
6. **Pure logic is tested offline**, before the bench session: limit evaluation, ETA arithmetic,
   config diffing, warning-rule matching, CSV shaping. Bench time is the scarce resource.
7. **Test fixtures are synthetic.** No real unit data or real log files are used as fixtures.

---

## 8. Documentation and decision records

Everything below lives in the repo and is committed. **GitHub is the single source of truth; chat
history is not.** Something agreed in conversation is not agreed until it is committed.

| File | Purpose |
|---|---|
| `CLAUDE.md` | Entry point for any agent — points at the rest, states the hard constraints |
| `docs/VALIDATION_APP_SPEC.md` | What we build, acceptance criteria, decision log |
| `docs/DEVELOPMENT_RULES.md` | This file |
| `docs/ROADMAP.md` | Order of work, gates, current position |
| `docs/JOURNAL.md` | Append-only session log: what was done, decided, measured |
| `docs/adr/NNNN-*.md` | Architecture Decision Records |
| `CHANGELOG.md` | One entry per tagged release |
| `POWER_ACCURACY_HANDOFF.md`, `POWER_ACCURACY_SESSION_HANDOFF_*.md` | Legacy spec, parity plan, Decisions 1–5, per-session snapshots |
| `docs/bench/` | Archived run logs used as baselines |

Rules:

- Documentation updates ship **in the same PR** as the code they describe. Never "docs later".
- **ADRs are immutable.** A superseded decision gets a dated annotation, never a silent rewrite.
  The ADR is the source of truth; code and docs follow it.
- Numbered decisions (D1, D2, …) live in the spec's decision log and are referenced by number.
  A decision with architectural consequences is promoted to an ADR.
- Roadmap progress is recorded by ticking the stage, in the repo, not in chat.
- The session journal is written at the end of a session, while the detail is still available.

---

## 9. Rules for agent-written code (Claude Code)

1. **Work strictly to the stage in the prompt.** Do not implement the next stage "since it is
   related".
2. **CC is the verification layer for project state.** Claude's account of the repo can drift; CC
   reads real `master`. Any claim by Claude about current file contents is verified against the
   repository before being acted on.
3. **State assumptions and stop rather than guess.** Ambiguity becomes a numbered decision for the
   operator, not a silent choice in code.
4. **Never infer a requirement from the current config file and present it as a decision.** This
   happened once — the `ext_gain_db = 0` claim — and it contradicted D5.
5. **Separate what was verified from what was not.** "Bench-verified" and "mechanism confirmed by
   the outgoing command in the log" are different claims and are reported differently.
6. **Idempotency and state checks use deterministic shell commands** — `grep`, `diff`,
   `git status --porcelain` — never model reasoning over remembered file contents.
7. **No reformatting or tidying outside scope.** It destroys diff review.
8. **The PR description is written for the operator standing at the bench**: what to run, what to
   look at, what a pass looks like.

---

## 10. Phase close — CC's responsibilities

Closing a stage is CC's job, not the operator's, and it is not finished when the code merges. As on
BelSystem, there is a defined close-phase routine. CC performs all of it in one pass, commits it as
a `docs` commit, and does **not** push or merge — that stays with the operator.

1. **Update `docs/ROADMAP.md`** — move the stage's `Status` cell in the `<!-- STAGES:BEGIN -->`
   table to its new value, and fill in `Tag` and `Accepted` once the operator has bench-accepted it.
2. **Append to `docs/JOURNAL.md`** — what was done, decided, measured, and what remains open.
3. **Add a `CHANGELOG.md` entry** under the new tag.
4. **Add or annotate an ADR** if an architectural decision was made or superseded.
5. **Verify the tracker renders** — run `docs/tracker.bat`, confirm the stage moved and the
   percentage changed. A stage is not closed until the tracker shows it closed.
6. **Add any new deferred portability item** to spec §9.

### The tracker

`docs/progress.html` lives in the repository and is launched from it via `docs/tracker.bat`.
It is **not** regenerated at phase close — it parses `ROADMAP.md`, `VALIDATION_APP_SPEC.md` and
`JOURNAL.md` live in the browser, so the only thing CC updates is the source documents. This is the
BelSystem lesson about `tracker_import.json` applied from the start: there is no intermediate data
file, therefore there is nothing that can go stale.

If the tracker ever needs data that is not derivable from those documents, the fix is to add it to
the machine-readable block in `ROADMAP.md` — never to introduce a second source.

---

## 11. UI work — method

**There is no prototype and none will be made.** The existing running UI is the baseline and the
reference. Work is modernisation of what exists, not implementation of a design.

1. **Changes are specified as deltas against the current screen**: what changes, what stays exactly
   as it is. "Stays as it is" is stated explicitly — silence is not agreement.
2. **Screenshots are the review medium, before and after**, at a fixed viewport, attached to the PR.
   From BelSystem: three rounds of prose-based fix instructions failed where one screenshot
   comparison succeeded. Describing a visual difference in words is the slow path.
3. **Keep domain and presentation separate in instructions.** "Which field belongs where" is domain;
   "how many columns" is presentation. Conflating them once accidentally deleted a two-column
   layout on BelSystem. State both explicitly or state neither.
4. **No big-bang redesign.** U8 ships in slices, each independently deployable. A half-migrated
   menu never reaches `master`.
5. UI changes are R0 by definition (spec §3). If a UI change requires touching a check module,
   the classification is wrong — stop and re-plan.
