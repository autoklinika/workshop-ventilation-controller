# Integration Stage 1 — walidacja laboratoryjna CM5

Data: 2026-08-18

## Wynik

**PASS** — zintegrowana gałąź `agent/integration-stage1` została zwalidowana na CM5 z rzeczywistym sprzętem i działającym stosem Zigbee.

Walidowany HEAD przed raportem:

`1f5b8b9bfc4a10b38f45566a05b1fbcde71a70d3`

Walidator:

`tools/validate_integration_stage1_cm5.sh`

## Zakres

Walidacja objęła jednoczesne działanie:

- pełnego zestawu testów jednostkowych i kontraktowych,
- SENSOR / SEN55,
- AERO,
- TACHO,
- Zigbee2MQTT + Mosquitto + ventilation-core,
- trzech urządzeń Zigbee i ich ról,
- retained telemetry,
- harmonogramu,
- SHADOW Policy V1,
- lokalnego capture telemetrii,
- historii i read-only Web API,
- wspólnej strony `USTAWIENIA` zawierającej Zigbee oraz harmonogram,
- bezpiecznego przywrócenia produkcji.

## Test suite

Pełny zestaw testów:

`Ran 353 tests in 0.199s`

`OK`

Logi oczekiwanych scenariuszy błędowych w testach (m.in. DAC/AERO/TACHO/SENSOR, niedostępna baza harmonogramu oraz timeout przy usuwaniu śpiącego urządzenia Zigbee) były generowane przez testy negatywne i nie oznaczały awarii walidacji.

## Stan przed testem

Produkcyjny core:

- `STOP`,
- 0 V / 0 V,
- Zigbee online,
- `permit_join=false`.

Usługi produkcyjne zostały bezpiecznie wstrzymane na czas testowego core.

## Zintegrowany core — real hardware + Zigbee

Wspólny core poprawnie uruchomił jednocześnie SENSOR/AERO/TACHO oraz Zigbee.

Potwierdzono:

- inventory Zigbee,
- `sensor_list`,
- role `supply`, `extract`, `other`,
- retained telemetry.

Odczyty podczas walidacji:

- `temp_nawiew`: 21.1 °C,
- `temp_wywiew`: 21.8 °C,
- `temp_zew`: 24.38 °C,
- `temp_zew` RH: 49.4 %.

W logu pojawił się pojedynczy `AssertionError` podczas pętli oczekującej na pełne osiągnięcie stanu ready przez testowy core. Była to przejściowa niegotowość jednego z warunków pollingu; pętla ponowiła sprawdzenie, następnie cały blok osiągnął PASS. Nie był to błąd końcowy ani obejście kryterium walidacji.

## Schedule + SHADOW

W tym samym `CoreState` potwierdzono współistnienie:

- harmonogramu,
- SHADOW,
- Zigbee.

SHADOW pozostał nieaktuujący:

- `actuation_supported=false`,
- wyjścia pozostały `STOP / 0 V`.

## Historia i telemetria

Jednorazowy capture pełnego zintegrowanego `CoreState` został poprawnie zapisany do lokalnej bazy telemetrycznej przy wyłączonej synchronizacji zdalnej.

Web API poprawnie udostępniło:

- state,
- Zigbee,
- schedule,
- history.

## GUI

Potwierdzono jeden endpoint/ekran `/settings`, na którym współistnieją:

- zarządzanie i telemetria Zigbee,
- edytor harmonogramu.

## Bezpieczeństwo i brak mutacji

Podczas testu:

- nie wykonywano aktuacji,
- stan pozostał `STOP / 0 V`,
- `permit_join=false`,
- wszystkie 3 urządzenia pozostały sparowane,
- produkcyjny rejestr ról Zigbee nie został zmieniony.

## Przywrócenie produkcji

Po walidacji poprawnie przywrócono:

- `ventilation-core.service` — active,
- `wvc-telemetry-sync.service` — active,
- `wvc-web-ui.service` — active.

Produkcyjny core po restore:

- `STOP`,
- 0 V / 0 V,
- hardware ready,
- rejestr ról Zigbee bez zmian.

## Wynik końcowy

```text
INTEGRATION STAGE 1 — CM5 LAB VALIDATION: PASS
Zigbee:                    PASS
schedule + SHADOW:         PASS
history capture/API:       PASS
GUI settings integration:  PASS
real hardware:              PASS
actuation during test:      NONE / STOP 0 V
production restored:        PASS
```

Na podstawie tej walidacji Integration Stage 1 kwalifikuje się do przygotowania merge do `main`.