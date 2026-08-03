# KAmod ESP32 POW RS485 + SEN55 — Modbus RTU Stage 2A

**Status: implementacja programowa zakończona; CI i walidacja fizyczna RS-485 w toku**

## Cel

Udostępnienie zwalidowanych pomiarów SEN55 i diagnostyki węzła przez prosty, deterministyczny i odporny kanał Modbus RTU po wbudowanym interfejsie RS-485 modułu KAmod.

Stage 2A jest celowo tylko do odczytu. Nie dodaje konfiguracji zdalnej, Wi-Fi, OTA transportu ani integracji z CM5.

## Punkt wyjścia

Stage 1 zakończył się fizycznym potwierdzeniem:

- działania KAmod ESP32 POW RS485,
- komunikacji SEN55 po I²C,
- pełnego pomiaru z `mask=0xFF`,
- automatycznego wykrywania po starcie,
- przejścia offline po odłączeniu,
- automatycznego powrotu po ponownym podłączeniu,
- zimnego startu i restartu.

Stage 2 powstał na gałęzi:

```text
agent/kamod-modbus-stage2
```

z bazowego commitu `main`:

```text
10bdd40284ae44441a5087e976a254f729822edc
```

## Decyzje architektoniczne

### 1. Osobny komponent Modbus

Dodano warstwę:

```text
components/modbus
├── register_map
└── modbus_rtu_slave
```

Sterownik SEN55 nie zależy od Modbus. Komponent Modbus otrzymuje:

- ostatni snapshot pomiaru,
- snapshot diagnostyki,
- czas pracy platformy.

Następnie tworzy wersjonowany bank rejestrów wejściowych.

### 2. Oficjalny stos Espressif

Użyto komponentu:

```text
espressif/esp-modbus 2.1.2
```

Wersję przypięto w `idf_component.yml`, aby uniknąć niekontrolowanych zmian API i zachowania. Jest to wydanie uwzględniające zgodność z ESP-IDF 6.0.

### 3. Tylko funkcja 0x04

Stage 2A udostępnia wyłącznie Input Registers i funkcję:

```text
0x04 Read Input Registers
```

Nie zdefiniowano:

- Holding Registers,
- Coils,
- Discrete Inputs,
- komend zapisu,
- konfiguracji adresu lub baudrate.

Nieobsługiwane zakresy i funkcje pozostają obsługiwane przez standardowe wyjątki stosu Modbus.

### 4. Stałe parametry transmisji

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

### 5. Jawna ważność danych

Master nie może użyć wartości wyłącznie dlatego, że rejestr zawiera liczbę. Musi sprawdzić:

- wersję mapy,
- bit `MEASUREMENT_VALID`,
- maskę dostępności konkretnego pola,
- wiek pomiaru.

Po utracie SEN55 ostatnie wartości pozostają dostępne diagnostycznie, ale są natychmiast oznaczone jako nieaktualne i nieważne.

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

Stan offline czyści `sensor_present` i `measurement_running`. Dzięki temu master nie widzi fałszywej obecności czujnika po utracie komunikacji.

## Aktualizacja banku rejestrów

Bank jest odświeżany co 250 ms. Aktualizacja odbywa się pomiędzy:

```text
mbc_slave_lock()
mbc_slave_unlock()
```

Zapobiega to odczytaniu przez mastera części starego i części nowego snapshotu podczas jednej transakcji.

## Zachowanie błędów

- brak pierwszego pomiaru: wiek `0xFFFF`, stale=1, valid=0,
- SEN55 offline: present=0, stale=1, offline=1, valid=0,
- CRC SEN55: data_error=1,
- błąd komunikacji inny niż CRC: i2c_error=1,
- brak części pól: maska pola=0, rejestr wartości=0, data_error=1,
- krytyczny błąd inicjalizacji Modbus/RS-485: kontrolowany restart,
- licznik błędów Modbus nasyca się w rejestrze na `0xFFFF`.

## OTA i zdrowie platformy

Od Stage 2 zatwierdzenie obrazu oczekującego na weryfikację wymaga gotowości:

- GPIO,
- I²C,
- RS-485 / Modbus.

Obecność SEN55 nadal nie jest wymagana do potwierdzenia obrazu, ponieważ jest urządzeniem zewnętrznym i może być chwilowo odłączona podczas serwisu.

## Narzędzie testowe PC

Dodano:

```text
tools/read_modbus_sensor.py
```

Narzędzie:

- nie korzysta z wysokopoziomowej biblioteki Modbus,
- buduje ramkę `0x04` bezpośrednio,
- oblicza i sprawdza CRC-16 Modbus,
- kontroluje adres, funkcję i długość odpowiedzi,
- obsługuje wyjątki Modbus,
- dekoduje temperaturę signed int16,
- składa wartości 32-bit w kolejności high/low,
- pokazuje aktywne bity statusu i dostępności.

Jedyną zależnością środowiska PC jest `pyserial`.

## Walidacja automatyczna

Dodano hostowy test `test_modbus_register_map.cpp`, który sprawdza:

- skalowanie wszystkich wartości,
- kodowanie ujemnej temperatury,
- mapę statusu,
- pola niedostępne,
- saturację wartości i liczników,
- kolejność słów wartości 32-bit,
- wersję firmware i mapy.

Workflow wykonuje test z:

```text
-std=c++20 -Wall -Wextra -Werror
```

oraz pełny build ESP-IDF 6.0.2.

## Walidacja fizyczna wymagana

1. Flash firmware `0.2.0-stage2`.
2. Potwierdzenie logu startowego Modbus RTU.
3. Połączenie KAmod A+/B- z konwerterem USB–RS485.
4. Odczyt 19 rejestrów przez komputer.
5. Porównanie wartości z logiem USB.
6. Odłączenie SEN55 i potwierdzenie:
   - valid=0,
   - present=0,
   - stale=1,
   - offline=1.
7. Ponowne podłączenie i powrót valid=1.
8. Minimum 30 minut ciągłego odpytywania.
9. Test złego adresu slave.
10. Test funkcji zapisu i wyjątku Modbus.
11. Zimny start całego urządzenia.

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

Stage 2A można zamknąć dopiero po fizycznym odczycie RS-485 i teście odporności. Następnie można rozpocząć Stage 2B: konfigurację adresów oraz test dwóch węzłów na jednej magistrali.
