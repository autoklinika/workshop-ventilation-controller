# Workshop Ventilation Controller — checkpoint integracyjny

Data: 2026-08-03

## 1. Cel checkpointu

Checkpoint zamyka zwalidowany zakres obejmujący:

- firmware KAmod ESP32 POW RS485 + SEN55 Stage 2A,
- odczyt danych SEN55 przez Modbus RTU,
- rozpoznanie interfejsu COMPIT NANO COLOR 2 firmware 6.30,
- odczyt i podstawowe sterowanie rekuperatorem Prodmax / AERO 4A2,
- decyzję o zastosowaniu dwóch niezależnych magistral RS-485,
- dokumentację i narzędzia stanowiskowe potrzebne do kolejnych etapów.

Zakres zostaje zintegrowany przez PR #6 z gałęzi `agent/rekuperator-modbus-control-stage1` do `main`. Gałąź PR #6 zawiera historię i końcowy stan PR #4 oraz PR #5, dlatego jest jednym punktem integracji dla całego checkpointu.

## 2. Stan przed integracją

Bazowy `main` zawiera zwalidowany firmware KAmod + SEN55 Stage 1 oraz wcześniejsze etapy `ventilation-core` i DAC.

Stan gałęzi integracyjnej przed dodaniem niniejszego raportu:

```text
agent/rekuperator-modbus-control-stage1
HEAD: c9ce59c7578ae9dd291179c7632b001d9fd056e6
PR: #6
```

Walidacja GitHub Actions dla tego HEAD:

- `Ventilation Core Tests` — success,
- `Sensor node firmware` — success.

## 3. Zakończony zakres SEN55 Stage 2A

Potwierdzono firmware `0.2.0-stage2` dla KAmod ESP32 POW RS485 + SEN55.

Kontrakt magistrali czujników:

```text
Modbus RTU slave
19200 bit/s
8N1
slave 1
FC04 Read Input Registers
mapa rejestrów: wersja 1
adresy: 0..18
brak funkcji zapisu
```

Dostępne dane:

- PM1.0,
- PM2.5,
- PM4.0,
- PM10,
- wilgotność,
- temperatura,
- VOC Index,
- NOx Index,
- maska dostępności,
- stan węzła,
- wiek pomiaru,
- liczniki błędów,
- uptime,
- wersja firmware,
- wersja mapy,
- sekwencja pomiaru.

Walidacja fizyczna objęła między innymi:

- odczyt wszystkich 19 rejestrów,
- kontrolę skalowania i signed temperature,
- stan poprawnego pomiaru,
- odłączenie i ponowne podłączenie SEN55,
- automatyczne odzyskanie pomiarów,
- zimny start,
- minimum 30 minut ciągłego odpytywania,
- brak timeoutów i błędów CRC,
- odrzucenie próby zapisu FC06.

Szczegóły:

- `docs/MODBUS_MAP_PL.md`,
- `docs/reports/KAMOD_MODBUS_STAGE2_IMPLEMENTATION_PL.md`.

## 4. Zakończony zakres rekuperatora

Zidentyfikowany sprzęt:

- Prodmax PRO MINI 300 H/V CLASSIC + WiFi,
- oznaczenie PRO MINI 300HV-C/WIFI,
- sterownik COMPIT AERO 4A2,
- panel COMPIT NANO COLOR 2,
- firmware panelu 6.30.

Potwierdzony kontrakt Modbus:

```text
Modbus RTU slave
9600 bit/s
8N1
slave 44
FC03 Read Holding Registers
FC06 Write Single Register
```

Potwierdzona telemetria:

| Adres PDU | Znaczenie | Kodowanie |
|---:|---|---|
| 2016 | wilgotność | raw / 10 = % RH |
| 2021 | temperatura nawiewu | signed raw / 10 = °C |
| 2022 | temperatura wywiewu | signed raw / 10 = °C |
| 2023 | temperatura czerpni | signed raw / 10 = °C |
| 2033 | moc wentylatora 1 | raw = % |
| 2034 | moc wentylatora 2 | raw = % |

Nie ustalono jeszcze, który z adresów 2033/2034 odpowiada nawiewowi, a który wywiewowi. Do czasu osobnej identyfikacji używamy nazw neutralnych `fan_1` i `fan_2`.

Potwierdzone sterowanie:

| Adres PDU | Funkcja | Zakres zwalidowany |
|---:|---|---|
| 1080 | wybór biegu | 0..3 |
| 1081 | wietrzenie | 0/1 |

Zaliczone:

- poprawne echo FC06,
- readback FC03,
- fizyczna zmiana biegu,
- wietrzenie ON/OFF,
- automatyczne przywrócenie poprzedniej wartości,
- obserwacja mocy wentylatorów.

## 5. Krytyczna cecha AERO

AERO 4A2 może wykonać prawidłowo przyjęte polecenie dopiero po około 30 sekundach.

Obowiązuje rozdzielenie:

1. poprawna transmisja i CRC,
2. echo FC06,
3. readback wartości z NANO,
4. fizyczna reakcja AERO potwierdzona telemetrią.

Założenia przyszłego adaptera:

```text
execution_timeout = 45 s
telemetry_poll_interval = 2 s
```

Echo FC06 ani szybki readback nie są dowodem fizycznego wykonania polecenia.

## 6. Docelowy podział magistral

Podjęto decyzję o niewłączaniu rekuperatora do magistrali czujników.

Docelowa architektura:

```text
RS-485 SENSOR BUS
CM5 / izolowany interfejs RS-485
    ├── KAmod + SEN55 #1
    └── KAmod + SEN55 #2

19200 bit/s, 8N1, FC04
```

```text
RS-485 AERO BUS
CM5 / drugi izolowany interfejs RS-485
    └── NANO COLOR 2 v6.30 / AERO 4A2

9600 bit/s, 8N1, slave 44, FC03/FC06
```

Każda magistrala otrzyma:

- osobny izolowany interfejs,
- osobny port systemowy,
- trwałą nazwę `udev`,
- osobnego workera lub adapter,
- własny harmonogram odpytywania,
- własne timeouty i diagnostykę.

Bezwładność AERO nie może wpływać na świeżość danych SEN55.

## 7. Obowiązujące zasady bezpieczeństwa

- AERO pozostaje nadrzędnym sterownikiem rekuperatora,
- CM5 nie steruje bezpośrednio wentylatorami ani zabezpieczeniami AERO,
- nie reverse-engineerujemy C14,
- nie podłączamy drugiego mastera do C14,
- dynamiczne sterowanie AERO używa wyłącznie potwierdzonych rejestrów RAM,
- nie używamy EEPROM do cyklicznej automatyki,
- nie zapisujemy adresów o niepotwierdzonym znaczeniu,
- awaria CM5 nie może blokować lokalnego panelu ani pracy AERO,
- magistrala czujników pozostaje read-only dla urządzeń Stage 2A,
- GUI, MQTT i AI nie mogą bezpośrednio otwierać portów ani wykonywać zapisów Modbus.

## 8. Narzędzia zapisane w repo

### SEN55

- `tools/read_modbus_sensor.py` — odczyt mapy czujnika FC04 i diagnostyka.

### NANO / AERO

- `tools/compit_nano_v630_discovery.py` — surowe snapshoty i diff,
- `tools/compit_nano_v630_labeled_read.py` — czytelny odczyt telemetrii,
- `tools/compit_nano_v630_control_test.py` — kontrolowane testy FC06 z readbackiem i obserwacją fizycznej reakcji.

## 9. Dokumentacja bazowa po checkpoincie

- `docs/DECISIONS_PL.md`,
- `docs/MODBUS_MAP_PL.md`,
- `docs/COMPIT_AERO4A2_INTEGRATION_PL.md`,
- `docs/reports/KAMOD_MODBUS_STAGE2_IMPLEMENTATION_PL.md`,
- `docs/reports/COMPIT_NANO_V630_CONTROL_VALIDATION_PL.md`,
- `docs/reports/COMPIT_NANO_V630_CONTROL_STAGE1_HANDOFF_NEXT_STAGE_PL.md`,
- `docs/reports/VENTILATION_CONTROLLER_CHECKPOINT_2026-08-03_PL.md`.

## 10. Następny etap

Następny etap to **SEN55 Modbus Stage 2B — dwa węzły na jednej, oddzielnej magistrali czujników**.

Zakres Stage 2B:

- utrzymać `19200 bit/s`, `8N1` i mapę tylko do odczytu,
- nadać dwóm węzłom unikalne, trwałe adresy `1` i `2`,
- nie dodawać rekuperatora do tej magistrali,
- nie dodawać zdalnego zapisu konfiguracji Modbus bez osobnej decyzji,
- przetestować oba węzły jednocześnie,
- sprawdzić odłączenie jednego węzła bez wpływu na drugi,
- sprawdzić błędny adres i brak odpowiedzi,
- przeprowadzić dłuższe odpytywanie bez timeoutów i błędów CRC,
- potwierdzić topologię liniową i terminację,
- zaktualizować CI, dokumentację, raport fizycznej walidacji i handoff.

## 11. Kryterium zakończenia Stage 2B

Etap można zakończyć dopiero po:

- testach jednostkowych i buildzie ESP-IDF,
- sukcesie obu workflowów CI,
- odczycie obu urządzeń na jednej magistrali,
- potwierdzeniu adresów `1` i `2`,
- potwierdzeniu niezależnego działania przy utracie jednego węzła,
- dłuższym teście stabilności,
- pełnym raporcie implementacyjnym i sprzętowym,
- przygotowaniu następnego handoffu.

## 12. Stan organizacyjny

PR #6 jest checkpointem integracyjnym tego zakresu. Po jego scaleniu kolejne prace należy rozpocząć z aktualnego `main`, po wcześniejszym sprawdzeniu rzeczywistego HEAD oraz stanu pozostałych PR-ów.
