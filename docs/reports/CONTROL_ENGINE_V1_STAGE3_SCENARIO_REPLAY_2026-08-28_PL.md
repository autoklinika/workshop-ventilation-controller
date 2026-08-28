# Control Engine V1 Stage3 — deterministyczny Scenario / Replay Engine

Data: 2026-08-28
Repozytorium: `autoklinika/workshop-ventilation-controller`
Gałąź: `agent/automation-v1-control-engine`
Stage3 HEAD: `1a266b979d877bd585554989fda2260fe10174b4`
GitHub Actions: `Ventilation Core Tests` run `33156336071`
Wynik CI: **PASS**

## Cel

Stage3 powstał po fizycznym PASS Stage2. LAB służy do walidacji toru danych i algorytmu, ale nie do strojenia parametrów warsztatowych na aktualnych odczytach środowiskowych.

Scenario / Replay Engine umożliwia uruchamianie tego samego `PolicyShadowAutomationEvaluator`, którego używa runtime, na kontrolowanych syntetycznych snapshotach `CoreState` i kontrolowanym zegarze.

Nie istnieje alternatywna logika decyzji testowej. Runner dostarcza wyłącznie wejścia i czas; decyzję liczy produkcyjny Control Engine SHADOW.

## Dodane elementy

- `src/ventilation_core/application/control_engine_scenario.py`
- `tools/run_control_engine_scenario.py`
- `config/control-engine-scenarios/lab-dynamics-v1.json`
- `tests/test_control_engine_scenario.py`
- `tests/test_control_engine_scenario_cli.py`

## Kontrakt bezpieczeństwa

Scenario Runner:
- nie ma portu DAC,
- nie ma AERO executora,
- nie ma GPIO,
- nie używa `/dev/tty*`,
- nie używa `systemctl`,
- nie używa host-power,
- nie ma shutdown/reboot/poweroff,
- wymaga `actuation_supported=false`,
- wymaga `proposed_supply_voltage=null`,
- wymaga `proposed_extract_voltage=null`.

Może zwracać procentowe i AERO-speed **propozycje SHADOW**, ale nigdy ich nie wykonuje.

## Ścisły format scenariusza

Scenariusz zawiera:
- `schema_version=1`,
- nazwę,
- timezone-aware `start_utc`,
- pełny `ControlEngineConfig`,
- listę kroków z monotonicznym `at_seconds`,
- kontekst Calendar,
- syntetyczny SEN55 strefy 1,
- syntetyczny SEN55 strefy 2,
- syntetyczny Zigbee supply/extract,
- opcjonalny hardware/output safety state,
- opcjonalny critical safety alarm.

Nieznane pola oraz coercion typów są odrzucane.

## Zakres zwalidowanych scenariuszy

### PM2.5 BOOST confirmation
Syntetycznie zweryfikowano:
- PM2.5 przekracza próg BOOST,
- `raw_air_quality_level=BOOST`,
- efektywny poziom pozostaje NORMAL podczas okna confirmation,
- po 30 s utrzymania następuje `ESCALATION_CONFIRMED`.

### Natychmiastowy HIGH
Syntetyczny VOC HIGH powoduje natychmiastową eskalację do HIGH bez opóźnienia.

### Minimum hold + delayed decay
Po HIGH i powrocie wejść do NORMAL:
- minimum hold 60 s utrzymuje stan HIGH,
- następnie rozpoczyna się 120 s decay,
- po decay następuje potwierdzona deeskalacja do NORMAL.

### Thermal cap
Przy dobrym powietrzu i syntetycznej niskiej temperaturze:
- thermal band ogranicza końcowy request fan-zone.

### Air-quality override
Przy jednoczesnym niskim thermal band i HIGH air quality:
- air-quality override ma priorytet nad oszczędzaniem ciepła.

### Utrata SEN55
W aktywnym lifecycle:
- stan FAULT,
- jawny skonfigurowany fallback SHADOW.

W INACTIVE:
- brak wymyślania wentylacji po utracie SEN55,
- request 0/0.

### Safety block
Critical safety fault:
- `BLOCKED_SAFETY`,
- brak końcowych requestów,
- brak AERO proposal,
- brak physical voltage proposal.

### Zigbee freshness
Replay obejmuje:
- fresh -> `OK`, usable, delta_t,
- stale -> `TEMPERATURE_STALE`, unusable, delta_t null,
- brak timestampu -> `TEMPERATURE_TIMESTAMP_UNAVAILABLE`, unusable.

## Wersjonowany scenariusz LAB

`config/control-engine-scenarios/lab-dynamics-v1.json` zawiera wyłącznie syntetyczne wartości i tuning laboratoryjny. Nie jest to konfiguracja produkcyjna i nie stanowi rekomendacji dla warsztatu.

Uruchomienie developerskie:

```bash
PYTHONPATH=src python3 tools/run_control_engine_scenario.py \
  config/control-engine-scenarios/lab-dynamics-v1.json
```

## CI

Exact SHA:
`1a266b979d877bd585554989fda2260fe10174b4`

Workflow:
`Ventilation Core Tests` — run `33156336071`

- Compile sources: PASS
- Unit tests: PASS
- Overall: SUCCESS

## Decyzja

**Stage3 PASS.**

Nie jest wymagany test fizyczny CM5, ponieważ ten etap ma być deterministyczny, syntetyczny i całkowicie odłączony od aktuatorów.
