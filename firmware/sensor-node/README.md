# KAmod ESP32 POW RS485 + SEN55 — firmware Stage 2

Stage 2 rozwija zwalidowany sterownik SEN55 o produkcyjny kanał danych Modbus RTU po wbudowanym interfejsie RS-485 płytki KAmod. Interfejs jest celowo tylko do odczytu.

## Zakres

- ESP-IDF 6.0.2,
- SEN55 po lokalnym I²C,
- I²C: SDA GPIO33, SCL GPIO32,
- Modbus RTU slave po UART2,
- RS-485: TX GPIO25, RX GPIO27, DE/RE GPIO26,
- adres slave `1`,
- `19200 bit/s`, `8N1`,
- funkcja `0x04` — Read Input Registers,
- 19 rejestrów pomiarowych i diagnostycznych,
- aktualizacja mapy pod blokadą kontrolera Modbus,
- automatyczne oznaczanie pomiaru nieaktualnego,
- brak rejestrów zapisywalnych w Stage 2A,
- OTA A/B, rollback i coredump zachowane ze Stage 1.

Oficjalny komponent `espressif/esp-modbus` jest przypięty do wersji `2.1.2`, zawierającej poprawki zgodności z ESP-IDF 6.0.

## Architektura

```text
main
  -> app
      -> services
          -> sen55
              -> drivers/I2C
      -> modbus
          -> register_map
          -> esp-modbus
              -> UART2 / RS-485
      -> diagnostics
      -> platform
      -> logging
      -> config
```

Sterownik SEN55 nie zna Modbus. Komponent Modbus pobiera gotowy snapshot pomiaru i diagnostyki, koduje go zgodnie z wersjonowaną mapą i udostępnia przez rejestry wejściowe.

## Wymagania

- KAmod ESP32 POW RS485,
- SEN55,
- stabilne zasilanie KAmod, w prototypie 12 V,
- przewód USB-C do flashowania i logów,
- do testu RS-485: konwerter USB–RS485 oraz komputer.

## Budowanie i flash

```powershell
cd C:\PROJEKTY\workshop-ventilation-controller\firmware\sensor-node
idf.py set-target esp32
idf.py -p COM9 build flash monitor
```

Monitor zamyka się kombinacją `Ctrl+]`.

Po uruchomieniu oczekiwane są między innymi logi:

```text
modbus_rtu: started: mode=RTU address=1 baud=19200 format=8N1 uart=2 tx=25 rx=27 de_re=26 input_registers=19
sensor_service: detected product=SEN55 ...
sensor_service: continuous measurement started
diagnostics: sensor_state=running
sensor_node: measurement=...
```

## Połączenie SEN55

| SEN55 | Kolor przewodu | KAmod ESP32 POW RS485 |
|---|---|---|
| VDD | czerwony | 5 V |
| GND | czarny | GND |
| SDA | zielony | GPIO33 / SDA, fizyczny pin 3 J1 |
| SCL | żółty | GPIO32 / SCL, fizyczny pin 5 J1 |
| SEL | niebieski | GND |
| NC | fioletowy | nie podłączać |

## Połączenie RS-485

Na złączu KAmod należy połączyć magistralę różnicową z konwerterem USB–RS485:

```text
KAmod A+  -> konwerter A / D+
KAmod B-  -> konwerter B / D-
GND       -> GND konwertera, jeżeli adapter udostępnia zacisk masy
```

Nazewnictwo A/B bywa odwracane przez producentów adapterów. Jeżeli urządzenie nie odpowiada mimo poprawnych ustawień, pierwszą diagnostyczną próbą jest zamiana A z B. Nie zmieniać przewodów przy włączonym zasilaniu.

Przy krótkim połączeniu stanowiskowym używamy magistrali bez dodatkowych terminatorów. Dla docelowej długiej magistrali terminację i polaryzację spoczynkową ustalimy po weryfikacji wszystkich urządzeń.

## Test z komputera

Skrypt testowy znajduje się w:

```text
tools/read_modbus_sensor.py
```

Instalacja zależności:

```powershell
py -m pip install pyserial
```

Odczyt przez przykładowy port COM10:

```powershell
py tools\read_modbus_sensor.py --port COM10
```

Port COM9 pozostaje portem USB KAmod do logów. Konwerter USB–RS485 zwykle pojawi się jako osobny port COM.

## Mapa rejestrów

Pełny kontrakt znajduje się w `docs/MODBUS_MAP_PL.md`.

Najważniejsze zasady:

- odczyt funkcją `0x04`, adres początkowy `0`, liczba rejestrów `19`,
- master musi sprawdzić rejestr statusu oraz maskę dostępności,
- wartości niedostępnych pól są zerowane,
- wiek `0xFFFF` oznacza brak pierwszego poprawnego pomiaru,
- wartości 32-bit są ułożone high word, potem low word,
- wersja mapy wynosi `1`.

## Walidacja programowa

Workflow wykonuje:

1. hostowy test kodowania mapy rejestrów z `-Wall -Wextra -Werror`,
2. pobranie przypiętego komponentu esp-modbus,
3. pełny build firmware dla klasycznego ESP32 na ESP-IDF 6.0.2,
4. kontrolę tabeli partycji.

## Walidacja sprzętowa Stage 2

Do wykonania na stanowisku:

1. flash aktualnego firmware,
2. potwierdzenie startu UART2 i Modbus RTU w logu,
3. odczyt rejestrów 0–18 przez konwerter USB–RS485,
4. porównanie danych Modbus z logiem USB,
5. odłączenie SEN55 i sprawdzenie statusu stale/offline,
6. ponowne podłączenie i powrót bitu measurement valid,
7. odpytywanie przez minimum 30 minut,
8. test błędnego adresu i nieobsługiwanej funkcji,
9. test zimnego startu całego węzła.
