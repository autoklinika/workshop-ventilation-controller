# Węzeł pomiarowy KAmod ESP32 POW RS485 + SEN55

## Cel

Węzeł pomiarowy znajduje się blisko reprezentatywnego punktu pomiaru. SEN55 komunikuje się lokalnie z modułem KAmod po krótkiej magistrali I²C. Pomiary i diagnostyka są przekazywane do nadrzędnego sterownika przez Modbus RTU po RS-485; do CM5 nie prowadzimy długiego I²C.

## Platforma

- moduł: KAmod ESP32 POW RS485,
- mikrokontroler: ESP32-WROOM-32D, 4 MB flash,
- framework: ESP-IDF 6.0.2,
- czujnik: Sensirion SEN55,
- produkcyjny kanał danych: Modbus RTU po RS-485,
- planowany niezależny kanał serwisowy: prywatne Wi-Fi CM5,
- aktualizacja firmware: docelowo OTA, z przygotowanym układem A/B i rollbackiem.

## Podział firmware

```text
Firmware
├── app
├── sen55
├── modbus
│   ├── register_map
│   └── modbus_rtu_slave
├── diagnostics
├── logging
├── config
├── platform
├── services
└── drivers
```

Zależności są jednokierunkowe. `main.cpp` uruchamia aplikację, ale nie zawiera obsługi I²C, protokołu SEN55 ani Modbus RTU. Sterownik SEN55 nie zna warstwy komunikacyjnej; Modbus otrzymuje gotowy snapshot pomiaru i diagnostyki.

## Stage 1 — sterownik SEN55

Status: **zakończony i zwalidowany sprzętowo 2026-08-03**.

Potwierdzono:

- inicjalizację GPIO i I²C,
- wykrywanie SEN55 pod adresem `0x69`,
- odczyt nazwy oraz wersji urządzenia,
- pomiar ciągły wszystkich ośmiu pól,
- kontrolę CRC Sensirion,
- przejście do stanu offline po utracie czujnika,
- automatyczny powrót pomiarów po ponownym podłączeniu,
- zimny start i restart płytki,
- poprawione przypisanie SDA GPIO33 / SCL GPIO32.

## Stage 2A — Modbus RTU tylko do odczytu

Status: **implementacja programowa w toku; walidacja fizyczna RS-485 wymagana**.

Zakres:

- oficjalny komponent `espressif/esp-modbus` 2.1.2,
- Modbus RTU slave,
- UART2 w trybie RS-485 half-duplex,
- stały adres urządzenia `1`,
- `19200 bit/s`, `8N1`,
- funkcja `0x04` — Read Input Registers,
- wersjonowana mapa 19 rejestrów wejściowych,
- pomiary SEN55, maska dostępności i status węzła,
- wiek ostatniego pomiaru,
- liczniki błędów SEN55 i usługi Modbus,
- czas pracy, wersja firmware i wersja mapy,
- sekwencja pomiaru,
- brak jakichkolwiek rejestrów zapisywalnych.

Stage 2A celowo nie pozwala zmienić adresu, prędkości transmisji ani konfiguracji czujnika. Najpierw musi zostać zwalidowany stabilny kanał tylko do odczytu.

## Konfiguracja sprzętowa

| Funkcja | GPIO / parametr |
|---|---|
| I²C SDA | GPIO33 |
| I²C SCL | GPIO32 |
| LED statusowa D6 | GPIO2 |
| adres SEN55 | `0x69` |
| szybkość I²C | 100 kHz |
| USB / UART0 | GPIO1 TX, GPIO3 RX, 115200 bit/s |
| Modbus UART | UART2 |
| RS-485 RX | GPIO27 |
| RS-485 TX | GPIO25 |
| RS-485 DE/RE | GPIO26 |
| adres Modbus | `1` |
| prędkość Modbus | `19200 bit/s` |
| format | `8N1` |

## Zweryfikowany schemat połączeń SEN55

| SEN55 | Kolor przewodu | KAmod ESP32 POW RS485 |
|---|---|---|
| VDD | czerwony | 5 V |
| GND | czarny | GND |
| SDA | zielony | GPIO33 / SDA, fizyczny pin 3 złącza J1 |
| SCL | żółty | GPIO32 / SCL, fizyczny pin 5 złącza J1 |
| SEL | niebieski | GND |
| NC | fioletowy | nie podłączać |

Zalecane zasilanie docelowe KAmod: 12 V podane na wejście `POWER`. Podczas walidacji Stage 1 na SEN55 zmierzono 5,05 V, na SDA i SCL po 3,28 V, a na SEL 0 V.

## Połączenie RS-485 do testu

```text
KAmod A+  -> A / D+ konwertera USB–RS485
KAmod B-  -> B / D- konwertera USB–RS485
GND       -> GND konwertera, jeżeli adapter udostępnia zacisk masy
```

Oznaczenia A/B nie są stosowane jednakowo przez wszystkich producentów. Jeżeli połączenie nie odpowiada mimo prawidłowych parametrów, należy wyłączyć zasilanie i diagnostycznie zamienić A z B.

## Dane udostępniane przez Modbus

Pełny kontrakt znajduje się w `docs/MODBUS_MAP_PL.md`.

Najważniejsze zasady:

- rejestry odczytuje się funkcją `0x04`, od adresu `0`, w liczbie `19`,
- wszystkie wartości pomiarowe wymagają sprawdzenia maski dostępności,
- master musi sprawdzić bit `MEASUREMENT_VALID`,
- pomiar starszy niż 5 sekund jest oznaczany jako nieaktualny,
- po utracie SEN55 ostatnie liczby pozostają w mapie, ale nie są oznaczone jako ważne,
- wartości wielorejestrowe mają kolejność high word, potem low word,
- CM5 musi zweryfikować wersję mapy przed dekodowaniem.

## Mierzone wielkości

- PM1.0,
- PM2.5,
- PM4.0,
- PM10,
- wilgotność względna,
- temperatura,
- VOC Index,
- NOx Index,
- dostępność każdego pola,
- czas i numer kolejny pomiaru.

## Odporność na błędy

- każdy blok SEN55 przechodzi kontrolę CRC-8,
- po trzech kolejnych błędach usługa czujnika przechodzi do offline,
- wykrywanie SEN55 jest ponawiane co 5 sekund,
- Modbus działa niezależnie od obecności czujnika i nadal udostępnia diagnostykę,
- brak aktualnego pomiaru jest jawnie sygnalizowany statusem i wiekiem,
- mapa rejestrów jest aktualizowana pod blokadą kontrolera Modbus,
- krytyczny błąd inicjalizacji GPIO, I²C lub RS-485 prowadzi do kontrolowanego restartu,
- zatwierdzenie obrazu OTA wymaga gotowości GPIO, I²C i RS-485, ale nie wymaga obecności zewnętrznego SEN55.

## Diagnostyka serwisowa

Log USB pokazuje:

- wersję firmware i ESP-IDF,
- przyczynę resetu oraz aktywną partycję,
- inicjalizację I²C i UART2/RS-485,
- adres i prędkość Modbus,
- nazwę oraz wersję SEN55,
- przejścia stanów usługi,
- błędy I²C, CRC i Modbus,
- pełne pomiary.

Do niezależnego testu z komputera służy `tools/read_modbus_sensor.py`.

## Walidacja Stage 2A

Wymagane testy stanowiskowe:

1. flash firmware i potwierdzenie startu Modbus RTU w logu USB,
2. odczyt rejestrów 0–18 przez konwerter USB–RS485,
3. porównanie danych Modbus z logiem USB,
4. odłączenie SEN55 i sprawdzenie bitów stale/offline,
5. ponowne podłączenie i automatyczny powrót `MEASUREMENT_VALID`,
6. ciągłe odpytywanie przez co najmniej 30 minut,
7. próba złego adresu slave,
8. próba funkcji zapisu i potwierdzenie standardowego wyjątku Modbus,
9. zimny start całego węzła.

## Montaż czujnika

- nie montować bezpośrednio przy nawiewie ani wyciągu,
- nie montować tuż nad piecem,
- zapewnić swobodny przepływ powietrza przez SEN55,
- ograniczyć osadzanie mgły i rozprysków z myjek,
- obudowa nie może tłumić przepływu przez kanał czujnika,
- moduł powinien być dostępny serwisowo.

## Ograniczenie pomiarowe

VOC Index jest wskaźnikiem jakościowym, a nie bezpośrednim pomiarem stężenia konkretnego rozpuszczalnika. W projekcie służy do wykrywania trendu i wyraźnego pogorszenia jakości powietrza, nie do certyfikowanego pomiaru bezpieczeństwa chemicznego.
