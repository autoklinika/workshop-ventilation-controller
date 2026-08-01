# Raport walidacji analogowej DFRobot DFR0971

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Platforma testowa

- Raspberry Pi Compute Module 5 Wireless,
- 4 GB RAM,
- 32 GB eMMC,
- oficjalna CM5 IO Board,
- Raspberry Pi OS Lite 64-bit / Debian 13 `trixie`,
- magistrala I²C `/dev/i2c-1`,
- DFRobot Gravity DFR0971 / GP8403,
- adres I²C `0x58`,
- zasilanie modułu DAC z 3,3 V,
- pomiar wyjść multimetrem,
- wentylatory całkowicie odłączone podczas walidacji.

## Walidacja komunikacji

Potwierdzono:

- obecność urządzenia `/dev/i2c-1`,
- wykrycie DAC przez `i2cdetect -y 1` pod adresem `0x58`,
- poprawną odpowiedź narzędzia `tools/hardware/dac_cli.py probe`,
- odczyt bajtu kontrolnego `0x11`.

## Wyniki kanału 0

| Zadane napięcie | Zmierzone VOUT0 | VOUT1 podczas testu | Wynik |
|---:|---:|---:|---|
| 0 V | 0 V | 0 V | PASS |
| 2 V | 2 V | 0 V | PASS |
| 5 V | 5 V | 0 V | PASS |
| 8 V | 8 V | 0 V | PASS |
| 10 V | 10 V | 0 V | PASS |

## Wyniki kanału 1

Pełna sekwencja 0 V, 2 V, 5 V, 8 V i 10 V została wykonana pozytywnie. W każdym punkcie kanał 1 osiągnął zadaną wartość, a kanał 0 pozostawał na 0 V.

| Zadane napięcie | Zmierzone VOUT1 | VOUT0 podczas testu | Wynik |
|---:|---:|---:|---|
| 0 V | 0 V | 0 V | PASS |
| 2 V | 2 V | 0 V | PASS |
| 5 V | 5 V | 0 V | PASS |
| 8 V | 8 V | 0 V | PASS |
| 10 V | 10 V | 0 V | PASS |

## Wnioski

- oba kanały DAC generują poprawne napięcia w całym badanym zakresie 0–10 V,
- kanały są sterowane niezależnie,
- polecenie `zero` poprawnie sprowadza oba wyjścia do 0 V,
- sterownik Python i narzędzie CLI poprawnie komunikują się z rzeczywistym modułem,
- część analogowa DFR0971 jest gotowa do dalszych testów integracyjnych.

## Ograniczenia obecnej walidacji

Walidacja nie obejmuje jeszcze:

- zachowania wyjść podczas restartu CM5,
- zachowania po odłączeniu i ponownym podaniu zasilania,
- zachowania przy przerwaniu procesu sterującego,
- pracy z obciążeniem wejść 0–10 V wentylatorów,
- minimalnego napięcia startu wentylatorów,
- charakterystyki napięcie–prędkość,
- sprzętowego mechanizmu wymuszenia bezpiecznego stanu.

## Następny etap

1. ustawić kontrolowane napięcie testowe bez użycia funkcji `store`,
2. sprawdzić stan obu wyjść podczas restartu systemu,
3. sprawdzić stan wyjść po pełnym odłączeniu i ponownym podaniu zasilania,
4. ustalić wymagania bezpiecznego startu `ventilation-core`,
5. dopiero potem podłączyć jeden wentylator EC i rozpocząć charakterystykę 0–10 V.
