# Rejestr decyzji projektowych

## D-001 — Oddzielny projekt

Sterownik wentylacji jest niezależnym projektem. Nie łączymy go z ECU Platform ani CAN Research Tool.

## D-002 — Przeznaczenie stref

Strefa 1 służy do mycia i wygrzewania sterowników ECU. Sąsiednia strefa 2 jest pomieszczeniem lutowniczym z miejscowym odciągiem oraz rekuperatorem Prodmax.

## D-003 — Prosta filozofia działania

Nie budujemy rozbudowanego systemu analizy chemicznej. Podstawą jest częste przewietrzanie, a czujniki jakości powietrza stanowią pomoc dla automatyki.

## D-004 — Dwa niezależne wentylatory EC w strefie 1

Nawiew i wyciąg są sterowane osobno sygnałami 0–10 V. Pozwala to ustawić wyciąg nieco wyżej od nawiewu.

## D-005 — Raspberry Pi w rozdzielni DIN

Sterownik główny oraz zasilanie są montowane w rozdzielni. Raspberry Pi otrzymuje zasilanie z zasilacza 5 V na szynę DIN.

## D-006 — DAC 2 × 0–10 V

Do sterowania wentylatorami przyjęto DFRobot Gravity 2-Channel I²C DAC 0–10 V lub funkcjonalnie równoważny moduł po końcowej weryfikacji elektrycznej.

## D-007 — Zdalne moduły czujników

SEN55 nie będą łączone długą magistralą I²C z Raspberry Pi. Każda strefa otrzyma lokalny moduł SEN55 + STM32 + RS-485.

## D-008 — Modbus RTU

Komunikacja pomiędzy Raspberry Pi a węzłami czujników będzie realizowana przez RS-485 Modbus RTU.

## D-009 — SEN55 jako czujnik pomocniczy

VOC Index i PM służą do obserwacji trendów i uruchamiania mocniejszej wentylacji. Nie traktujemy ich jako certyfikowanego pomiaru stężenia konkretnej substancji.

## D-010 — Szczegóły sterowania później

Tryby, harmonogramy, progi, histerezy i reakcje awaryjne zostaną rozstrzygnięte na etapie pisania oprogramowania oraz testów w rzeczywistych pomieszczeniach.

## D-011 — Tacho opcjonalne

Odczyt Tacho jest pożądany diagnostycznie, ale przed podłączeniem do elektroniki trzeba ustalić charakterystykę elektryczną wyjścia. Dla Harmann ML EC.A 125/300 producent podaje 3 impulsy na obrót, ale nie określa wprost poziomów i typu wyjścia.

## D-012 — Brak LEL na obecnym etapie

Nie dodajemy obecnie detektora LEL ani innych rozbudowanych czujników gazowych. Możliwość ich późniejszego dołożenia pozostaje otwarta bez zmiany głównej architektury.

## D-013 — Druga strefa z rekuperatorem Prodmax

Do wspólnego systemu zostaje dołączone pomieszczenie lutownicze wyposażone w Prodmax PRO MINI 300 H/V CLASSIC, sterownik COMPIT AERO 4A2 i panel NANO COLOR 2.

## D-014 — Integracja przez oficjalny Modbus panelu

Preferowaną drogą integracji AERO 4A2 jest udokumentowany Modbus RTU panelu NANO COLOR 2. Nie odtwarzamy protokołu C14, jeżeli tryb Modbus działa na posiadanej wersji firmware.

## D-015 — AERO pozostaje sterownikiem nadrzędnym urządzenia

Raspberry Pi nie steruje bezpośrednio elementami wykonawczymi rekuperatora. Rozmrażanie, bypass, nagrzewnice, zabezpieczenia, alarmy oraz logika wentylatorów pozostają po stronie AERO 4A2.

## D-016 — Sterowanie rekuperatorem przez żądanie trybu

Raspberry Pi może odczytywać stan centrali i żądać czasowego wietrzenia lub zmiany trybu. Preferowanym poleceniem dynamicznym jest rejestr RAM 1081, a nie częste modyfikowanie trwałej konfiguracji.

## D-017 — Ochrona EEPROM

Nie używamy rejestrów EEPROM do cyklicznej automatyki. Dynamiczne sterowanie ma korzystać z obszaru RAM, aby nie skracać trwałości pamięci panelu.

## D-018 — Odporność na awarię Raspberry Pi

Wyłączenie lub awaria Raspberry Pi nie może blokować lokalnego panelu ani normalnej automatyki rekuperatora.

## D-019 — iNext wymaga weryfikacji

Przed wdrożeniem Modbus trzeba sprawdzić, czy konkretny firmware NANO COLOR 2 pozwala jednocześnie używać modułu iNext. Dokumentacja wskazuje możliwość wzajemnego wykluczania tych trybów.

## D-020 — Pierwsza walidacja tylko do odczytu

Pierwsze podłączenie zostanie wykonane przez izolowany interfejs RS-485. Najpierw odczytamy rejestry stanu i porównamy je z panelem. Zapis sterujący zostanie wykonany dopiero po potwierdzeniu poprawnej komunikacji i przypisania zacisków.