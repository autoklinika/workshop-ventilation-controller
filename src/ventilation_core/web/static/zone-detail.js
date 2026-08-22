"use strict";

/*
 * Zone detail client.
 *
 * This file is presentation-only. It reads already normalized ventilation-core
 * state through the existing WebUI GET endpoints and renders direct values.
 * It does not calculate air-quality decisions, trends, averages, automation or
 * control commands. No POST/PUT/PATCH/DELETE requests are issued here.
 */

const ZONE_DETAIL_OPEN_MS = 280;
const ZONE_DETAIL_CLOSE_MS = 240;
const ZONE_DETAIL_POLL_MS = 2000;
const ZONE_DETAIL_VALUE_MIN_PX = 16;
const ZONE_DETAIL_VALUE_MAX_PX = 64;
const ZONE_DETAIL_TEXT_MAX_PX = 50;

let zoneDetailTransitionSerial = 0;
let zoneDetailActiveKey = null;
let zoneDetailSourceCard = null;
let zoneDetailPollTimer = null;
let zoneDetailRefreshBusy = false;
let zoneDetailConfigLoaded = false;
let zoneDetailFitFrame = null;
let zoneDetailConfig = {
  zone1: { name: "Mycie / Wygrzewanie", sensor_address: 1 },
  zone2: { name: "Lutowanie", sensor_address: 2 },
};

function zoneDetailReducedMotion() {
  return typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function zoneDetailCanAnimate(element) {
  return !zoneDetailReducedMotion() && element && typeof element.animate === "function";
}

function cancelZoneDetailAnimations(overlay) {
  if (!overlay || typeof overlay.getAnimations !== "function") return;
  overlay.getAnimations({ subtree: true }).forEach((animation) => animation.cancel());
}

function zoneDetailTransformFromCard(sourceCard, detailCard) {
  const source = sourceCard.getBoundingClientRect();
  const target = detailCard.getBoundingClientRect();
  const targetWidth = Math.max(1, target.width);
  const targetHeight = Math.max(1, target.height);
  const scaleX = Math.max(0.001, source.width / targetWidth);
  const scaleY = Math.max(0.001, source.height / targetHeight);
  const sourceCenterX = source.left + source.width / 2;
  const sourceCenterY = source.top + source.height / 2;
  const targetCenterX = target.left + target.width / 2;
  const targetCenterY = target.top + target.height / 2;
  return `translate(${sourceCenterX - targetCenterX}px, ${sourceCenterY - targetCenterY}px) scale(${scaleX}, ${scaleY})`;
}

function ensureZoneDetailModal() {
  let overlay = document.getElementById("zoneDetailModal");
  if (overlay) return overlay;

  overlay = document.createElement("div");
  overlay.id = "zoneDetailModal";
  overlay.className = "v2-zone-detail";
  overlay.hidden = true;
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "zoneDetailTitle");
  overlay.innerHTML = `
    <section class="v2-zone-detail-card">
      <header class="v2-zone-detail-header">
        <div class="v2-zone-detail-title">
          <span id="zoneDetailKicker">STREFA</span>
          <h2 id="zoneDetailTitle">—</h2>
        </div>
        <div class="v2-zone-detail-head-meta">
          <span id="zoneDetailStatus" class="status-chip status-unknown">ŁADOWANIE</span>
          <span id="zoneDetailUpdated" class="v2-zone-detail-updated">—</span>
        </div>
        <button id="zoneDetailClose" class="v2-zone-detail-close" type="button">ZAMKNIJ</button>
      </header>
      <div id="zoneDetailBody" class="v2-zone-detail-body">
        <div class="v2-zone-detail-empty">Ładowanie bieżących danych…</div>
      </div>
    </section>`;
  document.body.appendChild(overlay);

  const close = document.getElementById("zoneDetailClose");
  if (close) close.addEventListener("click", closeZoneDetailModal);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || overlay.hidden) return;
    const systemAlert = document.getElementById("globalSystemAlert");
    if (systemAlert && !systemAlert.hidden) return;
    closeZoneDetailModal();
  });

  return overlay;
}

function zoneDetailFormatNumber(value, digits) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("pl-PL", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })
    : "—";
}

function zoneDetailItem(label, value, unit = "", kind = "") {
  return { label, value, unit, kind };
}

function zoneDetailBool(value, trueText = "TAK", falseText = "NIE") {
  if (value === true) return trueText;
  if (value === false) return falseText;
  return "—";
}

function zoneDetailNodeByAddress(sensorBus, address) {
  if (!sensorBus || !Array.isArray(sensorBus.nodes)) return null;
  return sensorBus.nodes.find((node) => node && node.slave_address === address) || null;
}

function zoneDetailNodeCurrent(node) {
  return Boolean(
    node &&
      node.online === true &&
      node.usable === true &&
      node.measurement_valid === true &&
      node.measurement_stale !== true
  );
}

function zoneDetailReading(node) {
  return zoneDetailNodeCurrent(node) && node.reading && typeof node.reading === "object"
    ? node.reading
    : {};
}

function zoneDetailZigbeeByRole(state, role) {
  const zigbee = state && state.zigbee;
  const devices = zigbee && Array.isArray(zigbee.devices) ? zigbee.devices : [];
  return devices.find((item) => item && item.role === role) || null;
}

function zoneDetailZigbeeValue(device, field, digits) {
  if (!device || device.available === false) return "—";
  return zoneDetailFormatNumber(device[field], digits);
}

function zoneDetailTachoValue(channel, field, digits) {
  if (!channel || channel.valid !== true) return "—";
  return zoneDetailFormatNumber(channel[field], digits);
}

function zoneDetailAeroUsable(aero) {
  return Boolean(
    aero &&
      aero.ready === true &&
      aero.worker_alive === true &&
      aero.online === true &&
      aero.usable === true
  );
}

function zoneDetailAirGroup(reading) {
  return {
    title: "POWIETRZE · SEN55",
    items: [
      zoneDetailItem("PM1.0", zoneDetailFormatNumber(reading.pm1_0_ug_m3, 1), "µg/m³"),
      zoneDetailItem("PM2.5", zoneDetailFormatNumber(reading.pm2_5_ug_m3, 1), "µg/m³"),
      zoneDetailItem("PM4", zoneDetailFormatNumber(reading.pm4_0_ug_m3, 1), "µg/m³"),
      zoneDetailItem("PM10", zoneDetailFormatNumber(reading.pm10_0_ug_m3, 1), "µg/m³"),
      zoneDetailItem("VOC Index", zoneDetailFormatNumber(reading.voc_index, 0)),
      zoneDetailItem("NOx Index", zoneDetailFormatNumber(reading.nox_index, 0)),
      zoneDetailItem("Temperatura", zoneDetailFormatNumber(reading.temperature_celsius, 1), "°C"),
      zoneDetailItem("Wilgotność", zoneDetailFormatNumber(reading.humidity_percent, 1), "%"),
    ],
  };
}

function zoneDetailZone1Groups(state, node) {
  const reading = zoneDetailReading(node);
  const setpoints = state && state.setpoints ? state.setpoints : {};
  const tacho = state && state.tacho ? state.tacho : {};
  const supplyTacho = tacho && tacho.supply ? tacho.supply : null;
  const extractTacho = tacho && tacho.extract ? tacho.extract : null;
  const supplyTemp = zoneDetailZigbeeByRole(state, "supply");
  const extractTemp = zoneDetailZigbeeByRole(state, "extract");

  return [
    zoneDetailAirGroup(reading),
    {
      title: "WENTYLACJA · EC 0–10 V",
      items: [
        zoneDetailItem("Nawiew · zadane", zoneDetailFormatNumber(setpoints.supply_voltage, 1), "V"),
        zoneDetailItem("Wyciąg · zadane", zoneDetailFormatNumber(setpoints.extract_voltage, 1), "V"),
        zoneDetailItem("Nawiew · RPM", zoneDetailTachoValue(supplyTacho, "rpm", 0), "RPM"),
        zoneDetailItem("Wyciąg · RPM", zoneDetailTachoValue(extractTacho, "rpm", 0), "RPM"),
        zoneDetailItem("Nawiew · TACHO", zoneDetailTachoValue(supplyTacho, "frequency_hz", 1), "Hz"),
        zoneDetailItem("Wyciąg · TACHO", zoneDetailTachoValue(extractTacho, "frequency_hz", 1), "Hz"),
        zoneDetailItem("Tryb", state && typeof state.mode === "string" ? state.mode : "—", "", "text"),
        zoneDetailItem(
          "Stan wyjść",
          state && state.output_state_known === true ? "ZNANY" : "NIEPEWNY",
          "",
          state && state.output_state_known === true ? "good text" : "warn text"
        ),
      ],
    },
    {
      title: "TEMPERATURY KANAŁÓW · ZIGBEE",
      items: [
        zoneDetailItem("Nawiew", zoneDetailZigbeeValue(supplyTemp, "temperature_celsius", 1), "°C"),
        zoneDetailItem("Wywiew", zoneDetailZigbeeValue(extractTemp, "temperature_celsius", 1), "°C"),
        zoneDetailItem("Bateria · nawiew", zoneDetailZigbeeValue(supplyTemp, "battery_percent", 0), "%"),
        zoneDetailItem("Bateria · wywiew", zoneDetailZigbeeValue(extractTemp, "battery_percent", 0), "%"),
        zoneDetailItem(
          "SEN55",
          node ? (zoneDetailNodeCurrent(node) ? "ONLINE" : node.online === true ? "BRAK DANYCH" : "OFFLINE") : "BRAK",
          "",
          zoneDetailNodeCurrent(node) ? "good text" : "warn text"
        ),
        zoneDetailItem(
          "TACHO monitor",
          tacho && tacho.ready === true && tacho.worker_alive === true ? "ONLINE" : "NIEDOSTĘPNY",
          "",
          tacho && tacho.ready === true && tacho.worker_alive === true ? "good text" : "warn text"
        ),
        zoneDetailItem(
          "Zigbee",
          state && state.zigbee && state.zigbee.connected === true ? "POŁĄCZONY" : "NIEDOSTĘPNY",
          "",
          state && state.zigbee && state.zigbee.connected === true ? "good text" : "warn text"
        ),
        zoneDetailItem("Wiek danych SEN55", zoneDetailFormatNumber(node && node.age_seconds, 0), "s"),
      ],
    },
  ];
}

function zoneDetailAeroCommandValue(result, field) {
  if (!result || !Number.isInteger(result[field])) return "—";
  const value = result[field];
  if (result.kind === "speed") return `BIEG ${value}`;
  if (result.kind === "airing") return value === 1 ? "WŁĄCZONE" : "WYŁĄCZONE";
  return String(value);
}

function zoneDetailAeroCommandName(result) {
  if (!result || typeof result.kind !== "string") return "—";
  if (result.kind === "speed") return "PRĘDKOŚĆ";
  if (result.kind === "airing") return "PRZEWIETRZANIE";
  return result.kind.toUpperCase();
}

function zoneDetailZone2Groups(state, node) {
  const reading = zoneDetailReading(node);
  const aero = state && state.aero_bus ? state.aero_bus : null;
  const usable = zoneDetailAeroUsable(aero);
  const telemetry = usable && aero.telemetry && typeof aero.telemetry === "object" ? aero.telemetry : {};
  const result = aero && aero.last_control_result && typeof aero.last_control_result === "object"
    ? aero.last_control_result
    : null;

  return [
    zoneDetailAirGroup(reading),
    {
      title: "REKUPERATOR AERO · POMIARY",
      items: [
        zoneDetailItem("Wilgotność", zoneDetailFormatNumber(telemetry.humidity_percent, 1), "%"),
        zoneDetailItem("Temperatura nawiewu", zoneDetailFormatNumber(telemetry.supply_temperature_celsius, 1), "°C"),
        zoneDetailItem("Temperatura wywiewu", zoneDetailFormatNumber(telemetry.extract_temperature_celsius, 1), "°C"),
        zoneDetailItem("Temperatura zewnętrzna", zoneDetailFormatNumber(telemetry.outdoor_temperature_celsius, 1), "°C"),
        zoneDetailItem("Wentylator 1", zoneDetailFormatNumber(telemetry.fan_1_percent, 0), "%"),
        zoneDetailItem("Wentylator 2", zoneDetailFormatNumber(telemetry.fan_2_percent, 0), "%"),
        zoneDetailItem(
          "AERO",
          usable ? "ONLINE" : "NIEDOSTĘPNY",
          "",
          usable ? "good text" : "warn text"
        ),
        zoneDetailItem("Tryb systemu", state && typeof state.mode === "string" ? state.mode : "—", "", "text"),
      ],
    },
    {
      title: "REKUPERATOR AERO · STEROWANIE",
      items: [
        zoneDetailItem("Ostatnie polecenie", zoneDetailAeroCommandName(result), "", "text"),
        zoneDetailItem("Ostatnia wartość zadana", zoneDetailAeroCommandValue(result, "target_value"), "", "text"),
        zoneDetailItem("Odczyt zwrotny", zoneDetailAeroCommandValue(result, "readback_value"), "", "text"),
        zoneDetailItem(
          "Stan polecenia",
          result && typeof result.state === "string" ? result.state.toUpperCase() : "—",
          "",
          "text"
        ),
        zoneDetailItem("Sterowanie w toku", zoneDetailBool(aero && aero.control_busy, "TAK", "NIE"), "", "text"),
        zoneDetailItem("Potwierdzenie fizyczne", zoneDetailBool(result && result.physical_confirmation), "", "text"),
        zoneDetailItem(
          "SEN55",
          node ? (zoneDetailNodeCurrent(node) ? "ONLINE" : node.online === true ? "BRAK DANYCH" : "OFFLINE") : "BRAK",
          "",
          zoneDetailNodeCurrent(node) ? "good text" : "warn text"
        ),
        zoneDetailItem("Wiek danych SEN55", zoneDetailFormatNumber(node && node.age_seconds, 0), "s"),
      ],
    },
  ];
}

function zoneDetailFitValue(value) {
  const wrap = value && value.parentElement;
  if (!wrap) return;

  const row = value.closest(".v2-zone-detail-item");
  const maxPx = row && row.classList.contains("is-text")
    ? ZONE_DETAIL_TEXT_MAX_PX
    : ZONE_DETAIL_VALUE_MAX_PX;
  const availableWidth = Math.max(1, wrap.clientWidth);
  const availableHeight = Math.max(1, wrap.clientHeight);
  let low = ZONE_DETAIL_VALUE_MIN_PX;
  let high = maxPx;

  value.style.fontSize = `${high}px`;
  if (value.scrollWidth <= availableWidth && value.scrollHeight <= availableHeight) return;

  for (let step = 0; step < 8; step += 1) {
    const middle = (low + high) / 2;
    value.style.fontSize = `${middle}px`;
    if (value.scrollWidth <= availableWidth && value.scrollHeight <= availableHeight) low = middle;
    else high = middle;
  }

  value.style.fontSize = `${Math.max(ZONE_DETAIL_VALUE_MIN_PX, Math.floor(low * 10) / 10)}px`;
}

function zoneDetailFitValues(root = document.getElementById("zoneDetailBody")) {
  if (!root) return;
  if (zoneDetailFitFrame !== null) window.cancelAnimationFrame(zoneDetailFitFrame);
  zoneDetailFitFrame = window.requestAnimationFrame(() => {
    zoneDetailFitFrame = null;
    root.querySelectorAll('strong[data-autofit="true"]').forEach(zoneDetailFitValue);
  });
}

function renderZoneDetailGroup(group) {
  const section = document.createElement("section");
  section.className = "v2-zone-detail-group";

  const header = document.createElement("header");
  header.textContent = group.title;
  section.appendChild(header);

  const items = document.createElement("div");
  items.className = "v2-zone-detail-items";

  group.items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "v2-zone-detail-item";
    const kinds = String(item.kind || "").split(/\s+/).filter(Boolean);
    if (kinds.includes("text")) row.classList.add("is-text");
    if (kinds.includes("good")) row.classList.add("is-good");
    if (kinds.includes("warn")) row.classList.add("is-warn");
    if (kinds.includes("bad")) row.classList.add("is-bad");

    const label = document.createElement("span");
    label.textContent = item.label;

    const valueWrap = document.createElement("div");
    valueWrap.className = "v2-zone-detail-value-wrap";

    const value = document.createElement("strong");
    value.dataset.autofit = "true";
    value.textContent = item.value;
    if (item.unit) {
      const unit = document.createElement("small");
      unit.textContent = item.unit;
      value.appendChild(unit);
    }

    valueWrap.appendChild(value);
    row.append(label, valueWrap);
    items.appendChild(row);
  });

  section.appendChild(items);
  return section;
}

function zoneDetailSnapshotStatus(zoneKey, state, node) {
  if (!state || !node) return { label: "BRAK DANYCH", css: "status-unknown" };
  if (!zoneDetailNodeCurrent(node)) {
    return { label: node.online === true ? "DANE NIEAKTUALNE" : "CZUJNIK OFFLINE", css: "status-warn" };
  }
  if (zoneKey === "zone2" && !zoneDetailAeroUsable(state.aero_bus)) {
    return { label: "AERO NIEDOSTĘPNY", css: "status-warn" };
  }
  return { label: "DANE BIEŻĄCE", css: "status-good" };
}

function renderZoneDetail(zoneKey, state) {
  const body = document.getElementById("zoneDetailBody");
  const status = document.getElementById("zoneDetailStatus");
  const updated = document.getElementById("zoneDetailUpdated");
  if (!body || !status || !updated) return;

  const config = zoneDetailConfig[zoneKey];
  const node = zoneDetailNodeByAddress(state && state.sensor_bus, config.sensor_address);
  const groups = zoneKey === "zone1"
    ? zoneDetailZone1Groups(state, node)
    : zoneDetailZone2Groups(state, node);

  body.replaceChildren(...groups.map(renderZoneDetailGroup));
  zoneDetailFitValues(body);

  const snapshotStatus = zoneDetailSnapshotStatus(zoneKey, state, node);
  status.className = `status-chip ${snapshotStatus.css}`;
  status.textContent = snapshotStatus.label;
  updated.textContent = new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date());
}

function renderZoneDetailFailure(error) {
  const body = document.getElementById("zoneDetailBody");
  const status = document.getElementById("zoneDetailStatus");
  if (status) {
    status.className = "status-chip status-bad";
    status.textContent = "BŁĄD ODCZYTU";
  }
  if (body) {
    body.replaceChildren();
    const message = document.createElement("div");
    message.className = "v2-zone-detail-empty";
    message.textContent = `Nie udało się odczytać bieżących danych: ${String(error && error.message ? error.message : error)}`;
    body.appendChild(message);
  }
}

async function zoneDetailGet(path) {
  const response = await fetch(path, { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok || payload.ok !== true) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function loadZoneDetailConfig() {
  if (zoneDetailConfigLoaded) return;
  const payload = await zoneDetailGet("/api/v1/config");
  if (payload.config && payload.config.zone1 && payload.config.zone2) {
    zoneDetailConfig = payload.config;
  }
  zoneDetailConfigLoaded = true;
}

async function refreshZoneDetail() {
  if (!zoneDetailActiveKey || zoneDetailRefreshBusy) return;
  zoneDetailRefreshBusy = true;
  try {
    await loadZoneDetailConfig();
    const payload = await zoneDetailGet("/api/v1/state");
    if (!zoneDetailActiveKey) return;
    renderZoneDetail(zoneDetailActiveKey, payload.state);
  } catch (error) {
    if (zoneDetailActiveKey) renderZoneDetailFailure(error);
  } finally {
    zoneDetailRefreshBusy = false;
  }
}

function startZoneDetailPolling() {
  stopZoneDetailPolling();
  zoneDetailPollTimer = window.setInterval(refreshZoneDetail, ZONE_DETAIL_POLL_MS);
}

function stopZoneDetailPolling() {
  if (zoneDetailPollTimer !== null) {
    window.clearInterval(zoneDetailPollTimer);
    zoneDetailPollTimer = null;
  }
}

function finalizeZoneDetailOpen(serial) {
  if (serial !== zoneDetailTransitionSerial) return;
  const overlay = document.getElementById("zoneDetailModal");
  if (!overlay || overlay.hidden) return;
  overlay.classList.remove("is-transitioning");
  cancelZoneDetailAnimations(overlay);
  zoneDetailFitValues();

  const close = document.getElementById("zoneDetailClose");
  if (close) close.focus({ preventScroll: true });
}

function finalizeZoneDetailClose(serial) {
  if (serial !== zoneDetailTransitionSerial) return;
  const overlay = document.getElementById("zoneDetailModal");
  if (!overlay) return;

  cancelZoneDetailAnimations(overlay);
  overlay.classList.remove("is-transitioning", "zone-one", "zone-two");
  overlay.hidden = true;
  document.body.classList.remove("v2-zone-detail-open");
  stopZoneDetailPolling();

  const source = zoneDetailSourceCard;
  zoneDetailActiveKey = null;
  zoneDetailSourceCard = null;
  if (source) {
    source.setAttribute("aria-expanded", "false");
    source.focus({ preventScroll: true });
  }
}

function openZoneDetailModal(zoneKey, sourceCard) {
  if (zoneKey !== "zone1" && zoneKey !== "zone2") return;
  const overlay = ensureZoneDetailModal();
  const detailCard = overlay.querySelector(".v2-zone-detail-card");
  const detailHeader = overlay.querySelector(".v2-zone-detail-header");
  const detailBody = overlay.querySelector(".v2-zone-detail-body");
  const title = document.getElementById("zoneDetailTitle");
  const kicker = document.getElementById("zoneDetailKicker");
  const status = document.getElementById("zoneDetailStatus");
  const updated = document.getElementById("zoneDetailUpdated");

  zoneDetailActiveKey = zoneKey;
  zoneDetailSourceCard = sourceCard;
  const serial = ++zoneDetailTransitionSerial;
  cancelZoneDetailAnimations(overlay);
  overlay.hidden = false;
  overlay.classList.remove("zone-one", "zone-two");
  overlay.classList.add(zoneKey === "zone1" ? "zone-one" : "zone-two", "is-transitioning");
  document.body.classList.add("v2-zone-detail-open");
  sourceCard.setAttribute("aria-expanded", "true");

  const config = zoneDetailConfig[zoneKey];
  if (kicker) kicker.textContent = zoneKey === "zone1" ? "STREFA 1 · DANE BIEŻĄCE" : "STREFA 2 · DANE BIEŻĄCE";
  if (title) title.textContent = config.name;
  if (status) {
    status.className = "status-chip status-unknown";
    status.textContent = "ŁADOWANIE";
  }
  if (updated) updated.textContent = "—";
  if (detailBody) detailBody.innerHTML = '<div class="v2-zone-detail-empty">Ładowanie bieżących danych…</div>';

  refreshZoneDetail();
  startZoneDetailPolling();

  if (!detailCard || !zoneDetailCanAnimate(detailCard)) {
    finalizeZoneDetailOpen(serial);
    return;
  }

  const fromTransform = zoneDetailTransformFromCard(sourceCard, detailCard);
  overlay.animate(
    [{ opacity: 0 }, { opacity: 1 }],
    { duration: ZONE_DETAIL_OPEN_MS, easing: "linear", fill: "both" }
  );
  if (detailHeader) {
    detailHeader.animate(
      [{ opacity: 0 }, { opacity: 0, offset: 0.36 }, { opacity: 1 }],
      { duration: ZONE_DETAIL_OPEN_MS, easing: "ease-out", fill: "both" }
    );
  }
  if (detailBody) {
    detailBody.animate(
      [{ opacity: 0 }, { opacity: 0, offset: 0.44 }, { opacity: 1 }],
      { duration: ZONE_DETAIL_OPEN_MS, easing: "ease-out", fill: "both" }
    );
  }

  const morph = detailCard.animate(
    [
      { transform: fromTransform, borderRadius: "14px", offset: 0 },
      { transform: "translate(0px,0px) scale(1.012,1.012)", borderRadius: "18px", offset: 0.86 },
      { transform: "translate(0px,0px) scale(1,1)", borderRadius: "18px", offset: 1 },
    ],
    {
      duration: ZONE_DETAIL_OPEN_MS,
      easing: "cubic-bezier(.18,.78,.18,1)",
      fill: "both",
    }
  );
  morph.addEventListener("finish", () => finalizeZoneDetailOpen(serial), { once: true });
}

function closeZoneDetailModal() {
  const overlay = document.getElementById("zoneDetailModal");
  if (!overlay || overlay.hidden) return;

  const sourceCard = zoneDetailSourceCard;
  const detailCard = overlay.querySelector(".v2-zone-detail-card");
  const detailHeader = overlay.querySelector(".v2-zone-detail-header");
  const detailBody = overlay.querySelector(".v2-zone-detail-body");
  const serial = ++zoneDetailTransitionSerial;

  stopZoneDetailPolling();
  cancelZoneDetailAnimations(overlay);
  overlay.classList.add("is-transitioning");

  if (!sourceCard || !detailCard || !zoneDetailCanAnimate(detailCard)) {
    finalizeZoneDetailClose(serial);
    return;
  }

  const toTransform = zoneDetailTransformFromCard(sourceCard, detailCard);
  overlay.animate(
    [{ opacity: 1 }, { opacity: 0 }],
    { duration: ZONE_DETAIL_CLOSE_MS, easing: "linear", fill: "both" }
  );
  if (detailHeader) {
    detailHeader.animate(
      [{ opacity: 1 }, { opacity: 0 }],
      { duration: Math.round(ZONE_DETAIL_CLOSE_MS * 0.55), easing: "ease-in", fill: "both" }
    );
  }
  if (detailBody) {
    detailBody.animate(
      [{ opacity: 1 }, { opacity: 0 }],
      { duration: Math.round(ZONE_DETAIL_CLOSE_MS * 0.5), easing: "ease-in", fill: "both" }
    );
  }

  const morph = detailCard.animate(
    [
      { transform: "translate(0px,0px) scale(1,1)", borderRadius: "18px" },
      { transform: toTransform, borderRadius: "14px" },
    ],
    {
      duration: ZONE_DETAIL_CLOSE_MS,
      easing: "cubic-bezier(.42,0,.72,.18)",
      fill: "both",
    }
  );
  morph.addEventListener("finish", () => finalizeZoneDetailClose(serial), { once: true });
}

function wireZoneDetailCard(card, zoneKey) {
  if (!card || card.dataset.zoneDetailWired === "true") return;
  card.dataset.zoneDetailWired = "true";
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute("aria-haspopup", "dialog");
  card.setAttribute("aria-controls", "zoneDetailModal");
  card.setAttribute("aria-expanded", "false");
  card.setAttribute("aria-label", zoneKey === "zone1" ? "Otwórz szczegóły strefy 1" : "Otwórz szczegóły strefy 2");

  card.addEventListener("click", (event) => {
    if (event.target.closest("a,button,input,select,textarea")) return;
    openZoneDetailModal(zoneKey, card);
  });
  card.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    openZoneDetailModal(zoneKey, card);
  });
}

function initializeZoneDetail() {
  ensureZoneDetailModal();
  wireZoneDetailCard(document.querySelector(".v2-zone-card.zone-one"), "zone1");
  wireZoneDetailCard(document.querySelector(".v2-zone-card.zone-two"), "zone2");
  loadZoneDetailConfig().catch(() => {});
}

window.addEventListener("resize", () => zoneDetailFitValues());
initializeZoneDetail();
