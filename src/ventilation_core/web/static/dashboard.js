"use strict";

const DASHBOARD_POLL_MS = 2000;
const DASHBOARD_TIMEOUT_MS = 8000;

const dashboardUi = {
  systemChip: document.getElementById("systemChip"),
  clock: document.getElementById("clock"),
  airSummaryChip: document.getElementById("airSummaryChip"),
  airZone1Name: document.getElementById("airZone1Name"),
  airZone1Status: document.getElementById("airZone1Status"),
  airZone1Pm25: document.getElementById("airZone1Pm25"),
  airZone1Voc: document.getElementById("airZone1Voc"),
  airZone1Nox: document.getElementById("airZone1Nox"),
  airZone2Name: document.getElementById("airZone2Name"),
  airZone2Status: document.getElementById("airZone2Status"),
  airZone2Pm25: document.getElementById("airZone2Pm25"),
  airZone2Voc: document.getElementById("airZone2Voc"),
  airZone2Nox: document.getElementById("airZone2Nox"),
  insideTempZone1Label: document.getElementById("insideTempZone1Label"),
  insideTempZone1: document.getElementById("insideTempZone1"),
  insideTempZone2Label: document.getElementById("insideTempZone2Label"),
  insideTempZone2: document.getElementById("insideTempZone2"),
  outsideTemp: document.getElementById("outsideTemp"),
  temperatureSource: document.getElementById("temperatureSource"),
  dashboardMode: document.getElementById("dashboardMode"),
  ecZoneLabel: document.getElementById("ecZoneLabel"),
  aeroZoneLabel: document.getElementById("aeroZoneLabel"),
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

function publishedAirStatus(state, zoneKey) {
  const zone = state && state.air_quality ? state.air_quality[zoneKey] : null;
  const status = zone ? zone.status : null;
  return typeof status === "string" && status.trim() ? status.trim().toUpperCase() : null;
}

function airStatusKind(status) {
  if (status === "DOBRE") return "good";
  if (status === "ZŁE") return "bad";
  if (status) return "warn";
  return "neutral";
}

function renderAirZone(state, zoneKey, config, node, elements) {
  const reading = node && node.reading ? node.reading : {};
  elements.name.textContent = config.name;
  elements.pm25.textContent = formatNumber(reading.pm2_5_ug_m3);
  elements.voc.textContent = formatNumber(reading.voc_index, 0);
  elements.nox.textContent = formatNumber(reading.nox_index, 0);

  if (!node) {
    elements.status.textContent = "BRAK CZUJNIKA";
    elements.status.className = "air-zone-status air-zone-bad";
    return;
  }
  if (!nodeUsable(node)) {
    elements.status.textContent = node.online ? "BRAK DANYCH" : "OFFLINE";
    elements.status.className = `air-zone-status ${node.online ? "air-zone-warn" : "air-zone-bad"}`;
    return;
  }

  const published = publishedAirStatus(state, zoneKey);
  const label = published || "MONITORING";
  elements.status.textContent = label;
  elements.status.className = `air-zone-status air-zone-${airStatusKind(published)}`;
}

function renderAir(state, zone1, zone2) {
  renderAirZone(state, "zone1", dashboardConfig.zone1, zone1, {
    name: dashboardUi.airZone1Name,
    status: dashboardUi.airZone1Status,
    pm25: dashboardUi.airZone1Pm25,
    voc: dashboardUi.airZone1Voc,
    nox: dashboardUi.airZone1Nox,
  });
  renderAirZone(state, "zone2", dashboardConfig.zone2, zone2, {
    name: dashboardUi.airZone2Name,
    status: dashboardUi.airZone2Status,
    pm25: dashboardUi.airZone2Pm25,
    voc: dashboardUi.airZone2Voc,
    nox: dashboardUi.airZone2Nox,
  });

  const usableCount = [zone1, zone2].filter(nodeUsable).length;
  if (usableCount === 2) setChip(dashboardUi.airSummaryChip, "2/2 CZUJNIKI OK", "good");
  else if (usableCount === 1) setChip(dashboardUi.airSummaryChip, "1/2 CZUJNIKI", "warn");
  else setChip(dashboardUi.airSummaryChip, "CZUJNIKI NIEDOSTĘPNE", "bad");
}

function renderTemperature(state, zone1, zone2) {
  const reading1 = zone1 && zone1.reading ? zone1.reading : {};
  const reading2 = zone2 && zone2.reading ? zone2.reading : {};

  dashboardUi.insideTempZone1Label.textContent = dashboardConfig.zone1.name;
  dashboardUi.insideTempZone2Label.textContent = dashboardConfig.zone2.name;
  dashboardUi.insideTempZone1.textContent = typeof reading1.temperature_celsius === "number"
    ? `${formatNumber(reading1.temperature_celsius)}°C`
    : "—";
  dashboardUi.insideTempZone2.textContent = typeof reading2.temperature_celsius === "number"
    ? `${formatNumber(reading2.temperature_celsius)}°C`
    : "—";

  const environment = state && state.environment ? state.environment : {};
  const outdoor = environment.outdoor_temperature_celsius;
  dashboardUi.outsideTemp.textContent = typeof outdoor === "number"
    ? `${formatNumber(outdoor)}°C`
    : "—";

  dashboardUi.temperatureSource.textContent = typeof outdoor === "number"
    ? "Pomieszczenia: SEN55 · na zewnątrz: fizyczny czujnik systemu."
    : "Pomieszczenia: SEN55 · zewnętrzny czujnik: oczekiwanie na integrację.";
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
  dashboardUi.ecZoneLabel.textContent = dashboardConfig.zone1.name;
  dashboardUi.aeroZoneLabel.textContent = dashboardConfig.zone2.name;
  renderAir(state, zone1, zone2);
  renderTemperature(state, zone1, zone2);
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
