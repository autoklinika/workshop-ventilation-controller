"use strict";

const DASHBOARD_POLL_MS = 2000;
const DASHBOARD_TIMEOUT_MS = 8000;

const dashboardUi = {
  systemChip: document.getElementById("systemChip"),
  clock: document.getElementById("clock"),
  airSensorChip: document.getElementById("airSensorChip"),
  airVerdict: document.getElementById("airVerdict"),
  airSource: document.getElementById("airSource"),
  airPm25: document.getElementById("airPm25"),
  airVoc: document.getElementById("airVoc"),
  airNox: document.getElementById("airNox"),
  insideTemp: document.getElementById("insideTemp"),
  outsideTemp: document.getElementById("outsideTemp"),
  temperatureSource: document.getElementById("temperatureSource"),
  dashboardMode: document.getElementById("dashboardMode"),
  ecStatus: document.getElementById("ecStatus"),
  supplyRpm: document.getElementById("dashboardSupplyRpm"),
  extractRpm: document.getElementById("dashboardExtractRpm"),
  supplyStatus: document.getElementById("dashboardSupplyStatus"),
  extractStatus: document.getElementById("dashboardExtractStatus"),
  aeroStatus: document.getElementById("dashboardAeroStatus"),
  aeroSpeed: document.getElementById("dashboardAeroSpeed"),
  aeroFan1: document.getElementById("dashboardAeroFan1"),
  aeroFan2: document.getElementById("dashboardAeroFan2"),
  aeroSupplyTemp: document.getElementById("dashboardAeroSupplyTemp"),
  aeroExtractTemp: document.getElementById("dashboardAeroExtractTemp"),
  attentionCard: document.getElementById("attentionCard"),
  attentionIcon: document.getElementById("attentionIcon"),
  attentionText: document.getElementById("attentionText"),
};

let dashboardConfig = {
  zone1: { name: "Mycie i wygrzewanie ECU", sensor_address: 1 },
  zone2: { name: "Pomieszczenie lutowania", sensor_address: 2 },
};

function setClock() {
  dashboardUi.clock.textContent = new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date());
}

function setChip(element, text, kind) {
  element.textContent = text;
  element.className = `status-chip status-${kind}`;
}

function formatNumber(value, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("pl-PL", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })
    : "—";
}

function nodeByAddress(sensorBus, address) {
  if (!sensorBus || !Array.isArray(sensorBus.nodes)) return null;
  return sensorBus.nodes.find((node) => node.slave_address === address) || null;
}

function nodeUsable(node) {
  return Boolean(
    node &&
      node.online === true &&
      node.usable === true &&
      node.measurement_valid === true &&
      node.measurement_stale !== true
  );
}

function renderAir(state, node) {
  const reading = node && node.reading ? node.reading : {};
  dashboardUi.airPm25.textContent = formatNumber(reading.pm2_5_ug_m3);
  dashboardUi.airVoc.textContent = formatNumber(reading.voc_index, 0);
  dashboardUi.airNox.textContent = formatNumber(reading.nox_index, 0);
  dashboardUi.airSource.textContent = dashboardConfig.zone1.name;

  if (!node) {
    setChip(dashboardUi.airSensorChip, "Czujnik: brak", "bad");
    dashboardUi.airVerdict.textContent = "BRAK DANYCH";
    dashboardUi.airVerdict.className = "hero-value hero-bad";
    return;
  }

  if (!nodeUsable(node)) {
    setChip(
      dashboardUi.airSensorChip,
      node.online ? "Czujnik: dane niedostępne" : "Czujnik: offline",
      node.online ? "warn" : "bad"
    );
    dashboardUi.airVerdict.textContent = "BRAK DANYCH";
    dashboardUi.airVerdict.className = "hero-value hero-warn";
    return;
  }

  setChip(dashboardUi.airSensorChip, "Czujnik: OK", "good");

  const publishedStatus = state && state.air_quality && state.air_quality.zone1
    ? state.air_quality.zone1.status
    : null;
  if (typeof publishedStatus === "string" && publishedStatus.trim()) {
    const normalized = publishedStatus.trim().toUpperCase();
    dashboardUi.airVerdict.textContent = normalized;
    dashboardUi.airVerdict.className = `hero-value ${
      normalized === "DOBRE" ? "hero-good" : normalized === "ZŁE" ? "hero-bad" : "hero-warn"
    }`;
  } else {
    dashboardUi.airVerdict.textContent = "MONITORING";
    dashboardUi.airVerdict.className = "hero-value hero-info";
  }
}

function renderTemperature(state, node) {
  const reading = node && node.reading ? node.reading : {};
  dashboardUi.insideTemp.textContent = typeof reading.temperature_celsius === "number"
    ? `${formatNumber(reading.temperature_celsius)}°C`
    : "—";

  const environment = state && state.environment ? state.environment : {};
  const outdoor = environment.outdoor_temperature_celsius;
  dashboardUi.outsideTemp.textContent = typeof outdoor === "number"
    ? `${formatNumber(outdoor)}°C`
    : "—";

  dashboardUi.temperatureSource.textContent = typeof outdoor === "number"
    ? `Wewnątrz: SEN55 · na zewnątrz: fizyczny czujnik systemu.`
    : "Wewnątrz: SEN55 · zewnętrzny czujnik: oczekiwanie na integrację.";
}

function fanPresentation(setpoint, channel) {
  const rpm = channel && channel.valid === true && typeof channel.rpm === "number"
    ? channel.rpm
    : null;

  if (rpm !== null && rpm > 0) {
    return { rpm: `${formatNumber(rpm, 0)} RPM`, status: "● pracuje", kind: "good" };
  }
  if (Number(setpoint || 0) > 0) {
    return { rpm: "—", status: "⚠ brak feedbacku TACHO", kind: "warn" };
  }
  return { rpm: "—", status: "○ STOP", kind: "neutral" };
}

function renderEcFans(state) {
  const setpoints = state && state.setpoints ? state.setpoints : {};
  const tacho = state ? state.tacho : null;
  const supply = fanPresentation(setpoints.supply_voltage, tacho ? tacho.supply : null);
  const extract = fanPresentation(setpoints.extract_voltage, tacho ? tacho.extract : null);

  dashboardUi.supplyRpm.textContent = supply.rpm;
  dashboardUi.extractRpm.textContent = extract.rpm;
  dashboardUi.supplyStatus.textContent = supply.status;
  dashboardUi.extractStatus.textContent = extract.status;
  dashboardUi.supplyStatus.className = `fan-status fan-status-${supply.kind}`;
  dashboardUi.extractStatus.className = `fan-status fan-status-${extract.kind}`;

  if (supply.kind === "warn" || extract.kind === "warn") {
    dashboardUi.ecStatus.textContent = "feedback niepełny";
    dashboardUi.ecStatus.className = "subsystem-state subsystem-warn";
  } else if (supply.kind === "good" || extract.kind === "good") {
    dashboardUi.ecStatus.textContent = "● pracuje";
    dashboardUi.ecStatus.className = "subsystem-state subsystem-good";
  } else {
    dashboardUi.ecStatus.textContent = "○ STOP";
    dashboardUi.ecStatus.className = "subsystem-state";
  }
}

function lastConfirmedAeroSpeed(aero) {
  const result = aero && aero.last_control_result;
  if (
    result &&
    result.kind === "speed" &&
    result.state === "succeeded" &&
    result.physical_confirmation === true &&
    Number.isInteger(result.target_value)
  ) {
    return String(result.target_value);
  }
  return "—";
}

function renderAero(aero) {
  const usable = Boolean(
    aero && aero.ready === true && aero.worker_alive === true && aero.online === true && aero.usable === true
  );
  const telemetry = aero && aero.telemetry ? aero.telemetry : {};

  dashboardUi.aeroSpeed.textContent = lastConfirmedAeroSpeed(aero);
  dashboardUi.aeroFan1.textContent = typeof telemetry.fan_1_percent === "number"
    ? `${telemetry.fan_1_percent}%`
    : "—";
  dashboardUi.aeroFan2.textContent = typeof telemetry.fan_2_percent === "number"
    ? `${telemetry.fan_2_percent}%`
    : "—";
  dashboardUi.aeroSupplyTemp.textContent = typeof telemetry.supply_temperature_celsius === "number"
    ? `${formatNumber(telemetry.supply_temperature_celsius)}°C`
    : "—";
  dashboardUi.aeroExtractTemp.textContent = typeof telemetry.extract_temperature_celsius === "number"
    ? `${formatNumber(telemetry.extract_temperature_celsius)}°C`
    : "—";

  if (!usable) {
    dashboardUi.aeroStatus.textContent = "⚠ niedostępny";
    dashboardUi.aeroStatus.className = "subsystem-state subsystem-warn";
    return;
  }

  if (aero.control_busy === true) {
    dashboardUi.aeroStatus.textContent = "… zmiana ustawienia";
    dashboardUi.aeroStatus.className = "subsystem-state subsystem-warn";
    return;
  }

  const fan1 = Number(telemetry.fan_1_percent || 0);
  const fan2 = Number(telemetry.fan_2_percent || 0);
  if (fan1 > 0 || fan2 > 0) {
    dashboardUi.aeroStatus.textContent = "● pracuje";
    dashboardUi.aeroStatus.className = "subsystem-state subsystem-good";
  } else {
    dashboardUi.aeroStatus.textContent = "○ STOP";
    dashboardUi.aeroStatus.className = "subsystem-state";
  }
}

function tachoInfrastructureHealthy(tacho) {
  if (!tacho) return false;
  return tacho.ready === true && tacho.worker_alive === true && !tacho.last_error;
}

function renderSystemSummary(state, zone1, zone2) {
  const issues = [];
  const alarms = Array.isArray(state.active_alarms) ? state.active_alarms : [];
  const coreHealthy = state.hardware_ready === true && state.output_state_known === true && alarms.length === 0;

  if (!coreHealthy) issues.push("Core / DAC wymaga uwagi");
  if (!nodeUsable(zone1)) issues.push(`${dashboardConfig.zone1.name}: brak aktualnych danych SEN55`);
  if (!nodeUsable(zone2)) issues.push(`${dashboardConfig.zone2.name}: brak aktualnych danych SEN55`);
  if (!tachoInfrastructureHealthy(state.tacho)) issues.push("Monitor TACHO niedostępny");

  const aero = state.aero_bus;
  const aeroHealthy = Boolean(
    aero && aero.ready === true && aero.worker_alive === true && aero.online === true && aero.usable === true
  );
  if (!aeroHealthy) issues.push("Rekuperator AERO niedostępny");

  if (alarms.length > 0) {
    for (const alarm of alarms) {
      const label = typeof alarm === "string" ? alarm : alarm && (alarm.code || alarm.message);
      if (label) issues.push(`Alarm: ${label}`);
    }
  }

  if (issues.length === 0) {
    setChip(dashboardUi.systemChip, "● SYSTEM OK", "good");
    dashboardUi.attentionCard.className = "attention-card attention-good";
    dashboardUi.attentionIcon.textContent = "●";
    dashboardUi.attentionText.textContent = "BRAK AKTYWNYCH ALARMÓW";
  } else {
    setChip(dashboardUi.systemChip, "⚠ SYSTEM · UWAGA", "warn");
    dashboardUi.attentionCard.className = "attention-card attention-warn";
    dashboardUi.attentionIcon.textContent = "⚠";
    dashboardUi.attentionText.textContent = issues.join(" · ");
  }
}

function renderState(state) {
  const sensorBus = state.sensor_bus;
  const zone1 = nodeByAddress(sensorBus, dashboardConfig.zone1.sensor_address);
  const zone2 = nodeByAddress(sensorBus, dashboardConfig.zone2.sensor_address);

  dashboardUi.dashboardMode.textContent = state.mode || "—";
  renderAir(state, zone1);
  renderTemperature(state, zone1);
  renderEcFans(state);
  renderAero(state.aero_bus);
  renderSystemSummary(state, zone1, zone2);
}

async function requestJson(path) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DASHBOARD_TIMEOUT_MS);
  try {
    const response = await fetch(path, {
      cache: "no-store",
      signal: controller.signal,
    });
    const payload = await response.json();
    if (!response.ok || payload.ok !== true) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    return payload;
  } finally {
    clearTimeout(timeout);
  }
}

async function loadConfig() {
  try {
    const response = await requestJson("/api/v1/config");
    if (response.config && response.config.zone1 && response.config.zone2) {
      dashboardConfig = response.config;
    }
  } catch (_error) {
    // Display mapping has safe local defaults. State polling remains independent.
  }
}

async function pollDashboard() {
  try {
    const response = await requestJson("/api/v1/state");
    renderState(response.state);
  } catch (error) {
    setChip(dashboardUi.systemChip, "● CM5 · BRAK DANYCH", "bad");
    dashboardUi.attentionCard.className = "attention-card attention-bad";
    dashboardUi.attentionIcon.textContent = "●";
    dashboardUi.attentionText.textContent = `Brak aktualnego stanu ventilation-core: ${error.message}`;
  }
}

setClock();
setInterval(setClock, 1000);
loadConfig().finally(() => pollDashboard());
setInterval(pollDashboard, DASHBOARD_POLL_MS);
