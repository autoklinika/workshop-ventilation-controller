"use strict";

const POLL_MS = 2000;
const REQUEST_TIMEOUT_MS = 75000;
const ui = {
  connectionChip: document.getElementById("connectionChip"), messageBar: document.getElementById("messageBar"), clock: document.getElementById("clock"),
  sensor1Chip: document.getElementById("sensor1Chip"), sensor2Chip: document.getElementById("sensor2Chip"), aeroChip: document.getElementById("aeroChip"), coreMode: document.getElementById("coreMode"),
  coreHealth: document.getElementById("coreHealth"), sensorBusHealth: document.getElementById("sensorBusHealth"), aeroBusHealth: document.getElementById("aeroBusHealth"), lastRefresh: document.getElementById("lastRefresh"),
  supplyActual: document.getElementById("supplyActual"), extractActual: document.getElementById("extractActual"), supplyToggle: document.getElementById("supplyToggle"), extractToggle: document.getElementById("extractToggle"),
  supplySlider: document.getElementById("supplySlider"), extractSlider: document.getElementById("extractSlider"), supplyPlanned: document.getElementById("supplyPlanned"), extractPlanned: document.getElementById("extractPlanned"),
  applyFansButton: document.getElementById("applyFansButton"), stopFansButton: document.getElementById("stopFansButton"), aeroFan1: document.getElementById("aeroFan1"), aeroFan2: document.getElementById("aeroFan2"),
  aeroSupplyTemp: document.getElementById("aeroSupplyTemp"), aeroExtractTemp: document.getElementById("aeroExtractTemp"), aeroOutdoorTemp: document.getElementById("aeroOutdoorTemp"), aeroHumidity: document.getElementById("aeroHumidity"),
  aeroCommandState: document.getElementById("aeroCommandState"), airingOnButton: document.getElementById("airingOnButton"), airingOffButton: document.getElementById("airingOffButton"),
  speedButtons: Array.from(document.querySelectorAll("[data-aero-speed]")),
};
const sensorFields = {
  zone1: { pm25: document.getElementById("s1Pm25"), pm10: document.getElementById("s1Pm10"), voc: document.getElementById("s1Voc"), nox: document.getElementById("s1Nox"), temp: document.getElementById("s1Temp"), humidity: document.getElementById("s1Humidity") },
  zone2: { pm25: document.getElementById("s2Pm25"), pm10: document.getElementById("s2Pm10"), voc: document.getElementById("s2Voc"), nox: document.getElementById("s2Nox"), temp: document.getElementById("s2Temp"), humidity: document.getElementById("s2Humidity") },
};
let latestState = null;
let publicConfig = { zone1: { name: "Mycie i wygrzewanie ECU", sensor_address: 1 }, zone2: { name: "Pomieszczenie lutowania", sensor_address: 2 } };
let manualDraftDirty = false, supplyEnabled = false, extractEnabled = false, fanCommandPending = false, aeroCommandPending = false;

function setClock() { ui.clock.textContent = new Intl.DateTimeFormat("pl-PL", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date()); }
function setChip(element, text, kind) { element.textContent = text; element.className = `status-chip status-${kind}`; }
function setMessage(text, kind = "neutral") { ui.messageBar.textContent = text; ui.messageBar.className = `message-bar message-${kind}`; }
function formatNumber(value, digits = 1) { return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("pl-PL", { minimumFractionDigits: digits, maximumFractionDigits: digits }) : "—"; }
function nodeByAddress(sensorBus, address) { return sensorBus && Array.isArray(sensorBus.nodes) ? sensorBus.nodes.find((node) => node.slave_address === address) || null : null; }
function renderSensor(slot, address, node, chip) {
  const f = sensorFields[slot], r = node && node.reading ? node.reading : {};
  f.pm25.textContent = formatNumber(r.pm2_5_ug_m3); f.pm10.textContent = formatNumber(r.pm10_0_ug_m3); f.voc.textContent = formatNumber(r.voc_index, 0); f.nox.textContent = formatNumber(r.nox_index, 0); f.temp.textContent = formatNumber(r.temperature_celsius); f.humidity.textContent = formatNumber(r.humidity_percent);
  if (!node) setChip(chip, `Czujnik ${address}: brak`, "bad");
  else if (node.online && node.usable && node.measurement_valid && !node.measurement_stale) setChip(chip, `Czujnik ${address}: OK`, "good");
  else if (node.online) setChip(chip, `Czujnik ${address}: dane niedostępne`, "warn");
  else setChip(chip, `Czujnik ${address}: offline`, "bad");
}
function setToggle(button, enabled, labelOn, labelOff) { button.setAttribute("aria-pressed", enabled ? "true" : "false"); button.textContent = enabled ? labelOn : labelOff; }
function renderFanDraft() {
  ui.supplySlider.disabled = !supplyEnabled || fanCommandPending; ui.extractSlider.disabled = !extractEnabled || fanCommandPending;
  setToggle(ui.supplyToggle, supplyEnabled, "AKTYWNY", "WYŁĄCZONY"); setToggle(ui.extractToggle, extractEnabled, "AKTYWNY", "WYŁĄCZONY");
  ui.supplyPlanned.value = supplyEnabled ? `${Number(ui.supplySlider.value).toFixed(1)} V` : "0.0 V"; ui.extractPlanned.value = extractEnabled ? `${Number(ui.extractSlider.value).toFixed(1)} V` : "0.0 V";
}
function syncDraftFromCore(state) {
  if (manualDraftDirty || fanCommandPending) return;
  const setpoints = state && state.setpoints ? state.setpoints : {}, supply = Number(setpoints.supply_voltage || 0), extract = Number(setpoints.extract_voltage || 0);
  supplyEnabled = supply >= 1; extractEnabled = extract >= 1;
  if (supplyEnabled) ui.supplySlider.value = String(Math.max(1, Math.min(10, supply))); if (extractEnabled) ui.extractSlider.value = String(Math.max(1, Math.min(10, extract))); renderFanDraft();
}
function renderAero(aero) {
  const usable = Boolean(aero && aero.ready && aero.worker_alive && aero.online && aero.usable), busy = Boolean(aero && aero.control_busy);
  if (usable && !busy) setChip(ui.aeroChip, "AERO: gotowy", "good"); else if (usable && busy) setChip(ui.aeroChip, "AERO: wykonuje", "warn"); else setChip(ui.aeroChip, "AERO: niedostępny", "bad");
  const t = aero && aero.telemetry ? aero.telemetry : {};
  ui.aeroFan1.textContent = typeof t.fan_1_percent === "number" ? `${t.fan_1_percent}%` : "—"; ui.aeroFan2.textContent = typeof t.fan_2_percent === "number" ? `${t.fan_2_percent}%` : "—";
  ui.aeroSupplyTemp.textContent = typeof t.supply_temperature_celsius === "number" ? `${formatNumber(t.supply_temperature_celsius)}°C` : "—"; ui.aeroExtractTemp.textContent = typeof t.extract_temperature_celsius === "number" ? `${formatNumber(t.extract_temperature_celsius)}°C` : "—";
  ui.aeroOutdoorTemp.textContent = typeof t.outdoor_temperature_celsius === "number" ? `${formatNumber(t.outdoor_temperature_celsius)}°C` : "—"; ui.aeroHumidity.textContent = typeof t.humidity_percent === "number" ? `${formatNumber(t.humidity_percent)}%` : "—";
  const disabled = !usable || busy || aeroCommandPending; ui.speedButtons.forEach((b) => { b.disabled = disabled; }); ui.airingOnButton.disabled = disabled; ui.airingOffButton.disabled = disabled;
  if (!aeroCommandPending && aero && aero.last_control_result) renderAeroResult(aero.last_control_result, false);
}
function renderAeroResult(result, fromCurrentCommand = true) {
  if (!result || typeof result !== "object") return;
  const kind = result.kind === "speed" ? "bieg" : "przewietrzanie", target = result.kind === "airing" ? (result.target_value === 1 ? "ON" : "OFF") : String(result.target_value), observed = result.observed_power;
  const power = observed && typeof observed.fan_1_percent === "number" ? ` · ${observed.fan_1_percent}% / ${observed.fan_2_percent}%` : "";
  if (result.state === "succeeded" && result.physical_confirmation === true) { ui.aeroCommandState.textContent = `Potwierdzono: ${kind} ${target}${power}`; ui.aeroCommandState.className = "command-state success"; }
  else if (result.error) { ui.aeroCommandState.textContent = `Błąd ${kind} ${target}: ${result.error}`; ui.aeroCommandState.className = "command-state failure"; }
  else if (fromCurrentCommand) { ui.aeroCommandState.textContent = `Stan polecenia ${kind} ${target}: ${result.state || "nieznany"}`; ui.aeroCommandState.className = "command-state pending"; }
}
function renderState(state) {
  latestState = state; setChip(ui.connectionChip, "CM5 · online", "good"); setMessage("Połączenie z ventilation-core działa. Sterowanie pozostaje wyłącznie ręczne.", "good");
  const setpoints = state.setpoints || {}; setChip(ui.coreMode, "CORE: ONLINE", "good"); ui.supplyActual.textContent = `${formatNumber(setpoints.supply_voltage || 0)} V`; ui.extractActual.textContent = `${formatNumber(setpoints.extract_voltage || 0)} V`;
  ui.coreHealth.textContent = state.hardware_ready && state.output_state_known && Array.isArray(state.active_alarms) && state.active_alarms.length === 0 ? "OK" : "UWAGA";
  const sensorBus = state.sensor_bus; renderSensor("zone1", publicConfig.zone1.sensor_address, nodeByAddress(sensorBus, publicConfig.zone1.sensor_address), ui.sensor1Chip); renderSensor("zone2", publicConfig.zone2.sensor_address, nodeByAddress(sensorBus, publicConfig.zone2.sensor_address), ui.sensor2Chip);
  ui.sensorBusHealth.textContent = sensorBus && sensorBus.ready && sensorBus.worker_alive ? "OK" : "NIEDOSTĘPNY";
  const aero = state.aero_bus; renderAero(aero); ui.aeroBusHealth.textContent = aero && aero.ready && aero.worker_alive && aero.online && aero.usable ? "OK" : "NIEDOSTĘPNY";
  syncDraftFromCore(state); ui.lastRefresh.textContent = new Intl.DateTimeFormat("pl-PL", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());
  const fanDisabled = !state.hardware_ready || !state.output_state_known || fanCommandPending;
  ui.applyFansButton.disabled = fanDisabled; ui.stopFansButton.disabled = fanCommandPending; ui.supplyToggle.disabled = fanDisabled; ui.extractToggle.disabled = fanDisabled;
}
async function requestJson(path, options = {}) {
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try { const response = await fetch(path, { cache: "no-store", headers: { "Content-Type": "application/json", ...(options.headers || {}) }, signal: controller.signal, ...options }); const data = await response.json(); if (!response.ok || data.ok !== true) throw new Error(data.error || `HTTP ${response.status}`); return data; }
  finally { clearTimeout(timeout); }
}
async function loadConfig() {
  try { const response = await requestJson("/api/v1/config"); if (response.config && response.config.zone1 && response.config.zone2) { publicConfig = response.config; document.getElementById("zone1Title").textContent = publicConfig.zone1.name; document.getElementById("zone2Title").textContent = publicConfig.zone2.name; } }
  catch (error) { setMessage(`Nie udało się pobrać konfiguracji nazw stref: ${error.message}`, "warn"); }
}
async function pollState() {
  try { const response = await requestJson("/api/v1/state"); renderState(response.state); }
  catch (error) { setChip(ui.connectionChip, "CM5 · brak danych", "bad"); setChip(ui.coreMode, "CORE: BRAK DANYCH", "bad"); setMessage(`Brak aktualnego stanu ventilation-core: ${error.message}`, "bad"); ui.coreHealth.textContent = "BRAK DANYCH"; }
}
function markManualDirty() { manualDraftDirty = true; renderFanDraft(); }
ui.supplyToggle.addEventListener("click", () => { supplyEnabled = !supplyEnabled; markManualDirty(); }); ui.extractToggle.addEventListener("click", () => { extractEnabled = !extractEnabled; markManualDirty(); }); ui.supplySlider.addEventListener("input", markManualDirty); ui.extractSlider.addEventListener("input", markManualDirty);
ui.applyFansButton.addEventListener("click", async () => {
  fanCommandPending = true; renderFanDraft(); ui.applyFansButton.disabled = true; ui.stopFansButton.disabled = true; setMessage("Wysyłam ręczne ustawienie wentylatorów EC…", "warn");
  try { const supply = supplyEnabled ? Number(ui.supplySlider.value) : 0, extract = extractEnabled ? Number(ui.extractSlider.value) : 0; const response = await requestJson("/api/v1/manual/fans", { method: "POST", body: JSON.stringify({ supply_voltage: supply, extract_voltage: extract }) }); manualDraftDirty = false; if (response.state) renderState(response.state); setMessage(`Potwierdzono ręczne ustawienie: nawiew ${supply.toFixed(1)} V, wyciąg ${extract.toFixed(1)} V.`, "good"); }
  catch (error) { setMessage(`Nie wykonano ustawienia wentylatorów: ${error.message}`, "bad"); }
  finally { fanCommandPending = false; renderFanDraft(); await pollState(); }
});
ui.stopFansButton.addEventListener("click", async () => {
  fanCommandPending = true; ui.applyFansButton.disabled = true; ui.stopFansButton.disabled = true; setMessage("Wymuszam bezpieczny STOP wentylatorów EC…", "warn");
  try { const response = await requestJson("/api/v1/manual/stop", { method: "POST", body: "{}" }); manualDraftDirty = false; supplyEnabled = false; extractEnabled = false; if (response.state) renderState(response.state); setMessage("STOP potwierdzony: nawiew 0.0 V, wyciąg 0.0 V.", "good"); }
  catch (error) { setMessage(`Nie udało się potwierdzić STOP: ${error.message}`, "bad"); }
  finally { fanCommandPending = false; renderFanDraft(); await pollState(); }
});
async function executeAero(path, payload, label) {
  if (aeroCommandPending) return; aeroCommandPending = true; renderAero(latestState ? latestState.aero_bus : null); ui.aeroCommandState.textContent = `${label}: wykonywanie i oczekiwanie na fizyczne potwierdzenie…`; ui.aeroCommandState.className = "command-state pending"; setMessage(`${label}: AERO może potrzebować do 60 s na potwierdzenie.`, "warn");
  try { const response = await requestJson(path, { method: "POST", body: JSON.stringify(payload) }); renderAeroResult(response.aero_control, true); setMessage(`${label}: wykonanie potwierdzone przez ventilation-core.`, "good"); }
  catch (error) { ui.aeroCommandState.textContent = `${label}: ${error.message}`; ui.aeroCommandState.className = "command-state failure"; setMessage(`${label}: polecenie nie zostało potwierdzone. ${error.message}`, "bad"); }
  finally { aeroCommandPending = false; await pollState(); }
}
ui.speedButtons.forEach((button) => button.addEventListener("click", () => { const speed = Number(button.dataset.aeroSpeed); executeAero("/api/v1/manual/aero/speed", { speed }, `AERO · bieg ${speed}`); }));
ui.airingOnButton.addEventListener("click", () => executeAero("/api/v1/manual/aero/airing", { enabled: true }, "AERO · przewietrzanie ON")); ui.airingOffButton.addEventListener("click", () => executeAero("/api/v1/manual/aero/airing", { enabled: false }, "AERO · przewietrzanie OFF"));
setClock(); setInterval(setClock, 1000); loadConfig().finally(() => pollState()); setInterval(() => { if (!fanCommandPending && !aeroCommandPending) pollState(); }, POLL_MS);