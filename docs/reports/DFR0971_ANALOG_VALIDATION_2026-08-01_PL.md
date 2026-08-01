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
- wentylatory całkowicie odłączone podczas walidacji samego DAC.

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

## Test pełnego zaniku zasilania

Przed odłączeniem zasilania ustawiono:

- `VOUT0 = 5 V`,
- `VOUT1 = 0 V`.

Następnie całkowicie odłączono zasilanie CM5 IO Board i DFR0971, odczekano około 10 sekund i ponownie podano zasilanie.

Potwierdzone zachowanie:

- po zaniku zasilania napięcia wyjściowe spadły do 0 V,
- po ponownym podaniu zasilania DFR0971 uruchomił oba kanały w stanie 0 V,
- oba kanały utrzymywały 0 V bez uruchamiania jakiegokolwiek skryptu,
- poprzednia wartość 5 V nie została przywrócona, ponieważ podczas testów nie używano funkcji nieulotnego zapisu `store`.

Wniosek: pełny zanik zasilania przywraca DFR0971 do bezpiecznego stanu 0 V. Zachowanie po miękkim restarcie i po pełnym zaniku zasilania jest różne i musi być uwzględnione przez `ventilation-core`.

## Pierwsze uruchomienie wentylatora EC

Po zakończeniu walidacji samego DAC do kanału 0 podłączono jeden wentylator EC przez wejście sterujące 0–10 V. Drugi kanał DAC oraz sygnał Tacho pozostały niewykorzystane.

Potwierdzono:

- wentylator poprawnie zareagował na napięcie sterujące z DFR0971,
- tor `CM5 → I²C → DFR0971 → 0–10 V → wentylator EC` działa na rzeczywistym obciążeniu,
- wspólna masa sterowania i sygnał 0–10 V zostały podłączone poprawnie,
- nie stwierdzono problemu z podstawową kompatybilnością elektryczną wejścia sterującego wentylatora i wyjścia DFR0971.

Jest to pierwszy pozytywny test wykonawczy systemu. Dokładne napięcie startu, minimalne napięcie podtrzymania oraz charakterystyka napięcie–prędkość nie zostały jeszcze wyznaczone.

## Wnioski

- oba kanały DAC generują poprawne napięcia w całym badanym zakresie 0–10 V,
- kanały są sterowane niezależnie,
- polecenie `zero` poprawnie sprowadza oba wyjścia do 0 V,
- sterownik Python i narzędzie CLI poprawnie komunikują się z rzeczywistym modułem,
- część analogowa DFR0971 jest gotowa do dalszych testów integracyjnych,
- miękki restart systemu nie powoduje automatycznego przejścia wyjść do 0 V,
- pełny zanik zasilania powoduje start obu kanałów od 0 V,
- `ventilation-core` musi jawnie przejąć kontrolę nad DAC po starcie i ustawić stan zgodny z polityką bezpieczeństwa,
- funkcji `store` nie należy używać do bieżącego sterowania wentylatorami,
- pierwszy wentylator EC został skutecznie uruchomiony z CM5 przez DFR0971.

## Ograniczenia obecnej walidacji

Walidacja nie obejmuje jeszcze:

- zachowania przy awaryjnym przerwaniu procesu bez restartu systemu,
- dokładnego minimalnego napięcia startu wentylatora,
- minimalnego napięcia podtrzymania obrotów,
- pełnej charakterystyki napięcie–prędkość,
- testu drugiego wentylatora,
- sygnału Tacho,
- sprzętowego mechanizmu wymuszenia bezpiecznego stanu.

## Następny etap

1. wyznaczyć minimalne napięcie startu pierwszego wentylatora małymi krokami,
2. wyznaczyć minimalne napięcie podtrzymania po wcześniejszym rozpędzeniu,
3. sprawdzić zachowanie przy 0 V, 2 V, 5 V, 8 V i 10 V,
4. zanotować obserwowaną zmianę prędkości i hałasu,
5. po zakończeniu testu zawsze sprowadzić oba kanały do 0 V,
6. nie podłączać jeszcze drugiego wentylatora ani sygnału Tacho.
