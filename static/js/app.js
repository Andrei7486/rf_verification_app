"use strict";
async function postJSON(url, body) {
  const res = await fetch(url, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
  return data;
}
async function getJSON(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
  return data;
}
const $ = (id) => document.getElementById(id);
let RUN = null, POLL = null, LOG_SEQ = 0;
// U3/D6: the live log is a stream (EventSource) independent of status polling,
// with LOG_POLL as the D6-mandated fallback when SSE is unsupported or drops for
// good (LOG_ES/LOG_POLL are never both set - one is always null).
let LOG_ES = null, LOG_POLL = null;
// Rows measured in manual mode; auto mode reads them back from /api/run/status.
let MANUAL_ROWS = [];
const LIVE_FAILS = { box: "failBox", count: "failCount", list: "failList" };
const REPORT_FAILS = { box: "failReport", count: "failReportCount", list: "failReportList" };

function failItem(columns, row) {
  const div = document.createElement("div"); div.className = "fail-item";
  const head = document.createElement("span"); head.className = "f";
  head.textContent = (row.Frequency_MHz === undefined || row.Frequency_MHz === "")
    ? "point" : row.Frequency_MHz + " MHz";
  div.appendChild(head);
  const rest = columns
    .filter((c) => c !== "Frequency_MHz" && c !== "Result")
    .filter((c) => row[c] !== undefined && row[c] !== "")
    .map((c) => c.replace(/_/g, " ") + " " + row[c]);
  div.appendChild(document.createTextNode("   " + rest.join("   ")));
  return div;
}
// Shows every FAIL point - live while the run goes on, and as the report afterwards.
function renderFails(columns, rows, ids, prefix, live) {
  const box = $(ids.box), list = $(ids.list);
  const fails = (rows || []).filter((r) => r.Result === "FAIL");
  $(ids.count).textContent = prefix + fails.length;
  list.innerHTML = "";
  if (!fails.length) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  fails.forEach((r) => list.appendChild(failItem(columns || [], r)));
  if (live) list.scrollTop = list.scrollHeight;
}

async function loadUnits() {
  const { units } = await getJSON("/api/units");
  const sel = $("unitSel"); sel.innerHTML = "";
  units.forEach((u) => { const o = document.createElement("option"); o.value = u; o.textContent = u; sel.appendChild(o); });
  if (units.length) await loadFreqList(sel.value);
}
async function loadFreqList(unit) {
  const data = await getJSON("/api/freqlist/" + encodeURIComponent(unit));
  const box = $("freqBoxes"); box.innerHTML = "";
  data.freqs.forEach((f) => {
    const lab = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.value = f; cb.checked = true;
    lab.appendChild(cb); lab.appendChild(document.createTextNode(f)); box.appendChild(lab);
  });
}
function toggleFreqUi() {
  const isFlat = $("checkSel").value === "flatness";
  $("freqListWrap").classList.toggle("hidden", isFlat);
  $("flatNote").classList.toggle("hidden", !isFlat);
}
function checkedFreqs() {
  return Array.from($("freqBoxes").querySelectorAll("input:checked")).map((c) => parseFloat(c.value));
}
async function startRun() {
  $("setupErr").textContent = "";
  const check = $("checkSel").value, unit = $("unitSel").value, mode = $("modeSel").value;
  let freqs = [];
  if (check !== "flatness") {
    freqs = checkedFreqs();
    if (!freqs.length) { $("setupErr").textContent = "Select at least one frequency."; return; }
  }
  // U2: the UI switches to "running" state synchronously, before the network call that
  // triggers instrument I/O even fires - status/indicator/log therefore change within
  // the same tick as the click, not after the multi-second connect+setup sequence.
  enterStartingUi(mode === "auto");
  try {
    const info = await postJSON("/api/run/start", { check, unit, mode, freqs, params: {} });
    RUN = info; finishEnteringRunUi(info);
  } catch (e) { exitStartingUi(e.message); }
}
function enterStartingUi(auto) {
  // Locks the Start button immediately - a second click during the connect window (the
  // gap this stage exists to close) hits a disabled button and does nothing; the
  // disabled/dimmed state itself is the "and says so" the U2 acceptance test asks for.
  $("startBtn").disabled = true;
  $("setupPanel").classList.add("hidden");
  $("runPanel").classList.remove("hidden");
  $("resultsPanel").classList.remove("hidden");
  $("runTitle").textContent = "Starting \u2026";
  $("pointReadout").innerHTML = "";
  $("verdictBox").innerHTML = ""; $("filesHint").textContent = "";
  $("logView").textContent = ""; LOG_SEQ = 0;
  MANUAL_ROWS = [];
  renderFails([], [], LIVE_FAILS, "FAIL: ", false);
  renderFails([], [], REPORT_FAILS, "FAILING POINTS: ", false);
  $("cableBox").classList.add("hidden");
  $("resHead").innerHTML = ""; $("resBody").innerHTML = "";
  $("manualBtns").classList.toggle("hidden", auto);
  $("manualInputs").classList.toggle("hidden", auto);
  // Nothing in manual mode is valid to click yet - there is no point loaded, no run
  // confirmed active server-side. Stop is disabled too: a click here would otherwise hit
  // "No run in progress" (session.py sets active=True only once setup finishes).
  ["stopBtn", "measureBtn", "nextBtn", "skipBtn"].forEach((id) => { $(id).disabled = true; });
  $("modeHint").textContent = "Connecting to the analyzer and modulator \u2026";
  $("runErr").textContent = "";
  // Log lines the server writes during connect/setup land in the same live-log
  // buffer the SSE stream (U3/D6) reads from - starting it here, before the start
  // call resolves, is what makes them "appear immediately" (U2).
  startLogStream();
}
function finishEnteringRunUi(info) {
  $("runTitle").textContent = info.title + "  \u2014  " + info.unit;
  const head = $("resHead"); head.innerHTML = "";
  info.columns.forEach((c) => { const th = document.createElement("th"); th.textContent = c; head.appendChild(th); });
  $("stopBtn").disabled = false;
  if (info.mode === "auto") {
    $("modeHint").textContent = "Auto mode: the run proceeds by itself. Watch the log below.";
    renderProgress(0, info.point ? info.point.total : 0);
    startPolling();
  } else {
    buildManualInputs(info); renderPoint(info.point);
    $("measureBtn").disabled = false; $("nextBtn").disabled = true; $("skipBtn").disabled = false;
    $("modeHint").textContent = "Manual mode: read the value(s) on the CXA, type them, Measure.";
  }
}
function exitStartingUi(message) {
  stopPolling(); stopLogStream();
  $("runPanel").classList.add("hidden");
  $("resultsPanel").classList.add("hidden");
  $("setupPanel").classList.remove("hidden");
  $("startBtn").disabled = false;
  $("setupErr").textContent = message;
}
function buildManualInputs(info) {
  const box = $("manualInputs"); box.innerHTML = "";
  info.manual_fields.forEach((f) => {
    const wrap = document.createElement("div"); wrap.className = "field";
    const lab = document.createElement("label"); lab.textContent = f.label;
    const inp = document.createElement("input");
    inp.type = "number"; inp.step = f.step || "0.01"; inp.id = "mf_" + f.name;
    wrap.appendChild(lab); wrap.appendChild(inp); box.appendChild(wrap);
  });
}
function renderProgress(done, total) {
  $("pointReadout").innerHTML =
    '<div><div class="k">Progress</div><div class="v">' + done + " / " + total + "</div></div>";
}
function renderPoint(point) {
  const box = $("pointReadout");
  if (!point) { box.innerHTML = ""; return; }
  let html = '<div><div class="k">Point</div><div class="progress">' +
    (point.index + 1) + " / " + point.total + "</div></div>" +
    '<div><div class="k">Frequency</div><div class="v">' + point.freq_mhz + " MHz</div></div>";
  if (point.set_dbm !== undefined)
    html += '<div><div class="k">Set power</div><div class="v">' + point.set_dbm + " dBm</div></div>";
  box.innerHTML = html;
  document.querySelectorAll("#manualInputs input").forEach((i) => (i.value = ""));
}
function collectManual() {
  const out = {};
  if (RUN && RUN.mode === "manual")
    RUN.manual_fields.forEach((f) => { const el = $("mf_" + f.name); out[f.name] = el ? el.value : ""; });
  return out;
}
function fillTable(columns, rows, flags) {
  const body = $("resBody"); body.innerHTML = "";
  rows.forEach((row, i) => {
    const tr = document.createElement("tr");
    if (flags && flags[i]) tr.classList.add("flag");
    if (row.Result === "FAIL") tr.classList.add("fail");
    columns.forEach((c) => {
      const td = document.createElement("td");
      td.textContent = (row[c] === undefined || row[c] === "") ? "\u2013" : row[c];
      if (c === "Result" && row[c] === "PASS") td.classList.add("pass");
      if (c === "Result" && row[c] === "FAIL") td.classList.add("fail");
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
}
async function measure() {
  $("runErr").textContent = "";
  try {
    const res = await postJSON("/api/run/measure", { manual: collectManual() });
    const tr = document.createElement("tr");
    if (res.flag) tr.classList.add("flag");
    if (res.row.Result === "FAIL") tr.classList.add("fail");
    RUN.columns.forEach((c) => {
      const td = document.createElement("td");
      td.textContent = (res.row[c] === undefined || res.row[c] === "") ? "\u2013" : res.row[c];
      if (c === "Result" && res.row[c] === "PASS") td.classList.add("pass");
      if (c === "Result" && res.row[c] === "FAIL") td.classList.add("fail");
      tr.appendChild(td);
    });
    $("resBody").appendChild(tr);
    const key = (r) => String(r.Frequency_MHz) + "|" + String(r.Set_dBm);
    MANUAL_ROWS = MANUAL_ROWS.filter((r) => key(r) !== key(res.row)).concat([res.row]);
    renderFails(RUN.columns, MANUAL_ROWS, LIVE_FAILS, "FAIL: ", true);
    $("nextBtn").disabled = !res.has_next;
    if (!res.has_next) $("modeHint").textContent = "Last point measured \u2014 press Stop & finish.";
  } catch (e) { $("runErr").textContent = e.message; }
}
async function advance(url) {
  $("runErr").textContent = "";
  try {
    const res = await postJSON(url, {});
    if (res.done) { $("modeHint").textContent = "All points done \u2014 press Stop & finish."; $("nextBtn").disabled = true; }
    else { renderPoint(res.point); $("nextBtn").disabled = true; }
  } catch (e) { $("runErr").textContent = e.message; }
}
async function stopRun() {
  $("runErr").textContent = "";
  try {
    stopPolling(); stopLogStream();
    const res = await postJSON("/api/run/stop", {});
    RUN = null; $("runPanel").classList.add("hidden"); renderResults(res);
  } catch (e) { $("runErr").textContent = e.message; }
}
async function confirmCable() {
  try { await postJSON("/api/run/confirm", {}); $("cableBox").classList.add("hidden"); }
  catch (e) { $("runErr").textContent = e.message; }
}
async function pollOnce() {
  // Status only - the live log is its own independent stream (see below), not
  // tied to this 1 s cadence any more (U3/D6).
  try {
    const s = await getJSON("/api/run/status");
    if (s.idle) return;
    fillTable(s.columns, s.rows, s.flags);
    renderProgress(s.idx, s.total);
    renderFails(s.columns, s.rows, LIVE_FAILS, "FAIL: ", true);
    if (s.paused) { $("cableMsg").textContent = s.pause_msg; $("cableBox").classList.remove("hidden"); }
    else { $("cableBox").classList.add("hidden"); }
    if (s.finished) {
      stopPolling(); stopLogStream(); $("runPanel").classList.add("hidden");
      renderResults({ verdict: s.verdict, summary: s.summary, columns: s.columns,
                      rows: s.rows, flags: s.flags, log_base: s.log_base });
    }
  } catch (e) {}
}
function appendLogLine(text) {
  const view = $("logView");
  view.textContent += (view.textContent ? "\n" : "") + text;
  view.scrollTop = view.scrollHeight;
}
async function pollLogs() {
  // D6's mandated fallback transport - used when EventSource is unsupported or
  // its connection gives up for good. Same ~1 s cadence as before S3.
  try {
    const d = await getJSON("/api/run/logs?since=" + LOG_SEQ);
    if (d.lines && d.lines.length) { LOG_SEQ = d.seq; d.lines.forEach(appendLogLine); }
  } catch (e) {}
}
function startLogStream() {
  stopLogStream();
  if (typeof EventSource === "undefined") { startLogPollFallback(); return; }
  const es = new EventSource("/api/run/logs/stream?since=" + LOG_SEQ);
  es.onmessage = (ev) => {
    LOG_SEQ = Number(ev.lastEventId) || LOG_SEQ;
    appendLogLine(JSON.parse(ev.data));
  };
  // Only fall back once the browser has genuinely given up (CLOSED) - a
  // transient drop leaves it CONNECTING while EventSource's own native
  // reconnect (Last-Event-ID) retries, which should be left alone.
  es.onerror = () => { if (es.readyState === EventSource.CLOSED) { stopLogStream(); startLogPollFallback(); } };
  LOG_ES = es;
}
function startLogPollFallback() {
  stopLogStream();
  pollLogs();
  LOG_POLL = setInterval(pollLogs, 1000);
}
function stopLogStream() {
  if (LOG_ES) { LOG_ES.close(); LOG_ES = null; }
  if (LOG_POLL) { clearInterval(LOG_POLL); LOG_POLL = null; }
}
function startPolling() { stopPolling(); POLL = setInterval(pollOnce, 1000); pollOnce(); }
function stopPolling() { if (POLL) { clearInterval(POLL); POLL = null; } }
function renderResults(res) {
  const head = $("resHead"); head.innerHTML = "";
  res.columns.forEach((c) => { const th = document.createElement("th"); th.textContent = c; head.appendChild(th); });
  fillTable(res.columns, res.rows, res.flags);
  renderFails(res.columns, res.rows, REPORT_FAILS, "FAILING POINTS: ", false);
  const v = res.verdict || "N/A", s = res.summary || {};
  let detail = "";
  if (s.pk_pk_db !== undefined)
    detail = "pk-pk " + s.pk_pk_db + " dB (limit " + s.tolerance_db + " dB), max " + s.max_dbm + " / min " + s.min_dbm + " dBm";
  else if (s.tolerance_db !== undefined)
    detail = "tolerance \u00b1" + s.tolerance_db + " dB over " + (s.steps || "") + " steps";
  else if (s.loft_limit_dbc !== undefined)
    detail = "LOFT \u2264 " + s.loft_limit_dbc + " dBc, Image \u2264 " + s.image_limit_dbc +
             " dBc over " + (s.points || "") + " points";
  else if (s.spur_limit_dbc !== undefined)
    detail = "limit " + s.spur_limit_dbc + " dBc over " + (s.points || "") + " points";
  const box = $("verdictBox");
  box.className = "verdict " + (v === "PASS" ? "pass" : "fail");
  box.innerHTML = "<div>" + v + "</div><div class='detail'>" + detail + "</div>";
  if (res.log_base) $("filesHint").textContent = "Saved to results/: " + res.log_base + ".log / .csv / .json";
}
function newRun() {
  stopPolling(); stopLogStream();
  $("failBox").classList.add("hidden"); $("failReport").classList.add("hidden");
  $("resultsPanel").classList.add("hidden");
  $("setupPanel").classList.remove("hidden");
  $("startBtn").disabled = false;
  $("setupErr").textContent = "";
}
window.addEventListener("DOMContentLoaded", () => {
  $("checkSel").addEventListener("change", toggleFreqUi);
  $("unitSel").addEventListener("change", (e) => loadFreqList(e.target.value));
  $("selAll").addEventListener("click", () => $("freqBoxes").querySelectorAll("input").forEach((c) => (c.checked = true)));
  $("selNone").addEventListener("click", () => $("freqBoxes").querySelectorAll("input").forEach((c) => (c.checked = false)));
  $("startBtn").addEventListener("click", startRun);
  $("measureBtn").addEventListener("click", measure);
  $("nextBtn").addEventListener("click", () => advance("/api/run/next"));
  $("skipBtn").addEventListener("click", () => advance("/api/run/skip"));
  $("stopBtn").addEventListener("click", stopRun);
  $("continueBtn").addEventListener("click", confirmCable);
  $("newRunBtn").addEventListener("click", newRun);
  toggleFreqUi();
  loadUnits().catch((e) => ($("setupErr").textContent = e.message));
});
