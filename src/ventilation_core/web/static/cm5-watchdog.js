"use strict";

const CM5_WATCHDOG_POLL_MS = 2000;
const CM5_WATCHDOG_REQUEST_TIMEOUT_MS = 1500;
const CM5_WATCHDOG_FAILURE_LIMIT = 3;
const CM5_WATCHDOG_RECOVERY_LIMIT = 2;

let cm5WatchdogFailures = 0;
let cm5WatchdogRecoveries = 0;
let cm5WatchdogOffline = false;
let cm5WatchdogInFlight = false;

function ensureCm5WatchdogOverlay() {
  let overlay = document.getElementById("cm5CommunicationWatchdog");
  if (overlay) return overlay;

  overlay = document.createElement("div");
  overlay.id = "cm5CommunicationWatchdog";
  overlay.className = "v2-cm5-watchdog";
  overlay.hidden = true;
  overlay.setAttribute("role", "alert");
  overlay.setAttribute("aria-live", "assertive");
  overlay.setAttribute("aria-atomic", "true");
  overlay.innerHTML = `
    <div class="v2-cm5-watchdog-panel">
      <div class="v2-cm5-watchdog-icon" aria-hidden="true">!</div>
      <div class="v2-cm5-watchdog-kicker">POŁĄCZENIE UTRACONE</div>
      <h1>BRAK KOMUNIKACJI Z CM5</h1>
      <p>Panel nie otrzymuje danych ze sterownika.</p>
      <p class="v2-cm5-watchdog-retry">Ponawianie połączenia automatycznie…</p>
    </div>`;
  document.body.appendChild(overlay);
  return overlay;
}

function setCm5WatchdogOffline(offline) {
  if (cm5WatchdogOffline === offline) return;
  cm5WatchdogOffline = offline;

  const overlay = ensureCm5WatchdogOverlay();
  overlay.hidden = !offline;
  document.body.classList.toggle("v2-cm5-offline", offline);

  const sidebar = document.querySelector(".v2-sidebar");
  const viewHost = document.getElementById("viewHost");
  for (const element of [sidebar, viewHost]) {
    if (!element) continue;
    if (offline) element.setAttribute("inert", "");
    else element.removeAttribute("inert");
  }

  if (offline && document.activeElement instanceof HTMLElement) {
    document.activeElement.blur();
  }

  window.dispatchEvent(new CustomEvent(offline ? "cm5-watchdog-offline" : "cm5-watchdog-online"));
}

async function probeCm5Communication() {
  if (cm5WatchdogInFlight) return;
  cm5WatchdogInFlight = true;

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), CM5_WATCHDOG_REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch("/api/v1/state", {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const payload = await response.json();
    if (!payload || payload.ok !== true || !payload.state) {
      throw new Error("Invalid CM5 state response");
    }

    cm5WatchdogFailures = 0;
    if (cm5WatchdogOffline) {
      cm5WatchdogRecoveries += 1;
      if (cm5WatchdogRecoveries >= CM5_WATCHDOG_RECOVERY_LIMIT) {
        cm5WatchdogRecoveries = 0;
        setCm5WatchdogOffline(false);
      }
    } else {
      cm5WatchdogRecoveries = 0;
    }
  } catch (_error) {
    cm5WatchdogRecoveries = 0;
    cm5WatchdogFailures += 1;
    if (cm5WatchdogFailures >= CM5_WATCHDOG_FAILURE_LIMIT) {
      setCm5WatchdogOffline(true);
    }
  } finally {
    window.clearTimeout(timeout);
    cm5WatchdogInFlight = false;
  }
}

function startCm5CommunicationWatchdog() {
  ensureCm5WatchdogOverlay();
  probeCm5Communication();
  window.setInterval(probeCm5Communication, CM5_WATCHDOG_POLL_MS);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startCm5CommunicationWatchdog, { once: true });
} else {
  startCm5CommunicationWatchdog();
}
