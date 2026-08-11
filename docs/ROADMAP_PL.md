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
- końcowy schemat dwóch oddzielnych magistral RS-485,
- końcowe uporządkowanie dokumentacji zasilania i oznaczeń przewodów.

Zasilanie i bring-up dwóch DFR0845 zostały praktycznie zamknięte podczas uruchamiania produkcyjnych SENSOR BUS i AERO BUS.

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

## Etap 3 — Sterowanie wentylatorami EC przez DAC

Status: **produkcyjna ścieżka ręczna zakończona; strojenie charakterystyki pozostaje**.

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
- ewentualna korekta minimalnego napięcia użytkowego,
- odczyt Tacho,
- finalny bilans nawiew–wyciąg.

## Etap 4 — Integracja magistral RS-485 z `ventilation-core`

Status: **zakończony i zwalidowany sprzętowo 2026-08-11**.

### Stage 4A — CM5 SENSOR BUS

Status: **PASS**.

- `/dev/ttyAMA0`, Modbus RTU 19200 8N1,
- slave `1` i `2`,
- `sensor_bus_worker` jako jedyny właściciel UART,
- mapa SEN55 v1,
- niezależne błędy i recovery per węzeł,
- normalizowany stan w `CoreState`,
- izolacja awarii SENSOR BUS od DAC i AERO.

### Stage 4B — CM5 AERO BUS telemetria

Status: **PASS**.

- `/dev/ttyAMA4`, Modbus RTU 9600 8N1, slave `44`,
- `aero_bus_worker` jako jedyny właściciel UART,
- sześć osobnych odczytów FC03,
- telemetria NANO/AERO porównana z panelem,
- niezależna domena błędów i automatyczny recovery.

### Stage 4C — produkcyjne sterowanie AERO

Status: **PASS / PR #19 / main `e689a991f9e71bf77f1771ca2cec31cd9b5716f6`**.

- FC06 tylko dla ADR `1080` i `1081`,
- exact echo,
- FC03 readback,
- osobne potwierdzenie fizyczne przez `2033/2034`,
- timeout 60 s i polling 2 s,
- rollback poprzedniej wartości przy błędzie,
- pojedyncza kolejka komend,
- brak wpływu awarii AERO na SENSOR BUS i DAC.

Dokument końcowy:

```text
docs/reports/CM5_AERO_BUS_STAGE3B_FINAL_REPORT_AND_HANDOFF_PL.md
```

## Etap 5 — Web GUI + ręczne sterowanie

Status: **w realizacji od 2026-08-11**.

Cel etapu:

- jedno responsywne GUI webowe dla komputera, telefonu/tabletu i przyszłego panelu dotykowego w trybie kiosk,
- brak osobnej logiki sterowania w GUI,
- GUI jako klient autorytatywnego `ventilation-core`,
- duże elementy dotykowe i brak funkcji zależnych wyłącznie od myszy,
- normalny ekran operatorski oddzielony od przyszłego trybu serwisowego.

### Stage 5A — Web GUI Manual Control Stage 1

Zakres:

- bieżący stan dwóch węzłów SEN55,
- PM2.5, PM10, VOC, NOx, temperatura i wilgotność,
- ręczne ustawienie obu kanałów DAC 0–10 V i jawny STOP,
- AERO speed `0/1/2/3`,
- AERO airing `on/off`,
- pokazywanie rzeczywiście potwierdzonego stanu zamiast optymistycznego stanu przycisku,
- obsługa `control_busy` oraz wyniku fizycznego potwierdzenia AERO,
- status Core/DAC, SENSOR BUS i AERO BUS,
- konfiguracja mapowania adresów SENSOR BUS na nazwy stref bez zmiany firmware,
- osobna usługa `wvc-web-ui.service`, która nie otwiera UART ani I²C i komunikuje się tylko z Unix socketem core.

Świadomie poza zakresem Stage 5A:

- AUTO,
- progi jakości powietrza,
- BOOST zależny od czujników,
- harmonogramy,
- automatyczne decyzje AI,
- MQTT control,
- bezpośredni dostęp GUI do Modbus/DAC.

## Etap 6 — Instalacja próbna i eksploatacja ręczna

- montaż w rozdzielni i docelowych pomieszczeniach,
- test komunikacji na docelowych przewodach,
- codzienna obserwacja VOC, PM, temperatury i wilgotności przez GUI,
- ręczne sprawdzanie różnych ustawień DAC i AERO,
- sprawdzenie bilansu nawiew–wyciąg,
- weryfikacja hałasu, bezwładności i realnej skuteczności przewietrzania,
- zebranie danych potrzebnych do późniejszej automatyki.

## Etap 7 — Automatyka jakości powietrza — później

Automatyka jest świadomie odłożona do czasu zebrania doświadczeń z ręcznej eksploatacji.

Dopiero w tym etapie zostaną ustalone i wdrożone:

- warstwa oceny jakości powietrza,
- progi i histerezy,
- tryby AUTO / BOOST / przewietrzanie,
- harmonogramy,
- reakcje na utratę czujnika,
- priorytety manual / auto / safety,
- lokalny dziennik wyjaśnialnych decyzji.

AI pozostaje advisory-only również po uruchomieniu automatyki deterministycznej.

## Etap 8 — Wersja docelowa

- uporządkowany schemat elektryczny,
- docelowe obudowy i uchwyty,
- oznaczenia przewodów i złączy,
- instrukcja montażu i uruchomienia,
- kopia konfiguracji,
- raport z testów końcowych.

## Najbliższe punkty kontrolne

1. implementacja Web GUI Manual Control Stage 1,
2. lokalne testy regresyjne bez restartu produkcyjnego core,
3. instalacja `wvc-web-ui.service` na CM5,
4. walidacja odczytu dashboardu na rzeczywistych danych,
5. kontrolowane testy ręcznych poleceń DAC i AERO z GUI,
6. test na desktopie i urządzeniu dotykowym / trybie kiosk,
7. dopiero po okresie ręcznej eksploatacji planowanie automatyki.
