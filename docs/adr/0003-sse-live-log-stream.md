# ADR 0003: Server-Sent Events for the live log stream

**Status:** Accepted
**Date:** 2026-09-08
**Stage:** S3 (spec §U3, decision D6)

## Context

Spec §U3 requires DUT/analyzer log lines to appear in the UI "as they happen — not batched, not
after part of the check completes," with an acceptance bar of "within ~1 s." D6 (already decided,
before this stage: "SSE from Flask 2.3.3 with a polling fallback; no new dependencies") settled
the transport question in principle. This ADR is the design that implements it — what D6 left
open.

Before this stage, the client polled `GET /api/run/logs?since=N` on a 1 s `setInterval` (inherited,
unchanged since before S2/S3). That already meets the letter of the ~1 s acceptance bar in the
average case, but not reliably: worst-case latency for a line written just after a poll fired is
just under the full interval, and every poll is a full HTTP request/response round-trip whether or
not anything new happened.

## Decision

**Server** (`core/logger.py`, the module that already owns the live-log ring buffer and
`live_tail()`):

- New generator `stream_live(after_seq=0, poll_interval=0.2)`. Internally it still polls
  `live_tail()` — no new threading primitive (no `Condition`/`Event`) — at a fifth of the old
  client interval. This is not "real push" in the strictest sense, but it is simple, correct under
  concurrent listeners (each generator instance tracks its own `seq` locally; `live_tail()` is a
  stateless read), and consistent with this project's preference for legible mechanisms over
  clever ones (D14's same reasoning, applied here to a different question).
- Each line's SSE `id:` is reconstructed from the batch as `enumerate(lines, start=seq+1)`.
  `_LIVE_SEQ` increments by exactly 1 per append with no possibility of a gap (verified by reading
  `_live_append()`), so this reconstruction is exact, not a guess — it doesn't require
  `live_tail()` to change its return shape (which several other callers already depend on, e.g.
  `GET /api/run/logs`, `enterStartingUi()`'s fallback path).
- Line text is JSON-encoded inside `data:` so a multi-line buffered value (the modulator's raw
  telnet echo, logged at DEBUG, occasionally spans lines) can't be mistaken for multiple SSE
  events — SSE treats a bare newline as a field separator.

**Server** (`app.py`): one thin route, `GET /api/run/logs/stream`, wiring HTTP framing
(`Response(..., mimetype="text/event-stream")`) around the generator. `Last-Event-ID` (sent
automatically by the browser on every `EventSource` reconnect) takes priority over `?since=`,
which only matters for a page's very first connection.

**Client** (`static/js/app.js`): `startLogStream()` opens an `EventSource`; `onmessage` appends
each line and advances `LOG_SEQ` from `ev.lastEventId`. Falls back to the pre-existing
`pollLogs()`/1 s-interval mechanism (renamed `startLogPollFallback()`, otherwise untouched) in two
cases: `EventSource` doesn't exist on `window` at all (feature-detected before ever constructing
one — matters for the eventual Windows 7/older-browser target, `DEVELOPMENT_RULES.md` §2), or the
connection reaches `readyState === CLOSED` (genuinely given up). A transient drop that leaves the
connection `CONNECTING` is deliberately left alone — the browser's own native reconnect (which
sends `Last-Event-ID` for a gap-free resume) handles that case on its own; forcing a fallback on
every `onerror` regardless of `readyState` would throw away a connection that was about to
self-heal.

Status polling (`pollOnce()`, auto mode only) and log streaming are now fully independent — before
this stage, the same interval/variable (`POLL`) served double duty depending on mode, so log
delivery was implicitly bounded by the status-poll cadence in auto mode.

## Consequences

- The acceptance bar ("within ~1 s") is now met with a comfortable margin (`poll_interval=0.2`,
  i.e. worst case ~200 ms plus one HTTP round trip on connect) when SSE is in use, and exactly as
  before (unchanged 1 s polling) when the fallback is active.
- `core/session.py` — the module that actually runs `modulator_setup()`/`analyzer_setup()` and
  every measurement command — is untouched. This stage only changes how already-written log lines
  reach the browser, not what gets logged or when; R0 holds.
- The existing `GET /api/run/logs` endpoint and its `live_tail()` contract are unchanged and still
  serve the fallback path directly — no duplicated logic between the two transports.
- The browser-side log buffer (`$("logView").textContent`, grown by `appendLogLine()`) is still
  unbounded for the duration of a run — already recorded in spec §9 as a deferred item attributed
  to U3 (this stage), not a new concern this ADR introduces.

## Alternatives considered

- **A `threading.Event`/`Condition` for true push instead of a tight poll loop.** Rejected for
  now — correctly supporting multiple concurrent SSE listeners without one clearing a flag the
  others still needed would add real complexity (per-listener event objects, or a
  broadcast/pub-sub structure) for a benefit (removing the last ~0–200 ms of latency) this
  single-operator app doesn't need. Revisit if multiple simultaneous viewers become a real use
  case.
- **Falling back to polling on every `onerror`, unconditionally.** Rejected — `EventSource` fires
  `onerror` for transient drops it's already about to recover from on its own; abandoning the SSE
  connection at the first sign of trouble would make the "fallback" path trigger constantly on any
  network hiccup, defeating the point of preferring SSE at all.
- **Keeping log delivery tied to the status-poll interval (as it was for auto mode before this
  stage).** Rejected — ties a UI concern (log visibility) to a data concern (point/verdict state)
  that happens to share a timer today but has no reason to share one going forward, and manual
  mode already needed logs independent of any status poll.
