# Control Engine V1 Stage3 — macierz cross-domain Calendar × AQ × temperatura × awarie

Data: 2026-08-28
Repozytorium: `autoklinika/workshop-ventilation-controller`
Gałąź: `agent/automation-v1-control-engine`
Kod zwalidowany: `04736ee574681f067eb47921058ca04e43e977dc`
GitHub Actions: `Ventilation Core Tests` run `33158386237`
Wynik: **PASS**

## Cel

Po deterministycznym Scenario / Replay Engine dodano niezależną macierz stanów ustalonych, która sprawdza priorytety Control Engine pomiędzy domenami:

- Calendar,
- jakość powietrza,
- temperatura wewnętrzna,
- awarie i utrata kontekstu.

Macierz korzysta z tego samego `ControlEngineScenarioRunner`, a ten z tego samego `PolicyShadowAutomationEvaluator`, którego używa runtime. Nie istnieje alternatywna logika decyzyjna tylko na potrzeby testu.

## Zakres macierzy

Wersjonowany plik:

`config/control-engine-scenarios/lab-cross-domain-matrix-v1.json`

Wymiary:

- Calendar: 6 wariantów,
- Air Quality: 4 warianty,
- temperatura: 4 warianty,
- fault/context: 10 wariantów.

Łącznie:

`6 × 4 × 4 × 10 = 960` niezależnych przypadków.

Każdy przypadek dostaje nową instancję Scenario Runner / evaluatora, więc stan histerezy i timerów nie przecieka pomiędzy kombinacjami. Macierz bada stany ustalone; confirmation/hold/decay pozostają testowane osobno przez temporalne replaye.

## Calendar

Sprawdzane warianty:

- `inactive_off`,
- `inactive_standby`,
- `preventilation_auto`,
- `active_auto`,
- `purge_auto`,
- `active_fixed`.

## Air Quality

Syntetyczne warianty stanu ustalonego:

- `normal`,
- `boost_voc`,
- `high_voc`,
- `max_voc`.

Wartości służą wyłącznie do deterministycznego testowania progów i nie są tuningiem warsztatowym.

## Temperatura wewnętrzna

Syntetyczne pasma:

- `normal`,
- `limiting`,
- `minimum`,
- `protection`.

## Fault / context

Sprawdzane warianty:

- `none`,
- `sensor1_loss`,
- `sensor2_loss`,
- `both_sensor_loss`,
- `zigbee_supply_stale`,
- `zigbee_supply_offline`,
- `critical_alarm`,
- `output_unknown`,
- `hardware_not_ready`,
- `sensor1_loss_critical`.

## Zweryfikowane reguły priorytetów

### Safety ma najwyższy priorytet

`critical_alarm`, `output_unknown`, `hardware_not_ready` oraz kombinacja utraty SEN55 z critical fault powodują:

- `BLOCKED_SAFETY`,
- `automation_state=FAULT`,
- brak finalnych requestów,
- brak AERO proposal,
- brak physical voltage proposal.

Safety block ma priorytet także nad skonfigurowanym sensor fallback.

### Utrata SEN55 strefy wentylatorów

W aktywnym lifecycle:

- `automation_state=FAULT`,
- stosowany jest jawny fallback,
- Calendar pozostaje dolnym ograniczeniem requestu.

W INACTIVE:

- fallback nie wymyśla wentylacji,
- wynik pozostaje `0/0`.

### Utrata SEN55 strefy AERO

W aktywnym lifecycle:

- jawny AERO fallback speed.

W INACTIVE:

- AERO proposal `0`.

### Temperatura ogranicza tylko dobre powietrze

Przy NORMAL AQ aktywny Calendar request podlega thermal cap.

Przy BOOST/HIGH/MAX AQ:

- thermal cap nie ogranicza requestu,
- air-quality override ma pierwszeństwo.

### Degraded AQ może przebić OFF / STANDBY

Przy INACTIVE/OFF lub INACTIVE/STANDBY i pogorszonym syntetycznym AQ Control Engine nadal proponuje wentylację SHADOW zgodnie z regułą jakości powietrza.

### FIXED Calendar pozostaje baseline

Przy aktywnym FIXED i sensor fallback wyższy Calendar baseline pozostaje dolną granicą requestu.

## Zigbee supply — kontekst V1

Dodano dwa przekrojowe warianty:

- `zigbee_supply_stale`,
- `zigbee_supply_offline`.

W V1 temperatura supply/outside jest nadal kontekstem do `delta_t`, a nie wejściem modyfikującym finalny request wentylatorów.

Macierz wymusza więc następujący kontrakt:

- stale/offline → `outside_temperature_usable=false`,
- stale → `TEMPERATURE_STALE`,
- offline → `ZIGBEE_DEVICE_OFFLINE`,
- `temperature_delta_celsius=null`,
- final supply/extract request oraz `automation_state` pozostają identyczne jak w odpowiadającym przypadku bez faultu Zigbee.

Jeżeli SEN55 #1 jest utracony, zdrowe Zigbee może nadal mieć `outside_temperature_usable=true`, ale `delta_t` pozostaje `null`, ponieważ brakuje wiarygodnej temperatury wewnętrznej. Ten przypadek został jawnie objęty regresją.

## Kontrakt bezpieczeństwa macierzy

Dla wszystkich 960 przypadków:

- `actuation_supported=false`,
- `proposed_supply_voltage=null`,
- `proposed_extract_voltage=null`.

Matrix Runner nie ma portu DAC, GPIO, AERO executor, host-power, socketu sterującego ani systemd.

## CLI

Dodano:

`tools/run_control_engine_matrix.py`

Przykład bounded summary:

```bash
PYTHONPATH=src python3 tools/run_control_engine_matrix.py \
  config/control-engine-scenarios/lab-cross-domain-matrix-v1.json \
  --summary
```

Zwalidowane liczniki dla 960 przypadków:

- `BLOCKED_SAFETY`: 384,
- `DEGRADED`: 288,
- `READY`: 288,
- safety-blocked cases: 384,
- sensor-fallback cases: 192.

## CI

Exact code SHA:

`04736ee574681f067eb47921058ca04e43e977dc`

Workflow:

`Ventilation Core Tests` — run `33158386237`

- Compile sources: PASS,
- Unit tests: PASS,
- Overall: SUCCESS.

## Tuning

Cały tuning użyty przez wersjonowaną macierz jest syntetyczny i służy wyłącznie do testów algorytmicznych w LAB. Nie jest konfiguracją produkcyjną ani rekomendacją dla warsztatu.

## Decyzja

**Stage3 cross-domain matrix PASS.**

Fizyczny test CM5 nie jest wymagany dla tego etapu, ponieważ macierz jest deterministyczną walidacją algorytmu i nie posiada ścieżki aktuacyjnej.
