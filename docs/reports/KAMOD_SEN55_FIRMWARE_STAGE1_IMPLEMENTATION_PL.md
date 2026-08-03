# KAmod ESP32 POW RS485 + SEN55 — Firmware Stage 1

## Cel

Dostarczenie stabilnej, warstwowej podstawy firmware węzła pomiarowego przed rozpoczęciem Modbus RTU, Wi-Fi i komunikacji z CM5.

## Zakres wykonany

1. Utworzono podprojekt `firmware/sensor-node` dla ESP-IDF 6.0.2.
2. Dodano komponenty `app`, `sen55`, `diagnostics`, `logging`, `config`, `platform`, `services` i `drivers`.
3. `main.cpp` został ograniczony do utworzenia i uruchomienia `Application`.
4. Dodano konfigurację KAmod:
   - SDA GPIO32,
   - SCL GPIO33,
   - LED D6 GPIO2,
   - zarezerwowane piny RS-485 GPIO27/25/26.
5. Dodano sterownik nowego API I²C master ESP-IDF.
6. Dodano sterownik protokołu SEN55:
   - probe adresu `0x69`,
   - nazwa produktu `0xD014`,
   - wersja `0xD100`,
   - start pomiaru `0x0021`,
   - data-ready `0x0202`,
   - pomiar `0x03C4`,
   - kontrola CRC-8 polynomial `0x31`, init `0xFF`.
7. Dodano dekodowanie wszystkich ośmiu wartości pomiarowych i rozpoznawanie wartości niedostępnych.
8. Dodano usługę ponawiania, która przechodzi do offline po serii błędów i automatycznie odzyskuje czujnik po ponownym podłączeniu.
9. Dodano diagnostykę etapów startu i liczników błędów.
10. Dodano logowanie pełnych pomiarów przez UART0 / USB-C.
11. Dodano układ partycji 4 MB:
    - `nvs`,
    - `otadata`,
    - `phy_init`,
    - `ota_0`,
    - `ota_1`,
    - `coredump`.
12. Włączono rollback obrazu oczekującego na weryfikację oraz kontrolowane zatwierdzanie po 30 sekundach stabilnego działania platformy.
13. Dodano workflow GitHub Actions budujący firmware w obrazie `espressif/idf:v6.0.2`.
14. Zaktualizowano dokumentację węzła z nieaktualnej platformy STM32 na KAmod ESP32.

## Ważna decyzja rollback

SEN55 jest urządzeniem zewnętrznym i może zostać odłączony podczas serwisu. Dlatego brak czujnika nie jest traktowany jako wada obrazu firmware. Obraz jest zatwierdzany, gdy działają podstawowe zasoby platformy: GPIO, I²C i główna pętla aplikacji.

Krytyczny błąd inicjalizacji platformy prowadzi do restartu. Jeżeli uruchomiony obraz ma stan `PENDING_VERIFY`, bootloader może wtedy wrócić do poprzedniej partycji.

## Kryteria walidacji programowej

- projekt buduje się dla `esp32`,
- tabela partycji mieści się dokładnie w 4 MB flash,
- każda warstwa ma jawne zależności CMake,
- brak obsługi SEN55 w `main.cpp`,
- parser CRC odrzuca uszkodzone słowo,
- nieznane pola SEN55 nie są przedstawiane jako poprawne zero,
- błąd I²C nie powoduje nieskończonego blokowania,
- firmware podejmuje próbę odzyskania czujnika bez resetu.

## Walidacja sprzętowa wymagana na stanowisku

1. Build ESP-IDF 6.0.2.
2. Flash przez USB-C.
3. Potwierdzenie nazwy produktu i wersji SEN55.
4. Potwierdzenie pierwszego pomiaru.
5. Minimum 30 minut ciągłej pracy.
6. Odłączenie SEN55 podczas pracy.
7. Potwierdzenie przejścia do offline bez reset loop.
8. Ponowne podłączenie i automatyczny powrót pomiarów.
9. Restart zimny i programowy.
10. Sprawdzenie aktywnej partycji i logu OTA.

## Poza zakresem

- Modbus RTU,
- aktywacja transceivera RS-485,
- heartbeat,
- Wi-Fi,
- transport obrazu OTA,
- komunikacja z CM5,
- MQTT,
- Home Assistant,
- AI.

## Następny checkpoint

Stage 1 można zamknąć po przejściu testu USB na fizycznym KAmod + SEN55. Dopiero potem należy rozpocząć Stage 2 obejmujący kontrakt danych i Modbus RTU slave.
