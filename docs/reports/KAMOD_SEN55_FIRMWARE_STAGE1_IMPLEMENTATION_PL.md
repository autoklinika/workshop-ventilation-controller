# KAmod ESP32 POW RS485 + SEN55 — Firmware Stage 1

## Cel

Dostarczenie stabilnej, warstwowej podstawy firmware węzła pomiarowego przed rozpoczęciem Modbus RTU, Wi-Fi i komunikacji z CM5.

## Zakres wykonany

1. Utworzono podprojekt `firmware/sensor-node` dla ESP-IDF 6.0.2.
2. Dodano komponenty `app`, `sen55`, `diagnostics`, `logging`, `config`, `platform`, `services` i `drivers`.
3. `main.cpp` został ograniczony do utworzenia i uruchomienia `Application`.
4. Dodano konfigurację KAmod:
   - SDA GPIO33,
   - SCL GPIO32,
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
15. Po teście stanowiskowym skorygowano przypisanie linii I²C KAmod z błędnego SDA GPIO32 / SCL GPIO33 na właściwe SDA GPIO33 / SCL GPIO32.

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

## Zweryfikowany schemat połączeń

| SEN55 | Kolor przewodu | KAmod ESP32 POW RS485 |
|---|---|---|
| VDD | czerwony | 5 V |
| GND | czarny | GND |
| SDA | zielony | GPIO33 / SDA, fizyczny pin 3 J1 |
| SCL | żółty | GPIO32 / SCL, fizyczny pin 5 J1 |
| SEL | niebieski | GND |
| NC | fioletowy | nie podłączać |

Względem pierwotnego schematu przewody zielony i żółty zostały zamienione miejscami. Pierwszy test został uruchomiony przez tymczasowe skrzyżowanie przewodów, ponieważ firmware miał odwrócone przypisanie SDA/SCL. Po korekcie firmware należy stosować powyższy końcowy schemat bez dodatkowego krzyżowania przewodów.

## Walidacja stanowiskowa 2026-08-03

### Stanowisko

- KAmod ESP32 POW RS485,
- ESP32 revision 3.1,
- flash 4 MB,
- ESP-IDF 6.0.2,
- firmware `0.1.0-stage1`,
- port serwisowy COM9, UART0 115200 bit/s,
- zasilanie KAmod 12 V przez wejście `POWER`,
- SEN55 podłączony lokalnie po I²C.

### Pomiary elektryczne

- zasilanie SEN55: 5,05 V,
- SDA w stanie spoczynku: 3,28 V,
- SCL w stanie spoczynku: 3,28 V,
- SEL: 0 V.

### Wyniki

1. Build ESP-IDF 6.0.2 — zaliczony.
2. Flash przez USB-C — zaliczony.
3. Boot z partycji `ota_0` — zaliczony.
4. Identyfikacja czujnika — zaliczona:
   - produkt `SEN55`,
   - firmware 2.0,
   - hardware 5.0,
   - protocol 1.0.
5. Start pomiaru ciągłego — zaliczony.
6. Pierwszy i kolejne pomiary — zaliczone.
7. Dostępność wszystkich ośmiu wartości — zaliczona, `mask=0xFF`.
8. Odczyty PM1.0, PM2.5, PM4.0, PM10, RH, temperatury, VOC i NOx — zaliczone.
9. Odłączenie SEN55 podczas pracy — wykryte bez zawieszenia i bez reset loop.
10. Ponowne podłączenie SEN55 — automatyczny powrót pomiarów bez restartu ESP32.

Przykładowe potwierdzenie z logu:

```text
sensor_service: detected product=SEN55 firmware=2.0 hardware=5.0 protocol=1.0
sensor_service: continuous measurement started
diagnostics: sensor_state=running
sensor_node: measurement=1 PM1.0=49.2 PM2.5=51.6 PM4.0=51.6 PM10=51.6 RH=55.73 T=25.47 VOC=0.0 NOx=0.0 mask=0xFF
```

### Wykryta i usunięta niezgodność

Pierwsza wersja konfiguracji określała SDA jako GPIO32 i SCL jako GPIO33. Oficjalne przypisanie KAmod oraz wynik testu wskazują odwrotny układ: SDA GPIO33 i SCL GPIO32. Błąd został usunięty w konfiguracji firmware oraz w schematach połączeń.

Funkcjonalność sterownika SEN55 i mechanizm odzyskiwania komunikacji zostały potwierdzone fizycznie. Po pobraniu commitu z korektą pinów wymagany jest jeszcze krótki test regresyjny: ponowny flash, standardowe podłączenie zielony SDA → GPIO33 i żółty SCL → GPIO32 oraz potwierdzenie pierwszego pomiaru.

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

Po krótkim teście regresyjnym skorygowanego przypisania SDA/SCL Stage 1 można formalnie zamknąć. Następny etap powinien obejmować kontrakt danych oraz Modbus RTU slave, bez mieszania tej logiki ze sterownikiem SEN55.
