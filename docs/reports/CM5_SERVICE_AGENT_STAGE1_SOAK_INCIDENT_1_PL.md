# CM5 Service Agent Stage 1 — incydent soak #1

Data: 2026-08-06

Repozytorium: `autoklinika/workshop-ventilation-controller`

Gałąź:

```text
agent/cm5-service-agent-stage1
```

Draft PR:

```text
#12
```

## 1. Przebieg

Uruchomiono sprzętowy soak test:

```text
duration: 1800 s
interval: 10 s
ventilation-core PID: 23824
```

Próbki 1–64 zakończyły się wynikiem PASS. Podczas próbki 65 walidator zakończył pracę komunikatem:

```text
not all service nodes are online
```

Test trwał w tym momencie około 11 minut.

## 2. Co wiadomo

Komunikat oznacza, że w chwili snapshotu liczba węzłów z `online=true` była mniejsza niż dwa. Próg offline agenta wynosi 35 sekund, dlatego nie był to pojedynczy utracony datagram heartbeat.

Na podstawie samego starego komunikatu nie można jeszcze ustalić:

- który węzeł był offline,
- czy firmware KAmod wykonał restart,
- czy zmienił się `boot_id`,
- czy zatrzymało się wyłącznie zadanie heartbeat,
- czy wystąpiła utrata asocjacji Wi-Fi,
- czy węzeł samoczynnie wrócił online,
- czy produkcyjny Modbus RTU pozostał ciągły w dokładnym momencie incydentu.

Nie należy uznawać Stage 1 za zwalidowany ani powtarzać testu bez zebrania diagnostyki.

## 3. Defekt walidatora ujawniony przez incydent

Pierwsza wersja soak walidatora:

- wypisywała tylko ogólne `not all service nodes are online`,
- kasowała katalog tymczasowy przy wyjściu,
- nie zachowywała snapshotu awarii,
- nie dołączała logów agenta, stanu stacji Wi-Fi ani danych `boot_id`/`seq`.

To ograniczenie zostało poprawione.

## 4. Poprawki diagnostyczne

Walidator po poprawce:

- podaje stan każdego węzła,
- zapisuje `node_id`, `received_unix_ms`, `source_ip`, `boot_id`, `seq`, uptime, RSSI i licznik zapytań Modbus,
- zachowuje pełne snapshoty JSON po awarii,
- zachowuje journal `wvc-service-agent.service`, journal kernela, `iw station dump`, tablicę sąsiadów, stan NetworkManagera i lease DHCP,
- drukuje ścieżkę katalogu diagnostycznego.

Dodano także osobny kolektor:

```text
tools/diagnose_cm5_service_agent_dropout.sh
```

## 5. Status

```text
soak #1:                         FAIL
przyczyna funkcjonalna:          DO USTALENIA
ciągłość Modbus w chwili failu:  DO POTWIERDZENIA
walidator diagnostyczny:         POPRAWIONY
Stage 1 final validation:        BLOCKED BY INVESTIGATION
```

PR #12 pozostaje Draft. Nie wykonano merge ani nie oznaczono Ready for Review.
