# KAmod ESP32 POW RS485 + SEN55 — Modbus RTU Stage 2A

**Status: implementacja programowa i podstawowa walidacja fizyczna zakończone; do zamknięcia pozostają zimny start oraz test odrzucenia funkcji zapisu**

## Cel

Udostępnienie pomiarów SEN55 i diagnostyki węzła przez deterministyczny kanał Modbus RTU po wbudowanym interfejsie RS-485 modułu KAmod.

Stage 2A jest celowo tylko do odczytu. Nie dodaje konfiguracji zdalnej, Wi-Fi, transportu OTA ani integracji z CM5.

## Punkt wyjścia

Stage 1 zakończył się fizycznym potwierdzeniem działania KAmod, komunikacji SEN55 po I²C, pełnego pomiaru `mask=0xFF`, automatycznego odzyskiwania czujnika, zimnego startu i restartu.

Stage 2 powstał na gałęzi:

```text
agent/kamod-modbus-stage2
```

z bazowego commitu `main`:

```text
10bdd40284ae44441a5087e976a254f729822edc
```

## Architektura

Dodano niezależny komponent:

```text
components/modbus
├── register_map
└── modbus_rtu_slave
```

Sterownik SEN55 nie zależy od Modbus. Komponent Modbus otrzymuje ostatni pomiar, snapshot diagnostyki i czas pracy platformy, a następnie buduje wersjonowany bank rejestrów wejściowych.

Użyto oficjalnego komponentu:

```text
espressif/esp-modbus 2.1.2
```

Wersja została przypięta w `idf_component.yml`.

## Parametry transmisji

```text
slave address: 1
baudrate:      19200 bit/s
format:        8N1
UART:          UART2
TX:            GPIO25
RX:            GPIO27
DE/RE:         GPIO26
mode:          RS-485 half-duplex
```

Stage 2A udostępnia wyłącznie Input Registers i funkcję:

```text
0x04 Read Input Registers
```

Nie zdefiniowano Holding Registers, Coils, Discrete Inputs ani komend zapisu.

## Mapa rejestrów v1

Mapa ma 19 rejestrów wejściowych, adresy 0–18.

| Adres | Dane |
|---:|---|
| 0 | PM1.0 × 10 |
| 1 | PM2.5 × 10 |
| 2 | PM4.0 × 10 |
| 3 | PM10 × 10 |
| 4 | RH × 100 |
| 5 | temperatura × 100, signed int16 |
| 6 | VOC × 10 |
| 7 | NOx × 10 |
| 8 | maska dostępności |
| 9 | status węzła |
| 10 | wiek pomiaru w sekundach |
| 11 | licznik błędów SEN55 |
| 12 | licznik błędów usługi Modbus |
| 13–14 | uptime uint32, high word / low word |
| 15 | wersja firmware |
| 16 | wersja mapy |
| 17–18 | sekwencja pomiaru uint32, high word / low word |

Pełna definicja znajduje się w `docs/MODBUS_MAP_PL.md`.

## Status węzła

Rejestr statusu zawiera:

- bit 0: pomiar ważny,
- bit 1: czujnik obecny,
- bit 2: pomiar nieaktualny,
- bit 3: błąd I²C lub komunikacji,
- bit 4: błąd danych / CRC / brak części pól,
- bit 5: inicjalizacja,
- bit 6: czujnik offline,
- bit 7: błąd platformy.

Master musi sprawdzić wersję mapy, `MEASUREMENT_VALID`, maskę dostępności pola oraz wiek pomiaru. Po utracie SEN55 ostatnie wartości pozostają dostępne diagnostycznie, ale są oznaczone jako nieważne i nieaktualne.

## Aktualizacja banku rejestrów

Bank jest odświeżany co 250 ms pomiędzy:

```text
mbc_slave_lock()
mbc_slave_unlock()
```

Zapobiega to odczytaniu części starego i części nowego snapshotu podczas jednej transakcji.

## Zachowanie błędów

- brak pierwszego pomiaru: wiek `0xFFFF`, stale=1, valid=0,
- SEN55 offline: present=0, stale=1, offline=1, valid=0,
- CRC SEN55: data_error=1,
- inny błąd komunikacji: i2c_error=1,
- brak części pól: maska pola=0, rejestr wartości=0, data_error=1,
- krytyczny błąd inicjalizacji Modbus/RS-485: kontrolowany restart,
- licznik błędów Modbus nasyca się na `0xFFFF`,
- licznik błędów SEN55 jest historyczny od uruchomienia i nie zeruje się automatycznie po odzyskaniu czujnika.

## OTA i zdrowie platformy

Od Stage 2 zatwierdzenie obrazu oczekującego na weryfikację wymaga gotowości GPIO, I²C oraz RS-485/Modbus. Obecność SEN55 nie jest wymagana do potwierdzenia obrazu, ponieważ jest urządzeniem zewnętrznym.

## Narzędzie testowe PC

Dodano:

```text
tools/read_modbus_sensor.py
```

Narzędzie buduje ramkę FC04 bezpośrednio, oblicza i sprawdza CRC-16 Modbus, kontroluje adres, funkcję i długość odpowiedzi, obsługuje wyjątki, dekoduje temperaturę signed int16 oraz wartości 32-bit high/low. Zależnością PC jest `pyserial`.

## Walidacja automatyczna

Hostowy test `test_modbus_register_map.cpp` sprawdza skalowanie, ujemną temperaturę, statusy, pola niedostępne, saturację liczników, kolejność słów 32-bit oraz wersje firmware i mapy.

Workflow wykonuje test z:

```text
-std=c++20 -Wall -Wextra -Werror
```

oraz pełny build ESP-IDF 6.0.2.

Wynik CI dla implementacji:

- `Ventilation Core Tests` — success,
- `Sensor node firmware` — success,
- aplikacja `0.2.0`,
- obraz `kamod_sen55_sensor_node.bin`,
- około 85% wolnego miejsca w najmniejszej partycji aplikacji.

## Walidacja fizyczna — wykonana

Stanowisko:

- KAmod ESP32 POW RS485,
- SEN55 po I²C,
- KAmod USB RS485 ISO,
- port serwisowy KAmod: COM9,
- port konwertera RS-485: COM10,
- Modbus slave address 1, 19200 bit/s, 8N1.

Potwierdzono:

1. Flash firmware `0.2.0-stage2` — zaliczony.
2. Start Modbus RTU po UART2 — zaliczony.
3. Połączenie A+/B- z izolowanym konwerterem USB–RS485 — zaliczone.
4. Odczyt wszystkich 19 rejestrów funkcją 0x04 — zaliczony.
5. Prawidłowe skalowanie PM, RH, temperatury, VOC i NOx — zaliczone.
6. Prawidłowe dekodowanie temperatury signed int16 — zaliczone.
7. Prawidłowe pola uptime, sequence, firmware 0.2 i map version 1 — zaliczone.
8. Stabilny stan roboczy:

```text
status=measurement_valid,sensor_present
availability=PM1.0,PM2.5,PM4.0,PM10,RH,T,VOC,NOx
age=0 s
modbus_errors=0
```

9. Odłączenie SEN55 — zaliczone. Modbus pozostał dostępny i raportował:

```text
status=measurement_stale,i2c_error,sensor_offline
```

Jednocześnie:

- usunięte zostały `measurement_valid` i `sensor_present`,
- wiek pomiaru rósł,
- sekwencja ostatniego pomiaru pozostawała zamrożona,
- uptime nadal rósł,
- `modbus_errors=0`.

10. Ponowne podłączenie SEN55 — zaliczone; pomiary i `measurement_valid,sensor_present` wróciły automatycznie bez restartu ESP32.
11. Historyczny licznik `sensor_errors` prawidłowo zachował liczbę błędów powstałych podczas odłączenia.
12. Test błędnego adresu slave — zaliczony:

```text
address 2 -> brak odpowiedzi
address 1 -> poprawna odpowiedź
```

13. Minimum 30 minut ciągłego odpytywania przez COM10 — zaliczone 2026-08-03:

- brak timeoutów,
- brak błędów CRC,
- brak niepełnych odpowiedzi,
- `modbus_errors=0`,
- uptime wzrastał,
- sequence wzrastała wraz z kolejnymi pomiarami SEN55.

## Walidacja pozostała do wykonania

1. Test funkcji zapisu i potwierdzenie standardowego wyjątku Modbus.
2. Zimny start całego zestawu z odłączonym 12 V, COM9 i COM10, a następnie automatyczny powrót komunikacji Modbus i pomiarów.

## Poza zakresem Stage 2A

- zapisywalny adres Modbus,
- zapisywalna prędkość,
- NVS konfiguracji komunikacji,
- drugi węzeł na magistrali,
- integracja Modbus master na CM5,
- Wi-Fi,
- transport OTA,
- MQTT,
- Home Assistant,
- AI.

## Następny checkpoint

Stage 2A zostanie formalnie zamknięty po zaliczeniu testu odrzucenia funkcji zapisu oraz zimnego startu. Następnie można rozpocząć Stage 2B: konfigurację adresów i test dwóch węzłów na jednej magistrali.
