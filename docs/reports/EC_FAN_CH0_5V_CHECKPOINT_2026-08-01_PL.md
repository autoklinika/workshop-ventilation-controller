# Checkpoint wentylatora EC — kanał 0, 5 V

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Warunki testu

- pierwszy wentylator EC podłączony do kanału 0 DFR0971,
- sterowanie z CM5 przez I²C,
- napięcie zadane: `5 V`,
- drugi kanał pozostawał niewykorzystany.

## Wynik

Potwierdzono:

- wentylator startuje pewnie,
- prędkość wyraźnie wzrasta względem pracy przy `2 V`,
- praca pozostaje stabilna,
- po zakończeniu testu i powrocie wyjścia do `0 V` wentylator zatrzymuje się.

Wynik: `PASS`.
