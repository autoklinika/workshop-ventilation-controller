# Checkpoint testu wentylatora EC — kanał 0, 2 V

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Konfiguracja

- jeden wentylator EC podłączony do kanału 0 DFR0971,
- kanał 1 pozostaje na 0 V,
- sterowanie z CM5 przez I²C i DFR0971,
- test wykonany poleceniem `fan-test`.

## Wynik

Przy zadanym napięciu `2 V`:

- wentylator startuje pewnie z postoju,
- pracuje stabilnie,
- po zakończeniu testu i sprowadzeniu wyjścia do `0 V` zatrzymuje się poprawnie.

Wynik: `PASS`.

## Następny punkt

Sprawdzić zachowanie przy `5 V`, następnie `8 V` i `10 V`, każdorazowo potwierdzając poprawny powrót do `0 V`.
