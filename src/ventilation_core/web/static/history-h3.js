"use strict";

/* History H3: presentation labels for long-range backend resolutions. */

const historyH3BaseRangeLabel = historyRangeLabel;
historyRangeLabel = function historyH3RangeLabel(rangeId) {
  const labels = {
    "30d": "30 DNI",
    "90d": "90 DNI",
    "1y": "1 ROK",
  };
  return labels[rangeId] || historyH3BaseRangeLabel(rangeId);
};

const historyH3BaseResolutionText = historyResolutionText;
historyResolutionText = function historyH3ResolutionText(resolution) {
  const labels = {
    "1h": "1 GODZ.",
    "1d": "1 DZIEŃ",
  };
  return labels[resolution] || historyH3BaseResolutionText(resolution);
};

const historyH3BaseCursorKind = historyH21CursorKind;
historyH21CursorKind = function historyH3CursorKind(resolution) {
  const labels = {
    "1h": "1 GODZ. · ŚREDNIA",
    "1d": "1 DZIEŃ · ŚREDNIA",
  };
  return labels[resolution] || historyH3BaseCursorKind(resolution);
};

const historyH3BaseTimeLabel = historyTimeLabel;
historyTimeLabel = function historyH3TimeLabel(timestamp, rangeId) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  if (rangeId === "30d" || rangeId === "90d") {
    return new Intl.DateTimeFormat("pl-PL", {
      day: "2-digit",
      month: "2-digit",
    }).format(date);
  }
  if (rangeId === "1y") {
    return new Intl.DateTimeFormat("pl-PL", {
      month: "short",
      year: "2-digit",
    }).format(date);
  }
  return historyH3BaseTimeLabel(timestamp, rangeId);
};
