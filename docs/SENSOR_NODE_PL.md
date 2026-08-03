# Węzeł pomiarowy KAmod ESP32 POW RS485 + SEN55

## Cel

Węzeł pomiarowy znajduje się blisko reprezentatywnego punktu pomiaru. SEN55 komunikuje się lokalnie z modułem KAmod po krótkiej magistrali I²C. Do CM5 nie prowadzimy długiego I²C.

## Platforma

- moduł: KAmod ESP32 POW RS485,
- mikrokontroler: ESP32-WROOM-32D, 4 MB flash,
- framework: ESP-IDF,
- czujnik: Sensirion SEN55,
- produkcyjny kanał danych w późniejszym etapie: Modbus RTU po RS-485,
- niezależny kanał serwisowy w późniejszym etapie: prywatne Wi-Fi CM5.

## Podział firmware

```text
Firmware
├── app
├── sen55
├── diagnostics
├── logging
├── config
├── platform
├── services
└── drivers
```

Zależności są jednokierunkowe. `main.cpp` uruchamia aplikację, ale nie zawiera obsługi I²C ani protokołu SEN55.

## Stage 1 — stabilny sterownik czujnika

Zakres pierwszego etapu:

- projekt ESP-IDF i konfiguracja CMake,
- `sdkconfig.defaults`,
- partycje OTA A/B, rollback i coredump,
- logowanie przez USB,
- konfiguracja GPIO,
- konfiguracja I²C,
- wykrywanie SEN55,
- odczyt nazwy i wersji urządzenia,
- rozpoczęcie pomiaru ciągłego,
- walidacja CRC,
- pierwszy i kolejne odczyty,
- kontrolowana obsługa odłączenia i ponownego podłączenia czujnika.

Poza Stage 1 pozostają:

- Modbus RTU,
- RS-485,
- heartbeat,
- Wi-Fi,
- pobieranie OTA,
- komunikacja z CM5,
- AI.

## Konfiguracja sprzętowa Stage 1

| Funkcja | GPIO / parametr |
|---|---|
| I²C SDA | GPIO33 |
| I²C SCL | GPIO32 |
| LED statusowa D6 | GPIO2 |
| adres SEN55 | `0x69` |
| szybkość I²C | 100 kHz |
| USB / UART0 | GPIO1 TX, GPIO3 RX, 115200 bit/s |
| RS-485 RX — zarezerwowane | GPIO27 |
| RS-485 TX — zarezerwowane | GPIO25 |
| RS-485 DE/RE — zarezerwowane | GPIO26 |

## Zweryfikowany schemat połączeń SEN55

Poniższe połączenie jest obowiązującym schematem po korekcie wykrytej podczas testu stanowiskowego 2026-08-03.

| SEN55 | Kolor przewodu | KAmod ESP32 POW RS485 |
|---|---|---|
| VDD | czerwony | 5 V |
| GND | czarny | GND |
| SDA | zielony | GPIO33 / SDA, fizyczny pin 3 złącza J1 |
| SCL | żółty | GPIO32 / SCL, fizyczny pin 5 złącza J1 |
| SEL | niebieski | GND |
| NC | fioletowy | nie podłączać |

Względem pierwszej wersji instrukcji przewody zielony i żółty zostały zamienione miejscami: końcowo zielony SDA trafia na GPIO33, a żółty SCL na GPIO32. Jest to zgodne z oznaczeniami I²C płytki KAmod. Po wgraniu firmware zawierającego tę korektę nie należy stosować tymczasowego skrzyżowania SDA/SCL użytego podczas diagnostyki.

Zalecane zasilanie docelowe KAmod: 12 V podane na wejście `POWER`. Podczas testu stanowiskowego na SEN55 zmierzono 5,05 V, a na liniach SDA i SCL po 3,28 V. Linia SEL miała 0 V.

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

- każdy blok danych SEN55 przechodzi kontrolę CRC-8,
- błąd czujnika nie może zawiesić firmware,
- po trzech kolejnych błędach węzeł przechodzi do stanu offline,
- wykrywanie jest ponawiane co 5 sekund,
- ponowne podłączenie czujnika nie wymaga restartu ESP32,
- obraz OTA jest zatwierdzany na podstawie zdrowia platformy, a nie obecności zewnętrznego czujnika,
- krytyczny błąd inicjalizacji GPIO lub I²C prowadzi do kontrolowanego restartu; dla obrazu oczekującego na weryfikację umożliwia to rollback.

## Miernik diagnostyczny Stage 1

Log USB pokazuje:

- wersję firmware i ESP-IDF,
- przyczynę resetu,
- aktywną partycję,
- stan obrazu OTA,
- wynik inicjalizacji GPIO i I²C,
- nazwę oraz wersję SEN55,
- przejścia stanów usługi,
- błędy I²C i CRC,
- pełne pomiary.

## Montaż czujnika

- nie montować bezpośrednio przy nawiewie ani wyciągu,
- nie montować tuż nad piecem,
- zapewnić swobodny przepływ powietrza przez SEN55,
- ograniczyć osadzanie mgły i rozprysków z myjek,
- obudowa nie może tłumić przepływu przez kanał czujnika,
- moduł powinien być dostępny serwisowo.

## Ograniczenie pomiarowe

VOC Index jest wskaźnikiem jakościowym, a nie bezpośrednim pomiarem stężenia konkretnego rozpuszczalnika. W projekcie służy do wykrywania trendu i wyraźnego pogorszenia jakości powietrza, nie do certyfikowanego pomiaru bezpieczeństwa chemicznego.

Szczegóły implementacji znajdują się w `firmware/sensor-node/README.md` oraz raporcie `docs/reports/KAMOD_SEN55_FIRMWARE_STAGE1_IMPLEMENTATION_PL.md`.
