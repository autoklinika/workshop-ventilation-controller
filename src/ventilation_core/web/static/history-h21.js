"use strict";

/*
 * History H2.1 presentation refinements.
 * No aggregation, interpolation, classification or trend logic lives here.
 * This module only renders backend-provided points and lets the operator inspect
 * the nearest backend-provided timestamp/value on mouse or touch.
 */

const HISTORY_H21_SPLIT_SERIES = [".voc_index", ".nox_index"];
const HISTORY_H21_TOUCH_DRAG_PX = 8;
let historyH21CompactDragged = false;

function historyH21IsGasPayload(payload) {
  if (!payload || !Array.isArray(payload.series) || payload.series.length !== 2) return false;
  return HISTORY_H21_SPLIT_SERIES.every((suffix) =>
    payload.series.some((series) => String(series && series.id || "").endsWith(suffix))
  );
}

function historyH21SeriesValues(series, resolution) {
  const values = [];
  (series && Array.isArray(series.points) ? series.points : []).forEach((point) => {
    const value = historySeriesValue(point, resolution);
    if (value !== null) values.push(value);
  });
  return values;
}

function historyH21Bounds(values) {
  if (!Array.isArray(values) || values.length === 0) return null;
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const allNonNegative = rawMin >= 0;
  let low;
  let high;

  if (rawMin === rawMax) {
    const delta = Math.max(1, Math.abs(rawMin) * 0.05);
    low = rawMin - delta;
    high = rawMax + delta;
  } else {
    const pad = (rawMax - rawMin) * 0.07;
    low = rawMin - pad;
    high = rawMax + pad;
  }

  if (allNonNegative) low = Math.max(0, low);
  if (!(high > low)) high = low + Math.max(1, Math.abs(low) * 0.05);
  return { low, high };
}

function historyH21BuildBands(payload, margin, plotHeight) {
  const split = historyH21IsGasPayload(payload);
  if (!split) {
    const values = [];
    payload.series.forEach((series) => values.push(...historyH21SeriesValues(series, payload.resolution)));
    const bounds = historyH21Bounds(values);
    return bounds ? [{
      seriesIndexes: payload.series.map((_series, index) => index),
      top: margin.top,
      height: plotHeight,
      bounds,
      label: null,
    }] : [];
  }

  const gap = Math.max(20, Math.round(plotHeight * 0.055));
  const bandHeight = Math.max(1, (plotHeight - gap) / 2);
  return payload.series.map((series, index) => {
    const bounds = historyH21Bounds(historyH21SeriesValues(series, payload.resolution));
    return bounds ? {
      seriesIndexes: [index],
      top: margin.top + index * (bandHeight + gap),
      height: bandHeight,
      bounds,
      label: historyShortLabel(series.label),
    } : null;
  }).filter(Boolean);
}

function historyH21BandForSeries(bands, seriesIndex) {
  return bands.find((band) => band.seriesIndexes.includes(seriesIndex)) || null;
}

function historyH21YFor(band, value) {
  const span = Math.max(Number.EPSILON, band.bounds.high - band.bounds.low);
  return band.top + (1 - (value - band.bounds.low) / span) * band.height;
}

function historyH21DrawBandGrid(svg, payload, band, width, margin, split) {
  const firstIndex = band.seriesIndexes[0];
  const series = payload.series[firstIndex];
  const lineCount = split ? 2 : 4;

  for (let i = 0; i <= lineCount; i += 1) {
    const ratio = i / lineCount;
    const y = band.top + ratio * band.height;
    svg.appendChild(historySvgElement("line", {
      x1: margin.left,
      y1: y,
      x2: width - margin.right,
      y2: y,
      class: "v2-history-grid-line",
    }));
    const label = historySvgElement("text", {
      x: margin.left - 10,
      y: y + 4,
      "text-anchor": "end",
      class: "v2-history-axis-label",
    });
    label.textContent = historyFormatValue(
      band.bounds.high - ratio * (band.bounds.high - band.bounds.low),
      series.digits,
    );
    svg.appendChild(label);
  }

  if (band.label) {
    const label = historySvgElement("text", {
      x: margin.left + 8,
      y: band.top + 16,
      class: `v2-history-band-label s${firstIndex % 4}`,
    });
    label.textContent = band.label;
    svg.appendChild(label);
  }
}

function historyH21CursorTimeLabel(timestamp, resolution) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  const options = resolution === "raw"
    ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }
    : { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" };
  return new Intl.DateTimeFormat("pl-PL", options).format(date);
}

function historyH21CursorKind(resolution) {
  if (resolution === "raw") return "RAW · POMIAR";
  if (resolution === "1m") return "1 MIN · ŚREDNIA";
  if (resolution === "15m") return "15 MIN · ŚREDNIA";
  return String(resolution || "—").toUpperCase();
}

function historyH21EnsureTooltip(svg) {
  const stage = svg && svg.parentElement;
  if (!stage) return null;
  let tooltip = stage.querySelector(":scope > .v2-history-cursor-tooltip");
  if (!tooltip) {
    tooltip = document.createElement("div");
    tooltip.className = "v2-history-cursor-tooltip";
    tooltip.hidden = true;
    stage.appendChild(tooltip);
  }
  return tooltip;
}

function historyH21BuildCursorData(payload) {
  const timestamps = new Set();
  const maps = payload.series.map((series) => {
    const map = new Map();
    (series.points || []).forEach((point) => {
      const time = new Date(point.t).getTime();
      if (!Number.isFinite(time)) return;
      timestamps.add(time);
      map.set(time, point);
    });
    return map;
  });
  return { timestamps: [...timestamps].sort((a, b) => a - b), maps };
}

function historyH21NearestTimestamp(timestamps, target) {
  if (!timestamps.length) return null;
  let low = 0;
  let high = timestamps.length - 1;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (timestamps[mid] < target) low = mid + 1;
    else high = mid;
  }
  if (low === 0) return timestamps[0];
  const before = timestamps[low - 1];
  const after = timestamps[low];
  return Math.abs(target - before) <= Math.abs(after - target) ? before : after;
}

function historyH21HideCursor(svg, keepTouch = false) {
  if (!svg) return;
  if (keepTouch && svg.dataset.historyPointerType === "touch") return;
  const line = svg.querySelector(".v2-history-cursor-line");
  if (line) line.setAttribute("visibility", "hidden");
  svg.querySelectorAll(".v2-history-cursor-dot").forEach((dot) => dot.setAttribute("visibility", "hidden"));
  const tooltip = historyH21EnsureTooltip(svg);
  if (tooltip) tooltip.hidden = true;
}

function historyH21ShowCursor(svg, payload, geometry, clientX, pointerType) {
  const rect = svg.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const xView = ((clientX - rect.left) / rect.width) * geometry.width;
  const clampedX = Math.max(geometry.margin.left, Math.min(geometry.width - geometry.margin.right, xView));
  const ratio = (clampedX - geometry.margin.left) / geometry.plotWidth;
  const targetTime = geometry.startMs + ratio * (geometry.endMs - geometry.startMs);
  const timestamp = historyH21NearestTimestamp(geometry.cursorData.timestamps, targetTime);
  if (timestamp === null) return;

  const selectedX = geometry.xFor(timestamp);
  const line = svg.querySelector(".v2-history-cursor-line");
  if (line) {
    line.setAttribute("x1", selectedX);
    line.setAttribute("x2", selectedX);
    line.setAttribute("visibility", "visible");
  }

  const rows = [];
  payload.series.forEach((series, index) => {
    const point = geometry.cursorData.maps[index].get(timestamp) || null;
    const value = point ? historySeriesValue(point, payload.resolution) : null;
    rows.push({ series, index, value });
    const dot = svg.querySelector(`.v2-history-cursor-dot[data-series-index="${index}"]`);
    if (!dot) return;
    if (value === null) {
      dot.setAttribute("visibility", "hidden");
      return;
    }
    const band = historyH21BandForSeries(geometry.bands, index);
    if (!band) return;
    dot.setAttribute("cx", selectedX);
    dot.setAttribute("cy", historyH21YFor(band, value));
    dot.setAttribute("visibility", "visible");
  });

  const tooltip = historyH21EnsureTooltip(svg);
  if (tooltip) {
    const rowHtml = rows.map(({ series, index, value }) => {
      const unit = series.unit ? ` ${series.unit}` : "";
      return `<div class="v2-history-cursor-row"><i class="s${index % 4}"></i><span>${historyShortLabel(series.label)}</span><strong>${historyFormatValue(value, series.digits)}${value === null ? "" : unit}</strong></div>`;
    }).join("");
    tooltip.innerHTML = `<div class="v2-history-cursor-time"><strong>${historyH21CursorTimeLabel(timestamp, payload.resolution)}</strong><span>${historyH21CursorKind(payload.resolution)}</span></div>${rowHtml}`;
    const stageRect = svg.parentElement.getBoundingClientRect();
    const xPx = rect.left - stageRect.left + (selectedX / geometry.width) * rect.width;
    tooltip.style.left = `${xPx}px`;
    tooltip.classList.toggle("is-left", selectedX > geometry.width * 0.62);
    tooltip.hidden = false;
  }

  svg.dataset.historyPointerType = pointerType || "mouse";
}

function historyH21AttachCursor(svg, payload, geometry) {
  const cursorLine = historySvgElement("line", {
    x1: geometry.margin.left,
    y1: geometry.margin.top,
    x2: geometry.margin.left,
    y2: geometry.margin.top + geometry.plotHeight,
    class: "v2-history-cursor-line",
    visibility: "hidden",
  });
  svg.appendChild(cursorLine);

  payload.series.forEach((_series, index) => {
    svg.appendChild(historySvgElement("circle", {
      cx: 0,
      cy: 0,
      r: 4,
      class: `v2-history-cursor-dot s${index % 4}`,
      "data-series-index": index,
      visibility: "hidden",
    }));
  });

  historyH21EnsureTooltip(svg);
  const isCompact = svg.id === "historyChartSvg";
  let startX = 0;
  let startY = 0;

  svg.onpointerdown = (event) => {
    startX = event.clientX;
    startY = event.clientY;
    if (event.pointerType === "touch" && typeof svg.setPointerCapture === "function") {
      try { svg.setPointerCapture(event.pointerId); } catch (_error) { /* presentation fallback */ }
    }
    historyH21ShowCursor(svg, payload, geometry, event.clientX, event.pointerType);
  };

  svg.onpointermove = (event) => {
    if (event.pointerType === "touch" && isCompact && event.buttons !== 0) {
      const distance = Math.hypot(event.clientX - startX, event.clientY - startY);
      if (distance >= HISTORY_H21_TOUCH_DRAG_PX) historyH21CompactDragged = true;
    }
    if (event.pointerType === "mouse" || event.buttons !== 0 || event.pointerType === "touch") {
      historyH21ShowCursor(svg, payload, geometry, event.clientX, event.pointerType);
    }
  };

  svg.onpointerleave = (event) => {
    if (event.pointerType !== "touch") historyH21HideCursor(svg);
  };
  svg.onpointercancel = () => historyH21HideCursor(svg);
}

function historyH21RenderSvg(svg, payload) {
  if (!svg) return false;
  const oldTooltip = svg.parentElement && svg.parentElement.querySelector(":scope > .v2-history-cursor-tooltip");
  if (oldTooltip) oldTooltip.remove();
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

  const bands = historyH21BuildBands(payload, margin, plotHeight);
  if (!bands.length) return false;
  const split = historyH21IsGasPayload(payload);
  bands.forEach((band) => historyH21DrawBandGrid(svg, payload, band, width, margin, split));

  const xFor = (time) => margin.left + ((time - startMs) / (endMs - startMs)) * plotWidth;
  svg.appendChild(historySvgElement("line", {
    x1: margin.left,
    y1: margin.top + plotHeight,
    x2: width - margin.right,
    y2: margin.top + plotHeight,
    class: "v2-history-axis-line",
  }));

  for (let i = 0; i <= 4; i += 1) {
    const ratio = i / 4;
    const x = margin.left + ratio * plotWidth;
    const timestamp = startMs + ratio * (endMs - startMs);
    const label = historySvgElement("text", {
      x,
      y: height - 9,
      "text-anchor": i === 0 ? "start" : i === 4 ? "end" : "middle",
      class: "v2-history-axis-label",
    });
    label.textContent = historyTimeLabel(timestamp, payload.range && payload.range.preset);
    svg.appendChild(label);
  }

  payload.series.forEach((series, index) => {
    const band = historyH21BandForSeries(bands, index);
    if (!band) return;
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
      const y = historyH21YFor(band, value);
      path += `${drawing ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)} `;
      drawing = true;
    });
    if (!path) return;
    svg.appendChild(historySvgElement("path", {
      d: path.trim(),
      class: `v2-history-series-line s${index % 4}`,
    }));
  });

  const geometry = {
    width,
    height,
    margin,
    plotWidth,
    plotHeight,
    startMs,
    endMs,
    bands,
    xFor,
    cursorData: historyH21BuildCursorData(payload),
  };
  historyH21AttachCursor(svg, payload, geometry);
  return true;
}

historyRenderSvg = historyH21RenderSvg;

function historyH21WireCompactDragGuard() {
  const card = document.getElementById("historyChartCard");
  if (!card || card.dataset.historyH21Guard === "true") return;
  card.dataset.historyH21Guard = "true";
  card.addEventListener("click", (event) => {
    if (!historyH21CompactDragged) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    historyH21CompactDragged = false;
  }, true);
}

historyH21WireCompactDragGuard();
