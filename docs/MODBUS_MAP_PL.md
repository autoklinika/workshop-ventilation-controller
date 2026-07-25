# Wstępna mapa Modbus RTU

Dokument określa roboczą mapę rejestrów modułu SEN55 + STM32. Ostateczne skalowanie zostanie zatwierdzone podczas implementacji firmware.

## Parametry domyślne

- tryb: Modbus RTU slave,
- adres: 1,
- prędkość: 19200 bit/s,
- format: 8N1.

## Rejestry wejściowe — tylko odczyt

| Adres | Nazwa | Jednostka / skala |
|---:|---|---|
| 0 | PM1.0 | µg/m³ × 10 |
| 1 | PM2.5 | µg/m³ × 10 |
| 2 | PM4.0 | µg/m³ × 10 |
| 3 | PM10 | µg/m³ × 10 |
| 4 | Wilgotność | %RH × 100 |
| 5 | Temperatura | °C × 100, signed int16 |
| 6 | VOC Index | wartość × 10 |
| 7 | NOx Index | wartość × 10 |
| 8 | Status czujnika | bitmask |
| 9 | Wiek ostatniego pomiaru | sekundy |
| 10 | Licznik błędów SEN55 | licznik 16-bit |
| 11 | Licznik błędów Modbus | licznik 16-bit |
| 12–13 | Czas pracy | sekundy, uint32 |
| 14 | Wersja firmware major/minor | packed uint16 |
| 15 | Wersja mapy rejestrów | uint16 |

## Rejestry holding — konfiguracja

| Adres | Nazwa | Uwagi |
|---:|---|---|
| 100 | Adres Modbus | Zakres 1–247 |
| 101 | Kod prędkości transmisji | Mapa kodów do ustalenia |
| 102 | Interwał pomiaru | sekundy |
| 103 | Komenda serwisowa | zapis wartości chronionej |
| 104 | Reset liczników błędów | zapis wartości chronionej |

## Status czujnika — propozycja bitów

- bit 0: pomiar ważny,
- bit 1: SEN55 odpowiada,
- bit 2: pomiar nieaktualny,
- bit 3: błąd I²C,
- bit 4: błąd danych,
- bit 5: trwa inicjalizacja,
- bit 6: wymagany restart czujnika,
- bit 7: błąd wewnętrzny STM32.

## Zasady

- Raspberry Pi nie może traktować wartości pomiarowej jako ważnej bez sprawdzenia statusu.
- Po utracie komunikacji STM32 zachowuje ostatni pomiar, ale zwiększa jego wiek i oznacza go jako nieaktualny.
- Zmiany adresu i prędkości wymagają walidacji oraz kontrolowanego restartu.
- Rejestry konfiguracyjne powinny być chronione wartością odblokowującą lub osobną sekwencją serwisową.
