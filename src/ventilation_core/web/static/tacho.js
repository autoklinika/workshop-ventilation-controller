"use strict";

const TACHO_POLL_MS = 2000;
const tachoUi = {
  supplyCommandPercent: document.getElementById("supplyCommandPercent"),
  extractCommandPercent: document.getElementById("extractCommandPercent"),
  supplyRpm: document.getElementById("supplyRpm"),
  extractRpm: document.getElementById("extractRpm"),
  supplyChip: document.getElementById("supplyTachoChip"),
  extractChip: document.getElementById("extractTachoChip"),
  supplyDetail: document.getElementById("supplyTachoDetail"),
  extractDetail: document.getElementById("extractTachoDetail"),
  health: document.getElementById("tachoHealth"),
  systemDot: document.getElementById("controlSystemDot"),
  systemText: document.getElementById("controlSystemText"),
  clock: document.getElementById("controlClock"),
  date: document.getElementById("controlDate"),
};

function renderControlTopbarClock() {
  const now = new Date();
  tachoUi.clock.textContent = new Intl.DateTimeFormat("pl-PL", { hour: "2-digit", minute: "2-digit" }).format(now);
  tachoUi.date.textContent = new Intl.DateTimeFormat("pl-PL", { day: "2-digit", month: "2-digit", year: "numeric" }).format(now);
}

function controlNodeByAddress(sensorBus, address) {
  return sensorBus && Array.isArray(sensorBus.nodes)
    ? sensorBus.nodes.find((node) => node.slave_address === address) || null
    : null;
}

function controlSensorOk(node) {
  return Boolean(node && node.online === true && node.usable === true && node.measurement_valid === true && node.measurement_stale !== true);
}

function renderControlTopbarState(state) {
  if (!state) {
    tachoUi.systemDot.className = "v2-dot bad";
    tachoUi.systemText.textContent = "Brak danych z CM5";
    return;
  }
  const alarms = Array.isArray(state.active_alarms) ? state.active_alarms : [];
  const config = typeof publicConfig !== "undefined" ? publicConfig : { zone1: { sensor_address: 1 }, zone2: { sensor_address: 2 } };
  const zone1 = controlNodeByAddress(state.sensor_bus, config.zone1.sensor_address);
  const zone2 = controlNodeByAddress(state.sensor_bus, config.zone2.sensor_address);
  const aero = state.aero_bus;
  const tacho = state.tacho;
  const coreOk = state.hardware_ready === true && state.output_state_known === true && alarms.length === 0;
  const sensorsOk = controlSensorOk(zone1) && controlSensorOk(zone2);
  const aeroOk = Boolean(aero && aero.ready === true && aero.worker_alive === true && aero.online === true && aero.usable === true);
  const tachoOk = Boolean(tacho && tacho.ready === true && tacho.worker_alive === true && !tacho.last_error);
  const allOk = coreOk && sensorsOk && aeroOk && tachoOk;
  tachoUi.systemDot.className = `v2-dot ${allOk ? "good" : "warn"}`;
  tachoUi.systemText.textContent = allOk ? "System OK" : "System UWAGA";
}

function tachoFormatNumber(value, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("pl-PL", { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : "—";
}

function tachoSetChip(element, text, kind) {
  element.textContent = text;
  element.className = `status-chip status-${kind}`;
}

function commandPercentFromVoltage(voltage) {
  const numeric = Number(voltage) || 0;
  return `${Math.round(Math.max(0, Math.min(10, numeric)) * 10)}%`;
}

function renderTachoChannel(tacho, channelName, rpmElement, chipElement, detailElement) {
  rpmElement.textContent = "—";
  detailElement.textContent = "";

  if (!tacho) {
    tachoSetChip(chipElement, "TACHO: nieaktywne", "unknown");
    return;
  }

  const channel = tacho[channelName];
  if (!channel) {
    tachoSetChip(chipElement, "TACHO: nie skonfigurowano", "unknown");
    return;
  }

  if (tacho.last_error || tacho.worker_alive !== true) {
    tachoSetChip(chipElement, "TACHO: błąd monitora", "bad");
    detailElement.textContent = tacho.last_error || "Worker monitora TACHO nie działa.";
    return;
  }

  if (tacho.ready !== true) {
    tachoSetChip(chipElement, "TACHO: monitor niegotowy", "warn");
    return;
  }

  if (channel.valid === true) {
    if (typeof channel.rpm === "number" && Number.isFinite(channel.rpm)) {
      rpmElement.textContent = `${tachoFormatNumber(channel.rpm, 0)} RPM`;
    }
    tachoSetChip(chipElement, "TACHO: sygnał OK", "good");
    const frequency = typeof channel.frequency_hz === "number" && Number.isFinite(channel.frequency_hz)
      ? `${tachoFormatNumber(channel.frequency_hz, 1)} Hz`
      : null;
    const line = typeof channel.line_name === "string" && channel.line_name ? channel.line_name : null;
    detailElement.textContent = [frequency, line].filter(Boolean).join(" · ");
    return;
  }

  tachoSetChip(chipElement, "TACHO: brak sygnału", "warn");
  detailElement.textContent = typeof channel.line_name === "string" && channel.line_name
    ? `${channel.line_name} · brak aktualnych impulsów`
    : "Brak aktualnych impulsów";
}

function renderTachoState(state) {
  renderControlTopbarState(state);
  const setpoints = state && state.setpoints ? state.setpoints : {};
  tachoUi.supplyCommandPercent.textContent = commandPercentFromVoltage(setpoints.supply_voltage);
  tachoUi.extractCommandPercent.textContent = commandPercentFromVoltage(setpoints.extract_voltage);

  const tacho = state ? state.tacho : null;
  if (!tacho) tachoUi.health.textContent = "NIEAKTYWNE";
  else if (tacho.last_error || tacho.worker_alive !== true) tachoUi.health.textContent = "BŁĄD";
  else if (tacho.ready !== true) tachoUi.health.textContent = "NIEGOTOWE";
  else tachoUi.health.textContent = "OK";

  renderTachoChannel(tacho, "supply", tachoUi.supplyRpm, tachoUi.supplyChip, tachoUi.supplyDetail);
  renderTachoChannel(tacho, "extract", tachoUi.extractRpm, tachoUi.extractChip, tachoUi.extractDetail);
}

async function pollTachoState() {
  try {
    const response = await fetch("/api/v1/state", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || payload.ok !== true || !payload.state) throw new Error(payload.error || `HTTP ${response.status}`);
    renderTachoState(payload.state);
  } catch (_error) {
    renderControlTopbarState(null);
    tachoUi.health.textContent = "BRAK DANYCH";
    renderTachoChannel(null, "supply", tachoUi.supplyRpm, tachoUi.supplyChip, tachoUi.supplyDetail);
    renderTachoChannel(null, "extract", tachoUi.extractRpm, tachoUi.extractChip, tachoUi.extractDetail);
  }
}

renderControlTopbarClock();
setInterval(renderControlTopbarClock, 1000);
pollTachoState();
setInterval(pollTachoState, TACHO_POLL_MS);
