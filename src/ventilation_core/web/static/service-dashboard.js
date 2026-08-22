"use strict";

(() => {
  const SERVICE_PATH = "/service";
  const POLL_MS = 5000;
  let serviceNav = null;
  let serviceView = null;
  let pollTimer = null;
  let requestInFlight = false;

  function normalizePath(pathname) {
    if (!pathname || pathname === "/") return "/";
    return pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
  }

  function valueOrDash(value) {
    return value === null || value === undefined || value === "" ? "—" : String(value);
  }

  function objectOrEmpty(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function formatNumber(value, digits = 1) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return value.toFixed(digits);
  }

  function formatBytes(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let current = value;
    let index = 0;
    while (current >= 1024 && index < units.length - 1) {
      current /= 1024;
      index += 1;
    }
    const digits = index === 0 ? 0 : current >= 100 ? 0 : current >= 10 ? 1 : 2;
    return `${current.toFixed(digits)} ${units[index]}`;
  }

  function formatDuration(seconds) {
    if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return "—";
    const total = Math.floor(seconds);
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    if (days > 0) return `${days} d ${hours} h`;
    if (hours > 0) return `${hours} h ${minutes} min`;
    return `${minutes} min`;
  }

  function formatDate(value) {
    if (typeof value !== "string" || !value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("pl-PL", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date);
  }

  function formatBool(value, yes = "TAK", no = "NIE") {
    if (value === true) return yes;
    if (value === false) return no;
    return "—";
  }

  function boolClass(value) {
    if (value === true) return "v2-service-good";
    if (value === false) return "v2-service-warn";
    return "v2-service-muted";
  }

  function semanticClass(state) {
    if (state === "ok") return "v2-service-good";
    if (state === "warning") return "v2-service-warn";
    if (state === "critical") return "v2-service-bad";
    return "v2-service-muted";
  }

  function localizeSystemdState(value) {
    const labels = {
      active: "AKTYWNA",
      inactive: "NIEAKTYWNA",
      failed: "BŁĄD",
      activating: "URUCHAMIANIE",
      deactivating: "ZATRZYMYWANIE",
      reloading: "PRZEŁADOWANIE",
    };
    return labels[value] || valueOrDash(value);
  }

  function localizeSystemdSubstate(value) {
    const labels = {
      running: "DZIAŁA",
      exited: "ZAKOŃCZONA",
      dead: "ZATRZYMANA",
      failed: "BŁĄD",
      start: "START",
      stop: "STOP",
      auto_restarting: "RESTART",
    };
    return labels[value] || valueOrDash(value);
  }

  function localizeHmiColor(value) {
    const labels = {
      green: "ZIELONY",
      yellow: "ŻÓŁTY",
      orange: "POMARAŃCZOWY",
      red: "CZERWONY",
    };
    return labels[value] || valueOrDash(value);
  }

  function makeKv(rows) {
    const dl = document.createElement("dl");
    dl.className = "v2-service-kv";
    rows.forEach(([label, value, className]) => {
      const row = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = valueOrDash(value);
      if (className) dd.className = className;
      row.append(dt, dd);
      dl.appendChild(row);
    });
    return dl;
  }

  function makePanel(title, kicker, className = "") {
    const article = document.createElement("article");
    article.className = `v2-service-panel ${className}`.trim();
    const header = document.createElement("header");
    const h2 = document.createElement("h2");
    const span = document.createElement("span");
    h2.textContent = title;
    span.textContent = kicker;
    header.append(h2, span);
    article.appendChild(header);
    return article;
  }

  function ensureNav() {
    const candidates = Array.from(document.querySelectorAll("a.v2-nav"));
    serviceNav = candidates.find((anchor) => {
      const spans = Array.from(anchor.querySelectorAll("span"));
      const label = spans.length ? spans[spans.length - 1].textContent : anchor.textContent;
      return String(label || "").trim().toUpperCase() === "SERWIS";
    }) || null;
    if (!serviceNav) return null;
    serviceNav.href = SERVICE_PATH;
    serviceNav.classList.remove("disabled");
    serviceNav.removeAttribute("aria-disabled");
    serviceNav.dataset.serviceDashboard = "true";
    return serviceNav;
  }

  function ensureView() {
    if (serviceView) return serviceView;
    const host = document.getElementById("viewHost");
    if (!host) return null;
    serviceView = document.createElement("section");
    serviceView.id = "serviceView";
    serviceView.className = "v2-shell-view v2-service-view";
    serviceView.dataset.view = "service";
    serviceView.hidden = true;
    serviceView.innerHTML = `
      <section class="v2-page-heading">
        <div class="v2-service-heading-copy">
          <h1>SERWIS</h1>
          <p>Diagnostyka systemowa i sprzętowa CM5</p>
        </div>
        <span class="v2-service-readonly">READ-ONLY</span>
      </section>
      <div id="serviceConnection" class="v2-service-connection">Oczekiwanie na diagnostykę…</div>
      <section id="serviceSummary" class="v2-service-summary" aria-label="Stan podsystemów"></section>
      <section id="serviceGrid" class="v2-service-grid"></section>`;
    host.appendChild(serviceView);
    return serviceView;
  }

  function setRouteVisible(visible) {
    const view = ensureView();
    if (!view) return;
    if (visible) {
      document.querySelectorAll("#viewHost > .v2-shell-view").forEach((candidate) => {
        candidate.hidden = candidate !== view;
      });
      document.querySelectorAll("a.v2-nav").forEach((anchor) => {
        anchor.classList.toggle("active", anchor === serviceNav);
        if (anchor === serviceNav) anchor.setAttribute("aria-current", "page");
        else anchor.removeAttribute("aria-current");
      });
      view.hidden = false;
      pollServiceStatus();
    } else {
      view.hidden = true;
      if (serviceNav) {
        serviceNav.classList.remove("active");
        serviceNav.removeAttribute("aria-current");
      }
    }
  }

  function serviceIsVisible() {
    return serviceView && serviceView.hidden === false && normalizePath(window.location.pathname) === SERVICE_PATH;
  }

  function renderSummary(items) {
    const host = document.getElementById("serviceSummary");
    if (!host) return;
    host.replaceChildren();
    const rows = Array.isArray(items) ? items : [];
    rows.forEach((item) => {
      const card = document.createElement("article");
      card.className = "v2-service-summary-card";
      card.dataset.state = String(item && item.state || "unavailable");
      const label = document.createElement("span");
      const state = document.createElement("strong");
      const detail = document.createElement("small");
      label.textContent = valueOrDash(item && item.label);
      const stateValue = String(item && item.state || "unavailable");
      state.textContent = stateValue === "ok" ? "OK" : stateValue === "critical" ? "KRYTYCZNY" : stateValue === "warning" ? "UWAGA" : "BRAK DANYCH";
      detail.textContent = valueOrDash(item && item.detail);
      card.append(label, state, detail);
      host.appendChild(card);
    });
  }

  function renderSystem(system) {
    const panel = makePanel("CM5 / SYSTEM", "LINUX · ZASILANIE");
    const memory = objectOrEmpty(system && system.memory);
    const storage = objectOrEmpty(system && system.root_storage);
    const load = objectOrEmpty(system && system.load_average);
    const power = objectOrEmpty(system && system.power);
    panel.appendChild(makeKv([
      ["Model", system && system.model],
      ["Hostname", system && system.hostname],
      ["System", system && system.os],
      ["Kernel", system && system.kernel],
      ["Architektura", system && system.architecture],
      ["Uptime", formatDuration(system && system.uptime_seconds)],
      ["CPU", typeof (system && system.cpu_usage_percent) === "number" ? `${formatNumber(system.cpu_usage_percent)} %` : "—"],
      ["Temperatura CPU", typeof (system && system.cpu_temperature_celsius) === "number" ? `${formatNumber(system.cpu_temperature_celsius)} °C` : "—"],
      ["Load 1 / 5 / 15 min", `${formatNumber(load["1m"], 2)} / ${formatNumber(load["5m"], 2)} / ${formatNumber(load["15m"], 2)}`],
      ["RAM użyte", `${formatBytes(memory.used_bytes)} / ${formatBytes(memory.total_bytes)} (${valueOrDash(memory.used_percent)}%)`],
      ["Dysk / użyte", `${formatBytes(storage.used_bytes)} / ${formatBytes(storage.total_bytes)} (${valueOrDash(storage.used_percent)}%)`],
      ["get_throttled", power.mask_hex || power.raw, power.undervoltage_now === true ? "v2-service-bad" : power.available === true ? "v2-service-good" : "v2-service-muted"],
      ["Undervoltage TERAZ", formatBool(power.undervoltage_now), power.undervoltage_now === true ? "v2-service-bad" : boolClass(power.undervoltage_now === false ? true : null)],
      ["Undervoltage od boot", formatBool(power.undervoltage_occurred), power.undervoltage_occurred === true ? "v2-service-warn" : boolClass(power.undervoltage_occurred === false ? true : null)],
      ["Throttling TERAZ", formatBool(power.throttled_now), power.throttled_now === true ? "v2-service-bad" : boolClass(power.throttled_now === false ? true : null)],
      ["Throttling od boot", formatBool(power.throttled_occurred), power.throttled_occurred === true ? "v2-service-warn" : boolClass(power.throttled_occurred === false ? true : null)],
      ["Czas systemowy", formatDate(system && system.system_time)],
    ]));
    return panel;
  }

  function renderCore(core) {
    const panel = makePanel("CORE / BEZPIECZEŃSTWO", "VENTILATION-CORE");
    const setpoints = objectOrEmpty(core && core.setpoints);
    const v2 = objectOrEmpty(core && core.alert_v2);
    panel.appendChild(makeKv([
      ["Dostępność core", formatBool(core && core.available, "DOSTĘPNY", "BRAK"), boolClass(core && core.available)],
      ["Tryb", core && core.mode],
      ["Nawiew", typeof setpoints.supply_voltage === "number" ? `${setpoints.supply_voltage.toFixed(1)} V` : "—"],
      ["Wyciąg", typeof setpoints.extract_voltage === "number" ? `${setpoints.extract_voltage.toFixed(1)} V` : "—"],
      ["hardware_ready", formatBool(core && core.hardware_ready), boolClass(core && core.hardware_ready)],
      ["output_state_known", formatBool(core && core.output_state_known), boolClass(core && core.output_state_known)],
      ["Błędy sprzętowe z rzędu", core && core.consecutive_hardware_failures],
      ["Aktywne alerty", core && core.active_alert_count],
      ["Krytyczne alerty", core && core.critical_alert_count],
      ["AlertV2 policy", v2.policy_version],
      ["AlertV2 SHA", v2.policy_sha256],
      ["control_policy_applied", formatBool(v2.control_policy_applied), v2.control_policy_applied === false ? "v2-service-good" : v2.control_policy_applied === true ? "v2-service-warn" : "v2-service-muted"],
      ["Najwyższa waga", v2.highest_active_weight],
      ["Kolor HMI", localizeHmiColor(v2.hmi_color)],
    ]));
    return panel;
  }

  function renderServices(services) {
    const panel = makePanel("USŁUGI SYSTEMOWE", "SYSTEMD", "wide");
    const wrap = document.createElement("div");
    wrap.className = "v2-service-table-wrap";
    const table = document.createElement("table");
    table.className = "v2-service-table";
    table.innerHTML = "<thead><tr><th>USŁUGA</th><th>STAN</th><th>SUBSTATE</th><th>PID</th><th>UPTIME</th><th>RESTARTY</th><th>START</th></tr></thead>";
    const tbody = document.createElement("tbody");
    (Array.isArray(services) ? services : []).forEach((service) => {
      const tr = document.createElement("tr");
      const values = [
        service.unit,
        service.available === false ? "NIEDOSTĘPNA" : localizeSystemdState(service.active_state),
        localizeSystemdSubstate(service.sub_state),
        service.pid,
        formatDuration(service.uptime_seconds),
        service.restarts,
        service.started_at,
      ];
      values.forEach((value, index) => {
        const td = document.createElement("td");
        td.textContent = valueOrDash(value);
        if (index === 1) td.className = service.active_state === "active" ? "v2-service-good" : "v2-service-warn";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    panel.appendChild(wrap);
    return panel;
  }

  function renderHardware(hardware) {
    const panel = makePanel("SPRZĘT / MAGISTRALE", "SEN55 · AERO · TACHO · ZIGBEE", "double");
    const sensor = objectOrEmpty(hardware && hardware.sensor_bus);
    const aero = objectOrEmpty(hardware && hardware.aero);
    const tacho = objectOrEmpty(hardware && hardware.tacho);
    const zigbee = objectOrEmpty(hardware && hardware.zigbee);

    const subgrid = document.createElement("div");
    subgrid.className = "v2-service-subgrid";

    const busCard = document.createElement("div");
    busCard.className = "v2-service-subcard";
    busCard.innerHTML = "<h3>SENSOR BUS</h3>";
    busCard.appendChild(makeKv([
      ["Port", sensor.port],
      ["Baud", sensor.baudrate],
      ["Ready", formatBool(sensor.ready), boolClass(sensor.ready)],
      ["Worker", formatBool(sensor.worker_alive), boolClass(sensor.worker_alive)],
      ["Restarty", sensor.worker_restarts],
      ["Ostatni cykl", formatDate(sensor.last_cycle_at)],
      ["Błąd", sensor.last_error],
    ]));
    subgrid.appendChild(busCard);

    const aeroCard = document.createElement("div");
    aeroCard.className = "v2-service-subcard";
    aeroCard.innerHTML = "<h3>AERO / MODBUS</h3>";
    aeroCard.appendChild(makeKv([
      ["Port", aero.port],
      ["Adres", aero.slave_address],
      ["Baud", aero.baudrate],
      ["Online", formatBool(aero.online), boolClass(aero.online)],
      ["Usable", formatBool(aero.usable), boolClass(aero.usable)],
      ["Polls", aero.polls],
      ["Błędy komunikacji", aero.communication_errors],
      ["Ostatni sukces", formatDate(aero.last_success_at)],
      ["Błąd", aero.last_error],
    ]));
    subgrid.appendChild(aeroCard);

    const tachoCard = document.createElement("div");
    tachoCard.className = "v2-service-subcard";
    tachoCard.innerHTML = "<h3>TACHO</h3>";
    const supply = objectOrEmpty(tacho.supply);
    const extract = objectOrEmpty(tacho.extract);
    const supplyStatus = objectOrEmpty(supply.service_status);
    const extractStatus = objectOrEmpty(extract.service_status);
    tachoCard.appendChild(makeKv([
      ["Monitor ready", formatBool(tacho.ready), boolClass(tacho.ready)],
      ["Worker", formatBool(tacho.worker_alive), boolClass(tacho.worker_alive)],
      ["Nawiew GPIO", supply.line_name],
      ["Nawiew Hz / RPM", `${formatNumber(supply.frequency_hz, 1)} / ${formatNumber(supply.rpm, 0)}`],
      ["Nawiew valid", supplyStatus.text, semanticClass(supplyStatus.state)],
      ["Wyciąg GPIO", extract.line_name],
      ["Wyciąg Hz / RPM", `${formatNumber(extract.frequency_hz, 1)} / ${formatNumber(extract.rpm, 0)}`],
      ["Wyciąg valid", extractStatus.text, semanticClass(extractStatus.state)],
      ["Błąd", tacho.last_error],
    ]));
    subgrid.appendChild(tachoCard);

    const zigbeeCard = document.createElement("div");
    zigbeeCard.className = "v2-service-subcard";
    zigbeeCard.innerHTML = "<h3>ZIGBEE / MQTT</h3>";
    zigbeeCard.appendChild(makeKv([
      ["Broker", `${valueOrDash(zigbee.broker_host)}:${valueOrDash(zigbee.broker_port)}`],
      ["Połączony", formatBool(zigbee.connected), boolClass(zigbee.connected)],
      ["Bridge online", formatBool(zigbee.bridge_online), boolClass(zigbee.bridge_online)],
      ["Urządzenia", Array.isArray(zigbee.inventory) ? zigbee.inventory.length : null],
      ["Czujniki", Array.isArray(zigbee.sensor_list) ? zigbee.sensor_list.length : null],
      ["Ostatnia wiadomość", formatDate(zigbee.last_message_at)],
      ["Błąd", zigbee.last_error],
    ]));
    subgrid.appendChild(zigbeeCard);

    panel.appendChild(subgrid);

    const nodes = Array.isArray(hardware && hardware.sen55_nodes) ? hardware.sen55_nodes : [];
    if (nodes.length) {
      const wrap = document.createElement("div");
      wrap.className = "v2-service-table-wrap";
      wrap.style.marginTop = "10px";
      const table = document.createElement("table");
      table.className = "v2-service-table";
      table.innerHTML = "<thead><tr><th>SEN55</th><th>ONLINE</th><th>USABLE</th><th>FW</th><th>POLLS</th><th>BŁĘDY COMM</th><th>FAILS</th><th>OSTATNI SUKCES</th><th>BŁĄD</th></tr></thead>";
      const tbody = document.createElement("tbody");
      nodes.forEach((node) => {
        const tr = document.createElement("tr");
        [
          `#${valueOrDash(node.slave_address)}`,
          formatBool(node.online),
          formatBool(node.usable),
          node.firmware_version,
          node.polls,
          node.communication_errors,
          node.consecutive_failures,
          formatDate(node.last_success_at),
          node.last_error,
        ].forEach((value, index) => {
          const td = document.createElement("td");
          td.textContent = valueOrDash(value);
          if (index === 1) td.className = boolClass(node.online);
          if (index === 2) td.className = boolClass(node.usable);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      panel.appendChild(wrap);
    }
    return panel;
  }

  function renderNetwork(network) {
    const panel = makePanel("SIEĆ", "ETHERNET · WI-FI · SERVICE AP");
    const route = objectOrEmpty(network && network.default_route);
    const ai = objectOrEmpty(network && network.ai_server);
    const mqtt = objectOrEmpty(network && network.mqtt);
    const plane = objectOrEmpty(network && network.service_plane);
    const planeNetwork = objectOrEmpty(plane.network);
    panel.appendChild(makeKv([
      ["Default route", `${valueOrDash(route.interface)} → ${valueOrDash(route.gateway)}`],
      ["AI Server", `${valueOrDash(ai.host)}:${valueOrDash(ai.port)}`],
      ["AI TCP", formatBool(ai.reachable, "DOSTĘPNY", "BRAK"), boolClass(ai.reachable)],
      ["MQTT", `${valueOrDash(mqtt.host)}:${valueOrDash(mqtt.port)}`],
      ["MQTT TCP", formatBool(mqtt.reachable, "DOSTĘPNY", "BRAK"), boolClass(mqtt.reachable)],
      ["Service Agent", formatBool(plane.available, "DOSTĘPNY", "BRAK"), boolClass(plane.available)],
      ["Service AP ready", formatBool(planeNetwork.ready), boolClass(planeNetwork.ready)],
      ["Service AP", planeNetwork.interface],
      ["Service IP", planeNetwork.bind_address],
    ]));

    const interfaces = Array.isArray(network && network.interfaces) ? network.interfaces : [];
    if (interfaces.length) {
      const list = document.createElement("div");
      list.className = "v2-service-inline-list";
      list.style.marginTop = "10px";
      interfaces.forEach((item) => {
        const row = document.createElement("div");
        row.className = "v2-service-subcard";
        const ipv4 = Array.isArray(item.ipv4) ? item.ipv4.join(", ") : "—";
        row.innerHTML = `<h3>${valueOrDash(item.name)}</h3>`;
        row.appendChild(makeKv([
          ["Stan", item.operstate],
          ["IPv4", ipv4],
          ["MAC", item.mac],
          ["Link", typeof item.speed_mbps === "number" ? `${item.speed_mbps} Mb/s` : "—"],
          ["MTU", item.mtu],
        ]));
        list.appendChild(row);
      });
      panel.appendChild(list);
    }
    return panel;
  }

  function renderDataAi(data, ai) {
    const panel = makePanel("DANE / AI", "SQLITE · SYNC · ADVISORY");
    const telemetry = objectOrEmpty(data && data.telemetry);
    const alerts = objectOrEmpty(data && data.alerts);
    const rollups = objectOrEmpty(telemetry.rollups);
    panel.appendChild(makeKv([
      ["Telemetry DB", formatBytes(telemetry.size_bytes)],
      ["Próbek raw", telemetry.samples],
      ["Pending sync", telemetry.pending_sync],
      ["Ostatnia próbka", formatDate(telemetry.last_sample_at)],
      ["Ostatni sync", formatDate(telemetry.last_synced_at)],
      ["Rollup 1m", rollups["1m"] && rollups["1m"].available === true ? formatDate(rollups["1m"].latest_bucket) : "—"],
      ["Rollup 15m", rollups["15m"] && rollups["15m"].available === true ? formatDate(rollups["15m"].latest_bucket) : "—"],
      ["Rollup 1h", rollups["1h"] && rollups["1h"].available === true ? formatDate(rollups["1h"].latest_bucket) : "—"],
      ["Rollup 1d", rollups["1d"] && rollups["1d"].available === true ? formatDate(rollups["1d"].latest_bucket) : "—"],
      ["Alert DB", formatBytes(alerts.size_bytes)],
      ["Wpisy alertów", alerts.records],
      ["Aktywne w DB", alerts.active_records],
      ["AI Server TCP", formatBool(ai && ai.server_reachable, "DOSTĘPNY", "BRAK"), boolClass(ai && ai.server_reachable)],
      ["Advisory", formatBool(ai && ai.advisory_available, "DOSTĘPNE", "BRAK"), boolClass(ai && ai.advisory_available)],
      ["Advisory świeże", formatBool(ai && ai.advisory_fresh), boolClass(ai && ai.advisory_fresh)],
      ["Wiek advisory", formatDuration(ai && ai.advisory_age_seconds)],
      ["Okno AI", formatDate(ai && ai.last_window_end)],
      ["Błąd AI", ai && ai.error],
    ]));
    return panel;
  }

  function renderServicePlane(network) {
    const plane = objectOrEmpty(network && network.service_plane);
    const agent = objectOrEmpty(plane.agent);
    const nodes = Array.isArray(plane.nodes) ? plane.nodes : [];
    const panel = makePanel("WĘZŁY SERWISOWE", "WVC-SERVICE", "wide");
    panel.appendChild(makeKv([
      ["Agent ready", formatBool(agent.ready), boolClass(agent.ready)],
      ["Socket", plane.socket],
      ["UDP bind", agent.udp_bind],
      ["Węzły zarejestrowane", agent.registered_nodes],
      ["Węzły online", agent.online_nodes],
      ["Start agenta", typeof agent.started_unix_ms === "number" ? formatDate(new Date(agent.started_unix_ms).toISOString()) : "—"],
      ["Błąd", plane.error],
    ]));
    if (nodes.length) {
      const wrap = document.createElement("div");
      wrap.className = "v2-service-table-wrap";
      wrap.style.marginTop = "10px";
      const table = document.createElement("table");
      table.className = "v2-service-table";
      table.innerHTML = "<thead><tr><th>NODE</th><th>ONLINE</th><th>IP</th><th>MAC</th><th>FW</th><th>UPTIME</th><th>RSSI</th><th>RS485</th><th>MODBUS</th><th>ADDR</th><th>OSTATNI HB</th></tr></thead>";
      const tbody = document.createElement("tbody");
      nodes.forEach((node) => {
        const tr = document.createElement("tr");
        const values = [
          node.node_id,
          formatBool(node.online),
          node.source_ip,
          node.mac,
          node.firmware,
          formatDuration(node.uptime_s),
          typeof node.wifi_rssi_dbm === "number" ? `${node.wifi_rssi_dbm} dBm` : "—",
          formatBool(node.rs485_ready),
          formatBool(node.modbus_monitor_ready),
          node.modbus_address,
          typeof node.received_unix_ms === "number" ? formatDate(new Date(node.received_unix_ms).toISOString()) : "—",
        ];
        values.forEach((value, index) => {
          const td = document.createElement("td");
          td.textContent = valueOrDash(value);
          if (index === 1) td.className = boolClass(node.online);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      panel.appendChild(wrap);
    }
    return panel;
  }

  function renderSnapshot(snapshot) {
    const connection = document.getElementById("serviceConnection");
    const grid = document.getElementById("serviceGrid");
    if (!connection || !grid) return;
    if (!snapshot || snapshot.available !== true) {
      connection.textContent = `Diagnostyka niedostępna: ${valueOrDash(snapshot && snapshot.error)}`;
      connection.className = "v2-service-connection bad";
      renderSummary([]);
      grid.replaceChildren();
      return;
    }
    connection.textContent = `Dane read-only z CM5 · aktualizacja ${formatDate(snapshot.generated_at)}`;
    connection.className = "v2-service-connection good";
    renderSummary(snapshot.summary);
    grid.replaceChildren(
      renderSystem(snapshot.system || {}),
      renderCore(snapshot.core || {}),
      renderNetwork(snapshot.network || {}),
      renderServices(snapshot.services || []),
      renderHardware(snapshot.hardware || {}),
      renderDataAi(snapshot.data || {}, snapshot.ai || {}),
      renderServicePlane(snapshot.network || {}),
    );
  }

  async function pollServiceStatus() {
    if (!serviceIsVisible() || requestInFlight) return;
    requestInFlight = true;
    const connection = document.getElementById("serviceConnection");
    try {
      const response = await fetch("/api/v1/service/status", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok || payload.ok !== true || !payload.service || typeof payload.service !== "object") {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      renderSnapshot(payload.service);
    } catch (error) {
      if (connection) {
        connection.textContent = `Brak danych SERWIS: ${String(error.message || error)}`;
        connection.className = "v2-service-connection bad";
      }
    } finally {
      requestInFlight = false;
    }
  }

  function installRouting() {
    const nav = ensureNav();
    const view = ensureView();
    if (!nav || !view) return;

    nav.addEventListener("click", (event) => {
      event.preventDefault();
      if (normalizePath(window.location.pathname) !== SERVICE_PATH) {
        window.history.pushState({}, "", SERVICE_PATH);
      }
      setRouteVisible(true);
    });

    document.addEventListener("click", (event) => {
      const anchor = event.target.closest && event.target.closest("a.v2-nav");
      if (!anchor || anchor === nav) return;
      setRouteVisible(false);
    }, true);

    window.addEventListener("popstate", () => {
      setRouteVisible(normalizePath(window.location.pathname) === SERVICE_PATH);
    });

    if (normalizePath(window.location.pathname) === SERVICE_PATH) {
      setRouteVisible(true);
    }

    pollTimer = window.setInterval(() => {
      if (serviceIsVisible()) pollServiceStatus();
    }, POLL_MS);
  }

  installRouting();

  window.addEventListener("beforeunload", () => {
    if (pollTimer !== null) window.clearInterval(pollTimer);
  });
})();