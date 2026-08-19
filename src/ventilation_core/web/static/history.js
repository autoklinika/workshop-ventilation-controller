"use strict";

/*
 * History H2 client.
 * Backend owns series catalog, resolution selection, stored values, rollups and gaps.
 * The browser only selects stable series IDs and renders returned points.
 */

const HISTORY_QUERY_TIMEOUT_MS = 10000;
const HISTORY_REFRESH_MS = 30000;
const HISTORY_MODAL_OPEN_MS = 280;
const HISTORY_MODAL_CLOSE_MS = 240;

const HISTORY_PRESETS = {
  zone1: [
    { id: "pm", label: "PYŁY PM", series: ["zone1.air.pm1_0", "zone1.air.pm2_5", "zone1.air.pm4_0", "zone1.air.pm10_0"] },
    { id: "gas", label: "VOC / NOx", series: ["zone1.air.voc_index", "zone1.air.nox_index"] },
    { id: "temperature", label: "TEMP. POMIESZCZENIA", series: ["zone1.air.temperature"] },
    { id: "humidity", label: "WILGOTNOŚĆ", series: ["zone1.air.humidity"] },
    { id: "rpm", label: "WENTYLATORY RPM", series: ["zone1.fans.supply.rpm", "zone1.fans.extract.rpm"] },
    { id: "setpoints", label: "STEROWANIE 0–10 V", series: ["zone1.fans.supply.setpoint_v", "zone1.fans.extract.setpoint_v"] },
    { id: "duct", label: "TEMP. KANAŁÓW", series: ["zone1.duct.supply.temperature", "zone1.duct.extract.temperature"] },
  ],
  zone2: [
    { id: "pm", label: "PYŁY PM", series: ["zone2.air.pm1_0", "zone2.air.pm2_5", "zone2.air.pm4_0", "zone2.air.pm10_0"] },
    { id: "gas", label: "VOC / NOx", series: ["zone2.air.voc_index", "zone2.air.nox_index"] },
    { id: "temperature", label: "TEMP. POMIESZCZENIA", series: ["zone2.air.temperature"] },
    { id: "humidity", label: "WILGOTNOŚĆ", series: ["zone2.air.humidity"] },
    { id: "aero-temp", label: "TEMP. AERO", series: ["zone2.aero.supply_temperature", "zone2.aero.extract_temperature", "zone2.aero.outdoor_temperature"] },
    { id: "aero-fans", label: "WENTYLATORY AERO", series: ["zone2.aero.fan1_percent", "zone2.aero.fan2_percent"] },
    { id: "aero-humidity", label: "WILGOTNOŚĆ AERO", series: ["zone2.aero.humidity"] },
  ],
};

const historyClient = {
  zone: "zone1",
  preset: "pm",
  range: "24h",
  catalog: null,
  status: null,
  payload: null,
  loading: false,
  initialized: false,
  requestSerial: 0,
  modalSerial: 0,
};

function ensureHistoryView() {
  let view = document.getElementById("historyView");
  if (view) return view;
  const host = document.getElementById("viewHost");
  if (!host) return null;

  view = document.createElement("section");
  view.id = "historyView";
  view.className = "v2-shell-view v2-history-view";
  view.dataset.view = "history";
  view.hidden = true;
  view.innerHTML = `
    <section class="v2-history-head">
      <div><h1>HISTORIA</h1><p>Zarejestrowane pomiary i parametry pracy systemu</p></div>
      <div class="v2-history-status"><span id="historyStorageState">CM5 · HISTORIA</span><strong id="historyStorageInfo">—</strong></div>
    </section>
    <section class="v2-history-controls" aria-label="Zakres historii">
      <div id="historyZoneButtons" class="v2-history-segment">
        <button class="v2-history-btn is-active" type="button" data-history-zone="zone1">STREFA 1</button>
        <button class="v2-history-btn" type="button" data-history-zone="zone2">STREFA 2</button>
      </div>
      <div id="historyRangeButtons" class="v2-history-ranges"></div>
    </section>
    <section id="historyMetricButtons" class="v2-history-metrics" aria-label="Grupa pomiarów"></section>
    <article id="historyChartCard" class="v2-history-chart-card" tabindex="0" role="button" aria-haspopup="dialog" aria-controls="historyChartModal" aria-label="Powiększ wykres historii">
      <header class="v2-history-chart-head">
        <div class="v2-history-chart-title"><span id="historyChartKicker">STREFA 1 · 24 GODZINY</span><h2 id="historyChartTitle">Pyły PM</h2></div>
        <div class="v2-history-chart-meta"><span id="historyResolutionChip" class="v2-history-chip">—</span><span id="historyPointsChip" class="v2-history-chip">—</span></div>
      </header>
      <div class="v2-history-stage">
        <svg id="historyChartSvg" class="v2-history-svg" role="img" aria-label="Wykres historii"></svg>
        <div id="historyChartEmpty" class="v2-history-empty" hidden>Brak danych dla wybranego zakresu.</div>
        <div id="historyChartLoading" class="v2-history-loading" hidden>ŁADOWANIE…</div>
      </div>
      <footer class="v2-history-chart-foot"><div id="historyLegend" class="v2-history-legend"></div><div id="historySummary" class="v2-history-summary">—</div></footer>
    </article>`;
  host.appendChild(view);
  return view;
}

function historyNavLink() {
  return [...document.querySelectorAll(".v2-nav")].find((item) => item.textContent.trim() === "HISTORIA") || null;
}

function historySetView(push = false) {
  const view = ensureHistoryView();
  if (!view) return;
  document.querySelectorAll(".v2-shell-view").forEach((item) => { item.hidden = item !== view; });
  document.querySelectorAll(".v2-nav[data-route]").forEach((item) => {
    const active = item.dataset.route === "/history";
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  if (push && window.location.pathname !== "/history") history.pushState({ v2Route: "/history" }, "", "/history");
  window.scrollTo(0, 0);
  historyEnsureLoaded();
}

function historyHideView() {
  const view = document.getElementById("historyView");
  if (view) view.hidden = true;
  closeHistoryChartModal(true);
}

function wireHistoryNavigation() {
  const link = historyNavLink();
  if (!link) return;
  link.classList.remove("disabled");
  link.removeAttribute("aria-disabled");
  link.href = "/history";
  link.dataset.route = "/history";
  link.addEventListener("click", (event) => {
    event.preventDefault();
    historySetView(true);
  });

  document.addEventListener("click", (event) => {
    const other = event.target.closest('a[href="/"],a[href="/control"],a[href="/alerts"],a[href="/settings"]');
    if (other) historyHideView();
  });

  window.addEventListener("popstate", () => {
    if (window.location.pathname.startsWith("/history")) historySetView(false);
    else historyHideView();
  });

  if (window.location.pathname.startsWith("/history")) historySetView(false);
}

async function historyRequest(path, options = {}) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), HISTORY_QUERY_TIMEOUT_MS);
  try {
    const response = await fetch(path, { cache: "no-store", signal: controller.signal, ...options });
    const payload = await response.json();
    if (!response.ok || payload.ok !== true) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  } finally {
    window.clearTimeout(timer);
  }
}

function historyPost(path, body) {
  return historyRequest(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function historyFormatBytes(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toLocaleString("pl-PL", { maximumFractionDigits: 0 })} MB`;
}

function historyRenderStatus() {
  const state = document.getElementById("historyStorageState");
  const info = document.getElementById("historyStorageInfo");
  const status = historyClient.status;
  if (!state || !info) return;
  if (!status || status.available !== true) {
    state.textContent = "CM5 · HISTORIA NIEDOSTĘPNA";
    info.textContent = "—";
    return;
  }
  state.textContent = "CM5 · SQLITE";
  info.textContent = `${Number(status.total_samples || 0).toLocaleString("pl-PL")} próbek · ${historyFormatBytes(status.database_bytes)}`;
}

function historyRangeLabel(rangeId) {
  const map = { "1h": "1 GODZINA", "24h": "24 GODZINY", "7d": "7 DNI" };
  return map[rangeId] || String(rangeId || "").toUpperCase();
}

function historyRenderRanges() {
  const host = document.getElementById("historyRangeButtons");
  if (!host || !historyClient.catalog) return;
  host.replaceChildren();
  (historyClient.catalog.ranges || []).forEach((range) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `v2-history-btn${range.id === historyClient.range ? " is-active" : ""}`;
    button.dataset.historyRange = range.id;
    button.textContent = historyRangeLabel(range.id);
    button.addEventListener("click", () => {
      if (historyClient.range === range.id) return;
      historyClient.range = range.id;
      historyRenderRanges();
      historyLoadChart();
    });
    host.appendChild(button);
  });
}

function historyPresetList() {
  return HISTORY_PRESETS[historyClient.zone] || [];
}

function historyCurrentPreset() {
  return historyPresetList().find((item) => item.id === historyClient.preset) || historyPresetList()[0] || null;
}

function historyRenderZoneButtons() {
  document.querySelectorAll("[data-history-zone]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.historyZone === historyClient.zone);
  });
}

function historyRenderMetricButtons() {
  const host = document.getElementById("historyMetricButtons");
  if (!host) return;
  host.replaceChildren();
  historyPresetList().forEach((preset) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `v2-history-metric${preset.id === historyClient.preset ? " is-active" : ""}`;
    button.dataset.historyPreset = preset.id;
    const span = document.createElement("span");
    span.textContent = preset.label;
    button.appendChild(span);
    button.addEventListener("click", () => {
      if (historyClient.preset === preset.id) return;
      historyClient.preset = preset.id;
      historyRenderMetricButtons();
      historyLoadChart();
    });
    host.appendChild(button);
  });
}

function wireHistoryControls() {
  document.querySelectorAll("[data-history-zone]").forEach((button) => {
    if (button.dataset.historyWired === "true") return;
    button.dataset.historyWired = "true";
    button.addEventListener("click", () => {
      const zone = button.dataset.historyZone;
      if (!HISTORY_PRESETS[zone] || zone === historyClient.zone) return;
      historyClient.zone = zone;
      historyClient.preset = HISTORY_PRESETS[zone][0].id;
      historyRenderZoneButtons();
      historyRenderMetricButtons();
      historyLoadChart();
    });
  });
}

function historyResolutionText(resolution) {
  return ({ raw: "RAW · 5 s", "1m": "1 MIN", "15m": "15 MIN" })[resolution] || String(resolution || "—").toUpperCase();
}

function historySeriesValue(point, resolution) {
  const value = resolution === "raw" ? point.value : point.avg;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function historyShortLabel(label) {
  const text = String(label || "—");
  const parts = text.split("·");
  return parts[parts.length - 1].trim();
}

function historyFormatValue(value, digits) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const d = Number.isInteger(digits) ? digits : 1;
  return value.toLocaleString("pl-PL", { minimumFractionDigits: d, maximumFractionDigits: d });
}

function historySvgElement(name, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

function historyTimeLabel(timestamp, rangeId) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  if (rangeId === "7d") {
    return new Intl.DateTimeFormat("pl-PL", { day: "2-digit", month: "2-digit", hour: "2-digit" }).format(date);
  }
  return new Intl.DateTimeFormat("pl-PL", { hour: "2-digit", minute: "2-digit" }).format(date);
}

function historyRenderSvg(svg, payload) {
  if (!svg) return false;
  svg.replaceChildren();
  if (!payload || !Array.isArray(payload.series) || payload.series.length === 0) return false;

  const width = Math.max(640, Math.round(svg.clientWidth || 1000));
  const height = Math.max(260, Math.round(svg.clientHeight || 360));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const margin = { left: 62, right: 20, top: 18, bottom: 34 };
  const plotWidth = Math.max(1, width - margin.left - margin.right);
  const plotHeight = Math.max(1, height - margin.top - margin.bottom);
  const startMs = new Date(payload.range && payload.range.start).getTime();
  const endMs = new Date(payload.range && payload.range.end).getTime();
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return false;

  const values = [];
  payload.series.forEach((series) => {
    (series.points || []).forEach((point) => {
      const value = historySeriesValue(point, payload.resolution);
      if (value !== null) values.push(value);
    });
  });
  if (values.length === 0) return false;

  let yMin = Math.min(...values);
  let yMax = Math.max(...values);
  if (yMin === yMax) {
    const delta = Math.max(1, Math.abs(yMin) * 0.05);
    yMin -= delta;
    yMax += delta;
  } else {
    const pad = (yMax - yMin) * 0.07;
    yMin -= pad;
    yMax += pad;
  }

  const xFor = (t) => margin.left + ((t - startMs) / (endMs - startMs)) * plotWidth;
  const yFor = (v) => margin.top + (1 - (v - yMin) / (yMax - yMin)) * plotHeight;

  for (let i = 0; i <= 4; i += 1) {
    const ratio = i / 4;
    const y = margin.top + ratio * plotHeight;
    svg.appendChild(historySvgElement("line", { x1: margin.left, y1: y, x2: width - margin.right, y2: y, class: "v2-history-grid-line" }));
    const label = historySvgElement("text", { x: margin.left - 10, y: y + 4, "text-anchor": "end", class: "v2-history-axis-label" });
    label.textContent = historyFormatValue(yMax - ratio * (yMax - yMin), payload.series[0].digits);
    svg.appendChild(label);
  }

  svg.appendChild(historySvgElement("line", { x1: margin.left, y1: margin.top + plotHeight, x2: width - margin.right, y2: margin.top + plotHeight, class: "v2-history-axis-line" }));

  for (let i = 0; i <= 4; i += 1) {
    const ratio = i / 4;
    const x = margin.left + ratio * plotWidth;
    const timestamp = startMs + ratio * (endMs - startMs);
    const label = historySvgElement("text", { x, y: height - 9, "text-anchor": i === 0 ? "start" : i === 4 ? "end" : "middle", class: "v2-history-axis-label" });
    label.textContent = historyTimeLabel(timestamp, payload.range && payload.range.preset);
    svg.appendChild(label);
  }

  payload.series.forEach((series, index) => {
    let path = "";
    let drawing = false;
    (series.points || []).forEach((point) => {
      const value = historySeriesValue(point, payload.resolution);
      const time = new Date(point.t).getTime();
      if (value === null || !Number.isFinite(time)) {
        drawing = false;
        return;
      }
      if (point.gap_before === true) drawing = false;
      const x = xFor(time);
      const y = yFor(value);
      path += `${drawing ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)} `;
      drawing = true;
    });
    if (!path) return;
    svg.appendChild(historySvgElement("path", { d: path.trim(), class: `v2-history-series-line s${index % 4}` }));
  });
  return true;
}

function historyRenderLegend(payload, host) {
  if (!host) return;
  host.replaceChildren();
  if (!payload || !Array.isArray(payload.series)) return;
  payload.series.forEach((series, index) => {
    const item = document.createElement("div");
    item.className = "v2-history-legend-item";
    const mark = document.createElement("i");
    mark.className = `s${index % 4}`;
    const label = document.createElement("span");
    label.textContent = `${historyShortLabel(series.label)}${series.unit ? ` [${series.unit}]` : ""}`;
    item.append(mark, label);
    host.appendChild(item);
  });
}

function historyRenderPayload(payload) {
  historyClient.payload = payload;
  const preset = historyCurrentPreset();
  const title = document.getElementById("historyChartTitle");
  const kicker = document.getElementById("historyChartKicker");
  const resolution = document.getElementById("historyResolutionChip");
  const points = document.getElementById("historyPointsChip");
  const summary = document.getElementById("historySummary");
  const empty = document.getElementById("historyChartEmpty");
  const svg = document.getElementById("historyChartSvg");

  if (title) title.textContent = preset ? preset.label : "Historia";
  if (kicker) kicker.textContent = `${historyClient.zone === "zone1" ? "STREFA 1" : "STREFA 2"} · ${historyRangeLabel(historyClient.range)}`;
  if (resolution) resolution.textContent = historyResolutionText(payload.resolution);

  const firstSeries = Array.isArray(payload.series) && payload.series.length ? payload.series[0] : null;
  if (points) points.textContent = firstSeries ? `${Number(firstSeries.point_count || 0).toLocaleString("pl-PL")} PKT` : "0 PKT";
  if (summary) {
    const missing = firstSeries ? Number(firstSeries.missing_points || 0) : 0;
    const gaps = firstSeries ? Number(firstSeries.gap_count || 0) : 0;
    summary.innerHTML = `<strong>Braki:</strong> ${missing.toLocaleString("pl-PL")} · <strong>Przerwy:</strong> ${gaps.toLocaleString("pl-PL")}`;
  }

  const rendered = historyRenderSvg(svg, payload);
  if (empty) {
    empty.hidden = rendered;
    empty.textContent = rendered ? "" : "Brak zarejestrowanych danych dla wybranego zakresu.";
  }
  historyRenderLegend(payload, document.getElementById("historyLegend"));

  const modal = document.getElementById("historyChartModal");
  if (modal && !modal.hidden) syncHistoryChartModal();
}

function historyRenderFailure(error) {
  historyClient.payload = null;
  const empty = document.getElementById("historyChartEmpty");
  const svg = document.getElementById("historyChartSvg");
  if (svg) svg.replaceChildren();
  if (empty) {
    empty.hidden = false;
    empty.textContent = `Nie udało się pobrać historii: ${String(error && error.message ? error.message : error)}`;
  }
  const points = document.getElementById("historyPointsChip");
  const resolution = document.getElementById("historyResolutionChip");
  const summary = document.getElementById("historySummary");
  if (points) points.textContent = "—";
  if (resolution) resolution.textContent = "BŁĄD";
  if (summary) summary.textContent = "—";
  historyRenderLegend(null, document.getElementById("historyLegend"));
}

async function historyLoadChart() {
  const preset = historyCurrentPreset();
  if (!preset || !historyClient.catalog) return;
  const loading = document.getElementById("historyChartLoading");
  const serial = ++historyClient.requestSerial;
  historyClient.loading = true;
  if (loading) loading.hidden = false;
  try {
    const response = await historyPost("/api/v1/history/series/query", {
      range: historyClient.range,
      resolution: "auto",
      series: preset.series,
    });
    if (serial !== historyClient.requestSerial) return;
    historyRenderPayload(response.history);
  } catch (error) {
    if (serial === historyClient.requestSerial) historyRenderFailure(error);
  } finally {
    if (serial === historyClient.requestSerial) {
      historyClient.loading = false;
      if (loading) loading.hidden = true;
    }
  }
}

async function historyEnsureLoaded() {
  if (!historyClient.initialized) {
    historyClient.initialized = true;
    try {
      const [catalogResponse, statusResponse] = await Promise.all([
        historyRequest("/api/v1/history/series"),
        historyRequest("/api/v1/history/status"),
      ]);
      historyClient.catalog = catalogResponse.history;
      historyClient.status = statusResponse.history;
      historyRenderStatus();
      historyRenderRanges();
      historyRenderZoneButtons();
      historyRenderMetricButtons();
      wireHistoryControls();
    } catch (error) {
      historyClient.initialized = false;
      historyRenderFailure(error);
      return;
    }
  }
  historyLoadChart();
}

function ensureHistoryChartModal() {
  let overlay = document.getElementById("historyChartModal");
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.id = "historyChartModal";
  overlay.className = "v2-history-detail";
  overlay.hidden = true;
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "historyModalTitle");
  overlay.innerHTML = `
    <section class="v2-history-detail-card">
      <header class="v2-history-detail-head"><div><span id="historyModalKicker">HISTORIA</span><h2 id="historyModalTitle">Wykres</h2></div><button id="historyModalClose" class="v2-history-detail-close" type="button">ZAMKNIJ</button></header>
      <div class="v2-history-detail-stage"><svg id="historyModalSvg" class="v2-history-svg" role="img" aria-label="Powiększony wykres historii"></svg><div id="historyModalEmpty" class="v2-history-empty" hidden>Brak danych.</div></div>
      <footer class="v2-history-detail-foot"><div id="historyModalLegend" class="v2-history-legend"></div><div id="historyModalSummary" class="v2-history-summary">—</div></footer>
    </section>`;
  document.body.appendChild(overlay);
  document.getElementById("historyModalClose").addEventListener("click", () => closeHistoryChartModal(false));
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || overlay.hidden) return;
    const alert = document.getElementById("globalSystemAlert");
    if (alert && !alert.hidden) return;
    closeHistoryChartModal(false);
  });
  return overlay;
}

function syncHistoryChartModal() {
  const overlay = ensureHistoryChartModal();
  if (overlay.hidden) return;
  const title = document.getElementById("historyModalTitle");
  const kicker = document.getElementById("historyModalKicker");
  const summary = document.getElementById("historyModalSummary");
  const sourceTitle = document.getElementById("historyChartTitle");
  const sourceKicker = document.getElementById("historyChartKicker");
  const sourceSummary = document.getElementById("historySummary");
  if (title && sourceTitle) title.textContent = sourceTitle.textContent;
  if (kicker && sourceKicker) kicker.textContent = sourceKicker.textContent;
  if (summary && sourceSummary) summary.innerHTML = sourceSummary.innerHTML;
  historyRenderLegend(historyClient.payload, document.getElementById("historyModalLegend"));
  const rendered = historyRenderSvg(document.getElementById("historyModalSvg"), historyClient.payload);
  const empty = document.getElementById("historyModalEmpty");
  if (empty) empty.hidden = rendered;
}

function historyReducedMotion() {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function historyCanAnimate(element) {
  return !historyReducedMotion() && element && typeof element.animate === "function";
}

function historyCancelAnimations(overlay) {
  if (!overlay || typeof overlay.getAnimations !== "function") return;
  overlay.getAnimations({ subtree: true }).forEach((animation) => animation.cancel());
}

function historyFlight(sourceCard, targetCard) {
  const source = sourceCard.getBoundingClientRect();
  const target = targetCard.getBoundingClientRect();
  const sourceCenterX = source.left + source.width / 2;
  const sourceCenterY = source.top + source.height / 2;
  const targetCenterX = target.left + target.width / 2;
  const targetCenterY = target.top + target.height / 2;
  const scaleX = Math.max(0.001, source.width / Math.max(1, target.width));
  const scaleY = Math.max(0.001, source.height / Math.max(1, target.height));
  const x = sourceCenterX - targetCenterX;
  const y = sourceCenterY - targetCenterY;
  return { x, y, scaleX, scaleY, transform: `translate(${x}px, ${y}px) scale(${scaleX}, ${scaleY})` };
}

function historyTravel(flight, remaining, boost = 0) {
  const x = flight.x * remaining;
  const y = flight.y * remaining;
  const sx = 1 + (flight.scaleX - 1) * remaining + boost;
  const sy = 1 + (flight.scaleY - 1) * remaining + boost;
  return `translate(${x}px, ${y}px) scale(${sx}, ${sy})`;
}

function openHistoryChartModal() {
  if (!historyClient.payload) return;
  const overlay = ensureHistoryChartModal();
  const source = document.getElementById("historyChartCard");
  const card = overlay.querySelector(".v2-history-detail-card");
  const header = overlay.querySelector(".v2-history-detail-head");
  const stage = overlay.querySelector(".v2-history-detail-stage");
  const serial = ++historyClient.modalSerial;
  historyCancelAnimations(overlay);
  overlay.hidden = false;
  overlay.classList.add("is-transitioning");
  document.body.classList.add("v2-history-detail-open");
  syncHistoryChartModal();

  const finish = () => {
    if (serial !== historyClient.modalSerial) return;
    historyCancelAnimations(overlay);
    overlay.classList.remove("is-transitioning");
    const close = document.getElementById("historyModalClose");
    if (close) close.focus({ preventScroll: true });
  };
  if (!source || !card || !historyCanAnimate(card)) { finish(); return; }

  const flight = historyFlight(source, card);
  overlay.animate([{ opacity: 0 }, { opacity: .92, offset: .55 }, { opacity: 1 }], { duration: HISTORY_MODAL_OPEN_MS, easing: "linear", fill: "both" });
  if (header) header.animate([{ opacity: 0 }, { opacity: 0, offset: .5 }, { opacity: 1 }], { duration: HISTORY_MODAL_OPEN_MS, easing: "ease-out", fill: "both" });
  if (stage) stage.animate([{ opacity: 0 }, { opacity: 0, offset: .52 }, { opacity: 1 }], { duration: HISTORY_MODAL_OPEN_MS, easing: "ease-out", fill: "both" });
  const animation = card.animate([
    { transform: flight.transform, borderRadius: "14px", offset: 0 },
    { transform: historyTravel(flight, .08, .018), borderRadius: "19px", offset: .78 },
    { transform: "translate(0px, 0px) scale(1, 1)", borderRadius: "18px", offset: 1 },
  ], { duration: HISTORY_MODAL_OPEN_MS, easing: "cubic-bezier(.18,.84,.24,1)", fill: "both" });
  animation.addEventListener("finish", finish, { once: true });
}

function closeHistoryChartModal(immediate = false) {
  const overlay = document.getElementById("historyChartModal");
  if (!overlay || overlay.hidden) return;
  const source = document.getElementById("historyChartCard");
  const card = overlay.querySelector(".v2-history-detail-card");
  const header = overlay.querySelector(".v2-history-detail-head");
  const stage = overlay.querySelector(".v2-history-detail-stage");
  const serial = ++historyClient.modalSerial;

  const finish = () => {
    if (serial !== historyClient.modalSerial) return;
    historyCancelAnimations(overlay);
    overlay.classList.remove("is-transitioning");
    overlay.hidden = true;
    document.body.classList.remove("v2-history-detail-open");
    if (source && !immediate) source.focus({ preventScroll: true });
  };
  if (immediate || !source || !card || !historyCanAnimate(card)) { finish(); return; }

  historyCancelAnimations(overlay);
  overlay.classList.add("is-transitioning");
  const flight = historyFlight(source, card);
  overlay.animate([{ opacity: 1 }, { opacity: 1, offset: .3 }, { opacity: 0 }], { duration: HISTORY_MODAL_CLOSE_MS, easing: "linear", fill: "both" });
  if (header) header.animate([{ opacity: 1 }, { opacity: 0 }], { duration: Math.round(HISTORY_MODAL_CLOSE_MS * .48), easing: "ease-in", fill: "both" });
  if (stage) stage.animate([{ opacity: 1 }, { opacity: 0 }], { duration: Math.round(HISTORY_MODAL_CLOSE_MS * .42), easing: "ease-in", fill: "both" });
  const animation = card.animate([
    { transform: "translate(0px, 0px) scale(1, 1)", borderRadius: "18px", offset: 0 },
    { transform: historyTravel(flight, .14, -.008), borderRadius: "17px", offset: .28 },
    { transform: flight.transform, borderRadius: "14px", offset: 1 },
  ], { duration: HISTORY_MODAL_CLOSE_MS, easing: "cubic-bezier(.42,0,.78,.22)", fill: "both" });
  animation.addEventListener("finish", finish, { once: true });
}

function wireHistoryChartInteraction() {
  const card = document.getElementById("historyChartCard");
  if (!card || card.dataset.historyModalWired === "true") return;
  card.dataset.historyModalWired = "true";
  card.addEventListener("click", () => openHistoryChartModal());
  card.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    openHistoryChartModal();
  });
}

function historyRouteVisible() {
  const view = document.getElementById("historyView");
  return Boolean(view && !view.hidden && window.location.pathname.startsWith("/history"));
}

function historyRefreshVisible() {
  if (!historyRouteVisible() || historyClient.loading || !historyClient.initialized) return;
  historyLoadChart();
}

ensureHistoryView();
wireHistoryNavigation();
wireHistoryControls();
wireHistoryChartInteraction();
ensureHistoryChartModal();
window.setInterval(historyRefreshVisible, HISTORY_REFRESH_MS);
