# Plan realizacji

## Etap 0 — Platforma CM5 i uruchamianie peryferiów

Status: **zakończony dla bazowego uruchomienia CM5 i DFR0971**.

- Raspberry Pi Compute Module 5 Wireless 4 GB / 32 GB eMMC uruchomiony,
- Raspberry Pi OS Lite 64-bit / Debian 13 zainstalowany na eMMC,
- repozytorium uruchomione na CM5,
- DFRobot DFR0971 2 × 0–10 V zwalidowany,
- oba kanały DAC sprawdzone,
- pierwszy wentylator EC przeszedł testy przy 1 V, 2 V, 5 V, 8 V i 10 V,
- `ventilation-core` Stage 1 działa jako warstwowy rdzeń z osobnym workerem sprzętowym,
- usługa `systemd` i bezpieczny start w stanie STOP zostały zwalidowane.

## Etap 1 — Zamknięcie koncepcji sprzętowej

Status: **w toku**.

Pozostaje:

- potwierdzenie modelu drugiego wentylatora,
- dobór docelowego zasilacza DIN,
- sprawdzenie Tacho,
- potwierdzenie pinoutu złączy RJ45 Keystone używanych jako złącza nie-Ethernetowe,
- zamknięcie zasilania dwóch modułów DFR0845,
- potwierdzenie budżetu prądowego szyn 12 V, 5 V i 3,3 V,
- końcowy schemat dwóch oddzielnych magistral RS-485.

## Etap 2 — Węzły pomiarowe SEN55

Status: **zakończony i zwalidowany sprzętowo 2026-08-04**.

### Stage 1 — SEN55 po I²C

Status: **zakończony 2026-08-03**.

- KAmod ESP32 POW RS485 + SEN55,
- komunikacja I²C,
- odczyt wszystkich wymaganych wartości,
- walidacja CRC,
- utrata i automatyczny powrót czujnika,
- zimny start i restart,
- partycje OTA A/B oraz rollback.

### Stage 2A — Modbus RTU read-only

Status: **zakończony i zwalidowany sprzętowo 2026-08-03**.

Potwierdzony kontrakt:

```text
slave 1
19200 bit/s
8N1
FC04
mapa v1
19 Input Registers
brak funkcji zapisu
```

Zaliczone:

- pełny odczyt mapy,
- zgodność z logiem USB,
- poprawne statusy po utracie SEN55,
- automatyczny powrót,
- zimny start,
- minimum 30 minut stabilnego odpytywania,
- odrzucenie FC06,
- `modbus_errors=0`.

### Stage 2B — konfiguracja i dwa węzły

Status: **zakończony, zwalidowany sprzętowo i scalony przez PR #7 w dniu 2026-08-04**.

- jeden wspólny firmware `0.3.0-stage2b`,
- trwałe adresy w NVS,
- slave `1` i `2`,
- lokalny provisioning przez USB,
- wspólna magistrala SENSOR BUS,
- niezależna diagnostyka obu urządzeń,
- domyślna przerwa 10 ms między transakcjami,
- 800/800 poprawnych odpytań w obu kolejnościach,
- brak timeoutów, invalid, stale i błędów mapy.

Dokument końcowy:

```text
docs/reports/SEN55_MODBUS_STAGE2B_FINAL_REPORT_AND_CM5_SENSOR_BUS_HANDOFF_PL.md
```

## Etap 3 — Sterowanie wentylatorami

Status: **częściowo zakończony**.

Zrealizowano:

- uruchomienie DAC 0–10 V,
- niezależne kanały nawiewu i wyciągu,
- ręczne sterowanie przez `ventilationctl`,
- bezpieczny STOP,
- nadzór komunikacji z DAC,
- tryb FAULT i automatyczny powrót do STOP,
- restart usługi i reboot CM5 bez samoczynnego uruchomienia wentylatora.

Pozostaje:

- pomiar rzeczywistej charakterystyki obu wentylatorów,
- ustalenie minimalnego napięcia startu,
- odczyt Tacho,
- finalny bilans nawiew–wyciąg.

## Etap 4 — Integracja magistral RS-485 z `ventilation-core`

Status: **następny główny etap**.

### Stage 1 — zasilanie i bring-up DFR0845

Pierwszy problem do zamknięcia:

- dwa moduły DFR0845 dla dwóch oddzielnych magistral,
- braki magazynowe wcześniej rozważanych konwerterów 3,3 V,
- wybór bezpiecznego sposobu zasilania strony UART,
- sprawdzenie poboru prądu i poziomów TX/RX,
- zachowanie izolacji galwanicznej,
- gotowy schemat oraz lista elementów.

Prompt startowy:

```text
docs/reports/CM5_DFR0845_POWER_AND_SENSOR_BUS_STAGE1_START_PROMPT_PL.md
```

### Stage 2 — CM5 SENSOR BUS worker

- osobny `sensor_bus_worker`,
- wyłączna własność portu UART/RS-485,
- trwała nazwa portu,
- odczyt slave `1` i `2`,
- 10 ms przerwy pomiędzy węzłami,
- walidacja mapy, statusów, wieku i maski dostępności,
- niezależne błędy i odzyskiwanie per węzeł,
- normalizowany model danych,
- integracja z autorytatywnym stanem rdzenia,
- diagnostyka przez `ventilationctl`,
- testy na rzeczywistym CM5 i pod `systemd`.

### Stage 3 — CM5 AERO BUS worker

- osobny drugi DFR0845,
- osobna magistrala,
- `9600 bit/s`, `8N1`, slave `44`,
- FC03 i kontrolowane FC06,
- asynchroniczne potwierdzanie fizycznego wykonania,
- `execution_timeout = 45 s`,
- bez wpływu bezwładności AERO na SENSOR BUS.

## Etap 5 — Pierwsza automatyka jakości powietrza

- przypisanie czujników do stref,
- warstwa oceny jakości powietrza,
- podstawowe stany ECO, AUTO, PRZEWIETRZANIE i BOOST,
- histerezy i opóźnienia,
- reakcja na utratę czujnika,
- lokalny dziennik decyzji,
- brak zależności od GUI i MQTT.

## Etap 6 — Instalacja próbna

- montaż w rozdzielni,
- montaż czujników w pomieszczeniach,
- test komunikacji na docelowych przewodach,
- obserwacja VOC, PM, temperatury i wilgotności,
- sprawdzenie bilansu nawiew–wyciąg,
- weryfikacja hałasu i wydajności.

## Etap 7 — Strojenie logiki

- harmonogram przewietrzania,
- czas przewietrzania po pracy,
- progi i histerezy,
- reakcja na brak Tacho,
- opcjonalne wejścia „myjka pracuje” i „piec pracuje”,
- walidacja zachowania w rzeczywistych warunkach.

## Etap 8 — Wersja docelowa

- uporządkowany schemat elektryczny,
- docelowe obudowy i uchwyty,
- oznaczenia przewodów i złączy,
- instrukcja montażu i uruchomienia,
- kopia konfiguracji,
- raport z testów końcowych.

## Najbliższe punkty kontrolne

1. rozstrzygnięcie zasilania dwóch DFR0845,
2. schemat i pomiary stanowiskowe jednego DFR0845,
3. potwierdzenie bezpiecznych poziomów UART CM5,
4. przygotowanie gałęzi `agent/cm5-sensor-bus-worker-stage1`,
5. implementacja i walidacja `sensor_bus_worker`,
6. dopiero potem osobny worker AERO BUS.
