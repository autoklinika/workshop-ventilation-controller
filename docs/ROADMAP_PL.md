# Plan realizacji

## Etap 0 — Platforma CM5 i uruchamianie peryferiów

Status: rozpoczęty.

- Raspberry Pi Compute Module 5 Wireless 4 GB / 32 GB eMMC uruchomiony,
- Raspberry Pi OS Lite 64-bit / Debian 13 zainstalowany na eMMC,
- repozytorium sklonowane na CM5,
- gałąź `agent/cm5-hardware-bringup-stage1` przygotowana,
- pierwszym uruchamianym peryferium jest DFRobot DFR0971 2 × 0–10 V,
- test DAC najpierw bez wentylatorów, z pomiarem multimetrem,
- następnie uruchomienie jednego i dwóch wentylatorów EC,
- dopiero później integracja RS-485 z CM5 oraz rekuperatorem.

Rezultatem etapu ma być zweryfikowana warstwa dostępu do DFR0971, tabela rzeczywistych napięć oraz udokumentowane zachowanie wyjść po starcie i awarii.

## Etap 1 — Zamknięcie koncepcji sprzętowej

- potwierdzenie modelu wentylatora nawiewnego,
- dobór docelowego zasilacza DIN,
- pełna weryfikacja elektryczna DFR0971,
- dobór izolowanego interfejsu RS-485 dla CM5,
- decyzja o izolacji galwanicznej magistrali,
- sprawdzenie charakterystyki Tacho,
- potwierdzenie pinoutu złączy RJ45 Keystone używanych jako złącza nie-Ethernetowe.

## Etap 2 — Prototyp modułu czujnika

Status: **w toku**.

### Stage 1 — SEN55 po I²C

Status: **zakończony i zwalidowany sprzętowo 2026-08-03**.

- przygotowanie KAmod ESP32 POW RS485 + SEN55,
- lokalna komunikacja I²C,
- odczyt wszystkich wymaganych wartości,
- walidacja CRC,
- obsługa utraty i automatycznego powrotu czujnika,
- zimny start i restart,
- przygotowanie OTA A/B oraz rollbacku.

### Stage 2A — Modbus RTU read-only

Status: **implementacja programowa rozpoczęta na `agent/kamod-modbus-stage2`; walidacja fizyczna oczekuje na konwerter USB–RS485**.

- oficjalny `espressif/esp-modbus` 2.1.2,
- UART2 i wbudowany transceiver RS-485 KAmod,
- adres `1`, `19200 bit/s`, `8N1`,
- funkcja `0x04`,
- wersjonowana mapa 19 rejestrów wejściowych,
- pomiary, maska dostępności i status,
- wiek pomiaru, liczniki błędów, uptime i wersje,
- narzędzie testowe dla komputera,
- brak rejestrów zapisywalnych.

Kryterium zamknięcia Stage 2A:

1. odczyt wszystkich 19 rejestrów przez konwerter USB–RS485,
2. zgodność danych z logiem USB,
3. poprawny status po odłączeniu i ponownym podłączeniu SEN55,
4. minimum 30 minut ciągłego odpytywania,
5. poprawne wyjątki dla nieobsługiwanych funkcji,
6. poprawny zimny start.

### Stage 2B — konfiguracja i dwa węzły

Rozpocząć dopiero po walidacji Stage 2A.

- trwała konfiguracja adresu Modbus,
- ewentualna konfiguracja prędkości,
- kontrolowana sekwencja serwisowa,
- test dwóch węzłów na wspólnej magistrali,
- terminacja, polaryzacja spoczynkowa i zachowanie przy awarii jednego węzła.

## Etap 3 — Sterowanie wentylatorami

- uruchomienie DAC 0–10 V,
- niezależna regulacja nawiewu i wyciągu,
- pomiar rzeczywistej zależności napięcie–wydajność,
- ustalenie minimalnego napięcia startu,
- próba odczytu Tacho,
- test bezpiecznego zachowania po restarcie CM5 i procesu sterującego.

Etap 3 rozpoczynamy częściowo już w Etapie 0, ponieważ sprawne uruchomienie wentylatorów ma obecnie najwyższy priorytet praktyczny.

## Etap 4 — Pierwsza wersja `ventilation-core`

- warstwa abstrakcji DFR0971 i wentylatorów,
- obsługa Modbus RTU master,
- odczyt i walidacja pomiarów,
- ręczne sterowanie dwoma kanałami 0–10 V przez kontrolowany interfejs serwisowy,
- podstawowe stany ECO, AUTO, PRZEWIETRZANIE i BOOST,
- konfiguracja czasu oraz mocy,
- lokalny dziennik zdarzeń,
- uruchamianie przez `systemd` i watchdog procesu.

Pełny rdzeń nie jest warunkiem laboratoryjnego testu DAC. Kod uruchomieniowy ma jednak od początku oddzielać sterownik urządzenia od narzędzia testowego, aby sprawdzony adapter można było później włączyć do `ventilation-core` bez przepisywania obsługi I²C.

## Etap 5 — Instalacja próbna

- montaż w rozdzielni,
- montaż czujników w pomieszczeniach,
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
- docelowe obudowy i uchwyty gotowych modułów,
- oznaczenia przewodów i złączy,
- instrukcja montażu i uruchomienia,
- kopia konfiguracji,
- raport z testów końcowych.

## Najbliższe punkty kontrolne

### Węzeł SEN55

1. zielone CI dla Stage 2A,
2. flash firmware 0.2.0-stage2,
3. odczyt Modbus przez komputer i konwerter USB–RS485,
4. raport z walidacji sprzętowej,
5. dopiero potem Stage 2B.

### DFR0971

Po uruchomieniu DFR0971 należy zapisać:

1. model i adres I²C wykrytego urządzenia,
2. schemat połączeń CM5 IO Board ↔ DFR0971,
3. zmierzone napięcia dla kilku wartości zadanych,
4. zachowanie obu kanałów po restarcie i awarii programu,
5. pierwszy sterownik urządzenia oraz osobne narzędzie testowe,
6. commit, push i krótki raport z etapu uruchomienia DAC.
