# Plan realizacji

## Etap 1 — Zamknięcie koncepcji sprzętowej

- potwierdzenie modeli obu wentylatorów,
- potwierdzenie Raspberry Pi,
- dobór zasilacza DIN,
- weryfikacja DAC 0–10 V,
- dobór interfejsów RS-485,
- decyzja o izolacji galwanicznej,
- sprawdzenie charakterystyki Tacho.

## Etap 2 — Prototyp modułu czujnika

- wybór konkretnego STM32,
- schemat SEN55 + STM32 + RS-485,
- prototyp na płytce rozwojowej,
- odczyt wszystkich wartości SEN55,
- implementacja Modbus RTU slave,
- test odporności na przerwanie komunikacji i restart.

## Etap 3 — Sterowanie wentylatorami

- uruchomienie DAC 0–10 V,
- niezależna regulacja nawiewu i wyciągu,
- pomiar rzeczywistej zależności napięcie–wydajność,
- ustalenie minimalnego napięcia startu,
- próba odczytu Tacho,
- test bezpiecznego zachowania po restarcie Raspberry Pi.

## Etap 4 — Pierwsza wersja oprogramowania Raspberry Pi

- obsługa Modbus RTU master,
- odczyt i walidacja pomiarów,
- ręczne sterowanie dwoma kanałami 0–10 V,
- podstawowe stany ECO, AUTO, PRZEWIETRZANIE i BOOST,
- konfiguracja czasu oraz mocy,
- lokalny dziennik zdarzeń.

## Etap 5 — Instalacja próbna

- montaż w rozdzielni,
- montaż czujnika w pomieszczeniu,
- test komunikacji na docelowych przewodach,
- obserwacja VOC, PM, temperatury i wilgotności podczas normalnej pracy,
- sprawdzenie bilansu nawiew–wyciąg,
- weryfikacja hałasu i wydajności.

## Etap 6 — Strojenie logiki

- ustalenie harmonogramu przewietrzania,
- dobór czasu przewietrzania po pracy,
- ustalenie progów i histerez,
- określenie reakcji na utratę czujnika,
- określenie reakcji na brak Tacho,
- dodanie wejść „myjka pracuje” i „piec pracuje”, jeżeli okażą się potrzebne.

## Etap 7 — Wersja docelowa

- uporządkowany schemat elektryczny,
- docelowa płytka modułu czujnika,
- obudowy i oznaczenia przewodów,
- instrukcja montażu i uruchomienia,
- kopia konfiguracji,
- raport z testów końcowych.

## Najbliższy punkt kontrolny

Po potwierdzeniu dokładnych modeli dostępnych elementów należy przygotować:

1. finalną listę zakupową,
2. schemat połączeń rozdzielni,
3. wybór konkretnego STM32 i transceivera RS-485,
4. pierwszy plan pinów modułu czujnika.
