# SHADOW Policy V1 — implementacja Stage 1

## Status

Dokument opisuje implementację deterministycznej, nieaktuującej polityki SHADOW na branchu `agent/schedules-history-automation-stage1`.

Źródłem założeń jest istniejący dokument produkcyjny:

- `docs/ZALOZENIA_AUTOMATYKI_PL.md`.

SHADOW pozostaje warstwą obserwacyjną. `actuation_supported=false` jest częścią kontraktu i żadna decyzja SHADOW nie jest przekazywana do DAC ani AERO.

## Wersja polityki

Kod używa identyfikatora:

`shadow-policy-v1-2026-08-12`

Implementacja znajduje się w:

- `src/ventilation_core/domain/shadow_policy.py`,
- `src/ventilation_core/application/shadow_controller.py`,
- `src/ventilation_core/domain/shadow.py`.

## Progi jakości powietrza

### PM2.5

Zgodnie ze źródłowym zapisem procesowym:

- `<= 15 µg/m³` -> `NORMAL`,
- `> 15 µg/m³` -> `BOOST`,
- `> 25 µg/m³` -> `HIGH`,
- `> 50 µg/m³` -> `MAX`.

Dla pierwszego progu dokument wymaga potwierdzenia przekroczenia przez określony czas, ale czas nie został jeszcze ustalony. Dlatego SHADOW klasyfikuje chwilowy poziom, a dla przypadku PM2.5/BOOST raportuje `PM2_5_BOOST_CONFIRMATION_TUNING_REQUIRED`, dopóki parametr czasu potwierdzenia nie zostanie skonfigurowany.

### VOC Index

Zakodowane zakresy:

- `< 150` -> `NORMAL`,
- `150.. <200` -> `BOOST`,
- `200..300` -> `HIGH`,
- `> 300` -> `MAX`.

VOC Index pozostaje wskaźnikiem względnym Sensiriona, a nie pomiarem toksykologicznym.

### NOx Index

Zgodnie z zapisanymi progami procesowymi:

- `<= 10` -> `NORMAL`,
- `> 10` -> `BOOST`,
- `> 50` -> `HIGH`,
- `> 100` -> `MAX`.

### PM10

`45 µg/m³` jest przechowywane jako punkt referencyjny i SHADOW publikuje `pm10_reference_exceeded`.

Nie dodano własnej tabeli `BOOST/HIGH/MAX` dla PM10, ponieważ źródłowy dokument takiej tabeli nie definiuje. Nie należy jej wymyślać bez kolejnej decyzji projektowej lub strojenia na danych.

## Temperatura

Dla `zone-1` — pomieszczenia bez rekuperatora — zakodowano strefy temperatury wewnętrznej:

- `>20°C` -> `NORMAL`,
- `18..20°C` -> `LIMITING`,
- `16..<18°C` -> `MINIMUM`,
- `<16°C` -> `PROTECTION`.

Dla `zone-2` z rekuperatorem lokalny thermal limiter otrzymuje `NOT_APPLICABLE`.

Temperatura zewnętrzna / temperatura powietrza nawiewanego jest przewidziana w kontrakcie SHADOW jako `outside_temperature_celsius`, ale pozostaje `null` do czasu integracji rzeczywistego toru pomiarowego Zigbee. Nie jest zastępowana pogodą internetową ani wartością syntetyczną.

## Priorytet decyzji

Zachowana jest zasada projektowa:

`BEZPIECZEŃSTWO > JAKOŚĆ POWIETRZA > TEMPERATURA / ENERGIA`.

Jeżeli jakość powietrza jest powyżej `NORMAL`, a temperatura `zone-1` znajduje się w ograniczającej strefie cieplnej, SHADOW raportuje:

`LOW_TEMPERATURE + AIR_QUALITY_OVERRIDE`

oraz `air_quality_override=true`.

Oznacza to, że przyszła aktywna automatyka nie może obniżyć wymiany wymaganej przez jakość powietrza wyłącznie z powodu temperatury.

## AIR_REQUEST i TEMP_LIMIT

SHADOW publikuje osobno:

- `air_quality_level`,
- `air_quality_driver`,
- `air_request_pct`,
- `thermal_band`,
- `temperature_limit_pct`,
- `final_supply_pct`,
- `final_extract_pct`,
- `proposed_aero_speed`,
- `control_reason`.

Dzięki temu źródło decyzji pozostaje jawne w CoreState, telemetrii lokalnej i archiwum AI.

## Parametry strojenia

`ShadowOutputTuning` zawiera jawne parametry dla:

- NORMAL / BOOST / HIGH / MAX w procentach dla wentylatorów,
- limitów cieplnych NORMAL / LIMITING / MINIMUM / PROTECTION,
- różnicy wyciąg względem nawiewu,
- poziomów AERO 0/1/2/3,
- histerezy PM2.5,
- histerezy VOC Index,
- histerezy NOx Index,
- histerezy temperatury,
- czasu potwierdzenia PM2.5 BOOST,
- minimalnego czasu utrzymania stanu,
- czasu wygaszania BOOST.

Produkcja Stage 1 pozostawia wszystkie te wartości jako `None`. W efekcie:

- progi procesowe i klasyfikacja działają,
- `policy_version` jest publikowane,
- wynik ma status `TUNING_REQUIRED`, jeżeli wejścia są poprawne,
- nie są generowane przypadkowe procenty ani nastawy AERO,
- `tuning_complete=false`.

Parametry mają walidację zakresów i monotoniczności. Tuning wentylatorów i AERO może być wykonywany niezależnie.

## Brak aktuacji

Nawet po wypełnieniu testowego tuningu:

- `actuation_supported=false`,
- SHADOW nie wywołuje `set_manual`,
- SHADOW nie wywołuje `control_aero`,
- SHADOW nie zapisuje do DAC,
- SHADOW nie wysyła Modbus control do AERO.

Testowy tuning służy wyłącznie do wyliczania i rejestrowania propozycji do późniejszego porównania z rzeczywistym zachowaniem systemu.

## Testy

Testy obejmują:

- wartości dokładnie na progach i tuż powyżej progów PM2.5/VOC/NOx,
- strefy temperatury,
- wybór najwyższego żądania jakości powietrza,
- diagnostyczne PM10 bez wymyślonej tabeli sterowania,
- `LOW_TEMPERATURE + AIR_QUALITY_OVERRIDE`,
- brak proponowanych wyjść przy niewypełnionym tuningu,
- przykładowy tuning wyłącznie testowy,
- walidację procentów, AERO, histerez i czasów,
- monotoniczność kolejnych poziomów sterowania.

GitHub Actions `Ventilation Core Tests` dla implementacji zakończył się `SUCCESS`.

## Następny krok

Następnym krokiem nie jest aktywne AUTO. Należy:

1. zwalidować publikację Policy V1 na rzeczywistym CoreState CM5,
2. rozpocząć zbieranie SHADOW decyzji razem z historią,
3. po zebraniu danych ustalić pierwsze konserwatywne wartości procentów, histerez i czasów,
4. dodać command-vs-TACHO diagnostics przed jakąkolwiek aktywną automatyką wentylatorów,
5. aktywne AUTO rozważać dopiero po analizie zachowania SHADOW i walidacji bezpieczeństwa.
