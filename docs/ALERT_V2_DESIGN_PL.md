# AlertV2 — architektura, macierz wag, reakcje i polityka HMI

**Projekt:** Workshop Ventilation Controller  
**Data ustaleń:** 2026-08-18  
**Status:** dokument projektowy + zaimplementowany loader/validator polityki Stage 1; bez integracji runtime core  
**Baza repo podczas utworzenia:** `main` `0f156cc6fe6e7d64df82a7a748108a93783c5fb7`  
**Plik polityki:** `config/alerts-v2.default.toml`

## 1. Cel AlertV2

AlertV2 ma być **globalnym systemem diagnostycznym całego Workshop Ventilation Controller**, a nie zestawem alarmów dla jednego urządzenia ani logiką należącą do GUI.

Źródłem prawdy pozostaje warstwa lokalna CM5. AlertV2 ma:

1. wykrywać zdarzenia w poszczególnych podsystemach,
2. korelować niezależne źródła diagnostyczne,
3. przypisywać alertom wagę i reakcję systemu,
4. utrzymywać trwały lifecycle alertów,
5. sterować sygnalizacją operatora, w tym kolorem paska RGB HMI,
6. nie uzależniać bezpieczeństwa ani podstawowej pracy wentylacji od GUI, Internetu, AI lub NAS.

AlertV2 obejmuje co najmniej:

- CM5 / `ventilation-core`,
- DAC / wyjścia 0–10 V,
- wentylatory EC i TACHO,
- SENSOR BUS / RS-485,
- SEN55,
- KAmod i niezależny service-plane `WVC-SERVICE`,
- CM5 Service Agent,
- AERO,
- Zigbee,
- pogodę,
- harmonogramy i automatykę,
- lokalną historię i bazy SQLite,
- synchronizację do AI Bridge / centralnego storage,
- AI advisory,
- lokalny watchdog HMI ↔ CM5.

## 2. Fundament już istniejący — Alert Stage 1

Obecny system nie jest wyrzucany. AlertV2 rozwija istniejący, zwalidowany fundament:

- `ventilation-core` jest właścicielem alertów produkcyjnych,
- aktywne epizody mają trwały lifecycle,
- istnieje `alert_id`, ACK i historia,
- lifecycle `ACTIVE -> ACKNOWLEDGED -> CLEARED` został zwalidowany sprzętowo,
- historia jest zapisywana lokalnie w SQLite,
- GUI jest klientem i nie implementuje własnych reguł diagnostycznych,
- obecne alerty obejmują DAC, SENSOR BUS/SEN55, AERO, TACHO i podstawowe Zigbee.

AlertV2 ma rozszerzyć ten mechanizm o **wagę, reakcję, zakres, wpływ na sterowanie, kolor HMI i korelację**.

## 3. Najważniejsza zasada: waga != reakcja sterująca

Waga określa ważność zdarzenia dla operatora i priorytet sygnalizacji. Nie może sama z siebie oznaczać `STOP`.

Przykład:

```text
FAN_NO_ROTATION_FEEDBACK
weight = 3 / ALARM
reaction = continue_degraded
affects_control = false
```

oraz:

```text
DAC_COMMUNICATION_LOST
weight = 4 / CRITICAL
reaction = safe_state
affects_control = true
```

Dzięki temu można mieć bardzo widoczny alarm wymagający szybkiej interwencji bez automatycznego zatrzymywania całej instalacji.

## 4. Twarde niezmienniki bezpieczeństwa

Poniższych zasad **nie wolno osłabić edycją TOML**. Muszą być wymuszane przez kod i validator konfiguracji.

### 4.1. TACHO nigdy nie zatrzymuje systemu samo z siebie

**Brak TACHO nie może zatrzymać wentylacji.**

Dotyczy to m.in.:

- `TACHO_MONITOR_UNAVAILABLE`,
- `TACHO_CONFIGURATION_INVALID`,
- utraty sygnału wejściowego TACHO jako samego problemu diagnostycznego.

Sterowanie 0–10 V ma nadal działać. System traci jedynie potwierdzenie rzeczywistych RPM.

Oddzielnym zdarzeniem jest sytuacja:

```text
realne zadanie wentylatora
+ zdrowy monitor TACHO
+ brak oczekiwanego potwierdzenia obrotów przez wymagany czas
= FAN_NO_ROTATION_FEEDBACK
```

To jest alarm wykonania, ale zgodnie z obecnym ustaleniem również **nie powoduje globalnego STOP**. Ewentualna przyszła kompensacja innym wentylatorem musi być osobną, zwalidowaną polityką sterowania.

Dokładne progi zadania, minimalnego RPM i czasu debounce nie zostały jeszcze zatwierdzone i muszą zostać dobrane na podstawie testów sprzętowych. Nie należy ich teraz wymyślać ani traktować jako część tej wersji kontraktu.

### 4.2. DAC zachowuje zwalidowaną politykę bezpieczeństwa

Konfiguracja AlertV2 nie może pozwolić na osłabienie krytycznej reakcji dla stanów, w których core nie ma pewności nad wyjściami 0–10 V. Przykładowo `DAC_COMMUNICATION_LOST` nie może zostać zmienione przez TOML na zwykłe `continue`.

W aktualnym validatorze Stage 1 polityki:

```text
DAC_STATE_UNCERTAIN
DAC_COMMUNICATION_LOST
DAC_OUTPUT_MISMATCH
```

są obowiązkowe i nie mogą zostać wyłączone ani usunięte. Validator wymusza też uzgodnione minimalne reakcje/wagi dla tych zdarzeń.

### 4.3. HMI nie jest wymagane do działania core

Utrata komunikacji HMI ↔ CM5:

- wymusza lokalnie czerwony stan HMI,
- wyświetla pełnoekranowy komunikat,
- blokuje sterowanie z GUI,
- **nie zatrzymuje `ventilation-core`**,
- core nadal działa autonomicznie.

Watchdog HMI musi pozostać lokalny, ponieważ przy utracie CM5 przeglądarka nie może polegać na nowym alercie otrzymanym z core.

### 4.4. AI, NAS, Internet i pogoda nie są ścieżką bezpieczeństwa

Awaria:

- AI Servera,
- Qwena / AI advisory,
- NAS,
- synchronizacji do AI Bridge,
- Internetu,
- providera pogody

nie może zatrzymać lokalnego `ventilation-core` ani bezpośrednio zmieniać wyjść sterujących.

### 4.5. Brak danych nie oznacza dobrego stanu

Brak wiarygodnego pomiaru SEN55/Zigbee lub innego wymaganego wejścia automatyki nie może być interpretowany jako `AIR QUALITY NORMAL`. Core musi przejść do deterministycznego, jawnego fallbacku odpowiedniego dla danego kontekstu.

## 5. Skala wag i kolory HMI

| Waga | Klasa | Pasek HMI | Znaczenie |
|---:|---|---|---|
| 0 | `NORMAL` | zielony | brak aktywnych problemów |
| 1 | `INFO` | niebieski | informacja serwisowa, brak wpływu na podstawową pracę |
| 2 | `WARNING` | żółty | degradacja diagnostyki lub funkcji pomocniczej |
| 3 | `ALARM` | pomarańczowy | rzeczywista awaria/degradacja wymagająca reakcji operatora |
| 4 | `CRITICAL` | czerwony | stan krytyczny, bezpieczeństwo lub brak pewności wykonania sterowania |

### 5.1. Reguła paska RGB

Przy połączeniu HMI z CM5 kolor paska określa **najwyższa aktywna waga**:

```text
red > orange > yellow > blue > green
```

`ACK` oznacza wyłącznie, że operator widział alert. **ACK nie obniża wagi i nie zmienia koloru paska.**

Kolor jest ponownie przeliczany dopiero, gdy alert zostanie `CLEARED` albo pojawi się alert o wyższej wadze.

### 5.2. Lokalny wyjątek HMI

`HMI_CM5_COMMUNICATION_LOST` ma lokalny priorytet nad stanem otrzymanym z core. Przy braku komunikacji HMI nie może wiedzieć, czy ostatnia lista alertów nadal jest aktualna, dlatego przechodzi na czerwony niezależnie od ostatniego znanego stanu.

## 6. Reakcje AlertV2

Pierwsza wersja polityki używa następujących nazw reakcji:

| `reaction` | Znaczenie |
|---|---|
| `continue` | brak wpływu na sterowanie; zapis/wyświetlenie informacji |
| `continue_degraded` | system pracuje dalej, ale funkcja/diagnostyka jest oznaczona jako zdegradowana |
| `fallback_local` | lokalny deterministyczny fallback dla danego zakresu; nie oznacza automatycznie globalnego STOP |
| `recover_safe_outputs` | próba odzyskania potwierdzonego bezpiecznego stanu wyjść |
| `safe_state` | zwalidowana reakcja bezpieczeństwa dla krytycznej ścieżki sterowania |
| `block_gui` | reakcja wyłącznie lokalna HMI: blokada interakcji GUI, bez wpływu na autonomiczny core |

Lista ma być walidowana jako enum. Dodanie nowego typu reakcji wymaga świadomej zmiany kodu i testów, nie tylko wpisu tekstowego w konfiguracji.

## 7. Deklaratywna polityka TOML

Domyślna macierz znajduje się w:

```text
config/alerts-v2.default.toml
```

Docelowy aktywny plik CM5:

```text
/etc/workshop-ventilation/alerts-v2.toml
```

### 7.1. Dlaczego TOML

TOML jest czytelny ręcznie, ma jednoznaczne typy i może być parsowany natywnie w Pythonie przez `tomllib`. Nie wymaga GUI ani osobnej bazy konfiguracyjnej.

### 7.2. Plik nie jest edytowany z HMI ani Web GUI

To jest celowa decyzja.

Zmiany polityki AlertV2 mają być wykonywane serwisowo:

- przez SSH,
- przez VS Code/Remote SSH,
- albo przez kontrolowaną zmianę w repo i deployment.

HMI/Web GUI mają jedynie prezentować stan i wykonywać dozwolone operacje operatorskie takie jak ACK. Nie udostępniamy w GUI edytora wag, reakcji ani progów bezpieczeństwa.

### 7.3. Pola pojedynczego alertu

Przykład:

```toml
[alerts.FAN_NO_ROTATION_FEEDBACK]
enabled = true
owner = "core"
category = "fan"
weight = 3
severity = "alarm"
reaction = "continue_degraded"
scope = "fan"
affects_control = false
hmi_color = "orange"
correlation_group = "fan_execution"
correlation_priority = 90
title = "Wentylator nie potwierdza pracy"
message = "Wentylator otrzymuje realne zadanie, monitor TACHO jest zdrowy, ale brak oczekiwanego potwierdzenia obrotów."
```

Semantyka:

- `enabled` — czy dana polityka jest aktywna,
- `owner` — warstwa wykrywająca (`core`, `system`, `hmi`),
- `category` — grupa funkcjonalna,
- `weight` — 0..4,
- `severity` — czytelna klasa odpowiadająca wadze,
- `reaction` — reakcja systemu,
- `scope` — zakres problemu (`global`, `fan`, `sensor_node`, `aero`, itd.),
- `affects_control` — czy zdarzenie jest wejściem do polityki sterującej/fallbacku,
- `hmi_color` — kolor wynikający z polityki,
- `correlation_group` — grupa zdarzeń analizowanych razem,
- `correlation_priority` — priorytet przy wyborze bardziej przyczynowego/skorelowanego alertu,
- `title`, `message` — tekst operatora.

### 7.4. Loader i validator — Stage 1

Zaimplementowano:

```text
src/ventilation_core/alert_policy.py
src/ventilation_core/alertctl.py
```

oraz komendę:

```bash
wvc-alertctl validate /ścieżka/do/alerts-v2.toml
```

Validator sprawdza strukturę TOML, mapowanie wag na severity/kolor, enum reakcji oraz twarde niezmienniki bezpieczeństwa. Obliczany jest również SHA-256 dokładnej zawartości polityki.

Na tym etapie `ventilation-core` **nie ładuje jeszcze tej polityki produkcyjnie**. CLI wyłącznie sprawdza plik.

Szczegółowy raport:

```text
docs/reports/ALERT_V2_POLICY_LOADER_STAGE1_IMPLEMENTATION_PL.md
```

## 8. Detektor i polityka są rozdzielone

AlertV2 nie może zmienić TOML w niekontrolowany język programowania automatyki.

### 8.1. Detector

Kod core/system/HMI stwierdza fakt, np.:

```text
FAN_NO_ROTATION_FEEDBACK = active
```

albo:

```text
KAMOD_HEARTBEAT_LOST = active
```

Detektor odpowiada za:

- odczyt stanu sprzętu,
- debounce/histerezę tam, gdzie są wymagane,
- sprawdzenie jakości danych,
- jednoznaczne i testowalne warunki wystąpienia.

### 8.2. Policy

TOML odpowiada za znaczenie operatorskie i zachowanie systemu:

```text
weight
severity
reaction
scope
affects_control
hmi_color
correlation metadata
texts
```

### 8.3. Dodawanie nowych alertów

Jeżeli odpowiedni detektor już istnieje, nową politykę lub zmianę wagi/koloru/tekstu można wykonać przez TOML.

Jeżeli wymagane jest zupełnie nowe rozpoznanie stanu, np. nowa korelacja kilku sygnałów sprzętowych, trzeba dodać testowalny detektor w kodzie. Sam wpis TOML nie może wykonywać dowolnych wyrażeń na `CoreState`.

Dodatkowe nastawy detektora mogą być przechowywane w kontrolowanej podsekcji:

```toml
[alerts.CODE.parameters]
```

ale użycie konkretnego parametru musi być jawnie obsłużone i zwalidowane przez odpowiedni detektor.

## 9. Korelacja — główna różnica AlertV2

AlertV2 ma preferować **jeden alert przyczynowy** zamiast zasypywać operatora kilkoma objawami tego samego problemu.

### 9.1. Przykład: service-plane padł, produkcja działa

```text
KAMOD_HEARTBEAT_LOST
+ SENSOR BUS / Modbus = ONLINE
+ SEN55 = usable
```

Wynik:

```text
kanał serwisowy zdegradowany
weight = 2
sterowanie produkcyjne bez zmian
```

### 9.2. Przykład: cały węzeł niedostępny

```text
SENSOR_NODE_UNAVAILABLE
+ KAMOD_HEARTBEAT_LOST
```

Wynik preferowany:

```text
KAMOD_NODE_UNAVAILABLE
weight = 3
scope = konkretny sensor_node
```

Zamiast trzech równorzędnych komunikatów operator otrzymuje jeden bardziej użyteczny opis przyczyny, a szczegóły źródłowe pozostają dostępne w diagnostyce/historii.

### 9.3. Przykład: problem lokalnego RS-485

```text
heartbeat KAmod = ONLINE
rs485_ready = false
produkcja Modbus = DEGRADED/OFFLINE
```

Preferowany wynik:

```text
KAMOD_RS485_NOT_READY
```

### 9.4. Korelacja nie może ukrywać danych diagnostycznych

Suppress/aggregation dotyczy prezentacji alertu przyczynowego. Surowe fakty źródłowe nadal mają być dostępne w diagnostyce i historii, aby można było przeprowadzić późniejszą analizę incydentu.

## 10. Zasada HMI i ACK

HMI ma prezentować stan wyliczony przez core/politykę, ale nie definiuje wag alertów produkcyjnych.

Priorytet koloru:

```text
BRAK KOMUNIKACJI HMI-CM5
>
weight 4 red
>
weight 3 orange
>
weight 2 yellow
>
weight 1 blue
>
normal green
```

ACK:

- nie kasuje aktywnego alertu,
- nie zmienia jego wagi,
- nie zmienia koloru paska,
- zapisuje tylko fakt potwierdzenia przez operatora.

## 11. Zasada bezpieczeństwa konfiguracji

Nie ufamy plikowi TOML bez walidacji.

Przed zastosowaniem polityki system musi sprawdzić co najmniej:

- `schema_version`,
- komplet wymaganych pól,
- zakres `weight = 0..4`,
- zgodność `weight -> severity -> hmi_color`,
- dozwolony enum `reaction`,
- unikalność kodów wynikającą z TOML,
- twarde ograniczenia DAC/TACHO/HMI,
- brak nieznanych pól poza jawnie dozwolonym `.parameters`.

Docelowy workflow serwisowy:

```bash
wvc-alertctl validate /etc/workshop-ventilation/alerts-v2.toml
sudo systemctl restart ventilation-core.service
```

Reload bez restartu może zostać dodany dopiero później, po osobnej walidacji atomowego przełączania polityki.

## 12. Kolejność dalszej implementacji

1. **DONE:** pełna domyślna macierz `alerts-v2.default.toml`.
2. **DONE:** loader TOML i validator kontraktu/safety invariants.
3. **DONE:** `wvc-alertctl validate` bez prawa do zmiany runtime.
4. **NEXT:** runtime policy manager tylko do odczytu, publikacja `policy_version` + SHA-256, bez zmiany reakcji sprzętowych.
5. Rozszerzenie rekordów/kontraktu AlertV2 o wagę, reaction, scope, color.
6. Korelacja istniejących źródeł: przede wszystkim service-plane + SENSOR BUS.
7. Operational TACHO: commanded fan without valid rotation feedback.
8. Pozostałe nowe detektory systemowe.
9. Integracja koloru RGB HMI z najwyższą aktywną wagą.
10. Dopiero na gotowym kontrakcie finalne GUI Alerty V2.

## 13. Stan bieżący

Plik `config/alerts-v2.default.toml` oraz dokumentacja są kontraktem projektowym. Loader i validator istnieją i są objęte testami repo, ale nie są jeszcze częścią produkcyjnej ścieżki `ventilation-core`.

Nie wykonywać merge do `main`, wdrożenia runtime ani zmiany polityki produkcyjnego sterowania bez osobnej walidacji i wyraźnej decyzji operatora.
