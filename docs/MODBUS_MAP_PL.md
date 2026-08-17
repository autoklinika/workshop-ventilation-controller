# Mapa Modbus RTU — KAmod ESP32 + SEN55

**Wersja mapy: 1**  
**Status: zwalidowany kontrakt Stage 2B — tylko odczyt; rozszerzenie diagnostyki SEN55 zachowuje kompatybilność mapy v1**

## Parametry komunikacji

- rola: Modbus RTU slave,
- adres urządzenia: lokalnie provisionowany w NVS; produkcyjne węzły używają `1` i `2`,
- bezpieczny fallback kompilacyjny: `CONFIG_WVC_MODBUS_SLAVE_ADDRESS_DEFAULT`,
- prędkość: `19200 bit/s`,
- format: `8N1`,
- funkcja odczytu: `0x04` — Read Input Registers,
- UART KAmod: UART2,
- TX: GPIO25,
- RX: GPIO27,
- DE/RE: GPIO26,
- tryb sterownika UART: RS-485 half-duplex.

Nie są wystawiane rejestry holding, coils ani discrete inputs. Próby zapisu lub użycia nieobsługiwanej funkcji powinny zakończyć się standardową odpowiedzią wyjątkową Modbus. Wi-Fi nie zmienia tego kontraktu i nie stanowi źródła danych produkcyjnych.

## Rejestry wejściowe

Adresy są adresami protokołu Modbus liczonymi od zera. W programach używających notacji `30001` rejestr o adresie `0` może być prezentowany jako `30001`.

| Adres | Nazwa | Typ | Skala / znaczenie |
|---:|---|---|---|
| 0 | PM1.0 | `uint16` | µg/m³ × 10 |
| 1 | PM2.5 | `uint16` | µg/m³ × 10 |
| 2 | PM4.0 | `uint16` | µg/m³ × 10 |
| 3 | PM10 | `uint16` | µg/m³ × 10 |
| 4 | Wilgotność | `uint16` | %RH × 100 |
| 5 | Temperatura | `int16` | °C × 100, kod uzupełnień do dwóch |
| 6 | VOC Index | `uint16` | wartość × 10 |
| 7 | NOx Index | `uint16` | wartość × 10 |
| 8 | Maska dostępności pól | `uint16` | dolne 8 bitów |
| 9 | Status węzła | `uint16` | bitmask opisany niżej; od firmware `0.6` górny bajt zawiera diagnostykę SEN55 |
| 10 | Wiek pomiaru | `uint16` | sekundy; `0xFFFF` oznacza brak poprawnego pomiaru |
| 11 | Licznik błędów SEN55 | `uint16` | suma błędów detekcji, komunikacji i CRC, saturacja `0xFFFF` |
| 12 | Licznik błędów usługi Modbus | `uint16` | błędy inicjalizacji, blokady, kolejki zdarzeń lub aktualizacji mapy, saturacja `0xFFFF` |
| 13 | Czas pracy — high word | `uint16` | starsze 16 bitów czasu pracy w sekundach |
| 14 | Czas pracy — low word | `uint16` | młodsze 16 bitów czasu pracy w sekundach |
| 15 | Wersja firmware | `uint16` | major w starszym bajcie, minor w młodszym; diagnostyka SEN55 `0x0006` = `0.6` |
| 16 | Wersja mapy | `uint16` | `1` |
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

Dolny bajt zachowuje dotychczasowy kontrakt:

- bit 0 — `MEASUREMENT_VALID`,
- bit 1 — `SENSOR_PRESENT`,
- bit 2 — `MEASUREMENT_STALE`,
- bit 3 — `I2C_ERROR`,
- bit 4 — `DATA_ERROR`,
- bit 5 — `INITIALIZING`,
- bit 6 — `SENSOR_OFFLINE`,
- bit 7 — `PLATFORM_FAULT`.

Od firmware KAmod `0.6` górny bajt jest kompatybilnym rozszerzeniem diagnostycznym. Stary master, który używa tylko dolnego bajtu, działa bez zmian. Nowy master rozpoznaje obsługę diagnostyki po bicie 8:

- bit 8 — `SEN55_DEVICE_STATUS_SUPPORTED` — firmware węzła implementuje odczyt `Read Device Status (0xD206)`,
- bit 9 — `SEN55_DEVICE_STATUS_VALID` — ostatni odczyt Device Status był poprawny,
- bit 10 — `SEN55_FAN_SPEED_WARNING` — SEN55 Device Status bit 21 `SPEED`,
- bit 11 — `SEN55_FAN_CLEANING` — SEN55 Device Status bit 19; informacja o czyszczeniu, **nie alarm**,
- bit 12 — `SEN55_GAS_SENSOR_ERROR` — Device Status bit 7 `GAS SENSOR`,
- bit 13 — `SEN55_RHT_ERROR` — Device Status bit 6 `RHT`,
- bit 14 — `SEN55_LASER_ERROR` — Device Status bit 5 `LASER`,
- bit 15 — `SEN55_FAN_ERROR` — Device Status bit 4 `FAN`.

W firmware ignorowane są wszystkie bity zarezerwowane przez Sensirion. Jeżeli bit 9 jest `0`, bity 10–15 nie mogą być używane do klasyfikacji stanu sensora. Jeżeli bit 8 jest `0`, oznacza to starszy firmware bez transportu Device Status i nie wolno traktować tego jako awarii.

## Zasady interpretacji

1. Master nie może uznać wartości za aktualną bez sprawdzenia `MEASUREMENT_VALID`.
2. Dostępność konkretnego pola zawsze wynika z rejestru 8.
3. Po utracie SEN55 ostatnie wartości pozostają w mapie, lecz rośnie ich wiek i pojawiają się bity stale/offline.
4. Rejestr 10 ma `0xFFFF`, dopóki nie odebrano pierwszego poprawnego pomiaru.
5. Liczniki 16-bit są nasycane na `0xFFFF`.
6. CM5 musi sprawdzić wersję mapy przed dekodowaniem.
7. Adres slave jest przechowywany w `device_config/modbus_addr` w NVS.
8. Kanał Wi-Fi nie może modyfikować mapy ani zastępować jej w logice sterowania.
9. `SEN55_FAN_CLEANING` jest stanem informacyjnym. W czasie automatycznego czyszczenia SEN55 nie aktualizuje wartości pomiarowych; nie wolno klasyfikować samego bitu cleaning jako awarii.
10. Sticky błędy `LASER` i `FAN` nie są automatycznie czyszczone przez firmware KAmod. System tylko raportuje status SEN55; nie wysyła automatycznie komendy `Clear Device Status (0xD210)`.

## Walidacja Stage 2B

Na dwóch fizycznych węzłach o adresach `1` i `2` potwierdzono `800/800` poprawnych cykli odczytu, bez timeoutów, błędów protokołu, błędów wersji mapy, próbek invalid/stale i bez utraty stabilności po zastosowaniu 10 ms przerwy między węzłami.

Rozszerzenie diagnostyki SEN55 zostało zaprojektowane bez zmiany liczby rejestrów i bez zmiany `map_version=1`: nowe firmware używa wcześniej zarezerwowanego górnego bajtu rejestru 9, a nowe `ventilation-core` pozostaje kompatybilne ze starszym firmware, dopóki bit `SEN55_DEVICE_STATUS_SUPPORTED` ma wartość `0`.
