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

const globalAlertState = {
  acknowledged: new Set(),
  activeKeys: [],
};

function ensureGlobalSystemAlert() {
  let overlay = document.getElementById("globalSystemAlert");
  if (overlay) return overlay;

  overlay = document.createElement("div");
  overlay.id = "globalSystemAlert";
  overlay.className = "v2-system-alert";
  overlay.hidden = true;
  overlay.setAttribute("role", "alertdialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "globalSystemAlertTitle");
  overlay.setAttribute("aria-describedby", "globalSystemAlertDescription");
  overlay.innerHTML = `
    <section class="v2-system-alert-card">
      <div class="v2-system-alert-head">
        <span class="v2-system-alert-icon" aria-hidden="true">!</span>
        <div>
          <span class="v2-system-alert-kicker">ALARM</span>
          <h2 id="globalSystemAlertTitle">BŁĄD SYSTEMU</h2>
        </div>
      </div>
      <p id="globalSystemAlertDescription" class="v2-system-alert-description">Wykryto problem wymagający uwagi operatora.</p>
      <ul id="globalSystemAlertList" class="v2-system-alert-list"></ul>
      <p class="v2-system-alert-note">Okno pozostanie otwarte do momentu potwierdzenia komunikatu.</p>
      <button id="globalSystemAlertOk" class="v2-system-alert-ok" type="button">OK</button>
    </section>`;
  document.body.appendChild(overlay);

  const button = document.getElementById("globalSystemAlertOk");
  button.addEventListener("click", () => {
    globalAlertState.activeKeys.forEach((key) => globalAlertState.acknowledged.add(key));
    overlay.hidden = true;
  });

  document.addEventListener("keydown", (event) => {
    if (!overlay.hidden && event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  });

  return overlay;
}

function globalSystemErrorMessage(base, detail) {
  return typeof detail === "string" && detail.trim() ? `${base} · ${detail.trim()}` : base;
}

function collectGlobalSystemErrors(state, coreUnavailable = false) {
  const errors = [];
  const add = (key, message) => {
    if (!errors.some((item) => item.key === key)) errors.push({ key, message });
  };

  if (coreUnavailable || !state) {
    add("core:unavailable", "Brak komunikacji z ventilation-core.");
    return errors;
  }

  const alarms = Array.isArray(state.active_alarms) ? state.active_alarms : [];
  alarms.forEach((alarm, index) => {
    const code = alarm && alarm.code ? String(alarm.code) : `alarm-${index + 1}`;
    const message = alarm && alarm.message ? String(alarm.message) : `Aktywny alarm: ${code}`;
    const detail = alarm && alarm.last_error ? String(alarm.last_error) : "";
    add(`alarm:${code}`, globalSystemErrorMessage(message, detail));
  });

  if (state.hardware_ready !== true) {
    add("core:hardware", "Sterownik sprzętowy nie jest gotowy do bezpiecznej pracy.");
  }
  if (state.output_state_known !== true) {
    add("core:outputs", "Stan wyjść wentylatorów nie jest potwierdzony.");
  }
  if (state.mode === "FAULT" && alarms.length === 0) {
    add("core:fault", "ventilation-core znajduje się w trybie FAULT.");
  }

  const sensorBus = state.sensor_bus;
  if (!sensorBus) {
    add("sensor-bus:missing", "Brak stanu SENSOR BUS.");
  } else {
    if (sensorBus.worker_alive !== true) {
      add("sensor-bus:worker", "Proces SENSOR BUS nie działa.");
    } else if (sensorBus.ready !== true) {
      add("sensor-bus:ready", "SENSOR BUS nie jest gotowy.");
    }
    if (Array.isArray(sensorBus.nodes)) {
      sensorBus.nodes.forEach((sensor, index) => {
        const address = sensor && sensor.slave_address != null ? sensor.slave_address : index + 1;
        const detail = sensor && sensor.last_error ? String(sensor.last_error) : "";
        if (!sensor || sensor.online !== true || sensor.usable !== true) {
          add(`sensor:${address}`, globalSystemErrorMessage(`Czujnik SEN55 ${address}: brak poprawnej komunikacji.`, detail));
        } else if (sensor.measurement_stale === true || sensor.measurement_valid !== true) {
          add(`sensor:${address}`, `Czujnik SEN55 ${address}: dane pomiarowe są nieaktualne lub nieprawidłowe.`);
        }
      });
    }
  }

  const aero = state.aero_bus;
  if (!aero) {
    add("aero:missing", "Brak stanu AERO BUS.");
  } else if (aero.worker_alive !== true || aero.ready !== true || aero.online !== true || aero.usable !== true) {
    add("aero:unavailable", globalSystemErrorMessage("Rekuperator AERO: brak poprawnej komunikacji.", aero.last_error));
  }

  const tacho = state.tacho;
  if (!tacho) {
    add("tacho:missing", "Monitor TACHO nie jest skonfigurowany.");
  } else if (tacho.worker_alive !== true || tacho.ready !== true || tacho.last_error) {
    add("tacho:monitor", globalSystemErrorMessage("Monitor TACHO nie działa poprawnie.", tacho.last_error));
  } else if (!dualTachoConfigured(tacho)) {
    add("tacho:channels", "Nie są skonfigurowane oba kanały TACHO: SUPPLY i EXTRACT.");
  }

  return errors;
}

function updateGlobalSystemAlert(state, coreUnavailable = false) {
  const overlay = ensureGlobalSystemAlert();
  const errors = collectGlobalSystemErrors(state, coreUnavailable);
  const activeKeySet = new Set(errors.map((item) => item.key));

  [...globalAlertState.acknowledged].forEach((key) => {
    if (!activeKeySet.has(key)) globalAlertState.acknowledged.delete(key);
  });

  globalAlertState.activeKeys = errors.map((item) => item.key);
  const pending = errors.some((item) => !globalAlertState.acknowledged.has(item.key));
  if (!pending) {
    overlay.hidden = true;
    return;
  }

  const list = document.getElementById("globalSystemAlertList");
  list.replaceChildren();
  errors.forEach((item) => {
    const row = document.createElement("li");
    row.textContent = item.message;
    list.appendChild(row);
  });

  const wasHidden = overlay.hidden;
  overlay.hidden = false;
  if (wasHidden) document.getElementById("globalSystemAlertOk").focus({ preventScroll: true });
}

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

function dualTachoConfigured(tacho) {
  return Boolean(tacho && tacho.supply && tacho.extract);
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
  const tachoOk = Boolean(
    tacho &&
    tacho.ready === true &&
    tacho.worker_alive === true &&
    !tacho.last_error &&
    dualTachoConfigured(tacho)
  );
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
  updateGlobalSystemAlert(state);
  renderControlTopbarState(state);
  const setpoints = state && state.setpoints ? state.setpoints : {};
  tachoUi.supplyCommandPercent.textContent = commandPercentFromVoltage(setpoints.supply_voltage);
  tachoUi.extractCommandPercent.textContent = commandPercentFromVoltage(setpoints.extract_voltage);

  const tacho = state ? state.tacho : null;
  if (!tacho) tachoUi.health.textContent = "NIEAKTYWNE";
  else if (tacho.last_error || tacho.worker_alive !== true) tachoUi.health.textContent = "BŁĄD";
  else if (tacho.ready !== true) tachoUi.health.textContent = "NIEGOTOWE";
  else if (!dualTachoConfigured(tacho)) tachoUi.health.textContent = "NIEPEŁNE";
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
    updateGlobalSystemAlert(null, true);
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
