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
  try {
    const info = await postJSON("/api/run/start", { check, unit, mode, freqs, params: {} });
    RUN = info; enterRunUi(info);
  } catch (e) { $("setupErr").textContent = e.message; }
}
function enterRunUi(info) {
  $("setupPanel").classList.add("hidden");
  $("runPanel").classList.remove("hidden");
  $("resultsPanel").classList.remove("hidden");
  $("runTitle").textContent = info.title + "  \u2014  " + info.unit;
  $("verdictBox").innerHTML = ""; $("filesHint").textContent = "";
  $("logView").textContent = ""; LOG_SEQ = 0;
  const head = $("resHead"); head.innerHTML = "";
  info.columns.forEach((c) => { const th = document.createElement("th"); th.textContent = c; head.appendChild(th); });
  $("resBody").innerHTML = "";
  const auto = info.mode === "auto";
  $("manualBtns").classList.toggle("hidden", auto);
  $("manualInputs").classList.toggle("hidden", auto);
  if (auto) {
    $("modeHint").textContent = "Auto mode: the run proceeds by itself. Watch the log below.";
    renderProgress(0, info.point ? info.point.total : 0);
    startPolling();
  } else {
    buildManualInputs(info); renderPoint(info.point);
    $("nextBtn").disabled = true;
    $("modeHint").textContent = "Manual mode: read the value(s) on the CXA, type them, Measure.";
    startLogPolling();
  }
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
    stopPolling();
    const res = await postJSON("/api/run/stop", {});
    RUN = null; $("runPanel").classList.add("hidden"); renderResults(res);
  } catch (e) { $("runErr").textContent = e.message; }
}
async function confirmCable() {
  try { await postJSON("/api/run/confirm", {}); $("cableBox").classList.add("hidden"); }
  catch (e) { $("runErr").textContent = e.message; }
}
async function pollOnce() {
  try {
    const s = await getJSON("/api/run/status");
    if (s.idle) return;
    fillTable(s.columns, s.rows, s.flags);
    renderProgress(s.idx, s.total);
    if (s.paused) { $("cableMsg").textContent = s.pause_msg; $("cableBox").classList.remove("hidden"); }
    else { $("cableBox").classList.add("hidden"); }
    if (s.finished) {
      stopPolling(); $("runPanel").classList.add("hidden");
      renderResults({ verdict: s.verdict, summary: s.summary, columns: s.columns,
                      rows: s.rows, flags: s.flags, log_base: s.log_base });
    }
  } catch (e) {}
  await pollLogs();
}
async function pollLogs() {
  try {
    const d = await getJSON("/api/run/logs?since=" + LOG_SEQ);
    if (d.lines && d.lines.length) {
      LOG_SEQ = d.seq;
      const view = $("logView");
      view.textContent += (view.textContent ? "\n" : "") + d.lines.join("\n");
      view.scrollTop = view.scrollHeight;
    }
  } catch (e) {}
}
function startPolling() { stopPolling(); POLL = setInterval(pollOnce, 1000); pollOnce(); }
function startLogPolling() { stopPolling(); POLL = setInterval(pollLogs, 1000); pollLogs(); }
function stopPolling() { if (POLL) { clearInterval(POLL); POLL = null; } }
function renderResults(res) {
  const head = $("resHead"); head.innerHTML = "";
  res.columns.forEach((c) => { const th = document.createElement("th"); th.textContent = c; head.appendChild(th); });
  fillTable(res.columns, res.rows, res.flags);
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
  stopPolling();
  $("resultsPanel").classList.add("hidden");
  $("setupPanel").classList.remove("hidden");
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
