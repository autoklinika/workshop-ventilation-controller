# KAmod ESP32 POW RS485 + SEN55 — firmware Stage 1

Pierwszy etap uruchamia niezależny węzeł pomiarowy SEN55 na module KAmod ESP32 POW RS485. Kod jest przygotowany dla ESP-IDF 6.0.2 i nie zawiera jeszcze Modbus RTU, Wi-Fi, heartbeatów, pobierania OTA ani komunikacji z CM5.

## Zakres

- warstwowy projekt ESP-IDF,
- konfiguracja płytki KAmod,
- I²C przez GPIO32 (SDA) i GPIO33 (SCL),
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
idf.py -p COM5 flash monitor
```

Numer portu należy dopasować do systemu. Monitor zamyka się kombinacją `Ctrl+]`.

## Oczekiwany przebieg testu USB

Po poprawnym uruchomieniu log powinien zawierać między innymi:

```text
sensor_node: firmware=0.1.0-stage1
platform: running_partition=ota_0
platform: i2c initialized: port=0 sda=32 scl=33 frequency=100000
sen55: detected product=SEN55 ...
sensor_service: continuous measurement started
sensor_node: PM1.0=... PM2.5=... PM4.0=... PM10=... RH=... T=... VOC=... NOx=...
```

Po odłączeniu SEN55 firmware nie powinien się zawiesić ani wejść w reset loop. Powinien przejść do stanu offline i co 5 sekund próbować ponownie wykryć czujnik. Po ponownym podłączeniu powinien sam wrócić do pomiarów.

## Połączenie I²C

Konfiguracja firmware zakłada wyprowadzenia płytki KAmod:

| Sygnał | GPIO |
|---|---:|
| SDA | 32 |
| SCL | 33 |
| LED statusowa D6 | 2 |

Na płytce znajdują się rezystory podciągające I²C. Zasilanie SEN55 i wspólną masę należy podłączyć zgodnie z dokumentacją czujnika i rzeczywistą wiązką używaną w prototypie.

## OTA i rollback

Stage 1 nie pobiera jeszcze obrazu OTA. Układ flash jest jednak od początku zgodny z A/B:

- `ota_0`,
- `ota_1`,
- `otadata`,
- `coredump`.

Jeżeli uruchomiony obraz ma stan `PENDING_VERIFY`, firmware zatwierdza go po 30 sekundach stabilnej pracy platformy. Obecność SEN55 nie jest warunkiem zatwierdzenia, ponieważ chwilowe odłączenie zewnętrznego czujnika nie może powodować rollbacku poprawnego firmware.
