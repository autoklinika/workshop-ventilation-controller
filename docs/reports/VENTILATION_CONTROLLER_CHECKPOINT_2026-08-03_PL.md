# Workshop Ventilation Controller — checkpoint integracyjny

Data: 2026-08-03

## 1. Status końcowy

Checkpoint został zakończony i zintegrowany z `main`.

```text
PR integracyjny: #6
Gałąź: agent/rekuperator-modbus-control-stage1
Końcowy HEAD gałęzi: 22e405ad3061a95af8087d03c2493dd00d045399
Merge commit main: ba29de7e8a1fe8f376c7f4ceffb887785116f60e
Metoda integracji: merge commit
```

PR-y składowe zostały automatycznie rozpoznane jako włączone do `main`:

- PR #4 — Firmware Stage 2A: read-only Modbus RTU over KAmod RS-485 — merged,
- PR #5 — rozpoznanie RS-485 rekuperatora — merged,
- PR #6 — checkpoint integracyjny — merged.

Końcowa walidacja GitHub Actions dla HEAD `22e405ad3061a95af8087d03c2493dd00d045399`:

- `Ventilation Core Tests` — success,
- `Sensor node firmware` — success,
- brak nierozwiązanych wątków review.

Kolejne prace należy rozpoczynać z rzeczywistego aktualnego `main`, nie z historycznych gałęzi PR #4, #5 lub #6.

## 2. Zakres checkpointu

Checkpoint zamyka zwalidowany zakres obejmujący:

- firmware KAmod ESP32 POW RS485 + SEN55 Stage 2A,
- odczyt danych SEN55 przez Modbus RTU,
- rozpoznanie COMPIT NANO COLOR 2 firmware 6.30,
- odczyt i podstawowe sterowanie rekuperatorem Prodmax / AERO 4A2,
- decyzję o zastosowaniu dwóch niezależnych magistral RS-485,
- komplet narzędzi stanowiskowych,
- raporty walidacyjne,
- prompt startowy dla Stage 2B.

## 3. Zakończony zakres SEN55 Stage 2A

Potwierdzono firmware `0.2.0-stage2` dla KAmod ESP32 POW RS485 + SEN55.

Kontrakt magistrali czujnika:

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

- PM1.0, PM2.5, PM4.0 i PM10,
- wilgotność i temperatura,
- VOC Index i NOx Index,
- maska dostępności pól,
- status węzła,
- wiek pomiaru,
- liczniki błędów SEN55 i Modbus,
- uptime,
- wersja firmware i mapy,
- sekwencja pomiaru.

Walidacja fizyczna objęła:

- odczyt wszystkich 19 rejestrów,
- poprawne skalowanie i signed temperature,
- stan `MEASUREMENT_VALID` i `SENSOR_PRESENT`,
- odłączenie SEN55 i prawidłowy stan offline/stale,
- automatyczne odzyskanie pomiarów po ponownym podłączeniu,
- zimny start,
- minimum 30 minut ciągłego odpytywania,
- brak timeoutów i błędów CRC,
- `modbus_errors=0`,
- odrzucenie próby zapisu FC06 wyjątkiem Modbus.

Dokumenty bazowe:

- `docs/MODBUS_MAP_PL.md`,
- `docs/reports/KAMOD_MODBUS_STAGE2_IMPLEMENTATION_PL.md`.

## 4. Zakończony zakres rekuperatora

Zidentyfikowany sprzęt:

- Prodmax PRO MINI 300 H/V CLASSIC + WiFi,
- oznaczenie PRO MINI 300HV-C/WIFI,
- sterownik COMPIT AERO 4A2,
- panel COMPIT NANO COLOR 2,
- firmware panelu 6.30.

Potwierdzony kontrakt:

```text
Modbus RTU slave
9600 bit/s
8N1
slave 44
FC03 Read Holding Registers
FC06 Write Single Register
CRC poprawne
```

Potwierdzona telemetria firmware 6.30:

| Adres PDU | Znaczenie | Kodowanie |
|---:|---|---|
| 2016 | wilgotność | raw / 10 = % RH |
| 2021 | temperatura nawiewu | signed raw / 10 = °C |
| 2022 | temperatura wywiewu | signed raw / 10 = °C |
| 2023 | temperatura czerpni | signed raw / 10 = °C |
| 2033 | moc wentylatora 1 | raw = % |
| 2034 | moc wentylatora 2 | raw = % |

Nie ustalono jeszcze, który z adresów `2033/2034` odpowiada nawiewowi, a który wywiewowi. Do czasu osobnej identyfikacji obowiązują nazwy neutralne `fan_1` i `fan_2`.

Potwierdzone sterowanie:

| Adres PDU | Funkcja | Zakres zwalidowany |
|---:|---|---|
| 1080 | wybór biegu | 0..3 |
| 1081 | wietrzenie | 0/1 |

Zaliczone:

- echo FC06,
- readback FC03,
- fizyczna zmiana biegu,
- wietrzenie ON/OFF,
- automatyczne przywrócenie poprzedniej wartości,
- obserwacja mocy wentylatorów.

Dokumenty bazowe:

- `docs/COMPIT_AERO4A2_INTEGRATION_PL.md`,
- `docs/reports/COMPIT_NANO_V630_CONTROL_VALIDATION_PL.md`,
- `docs/reports/COMPIT_NANO_V630_CONTROL_STAGE1_HANDOFF_NEXT_STAGE_PL.md`.

## 5. Krytyczna bezwładność AERO

AERO 4A2 może wykonać prawidłowo przyjęte polecenie dopiero po około 30 sekundach.

Należy rozdzielać:

1. poprawną transmisję i CRC,
2. echo FC06,
3. readback wartości z NANO,
4. fizyczną reakcję AERO potwierdzoną telemetrią.

Założenia przyszłego adaptera:

```text
execution_timeout = 45 s
telemetry_poll_interval = 2 s
```

Echo FC06 ani szybki readback nie są dowodem fizycznego wykonania polecenia. Adapter AERO musi działać asynchronicznie i nie może blokować `ventilation-core`.

## 6. Docelowy podział magistral

Rekuperator nie będzie dołączony do magistrali czujników.

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

Decyzja jest zapisana w `docs/DECISIONS_PL.md` jako D-044.

## 7. Obowiązujące zasady bezpieczeństwa

- AERO pozostaje nadrzędnym sterownikiem rekuperatora,
- CM5 nie steruje bezpośrednio elementami wykonawczymi i zabezpieczeniami AERO,
- nie reverse-engineerujemy C14,
- nie podłączamy drugiego mastera do C14,
- dynamiczne sterowanie AERO używa wyłącznie potwierdzonych rejestrów RAM,
- nie używamy EEPROM do cyklicznej automatyki,
- nie zapisujemy adresów o niepotwierdzonym znaczeniu,
- awaria CM5 nie może blokować lokalnego panelu ani pracy AERO,
- magistrala czujników pozostaje read-only,
- GUI, MQTT i AI nie mogą bezpośrednio otwierać portów ani wykonywać zapisów Modbus.

## 8. Narzędzia zapisane w repo

### SEN55

- `tools/read_modbus_sensor.py` — odczyt mapy czujnika FC04 i diagnostyka.

### NANO / AERO

- `tools/compit_nano_v630_discovery.py` — surowe snapshoty i diff,
- `tools/compit_nano_v630_labeled_read.py` — czytelny odczyt telemetrii,
- `tools/compit_nano_v630_control_test.py` — kontrolowane testy FC06 z readbackiem i obserwacją fizycznej reakcji.

## 9. Następny etap

Następny etap to **SEN55 Modbus Stage 2B — dwa węzły na jednej, oddzielnej magistrali czujników**.

Zakres:

- utrzymać `19200 bit/s`, `8N1` i read-only FC04,
- nadać dwóm węzłom unikalne, trwałe adresy `1` i `2`,
- wykorzystać jeden kod firmware i tę samą mapę danych,
- nie dodawać rekuperatora do magistrali SENSOR,
- nie dodawać zdalnego zapisu konfiguracji Modbus,
- przetestować oba węzły jednocześnie,
- sprawdzić utratę jednego węzła bez wpływu na drugi,
- sprawdzić błędny adres i brak odpowiedzi,
- przeprowadzić dłuższe odpytywanie bez timeoutów i błędów CRC,
- potwierdzić topologię liniową i terminację,
- zaktualizować CI, dokumentację, raport sprzętowy i handoff.

Gotowy prompt znajduje się w:

`docs/reports/SEN55_MODBUS_STAGE2B_START_PROMPT_PL.md`

## 10. Kryterium zakończenia Stage 2B

Etap można zakończyć dopiero po:

- testach jednostkowych i buildzie ESP-IDF,
- sukcesie workflowów CI,
- odczycie obu urządzeń na jednej magistrali,
- potwierdzeniu adresów `1` i `2`,
- potwierdzeniu niezależnego działania przy utracie jednego węzła,
- dłuższym teście stabilności,
- pełnym raporcie implementacyjnym i sprzętowym,
- przygotowaniu kolejnego handoffu.
