# Control Engine V1 — Stage8B Actuation Readiness Blocker Matrix

Data: 2026-08-28

## Cel

Deterministyczna walidacja diagnostycznego `Actuation Readiness Gate` dla wszystkich głównych klas prerequisite failures. Stage8B nie dodaje authority ani żadnej ścieżki aktuacyjnej. Testuje wyłącznie zachowanie fail-closed i jednoznaczność blockerów.

## Checkpoint

- branch: `agent/automation-v1-control-engine`
- kodowy checkpoint: `816439fe807c437fa5c1c83b96d4aa349fdb1e93`
- GitHub Actions: `33172668133`
- Compile sources: PASS
- Run unit tests: PASS
- Overall: SUCCESS

## Zakres macierzy

Macierz sprawdza niezależnie:

### Konfiguracja
- `FAN_OUTPUT_TUNING_INCOMPLETE`
- `AERO_OUTPUT_TUNING_INCOMPLETE`
- `DYNAMICS_TUNING_INCOMPLETE`
- `FAN_SENSOR_FALLBACK_UNCONFIGURED`
- `AERO_SENSOR_FALLBACK_UNCONFIGURED`
- `TACHO_CONFIRMATION_UNCONFIGURED`
- `TACHO_SUPPLY_FALLBACK_UNCONFIGURED`
- `TACHO_EXTRACT_FALLBACK_UNCONFIGURED`
- `TACHO_BOTH_FALLBACK_UNCONFIGURED`

### Runtime / hardware state
- `CONTROL_ENGINE_CONFIG_NOT_PERSISTENT`
- `HARDWARE_NOT_READY`
- `OUTPUT_STATE_UNKNOWN`
- `TACHO_MONITOR_UNAVAILABLE` dla:
  - brak monitora,
  - `ready=false`,
  - `worker_alive=false`.

### SHADOW
Każdy status różny od `READY` musi generować jawny blocker `SHADOW_STATUS_<STATUS>`.

Dodatkowo:
- brak zone-1 => `ZONE1_SHADOW_MISSING`,
- aktywny fault TACHO => `TACHO_FAULT_ACTIVE`,
- aktywny fallback TACHO => `TACHO_FALLBACK_ACTIVE`.

## Authority

W każdym przypadku obowiązuje twarda granica tego PR:

- `actuation_supported=false`,
- `actuation_authorized=false`,
- `ACTUATION_AUTHORITY_NOT_IMPLEMENTED` jest zawsze obecny jako końcowy blocker,
- `ready=false`.

Przy kompletnych syntetycznych prerequisite'ach `preconditions_satisfied=true`, ale nadal:

```text
actuation_authorized=false
ready=false
blockers=[ACTUATION_AUTHORITY_NOT_IMPLEMENTED]
```

Wartości używane do kompletnego syntetycznego tuningu są wyłącznie wektorami testowymi i nie stanowią produkcyjnych ustawień warsztatowych.

## Wynik

**PASS**

Gate zachowuje się deterministycznie i fail-closed. Każdy badany brak lub fault jest widoczny jako jawny blocker, a brak authority uniemożliwia `ready=true` nawet przy syntetycznie kompletnych prerequisite'ach.

## Wniosek

Stage8A + Stage8B pozwalają uznać warstwę `Actuation Readiness Gate` za zwalidowaną diagnostycznie. Nie oznacza to gotowości do aktuacji. Następne prace powinny koncentrować się na świadomym tuningu brakujących prerequisite'ów oraz osobnej, późniejszej decyzji architektonicznej o authority.
