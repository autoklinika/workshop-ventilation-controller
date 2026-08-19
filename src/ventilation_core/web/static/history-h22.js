"use strict";

/*
 * History H2.2: modal-only visual zoom/pan.
 * The backend contract and stored history are unchanged. Zoom only changes the
 * visible time window over the already returned backend points.
 */

const HISTORY_H22_MIN_SCALE = 1;
const HISTORY_H22_MAX_SCALE = 12;
const HISTORY_H22_BUTTON_FACTOR = 2;
const HISTORY_H22_WHEEL_FACTOR = 1.35;
const HISTORY_H22_PAN_THRESHOLD_PX = 7;

const historyH22 = {
  scale: 1,
  center: 0.5,
  pointers: new Map(),
  gesture: null,
  panning: false,
  frame: 0,
};

function historyH22Clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

function historyH22Span(scale = historyH22.scale) {
  return 1 / historyH22Clamp(scale, HISTORY_H22_MIN_SCALE, HISTORY_H22_MAX_SCALE);
}

function historyH22ClampCenter(center, scale = historyH22.scale) {
  const half = historyH22Span(scale) / 2;
  return historyH22Clamp(center, half, 1 - half);
}

function historyH22SetViewport(scale, center) {
  historyH22.scale = historyH22Clamp(scale, HISTORY_H22_MIN_SCALE, HISTORY_H22_MAX_SCALE);
  historyH22.center = historyH22ClampCenter(center, historyH22.scale);
  historyH22UpdateControls();
}

function historyH22ResetViewport(render = false) {
  historyH22.pointers.clear();
  historyH22.gesture = null;
  historyH22.panning = false;
  historyH22SetViewport(1, 0.5);
  if (render) historyH22RenderModal();
}

function historyH22VisibleFractions() {
  const span = historyH22Span();
  const start = historyH22Clamp(historyH22.center - span / 2, 0, 1 - span);
  return { start, end: start + span };
}

function historyH22Payload(payload) {
  if (!payload || !payload.range || !Array.isArray(payload.series)) return payload;
  if (historyH22.scale <= 1.000001) return payload;

  const fullStart = new Date(payload.range.start).getTime();
  const fullEnd = new Date(payload.range.end).getTime();
  if (!Number.isFinite(fullStart) || !Number.isFinite(fullEnd) || fullEnd <= fullStart) return payload;

  const fractions = historyH22VisibleFractions();
  const startMs = fullStart + (fullEnd - fullStart) * fractions.start;
  const endMs = fullStart + (fullEnd - fullStart) * fractions.end;
  const startIso = new Date(startMs).toISOString();
  const endIso = new Date(endMs).toISOString();

  return {
    ...payload,
    range: { ...payload.range, start: startIso, end: endIso },
    series: payload.series.map((series) => ({
      ...series,
      points: (series.points || []).filter((point) => {
        const time = new Date(point.t).getTime();
        return Number.isFinite(time) && time >= startMs && time <= endMs;
      }),
    })),
  };
}

function historyH22Geometry(svg, payload) {
  const width = Math.max(640, Math.round(svg.clientWidth || 1000));
  const height = Math.max(260, Math.round(svg.clientHeight || 360));
  const margin = { left: 62, right: 20, top: 18, bottom: 34 };
  const plotWidth = Math.max(1, width - margin.left - margin.right);
  const plotHeight = Math.max(1, height - margin.top - margin.bottom);
  const startMs = new Date(payload.range && payload.range.start).getTime();
  const endMs = new Date(payload.range && payload.range.end).getTime();
  const bands = historyH21BuildBands(payload, margin, plotHeight);
  return {
    width,
    height,
    margin,
    plotWidth,
    plotHeight,
    startMs,
    endMs,
    bands,
    xFor: (time) => margin.left + ((time - startMs) / (endMs - startMs)) * plotWidth,
    cursorData: historyH21BuildCursorData(payload),
  };
}

function historyH22LocalFraction(svg, clientX) {
  const rect = svg.getBoundingClientRect();
  if (!rect.width) return 0.5;
  const left = 62 / Math.max(640, Math.round(svg.clientWidth || 1000));
  const right = 20 / Math.max(640, Math.round(svg.clientWidth || 1000));
  const raw = (clientX - rect.left) / rect.width;
  return historyH22Clamp((raw - left) / Math.max(0.001, 1 - left - right), 0, 1);
}

function historyH22ZoomAt(localFraction, nextScale) {
  const oldSpan = historyH22Span();
  const oldStart = historyH22VisibleFractions().start;
  const anchor = oldStart + localFraction * oldSpan;
  const scale = historyH22Clamp(nextScale, HISTORY_H22_MIN_SCALE, HISTORY_H22_MAX_SCALE);
  const newSpan = historyH22Span(scale);
  const newStart = historyH22Clamp(anchor - localFraction * newSpan, 0, 1 - newSpan);
  historyH22SetViewport(scale, newStart + newSpan / 2);
}

function historyH22PanFrom(startCenter, dxPixels, widthPixels, startScale) {
  if (!(widthPixels > 0) || startScale <= 1) return;
  const span = 1 / startScale;
  const shift = -(dxPixels / widthPixels) * span;
  historyH22SetViewport(startScale, startCenter + shift);
}

function historyH22ScheduleRender() {
  if (historyH22.frame) return;
  historyH22.frame = window.requestAnimationFrame(() => {
    historyH22.frame = 0;
    historyH22RenderModal();
  });
}

function historyH22EnsureControls() {
  const overlay = document.getElementById("historyChartModal");
  if (!overlay) return null;
  const header = overlay.querySelector(".v2-history-detail-head");
  const close = document.getElementById("historyModalClose");
  if (!header || !close) return null;

  let controls = document.getElementById("historyZoomControls");
  if (controls) return controls;

  controls = document.createElement("div");
  controls.id = "historyZoomControls";
  controls.className = "v2-history-zoom-controls";
  controls.setAttribute("aria-label", "Powiększenie wykresu");
  controls.innerHTML = `
    <button type="button" class="v2-history-zoom-button" data-history-zoom="out" aria-label="Oddal wykres">−</button>
    <button type="button" class="v2-history-zoom-reset" data-history-zoom="reset" aria-label="Przywróć pełny zakres">100%</button>
    <button type="button" class="v2-history-zoom-button" data-history-zoom="in" aria-label="Powiększ wykres">+</button>`;
  header.insertBefore(controls, close);

  controls.querySelector('[data-history-zoom="in"]').addEventListener("click", () => {
    historyH22ZoomAt(0.5, historyH22.scale * HISTORY_H22_BUTTON_FACTOR);
    historyH22RenderModal();
  });
  controls.querySelector('[data-history-zoom="out"]').addEventListener("click", () => {
    historyH22ZoomAt(0.5, historyH22.scale / HISTORY_H22_BUTTON_FACTOR);
    historyH22RenderModal();
  });
  controls.querySelector('[data-history-zoom="reset"]').addEventListener("click", () => historyH22ResetViewport(true));
  return controls;
}

function historyH22UpdateControls() {
  const controls = document.getElementById("historyZoomControls");
  if (!controls) return;
  const reset = controls.querySelector('[data-history-zoom="reset"]');
  const out = controls.querySelector('[data-history-zoom="out"]');
  const inside = controls.querySelector('[data-history-zoom="in"]');
  if (reset) reset.textContent = `${Math.round(historyH22.scale * 100)}%`;
  if (out) out.disabled = historyH22.scale <= HISTORY_H22_MIN_SCALE + 0.001;
  if (inside) inside.disabled = historyH22.scale >= HISTORY_H22_MAX_SCALE - 0.001;
}

function historyH22PinchInfo(svg) {
  const points = [...historyH22.pointers.values()];
  if (points.length < 2) return null;
  const a = points[0];
  const b = points[1];
  const distance = Math.max(1, Math.hypot(b.x - a.x, b.y - a.y));
  const midpointX = (a.x + b.x) / 2;
  return { distance, local: historyH22LocalFraction(svg, midpointX) };
}

function historyH22WireModalSvg(svg, payload) {
  if (!svg) return;
  const geometry = historyH22Geometry(svg, payload);
  const stage = svg.parentElement;
  if (stage) stage.classList.toggle("is-zoomed", historyH22.scale > 1.000001);

  svg.onwheel = (event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? HISTORY_H22_WHEEL_FACTOR : 1 / HISTORY_H22_WHEEL_FACTOR;
    historyH22ZoomAt(historyH22LocalFraction(svg, event.clientX), historyH22.scale * factor);
    historyH22RenderModal();
  };

  svg.onpointerdown = (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    historyH22.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (typeof svg.setPointerCapture === "function") {
      try { svg.setPointerCapture(event.pointerId); } catch (_error) { /* presentation fallback */ }
    }

    if (historyH22.pointers.size >= 2) {
      const pinch = historyH22PinchInfo(svg);
      historyH22.gesture = pinch ? {
        type: "pinch",
        distance: pinch.distance,
        scale: historyH22.scale,
        local: pinch.local,
      } : null;
      historyH22.panning = false;
      event.preventDefault();
      return;
    }

    historyH22.gesture = {
      type: "single",
      pointerId: event.pointerId,
      x: event.clientX,
      center: historyH22.center,
      scale: historyH22.scale,
    };
    historyH22.panning = false;
    historyH21ShowCursor(svg, payload, geometry, event.clientX, event.pointerType);
  };

  svg.onpointermove = (event) => {
    if (historyH22.pointers.has(event.pointerId)) {
      historyH22.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    }

    if (historyH22.pointers.size >= 2) {
      const pinch = historyH22PinchInfo(svg);
      if (!pinch) return;
      if (!historyH22.gesture || historyH22.gesture.type !== "pinch") {
        historyH22.gesture = {
          type: "pinch",
          distance: pinch.distance,
          scale: historyH22.scale,
          local: pinch.local,
        };
      }
      const nextScale = historyH22.gesture.scale * (pinch.distance / historyH22.gesture.distance);
      historyH22ZoomAt(historyH22.gesture.local, nextScale);
      historyH22.panning = true;
      event.preventDefault();
      historyH22ScheduleRender();
      return;
    }

    const single = historyH22.gesture && historyH22.gesture.type === "single" ? historyH22.gesture : null;
    const activeSingle = single && historyH22.pointers.has(single.pointerId);
    if (activeSingle && historyH22.scale > 1.000001 && (event.pointerType === "touch" || event.buttons !== 0)) {
      const dx = event.clientX - single.x;
      if (historyH22.panning || Math.abs(dx) >= HISTORY_H22_PAN_THRESHOLD_PX) {
        historyH22.panning = true;
        historyH22PanFrom(single.center, dx, Math.max(1, svg.getBoundingClientRect().width), single.scale);
        event.preventDefault();
        historyH22ScheduleRender();
        return;
      }
    }

    if (event.pointerType === "mouse" || activeSingle) {
      historyH21ShowCursor(svg, payload, geometry, event.clientX, event.pointerType);
    }
  };

  const finishPointer = (event) => {
    historyH22.pointers.delete(event.pointerId);
    if (historyH22.pointers.size === 1) {
      const [pointerId, point] = historyH22.pointers.entries().next().value;
      historyH22.gesture = {
        type: "single",
        pointerId,
        x: point.x,
        center: historyH22.center,
        scale: historyH22.scale,
      };
    } else if (historyH22.pointers.size === 0) {
      historyH22.gesture = null;
      historyH22.panning = false;
    }
  };

  svg.onpointerup = finishPointer;
  svg.onpointercancel = (event) => {
    finishPointer(event);
    historyH21HideCursor(svg);
  };
  svg.onpointerleave = (event) => {
    if (event.pointerType === "mouse" && event.buttons === 0) historyH21HideCursor(svg);
  };
}

function historyH22RenderModal() {
  const overlay = document.getElementById("historyChartModal");
  const svg = document.getElementById("historyModalSvg");
  if (!overlay || overlay.hidden || !svg || !historyClient.payload) return;

  historyH22EnsureControls();
  historyH22UpdateControls();
  const viewPayload = historyH22Payload(historyClient.payload);
  const rendered = historyH21RenderSvg(svg, viewPayload);
  const empty = document.getElementById("historyModalEmpty");
  if (empty) {
    empty.hidden = rendered;
    empty.textContent = rendered ? "" : "Brak danych w powiększonym fragmencie czasu.";
  }
  if (rendered) historyH22WireModalSvg(svg, viewPayload);
}

const historyH22BaseSyncHistoryChartModal = syncHistoryChartModal;
syncHistoryChartModal = function historyH22SyncHistoryChartModal() {
  historyH22BaseSyncHistoryChartModal();
  historyH22RenderModal();
};

const historyH22BaseOpenHistoryChartModal = openHistoryChartModal;
openHistoryChartModal = function historyH22OpenHistoryChartModal() {
  historyH22ResetViewport(false);
  historyH22BaseOpenHistoryChartModal();
  historyH22EnsureControls();
  historyH22UpdateControls();
};

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-history-zone],[data-history-range],[data-history-preset]")) {
    historyH22ResetViewport(false);
  }
}, true);
