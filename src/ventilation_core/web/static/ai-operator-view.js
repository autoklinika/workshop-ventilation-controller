"use strict";

/*
 * Stage 2 AI panel renderer.
 *
 * AI Server owns operator wording. This client only selects the already prepared
 * operator_view fields and renders them verbatim. Legacy result fields remain a
 * compatibility fallback for older cached analyses.
 *
 * Dashboard presentation rule:
 * - the compact AI card is a fixed-size HMI client view with CSS-only clipping;
 * - tapping the card opens a full-screen modal that shows the same DOM text in full;
 * - no summarization, trend calculation or other AI interpretation happens here.
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

function ensureAiDetailModal() {
  let overlay = document.getElementById("aiDetailModal");
  if (overlay) return overlay;

  overlay = document.createElement("div");
  overlay.id = "aiDetailModal";
  overlay.className = "v2-ai-detail";
  overlay.hidden = true;
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "aiDetailHeadline");
  overlay.innerHTML = `
    <section class="v2-ai-detail-card">
      <header class="v2-ai-detail-header">
        <div class="v2-ai-detail-title">
          <span>AI · ANALIZA SYSTEMU</span>
          <h2 id="aiDetailHeadline">Brak analizy AI</h2>
        </div>
        <button id="aiDetailClose" class="v2-ai-detail-close" type="button">ZAMKNIJ</button>
      </header>
      <div class="v2-ai-detail-scroll">
        <div class="v2-ai-detail-meta">
          <span id="aiDetailStatus" class="status-chip status-unknown">OCZEKIWANIE NA AI</span>
          <span id="aiDetailUpdatedAt">—</span>
        </div>
        <section class="v2-ai-detail-section">
          <h3>Podsumowanie</h3>
          <p id="aiDetailSummary">—</p>
        </section>
        <section class="v2-ai-detail-section">
          <h3>Rekomendacja</h3>
          <p id="aiDetailRecommendation">—</p>
        </section>
        <section class="v2-ai-detail-section">
          <h3>Jakość danych</h3>
          <p id="aiDetailDataQuality">—</p>
        </section>
      </div>
    </section>`;
  document.body.appendChild(overlay);

  const close = document.getElementById("aiDetailClose");
  if (close) close.addEventListener("click", closeAiDetailModal);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || overlay.hidden) return;
    const systemAlert = document.getElementById("globalSystemAlert");
    if (systemAlert && !systemAlert.hidden) return;
    closeAiDetailModal();
  });

  return overlay;
}

function copyAiText(sourceId, targetId) {
  const source = document.getElementById(sourceId);
  const target = document.getElementById(targetId);
  if (source && target) target.textContent = source.textContent;
}

function syncAiDetailModalFromCard() {
  const overlay = document.getElementById("aiDetailModal");
  if (!overlay || overlay.hidden) return;

  copyAiText("aiHeadline", "aiDetailHeadline");
  copyAiText("aiSummary", "aiDetailSummary");
  copyAiText("aiRecommendation", "aiDetailRecommendation");
  copyAiText("aiDataQuality", "aiDetailDataQuality");
  copyAiText("aiUpdatedAt", "aiDetailUpdatedAt");

  const sourceStatus = document.getElementById("aiStatus");
  const targetStatus = document.getElementById("aiDetailStatus");
  if (sourceStatus && targetStatus) {
    targetStatus.className = sourceStatus.className;
    targetStatus.textContent = sourceStatus.textContent;
  }
}

function openAiDetailModal() {
  const overlay = ensureAiDetailModal();
  const card = document.querySelector(".v2-ai-panel");
  overlay.hidden = false;
  document.body.classList.add("v2-ai-detail-open");
  if (card) card.setAttribute("aria-expanded", "true");
  syncAiDetailModalFromCard();

  const close = document.getElementById("aiDetailClose");
  if (close) close.focus({ preventScroll: true });
}

function closeAiDetailModal() {
  const overlay = document.getElementById("aiDetailModal");
  if (!overlay || overlay.hidden) return;

  overlay.hidden = true;
  document.body.classList.remove("v2-ai-detail-open");

  const card = document.querySelector(".v2-ai-panel");
  if (card) {
    card.setAttribute("aria-expanded", "false");
    card.focus({ preventScroll: true });
  }
}

function wireAiDetailInteraction() {
  const card = document.querySelector(".v2-ai-panel");
  if (!card || card.dataset.aiDetailWired === "true") return;

  ensureAiDetailModal();
  card.dataset.aiDetailWired = "true";
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute("aria-haspopup", "dialog");
  card.setAttribute("aria-controls", "aiDetailModal");
  card.setAttribute("aria-expanded", "false");
  card.setAttribute("aria-label", "Otwórz pełną analizę AI");

  card.addEventListener("click", (event) => {
    if (event.target.closest("a,button,input,select,textarea")) return;
    openAiDetailModal();
  });

  card.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    openAiDetailModal();
  });

  const observer = new MutationObserver(syncAiDetailModalFromCard);
  observer.observe(card, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true
  });
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
  syncAiDetailModalFromCard();
}

wireAiDetailInteraction();

// dashboard-live.js has already initialized the transport poller. Re-render once
// immediately with the Stage 2 client renderer; later polls call this replacement.
if (typeof aiAdvisory === "function") {
  aiAdvisory();
}
