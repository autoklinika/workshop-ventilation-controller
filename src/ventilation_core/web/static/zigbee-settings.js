"use strict";

(function () {
  const mount = document.getElementById("zigbeeSettingsMount");
  if (!mount) return;

  if (!document.querySelector('link[data-zigbee-settings-css="1"]')) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/zigbee-settings.css";
    link.dataset.zigbeeSettingsCss = "1";
    document.head.appendChild(link);
  }

  mount.innerHTML = `
    <div class="zigbee-settings-layout">
      <aside class="zigbee-settings-menu" aria-label="Sekcje ustawień">
        <span class="zigbee-settings-menu-title">USTAWIENIA</span>
        <div class="zigbee-settings-menu-item active" aria-current="page">
          <span class="zigbee-settings-menu-icon">Z</span>
          <div><strong>Zigbee</strong><small>Koordynator i czujniki</small></div>
        </div>
        <div class="zigbee-settings-readonly">TRYB TYLKO DO ODCZYTU</div>
      </aside>
      <section class="zigbee-settings-content">
        <header class="zigbee-settings-header">
          <div><span class="zigbee-settings-kicker">ZIGBEE</span><h2>Sieć i urządzenia</h2><p>Stan z ventilation-core przez lokalne API. GUI nie łączy się bezpośrednio z MQTT ani Zigbee2MQTT.</p></div>
          <span id="zigbeeSettingsStatus" class="zigbee-status-pill neutral">ŁĄCZENIE…</span>
        </header>
        <section class="zigbee-summary" aria-label="Stan Zigbee">
          <article><span>MQTT</span><strong id="zigbeeSummaryMqtt">—</strong><small id="zigbeeSummaryBroker">—</small></article>
          <article><span>URZĄDZENIA</span><strong id="zigbeeSummaryDevices">—</strong><small>sparowane czujniki w core</small></article>
          <article><span>BŁĘDY PARSOWANIA</span><strong id="zigbeeSummaryErrors">—</strong><small>bieżąca sesja core</small></article>
        </section>
        <div id="zigbeeSettingsError" class="zigbee-settings-error" hidden></div>
        <section>
          <div class="zigbee-section-heading"><div><span>URZĄDZENIA</span><h3>Czujniki temperatury kanałów</h3></div><span id="zigbeeSettingsUpdated">—</span></div>
          <div id="zigbeeDeviceGrid" class="zigbee-device-grid"><div class="zigbee-loading">Oczekiwanie na dane…</div></div>
        </section>
      </section>
    </div>`;

  const byId = (id) => document.getElementById(id);
  const ui = {
    status: byId("zigbeeSettingsStatus"),
    mqtt: byId("zigbeeSummaryMqtt"),
    broker: byId("zigbeeSummaryBroker"),
    devices: byId("zigbeeSummaryDevices"),
    errors: byId("zigbeeSummaryErrors"),
    error: byId("zigbeeSettingsError"),
    updated: byId("zigbeeSettingsUpdated"),
    grid: byId("zigbeeDeviceGrid"),
  };

  function esc(value) {
    return String(value ?? "—")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function finite(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function number(value, digits = 0) {
    return finite(value)
      ? value.toLocaleString("pl-PL", { minimumFractionDigits: digits, maximumFractionDigits: digits })
      : "—";
  }

  function dateTime(value) {
    if (typeof value !== "string" || !value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return new Intl.DateTimeFormat("pl-PL", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit"
    }).format(parsed);
  }

  function roleName(role) {
    if (role === "supply") return "NAWIEW";
    if (role === "extract") return "WYWIEW";
    return String(role || "URZĄDZENIE").toUpperCase();
  }

  function availability(device) {
    if (device.available === true) return { text: "ONLINE", cls: "good" };
    if (device.available === false) return { text: "OFFLINE", cls: "bad" };
    if ((device.messages || 0) > 0) return { text: "TELEMETRIA AKTYWNA", cls: "good" };
    return { text: "BRAK DANYCH", cls: "neutral" };
  }

  function renderDevice(device) {
    const state = availability(device);
    const temp = finite(device.temperature_celsius) ? `${number(device.temperature_celsius, 1)} °C` : "—";
    const battery = finite(device.battery_percent) ? `${number(device.battery_percent)} %` : "—";
    const lqi = Number.isInteger(device.linkquality) ? String(device.linkquality) : "—";
    const availabilityRaw = device.available === true ? "online" : device.available === false ? "offline" : "niepublikowane";
    return `
      <article class="zigbee-device-card">
        <header>
          <div><span class="zigbee-device-role">${esc(roleName(device.role))}</span><h4>${esc(device.friendly_name)}</h4></div>
          <span class="zigbee-device-state ${state.cls}">${esc(state.text)}</span>
        </header>
        <div class="zigbee-device-primary"><span>Temperatura</span><strong>${esc(temp)}</strong></div>
        <dl class="zigbee-device-data">
          <div><dt>Bateria</dt><dd>${esc(battery)}</dd></div>
          <div><dt>Link quality</dt><dd>${esc(lqi)}</dd></div>
          <div><dt>IEEE</dt><dd class="mono">${esc(device.ieee_address)}</dd></div>
          <div><dt>Topic</dt><dd class="mono">${esc(device.topic)}</dd></div>
          <div><dt>Availability</dt><dd>${esc(availabilityRaw)}</dd></div>
          <div><dt>Ostatni pomiar urządzenia</dt><dd>${esc(dateTime(device.last_seen))}</dd></div>
          <div><dt>Odebrano przez core</dt><dd>${esc(dateTime(device.last_message_at))}</dd></div>
          <div><dt>Wiadomości / błędy</dt><dd>${esc(device.messages || 0)} / ${esc(device.parse_errors || 0)}</dd></div>
        </dl>
      </article>`;
  }

  function render(zigbee) {
    const devices = Array.isArray(zigbee.devices) ? zigbee.devices : [];
    const connected = zigbee.connected === true;
    const parseErrors = devices.reduce((sum, device) => sum + (Number.isInteger(device.parse_errors) ? device.parse_errors : 0), 0);

    ui.status.textContent = connected ? "MQTT POŁĄCZONY" : "MQTT ROZŁĄCZONY";
    ui.status.className = `zigbee-status-pill ${connected ? "good" : "bad"}`;
    ui.mqtt.textContent = connected ? "ONLINE" : "OFFLINE";
    ui.broker.textContent = `${zigbee.broker_host || "—"}:${zigbee.broker_port || "—"}`;
    ui.devices.textContent = String(devices.length);
    ui.errors.textContent = String(parseErrors);
    ui.updated.textContent = `Ostatnia wiadomość: ${dateTime(zigbee.last_message_at)}`;
    ui.grid.innerHTML = devices.length ? devices.map(renderDevice).join("") : '<div class="zigbee-loading">Brak urządzeń udostępnionych przez ventilation-core.</div>';
    ui.error.hidden = true;
  }

  async function refresh() {
    if (document.hidden) return;
    try {
      const response = await fetch("/api/v1/zigbee", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok || payload.ok !== true || !payload.zigbee) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      render(payload.zigbee);
    } catch (error) {
      ui.status.textContent = "BRAK API";
      ui.status.className = "zigbee-status-pill bad";
      ui.error.hidden = false;
      ui.error.textContent = `Nie udało się odczytać stanu Zigbee: ${String(error.message || error)}`;
    }
  }

  refresh();
  setInterval(refresh, 3000);
})();
