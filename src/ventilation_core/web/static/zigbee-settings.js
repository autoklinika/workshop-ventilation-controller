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
          <div><strong>Zigbee</strong><small>Koordynator i urządzenia</small></div>
        </div>
        <div class="zigbee-settings-readonly">ZARZĄDZANIE PRZEZ VENTILATION-CORE</div>
      </aside>
      <section class="zigbee-settings-content">
        <header class="zigbee-settings-header">
          <div><span class="zigbee-settings-kicker">ZIGBEE</span><h2>Sieć i urządzenia</h2><p>Stan i operacje pochodzą wyłącznie z ventilation-core. GUI nie łączy się bezpośrednio z MQTT ani Zigbee2MQTT.</p></div>
          <span id="zigbeeSettingsStatus" class="zigbee-status-pill neutral">ŁĄCZENIE…</span>
        </header>
        <section class="zigbee-summary" aria-label="Stan Zigbee">
          <article><span>MQTT</span><strong id="zigbeeSummaryMqtt">—</strong><small id="zigbeeSummaryBroker">—</small></article>
          <article><span>ZIGBEE2MQTT</span><strong id="zigbeeSummaryBridge">—</strong><small id="zigbeeSummaryJoin">parowanie: —</small></article>
          <article><span>URZĄDZENIA</span><strong id="zigbeeSummaryDevices">—</strong><small id="zigbeeSummaryErrors">błędy parsowania: —</small></article>
        </section>
        <section class="zigbee-management-panel">
          <div><span class="zigbee-section-kicker">ZARZĄDZANIE</span><h3>Dodawanie urządzeń</h3><p>Otwórz sieć na 120 sekund, a następnie uruchom tryb parowania na dodawanym urządzeniu. Możesz zamknąć parowanie wcześniej.</p></div>
          <div class="zigbee-management-actions">
            <button id="zigbeePermitJoin" class="zigbee-action primary" type="button">DODAJ URZĄDZENIE · 120 S</button>
            <button id="zigbeeCloseJoin" class="zigbee-action" type="button">ZAMKNIJ PAROWANIE</button>
          </div>
          <div id="zigbeeManagementMessage" class="zigbee-management-message" hidden></div>
        </section>
        <div id="zigbeeSettingsError" class="zigbee-settings-error" hidden></div>
        <section>
          <div class="zigbee-section-heading"><div><span>ROLE SYSTEMOWE</span><h3>Czujniki temperatury kanałów</h3></div><span id="zigbeeSettingsUpdated">—</span></div>
          <div id="zigbeeDeviceGrid" class="zigbee-device-grid"><div class="zigbee-loading">Oczekiwanie na dane…</div></div>
        </section>
        <section>
          <div class="zigbee-section-heading"><div><span>INWENTARZ SIECI</span><h3>Urządzenia Zigbee2MQTT</h3></div><span id="zigbeeInventoryUpdated">—</span></div>
          <div id="zigbeeInventoryGrid" class="zigbee-inventory-grid"><div class="zigbee-loading">Oczekiwanie na listę urządzeń…</div></div>
        </section>
      </section>
    </div>`;

  const byId = (id) => document.getElementById(id);
  const ui = {
    status: byId("zigbeeSettingsStatus"),
    mqtt: byId("zigbeeSummaryMqtt"),
    broker: byId("zigbeeSummaryBroker"),
    bridge: byId("zigbeeSummaryBridge"),
    join: byId("zigbeeSummaryJoin"),
    devices: byId("zigbeeSummaryDevices"),
    errors: byId("zigbeeSummaryErrors"),
    error: byId("zigbeeSettingsError"),
    updated: byId("zigbeeSettingsUpdated"),
    inventoryUpdated: byId("zigbeeInventoryUpdated"),
    grid: byId("zigbeeDeviceGrid"),
    inventory: byId("zigbeeInventoryGrid"),
    permit: byId("zigbeePermitJoin"),
    closeJoin: byId("zigbeeCloseJoin"),
    managementMessage: byId("zigbeeManagementMessage"),
  };
  let currentState = null;
  let managementBusy = false;

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

  function renderInventoryDevice(device) {
    const coordinator = device.is_coordinator === true;
    const model = device.model || device.description || "—";
    const meta = [device.vendor, device.device_type, device.power_source].filter(Boolean).join(" · ") || "—";
    return `
      <article class="zigbee-inventory-card ${coordinator ? "coordinator" : ""}">
        <div class="zigbee-inventory-main">
          <div><span>${coordinator ? "KOORDYNATOR" : "URZĄDZENIE"}</span><h4>${esc(device.friendly_name)}</h4><p>${esc(model)}</p></div>
          <span class="zigbee-supported ${device.supported === true || coordinator ? "good" : "warn"}">${coordinator ? "CORE" : device.supported === true ? "OBSŁUGIWANE" : "NIEPOTWIERDZONE"}</span>
        </div>
        <div class="zigbee-inventory-meta"><span class="mono">${esc(device.ieee_address)}</span><span>${esc(meta)}</span></div>
        ${coordinator ? "" : `<button class="zigbee-remove" type="button" data-zigbee-remove="${esc(device.ieee_address)}" data-zigbee-name="${esc(device.friendly_name)}">USUŃ</button>`}
      </article>`;
  }

  function joinText(zigbee) {
    if (zigbee.permit_join === true) return "parowanie: OTWARTE";
    if (zigbee.permit_join === false) return "parowanie: zamknięte";
    return "parowanie: —";
  }

  function render(zigbee) {
    currentState = zigbee;
    const devices = Array.isArray(zigbee.devices) ? zigbee.devices : [];
    const inventory = Array.isArray(zigbee.inventory) ? zigbee.inventory : [];
    const connected = zigbee.connected === true;
    const bridgeOnline = zigbee.bridge_online === true;
    const parseErrors = devices.reduce((sum, device) => sum + (Number.isInteger(device.parse_errors) ? device.parse_errors : 0), 0);

    ui.status.textContent = connected && bridgeOnline ? "ZIGBEE ONLINE" : connected ? "MQTT ONLINE" : "MQTT ROZŁĄCZONY";
    ui.status.className = `zigbee-status-pill ${connected && bridgeOnline ? "good" : "bad"}`;
    ui.mqtt.textContent = connected ? "ONLINE" : "OFFLINE";
    ui.broker.textContent = `${zigbee.broker_host || "—"}:${zigbee.broker_port || "—"}`;
    ui.bridge.textContent = bridgeOnline ? "ONLINE" : zigbee.bridge_online === false ? "OFFLINE" : "—";
    ui.join.textContent = joinText(zigbee);
    ui.devices.textContent = String(Math.max(0, inventory.filter((device) => device.is_coordinator !== true).length || devices.length));
    ui.errors.textContent = `błędy parsowania: ${parseErrors}`;
    ui.updated.textContent = `Ostatnia wiadomość: ${dateTime(zigbee.last_message_at)}`;
    ui.inventoryUpdated.textContent = `Lista: ${dateTime(zigbee.inventory_updated_at)}`;
    ui.grid.innerHTML = devices.length ? devices.map(renderDevice).join("") : '<div class="zigbee-loading">Brak ról urządzeń udostępnionych przez ventilation-core.</div>';
    ui.inventory.innerHTML = inventory.length ? inventory.map(renderInventoryDevice).join("") : '<div class="zigbee-loading">Brak danych bridge/devices.</div>';
    ui.permit.disabled = managementBusy || !connected || !bridgeOnline || zigbee.permit_join === true;
    ui.closeJoin.disabled = managementBusy || !connected || !bridgeOnline || zigbee.permit_join !== true;
    ui.error.hidden = true;
  }

  async function apiPost(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok || payload.ok !== true) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  function message(text, bad = false) {
    ui.managementMessage.hidden = false;
    ui.managementMessage.className = `zigbee-management-message ${bad ? "bad" : "good"}`;
    ui.managementMessage.textContent = text;
  }

  async function setPermitJoin(seconds) {
    if (managementBusy) return;
    managementBusy = true;
    if (currentState) render(currentState);
    try {
      await apiPost("/api/v1/zigbee/permit-join", { seconds });
      message(seconds > 0 ? `Parowanie otwarte na ${seconds} s. Uruchom teraz tryb parowania urządzenia.` : "Parowanie zamknięte.");
      await refresh(true);
    } catch (error) {
      message(`Operacja Zigbee nie powiodła się: ${String(error.message || error)}`, true);
    } finally {
      managementBusy = false;
      if (currentState) render(currentState);
    }
  }

  async function removeDevice(ieee, name) {
    if (managementBusy) return;
    const accepted = window.confirm(`Usunąć urządzenie Zigbee „${name}” (${ieee})?\n\nUrządzenie będzie musiało zostać ponownie sparowane, aby wrócić do sieci.`);
    if (!accepted) return;
    managementBusy = true;
    if (currentState) render(currentState);
    try {
      await apiPost("/api/v1/zigbee/remove", { device_id: ieee });
      message(`Wysłano polecenie usunięcia: ${name}.`);
      await refresh(true);
    } catch (error) {
      message(`Nie udało się usunąć urządzenia: ${String(error.message || error)}`, true);
    } finally {
      managementBusy = false;
      if (currentState) render(currentState);
    }
  }

  async function refresh(force = false) {
    if (document.hidden && !force) return;
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

  ui.permit.addEventListener("click", () => setPermitJoin(120));
  ui.closeJoin.addEventListener("click", () => setPermitJoin(0));
  ui.inventory.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-zigbee-remove]");
    if (!button) return;
    removeDevice(button.dataset.zigbeeRemove || "", button.dataset.zigbeeName || "urządzenie");
  });

  refresh();
  setInterval(refresh, 3000);
})();
