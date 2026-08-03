# SEN55 Modbus Stage 2B — raport implementacyjny

Status: rozpoczęty, checkpoint konfiguracji adresu przed integracją runtime i walidacją sprzętową.

## Cel

Dwa węzły KAmod ESP32 POW RS485 + SEN55 mają pracować na jednej, oddzielnej magistrali SENSOR BUS przy 19200 bit/s, 8N1 i read-only FC04. Oba urządzenia zachowują identyczny kod firmware i mapę rejestrów v1.

## Wybór sposobu nadawania adresu

Rozważono:

1. Osobne warianty builda / Kconfig — najprostsze, ale zwiększają ryzyko wgrania niewłaściwego obrazu i utrudniają serwisowanie.
2. Lokalny provisioning USB/UART z zapisem w NVS — jeden obraz firmware, trwała konfiguracja per urządzenie i brak zdalnej zmiany przez Modbus.
3. Stały adres zależny od GPIO lub sprzętowego strapu — wymaga dodatkowego okablowania i nie daje istotnej korzyści w pojedynczym lokalnym wdrożeniu.

Wybrano lokalny provisioning USB/UART z zapisem w NVS. Kconfig pozostaje wyłącznie walidowanym fallbackiem dla pustej pamięci NVS. Produkcyjne węzły zostaną jawnie provisionowane jako slave 1 i slave 2.

## Checkpoint 1 — fundament konfiguracji

Dodano:

- wspólny kontrakt poprawnego adresu Modbus 1..247,
- build-time fallback `CONFIG_WVC_MODBUS_SLAVE_ADDRESS_DEFAULT`,
- odczyt klucza NVS `device_config/modbus_addr`,
- odrzucenie wartości NVS spoza zakresu,
- brak automatycznego kasowania NVS przy błędzie inicjalizacji,
- brak jakiejkolwiek możliwości zmiany adresu przez Modbus.

Na tym checkpointcie loader nie jest jeszcze podłączony do uruchomienia slave. Stage 2A nadal używa adresu 1, dzięki czemu nie zmieniono działającego kontraktu przed dodaniem i przetestowaniem lokalnej komendy provisioningowej.

## Następny kontrolowany krok

1. Dodać lokalną komendę provisioningową dostępną wyłącznie przez port serwisowy USB/UART.
2. Wymagać jawnego polecenia, walidacji 1..247 i potwierdzenia odczytem z NVS.
3. Podłączyć rozstrzygnięty adres do `ModbusRtuSlave::initialize()`.
4. Dodać testy hostowe adresów 0, 1, 2, 247 i 248 oraz dwóch konfiguracji urządzenia.
5. Rozbudować `tools/read_modbus_sensor.py` o bezpieczne odpytywanie slave 1 i 2.
6. Uruchomić pełny build ESP-IDF i CI przed instrukcją walidacji fizycznej.

## Ograniczenia

- brak AERO na SENSOR BUS,
- brak zapisywalnych rejestrów,
- brak zdalnego provisioning przez Modbus,
- brak twierdzenia o walidacji fizycznej dwóch węzłów,
- mapa rejestrów v1 i FC04 pozostają bez zmian.
