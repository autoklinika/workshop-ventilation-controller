# Stage 2 — podłączenie dwóch DFR0845 do UART CM5

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Status bezpieczeństwa — obowiązująca korekta

Bezpośrednie połączenie linii UART DFR0845 z CM5 przy zasilaniu DFR0845 napięciem **5 V jest zabronione**.

Powód:

- UART CM5 pracuje w logice 3,3 V i nie jest odporny na 5 V,
- schemat DFR0845 pokazuje, że strona zewnętrzna translatora UART jest odniesiona i podciągnięta do `VCC_IN`,
- przy `VCC_IN = 5 V` nie można uznać wyjścia `T` za bezpieczne dla wejścia RX CM5.

Wcześniejsze zalecenie podłączenia `+` DFR0845 bezpośrednio do 5 V CM5IO przy jednoczesnym bezpośrednim połączeniu `T/R` z GPIO zostało wycofane.

## Zweryfikowana obserwacja sprzętowa

Zasilanie DFR0845 bezpośrednio z pinu 3,3 V CM5IO powodowało zbyt duże obciążenie podczas startu i CM5 nie uruchamiał się prawidłowo.

Nie oznacza to, że należy zasilać moduł z 5 V przy bezpośrednim UART. Oznacza to, że DFR0845 wymaga osobnego, wydajnego źródła 3,3 V.

## Obowiązująca architektura zasilania

Dwa DFR0845 będą zasilane z osobnego gotowego stabilizatora step-down:

```text
CM5IO 5 V / zasilacz 5 V
          |
          v
stabilizator 5 V -> 3,3 V, zalecane minimum 2 A, preferowane 3 A
          |
          +---- DFR0845 nr 1: + = 3,3 V
          |
          +---- DFR0845 nr 2: + = 3,3 V
```

Masa wyjścia stabilizatora 3,3 V musi być połączona z masą UART CM5 i pinami `-` obu DFR0845.

Przy takim zasilaniu zewnętrzna strona UART DFR0845 pracuje w domenie 3,3 V i może być bezpośrednio połączona z UART CM5.

Alternatywa techniczna — pozostawienie zasilania DFR0845 na 5 V i dodanie pełnych konwerterów poziomów 3,3 V ↔ 5 V dla każdej linii UART — nie jest obecnie preferowana, ponieważ zwiększa liczbę elementów i punktów awarii.

## Złącze Gravity DFR0845

| Kolor | Oznaczenie | Funkcja modułu |
|---|---|---|
| czerwony | `+` | VCC; docelowo 3,3 V z osobnego stabilizatora |
| czarny | `-` | masa UART |
| niebieski | `R` | wejście RX modułu |
| zielony | `T` | wyjście TX modułu |

Połączenia sygnałowe są skrzyżowane funkcjonalnie:

- TX CM5 → `R` DFR0845 — przewód niebieski,
- RX CM5 ← `T` DFR0845 — przewód zielony.

## DFR0845 nr 1 — UART0

Overlay: `uart0-pi5`

| DFR0845 | Kolor | CM5 / zasilanie |
|---|---|---|
| `+` | czerwony | 3,3 V z osobnego stabilizatora |
| `-` | czarny | wspólna masa UART |
| `R` | niebieski | pin 8, GPIO14 / TXD0 |
| `T` | zielony | pin 10, GPIO15 / RXD0 |

Urządzenie Linux potwierdzone na CM5:

```text
/dev/serial0 -> /dev/ttyAMA0
```

## DFR0845 nr 2 — UART2

Overlay: `uart2-pi5`

| DFR0845 | Kolor | CM5 / zasilanie |
|---|---|---|
| `+` | czerwony | 3,3 V z osobnego stabilizatora |
| `-` | czarny | wspólna masa UART |
| `R` | niebieski | pin 7, GPIO4 / TXD2 |
| `T` | zielony | pin 29, GPIO5 / RXD2 |

Urządzenie Linux potwierdzone na CM5:

```text
/dev/ttyAMA2
```

## Konfiguracja Raspberry Pi OS — zweryfikowana

W `/boot/firmware/config.txt` aktywne są:

```ini
enable_uart=1
dtoverlay=uart0-pi5
dtoverlay=uart2-pi5
```

Potwierdzone funkcje pinów:

```text
GPIO14 = TXD0
GPIO15 = RXD0
GPIO4  = TXD2
GPIO5  = RXD2
```

`/dev/ttyAMA10` jest debug UART-em i nie jest używany do RS-485.

## Zaciski RS-485

Dla dwóch modułów pracujących w teście punkt-punkt:

```text
A   <-> A
B   <-> B
GND <-> GND strony izolowanej RS-485
```

Zaciski `12V` oraz `12V-IN` nie uczestniczą w teście.

Terminacja 120 Ω pozostaje wyłączona podczas krótkiego testu stanowiskowego, chyba że późniejszy pomiar lub dokumentacja urządzenia wykażą potrzebę jej włączenia.

## Procedura natychmiastowa po wykryciu ryzyka

1. Wyłączyć CM5.
2. Odłączyć zasilanie `+` obu DFR0845 od 5 V.
3. Odłączyć co najmniej przewody `T` od wejść RX CM5; preferowane jest całkowite odłączenie przewodów Gravity do czasu dodania stabilizatora 3,3 V.
4. Nie wykonywać kolejnych prób `rs485ctl loopback` w konfiguracji 5 V bez konwersji poziomów.
5. Po zamontowaniu osobnego stabilizatora 3,3 V ponownie zweryfikować napięcie multimetrem przed podłączeniem linii UART.

## Stan Stage 2

Warstwa systemowa została potwierdzona:

- oba UART-y istnieją,
- oba porty otwierają się osobno i równocześnie,
- workery działają bez kolizji,
- testy jednostkowe przechodzą.

Test elektryczny DFR0845 pozostaje wstrzymany do czasu bezpiecznego zasilenia ich strony UART napięciem 3,3 V.
