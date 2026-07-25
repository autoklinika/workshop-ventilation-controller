# Architektura systemu

## 1. Przeznaczenie

System zarządza jakością powietrza i wentylacją dwóch pomieszczeń warsztatowych:

- strefy mycia i wygrzewania sterowników ECU,
- sąsiedniego pomieszczenia lutowniczego.

Nie jest to system laboratoryjnego pomiaru stężeń substancji ani certyfikowany system bezpieczeństwa chemicznego. Jego zadaniem jest zapewnienie częstej wymiany powietrza i reagowanie na wyraźne pogorszenie jego jakości.

## 2. Główne bloki

```text
Rozdzielnia DIN
├── Zasilacz 5 V DIN
├── Raspberry Pi
├── Interfejsy RS-485
├── DAC 2 × 0–10 V
└── Listwy zaciskowe i zabezpieczenia

Strefa 1 — mycie i wygrzewanie
├── Wentylator nawiewny EC 0–10 V
├── Wentylator wyciągowy EC 0–10 V
└── Moduł pomiarowy
    ├── STM32
    ├── SEN55
    └── RS-485 Modbus RTU

Strefa 2 — lutowanie
├── Miejscowy odciąg lutowniczy
├── Moduł pomiarowy
│   ├── STM32
│   ├── SEN55
│   └── RS-485 Modbus RTU
└── Rekuperator Prodmax PRO MINI 300
    ├── sterownik COMPIT AERO 4A2
    ├── panel COMPIT NANO COLOR 2
    └── integracja Modbus RTU / C14
```

## 3. Przepływ sygnałów — strefa 1

1. SEN55 mierzy parametry powietrza.
2. STM32 odczytuje SEN55 lokalnie przez I²C.
3. STM32 udostępnia pomiary przez Modbus RTU po RS-485.
4. Raspberry Pi odczytuje pomiary.
5. Raspberry Pi wylicza zadane poziomy nawiewu i wyciągu.
6. DAC generuje dwa niezależne sygnały 0–10 V.
7. Wentylatory EC realizują zadane obroty.
8. Opcjonalnie Raspberry Pi sprawdza sygnały Tacho obu wentylatorów.

## 4. Przepływ sygnałów — strefa 2

1. Drugi moduł SEN55 + STM32 mierzy jakość powietrza w pomieszczeniu lutowniczym.
2. Raspberry Pi odczytuje pomiary przez Modbus RTU.
3. Raspberry Pi odczytuje stan rekuperatora przez udokumentowany interfejs Modbus panelu NANO COLOR 2.
4. W razie pogorszenia jakości powietrza Raspberry Pi może zażądać czasowego wietrzenia lub odpowiedniego biegu.
5. Panel NANO COLOR 2 przekazuje żądanie do AERO 4A2 przez protokół C14.
6. AERO 4A2 pozostaje odpowiedzialny za bezpieczną realizację pracy centrali.
7. Po ustąpieniu warunku Raspberry Pi wycofuje żądanie i pozostawia centralę w normalnym trybie pracy.

## 5. Zasady architektoniczne

- I²C pozostaje wyłącznie wewnątrz modułów czujników.
- Połączenia pomiędzy rozdzielnią a czujnikami realizuje RS-485.
- Nawiew i wyciąg strefy 1 mają osobne kanały 0–10 V.
- Wyciąg strefy 1 może pracować nieco mocniej od nawiewu, aby utrzymywać lekkie podciśnienie.
- Logika sterowania ma być konfigurowalna programowo bez zmian sprzętowych.
- System ma działać także przy braku odczytu Tacho, ale powinien wtedy zgłaszać ograniczoną diagnostykę.
- Raspberry Pi nie zastępuje AERO 4A2 i nie przejmuje funkcji bezpieczeństwa rekuperatora.
- Rozmrażanie, bypass, nagrzewnice, zabezpieczenia i alarmy pozostają po stronie Compit.
- Awaria Raspberry Pi nie może uniemożliwić ręcznej i fabrycznej pracy rekuperatora.
- Do integracji z AERO 4A2 preferowany jest udokumentowany Modbus RTU NANO COLOR 2; bezpośrednia analiza C14 pozostaje planem awaryjnym.

## 6. Podział odpowiedzialności

### STM32 w każdym węźle pomiarowym

- obsługa SEN55,
- filtrowanie i walidacja pomiarów,
- Modbus RTU slave,
- watchdog,
- diagnostyka czujnika i magistrali.

### Raspberry Pi

- Modbus RTU master dla węzłów pomiarowych,
- odczyt i sterowanie NANO COLOR 2 przez Modbus RTU,
- niezależna logika obu stref,
- harmonogramy,
- sterowanie DAC strefy 1,
- interfejs użytkownika,
- rejestr zdarzeń,
- opcjonalna diagnostyka Tacho,
- zachowanie historii pomiarów i stanu centrali.

### COMPIT AERO 4A2

- bezpośrednie sterowanie rekuperatorem,
- ochrona temperaturowa,
- rozmrażanie,
- bypass,
- obsługa nagrzewnic i wentylatorów,
- alarmy i funkcje serwisowe,
- realizacja żądań trybu przekazywanych przez NANO COLOR 2.
