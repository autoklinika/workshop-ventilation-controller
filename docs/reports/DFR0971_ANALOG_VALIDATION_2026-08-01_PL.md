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

## Test miękkiego restartu CM5

Przed restartem ustawiono:

- `VOUT0 = 5 V`,
- `VOUT1 = 0 V`.

Następnie wykonano `sudo reboot` bez odłączania zasilania CM5 IO Board i modułu DAC.

Potwierdzone zachowanie:

- podczas całego restartu `VOUT0` pozostawało na 5 V,
- podczas całego restartu `VOUT1` pozostawało na 0 V,
- po ponownym uruchomieniu systemu, przed uruchomieniem skryptu sterującego, wyjścia nadal miały 5 V i 0 V,
- po uruchomieniu polecenia `zero` oba kanały poprawnie przeszły do 0 V.

Wniosek: miękki restart CM5 nie resetuje DFR0971, ponieważ moduł DAC pozostaje zasilany. Ostatnie napięcia wyjściowe są utrzymywane do chwili otrzymania kolejnej komendy I²C albo do zaniku zasilania modułu.

## Wnioski

- oba kanały DAC generują poprawne napięcia w całym badanym zakresie 0–10 V,
- kanały są sterowane niezależnie,
- polecenie `zero` poprawnie sprowadza oba wyjścia do 0 V,
- sterownik Python i narzędzie CLI poprawnie komunikują się z rzeczywistym modułem,
- część analogowa DFR0971 jest gotowa do dalszych testów integracyjnych,
- miękki restart systemu nie powoduje automatycznego przejścia wyjść do 0 V,
- `ventilation-core` musi jawnie przejąć kontrolę nad DAC po starcie i ustawić stan zgodny z polityką bezpieczeństwa.

## Ograniczenia obecnej walidacji

Walidacja nie obejmuje jeszcze:

- zachowania po pełnym odłączeniu i ponownym podaniu zasilania,
- zachowania przy awaryjnym przerwaniu procesu bez miękkiego restartu,
- pracy z obciążeniem wejść 0–10 V wentylatorów,
- minimalnego napięcia startu wentylatorów,
- charakterystyki napięcie–prędkość,
- sprzętowego mechanizmu wymuszenia bezpiecznego stanu.

## Następny etap

1. ustawić kontrolowane napięcie testowe bez użycia funkcji `store`,
2. wykonać pełne odłączenie zasilania CM5 IO Board i DFR0971,
3. ponownie podać zasilanie i zmierzyć wyjścia przed uruchomieniem jakiegokolwiek skryptu,
4. ustalić docelową politykę startu `ventilation-core`,
5. dopiero potem podłączyć jeden wentylator EC i rozpocząć charakterystykę 0–10 V.
