"use strict";

const AUTOMATION_POLL_MS = 2000;
const GROUP_LABELS = {
  fan_outputs: "Charakterystyka wentylatorów EC",
  aero_outputs: "Charakterystyka AERO",
  dynamics: "Dynamika / histereza",
  fan_sensor_fallback: "Fallback SEN55 · wentylatory",
  aero_sensor_fallback: "Fallback SEN55 · AERO",
  tacho_confirmation: "TACHO · czas potwierdzenia",
  tacho_supply_fallback: "TACHO · fallback SUPPLY",
  tacho_extract_fallback: "TACHO · fallback EXTRACT",
  tacho_both_fallback: "TACHO · fallback BOTH",
};

let lastState = null;
let selectedOperatorMode = "AUTO";
let pollBusy = false;

function byId(id) { return document.getElementById(id); }
function text(id, value) {
  const node = byId(id);
  if (node) node.textContent = value == null || value === "" ? "—" : String(value);
}
function yesNo(value) { return value === true ? "TAK" : value === false ? "NIE" : "—"; }
function pct(value) { return Number.isFinite(Number(value)) ? `${Number(value).toFixed(0)}%` : "—"; }
function volts(value) { return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)} V` : "—"; }
function rpm(value) { return Number.isFinite(Number(value)) ? `${Math.round(Number(value))} RPM` : "—"; }
function temp(value) { return Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)} °C` : "—"; }
function metric(value, unit = "") {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}${unit}` : "—";
}

async function automationApi(path, options = {}) {
  const response = await fetch(path, {cache: "no-store", ...options});
  let payload;
  try { payload = await response.json(); }
  catch (_) { throw new Error(`Nieprawidłowa odpowiedź HTTP ${response.status}`); }
  if (!response.ok || payload.ok !== true) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function setConnection(ok, message = "ONLINE") {
  const node = byId("automationConnection");
  if (!node) return;
  node.textContent = message;
  node.className = `automation-connection ${ok ? "good" : "bad"}`;
}

function shadowZone(shadow) {
  const zones = shadow && Array.isArray(shadow.zones) ? shadow.zones : [];
  return zones.find(zone => zone && Object.prototype.hasOwnProperty.call(zone, "tacho_supply_status")) || zones[0] || {};
}

function physicalSetpoints(state) {
  const setpoints = state && state.setpoints && typeof state.setpoints === "object" ? state.setpoints : {};
  return {
    supply: setpoints.supply_voltage ?? setpoints.supply ?? null,
    extract: setpoints.extract_voltage ?? setpoints.extract ?? null,
  };
}

function renderOperator(shadow) {
  const mode = shadow.operator_mode || "—";
  text("automationOperatorMode", mode);
  text("automationOperatorRevision", shadow.operator_intent_revision == null
    ? "volatile intent"
    : `revision ${shadow.operator_intent_revision} · volatile`);
  text("manualCurrentIntent", mode === "MANUAL"
    ? `MANUAL · ${pct(shadow.operator_manual_supply_pct)} / ${pct(shadow.operator_manual_extract_pct)} · AERO ${shadow.operator_manual_aero_speed ?? "—"}`
    : "AUTO");
  text("manualIntentMeta", `revision ${shadow.operator_intent_revision ?? "—"} · persistent=${shadow.operator_intent_persistent === true ? "true" : "false"}`);

  if (mode === "MANUAL") {
    if (Number.isFinite(Number(shadow.operator_manual_supply_pct))) byId("manualSupplyPct").value = String(shadow.operator_manual_supply_pct);
    if (Number.isFinite(Number(shadow.operator_manual_extract_pct))) byId("manualExtractPct").value = String(shadow.operator_manual_extract_pct);
    if (Number.isInteger(shadow.operator_manual_aero_speed)) byId("manualAeroSpeed").value = String(shadow.operator_manual_aero_speed);
  }
  if (selectedOperatorMode !== "MANUAL" || mode === "AUTO") setSelectedOperatorMode(mode === "MANUAL" ? "MANUAL" : "AUTO", false);
}

function renderReadiness(shadow) {
  const readiness = shadow.actuation_readiness && typeof shadow.actuation_readiness === "object"
    ? shadow.actuation_readiness : {};
  text("automationReadiness", readiness.ready === true ? "GOTOWA" : "ZABLOKOWANA");
  text("automationAuthority", `authority: ${readiness.actuation_authorized === true ? "JEST" : "BRAK"}`);
  text("tuningPreconditions", yesNo(readiness.preconditions_satisfied));
  text("tuningAuthority", readiness.actuation_authorized === true ? "JEST" : "BRAK");
  text("tuningReady", readiness.ready === true ? "TAK" : "NIE");

  const host = byId("readinessBlockers");
  if (!host) return;
  host.replaceChildren();
  const blockers = Array.isArray(readiness.blockers) ? readiness.blockers : [];
  if (!blockers.length) {
    const empty = document.createElement("div");
    empty.className = "automation-empty";
    empty.textContent = "Brak raportowanych blockerów preconditions. Authority nadal jest osobnym warunkiem.";
    host.appendChild(empty);
    return;
  }
  for (const blocker of blockers) {
    const row = document.createElement("div");
    row.className = "readiness-blocker";
    row.textContent = String(blocker);
    host.appendChild(row);
  }
}

function renderState(state) {
  lastState = state;
  const shadow = state && state.shadow_automation && typeof state.shadow_automation === "object"
    ? state.shadow_automation : null;
  if (!shadow) {
    setConnection(false, "BRAK SHADOW");
    return;
  }
  const zone = shadowZone(shadow);
  const setpoints = physicalSetpoints(state);

  setConnection(true, "CORE ONLINE");
  renderOperator(shadow);
  renderReadiness(shadow);

  text("automationState", zone.automation_state || "—");
  text("automationShadowStatus", `${shadow.status || "—"} · policy ${shadow.policy_version || "—"}`);
  text("automationCalendarMode", zone.calendar_mode || "—");
  text("automationCalendarContext", `${zone.calendar_phase || "—"} · ${zone.calendar_profile || "brak profilu"}`);
  text("automationAqState", zone.air_quality_level ? `${zone.air_quality_level}${zone.air_quality_driver ? ` · ${zone.air_quality_driver}` : ""}` : "—");
  text("automationThermalState", zone.thermal_band || "—");
  text("shadowSupplyPct", pct(zone.final_supply_pct));
  text("shadowExtractPct", pct(zone.final_extract_pct));
  text("shadowAeroSpeed", zone.proposed_aero_speed == null ? "—" : `bieg ${zone.proposed_aero_speed}`);
  text("automationDecisionReason", zone.control_reason || "—");

  text("physicalSupplyVoltage", volts(setpoints.supply));
  text("physicalExtractVoltage", volts(setpoints.extract));
  text("automationActuationSupported", shadow.actuation_supported === false ? "false" : String(shadow.actuation_supported));

  text("automationPm25", metric(zone.sensor_pm2_5_ug_m3, " µg/m³"));
  text("automationVoc", metric(zone.sensor_voc_index));
  text("automationNox", metric(zone.sensor_nox_index));
  text("automationInsideTemp", temp(zone.inside_temperature_celsius));
  text("automationOutsideTemp", temp(zone.outside_temperature_celsius));
  text("automationDeltaT", temp(zone.temperature_delta_celsius));

  text("tachoConfirmation", Number.isFinite(Number(zone.tacho_failure_confirmation_seconds))
    ? `${Number(zone.tacho_failure_confirmation_seconds).toFixed(1)} s` : "NIEUSTAWIONE");
  text("tachoSupplyStatus", zone.tacho_supply_status || "—");
  text("tachoSupplyRpm", rpm(zone.tacho_supply_rpm));
  text("tachoExtractStatus", zone.tacho_extract_status || "—");
  text("tachoExtractRpm", rpm(zone.tacho_extract_rpm));
  text("tachoFaultPattern", zone.tacho_fault_pattern || "BRAK");
  text("tachoFallbackApplied", yesNo(zone.tacho_fallback_applied));
}

async function refreshState() {
  if (pollBusy) return;
  pollBusy = true;
  try {
    const payload = await automationApi("/api/v1/state");
    renderState(payload.state);
  } catch (error) {
    setConnection(false, "CORE OFFLINE");
    const node = byId("operatorMessage");
    if (node && !node.textContent) node.textContent = String(error.message || error);
  } finally {
    pollBusy = false;
  }
}

function renderTuning(payload) {
  const ledger = payload && payload.tuning_validation ? payload.tuning_validation : {};
  text("tuningProgress", `${ledger.completed ?? "—"} / ${ledger.total ?? "—"}`);
  const host = byId("tuningGroups");
  if (!host) return;
  host.replaceChildren();
  const groups = Array.isArray(ledger.groups) ? ledger.groups : [];
  if (!groups.length) {
    const empty = document.createElement("div");
    empty.className = "automation-empty";
    empty.textContent = "Brak danych ledgeru.";
    host.appendChild(empty);
    return;
  }
  for (const group of groups) {
    const row = document.createElement("div");
    row.className = "tuning-group";
    const name = document.createElement("strong");
    name.textContent = GROUP_LABELS[group.id] || group.id;
    const status = document.createElement("span");
    status.className = `status ${group.satisfied ? "ok" : "pending"}`;
    status.textContent = group.satisfied ? "GOTOWE" : "OCZEKUJE";
    const detail = document.createElement("small");
    detail.textContent = `${group.current_level || "—"} → wymagane ${group.required_level || "—"}`;
    row.append(name, status, detail);
    host.appendChild(row);
  }
}

async function loadTuning() {
  try {
    renderTuning(await automationApi("/api/v1/automation/tuning-validation"));
  } catch (error) {
    text("tuningProgress", "BŁĄD");
    const host = byId("tuningGroups");
    if (host) host.textContent = String(error.message || error);
  }
}

function setSelectedOperatorMode(mode, focus = true) {
  selectedOperatorMode = mode === "MANUAL" ? "MANUAL" : "AUTO";
  byId("operatorAutoBtn")?.classList.toggle("active", selectedOperatorMode === "AUTO");
  byId("operatorManualBtn")?.classList.toggle("active", selectedOperatorMode === "MANUAL");
  const form = byId("operatorManualForm");
  if (form) {
    [...form.querySelectorAll("input,select,button")].forEach(node => {
      node.disabled = selectedOperatorMode !== "MANUAL";
    });
  }
  if (focus && selectedOperatorMode === "MANUAL") byId("manualSupplyPct")?.focus();
}

function operatorMessage(message, ok = null) {
  const node = byId("operatorMessage");
  if (!node) return;
  node.textContent = message || "";
  node.className = `automation-message${ok === true ? " good" : ok === false ? " bad" : ""}`;
}

async function postOperator(intent) {
  operatorMessage("Zapisywanie operator intent…");
  try {
    await automationApi("/api/v1/automation/operator", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(intent),
    });
    operatorMessage(`Zapisano ${intent.mode} SHADOW. Fizyczne wyjścia nie są sterowane przez Control Engine.`, true);
    await refreshState();
  } catch (error) {
    operatorMessage(String(error.message || error), false);
  }
}

function readManualIntent() {
  const supply = Number(byId("manualSupplyPct").value);
  const extract = Number(byId("manualExtractPct").value);
  const aero = Number(byId("manualAeroSpeed").value);
  if (!Number.isFinite(supply) || supply < 0 || supply > 100) throw new Error("Nawiew musi być w zakresie 0..100%.");
  if (!Number.isFinite(extract) || extract < 0 || extract > 100) throw new Error("Wyciąg musi być w zakresie 0..100%.");
  if (!Number.isInteger(aero) || aero < 0 || aero > 3) throw new Error("AERO musi być biegiem 0..3.");
  return {mode: "MANUAL", manual_supply_pct: supply, manual_extract_pct: extract, manual_aero_speed: aero};
}

function selectTab(name) {
  document.querySelectorAll("[data-automation-tab]").forEach(button => {
    button.classList.toggle("active", button.dataset.automationTab === name);
  });
  document.querySelectorAll("[data-automation-panel]").forEach(panel => {
    const active = panel.dataset.automationPanel === name;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
}

document.addEventListener("click", event => {
  const tab = event.target.closest("[data-automation-tab]");
  if (tab) selectTab(tab.dataset.automationTab);
});

byId("operatorAutoBtn")?.addEventListener("click", async () => {
  setSelectedOperatorMode("AUTO", false);
  await postOperator({mode: "AUTO"});
});

byId("operatorManualBtn")?.addEventListener("click", () => {
  setSelectedOperatorMode("MANUAL");
  operatorMessage("Ustaw wartości i zatwierdź MANUAL SHADOW.");
});

byId("operatorManualForm")?.addEventListener("submit", async event => {
  event.preventDefault();
  if (selectedOperatorMode !== "MANUAL") return;
  try { await postOperator(readManualIntent()); }
  catch (error) { operatorMessage(String(error.message || error), false); }
});

setSelectedOperatorMode("AUTO", false);
refreshState();
loadTuning();
setInterval(refreshState, AUTOMATION_POLL_MS);
