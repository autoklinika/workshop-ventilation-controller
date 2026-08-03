# Mapa Modbus RTU — KAmod ESP32 + SEN55

**Wersja mapy: 1**  
**Status: kontrakt Stage 2A — tylko odczyt**

## Parametry komunikacji

- rola: Modbus RTU slave,
- adres urządzenia: `1`,
- prędkość: `19200 bit/s`,
- format: `8N1`,
- funkcja odczytu: `0x04` — Read Input Registers,
- UART KAmod: UART2,
- TX: GPIO25,
- RX: GPIO27,
- DE/RE: GPIO26,
- tryb sterownika UART: RS-485 half-duplex.

W Stage 2A nie są wystawiane rejestry holding, coils ani discrete inputs. Próby zapisu lub użycia nieobsługiwanej funkcji powinny zakończyć się standardową odpowiedzią wyjątkową Modbus.

## Rejestry wejściowe

Adresy w tabeli są adresami protokołu Modbus liczonymi od zera. W programach używających notacji `30001` rejestr o adresie `0` może być prezentowany jako `30001`.

| Adres | Nazwa | Typ | Skala / znaczenie |
|---:|---|---|---|
| 0 | PM1.0 | `uint16` | µg/m³ × 10 |
| 1 | PM2.5 | `uint16` | µg/m³ × 10 |
| 2 | PM4.0 | `uint16` | µg/m³ × 10 |
| 3 | PM10 | `uint16` | µg/m³ × 10 |
| 4 | Wilgotność | `uint16` | %RH × 100 |
| 5 | Temperatura | `int16` | °C × 100, zapis w kodzie uzupełnień do dwóch |
| 6 | VOC Index | `uint16` | wartość × 10 |
| 7 | NOx Index | `uint16` | wartość × 10 |
| 8 | Maska dostępności pól | `uint16` | dolne 8 bitów |
| 9 | Status węzła | `uint16` | bitmask opisany niżej |
| 10 | Wiek pomiaru | `uint16` | sekundy; `0xFFFF` oznacza brak poprawnego pomiaru |
| 11 | Licznik błędów SEN55 | `uint16` | suma błędów detekcji, komunikacji i CRC, saturacja `0xFFFF` |
| 12 | Licznik błędów usługi Modbus | `uint16` | błędy inicjalizacji, blokady lub aktualizacji mapy, saturacja `0xFFFF` |
| 13 | Czas pracy — high word | `uint16` | starsze 16 bitów czasu pracy w sekundach |
| 14 | Czas pracy — low word | `uint16` | młodsze 16 bitów czasu pracy w sekundach |
| 15 | Wersja firmware | `uint16` | major w starszym bajcie, minor w młodszym; Stage 2 = `0x0002` |
| 16 | Wersja mapy | `uint16` | obecnie `1` |
| 17 | Sekwencja pomiaru — high word | `uint16` | starsze 16 bitów dolnego `uint32` licznika |
| 18 | Sekwencja pomiaru — low word | `uint16` | młodsze 16 bitów licznika |

Wartości wielorejestrowe są zapisywane jako **high word, następnie low word**.

## Maska dostępności pól — rejestr 8

- bit 0: PM1.0,
- bit 1: PM2.5,
- bit 2: PM4.0,
- bit 3: PM10,
- bit 4: wilgotność,
- bit 5: temperatura,
- bit 6: VOC Index,
- bit 7: NOx Index.

Jeżeli bit pola ma wartość `0`, odpowiadający rejestr liczbowy zawiera `0` i nie może być interpretowany jako prawidłowy pomiar.

## Status węzła — rejestr 9

- bit 0 — `MEASUREMENT_VALID`: pomiar istnieje, nie jest przeterminowany i co najmniej jedno pole jest dostępne,
- bit 1 — `SENSOR_PRESENT`: SEN55 odpowiada,
- bit 2 — `MEASUREMENT_STALE`: brak pierwszego pomiaru albo wiek przekracza 5 sekund,
- bit 3 — `I2C_ERROR`: ostatnia operacja czujnika zakończyła się błędem,
- bit 4 — `DATA_ERROR`: pomiar nie zawiera kompletu ośmiu pól,
- bit 5 — `INITIALIZING`: trwa wykrywanie SEN55 albo oczekiwanie na pierwszy pomiar,
- bit 6 — `SENSOR_OFFLINE`: usługa SEN55 przeszła w tryb offline i ponawia detekcję,
- bit 7 — `PLATFORM_FAULT`: nie jest gotowy GPIO, I²C lub interfejs RS-485.

Pozostałe bity są zarezerwowane i muszą być ignorowane przez mastera.

## Zasady interpretacji

1. Master nie może uznać wartości za aktualną bez sprawdzenia bitu `MEASUREMENT_VALID`.
2. Dostępność konkretnego pola zawsze wynika z rejestru 8.
3. Po utracie SEN55 ostatnie wartości pozostają w mapie, ale rośnie ich wiek i pojawiają się bity `MEASUREMENT_STALE` oraz `SENSOR_OFFLINE`.
4. Rejestr 10 ma wartość `0xFFFF`, dopóki nie odebrano pierwszego poprawnego pomiaru.
5. Liczniki 16-bit są nasycane na `0xFFFF`; nie zawijają się.
6. Wersja mapy musi być sprawdzana przez CM5 przed użyciem dekodera.
7. Stage 2A jest celowo tylko do odczytu. Adres slave i prędkość transmisji są stałe w firmware.

## Plan dalszy

Rejestry konfiguracyjne zostaną rozważone dopiero w Stage 2B, po fizycznej walidacji read-only Modbus RTU z komputerem i konwerterem USB–RS485. Zapis konfiguracji będzie wymagał walidacji zakresów, trwałego zapisu i kontrolowanego restartu.
