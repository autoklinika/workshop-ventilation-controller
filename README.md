# Workshop Ventilation Controller

Centralny sterownik jakości powietrza i wentylacji dla dwóch pomieszczeń warsztatowych.

Projekt jest całkowicie niezależny od ECU Platform i CAN Research Tool.

## Obsługiwane strefy

### Strefa 1 — mycie i wygrzewanie ECU

System steruje dwoma wentylatorami EC 0–10 V:

- nawiewem,
- wyciągiem.

Podstawowym zadaniem jest regularne przewietrzanie pomieszczenia oraz automatyczne zwiększanie wydajności wentylacji przy pogorszeniu jakości powietrza.

### Strefa 2 — pomieszczenie lutownicze

Pomieszczenie ma miejscowy odciąg oraz rekuperator Prodmax PRO MINI 300 H/V CLASSIC ze sterownikiem COMPIT AERO 4A2 i panelem NANO COLOR 2.

Preferowana integracja wykorzystuje oficjalny Modbus RTU panelu NANO COLOR 2. Raspberry Pi odczytuje stan centrali i może żądać czasowego wietrzenia, nie przejmując zabezpieczeń ani wewnętrznej automatyki rekuperatora.

## Interfejs użytkownika

Aplikacja ma być pulpitem jakości powietrza warsztatu, a nie technicznym panelem urządzeń.

Ekran główny pokaże uproszczony plan dwóch pomieszczeń, stan każdej strefy, aktualną reakcję systemu oraz ostatnią ważną decyzję automatyki. Codzienny interfejs będzie używał nazw użytkowych, takich jak `Mycie i wygrzewanie ECU`, `Pomieszczenie lutowania` i `Przewietrzanie`, zamiast nazw sterowników, rejestrów i magistral.

Techniczne parametry Modbus, DAC, Tacho i RS-485 pozostaną dostępne w oddzielnym trybie serwisowym.

## Architektura oprogramowania

Oprogramowanie będzie rozwijane warstwowo. Logika sterowania działa w niezależnym rdzeniu usługowym, a interfejs webowy, lokalny wyświetlacz, HMI i przyszłe aplikacje są wyłącznie klientami wspólnego API.

GUI nie komunikuje się bezpośrednio z Modbusem, DAC ani czujnikami. Restart lub aktualizacja interfejsu nie może zatrzymywać automatyki wentylacji.

## Architektura sprzętowa

- Raspberry Pi w rozdzielni DIN,
- zasilacz 5 V na szynę DIN,
- interfejsy RS-485,
- 2-kanałowy DAC 0–10 V dla strefy mycia,
- dwa wentylatory EC 0–10 V,
- niezależne moduły pomiarowe SEN55 + STM32,
- komunikacja RS-485 Modbus RTU,
- opcjonalny odczyt sygnałów Tacho wentylatorów,
- integracja rekuperatora Compit bez zastępowania jego fabrycznego sterownika.

## Dokumentacja

- [Architektura systemu](docs/SYSTEM_ARCHITECTURE_PL.md)
- [Architektura oprogramowania](docs/SOFTWARE_ARCHITECTURE_PL.md)
- [Lista elementów](docs/HARDWARE_COMPONENTS_PL.md)
- [Moduł czujnika](docs/SENSOR_NODE_PL.md)
- [Założenia Modbus](docs/MODBUS_MAP_PL.md)
- [Logika sterowania](docs/CONTROL_LOGIC_PL.md)
- [Integracja Prodmax / Compit AERO 4A2](docs/COMPIT_AERO4A2_INTEGRATION_PL.md)
- [Koncepcja interfejsu użytkownika](docs/USER_INTERFACE_CONCEPT_PL.md)
- [Rejestr decyzji](docs/DECISIONS_PL.md)
- [Plan realizacji](docs/ROADMAP_PL.md)

## Status

Etap koncepcyjny sprzętu, integracji, interfejsu użytkownika i architektury oprogramowania. Szczegóły algorytmów sterowania zostaną ustalone podczas implementacji i testów w rzeczywistych pomieszczeniach. Integracja AERO 4A2 wymaga jeszcze potwierdzenia wersji firmware panelu, przypisania zacisków Modbus oraz wykonania bezpiecznego testu odczytu.
