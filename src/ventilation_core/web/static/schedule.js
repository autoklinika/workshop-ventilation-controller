"use strict";

const DAYS = [
  [1, "Poniedziałek"], [2, "Wtorek"], [3, "Środa"], [4, "Czwartek"],
  [5, "Piątek"], [6, "Sobota"], [7, "Niedziela"],
];
const ZONES = ["zone-1", "zone-2"];
const MAX_WINDOWS = 64;
const zoneNames = {"zone-1": "Mycie / Wygrzewanie", "zone-2": "Lutowanie"};
let scheduleSnapshot = null;

function el(id) { return document.getElementById(id); }
function zoneSuffix(zone) { return zone === "zone-1" ? "1" : "2"; }
function rowsHost(zone) { return el(`scheduleZone${zoneSuffix(zone)}Rows`); }
function emptyHost(zone) { return el(`scheduleZone${zoneSuffix(zone)}Empty`); }
function messageHost(zone) { return el(`scheduleZone${zoneSuffix(zone)}Message`); }

async function api(path, options = {}) {
  const response = await fetch(path, {cache: "no-store", ...options});
  let payload;
  try { payload = await response.json(); }
  catch (_) { throw new Error(`Nieprawidłowa odpowiedź HTTP ${response.status}`); }
  if (!response.ok || payload.ok !== true) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function expectationText(value) {
  if (value === "OCCUPIED_EXPECTED") return "OBECNOŚĆ OCZEKIWANA";
  if (value === "UNOCCUPIED_EXPECTED") return "BRAK OBECNOŚCI";
  return "NIEZNANY";
}

function renderOverview(schedule) {
  const available = schedule && schedule.available === true;
  el("scheduleAvailability").textContent = available ? "DOSTĘPNY" : "NIEDOSTĘPNY";
  el("scheduleAvailability").className = available ? "good" : "bad";
  el("scheduleTimezone").textContent = schedule && schedule.timezone ? schedule.timezone : "—";
  const state = schedule && schedule.state && typeof schedule.state === "object" ? schedule.state : null;
  el("scheduleLocalTime").textContent = state && state.local_time ? formatLocalDate(state.local_time) : "—";
  el("scheduleEvaluatedAt").textContent = state && state.evaluated_at_utc ? `ocena: ${formatDate(state.evaluated_at_utc)}` : "—";
  const error = schedule && schedule.last_error ? String(schedule.last_error) : "";
  el("scheduleError").textContent = error || (available ? "lokalny store core działa" : "brak szczegółów");

  for (const zone of ZONES) {
    const suffix = zoneSuffix(zone);
    const target = el(`scheduleZone${suffix}State`);
    const current = state && Array.isArray(state.zones) ? state.zones.find(item => item.zone === zone) : null;
    const expectation = current ? current.expectation : "UNKNOWN";
    target.textContent = expectationText(expectation);
    target.className = expectation === "OCCUPIED_EXPECTED" ? "good" : expectation === "UNOCCUPIED_EXPECTED" ? "muted" : "bad";
  }
}

function formatLocalDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("pl-PL", {weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit"}).format(date);
}
function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("pl-PL", {hour: "2-digit", minute: "2-digit", second: "2-digit"}).format(date);
}

function makeSelect(field, options, selected) {
  const select = document.createElement("select");
  select.dataset.field = field;
  for (const [value, text] of options) {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = text;
    if (String(value) === String(selected)) option.selected = true;
    select.appendChild(option);
  }
  return select;
}

function makeInput(field, type, value) {
  const input = document.createElement("input");
  input.dataset.field = field;
  input.type = type;
  input.value = value || "";
  if (field === "label") {
    input.maxLength = 80;
    input.placeholder = "np. Zmiana 1";
  }
  if (type === "time") input.step = "60";
  return input;
}

function addWindowRow(zone, window = {}) {
  const host = rowsHost(zone);
  if (!host || host.children.length >= MAX_WINDOWS) {
    setMessage(zone, `Maksymalnie ${MAX_WINDOWS} przedziałów.`, false);
    return;
  }
  const row = document.createElement("div");
  row.className = "schedule-row";
  row.dataset.scheduleRow = "true";
  row.appendChild(makeSelect("weekday", DAYS, window.weekday || 1));
  row.appendChild(makeInput("start_local", "time", window.start_local || "07:00"));
  row.appendChild(makeInput("end_local", "time", window.end_local || "15:00"));
  row.appendChild(makeSelect("expectation", [
    ["OCCUPIED_EXPECTED", "Obecność oczekiwana"],
    ["UNOCCUPIED_EXPECTED", "Brak obecności"],
  ], window.expectation || "OCCUPIED_EXPECTED"));
  row.appendChild(makeInput("label", "text", window.label || ""));

  const enabledWrap = document.createElement("label");
  enabledWrap.className = "schedule-enabled";
  enabledWrap.title = "Aktywny przedział";
  const enabled = document.createElement("input");
  enabled.type = "checkbox";
  enabled.dataset.field = "enabled";
  enabled.checked = window.enabled !== false;
  enabledWrap.appendChild(enabled);
  row.appendChild(enabledWrap);

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "schedule-delete";
  remove.title = "Usuń przedział";
  remove.setAttribute("aria-label", "Usuń przedział");
  remove.textContent = "×";
  remove.addEventListener("click", () => {
    row.remove();
    refreshEmpty(zone);
    setMessage(zone, "Zmiany niezapisane.");
  });
  row.appendChild(remove);

  host.appendChild(row);
  refreshEmpty(zone);
}

function refreshEmpty(zone) {
  const host = rowsHost(zone);
  const empty = emptyHost(zone);
  if (host && empty) empty.hidden = host.children.length !== 0;
}

function renderZone(zone, schedule) {
  const host = rowsHost(zone);
  if (!host) return;
  host.replaceChildren();
  const windows = schedule && Array.isArray(schedule.windows)
    ? schedule.windows.filter(item => item.zone === zone)
    : [];
  windows.sort((a, b) => Number(a.weekday) - Number(b.weekday) || String(a.start_local).localeCompare(String(b.start_local)));
  for (const window of windows) addWindowRow(zone, window);
  refreshEmpty(zone);
  setMessage(zone, windows.length ? `${windows.length} przedziałów w core.` : "Brak zapisanych przedziałów.");
}

function readZoneWindows(zone) {
  const host = rowsHost(zone);
  const rows = host ? [...host.querySelectorAll("[data-schedule-row]")] : [];
  if (rows.length > MAX_WINDOWS) throw new Error(`Maksymalnie ${MAX_WINDOWS} przedziałów na strefę.`);
  return rows.map((row, index) => {
    const get = field => row.querySelector(`[data-field="${field}"]`);
    const weekday = Number(get("weekday").value);
    const start = get("start_local").value;
    const end = get("end_local").value;
    const expectation = get("expectation").value;
    const label = get("label").value.trim();
    const enabled = get("enabled").checked;
    if (!/^\d{2}:\d{2}$/.test(start) || !/^\d{2}:\d{2}$/.test(end)) throw new Error(`Wiersz ${index + 1}: ustaw prawidłowe godziny.`);
    if (start === end) throw new Error(`Wiersz ${index + 1}: godzina OD i DO nie może być taka sama.`);
    return {weekday, start_local: start, end_local: end, expectation, enabled, label};
  });
}

function setMessage(zone, text, ok = null) {
  const target = messageHost(zone);
  if (!target) return;
  target.textContent = text || "";
  target.className = `schedule-save-status${ok === true ? " good" : ok === false ? " bad" : ""}`;
}

function setZoneBusy(zone, busy) {
  document.querySelectorAll(`[data-save-zone="${zone}"],[data-reload-zone="${zone}"],[data-add-window="${zone}"]`).forEach(button => { button.disabled = busy; });
}

async function saveZone(zone) {
  try {
    setZoneBusy(zone, true);
    setMessage(zone, "Zapisywanie…");
    const windows = readZoneWindows(zone);
    const payload = await api("/api/v1/schedule/zone", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({zone, windows}),
    });
    scheduleSnapshot = payload.schedule;
    renderOverview(scheduleSnapshot);
    for (const name of ZONES) renderZone(name, scheduleSnapshot);
    setMessage(zone, "Zapisano w ventilation-core.", true);
  } catch (error) {
    setMessage(zone, String(error.message || error), false);
  } finally {
    setZoneBusy(zone, false);
  }
}

async function loadSchedule(messageZone = null) {
  try {
    if (messageZone) { setZoneBusy(messageZone, true); setMessage(messageZone, "Wczytywanie…"); }
    const payload = await api("/api/v1/schedule");
    scheduleSnapshot = payload.schedule;
    renderOverview(scheduleSnapshot);
    for (const zone of ZONES) renderZone(zone, scheduleSnapshot);
    if (messageZone) setMessage(messageZone, "Wczytano stan z core.", true);
  } catch (error) {
    renderOverview({available: false, last_error: String(error.message || error)});
    if (messageZone) setMessage(messageZone, String(error.message || error), false);
  } finally {
    if (messageZone) setZoneBusy(messageZone, false);
  }
}

async function loadNames() {
  try {
    const payload = await api("/api/v1/config");
    if (payload.config && payload.config.zone1 && payload.config.zone1.name) zoneNames["zone-1"] = payload.config.zone1.name;
    if (payload.config && payload.config.zone2 && payload.config.zone2.name) zoneNames["zone-2"] = payload.config.zone2.name;
  } catch (_) {}
  el("scheduleZone1Name").textContent = zoneNames["zone-1"];
  el("scheduleZone2Name").textContent = zoneNames["zone-2"];
}

document.addEventListener("click", event => {
  const add = event.target.closest("[data-add-window]");
  if (add) { addWindowRow(add.dataset.addWindow); setMessage(add.dataset.addWindow, "Zmiany niezapisane."); return; }
  const save = event.target.closest("[data-save-zone]");
  if (save) { saveZone(save.dataset.saveZone); return; }
  const reload = event.target.closest("[data-reload-zone]");
  if (reload) loadSchedule(reload.dataset.reloadZone);
});

Promise.all([loadNames(), loadSchedule()]);
