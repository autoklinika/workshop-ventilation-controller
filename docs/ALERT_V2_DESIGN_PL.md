# AlertV2 — architektura, macierz wag, reakcje i polityka HMI

**Projekt:** Workshop Ventilation Controller  
**Data ustaleń:** 2026-08-18  
**Status:** dokument projektowy / przed implementacją Core AlertV2  
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

Preferowany alert:

```text
KAMOD_RS485_NOT_READY
```

### 9.4. Przykład: wentylator

```text
realne zadanie 0-10 V > zwalidowany próg
+ monitor TACHO zdrowy
+ brak oczekiwanych RPM przez zwalidowany debounce
```

Wynik:

```text
FAN_NO_ROTATION_FEEDBACK
weight = 3
reaction = continue_degraded
GLOBAL STOP = NIE
```

## 10. Macierz AlertV2 v0.1

Pełne wartości runtime znajdują się w `config/alerts-v2.default.toml`. Poniższa tabela służy jako skrócona mapa projektowa.

| Obszar | Alert | Waga | Kolor | Reakcja | Sterowanie |
|---|---|---:|---|---|---|
| HMI | `HMI_CM5_COMMUNICATION_LOST` | 4 | czerwony | `block_gui` | nie zatrzymuje core |
| Core | `CORE_PROCESS_RESTARTED` | 3 | pomarańczowy | `continue_degraded` | nie |
| DAC | `DAC_STATE_UNCERTAIN` | 3 | pomarańczowy | `recover_safe_outputs` | tak |
| DAC | `DAC_COMMUNICATION_LOST` | 4 | czerwony | `safe_state` | tak |
| DAC | `DAC_OUTPUT_MISMATCH` | 4 | czerwony | `safe_state` | tak |
| TACHO | `TACHO_MONITOR_UNAVAILABLE` | 2 | żółty | `continue_degraded` | **nie** |
| TACHO | `TACHO_CONFIGURATION_INVALID` | 2 | żółty | `continue_degraded` | **nie** |
| Fan | `FAN_NO_ROTATION_FEEDBACK` | 3 | pomarańczowy | `continue_degraded` | **nie zatrzymuje** |
| Fan | `FAN_RPM_OUT_OF_RANGE` | 3 | pomarańczowy | `continue_degraded` | nie domyślnie |
| SENSOR BUS | `SENSOR_BUS_UNAVAILABLE` | 3 | pomarańczowy | `fallback_local` | tak |
| SEN55 | `SENSOR_NODE_UNAVAILABLE` | 3 | pomarańczowy | `fallback_local` | tak lokalnie |
| SEN55 | `SENSOR_DATA_INVALID` | 3 | pomarańczowy | `fallback_local` | tak lokalnie |
| SEN55 | `SEN55_DIAGNOSTICS_UNAVAILABLE` | 2 | żółty | `continue_degraded` | nie |
| SEN55 | `SEN55_FAN_SPEED_WARNING` | 2 | żółty | `continue_degraded` | nie |
| SEN55 | `SEN55_GAS_SENSOR_ERROR` | 3 | pomarańczowy | `fallback_local` | dla VOC/NOx |
| SEN55 | `SEN55_RHT_ERROR` | 3 | pomarańczowy | `fallback_local` | dla RH/T |
| SEN55 | `SEN55_LASER_ERROR` | 3 | pomarańczowy | `fallback_local` | dla PM |
| SEN55 | `SEN55_FAN_ERROR` | 3 | pomarańczowy | `fallback_local` | tak lokalnie |
| KAmod | `KAMOD_HEARTBEAT_SINGLE_GAP` | 1 | niebieski | `continue` | nie |
| KAmod | `KAMOD_HEARTBEAT_DEGRADED` | 2 | żółty | `continue_degraded` | nie |
| KAmod | `KAMOD_HEARTBEAT_LOST` | 2 | żółty | `continue_degraded` | nie |
| KAmod | `KAMOD_UNEXPECTED_RESTART` | 2 | żółty | `continue_degraded` | nie |
| KAmod | `KAMOD_RS485_NOT_READY` | 3 | pomarańczowy | `fallback_local` | tak lokalnie |
| KAmod | `KAMOD_SENSOR_STATE_ERROR` | 3 | pomarańczowy | `fallback_local` | tak lokalnie |
| KAmod | `KAMOD_NODE_UNAVAILABLE` | 3 | pomarańczowy | `fallback_local` | tak lokalnie |
| Service-plane | `SERVICE_AGENT_UNAVAILABLE` | 2 | żółty | `continue_degraded` | nie |
| Service-plane | `SERVICE_NETWORK_AP_UNAVAILABLE` | 2 | żółty | `continue_degraded` | nie |
| Service-plane | `SERVICE_NETWORK_DHCP_UNAVAILABLE` | 2 | żółty | `continue_degraded` | nie |
| Service-plane | `SERVICE_NETWORK_FIREWALL_INVALID` | 3 | pomarańczowy | `continue_degraded` | nie dla wentylacji |
| AERO | `AERO_BUS_UNAVAILABLE` | 3 | pomarańczowy | `fallback_local` | lokalnie |
| AERO | `AERO_COMMAND_NOT_CONFIRMED` | 3 | pomarańczowy | `fallback_local` | lokalnie |
| Zigbee | `ZIGBEE_MQTT_DISCONNECTED` | 2 | żółty | `continue_degraded` | nie |
| Zigbee | `ZIGBEE_BRIDGE_OFFLINE` | 2 | żółty | `continue_degraded` | nie |
| Zigbee | `ZIGBEE_DEVICE_OFFLINE` | 2 | żółty | `fallback_local` | jeśli dane wymagane |
| Zigbee | `ZIGBEE_DEVICE_DATA_STALE` | 2 | żółty | `fallback_local` | jeśli dane wymagane |
| Zigbee | `ZIGBEE_LOW_BATTERY` | 1 | niebieski | `continue` | nie |
| Pogoda | `WEATHER_UNAVAILABLE` | 1 | niebieski | `continue` | obecnie nie |
| Pogoda | `WEATHER_DATA_STALE` | 1 | niebieski | `continue` | obecnie nie |
| Harmonogram | `SCHEDULE_INVALID` | 2 | żółty | `fallback_local` | dla AUTO |
| Harmonogram | `SCHEDULE_STORE_UNAVAILABLE` | 2 | żółty | `fallback_local` | dla AUTO |
| SHADOW | `SHADOW_ENGINE_UNAVAILABLE` | 1 | niebieski | `continue` | nie |
| AUTO | `AUTO_INPUTS_UNTRUSTED` | 3 | pomarańczowy | `fallback_local` | tak |
| Telemetria | `TELEMETRY_STORE_UNAVAILABLE` | 2 | żółty | `continue_degraded` | nie |
| Alert DB | `ALERT_STORE_UNAVAILABLE` | 3 | pomarańczowy | `continue_degraded` | nie dla sterowania |
| CM5 storage | `LOCAL_STORAGE_PRESSURE` | 3 | pomarańczowy | `continue_degraded` | nie dla sterowania |
| AI Bridge | `AI_BRIDGE_SYNC_TEMPORARY_FAILURE` | 1 | niebieski | `continue` | nie |
| AI Bridge | `AI_BRIDGE_BACKLOG_HIGH` | 2 | żółty | `continue_degraded` | nie |
| AI | `AI_ADVISORY_UNAVAILABLE` | 1 | niebieski | `continue` | nie |
| NAS | `NAS_STORAGE_UNAVAILABLE` | 1 | niebieski | `continue` | nie |

## 11. Walidacja pliku konfiguracyjnego

Przed zastosowaniem konfiguracji powinno istnieć narzędzie, np.:

```bash
wvc-alertctl validate /etc/workshop-ventilation/alerts-v2.toml
```

Validator ma co najmniej sprawdzać:

- `schema_version`,
- unikalność kodów,
- `weight` w zakresie 0..4,
- zgodność `severity` i `hmi_color` z dozwolonym modelem,
- dozwolone wartości `reaction`,
- poprawny `scope`,
- poprawny `owner`,
- poprawne typy wszystkich pól,
- brak reakcji zabronionych przez twarde niezmienniki bezpieczeństwa,
- brak możliwości ustawienia `safe_state` dla alertów TACHO,
- brak możliwości osłabienia minimalnej polityki bezpieczeństwa krytycznych alertów DAC.

Przy błędzie nowa konfiguracja nie może zostać aktywowana. Core ma zachować **last-known-good policy** i jednoznacznie zgłosić błąd konfiguracji.

## 12. Zasady instalacji i aktualizacji

Repo zawiera wzorzec:

```text
config/alerts-v2.default.toml
```

Docelowy instalator powinien:

1. utworzyć `/etc/workshop-ventilation/alerts-v2.toml` z defaultu tylko wtedy, gdy aktywnego pliku jeszcze nie ma,
2. nie nadpisywać automatycznie lokalnie zmodyfikowanej polityki podczas zwykłego OTA/update,
3. sprawdzać `schema_version`,
4. udostępniać jawny diff/migrację przy zmianie schematu,
5. walidować plik przed restartem/reloadem core.

Pierwsza wersja może stosować konfigurację po kontrolowanym restarcie `ventilation-core`. Hot-reload można dodać później dopiero po osobnej walidacji.

## 13. Stan implementacji względem obecnego repo

### Już istnieje i będzie rozwijane

- trwały Alert Stage 1 / ACK / historia,
- `DAC_STATE_UNCERTAIN`,
- `DAC_COMMUNICATION_LOST`,
- `SENSOR_BUS_UNAVAILABLE`,
- `SENSOR_NODE_UNAVAILABLE`,
- `SENSOR_DATA_INVALID`,
- diagnostyka SEN55,
- `AERO_BUS_UNAVAILABLE`,
- podstawowa diagnostyka TACHO,
- podstawowe alerty Zigbee,
- CM5 Service Agent i telemetria heartbeat KAmod,
- lokalny watchdog HMI ↔ CM5.

### Wymaga rozszerzenia / korelacji

- włączenie read-only Service Agent do warstwy diagnostycznej AlertV2,
- korelacja service-plane z produkcyjnym SENSOR BUS,
- `FAN_NO_ROTATION_FEEDBACK`,
- `FAN_RPM_OUT_OF_RANGE`,
- potwierdzanie wykonania AERO,
- systemowe alerty usług/persistence/storage,
- status AI/synchronizacji/pogody,
- HMI RGB wynikające z najwyższej aktywnej wagi.

### Nowa infrastruktura AlertV2

- loader TOML,
- validator i `wvc-alertctl`,
- model `weight/reaction/scope/affects_control/hmi_color`,
- correlator,
- last-known-good policy,
- wersjonowanie polityki,
- publikacja policy version/checksum w diagnostyce core.

## 14. Proponowana kolejność implementacji

1. **Policy loader + validator** bez zmiany zachowania produkcyjnego.
2. **Rozszerzenie rekordu AlertV2** z zachowaniem kompatybilności obecnego API.
3. **Mapowanie istniejących Alert Stage 1** na TOML i test zgodności 1:1.
4. **Read-only adapter Service Agent** bez uzależniania `ventilation-core` od działania Wi-Fi.
5. **Correlator SENSOR BUS / KAmod / SEN55**.
6. **Operational TACHO** z twardym testem regresyjnym: brak TACHO nie zatrzymuje systemu.
7. **AERO command confirmation**.
8. **Alerty usług/persistence/storage/AI/weather** zgodnie z ich niekrytycznym charakterem.
9. **Wyjście HMI severity + sterowanie paskiem RGB**.
10. **GUI AlertV2** dopiero na stabilnym kontrakcie core.
11. Pełne fault-injection i walidacja na fizycznym CM5/HMI przed jakimkolwiek merge do `main`.

## 15. Kryteria akceptacji AlertV2

AlertV2 można uznać za gotowy dopiero gdy:

- obecne Alert Stage 1 nie mają regresji,
- plik TOML jest walidowany przed użyciem,
- błędny TOML nie może osłabić twardych zasad bezpieczeństwa,
- brak TACHO nigdy nie wywołuje globalnego STOP,
- Service Agent pozostaje niezależny od produkcyjnego sterowania,
- korelacja redukuje duplikaty bez utraty szczegółów diagnostycznych,
- ACK nie zmienia wagi ani koloru,
- pasek HMI zawsze odpowiada najwyższej aktywnej wadze, z lokalnym wyjątkiem watchdog CM5,
- utrata HMI nie zatrzymuje core,
- utrata AI/NAS/Internetu/pogody nie zatrzymuje core,
- historia alertów zachowuje źródłowe szczegóły i policy version,
- wszystkie krytyczne i degradowane ścieżki przechodzą kontrolowany fault-injection na CM5,
- `main` pozostaje nietknięty do czasu jawnej decyzji o merge.

## 16. Decyzja projektowa

`config/alerts-v2.default.toml` i ten dokument są **punktem bazowym do implementacji Core AlertV2**. Nie oznaczają jeszcze aktywacji nowego zachowania w produkcji.

Najpierw budujemy i walidujemy mechanizm polityki oraz korelacji w osobnej gałęzi. Dopiero po stabilizacji kontraktu AlertV2 wracamy do finalnego wyglądu zakładki ALERTY w Web GUI/HMI.
