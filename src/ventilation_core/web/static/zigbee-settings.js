"use strict";

(function () {
  const mount = document.getElementById("zigbeeSettingsMount");
  if (!mount) return;

  function ensureCss(href, marker) {
    if (document.querySelector(`link[${marker}="1"]`)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.setAttribute(marker, "1");
    document.head.appendChild(link);
  }
  ensureCss("/zigbee-settings.css", "data-zigbee-settings-css");
  ensureCss("/zigbee-stage13.css", "data-zigbee-stage13-css");

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
          <div><span class="zigbee-settings-kicker">ZIGBEE</span><h2>Sieć i urządzenia</h2><p>Stan, telemetria, role i operacje pochodzą wyłącznie z ventilation-core.</p></div>
          <span id="zigbeeSettingsStatus" class="zigbee-status-pill neutral">ŁĄCZENIE…</span>
        </header>
        <section class="zigbee-summary" aria-label="Stan Zigbee">
          <article><span>MQTT</span><strong id="zigbeeSummaryMqtt">—</strong><small id="zigbeeSummaryBroker">—</small></article>
          <article><span>ZIGBEE2MQTT</span><strong id="zigbeeSummaryBridge">—</strong><small id="zigbeeSummaryJoin">parowanie: —</small></article>
          <article><span>URZĄDZENIA</span><strong id="zigbeeSummaryDevices">—</strong><small id="zigbeeSummaryErrors">błędy parsowania: —</small></article>
        </section>
        <section class="zigbee-management-panel">
          <div><span class="zigbee-section-kicker">ZARZĄDZANIE</span><h3>Dodawanie urządzeń</h3><p>Otwórz sieć na 120 sekund, a następnie uruchom tryb parowania na dodawanym urządzeniu. Po interview ventilation-core automatycznie dołączy urządzenie do listy.</p></div>
          <div class="zigbee-management-actions">
            <button id="zigbeePermitJoin" class="zigbee-action primary" type="button">DODAJ URZĄDZENIE · 120 S</button>
            <button id="zigbeeCloseJoin" class="zigbee-action" type="button">ZAMKNIJ PAROWANIE</button>
          </div>
          <div id="zigbeeManagementMessage" class="zigbee-management-message" hidden></div>
        </section>
        <div id="zigbeeSettingsError" class="zigbee-settings-error" hidden></div>
        <section>
          <div class="zigbee-section-heading"><div><span>CZUJNIKI I URZĄDZENIA</span><h3>Urządzenia Zigbee2MQTT</h3></div><span id="zigbeeInventoryUpdated">—</span></div>
          <div id="zigbeeInventoryGrid" class="zigbee-inventory-grid"><div class="zigbee-loading">Oczekiwanie na listę urządzeń…</div></div>
        </section>
      </section>
    </div>

    <div id="zigbeeSystemConfirm" class="zigbee-system-confirm" hidden role="alertdialog" aria-modal="true" aria-labelledby="zigbeeSystemConfirmTitle" aria-describedby="zigbeeSystemConfirmMessage">
      <section class="zigbee-system-confirm-card">
        <span class="zigbee-system-confirm-kicker">CM5 · VENTILATION-CORE</span>
        <h2 id="zigbeeSystemConfirmTitle">POTWIERDZENIE OPERACJI</h2>
        <p id="zigbeeSystemConfirmMessage"></p>
        <p id="zigbeeSystemConfirmDetail" class="zigbee-system-confirm-detail"></p>
        <div class="zigbee-system-confirm-meta"><span id="zigbeeSystemConfirmDevice"></span><span id="zigbeeSystemConfirmExpires"></span></div>
        <div class="zigbee-system-confirm-actions">
          <button id="zigbeeSystemConfirmCancel" class="zigbee-action" type="button">ANULUJ</button>
          <button id="zigbeeSystemConfirmOk" class="zigbee-remove" type="button">POTWIERDŹ USUNIĘCIE</button>
        </div>
        <p id="zigbeeSystemConfirmStatus" class="zigbee-system-confirm-status">Decyzja zostanie wykonana przez ventilation-core na CM5.</p>
      </section>
    </div>

    <div id="zigbeePairingResult" class="zigbee-pairing-modal" hidden role="dialog" aria-modal="true" aria-labelledby="zigbeePairingTitle">
      <section class="zigbee-pairing-card">
        <span class="zigbee-pairing-kicker">CM5 · VENTILATION-CORE</span>
        <h2 id="zigbeePairingTitle">URZĄDZENIE ZIGBEE ROZPOZNANE</h2>
        <div class="zigbee-pairing-device">
          <strong id="zigbeePairingName">—</strong>
          <span id="zigbeePairingModel">—</span>
          <span id="zigbeePairingIeee" class="mono">—</span>
        </div>
        <div class="zigbee-pairing-capabilities">
          <span class="zigbee-pairing-section-label">DOSTĘPNE DANE</span>
          <div id="zigbeePairingCapabilities" class="zigbee-capability-list"></div>
        </div>
        <p id="zigbeePairingNote" class="zigbee-pairing-note">Lista pochodzi z ventilation-core na podstawie danych rozpoznanych przez Zigbee2MQTT.</p>
        <div class="zigbee-pairing-actions"><button id="zigbeePairingOk" class="zigbee-action primary" type="button">OK</button></div>
      </section>
    </div>`;

  const byId = (id) => document.getElementById(id);
  const ui = {
    status: byId("zigbeeSettingsStatus"), mqtt: byId("zigbeeSummaryMqtt"), broker: byId("zigbeeSummaryBroker"),
    bridge: byId("zigbeeSummaryBridge"), join: byId("zigbeeSummaryJoin"), devices: byId("zigbeeSummaryDevices"),
    errors: byId("zigbeeSummaryErrors"), error: byId("zigbeeSettingsError"), inventoryUpdated: byId("zigbeeInventoryUpdated"),
    inventory: byId("zigbeeInventoryGrid"), permit: byId("zigbeePermitJoin"), closeJoin: byId("zigbeeCloseJoin"), managementMessage: byId("zigbeeManagementMessage"),
    confirmOverlay: byId("zigbeeSystemConfirm"), confirmTitle: byId("zigbeeSystemConfirmTitle"), confirmMessage: byId("zigbeeSystemConfirmMessage"),
    confirmDetail: byId("zigbeeSystemConfirmDetail"), confirmDevice: byId("zigbeeSystemConfirmDevice"), confirmExpires: byId("zigbeeSystemConfirmExpires"),
    confirmCancel: byId("zigbeeSystemConfirmCancel"), confirmOk: byId("zigbeeSystemConfirmOk"), confirmStatus: byId("zigbeeSystemConfirmStatus"),
    pairingOverlay: byId("zigbeePairingResult"), pairingName: byId("zigbeePairingName"), pairingModel: byId("zigbeePairingModel"),
    pairingIeee: byId("zigbeePairingIeee"), pairingCapabilities: byId("zigbeePairingCapabilities"), pairingNote: byId("zigbeePairingNote"), pairingOk: byId("zigbeePairingOk"),
  };

  let currentState = null;
  let currentRemovalConfirmation = null;
  let currentPairing = null;
  let managementBusy = false;
  let confirmationBusy = false;
  let pairingBusy = false;

  function esc(value) {
    return String(value ?? "—").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }
  function finite(value) { return typeof value === "number" && Number.isFinite(value); }
  function number(value, digits = 0) { return finite(value) ? value.toLocaleString("pl-PL", { minimumFractionDigits: digits, maximumFractionDigits: digits }) : "—"; }
  function dateTime(value) {
    if (typeof value !== "string" || !value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return new Intl.DateTimeFormat("pl-PL", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(parsed);
  }
  function roleName(role) {
    if (role === "supply") return "NAWIEW";
    if (role === "extract") return "WYWIEW";
    if (role === "other") return "INNE";
    return "BEZ ROLI";
  }
  function availability(device) {
    if (device?.available === true) return { text: "ONLINE", cls: "good" };
    if (device?.available === false) return { text: "OFFLINE", cls: "bad" };
    if ((device?.messages || 0) > 0) return { text: "DANE", cls: "good" };
    return { text: "BRAK DANYCH", cls: "neutral" };
  }
  function capabilityText(capability) {
    const unit = capability && capability.unit ? ` · ${capability.unit}` : "";
    const endpoint = capability && capability.endpoint ? ` · ${capability.endpoint}` : "";
    return `${capability?.label || capability?.name || capability?.property || "Dane"}${unit}${endpoint}`;
  }
  function renderCapabilityList(capabilities) {
    if (!Array.isArray(capabilities) || capabilities.length === 0) return `<span class="zigbee-capability-empty">Brak opisu publikowanych danych.</span>`;
    return capabilities.map((capability) => {
      const property = capability?.property ? `<small>${esc(capability.property)}</small>` : "";
      return `<span class="zigbee-capability"><strong>${esc(capabilityText(capability))}</strong>${property}</span>`;
    }).join("");
  }

  function sensorFor(device, sensorList) {
    return sensorList.find((item) => item.ieee_address === device.ieee_address) || null;
  }
  function reading(label, value, extraClass = "") {
    return `<div class="zigbee-sensor-reading ${extraClass}"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }
  function renderInventoryDevice(device, sensorList) {
    const coordinator = device.is_coordinator === true;
    const model = device.model || device.description || "—";
    const meta = [device.vendor, device.device_type, device.power_source].filter(Boolean).join(" · ") || "—";
    if (coordinator) {
      return `<article class="zigbee-inventory-card coordinator compact-row"><div class="zigbee-inventory-main"><div><span>KOORDYNATOR</span><h4>${esc(device.friendly_name)}</h4><p>${esc(model)}</p></div><span class="zigbee-supported good">CORE</span></div><div class="zigbee-inventory-meta"><span class="mono">${esc(device.ieee_address)}</span><span>${esc(meta)}</span></div></article>`;
    }

    const sensor = sensorFor(device, sensorList);
    const role = sensor?.role || null;
    const state = availability(sensor);
    const temperature = finite(sensor?.temperature_celsius) ? `${number(sensor.temperature_celsius, 1)} °C` : "—";
    const humidity = finite(sensor?.humidity_percent) ? `${number(sensor.humidity_percent, 1)} %` : "—";
    const battery = finite(sensor?.battery_percent) ? `${number(sensor.battery_percent)} %` : "—";
    const voltage = finite(sensor?.voltage_mv) ? `${number(sensor.voltage_mv)} mV` : "—";
    const lqi = Number.isInteger(sensor?.linkquality) ? String(sensor.linkquality) : "—";
    const lastMeasurement = dateTime(sensor?.last_seen || sensor?.last_message_at);
    const readings = `<div class="zigbee-sensor-values">${reading("Temperatura", temperature)}${reading("Wilgotność", humidity)}${reading("Bateria", battery)}${reading("Napięcie", voltage)}${reading("LQI", lqi)}${reading("Status", state.text, state.cls)}${reading("Ostatni pomiar", lastMeasurement, "wide")}</div>`;
    const controls = `<div class="zigbee-device-management"><label>Nazwa<input class="zigbee-rename-input" type="text" maxlength="64" value="${esc(device.friendly_name)}" data-zigbee-name-input="${esc(device.ieee_address)}"></label><button class="zigbee-action" type="button" data-zigbee-rename="${esc(device.ieee_address)}">ZMIEŃ NAZWĘ</button><label>Rola systemowa<select class="zigbee-role-select" data-zigbee-role="${esc(device.ieee_address)}"><option value="" ${role === null ? "selected" : ""}>BEZ ROLI</option><option value="supply" ${role === "supply" ? "selected" : ""}>NAWIEW</option><option value="extract" ${role === "extract" ? "selected" : ""}>WYWIEW</option><option value="other" ${role === "other" ? "selected" : ""}>INNE</option></select></label><button class="zigbee-remove" type="button" data-zigbee-remove="${esc(device.ieee_address)}" data-zigbee-name="${esc(device.friendly_name)}">USUŃ</button></div>`;
    const badge = role ? roleName(role) : device.supported === true ? "OBSŁUGIWANE" : "NIEPOTWIERDZONE";
    return `<article class="zigbee-inventory-card compact-row"><div class="zigbee-inventory-main"><div><span>URZĄDZENIE</span><h4>${esc(device.friendly_name)}</h4><p>${esc(model)}</p></div><span class="zigbee-supported ${device.supported === true ? "good" : "warn"}">${esc(badge)}</span></div><div class="zigbee-inventory-meta"><span class="mono">${esc(device.ieee_address)}</span><span>${esc(meta)}</span></div>${readings}${controls}</article>`;
  }

  function joinText(zigbee) { if (zigbee.permit_join === true) return "parowanie: OTWARTE"; if (zigbee.permit_join === false) return "parowanie: zamknięte"; return "parowanie: —"; }

  function renderPairing(pairing) {
    currentPairing = pairing && typeof pairing === "object" ? pairing : null;
    if (!currentPairing || currentPairing.status !== "successful" || currentPairing.acknowledged === true) {
      ui.pairingOverlay.hidden = true;
      return;
    }
    ui.pairingName.textContent = currentPairing.friendly_name || "Urządzenie Zigbee";
    const identity = [currentPairing.vendor, currentPairing.model].filter(Boolean).join(" · ") || currentPairing.description || "Rozpoznane przez Zigbee2MQTT";
    ui.pairingModel.textContent = identity;
    ui.pairingIeee.textContent = currentPairing.ieee_address || "—";
    ui.pairingCapabilities.innerHTML = renderCapabilityList(currentPairing.capabilities);
    ui.pairingNote.textContent = currentPairing.supported === false
      ? "Urządzenie zakończyło interview, ale Zigbee2MQTT nie ma pełnej definicji tego modelu."
      : "Lista danych pochodzi z ventilation-core na podstawie definicji rozpoznanej przez Zigbee2MQTT.";
    ui.pairingOk.disabled = pairingBusy;
    ui.pairingOk.textContent = pairingBusy ? "ZAPISYWANIE…" : "OK";
    ui.pairingOverlay.hidden = false;
  }

  function render(zigbee) {
    currentState = zigbee;
    const inventory = Array.isArray(zigbee.inventory) ? zigbee.inventory : [];
    const sensorList = Array.isArray(zigbee.sensor_list) ? zigbee.sensor_list : [];
    const connected = zigbee.connected === true;
    const bridgeOnline = zigbee.bridge_online === true;
    const parseErrors = sensorList.reduce((sum, device) => sum + (Number.isInteger(device.parse_errors) ? device.parse_errors : 0), 0);
    ui.status.textContent = connected && bridgeOnline ? "ZIGBEE ONLINE" : connected ? "MQTT ONLINE" : "MQTT ROZŁĄCZONY";
    ui.status.className = `zigbee-status-pill ${connected && bridgeOnline ? "good" : "bad"}`;
    ui.mqtt.textContent = connected ? "ONLINE" : "OFFLINE";
    ui.broker.textContent = `${zigbee.broker_host || "—"}:${zigbee.broker_port || "—"}`;
    ui.bridge.textContent = bridgeOnline ? "ONLINE" : zigbee.bridge_online === false ? "OFFLINE" : "—";
    ui.join.textContent = joinText(zigbee);
    ui.devices.textContent = String(inventory.filter((device) => device.is_coordinator !== true).length);
    ui.errors.textContent = `błędy parsowania: ${parseErrors}`;
    ui.inventoryUpdated.textContent = `Lista: ${dateTime(zigbee.inventory_updated_at)}`;
    ui.inventory.innerHTML = inventory.length ? inventory.map((device) => renderInventoryDevice(device, sensorList)).join("") : '<div class="zigbee-loading">Brak danych bridge/devices.</div>';
    ui.permit.disabled = managementBusy || !connected || !bridgeOnline || zigbee.permit_join === true;
    ui.closeJoin.disabled = managementBusy || !connected || !bridgeOnline || zigbee.permit_join !== true;
    ui.inventory.querySelectorAll("button,select,input").forEach((element) => { element.disabled = managementBusy || !connected || !bridgeOnline; });
    ui.error.hidden = true;
    renderPairing(zigbee.pairing);
  }

  function editingControlActive() {
    const active = document.activeElement;
    return Boolean(active && ui.inventory.contains(active) && active.matches("input[data-zigbee-name-input],select[data-zigbee-role]"));
  }

  function renderRemovalConfirmation(confirmation) {
    currentRemovalConfirmation = confirmation && typeof confirmation === "object" ? confirmation : null;
    if (!currentRemovalConfirmation) { ui.confirmOverlay.hidden = true; return; }
    ui.confirmTitle.textContent = currentRemovalConfirmation.title || "USUNIĘCIE URZĄDZENIA ZIGBEE";
    ui.confirmMessage.textContent = currentRemovalConfirmation.message || "Potwierdź operację.";
    ui.confirmDetail.textContent = currentRemovalConfirmation.detail || "";
    ui.confirmDevice.textContent = `${currentRemovalConfirmation.friendly_name || "urządzenie"} · ${currentRemovalConfirmation.device_id || "—"}`;
    ui.confirmExpires.textContent = `Wygasa: ${dateTime(currentRemovalConfirmation.expires_at)}`;
    const coreError = typeof currentRemovalConfirmation.last_error === "string" ? currentRemovalConfirmation.last_error.trim() : "";
    ui.confirmStatus.textContent = coreError || (confirmationBusy ? "VENTILATION-CORE PRZETWARZA DECYZJĘ…" : "Potwierdzenie pochodzi z ventilation-core na CM5.");
    ui.confirmStatus.classList.toggle("bad", Boolean(coreError));
    ui.confirmCancel.disabled = confirmationBusy;
    ui.confirmOk.disabled = confirmationBusy;
    ui.confirmOverlay.hidden = false;
  }

  async function apiPost(path, body) {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const payload = await response.json();
    if (!response.ok || payload.ok !== true) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }
  function message(text, bad = false) { ui.managementMessage.hidden = false; ui.managementMessage.className = `zigbee-management-message ${bad ? "bad" : "good"}`; ui.managementMessage.textContent = text; }
  async function withBusy(action) { if (managementBusy) return; managementBusy = true; if (currentState) render(currentState); try { await action(); } finally { managementBusy = false; if (currentState) render(currentState); } }
  async function setPermitJoin(seconds) { await withBusy(async () => { try { await apiPost("/api/v1/zigbee/permit-join", { seconds }); message(seconds > 0 ? `Parowanie otwarte na ${seconds} s. Uruchom teraz tryb parowania urządzenia.` : "Parowanie zamknięte."); await refresh(true); } catch (error) { message(`Operacja Zigbee nie powiodła się: ${String(error.message || error)}`, true); } }); }
  async function renameDevice(ieee) { const input = ui.inventory.querySelector(`[data-zigbee-name-input="${CSS.escape(ieee)}"]`); const newName = String(input?.value || "").trim(); await withBusy(async () => { try { await apiPost("/api/v1/zigbee/rename", { device_id: ieee, new_name: newName }); message(`Nazwa urządzenia zmieniona na ${newName}.`); await refresh(true); } catch (error) { message(`Nie udało się zmienić nazwy: ${String(error.message || error)}`, true); } }); }
  async function assignRole(ieee, roleValue) { const role = roleValue || null; await withBusy(async () => { try { await apiPost("/api/v1/zigbee/role", { device_id: ieee, role }); message(role ? `Przypisano rolę ${roleName(role)}.` : "Usunięto rolę urządzenia."); await refresh(true); } catch (error) { message(`Nie udało się zmienić roli: ${String(error.message || error)}`, true); await refresh(true); } }); }
  async function requestRemoveDevice(ieee, name) { await withBusy(async () => { try { const payload = await apiPost("/api/v1/zigbee/remove", { device_id: ieee }); if (payload.confirmation_required !== true || !payload.confirmation) throw new Error("CM5 nie zwrócił żądania potwierdzenia"); renderRemovalConfirmation(payload.confirmation); message(`CM5 oczekuje na potwierdzenie usunięcia: ${name}.`); } catch (error) { message(`Nie udało się utworzyć potwierdzenia w core: ${String(error.message || error)}`, true); } }); }

  async function resolveRemovalConfirmation(confirmed) {
    if (confirmationBusy || !currentRemovalConfirmation) return;
    const confirmation = currentRemovalConfirmation;
    confirmationBusy = true;
    renderRemovalConfirmation(confirmation);
    try {
      await apiPost("/api/v1/zigbee/remove-confirmation", { confirmation_id: confirmation.confirmation_id, confirmed });
      message(confirmed ? `Urządzenie ${confirmation.friendly_name || "Zigbee"} zostało usunięte przez ventilation-core.` : `Anulowano usunięcie urządzenia ${confirmation.friendly_name || "Zigbee"}.`);
      renderRemovalConfirmation(null);
      await refresh(true);
    } catch (error) {
      await pollRemovalConfirmation();
      if (!currentRemovalConfirmation) message(`Nie udało się usunąć urządzenia: ${String(error.message || error)}`, true);
    } finally {
      confirmationBusy = false;
      if (currentRemovalConfirmation) renderRemovalConfirmation(currentRemovalConfirmation);
    }
  }

  async function pollRemovalConfirmation() {
    try {
      const response = await fetch("/api/v1/zigbee/removal-confirmation", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok || payload.ok !== true) throw new Error(payload.error || `HTTP ${response.status}`);
      if (!confirmationBusy) renderRemovalConfirmation(payload.confirmation || null);
      else if (payload.confirmation) currentRemovalConfirmation = payload.confirmation;
    } catch (error) {
      if (currentRemovalConfirmation && !confirmationBusy) ui.confirmStatus.textContent = `Nie można odczytać potwierdzenia z CM5: ${String(error.message || error)}`;
    }
  }

  async function acknowledgePairing() {
    if (pairingBusy || !currentPairing || !currentPairing.ieee_address) return;
    pairingBusy = true;
    renderPairing(currentPairing);
    try { await apiPost("/api/v1/zigbee/pairing/ack", { ieee_address: currentPairing.ieee_address }); await refresh(true); }
    catch (error) { ui.pairingNote.textContent = `Nie udało się zapisać potwierdzenia w CM5: ${String(error.message || error)}`; }
    finally { pairingBusy = false; if (currentState) renderPairing(currentState.pairing); }
  }

  async function refresh(force = false) {
    if (document.hidden && !force) return;
    if (!force && editingControlActive()) return;
    try {
      const response = await fetch("/api/v1/zigbee", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok || payload.ok !== true || !payload.zigbee) throw new Error(payload.error || `HTTP ${response.status}`);
      if (!force && editingControlActive()) { currentState = payload.zigbee; return; }
      render(payload.zigbee);
    } catch (error) {
      ui.status.textContent = "BRAK API"; ui.status.className = "zigbee-status-pill bad"; ui.error.hidden = false;
      ui.error.textContent = `Nie udało się odczytać stanu Zigbee: ${String(error.message || error)}`;
    }
  }

  ui.permit.addEventListener("click", () => setPermitJoin(120));
  ui.closeJoin.addEventListener("click", () => setPermitJoin(0));
  ui.confirmCancel.addEventListener("click", () => resolveRemovalConfirmation(false));
  ui.confirmOk.addEventListener("click", () => resolveRemovalConfirmation(true));
  ui.pairingOk.addEventListener("click", acknowledgePairing);
  ui.inventory.addEventListener("click", (event) => {
    const rename = event.target.closest("button[data-zigbee-rename]");
    if (rename) { renameDevice(rename.dataset.zigbeeRename || ""); return; }
    const remove = event.target.closest("button[data-zigbee-remove]");
    if (remove) requestRemoveDevice(remove.dataset.zigbeeRemove || "", remove.dataset.zigbeeName || "urządzenie");
  });
  ui.inventory.addEventListener("change", (event) => {
    const select = event.target.closest("select[data-zigbee-role]");
    if (select) assignRole(select.dataset.zigbeeRole || "", select.value);
  });
  document.addEventListener("keydown", (event) => {
    if ((!ui.confirmOverlay.hidden || !ui.pairingOverlay.hidden) && event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); }
  });

  refresh();
  pollRemovalConfirmation();
  setInterval(refresh, 3000);
  setInterval(pollRemovalConfirmation, 2000);
})();
