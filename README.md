# Workshop Ventilation Controller

Sterownik wentylacji pomieszczenia przeznaczonego do mycia i wygrzewania sterowników ECU.

Projekt jest całkowicie niezależny od ECU Platform i CAN Research Tool.

## Cel

System ma sterować dwoma wentylatorami EC 0–10 V:

- nawiewem,
- wyciągiem.

Podstawowym zadaniem jest regularne przewietrzanie pomieszczenia oraz automatyczne zwiększanie wydajności wentylacji przy pogorszeniu jakości powietrza.

## Architektura

- Raspberry Pi w rozdzielni DIN,
- zasilacz 5 V na szynę DIN,
- 2-kanałowy DAC 0–10 V,
- dwa wentylatory EC 0–10 V,
- zdalny moduł pomiarowy SEN55 + STM32,
- komunikacja RS-485 Modbus RTU,
- opcjonalny odczyt sygnałów Tacho wentylatorów.

## Dokumentacja

- [Architektura systemu](docs/SYSTEM_ARCHITECTURE_PL.md)
- [Lista elementów](docs/HARDWARE_COMPONENTS_PL.md)
- [Moduł czujnika](docs/SENSOR_NODE_PL.md)
- [Założenia Modbus](docs/MODBUS_MAP_PL.md)
- [Logika sterowania](docs/CONTROL_LOGIC_PL.md)
- [Rejestr decyzji](docs/DECISIONS_PL.md)
- [Plan realizacji](docs/ROADMAP_PL.md)

## Status

Etap koncepcyjny sprzętu. Szczegóły algorytmów sterowania zostaną ustalone podczas implementacji i testów w rzeczywistym pomieszczeniu.
