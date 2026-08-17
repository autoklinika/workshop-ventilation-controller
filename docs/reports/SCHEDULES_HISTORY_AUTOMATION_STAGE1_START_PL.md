# Harmonogramy, historia i wstępna automatyzacja — Stage 1

## Status

Dokument startowy po zakończeniu i walidacji Alert System Stage 1 oraz Web GUI V2.

Punkt bazowy: aktualny `main` po produkcyjnym wdrożeniu Alert Stage 1 i Web GUI V2.

Ten etap nie zmienia nadrzędnej zasady architektury: **`ventilation-core` jest jedynym właścicielem logiki sterowania i bezpieczeństwa; GUI jest klientem.** AI pozostaje warstwą doradczą i nie może bezpośrednio sterować wentylacją.

## 1. Cel etapu

Etap ma dostarczyć trzy współpracujące funkcje:

1. trwałą historię pomiarów i decyzji sterownika,
2. lokalne harmonogramy pracy niezależne od GUI, sieci i AI,
3. deterministyczną automatykę uruchomioną najpierw w trybie `SHADOW`, bez fizycznej zmiany wyjść.

Aktywne automatyczne sterowanie będzie osobnym krokiem po walidacji danych z trybu SHADOW.

## 2. Zasady bezpieczeństwa

Priorytet pozostaje zgodny z `docs/ZALOZENIA_AUTOMATYKI_PL.md`:

`BEZPIECZEŃSTWO > JAKOŚĆ POWIETRZA > TEMPERATURA / ENERGOOSZCZĘDNOŚĆ`.

Harmonogram nigdy nie może wyłączyć wentylacji wymaganej przez warunek bezpieczeństwa albo jakość powietrza.

Automatyka nie zależy od AI, Internetu ani Web GUI. Awaria historii, synchronizacji do AI/NAS albo GUI nie może zatrzymać `ventilation-core` ani zmienić jego bezpiecznego zachowania.

Przed aktywnym AUTO należy dodać regułę diagnostyczną: **zadanie wentylatora > próg + brak oczekiwanych impulsów TACHO przez określony czas = alert core**. Brak impulsów przy STOP nadal nie jest alarmem.

## 3. Historia — architektura

W repo istnieje już lokalny `TelemetryStore` oparty o SQLite/WAL i agent telemetryczny zapisujący pełny snapshot core. Obecnie domyślne próbkowanie wynosi 5 s, a lokalna retencja zsynchronizowanych rekordów 30 dni.

Stage 1 rozszerza ten mechanizm zamiast tworzyć drugą konkurencyjną historię.

### 3.1. Wymagania

- lokalny zapis na CM5 ma działać również wtedy, gdy AI Bridge/NAS jest niedostępny,
- synchronizacja zewnętrzna nie może blokować lokalnego zapisu,
- historia alertów pozostaje w osobnym `alerts.sqlite3`,
- historia pomiarów i decyzji pozostaje w `telemetry.sqlite3`,
- zapis ma być odporny na restart i awarię sieci,
- Web GUI otrzyma wyłącznie odczyt historii przez wąski API, bez bezpośredniego dostępu przeglądarki do SQLite.

### 3.2. Retencja i agregacja

Nie będziemy utrzymywać przez wiele miesięcy pełnych snapshotów co 5 s na eMMC. Docelowy układ lokalny:

- surowe próbki 5 s — krótka retencja diagnostyczna,
- agregaty 1 min — historia operacyjna,
- agregaty 15 min / 1 h — historia długoterminowa i baza do analizy AI,
- pełna historia długoterminowa docelowo na NAS/serwerze, nie jako obowiązek eMMC CM5.

Dokładne okresy retencji zostaną dobrane po pomiarze rzeczywistego rozmiaru pojedynczego snapshotu i tempa przyrostu bazy.

### 3.3. Co zapisujemy

Historia ma obejmować co najmniej:

- wszystkie dostępne pomiary SEN55 dla obu stref,
- diagnostykę SEN55,
- temperatury wewnętrzne i później zewnętrzne/nawiewu,
- zadania wentylatorów i rzeczywiste RPM TACHO,
- stan AERO,
- aktywne alerty / identyfikatory aktywnych epizodów jako część snapshotu operacyjnego,
- tryb pracy core,
- stan harmonogramu,
- wynik automatyki: `air_request_pct`, `temperature_limit_pct`, `safety_override`, `final_supply_pct`, `final_extract_pct`, `control_reason`,
- w SHADOW: wartości `proposed_*` oddzielone od faktycznych wyjść.

### 3.4. Równoległy kontrakt z AI Serverem

Historia budowana w tym etapie na CM5 jest równocześnie wejściem dla istniejącej warstwy analitycznej w repozytorium `autoklinika/AI-server`. Nie projektujemy osobnego formatu dla GUI i osobnego formatu dla AI. Źródłem prawdy pozostaje autorytatywny `CoreState`, a transport i centralne archiwum rozwijają jego wersjonowany kontrakt.

Obowiązują równolegle założenia zapisane w:

- `Workshop Ventilation Controller: docs/AI_INTEGRATION_PL.md`,
- `AI-server: docs/ADR-002_AI_ANALYSIS_STRATEGY_PL.md`,
- `AI-server: docs/ADR-004_TELEMETRY_STORAGE_AND_RETENTION_PL.md`,
- `AI-server: docs/ADR-005_VENTILATION_AI_ANALYSIS_EXECUTION_PL.md`,
- `AI-server: docs/VENTILATION_TELEMETRY_API_V1_PL.md`,
- `AI-server: docs/VENTILATION_TELEMETRY_DATA_MODEL_V1_PL.md`.

Zasady integracji:

- CM5 najpierw zapisuje snapshot lokalnie, a dopiero potem synchronizuje go do AI Bridge,
- awaria AI Servera, PostgreSQL, Ollamy, Qwena, NAS lub sieci nie może zatrzymać lokalnego capture ani sterowania,
- `source_id`, `sample_id`, `sequence`, `captured_at`, `batch_id` i `schema_version` zachowują stabilną semantykę potrzebną do idempotentnego backfillu i audytu,
- AI Bridge zapisuje pełną surową telemetrię w centralnym archiwum; pierwszy rok ma zachować co najmniej 12 miesięcy szczegółowej historii do zbudowania baseline'u sezonowego,
- analiza na AI Serverze korzysta z zamkniętych, wyrównanych okien 15-minutowych; przy próbkowaniu około 5 s pełne okno ma około 180 snapshotów, a aktualny gate analizy wynosi 120 próbek,
- Python na AI Serverze wykonuje deterministyczne obliczenia matematyczne i przygotowuje materiał wejściowy; Qwen interpretuje przygotowane dane, ale nie jest częścią ścieżki ingest/ACK,
- wyniki SHADOW, harmonogram, faktyczne setpointy, TACHO/RPM, diagnostyka SEN55 i alerty muszą trafiać do telemetrii tak, aby AI mogło później porównywać decyzję regulatora z fizyczną odpowiedzią instalacji,
- wynik AI pozostaje advisory/experimental i nigdy nie staje się automatycznym wejściem do regulatora CM5.

### 3.5. Abstrakcja magazynu centralnego

CM5 nie może być sprzężony z fizycznym miejscem długoterminowego magazynu. Z punktu widzenia CM5 istnieje jeden logiczny endpoint synchronizacji `AI Bridge / Data Gateway`.

Aktualnie centralne RAW archive znajduje się na AI Serverze. Docelowo dane mają lądować na NAS. Zmiana ta ma następować po stronie backendu magazynu, bez zmiany kontraktu telemetrycznego CM5, kolejki, ACK, `sample_id`, `sequence` ani mechanizmu backfillu.

Docelowy model:

```text
CM5
├── lokalne telemetry.sqlite3
└── synchronizacja
       ↓
   AI Bridge / Data Gateway
       ↓
   Storage backend
       ├── teraz: AI Server / PostgreSQL
       └── docelowo: NAS
```

Konfiguracja storage backendu nie jest parametrem automatyki wentylacji. Ma należeć do warstwy infrastrukturalnej i może być później obsługiwana z GUI przez kontrolowane API. GUI nie otrzymuje haseł do DB/NAS i nie zapisuje bezpośrednio do magazynu.

Przełączenie backendu powinno wymagać testu łączności oraz zapisu/odczytu. Nieudane przełączenie pozostawia poprzedni backend aktywny. Architektura powinna umożliwić tymczasowy `dual-write` AI Server + NAS na czas migracji i walidacji kompletności danych.

W praktyce rozwój historii w tym PR oraz rozwój analizy w `AI-server` są jednym strumieniem danych rozwijanym równolegle, ale z twardym rozdzieleniem odpowiedzialności:

`CM5 zapisuje i steruje -> AI Bridge przechowuje -> Python liczy -> Qwen interpretuje -> operator otrzymuje rekomendację`.

## 4. Harmonogramy

Harmonogram jest częścią core, nie GUI.

### 4.1. Model Stage 1

Dla każdej strefy przechowujemy tygodniowe okna pracy w lokalnym czasie `Europe/Warsaw`.

Minimalny model:

- dzień tygodnia,
- godzina początku,
- godzina końca,
- stan oczekiwanej obecności / tryb bazowy,
- aktywność reguły.

Harmonogram musi działać po restarcie CM5 i bez połączenia sieciowego.

### 4.2. Semantyka

Harmonogram nie wydaje bezpośrednio polecenia napięcia 0–10 V. Dostarcza regulatorowi kontekst, np. `OCCUPIED_EXPECTED` albo `UNOCCUPIED_EXPECTED`.

Poza godzinami pracy można obniżyć bazową wymianę tylko wtedy, gdy jakość powietrza i bezpieczeństwo na to pozwalają.

### 4.3. Ręczne nadpisanie

Przyszły/manualny override musi mieć jawny czas wygaśnięcia. GUI może poprosić core o override, ale core przechowuje jego stan i czas końca. Restart GUI nie może zmieniać trybu sterownika.

Wygaśnięcie override powoduje automatyczny powrót do bieżącego harmonogramu/AUTO.

## 5. Automatyka Stage 1 — SHADOW

Pierwsza wersja regulatora pracuje jako deterministyczny silnik reguł w `ventilation-core`.

W trybie SHADOW:

- odczytuje te same dane, które później będą sterować urządzeniami,
- oblicza żądaną reakcję,
- zapisuje wynik do stanu/telemetrii,
- **nie zmienia fizycznych wyjść DAC ani AERO**.

### 5.1. Jawny pipeline decyzji

Regulator ma wyznaczać osobno:

1. `air_request` — żądanie z PM/VOC/NOx,
2. `schedule_baseline` — minimum wynikające z harmonogramu,
3. `temperature_limit` — ograniczenie cieplne, kiedy jakość powietrza na to pozwala,
4. `safety_override` — nadrzędne wymuszenie,
5. wynik końcowy i `control_reason`.

Nie implementujemy jednej nieprzejrzystej formuły sumującej korekty.

### 5.2. Progi startowe

Punktem startowym są progi procesowe z `docs/ZALOZENIA_AUTOMATYKI_PL.md`. Są to nastawy do strojenia, a nie deklaracja BHP.

Należy zastosować filtr czasu/debounce, histerezę przy schodzeniu z BOOST/MAX, kontrolę świeżości i poprawności danych oraz rozróżnienie awarii sensora od rzeczywiście dobrego powietrza.

Brak wiarygodnego pomiaru nie może być interpretowany jako `AIR QUALITY NORMAL`.

## 6. Kolejność implementacji

### Krok A — historia

1. uniezależnić lokalny capture od dostępności AI Bridge,
2. dodać zapytania historii i agregaty,
3. utrzymać kompatybilność z `Ventilation Telemetry API v1` i centralnym RAW archive,
4. dodać warstwę konfiguracji logicznego storage backendu bez sprzęgania CM5 z NAS,
5. dodać API read-only historii dla Web GUI,
6. dodać widok historii/trendów bez wpływu na core control path.

### Krok B — harmonogramy

1. trwały store harmonogramów po stronie core,
2. core API: odczyt i kontrolowana aktualizacja,
3. obliczanie bieżącego `schedule_state`,
4. klient GUI do edycji harmonogramu.

### Krok C — SHADOW automation

1. jawny model wejść i wyniku decyzji,
2. reguły PM/VOC/NOx + schedule baseline,
3. obsługa temperatury w zakresie możliwym na dostępnych czujnikach,
4. zapis każdej decyzji do telemetrii,
5. GUI pokazuje faktyczne wyjście vs propozycję automatyki.

### Krok D — diagnostyka wykonania

Dodać core alert dla wentylatora, który otrzymuje realne zadanie, ale nie potwierdza pracy przez TACHO. Ten krok jest wymagany przed aktywnym AUTO.

### Krok E — aktywne AUTO

Dopiero po walidacji SHADOW na CM5 i wyraźnej decyzji operatora. Włączenie AUTO nie może być skutkiem aktualizacji OTA ani restartu GUI.

## 7. Kryteria zakończenia Stage 1

Stage 1 uznajemy za zakończony, gdy:

- lokalna historia działa przy odłączonym AI/NAS,
- historia nie pogarsza czasu odpowiedzi core,
- centralna synchronizacja działa przez stabilny kontrakt niezależny od fizycznego storage backendu,
- przełączenie docelowego magazynu nie wymaga zmiany logiki sterowania CM5,
- harmonogram przetrwa restart i poprawnie obsłuży zmianę dnia/czasu,
- GUI nie zawiera własnej logiki automatyki,
- SHADOW generuje jawne, odtwarzalne decyzje bez sterowania sprzętem,
- wyniki SHADOW są widoczne w historii i dostępne dla analizy AI,
- awaria warstwy historii/harmonogramu/synchronizacji nie powoduje niekontrolowanego sterowania,
- testy jednostkowe i walidacja CM5 przechodzą bez regresji Alert Stage 1.

## 8. Poza zakresem tego kroku

- autonomiczne decyzje AI,
- aktywne sterowanie na podstawie prognozy pogody,
- automatyczne czyszczenie statusu sticky SEN55,
- formalna certyfikacja BHP,
- złożone kalendarze świąt/wyjątków,
- uczenie regulatora bez nadzoru.
