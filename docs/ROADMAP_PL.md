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
- dopiero później RS-485, moduły SEN55 i integracja rekuperatora.

Rezultatem etapu ma być zweryfikowana warstwa dostępu do DFR0971, tabela rzeczywistych napięć oraz udokumentowane zachowanie wyjść po starcie i awarii.

## Etap 1 — Zamknięcie koncepcji sprzętowej

- potwierdzenie modelu wentylatora nawiewnego,
- dobór docelowego zasilacza DIN,
- pełna weryfikacja elektryczna DFR0971,
- dobór izolowanego interfejsu RS-485,
- decyzja o izolacji galwanicznej magistrali,
- sprawdzenie charakterystyki Tacho,
- potwierdzenie pinoutu złączy RJ45 Keystone używanych jako złącza nie-Ethernetowe.

## Etap 2 — Prototyp modułu czujnika

- przygotowanie modułu SEN55 + KAmod ESP32 POW RS485,
- lokalna komunikacja I²C z SEN55,
- odczyt wszystkich wymaganych wartości SEN55,
- implementacja Modbus RTU slave,
- test odporności na przerwanie komunikacji i restart,
- test dwóch węzłów na wspólnej magistrali.

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

## Najbliższy punkt kontrolny

Po uruchomieniu DFR0971 należy zapisać:

1. model i adres I²C wykrytego urządzenia,
2. schemat połączeń CM5 IO Board ↔ DFR0971,
3. zmierzone napięcia dla kilku wartości zadanych,
4. zachowanie obu kanałów po restarcie i awarii programu,
5. pierwszy sterownik urządzenia oraz osobne narzędzie testowe,
6. commit, push i krótki raport z etapu uruchomienia DAC.
