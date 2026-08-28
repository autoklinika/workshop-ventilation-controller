# WebGUI V2 — Automatyka Stage 1

Data: 2026-08-28

## Zakres

Stage 1 dodaje do WebGUI V2 osobny ekran `/automation`, stacked na `agent/automation-v1-control-engine`.

Widok jest klientem istniejących kontraktów `ventilation-core` i nie przejmuje logiki automatyki.

## Ekrany

Zakładka `AUTOMATYKA` zawiera cztery widoki:

1. `STAN`
   - bieżący operator intent AUTO/MANUAL,
   - stan Control Engine,
   - kontekst Calendar Engine,
   - klasyfikację AQ i thermal,
   - proponowane SHADOW supply/extract/AERO,
   - rzeczywiste setpointy fizyczne pokazane osobno,
   - TACHO supervision,
   - Actuation Readiness Gate i powód decyzji.

2. `HARMONOGRAM`
   - wykorzystuje istniejący `calendar.js`/`calendar.css`,
   - korzysta z istniejącego `/api/v1/calendar`,
   - nie tworzy drugiego modelu harmonogramu,
   - jawnie rozdziela harmonogram wentylacji od przyszłego harmonogramu zasilania CM5 / RTC.

3. `MANUAL`
   - dotyczy wyłącznie volatile `OperatorControlIntent` Control Engine,
   - AUTO lub MANUAL z supply %, extract % i AERO 0..3,
   - nie korzysta z fizycznych endpointów `/api/v1/manual/*`,
   - po restarcie core intent nadal zgodnie z domeną wraca do AUTO.

4. `TUNING`
   - read-only prezentacja Validation Ledger,
   - postęp wymaganych grup tuningu,
   - aktualne blockery Actuation Readiness Gate,
   - brak funkcji apply/promote/bind.

## Granica bezpieczeństwa

Ekran ma stały komunikat:

`SHADOW — BRAK STEROWANIA FIZYCZNYMI WYJŚCIAMI`.

Frontend Automatyki korzysta wyłącznie z:

- `GET /api/v1/state`,
- `GET /api/v1/automation/tuning-validation`,
- `POST /api/v1/automation/operator`.

Backend operator intent posiada wąski kontrakt i mapuje wyłącznie na:

- `control-engine-operator`,
- `control-engine-operator-replace`.

Nie dodano generycznego proxy komend core ani authority do GP8403, AERO, GPIO, host-power lub scheduled shutdown.

## Harmonogram

Stage 1 przenosi harmonogram do głównego kontekstu `AUTOMATYKA`, ale zachowuje jedyne źródło prawdy w Calendar Engine.

Nie włącza scheduled shutdown ani RTC wake. Te funkcje pozostają poza ekranem operatora do czasu osobnej walidacji safety lifecycle.

## Workflow

- base GUI: `agent/automation-v1-control-engine`
- branch GUI: `agent/web-gui-automation-stage1`
- `main` nie jest modyfikowany
- GUI PR ma pozostać Draft
- brak merge bez wyraźnej decyzji właściciela projektu
