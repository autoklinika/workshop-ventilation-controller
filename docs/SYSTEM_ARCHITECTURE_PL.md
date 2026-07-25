# Architektura systemu

## 1. Przeznaczenie

System steruje wentylacją pomieszczenia używanego do mycia oraz wygrzewania sterowników ECU. Nie jest to system laboratoryjnego pomiaru stężeń substancji ani certyfikowany system bezpieczeństwa chemicznego. Jego zadaniem jest zapewnienie częstej wymiany powietrza i reagowanie na wyraźne pogorszenie jego jakości.

## 2. Główne bloki

```text
Rozdzielnia DIN
├── Zasilacz 5 V DIN
├── Raspberry Pi
├── Interfejs RS-485
├── DAC 2 × 0–10 V
└── Listwy zaciskowe i zabezpieczenia

Pomieszczenie
├── Wentylator nawiewny EC 0–10 V
├── Wentylator wyciągowy EC 0–10 V
└── Moduł pomiarowy
    ├── STM32
    ├── SEN55
    └── RS-485 Modbus RTU
```

## 3. Przepływ sygnałów

1. SEN55 mierzy parametry powietrza.
2. STM32 odczytuje SEN55 lokalnie przez I²C.
3. STM32 udostępnia pomiary przez Modbus RTU po RS-485.
4. Raspberry Pi odczytuje pomiary.
5. Raspberry Pi wylicza zadane poziomy nawiewu i wyciągu.
6. DAC generuje dwa niezależne sygnały 0–10 V.
7. Wentylatory EC realizują zadane obroty.
8. Opcjonalnie Raspberry Pi sprawdza sygnały Tacho obu wentylatorów.

## 4. Zasady architektoniczne

- I²C pozostaje wyłącznie wewnątrz modułu czujnika.
- Połączenie pomiędzy rozdzielnią a czujnikiem realizuje RS-485.
- Nawiew i wyciąg mają osobne kanały 0–10 V.
- Wyciąg może pracować nieco mocniej od nawiewu, aby utrzymywać lekkie podciśnienie.
- Logika sterowania ma być konfigurowalna programowo bez zmian sprzętowych.
- System ma działać także przy braku odczytu Tacho, ale powinien wtedy zgłaszać ograniczoną diagnostykę.

## 5. Podział odpowiedzialności

### STM32

- obsługa SEN55,
- filtrowanie i walidacja pomiarów,
- Modbus RTU slave,
- watchdog,
- diagnostyka czujnika i magistrali.

### Raspberry Pi

- Modbus RTU master,
- logika wentylacji,
- harmonogramy,
- sterowanie DAC,
- interfejs użytkownika,
- rejestr zdarzeń,
- opcjonalna diagnostyka Tacho.
