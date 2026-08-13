"use strict";

function upgradeControlToV2Shell() {
  const body = document.body;
  const shell = document.querySelector(".app-shell");
  const legacySidebar = document.querySelector(".app-sidebar");
  if (!body || !shell || !legacySidebar) return;

  body.classList.remove("with-sidebar");
  body.classList.add("v2-body");

  if (!document.querySelector('link[href="/sidebar.css"]')) {
    const sidebarStyles = document.createElement("link");
    sidebarStyles.rel = "stylesheet";
    sidebarStyles.href = "/sidebar.css";
    document.head.appendChild(sidebarStyles);
  }

  const legacyTopbar = shell.querySelector(":scope > .topbar");
  const legacyStatus = legacyTopbar ? legacyTopbar.querySelector(".topbar-status") : null;
  if (legacyStatus) legacyStatus.remove();
  if (legacyTopbar) {
    const eyebrow = legacyTopbar.querySelector(".eyebrow");
    if (eyebrow) eyebrow.textContent = "STREFY";
  }

  const topbar = document.createElement("header");
  topbar.className = "v2-topbar";
  topbar.innerHTML = '<div class="v2-system"><span id="controlSystemDot" class="v2-dot neutral"></span><span id="controlSystemText">System —</span></div><div class="v2-time"><strong id="controlClock">--:--</strong><span id="controlDate">--.--.----</span></div>';
  body.insertBefore(topbar, body.firstChild);

  const sidebar = document.createElement("aside");
  sidebar.className = "v2-sidebar";
  sidebar.setAttribute("aria-label", "Główna nawigacja");
  sidebar.innerHTML = `
    <a class="v2-nav" href="/">
      <span class="v2-nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="4" y="4" width="6" height="6" rx="1.2"/><rect x="14" y="4" width="6" height="6" rx="1.2"/><rect x="4" y="14" width="6" height="6" rx="1.2"/><rect x="14" y="14" width="6" height="6" rx="1.2"/></svg></span><span>PULPIT</span>
    </a>
    <a class="v2-nav active" href="/control" aria-current="page">
      <span class="v2-nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3.5 11.2 12 4l8.5 7.2"/><path d="M5.5 10.5V20h13v-9.5"/><path d="M9.5 20v-5.5h5V20"/></svg></span><span>STREFY</span>
    </a>
    <a class="v2-nav disabled" href="#" aria-disabled="true">
      <span class="v2-nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 19V5"/><path d="M4 19h16"/><path d="m7 15 4-4 3 2 5-6"/><circle cx="7" cy="15" r=".7"/><circle cx="11" cy="11" r=".7"/><circle cx="14" cy="13" r=".7"/><circle cx="19" cy="7" r=".7"/></svg></span><span>HISTORIA</span>
    </a>
    <a class="v2-nav disabled" href="#" aria-disabled="true">
      <span class="v2-nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 8.5h18C21 16 18 16 18 9Z"/><path d="M9.5 20h5"/><path d="M10 4.2a2 2 0 0 1 4 0"/></svg></span><span>ALARMY</span>
    </a>
    <a class="v2-nav disabled" href="#" aria-disabled="true">
      <span class="v2-nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.12-1.3l2-1.55-2-3.45-2.45 1a7 7 0 0 0-2.25-1.3L13.8 3h-4l-.38 2.4A7 7 0 0 0 7.17 6.7l-2.45-1-2 3.45 2 1.55A7 7 0 0 0 4.6 12c0 .44.04.88.12 1.3l-2 1.55 2 3.45 2.45-1a7 7 0 0 0 2.25 1.3L9.8 21h4l.38-2.4a7 7 0 0 0 2.25-1.3l2.45 1 2-3.45-2-1.55c.08-.42.12-.86.12-1.3Z"/></svg></span><span>USTAWIENIA</span>
    </a>
    <a class="v2-nav disabled" href="#" aria-disabled="true">
      <span class="v2-nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m14.7 5.3 4-4a5 5 0 0 1-6.4 6.4L6 14l4 4 6.3-6.3a5 5 0 0 1 6.4-6.4l-4 4"/><path d="m5 15-3 3 4 4 3-3"/></svg></span><span>SERWIS</span>
    </a>`;
  legacySidebar.replaceWith(sidebar);

  const main = document.createElement("main");
  main.className = "v2-main";
  shell.parentNode.insertBefore(main, shell);
  main.appendChild(shell);
}

upgradeControlToV2Shell();

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