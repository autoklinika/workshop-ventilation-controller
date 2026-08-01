# Architektura systemu

## 1. Przeznaczenie

System zarządza jakością powietrza i wentylacją dwóch pomieszczeń warsztatowych:

- strefy mycia i wygrzewania sterowników ECU,
- sąsiedniego pomieszczenia lutowniczego.

Nie jest to system laboratoryjnego pomiaru stężeń substancji ani certyfikowany system bezpieczeństwa chemicznego. Jego zadaniem jest zapewnienie częstej wymiany powietrza i reagowanie na wyraźne pogorszenie jego jakości.

## 2. Główne bloki

```text
Rozdzielnia DIN / sterownik centralny
├── Raspberry Pi Compute Module 5 Wireless
│   ├── 4 GB RAM
│   ├── 32 GB eMMC
│   └── oficjalna CM5 IO Board
├── zasilanie 5 V
├── izolowany interfejs RS-485
├── DFRobot DFR0971 — DAC 2 × 0–10 V po I²C
└── listwy zaciskowe i zabezpieczenia

Strefa 1 — mycie i wygrzewanie
├── wentylator nawiewny EC 0–10 V
├── wentylator wyciągowy EC 0–10 V
└── moduł pomiarowy
    ├── KAmod ESP32 POW RS485
    ├── SEN55
    └── RS-485 Modbus RTU

Strefa 2 — lutowanie
├── miejscowy odciąg lutowniczy
├── moduł pomiarowy
│   ├── KAmod ESP32 POW RS485
│   ├── SEN55
│   └── RS-485 Modbus RTU
└── rekuperator Prodmax PRO MINI 300
    ├── sterownik COMPIT AERO 4A2
    ├── panel COMPIT NANO COLOR 2
    └── integracja Modbus RTU / C14

Opcjonalna warstwa analityczna
└── Minisforum
    ├── Ollama / lokalny model AI
    ├── raporty i analiza historii
    ├── wykrywanie anomalii
    └── rekomendacje bez bezpośredniego sterowania
```

## 3. Platforma centralna

Sterownikiem głównym jest Raspberry Pi Compute Module 5 Wireless z 4 GB RAM i 32 GB eMMC, zamontowany na oficjalnej CM5 IO Board.

- Raspberry Pi OS Lite 64-bit działa bezpośrednio z eMMC.
- System operacyjny i krytyczna automatyka nie zależą od dodatkowego dysku.
- Opcjonalny NVMe może później przechowywać rozszerzoną historię i archiwa.
- Ethernet będzie podstawowym łączem sieciowym, a Wi-Fi kanałem serwisowym lub zapasowym.
- Brak sieci nie może zatrzymywać lokalnego sterowania.

## 4. Przepływ sygnałów — strefa 1

1. SEN55 mierzy parametry powietrza.
2. KAmod ESP32 odczytuje SEN55 lokalnie przez I²C.
3. KAmod udostępnia pomiary przez Modbus RTU po RS-485.
4. CM5 odczytuje i waliduje pomiary.
5. CM5 wylicza zadane poziomy nawiewu i wyciągu.
6. DFR0971 generuje dwa niezależne sygnały 0–10 V.
7. Wentylatory EC realizują zadane poziomy pracy.
8. Opcjonalnie CM5 sprawdza sygnały Tacho obu wentylatorów przez zabezpieczone wejścia.

## 5. Przepływ sygnałów — strefa 2

1. Drugi moduł SEN55 + KAmod ESP32 mierzy jakość powietrza w pomieszczeniu lutowniczym.
2. CM5 odczytuje pomiary przez Modbus RTU.
3. CM5 odczytuje stan rekuperatora przez udokumentowany interfejs Modbus panelu NANO COLOR 2.
4. W razie pogorszenia jakości powietrza CM5 może zażądać czasowego wietrzenia lub odpowiedniego biegu.
5. Panel NANO COLOR 2 przekazuje żądanie do AERO 4A2 przez protokół C14.
6. AERO 4A2 pozostaje odpowiedzialny za bezpieczną realizację pracy centrali.
7. Po ustąpieniu warunku CM5 wycofuje żądanie i pozostawia centralę w normalnym trybie pracy.

## 6. Zasady architektoniczne

- I²C do SEN55 pozostaje wyłącznie wewnątrz modułów czujników.
- Lokalna magistrala I²C CM5 służy między innymi do obsługi DFR0971.
- Połączenia pomiędzy rozdzielnią a czujnikami realizuje RS-485.
- Nawiew i wyciąg strefy 1 mają osobne kanały 0–10 V.
- Wyciąg strefy 1 może pracować nieco mocniej od nawiewu, aby utrzymywać lekkie podciśnienie.
- Logika sterowania ma być konfigurowalna programowo bez zmian sprzętowych.
- System ma działać także przy braku odczytu Tacho, ale powinien wtedy zgłaszać ograniczoną diagnostykę.
- CM5 nie zastępuje AERO 4A2 i nie przejmuje funkcji bezpieczeństwa rekuperatora.
- Rozmrażanie, bypass, nagrzewnice, zabezpieczenia i alarmy pozostają po stronie Compit.
- Awaria CM5 nie może uniemożliwić ręcznej i fabrycznej pracy rekuperatora.
- Do integracji z AERO 4A2 preferowany jest udokumentowany Modbus RTU NANO COLOR 2; bezpośrednia analiza C14 pozostaje planem awaryjnym.
- Wyjścia 0–10 V muszą mieć jawnie określony stan bezpieczny po starcie, restarcie procesu i awarii komunikacji.
- Lokalna AI jest wyłącznie opcjonalną warstwą analityczną i nie uczestniczy w deterministycznym sterowaniu.
- Wyłączenie Minisforum, Ollamy, modelu AI lub sieci nie może wpływać na automatykę, alarmy ani podstawową historię systemu.
- AI nie otrzymuje bezpośredniego dostępu do Modbus, RS-485, DAC ani funkcji kasowania alarmów.
- Rekomendacje AI nie są stosowane automatycznie; każda przyszła zmiana musi przejść przez warstwę aplikacyjną i walidację `ventilation-core`.

## 7. Podział odpowiedzialności

### KAmod ESP32 POW RS485 w każdym węźle pomiarowym

- lokalna obsługa SEN55,
- walidacja i oznaczanie świeżości pomiarów,
- Modbus RTU slave,
- watchdog,
- diagnostyka czujnika i magistrali.

### Raspberry Pi Compute Module 5

- Modbus RTU master dla węzłów pomiarowych,
- odczyt i sterowanie NANO COLOR 2 przez Modbus RTU,
- niezależna logika obu stref,
- harmonogramy,
- sterowanie DFR0971 dla strefy 1,
- interfejs użytkownika,
- rejestr zdarzeń,
- opcjonalna diagnostyka Tacho,
- zachowanie historii pomiarów i stanu centrali,
- autorytatywny stan systemu i pełna automatyka niezależna od AI.

### COMPIT AERO 4A2

- bezpośrednie sterowanie rekuperatorem,
- ochrona temperaturowa,
- rozmrażanie,
- bypass,
- obsługa nagrzewnic i wentylatorów,
- alarmy i funkcje serwisowe,
- realizacja żądań trybu przekazywanych przez NANO COLOR 2.

### Minisforum / Ollama — komponent opcjonalny

- analiza bieżących i historycznych danych,
- raporty i odpowiedzi w języku naturalnym,
- wykrywanie anomalii wymagających kontekstu historycznego,
- ocena skuteczności wentylacji,
- proponowanie zmian ustawień bez ich samodzielnego stosowania,
- praca na ustrukturyzowanym profilu pomieszczeń i instalacji,
- brak bezpośrednich uprawnień wykonawczych.

Szczegółowe zasady opisuje dokument [Integracja lokalnej AI](AI_INTEGRATION_PL.md).

## 8. Granica bezpieczeństwa warstwy AI

AI komunikuje się z systemem przez kontrolowany `AI Gateway`, MQTT i API przeznaczone do odczytu danych. W pierwszym etapie nie ma żadnego kanału zapisu konfiguracji ani sterowania urządzeniami.

Klasyczne algorytmy na CM5 odpowiadają za progi, histerezy, alarmy, watchdogi i reakcje natychmiastowe. AI może wykrywać wolniejsze trendy, porównywać podobne zdarzenia i zgłaszać diagnostyczne anomalie w czasie zbliżonym do rzeczywistego.

Model językowy nie powinien wykonywać podstawowych obliczeń na surowych próbkach. Statystyki, czas trwania zdarzeń, trendy, korelacje i porównania z bazą odniesienia są obliczane deterministycznie, a AI interpretuje przygotowane wyniki w kontekście profilu instalacji.

Usunięcie całej warstwy AI z systemu nie może wymagać zmian w `ventilation-core` ani powodować utraty podstawowej funkcjonalności wentylacji.

## 9. Kolejność uruchomienia sprzętu i usług

Pierwszy etap laboratoryjny rozpoczyna się od DFR0971, ponieważ uruchomienie i pomiar sterowania 0–10 V ma wyższy priorytet niż integracja czujników i rekuperatora.

1. wykrycie DFR0971 na I²C,
2. test wyjść bez wentylatorów,
3. walidacja napięć multimetrem,
4. test zachowania po restarcie,
5. uruchomienie jednego, a następnie dwóch wentylatorów,
6. RS-485, węzły SEN55 i Compit,
7. stabilny zapis historii i zdarzeń,
8. dopiero później uruchomienie Ollamy na Minisforum i integracja AI w trybie tylko do odczytu.
