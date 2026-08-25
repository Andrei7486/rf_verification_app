"use strict";
const $ = (id) => document.getElementById(id);
const SECTION_TITLES = {
  analyzer: "Analyzer (CXA)", modulator: "Modulator (DUT)", flatness: "Flatness",
  power_accuracy: "Power accuracy", iq_validation: "IQ validation", general: "General",
};
const ENUMS = {
  "modulator.dut_conn_type": ["telnet", "serial"],
  "general.verification_mode": ["auto", "manual"],
  "iq_validation.main_cw_low_action": ["fail", "abort"],
  "iq_validation.peak_frequency_mismatch_action": ["warning", "fail"],
};
let CONFIG = null;
async function getJSON(url) { const r = await fetch(url); const d = await r.json(); if (!r.ok) throw new Error(d.error || ("HTTP " + r.status)); return d; }
async function postJSON(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json(); if (!r.ok) throw new Error(d.error || ("HTTP " + r.status)); return d;
}
function makeInput(section, key, value) {
  const enumKey = section + "." + key;
  if (ENUMS[enumKey]) {
    const sel = document.createElement("select");
    ENUMS[enumKey].forEach((opt) => {
      const o = document.createElement("option");
      o.value = opt; o.textContent = opt; if (String(value) === opt) o.selected = true; sel.appendChild(o);
    });
    sel.dataset.section = section; sel.dataset.key = key; sel.dataset.kind = "string"; return sel;
  }
  if (typeof value === "boolean") {
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = value;
    cb.dataset.section = section; cb.dataset.key = key; cb.dataset.kind = "bool"; return cb;
  }
  const inp = document.createElement("input");
  if (typeof value === "number") { inp.type = "number"; inp.step = "any"; inp.dataset.kind = "number"; }
  else { inp.type = "text"; inp.dataset.kind = "string"; }
  inp.value = value; inp.dataset.section = section; inp.dataset.key = key; return inp;
}
function renderConfig(cfg) {
  const host = $("cfgGroups"); host.innerHTML = "";
  Object.keys(SECTION_TITLES).forEach((section, si) => {
    if (!cfg[section]) return;
    const det = document.createElement("details"); det.className = "group"; if (si === 0) det.open = true;
    const sum = document.createElement("summary"); sum.textContent = SECTION_TITLES[section]; det.appendChild(sum);
    const kv = document.createElement("div"); kv.className = "kv";
    Object.keys(cfg[section]).forEach((key) => {
      const lab = document.createElement("label"); lab.textContent = key; kv.appendChild(lab);
      kv.appendChild(makeInput(section, key, cfg[section][key]));
    });
    det.appendChild(kv); host.appendChild(det);
  });
}
function collectConfig() {
  document.querySelectorAll("#cfgGroups [data-section]").forEach((el) => {
    const s = el.dataset.section, k = el.dataset.key, kind = el.dataset.kind;
    if (kind === "bool") CONFIG[s][k] = el.checked;
    else if (kind === "number") CONFIG[s][k] = el.value === "" ? 0 : Number(el.value);
    else CONFIG[s][k] = el.value;
  });
  return CONFIG;
}
async function saveConfig() {
  $("cfgMsg").textContent = "";
  try { await postJSON("/api/config", collectConfig()); $("cfgMsg").style.color = "var(--pass)"; $("cfgMsg").textContent = "Saved."; }
  catch (e) { $("cfgMsg").style.color = "var(--fail)"; $("cfgMsg").textContent = e.message; }
}
async function loadUnits() {
  const { units } = await getJSON("/api/units");
  const sel = $("unitSel"); sel.innerHTML = "";
  units.forEach((u) => { const o = document.createElement("option"); o.value = u; o.textContent = u; sel.appendChild(o); });
  if (units.length) await loadFreq(sel.value);
}
async function loadFreq(unit) { const data = await getJSON("/api/freqlist/" + encodeURIComponent(unit)); $("freqText").value = data.text || ""; }
async function saveFreq() {
  $("freqMsg").textContent = "";
  try { await postJSON("/api/freqlist/" + encodeURIComponent($("unitSel").value), { text: $("freqText").value }); $("freqMsg").style.color = "var(--pass)"; $("freqMsg").textContent = "Saved."; }
  catch (e) { $("freqMsg").style.color = "var(--fail)"; $("freqMsg").textContent = e.message; }
}
window.addEventListener("DOMContentLoaded", async () => {
  try { CONFIG = await getJSON("/api/config"); renderConfig(CONFIG); await loadUnits(); }
  catch (e) { $("cfgMsg").textContent = e.message; }
  $("saveCfg").addEventListener("click", saveConfig);
  $("unitSel").addEventListener("change", (e) => loadFreq(e.target.value));
  $("saveFreq").addEventListener("click", saveFreq);
});
