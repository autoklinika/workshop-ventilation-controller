# SEN55 Modbus Stage 2B — raport końcowy implementacji i walidacji

Status: zakończony i zwalidowany sprzętowo 2026-08-04.

## Cel etapu

Uruchomić dwa identyczne węzły KAmod ESP32 POW RS485 + SEN55 na jednej, oddzielnej magistrali SENSOR BUS:

- slave 1,
- slave 2,
- 19200 bit/s,
- 8N1,
- Modbus RTU,
- read-only FC04,
- mapa rejestrów v1,
- jeden wspólny obraz firmware.

## Zrealizowane rozwiązanie

Oba urządzenia używają tego samego firmware `0.3.0-stage2b`. Różnią się wyłącznie trwałym adresem zapisanym lokalnie w NVS jako `device_config/modbus_addr`.

Adres jest provisionowany przez port serwisowy USB przy użyciu:

```text
tools/provision_sensor_node_address.py
```

Zakres adresów jest walidowany jako `1..247`. Nie dodano możliwości zmiany adresu przez Modbus. Kconfig pozostaje wyłącznie fallbackiem dla pustej lub niepoprawnej konfiguracji NVS.

## Integracja runtime

Rozstrzygnięty adres z NVS jest przekazywany do `ModbusRtuSlave::initialize()`. Log startowy jednoznacznie raportuje aktywny adres:

```text
resolved Modbus slave address=<adres>
started: mode=RTU address=<adres> baud=19200
```

Zwalidowano fizycznie:

```text
KAmod + SEN55 #1 -> slave 1
KAmod + SEN55 #2 -> slave 2
```

Oba urządzenia:

- wykrywają SEN55,
- uruchamiają pomiar ciągły,
- publikują 19 Input Registers,
- zachowują mapę v1,
- raportują firmware `0.3`,
- działają jednocześnie na jednej magistrali RS-485.

## Narzędzia PC

Dodano:

- `tools/provision_sensor_node_address.py` — generowanie i zapis partycji NVS z adresem,
- `tools/read_modbus_sensor_nodes.py` — niezależne odpytywanie wielu slave,
- statystyki per węzeł: polls, success, errors, invalid, stale, map_errors,
- regulowaną przerwę między zapytaniami do kolejnych węzłów.

Podczas walidacji wykryto, że bez jawnej przerwy kolejne zapytanie wysyłane natychmiast po odpowiedzi pierwszego urządzenia powodowało sporadyczne timeouty urządzenia odpytywanego jako drugie. Błąd podążał za pozycją w kolejności `1,2` / `2,1`, a nie za konkretnym KAmod.

Dodano domyślną przerwę `10 ms` pomiędzy kolejnymi zapytaniami (`--inter-node-delay 0.01`). Po tej korekcie problem zniknął w obu kierunkach odpytywania.

## Wyniki walidacji sprzętowej

### Kolejność 1,2

```text
slave=1: polls=300 success=300 errors=0 invalid=0 stale=0 map_errors=0
slave=2: polls=300 success=300 errors=0 invalid=0 stale=0 map_errors=0
```

### Kolejność 2,1

```text
slave=2: polls=100 success=100 errors=0 invalid=0 stale=0 map_errors=0
slave=1: polls=100 success=100 errors=0 invalid=0 stale=0 map_errors=0
```

Łącznie wykonano 800 poprawnych odpytań bez timeoutów, błędów protokołu, pomiarów invalid, pomiarów stale ani błędów wersji mapy.

## CI

Dla gałęzi Stage 2B zakończyły się sukcesem:

- `Ventilation Core Tests`,
- `Sensor node firmware`.

Workflow firmware obejmuje pełny build ESP-IDF, kontrolę składni narzędzi PC oraz walidację odrzucenia niepoprawnych adresów provisioningowych.

## Zachowane ograniczenia architektoniczne

- AERO pozostaje na osobnej magistrali,
- SENSOR BUS pozostaje read-only,
- brak zapisywalnych rejestrów Modbus,
- brak zdalnego provisioning przez Modbus,
- mapa rejestrów v1 pozostaje bez zmian,
- oba węzły korzystają z jednego obrazu firmware.

## Wniosek

Stage 2B spełnia cel: dwa węzły KAmod + SEN55 pracują stabilnie na jednej magistrali SENSOR BUS z trwałymi adresami 1 i 2. Etap jest zakończony i gotowy do checkpointu przed integracją z Ventilation Core na CM5.
