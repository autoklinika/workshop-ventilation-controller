"use strict";

/*
 * Stage 2 AI panel renderer.
 *
 * AI Server owns operator wording. This client only selects the already prepared
 * operator_view fields and renders them verbatim. Legacy result fields remain a
 * compatibility fallback for older cached analyses.
 */

function validAiOperatorView(result) {
  const view = result && result.operator_view;
  if (!view || typeof view !== "object" || view.schema_version !== 1) return null;

  const fields = [
    "status_label_pl",
    "headline_pl",
    "summary_pl",
    "recommendation_pl",
    "data_quality_short_pl"
  ];

  return fields.every((field) => typeof view[field] === "string" && view[field].trim())
    ? view
    : null;
}

function renderAiAdvisory(snapshot) {
  if (!snapshot || snapshot.available !== true) {
    renderAiUnavailable(
      snapshot && typeof snapshot.error === "string"
        ? snapshot.error
        : null
    );
    return;
  }

  const report = snapshot.report;
  const result = report && report.result;

  if (!report || !result || typeof result.status !== "string") {
    renderAiUnavailable("Lokalny raport AI ma niepoprawną strukturę.", true);
    return;
  }

  const presentation =
    AI_RESULT_PRESENTATION[result.status] ||
    AI_RESULT_PRESENTATION.insufficient_data;
  const operatorView = validAiOperatorView(result);

  const status = document.getElementById("aiStatus");
  const headline = document.getElementById("aiHeadline");
  const summary = document.getElementById("aiSummary");
  const recommendation = document.getElementById("aiRecommendation");
  const dataQuality = document.getElementById("aiDataQuality");
  const updatedAt = document.getElementById("aiUpdatedAt");
  const panel = document.getElementById("aiPanel");

  if (status) {
    if (snapshot.stale === true) {
      status.className = "status-chip status-warn";
      status.textContent = "ANALIZA NIEAKTUALNA";
    } else {
      status.className = `status-chip ${presentation.css}`;
      status.textContent = operatorView
        ? operatorView.status_label_pl
        : presentation.chip;
    }
  }

  if (headline) {
    headline.textContent = operatorView
      ? operatorView.headline_pl
      : presentation.headline;
  }

  if (summary) {
    summary.textContent = operatorView
      ? operatorView.summary_pl
      : typeof result.analysis_pl === "string" && result.analysis_pl.trim()
        ? result.analysis_pl
        : "Brak opisu analizy.";
  }

  if (recommendation) {
    recommendation.textContent = operatorView
      ? operatorView.recommendation_pl
      : typeof result.operator_recommendation_pl === "string" &&
          result.operator_recommendation_pl.trim()
        ? result.operator_recommendation_pl
        : "Brak rekomendacji.";
  }

  if (dataQuality) {
    dataQuality.textContent = operatorView
      ? operatorView.data_quality_short_pl
      : typeof result.data_quality_pl === "string" && result.data_quality_pl.trim()
        ? result.data_quality_pl
        : "Brak informacji o jakości danych.";
  }

  if (updatedAt) {
    updatedAt.textContent = aiWindowText(
      report.window_end,
      snapshot.age_seconds
    );
  }

  if (panel) {
    panel.dataset.analysisId =
      typeof report.analysis_id === "string" ? report.analysis_id : "";
    panel.dataset.resultStatus = result.status;
    panel.dataset.fresh = snapshot.fresh === true ? "true" : "false";
    panel.dataset.operatorView = operatorView ? "true" : "false";
  }

  setAiEventsMuted(false);
}

// dashboard-live.js has already initialized the transport poller. Re-render once
// immediately with the Stage 2 client renderer; later polls call this replacement.
if (typeof aiAdvisory === "function") {
  aiAdvisory();
}
