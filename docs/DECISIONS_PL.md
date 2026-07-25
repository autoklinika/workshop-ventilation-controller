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

## D-021 — UI jako pulpit jakości powietrza

Interfejs użytkownika nie będzie technicznym panelem wentylatorów i rekuperatora. Ekran główny ma przedstawiać stan jakości powietrza oraz reakcję systemu w sposób zrozumiały bez znajomości zastosowanego sprzętu.

## D-022 — Żywy plan warsztatu

Preferowany ekran główny pokazuje uproszczony plan dwóch pomieszczeń, dominujący status każdej strefy, aktualny sposób działania wentylacji i ostatnie ważne zdarzenie.

## D-023 — Nazwy użytkowe zamiast nazw urządzeń

W codziennym interfejsie stosujemy nazwy `Mycie i wygrzewanie ECU`, `Pomieszczenie lutowania` i `Przewietrzanie`. Nazwy AERO, SEN55, C14, DAC, Modbus oraz numery rejestrów są widoczne wyłącznie w trybie serwisowym.

## D-024 — Wyjaśnialna automatyka

Każda automatyczna zmiana wentylacji powinna zapisywać czas, powód, stan przed zmianą, wykonaną akcję i wynik. Historia ma tłumaczyć decyzje systemu, a nie ograniczać się do wykresów parametrów.

## D-025 — Oddzielny tryb serwisowy

Surowe rejestry, diagnostyka RS-485, wartości DAC, Tacho, wersje firmware i testy wykonawcze zostaną odseparowane od podstawowego interfejsu użytkownika.

## D-026 — Ręczne wymuszenia są czasowe

Ręczne przewietrzanie nie może pozostawiać systemu bezterminowo poza automatyką. UI pokazuje źródło sterowania i pozostały czas wymuszenia, a po jego zakończeniu przywraca tryb AUTO.

## D-027 — Modułowa rozbudowa pulpitu warsztatu

Interfejs zostanie przygotowany na kolejne strefy i moduły, takie jak energia, serwis filtrów, kompresor czy piec. Nie oznacza to łączenia kodu z ECU Platform lub CRT; projekty pozostają technicznie niezależne.

## D-028 — Obowiązkowa architektura warstwowa

Oprogramowanie jest rozwijane warstwowo: prezentacja, API, warstwa aplikacyjna, domena, abstrakcja sprzętu i sterowniki urządzeń. Pomijanie warstw przez bezpośrednie połączenie GUI ze sprzętem jest niedozwolone.

## D-029 — Rdzeń działa niezależnie od GUI

Automatyka wentylacji działa w osobnej usłudze `ventilation-core`. Restart, awaria lub aktualizacja interfejsu webowego, HMI albo lokalnego wyświetlacza nie może zatrzymywać sterowania.

## D-030 — Wiele interfejsów jako równorzędni klienci

Interfejs webowy, HMI, lokalny wyświetlacz, aplikacja mobilna i narzędzia serwisowe korzystają ze wspólnego API oraz tego samego modelu stanu. Żaden klient nie posiada własnej wersji logiki sterowania.

## D-031 — Jedno źródło prawdy

Autorytatywny stan systemu znajduje się w rdzeniu. Klient wysyła intencję, a nie zakłada wykonania polecenia. Stan jest aktualizowany dopiero po walidacji i wykonaniu operacji przez rdzeń.

## D-032 — Abstrakcja urządzeń

Czujniki, wentylatory, Tacho i rekuperatory są ukryte za interfejsami funkcjonalnymi. Zmiana modelu sprzętu lub producenta nie może wymagać przebudowy GUI ani podstawowej logiki strefy.

## D-033 — API domenowe zamiast rejestrów

Zwykłe interfejsy operują pojęciami takimi jak stan strefy, przewietrzanie, alarm i jakość powietrza. Surowe rejestry Modbus oraz wartości DAC są dostępne wyłącznie w kontrolowanym trybie serwisowym.

## D-034 — Testowalność bez sprzętu

Każde urządzenie musi mieć atrapę lub symulator. Logika domenowa, przypadki użycia i kontrakty API mają być testowane bez fizycznego sprzętu oraz bez uruchamiania GUI.

## D-035 — Rozszerzanie przez adaptery

Nowy czujnik, rekuperator lub element wykonawczy jest dodawany przez adapter implementujący istniejący interfejs. Nie dodajemy do GUI ani domeny rozgałęzień zależnych od konkretnego producenta, jeżeli urządzenie realizuje już obsługiwaną funkcję.

## D-036 — Rozstrzyganie konfliktów w rdzeniu

Rdzeń rozstrzyga priorytety pomiędzy automatyką, harmonogramem, alarmem i sterowaniem ręcznym. Każde wymuszenie ma źródło, czas rozpoczęcia i termin wygaśnięcia.
