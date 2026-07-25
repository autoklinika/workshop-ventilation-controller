# Rejestr decyzji projektowych

## D-001 — Oddzielny projekt

Sterownik wentylacji jest niezależnym projektem. Nie łączymy go z ECU Platform ani CAN Research Tool.

## D-002 — Przeznaczenie pomieszczenia

Pomieszczenie służy do mycia i wygrzewania sterowników ECU. Nie projektujemy systemu pod stanowisko lutownicze.

## D-003 — Prosta filozofia działania

Nie budujemy rozbudowanego systemu analizy chemicznej. Podstawą jest częste przewietrzanie, a czujnik jakości powietrza stanowi pomoc dla automatyki.

## D-004 — Dwa niezależne wentylatory EC

Nawiew i wyciąg są sterowane osobno sygnałami 0–10 V. Pozwala to ustawić wyciąg nieco wyżej od nawiewu.

## D-005 — Raspberry Pi w rozdzielni DIN

Sterownik główny oraz zasilanie są montowane w rozdzielni. Raspberry Pi otrzymuje zasilanie z zasilacza 5 V na szynę DIN.

## D-006 — DAC 2 × 0–10 V

Do sterowania wentylatorami przyjęto DFRobot Gravity 2-Channel I²C DAC 0–10 V lub funkcjonalnie równoważny moduł po końcowej weryfikacji elektrycznej.

## D-007 — Zdalny moduł czujnika

SEN55 nie będzie łączony długą magistralą I²C z Raspberry Pi. Powstanie lokalny moduł SEN55 + STM32 + RS-485.

## D-008 — Modbus RTU

Komunikacja pomiędzy Raspberry Pi a węzłem czujnika będzie realizowana przez RS-485 Modbus RTU.

## D-009 — SEN55 jako czujnik pomocniczy

VOC Index i PM służą do obserwacji trendów i uruchamiania mocniejszej wentylacji. Nie traktujemy ich jako certyfikowanego pomiaru stężenia konkretnej substancji.

## D-010 — Szczegóły sterowania później

Tryby, harmonogramy, progi, histerezy i reakcje awaryjne zostaną rozstrzygnięte na etapie pisania oprogramowania oraz testów w rzeczywistym pomieszczeniu.

## D-011 — Tacho opcjonalne

Odczyt Tacho jest pożądany diagnostycznie, ale przed podłączeniem do elektroniki trzeba ustalić charakterystykę elektryczną wyjścia. Dla Harmann ML EC.A 125/300 producent podaje 3 impulsy na obrót, ale nie określa wprost poziomów i typu wyjścia.

## D-012 — Brak LEL na obecnym etapie

Nie dodajemy obecnie detektora LEL ani innych rozbudowanych czujników gazowych. Możliwość ich późniejszego dołożenia pozostaje otwarta bez zmiany głównej architektury.
