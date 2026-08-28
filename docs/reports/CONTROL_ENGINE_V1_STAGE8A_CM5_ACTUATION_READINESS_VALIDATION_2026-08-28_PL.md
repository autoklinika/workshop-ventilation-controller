# Control Engine V1 — Stage8A CM5 Actuation Readiness Gate Validation

Data: 2026-08-28

## Cel

Fizyczna, nieaktuująca walidacja `Actuation Readiness Gate` na docelowym CM5. Test miał potwierdzić, że fizycznie zwalidowany parametr TACHO `tacho_failure_confirmation_seconds = 4.0 s` usuwa wyłącznie blocker konfiguracji czasu potwierdzenia, ale sam gate pozostaje zablokowany do czasu spełnienia pozostałych warunków i wdrożenia jawnej authority.

Stage8A nie uruchamia lokalnych wentylatorów i nie modyfikuje produkcyjnego `automation.sqlite3`.

## Zwalidowany kod

- branch: `agent/automation-v1-control-engine`
- exact SHA: `d577075b0d1348512a4506f73dd625aee8ca9497`
- produkcyjny main podczas testu: `7628c407cfc9c0ea72d262566759ea2d4598fec8`

## Przebieg

1. Produkcyjny preflight: EC 0 V, brak obserwowanego ruchu, SHADOW non-actuating.
2. Uruchomienie exact-SHA worktree z izolowanym `automation.sqlite3`.
3. Zastosowanie fizycznie zwalidowanego `tacho_failure_confirmation_seconds = 4.0 s` wyłącznie do izolowanej konfiguracji.
4. Odczyt `shadow_automation.actuation_readiness`.
5. Restart branch core i ponowna walidacja blockerów.
6. Rollback do produkcyjnego main oraz porównanie produkcyjnego rekordu Control Engine SQLite przed/po teście.

## Wynik

**PASS**

Po zastosowaniu 4.0 s:

```json
{
  "actuation_authorized": false,
  "blockers": [
    "ACTUATION_AUTHORITY_NOT_IMPLEMENTED",
    "AERO_OUTPUT_TUNING_INCOMPLETE",
    "AERO_SENSOR_FALLBACK_UNCONFIGURED",
    "DYNAMICS_TUNING_INCOMPLETE",
    "FAN_OUTPUT_TUNING_INCOMPLETE",
    "FAN_SENSOR_FALLBACK_UNCONFIGURED",
    "SHADOW_STATUS_TUNING_REQUIRED",
    "TACHO_BOTH_FALLBACK_UNCONFIGURED",
    "TACHO_EXTRACT_FALLBACK_UNCONFIGURED",
    "TACHO_SUPPLY_FALLBACK_UNCONFIGURED"
  ],
  "preconditions_satisfied": false,
  "ready": false
}
```

Po restarcie branch core wynik pozostał identyczny.

## Potwierdzone właściwości

- `TACHO_CONFIRMATION_UNCONFIGURED` nie występuje po zastosowaniu zwalidowanego 4.0 s.
- `ACTUATION_AUTHORITY_NOT_IMPLEMENTED` pozostaje aktywnym blockerem.
- niepełny tuning fanów, AERO i dynamiki pozostaje jawnie widoczny.
- fallback po utracie SEN55 pozostaje nieustawiony.
- fallback TACHO dla `SUPPLY`, `EXTRACT` i `BOTH` pozostaje nieustawiony.
- `preconditions_satisfied=false`.
- `ready=false`.
- `actuation_authorized=false`.
- lokalne EC przez cały test pozostawały na 0 V.
- brak obserwowanego ruchu lokalnych wentylatorów.
- boot ID, host-power i RTC wakealarm nie zmieniły się.
- produkcyjny rekord `control_engine_configuration` w `automation.sqlite3` nie zmienił się.
- rollback do produkcyjnego main zakończył się poprawnie.

## Wniosek

Readiness Gate działa jako fail-closed diagnostyczna granica przyszłej aktuacji. Fizycznie zwalidowane 4.0 s usuwa tylko odpowiadający mu blocker i nie odblokowuje sterowania.

W tym PR Control Engine nadal pozostaje SHADOW-only. Nie istnieje authority ani port aktuacyjny i nie należy ich włączać na podstawie Stage8A.

## Parametry nadal wymagające późniejszej walidacji/tuningu

- fan output tuning,
- AERO output tuning,
- dynamics tuning,
- SEN55-loss fan fallback,
- SEN55-loss AERO fallback,
- TACHO fallback `SUPPLY`,
- TACHO fallback `EXTRACT`,
- TACHO fallback `BOTH`.

Wartości środowiskowe z LAB nie są używane do strojenia tych parametrów.
