# CLAUDE.md — agent entry point

Repository: `Andrei7486/rf_verification_app`
Operator: Andrei (BelSystem / AYECKA)

Read this file first, then the documents it points to. Do not reason about this project from
memory or from chat history — the repository is the source of truth.

---

## What this is

A Flask web application that runs three RF checks against NovelSat modulators and a Keysight CXA
N9000B spectrum analyzer: **Flatness**, **Power Accuracy**, **IQ Validation**. It replaces a set of
Tera Term macros and legacy Java tools. The legacy tools are the known-good reference — where the
app disagrees with them, the app is wrong.

---

## Read before doing anything

| Order | File | Why |
|---|---|---|
| 1 | `docs/DEVELOPMENT_RULES.md` | How code is written, reviewed, released. Binding. |
| 2 | `docs/VALIDATION_APP_SPEC.md` | Requirements, acceptance criteria, decision log D1–D13 |
| 3 | `docs/ROADMAP.md` | Stage order, gates, current position |
| 4 | `docs/JOURNAL.md` | What happened last session |
| 5 | `POWER_ACCURACY_HANDOFF.md` | Legacy spec, parity plan, Decisions 1–5 |
| 6 | `docs/adr/` | Any ADR relevant to the stage being worked on |

---

## Hard constraints — violating these breaks the build or the bench

- **Python 3.8-compatible syntax only.** Target is portable Python 3.8.10 **win32** on Windows 7
  32-bit, even though development currently runs on a Windows 11 x64 laptop.
- **No new third-party dependency** without an explicit operator decision. It must have a `cp38`
  win32 wheel and install offline.
- **No PowerShell**, no npm, no frontend build step, no CDN-fetched assets.
- **One stage per PR.** Never bundle. Never implement the next stage because it looks related.
- **Checks never inherit instrument state** — each check asserts its own settings and reads them
  back. `:SYST:PRES` does not clear `CORR:SA:GAIN` on this instrument.
- **An absent per-check config key falls back to the configured global value, never to `0`.**
- **No `if model == ...` anywhere in logic.** Model-specific behaviour lives in a config profile.
- **New functions: 10–12 lines maximum.**
- **IQ Validation must not be run** until `iq_validation.ext_gain_db = -3.5` is merged (spec M1).

---

## Language

Conversation with the operator: Russian. Everything in this repository — code, comments, commits,
PR descriptions, documentation: **English**.

---

## Workflow

Discuss → all questions resolved → one consolidated prompt → CC produces a plan → plan reviewed →
implement → PR → operator reviews the diff → merge → bench-accept → tag.

Commits are split by concern: code / config / tests / docs.

At the end of every stage CC runs the close-phase routine in `docs/DEVELOPMENT_RULES.md` §10:
update the stage table in `docs/ROADMAP.md`, append to `docs/JOURNAL.md`, write the `CHANGELOG.md`
entry, add or annotate an ADR if needed, and confirm `docs/progress.html` reflects the change.
The tracker is never regenerated — it reads those documents live.

Anything outside the stage checklist is flagged for a conscious decision, never silently added.
