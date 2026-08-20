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
 * - tapping the card opens a large centered modal that shows the same DOM text in full;
 * - the transition is presentation-only: the modal flies out of the tapped card and
 *   returns into the same card when it is closed;
 * - no summarization, trend calculation or other AI interpretation happens here.
 */

const AI_DETAIL_OPEN_MS = 280;
const AI_DETAIL_CLOSE_MS = 240;
let aiDetailTransitionSerial = 0;

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

function aiDetailReducedMotion() {
  return typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function aiDetailCanAnimate(element) {
  return !aiDetailReducedMotion() && element && typeof element.animate === "function";
}

function cancelAiDetailAnimations(overlay) {
  if (!overlay || typeof overlay.getAnimations !== "function") return;
  overlay.getAnimations({ subtree: true }).forEach((animation) => animation.cancel());
}

function aiDetailFlightFromCard(card, detailCard) {
  const source = card.getBoundingClientRect();
  const target = detailCard.getBoundingClientRect();
  const targetWidth = Math.max(1, target.width);
  const targetHeight = Math.max(1, target.height);
  const sourceCenterX = source.left + source.width / 2;
  const sourceCenterY = source.top + source.height / 2;
  const targetCenterX = target.left + target.width / 2;
  const targetCenterY = target.top + target.height / 2;
  const translateX = sourceCenterX - targetCenterX;
  const translateY = sourceCenterY - targetCenterY;
  const scaleX = Math.max(0.001, source.width / targetWidth);
  const scaleY = Math.max(0.001, source.height / targetHeight);

  return {
    translateX,
    translateY,
    scaleX,
    scaleY,
    transform: `translate(${translateX}px, ${translateY}px) scale(${scaleX}, ${scaleY})`
  };
}

function aiDetailTravelTransform(flight, remaining, scaleBoost = 0) {
  const translateX = flight.translateX * remaining;
  const translateY = flight.translateY * remaining;
  const scaleX = 1 + (flight.scaleX - 1) * remaining + scaleBoost;
  const scaleY = 1 + (flight.scaleY - 1) * remaining + scaleBoost;
  return `translate(${translateX}px, ${translateY}px) scale(${scaleX}, ${scaleY})`;
}

function finalizeAiDetailOpen(serial) {
  if (serial !== aiDetailTransitionSerial) return;
  const overlay = document.getElementById("aiDetailModal");
  if (!overlay || overlay.hidden) return;
  overlay.classList.remove("is-transitioning");
  cancelAiDetailAnimations(overlay);

  const close = document.getElementById("aiDetailClose");
  if (close) close.focus({ preventScroll: true });
}

function finalizeAiDetailClose(serial) {
  if (serial !== aiDetailTransitionSerial) return;
  const overlay = document.getElementById("aiDetailModal");
  if (!overlay) return;

  cancelAiDetailAnimations(overlay);
  overlay.classList.remove("is-transitioning");
  overlay.hidden = true;
  document.body.classList.remove("v2-ai-detail-open");

  const card = document.querySelector(".v2-ai-panel");
  if (card) {
    card.setAttribute("aria-expanded", "false");
    card.focus({ preventScroll: true });
  }
}

function openAiDetailModal() {
  const overlay = ensureAiDetailModal();
  const card = document.querySelector(".v2-ai-panel");
  const detailCard = overlay.querySelector(".v2-ai-detail-card");
  const detailHeader = overlay.querySelector(".v2-ai-detail-header");
  const detailScroll = overlay.querySelector(".v2-ai-detail-scroll");

  const serial = ++aiDetailTransitionSerial;
  cancelAiDetailAnimations(overlay);
  overlay.hidden = false;
  overlay.classList.add("is-transitioning");
  document.body.classList.add("v2-ai-detail-open");
  if (card) card.setAttribute("aria-expanded", "true");
  syncAiDetailModalFromCard();
  if (detailScroll) detailScroll.scrollTop = 0;

  if (!card || !detailCard || !aiDetailCanAnimate(detailCard)) {
    finalizeAiDetailOpen(serial);
    return;
  }

  const flight = aiDetailFlightFromCard(card, detailCard);
  overlay.animate(
    [{ opacity: 0 }, { opacity: 0.92, offset: 0.55 }, { opacity: 1 }],
    { duration: AI_DETAIL_OPEN_MS, easing: "linear", fill: "both" }
  );

  if (detailHeader) {
    detailHeader.animate(
      [{ opacity: 0 }, { opacity: 0, offset: 0.50 }, { opacity: 1 }],
      { duration: AI_DETAIL_OPEN_MS, easing: "ease-out", fill: "both" }
    );
  }
  if (detailScroll) {
    detailScroll.animate(
      [{ opacity: 0 }, { opacity: 0, offset: 0.56 }, { opacity: 1 }],
      { duration: AI_DETAIL_OPEN_MS, easing: "ease-out", fill: "both" }
    );
  }

  const flyOut = detailCard.animate(
    [
      { transform: flight.transform, borderRadius: "14px", offset: 0 },
      { transform: aiDetailTravelTransform(flight, 0.08, 0.018), borderRadius: "19px", offset: 0.78 },
      { transform: "translate(0px, 0px) scale(1, 1)", borderRadius: "18px", offset: 1 }
    ],
    {
      duration: AI_DETAIL_OPEN_MS,
      easing: "cubic-bezier(.18,.84,.24,1)",
      fill: "both"
    }
  );
  flyOut.addEventListener("finish", () => finalizeAiDetailOpen(serial), { once: true });
}

function closeAiDetailModal() {
  const overlay = document.getElementById("aiDetailModal");
  if (!overlay || overlay.hidden) return;

  const card = document.querySelector(".v2-ai-panel");
  const detailCard = overlay.querySelector(".v2-ai-detail-card");
  const detailHeader = overlay.querySelector(".v2-ai-detail-header");
  const detailScroll = overlay.querySelector(".v2-ai-detail-scroll");
  const serial = ++aiDetailTransitionSerial;

  cancelAiDetailAnimations(overlay);
  overlay.classList.add("is-transitioning");

  if (!card || !detailCard || !aiDetailCanAnimate(detailCard)) {
    finalizeAiDetailClose(serial);
    return;
  }

  const flight = aiDetailFlightFromCard(card, detailCard);
  overlay.animate(
    [{ opacity: 1 }, { opacity: 1, offset: 0.30 }, { opacity: 0 }],
    { duration: AI_DETAIL_CLOSE_MS, easing: "linear", fill: "both" }
  );

  if (detailHeader) {
    detailHeader.animate(
      [{ opacity: 1 }, { opacity: 0 }],
      { duration: Math.round(AI_DETAIL_CLOSE_MS * 0.48), easing: "ease-in", fill: "both" }
    );
  }
  if (detailScroll) {
    detailScroll.animate(
      [{ opacity: 1 }, { opacity: 0 }],
      { duration: Math.round(AI_DETAIL_CLOSE_MS * 0.42), easing: "ease-in", fill: "both" }
    );
  }

  const flyBack = detailCard.animate(
    [
      { transform: "translate(0px, 0px) scale(1, 1)", borderRadius: "18px", offset: 0 },
      { transform: aiDetailTravelTransform(flight, 0.14, -0.008), borderRadius: "17px", offset: 0.28 },
      { transform: flight.transform, borderRadius: "14px", offset: 1 }
    ],
    {
      duration: AI_DETAIL_CLOSE_MS,
      easing: "cubic-bezier(.42,0,.78,.22)",
      fill: "both"
    }
  );
  flyBack.addEventListener("finish", () => finalizeAiDetailClose(serial), { once: true });
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
