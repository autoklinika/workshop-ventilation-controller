"use strict";

/*
 * History H2.3: every multi-series group uses separate stacked Y scales.
 * Time stays shared. Backend contract and data remain unchanged.
 */

const HISTORY_H23_MIN_GAP_PX = 10;

function historyH23IsMultiSeriesPayload(payload) {
  return Boolean(payload && Array.isArray(payload.series) && payload.series.length > 1);
}

function historyH23GapForCount(count, plotHeight) {
  if (count >= 4) return Math.max(HISTORY_H23_MIN_GAP_PX, Math.round(plotHeight * 0.025));
  if (count === 3) return Math.max(12, Math.round(plotHeight * 0.035));
  return Math.max(18, Math.round(plotHeight * 0.05));
}

function historyH23BuildBands(payload, margin, plotHeight) {
  if (!payload || !Array.isArray(payload.series) || payload.series.length === 0) return [];

  if (payload.series.length === 1) {
    const series = payload.series[0];
    const bounds = historyH21Bounds(historyH21SeriesValues(series, payload.resolution));
    return bounds ? [{
      seriesIndexes: [0],
      top: margin.top,
      height: plotHeight,
      bounds,
      label: null,
    }] : [];
  }

  const count = payload.series.length;
  const gap = historyH23GapForCount(count, plotHeight);
  const totalGap = gap * (count - 1);
  const bandHeight = Math.max(1, (plotHeight - totalGap) / count);

  return payload.series.map((series, index) => {
    const bounds = historyH21Bounds(historyH21SeriesValues(series, payload.resolution));
    if (!bounds) return null;
    return {
      seriesIndexes: [index],
      top: margin.top + index * (bandHeight + gap),
      height: bandHeight,
      bounds,
      label: historyShortLabel(series.label),
    };
  }).filter(Boolean);
}

/*
 * H2.1 renderer already supports multiple independent bands and H2.2 reuses
 * the same geometry for modal zoom/pan. Override only the split predicate and
 * band builder so PM, RPM, setpoints, duct temperatures and AERO groups all
 * get the same treatment as VOC/NOx.
 */
historyH21IsGasPayload = historyH23IsMultiSeriesPayload;
historyH21BuildBands = historyH23BuildBands;
