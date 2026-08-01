# Stage 2 — incydent bezpieczeństwa poziomów UART DFR0845 / CM5

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Streszczenie

Podczas bring-up dwóch modułów DFRobot DFR0845 stwierdzono, że zasilanie modułów z pinu 3,3 V CM5IO powoduje zbyt duże obciążenie podczas startu CM5. Moduły przełączono na zasilanie 5 V i pozostawiono bezpośrednie połączenia UART z GPIO CM5.

Po analizie oficjalnego schematu DFR0845 uznano tę konfigurację za elektrycznie niebezpieczną:

- zewnętrzna strona translatora UART DFR0845 jest odniesiona do `VCC_IN`,
- przy `VCC_IN = 5 V` wyjścia UART nie mogą być traktowane jako bezpieczne dla wejść 3,3 V CM5,
- UART-y Raspberry Pi/CM5 nie są odporne na 5 V.

## Zaobserwowany wynik

Testy jednostkowe:

```text
Ran 43 tests
OK
```

Test elektryczny dwóch DFR0845:

```json
{
  "ok": false,
  "error": "RS-485 loopback A->B failed: RS-485 response timed out after 0 of 10 bytes"
}
```

Timeout nie jest dowodem uszkodzenia CM5 ani DFR0845. Oznacza jedynie brak odebranych bajtów w kierunku UART0/DFR0845 nr 1 → UART2/DFR0845 nr 2. Dalsza diagnostyka została wstrzymana ze względu na ryzyko napięciowe.

## Natychmiastowe działanie

- wstrzymać kolejne testy pętli,
- wyłączyć CM5,
- odłączyć oba DFR0845 zasilane z 5 V od GPIO UART,
- nie podawać sygnału `T` modułu zasilanego z 5 V na wejście RX CM5,
- zachować konfigurację overlayów UART0/UART2 — została poprawnie zweryfikowana i nie jest przyczyną incydentu.

## Docelowa korekta

Preferowane rozwiązanie:

- osobny gotowy stabilizator step-down 5 V → 3,3 V,
- wydajność minimum 2 A, preferowane 3 A dla dwóch modułów i zapasu rozruchowego,
- oba DFR0845 zasilane z jego wyjścia 3,3 V,
- wspólna masa stabilizatora, CM5 i strony UART DFR0845,
- bezpośrednie TX/RX dopiero po pomiarze napięcia wyjściowego stabilizatora.

Alternatywa:

- pozostawienie DFR0845 na 5 V,
- pełna konwersja poziomów 3,3 V ↔ 5 V osobno dla obu kierunków każdego UART-u.

Alternatywa nie jest preferowana ze względu na większą liczbę elementów.

## Co pozostaje zweryfikowane

- `/dev/serial0 -> /dev/ttyAMA0` działa na GPIO14/15,
- `/dev/ttyAMA2` działa na GPIO4/5,
- oba porty otwierają się równocześnie w niezależnych workerach,
- `ttyAMA10` pozostaje osobnym debug UART-em,
- warstwa Modbus RTU i testy regresyjne są poprawne.

## Następny bezpieczny krok

Po całkowitym odłączeniu DFR0845 można wykonać test 3,3 V bezpośrednio między UART0 i UART2, aby niezależnie potwierdzić transmisję CM5 i oprogramowanie. Test DFR0845 należy powtórzyć dopiero po dodaniu bezpiecznego zasilania 3,3 V lub konwersji poziomów.
