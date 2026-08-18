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

## Platforma sprzętowa

Sterownikiem centralnym jest Raspberry Pi Compute Module 5 Wireless z 4 GB RAM i 32 GB eMMC, zamontowany na oficjalnej CM5 IO Board. Raspberry Pi OS Lite 64-bit / Debian 13 działa bezpośrednio z eMMC.

Pierwszym uruchomionym peryferium jest DFRobot Gravity DFR0971 — dwukanałowy DAC I²C 0–10 V dla nawiewu i wyciągu. Oba kanały zostały zweryfikowane w zakresie 0–10 V, a pierwszy wentylator EC przeszedł pełny test wykonawczy przy 1 V, 2 V, 5 V, 8 V i 10 V.

Węzły pomiarowe wykorzystują SEN55 oraz gotowe moduły KAmod ESP32 POW RS485. Połączenie z centralą będzie realizowane przez Modbus RTU po RS-485.

## Interfejs użytkownika

Aplikacja ma być pulpitem jakości powietrza warsztatu, a nie technicznym panelem urządzeń.

Ekran główny pokaże uproszczony plan dwóch pomieszczeń, stan każdej strefy, aktualną reakcję systemu oraz ostatnią ważną decyzję automatyki. Codzienny interfejs będzie używał nazw użytkowych, takich jak `Mycie i wygrzewanie ECU`, `Pomieszczenie lutowania` i `Przewietrzanie`, zamiast nazw sterowników, rejestrów i magistral.

Techniczne parametry Modbus, DAC, Tacho i RS-485 pozostaną dostępne w oddzielnym trybie serwisowym.

## Architektura oprogramowania

Oprogramowanie jest rozwijane warstwowo. Logika sterowania działa w niezależnym rdzeniu usługowym, a interfejs webowy, lokalny wyświetlacz, HMI i przyszłe aplikacje są wyłącznie klientami wspólnego API.

Pierwsza wersja `ventilation-core` zawiera rozdzielone warstwy domeny, aplikacji, infrastruktury i runtime. Dostęp do I²C został odizolowany w osobnym procesie sprzętowym, nadzorowanym przez proces główny. Dzięki temu przyszłe GUI, Modbus, historia i API nie będą komunikować się bezpośrednio z DAC.

GUI nie komunikuje się bezpośrednio z Modbusem, DAC ani czujnikami. Restart lub aktualizacja interfejsu nie może zatrzymywać automatyki wentylacji.

MQTT jest przewidziany jako opcjonalny kanał telemetrii, zdarzeń i integracji z Home Assistant, Node-RED lub innymi systemami. Nie stanowi podstawowego kanału sterowania i jego awaria nie może wpływać na lokalne działanie automatyki.

## Architektura sprzętowa

- Raspberry Pi Compute Module 5 Wireless 4 GB / 32 GB eMMC,
- oficjalna CM5 IO Board,
- zasilanie docelowe 5 V na szynę DIN,
- interfejsy RS-485,
- DFRobot DFR0971 — 2-kanałowy DAC 0–10 V,
- dwa wentylatory EC 0–10 V,
- niezależne moduły pomiarowe SEN55 + KAmod ESP32 POW RS485,
- komunikacja RS-485 Modbus RTU,
- opcjonalny odczyt sygnałów Tacho wentylatorów,
- integracja rekuperatora Compit bez zastępowania jego fabrycznego sterownika,
- opcjonalny NVMe w przyszłości wyłącznie jako dodatkowy magazyn danych.

## Dokumentacja

- [Architektura systemu](docs/SYSTEM_ARCHITECTURE_PL.md)
- [Bazowa platforma sprzętowa CM5](docs/hardware/CM5_HARDWARE_BASELINE_PL.md)
- [Architektura oprogramowania](docs/SOFTWARE_ARCHITECTURE_PL.md)
- [Implementacja ventilation-core Stage 1](docs/reports/VENTILATION_CORE_STAGE1_IMPLEMENTATION_PL.md)
- [Integracja MQTT](docs/MQTT_INTEGRATION_PL.md)
- [Lista elementów](docs/HARDWARE_COMPONENTS_PL.md)
- [Moduł czujnika](docs/SENSOR_NODE_PL.md)
- [Założenia Modbus](docs/MODBUS_MAP_PL.md)
- [Logika sterowania](docs/CONTROL_LOGIC_PL.md)
- [Integracja Prodmax / Compit AERO 4A2](docs/COMPIT_AERO4A2_INTEGRATION_PL.md)
- [Koncepcja interfejsu użytkownika](docs/USER_INTERFACE_CONCEPT_PL.md)
- [Rejestr decyzji](docs/DECISIONS_PL.md)
- [Plan realizacji](docs/ROADMAP_PL.md)

## Status

Platforma CM5 działa z systemem na eMMC. DFR0971 oraz pierwszy wentylator EC zostały zweryfikowane sprzętowo. Powstała pierwsza warstwowa wersja `ventilation-core`, obejmująca domenowe reguły napięć, warstwę aplikacyjną, produkcyjny adapter GP8403, osobny proces sprzętowy, nadzór procesu, lokalny Unix socket i klienta `ventilationctl`.

Następnym krokiem jest walidacja rdzenia na rzeczywistym CM5, a następnie uruchomienie go jako usługi `systemd`.
