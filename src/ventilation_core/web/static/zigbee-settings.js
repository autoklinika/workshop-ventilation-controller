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
          <div><span class="zigbee-settings-kicker">ZIGBEE</span><h2>Sieć i urządzenia</h2><p>Stan i operacje pochodzą wyłącznie z ventilation-core. Role NAWIEW/WYWIEW są zapisywane trwale w core.</p></div>
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
    </div>`;

  const byId = (id) => document.getElementById(id);
  const ui = {
    status: byId("zigbeeSettingsStatus"), mqtt: byId("zigbeeSummaryMqtt"), broker: byId("zigbeeSummaryBroker"),
    bridge: byId("zigbeeSummaryBridge"), join: byId("zigbeeSummaryJoin"), devices: byId("zigbeeSummaryDevices"),
    errors: byId("zigbeeSummaryErrors"), error: byId("zigbeeSettingsError"), updated: byId("zigbeeSettingsUpdated"),
    inventoryUpdated: byId("zigbeeInventoryUpdated"), grid: byId("zigbeeDeviceGrid"), inventory: byId("zigbeeInventoryGrid"),
    permit: byId("zigbeePermitJoin"), closeJoin: byId("zigbeeCloseJoin"), managementMessage: byId("zigbeeManagementMessage"),
    confirmOverlay: byId("zigbeeSystemConfirm"), confirmTitle: byId("zigbeeSystemConfirmTitle"),
    confirmMessage: byId("zigbeeSystemConfirmMessage"), confirmDetail: byId("zigbeeSystemConfirmDetail"),
    confirmDevice: byId("zigbeeSystemConfirmDevice"), confirmExpires: byId("zigbeeSystemConfirmExpires"),
    confirmCancel: byId("zigbeeSystemConfirmCancel"), confirmOk: byId("zigbeeSystemConfirmOk"),
    confirmStatus: byId("zigbeeSystemConfirmStatus"),
  };
  let currentState = null;
  let currentRemovalConfirmation = null;
  let managementBusy = false;
  let confirmationBusy = false;

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
  function roleName(role) { if (role === "supply") return "NAWIEW"; if (role === "extract") return "WYWIEW"; return "BEZ ROLI"; }
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
    return `<article class="zigbee-device-card"><header><div><span class="zigbee-device-role">${esc(roleName(device.role))}</span><h4>${esc(device.friendly_name)}</h4></div><span class="zigbee-device-state ${state.cls}">${esc(state.text)}</span></header><div class="zigbee-device-primary"><span>Temperatura</span><strong>${esc(temp)}</strong></div><dl class="zigbee-device-data"><div><dt>Bateria</dt><dd>${esc(battery)}</dd></div><div><dt>Link quality</dt><dd>${esc(lqi)}</dd></div><div><dt>IEEE</dt><dd class="mono">${esc(device.ieee_address)}</dd></div><div><dt>Topic</dt><dd class="mono">${esc(device.topic)}</dd></div><div><dt>Availability</dt><dd>${esc(availabilityRaw)}</dd></div><div><dt>Ostatni pomiar urządzenia</dt><dd>${esc(dateTime(device.last_seen))}</dd></div><div><dt>Odebrano przez core</dt><dd>${esc(dateTime(device.last_message_at))}</dd></div><div><dt>Wiadomości / błędy</dt><dd>${esc(device.messages || 0)} / ${esc(device.parse_errors || 0)}</dd></div></dl></article>`;
  }

  function renderUnassignedRole(role) {
    return `<article class="zigbee-device-card unassigned"><header><div><span class="zigbee-device-role">${esc(roleName(role))}</span><h4>NIEPRZYPISANE</h4></div><span class="zigbee-device-state neutral">BRAK URZĄDZENIA</span></header><div class="zigbee-unassigned-role">W inwentarzu wybierz urządzenie i przypisz mu rolę ${esc(roleName(role))}.</div></article>`;
  }

  function assignedRole(ieee, devices) {
    const match = devices.find((device) => device.ieee_address === ieee);
    return match ? match.role : null;
  }

  function renderInventoryDevice(device, devices) {
    const coordinator = device.is_coordinator === true;
    const model = device.model || device.description || "—";
    const meta = [device.vendor, device.device_type, device.power_source].filter(Boolean).join(" · ") || "—";
    const role = assignedRole(device.ieee_address, devices);
    const controls = coordinator ? "" : `<div class="zigbee-device-management"><label>Nazwa<input class="zigbee-rename-input" type="text" maxlength="64" value="${esc(device.friendly_name)}" data-zigbee-name-input="${esc(device.ieee_address)}"></label><button class="zigbee-action" type="button" data-zigbee-rename="${esc(device.ieee_address)}">ZMIEŃ NAZWĘ</button><label>Rola systemowa<select class="zigbee-role-select" data-zigbee-role="${esc(device.ieee_address)}"><option value="" ${role === null ? "selected" : ""}>BEZ ROLI</option><option value="supply" ${role === "supply" ? "selected" : ""}>NAWIEW</option><option value="extract" ${role === "extract" ? "selected" : ""}>WYWIEW</option></select></label><button class="zigbee-remove" type="button" data-zigbee-remove="${esc(device.ieee_address)}" data-zigbee-name="${esc(device.friendly_name)}">USUŃ</button></div>`;
    return `<article class="zigbee-inventory-card ${coordinator ? "coordinator" : ""}"><div class="zigbee-inventory-main"><div><span>${coordinator ? "KOORDYNATOR" : "URZĄDZENIE"}</span><h4>${esc(device.friendly_name)}</h4><p>${esc(model)}</p></div><span class="zigbee-supported ${device.supported === true || coordinator ? "good" : "warn"}">${coordinator ? "CORE" : role ? roleName(role) : device.supported === true ? "OBSŁUGIWANE" : "NIEPOTWIERDZONE"}</span></div><div class="zigbee-inventory-meta"><span class="mono">${esc(device.ieee_address)}</span><span>${esc(meta)}</span></div>${controls}</article>`;
  }

  function joinText(zigbee) { if (zigbee.permit_join === true) return "parowanie: OTWARTE"; if (zigbee.permit_join === false) return "parowanie: zamknięte"; return "parowanie: —"; }

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
    ui.grid.innerHTML = ["supply", "extract"].map((role) => {
      const device = devices.find((item) => item.role === role);
      return device ? renderDevice(device) : renderUnassignedRole(role);
    }).join("");
    ui.inventory.innerHTML = inventory.length ? inventory.map((device) => renderInventoryDevice(device, devices)).join("") : '<div class="zigbee-loading">Brak danych bridge/devices.</div>';
    ui.permit.disabled = managementBusy || !connected || !bridgeOnline || zigbee.permit_join === true;
    ui.closeJoin.disabled = managementBusy || !connected || !bridgeOnline || zigbee.permit_join !== true;
    ui.inventory.querySelectorAll("button,select,input").forEach((element) => { element.disabled = managementBusy || !connected || !bridgeOnline; });
    ui.error.hidden = true;
  }

  function editingControlActive() {
    const active = document.activeElement;
    return Boolean(
      active
      && ui.inventory.contains(active)
      && active.matches("input[data-zigbee-name-input],select[data-zigbee-role]")
    );
  }

  function renderRemovalConfirmation(confirmation) {
    currentRemovalConfirmation = confirmation && typeof confirmation === "object" ? confirmation : null;
    if (!currentRemovalConfirmation) {
      ui.confirmOverlay.hidden = true;
      return;
    }
    ui.confirmTitle.textContent = currentRemovalConfirmation.title || "POTWIERDZENIE OPERACJI";
    ui.confirmMessage.textContent = currentRemovalConfirmation.message || "Potwierdź operację Zigbee.";
    ui.confirmDetail.textContent = currentRemovalConfirmation.detail || "";
    ui.confirmDevice.textContent = `${currentRemovalConfirmation.friendly_name || "urządzenie"} · ${currentRemovalConfirmation.device_id || "—"}`;
    ui.confirmExpires.textContent = `Wygasa: ${dateTime(currentRemovalConfirmation.expires_at)}`;
    ui.confirmCancel.disabled = confirmationBusy;
    ui.confirmOk.disabled = confirmationBusy;
    ui.confirmStatus.textContent = confirmationBusy ? "VENTILATION-CORE PRZETWARZA DECYZJĘ…" : "Potwierdzenie pochodzi z ventilation-core na CM5.";
    const wasHidden = ui.confirmOverlay.hidden;
    ui.confirmOverlay.hidden = false;
    if (wasHidden) ui.confirmCancel.focus({ preventScroll: true });
  }

  async function apiPost(path, body) {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const payload = await response.json();
    if (!response.ok || payload.ok !== true) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }
  function message(text, bad = false) { ui.managementMessage.hidden = false; ui.managementMessage.className = `zigbee-management-message ${bad ? "bad" : "good"}`; ui.managementMessage.textContent = text; }

  async function withBusy(action) {
    if (managementBusy) return;
    managementBusy = true;
    if (currentState) render(currentState);
    try { await action(); } finally { managementBusy = false; if (currentState) render(currentState); }
  }

  async function setPermitJoin(seconds) {
    await withBusy(async () => {
      try { await apiPost("/api/v1/zigbee/permit-join", { seconds }); message(seconds > 0 ? `Parowanie otwarte na ${seconds} s. Uruchom teraz tryb parowania urządzenia.` : "Parowanie zamknięte."); await refresh(true); }
      catch (error) { message(`Operacja Zigbee nie powiodła się: ${String(error.message || error)}`, true); }
    });
  }

  async function renameDevice(ieee) {
    const input = ui.inventory.querySelector(`[data-zigbee-name-input="${CSS.escape(ieee)}"]`);
    const newName = String(input?.value || "").trim();
    await withBusy(async () => {
      try { await apiPost("/api/v1/zigbee/rename", { device_id: ieee, new_name: newName }); message(`Nazwa urządzenia zmieniona na ${newName}.`); await refresh(true); }
      catch (error) { message(`Nie udało się zmienić nazwy: ${String(error.message || error)}`, true); }
    });
  }

  async function assignRole(ieee, roleValue) {
    const role = roleValue || null;
    await withBusy(async () => {
      try { await apiPost("/api/v1/zigbee/role", { device_id: ieee, role }); message(role ? `Przypisano rolę ${roleName(role)}.` : "Usunięto rolę systemową urządzenia."); await refresh(true); }
      catch (error) { message(`Nie udało się zmienić roli: ${String(error.message || error)}`, true); await refresh(true); }
    });
  }

  async function requestRemoveDevice(ieee, name) {
    await withBusy(async () => {
      try {
        const payload = await apiPost("/api/v1/zigbee/remove", { device_id: ieee });
        if (payload.confirmation_required !== true || !payload.confirmation) throw new Error("CM5 nie zwrócił żądania potwierdzenia");
        renderRemovalConfirmation(payload.confirmation);
        message(`CM5 oczekuje na potwierdzenie usunięcia: ${name}.`);
      } catch (error) {
        message(`Nie udało się utworzyć potwierdzenia w core: ${String(error.message || error)}`, true);
      }
    });
  }

  async function resolveRemovalConfirmation(confirmed) {
    if (confirmationBusy || !currentRemovalConfirmation) return;
    const confirmation = currentRemovalConfirmation;
    confirmationBusy = true;
    renderRemovalConfirmation(confirmation);
    try {
      const payload = await apiPost("/api/v1/zigbee/remove-confirmation", {
        confirmation_id: confirmation.confirmation_id,
        confirmed,
      });
      renderRemovalConfirmation(null);
      if (confirmed) {
        message(`Urządzenie ${confirmation.friendly_name || "Zigbee"} zostało usunięte przez ventilation-core.`);
      } else {
        message(`Anulowano usunięcie urządzenia ${confirmation.friendly_name || "Zigbee"}.`);
      }
      await refresh(true);
    } catch (error) {
      ui.confirmStatus.textContent = `Błąd CM5: ${String(error.message || error)}`;
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
    } catch (error) {
      if (currentRemovalConfirmation && !confirmationBusy) {
        ui.confirmStatus.textContent = `Nie można odczytać potwierdzenia z CM5: ${String(error.message || error)}`;
      }
    }
  }

  async function refresh(force = false) {
    if (document.hidden && !force) return;
    if (!force && editingControlActive()) return;
    try {
      const response = await fetch("/api/v1/zigbee", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok || payload.ok !== true || !payload.zigbee) throw new Error(payload.error || `HTTP ${response.status}`);
      if (!force && editingControlActive()) {
        currentState = payload.zigbee;
        return;
      }
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
    if (!ui.confirmOverlay.hidden && event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  });

  refresh();
  pollRemovalConfirmation();
  setInterval(refresh, 3000);
  setInterval(pollRemovalConfirmation, 2000);
})();
