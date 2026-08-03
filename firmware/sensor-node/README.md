# KAmod ESP32 POW RS485 + SEN55 — firmware Stage 1

Pierwszy etap uruchamia niezależny węzeł pomiarowy SEN55 na module KAmod ESP32 POW RS485. Kod jest przygotowany dla ESP-IDF 6.0.2 i nie zawiera jeszcze Modbus RTU, Wi-Fi, heartbeatów, pobierania OTA ani komunikacji z CM5.

## Zakres

- warstwowy projekt ESP-IDF,
- konfiguracja płytki KAmod,
- I²C przez GPIO33 (SDA) i GPIO32 (SCL),
- wykrywanie SEN55 pod adresem `0x69`,
- odczyt nazwy produktu i wersji,
- uruchomienie pomiaru ciągłego,
- walidacja CRC Sensirion,
- cykliczny odczyt PM, temperatury, wilgotności, VOC i NOx,
- diagnostyka błędów i automatyczne ponawianie po odłączeniu czujnika,
- log przez USB-C / UART0 przy 115200 bit/s,
- układ partycji OTA A/B z rollbackiem i coredumpem.

## Architektura

```text
main
  -> app
      -> services
          -> sen55
              -> drivers
      -> diagnostics
      -> platform
      -> logging
      -> config
```

`main.cpp` jest wyłącznie punktem wejścia. Obsługa I²C, protokół SEN55, diagnostyka i logika ponawiania są oddzielnymi komponentami.

## Wymagania

- ESP-IDF 6.0.2,
- KAmod ESP32 POW RS485 z ESP32-WROOM-32D i 4 MB flash,
- SEN55,
- przewód USB-C do programowania i monitorowania logów.

## Budowanie

W terminalu ESP-IDF:

```bash
cd firmware/sensor-node
idf.py set-target esp32
idf.py build
```

## Flash i monitor

Linux:

```bash
idf.py -p /dev/ttyUSB0 flash monitor
```

Windows:

```powershell
idf.py -p COM9 flash monitor
```

Numer portu należy dopasować do systemu. Monitor zamyka się kombinacją `Ctrl+]`.

## Oczekiwany przebieg testu USB

Po poprawnym uruchomieniu log powinien zawierać między innymi:

```text
sensor_node: firmware=0.1.0-stage1
platform: running_partition=ota_0
platform: i2c initialized: port=0 sda=33 scl=32 frequency=100000
sen55: detected product=SEN55 ...
sensor_service: continuous measurement started
sensor_node: PM1.0=... PM2.5=... PM4.0=... PM10=... RH=... T=... VOC=... NOx=...
```

Po odłączeniu SEN55 firmware nie powinien się zawiesić ani wejść w reset loop. Powinien przejść do stanu offline i co 5 sekund próbować ponownie wykryć czujnik. Po ponownym podłączeniu powinien sam wrócić do pomiarów.

## Połączenie I²C i zasilanie

Obowiązujący schemat po korekcie stanowiskowej:

| SEN55 | Kolor przewodu | KAmod ESP32 POW RS485 |
|---|---|---|
| VDD | czerwony | 5 V |
| GND | czarny | GND |
| SDA | zielony | GPIO33 / SDA, fizyczny pin 3 J1 |
| SCL | żółty | GPIO32 / SCL, fizyczny pin 5 J1 |
| SEL | niebieski | GND |
| NC | fioletowy | nie podłączać |

Względem pierwszej instrukcji przewody sygnałowe zostały zamienione: zielony SDA należy połączyć z GPIO33, a żółty SCL z GPIO32. Na płytce znajdują się zewnętrzne rezystory podciągające I²C 2,2 kΩ, dlatego wewnętrzne pull-upy ESP32 pozostają wyłączone.

Do pracy docelowej KAmod należy zasilać przez wejście `POWER` napięciem 8–32 V; w prototypie użyto 12 V. Podczas walidacji zmierzono 5,05 V na zasilaniu SEN55, 3,28 V na obu liniach I²C oraz 0 V na SEL.

## Wynik walidacji stanowiskowej 2026-08-03

- flash przez USB-C na COM9 zakończony poprawnie,
- wykryty produkt `SEN55`, firmware 2.0, hardware 5.0, protokół 1.0,
- uruchomiony pomiar ciągły,
- wszystkie osiem pól dostępne (`mask=0xFF`),
- stabilne kolejne odczyty PM, RH, temperatury, VOC i NOx,
- odłączenie czujnika nie powoduje restartu ESP32,
- po ponownym podłączeniu pomiary wracają automatycznie.

Pierwszy test ujawnił odwrócone przypisanie SDA/SCL w konfiguracji firmware i dokumentacji. Tymczasowe skrzyżowanie przewodów pozwoliło potwierdzić działanie sterownika; następnie konfigurację poprawiono do właściwego przypisania KAmod: SDA GPIO33, SCL GPIO32. Po pobraniu tej poprawki należy stosować wyłącznie schemat z tabeli powyżej.

## OTA i rollback

Stage 1 nie pobiera jeszcze obrazu OTA. Układ flash jest jednak od początku zgodny z A/B:

- `ota_0`,
- `ota_1`,
- `otadata`,
- `coredump`.

Jeżeli uruchomiony obraz ma stan `PENDING_VERIFY`, firmware zatwierdza go po 30 sekundach stabilnej pracy platformy. Obecność SEN55 nie jest warunkiem zatwierdzenia, ponieważ chwilowe odłączenie zewnętrznego czujnika nie może powodować rollbacku poprawnego firmware.
