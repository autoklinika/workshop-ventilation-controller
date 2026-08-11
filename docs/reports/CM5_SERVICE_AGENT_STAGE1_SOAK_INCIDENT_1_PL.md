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
duration:             1800 s
interval:             10 s
ventilation-core PID: 23824
```

Próbki 1–64 zakończyły się wynikiem PASS. Podczas próbki 65 walidator zakończył pracę komunikatem:

```text
not all service nodes are online
```

Test trwał w tym momencie około 11 minut.

## 2. Ustalenia po zebraniu diagnostyki

Kolektor diagnostyczny potwierdził, że incydent dotyczył wyłącznie:

```text
sensor-node-2
IP:  10.55.0.110
MAC: 88:13:BF:01:37:28
```

Przejścia z journala agenta:

```text
2026-08-06 13:24:04,643  sensor-node-2 heartbeat offline
2026-08-06 13:24:19,134  sensor-node-2 heartbeat online
```

Próg offline wynosi 35 sekund. Ponieważ agent sprawdza timeout cyklicznie, ostatni zaakceptowany heartbeat musiał pojawić się około 50 sekund przed ponownym przejściem do online. Odpowiada to utracie około pięciu kolejnych okresów heartbeat przy nominalnym okresie 10 sekund.

`sensor-node-1` nie przeszedł do offline.

## 3. Brak restartu firmware

Po incydencie `sensor-node-2` raportował:

```text
boot_id:  6e02bc0cb541fb76
seq:      1187
uptime_s: 11887
state:    online
```

`boot_id` pozostał taki sam jak przed incydentem, a uptime był ciągły. Nie nastąpił więc restart ESP32, watchdog reset ani ponowne uruchomienie całego firmware.

Stosunek `seq` do uptime pozostaje zgodny z nominalnym okresem około 10 sekund. Dodatkowo oba węzły miały niemal identyczną relację liczby wysłanych heartbeat do czasu pracy:

```text
sensor-node-1: seq=1188, uptime_s=11895
sensor-node-2: seq=1187, uptime_s=11887
```

To silnie wskazuje, że zadanie heartbeat w `sensor-node-2` wykonywało kolejne cykle. Samo powodzenie UDP `sendto()` potwierdza jednak tylko przyjęcie datagramu przez lokalny stos sieciowy ESP32, nie jego dostarczenie do CM5.

## 4. Stan stacji Wi-Fi na AP

Snapshot `iw dev wlan0 station dump` wykonany po incydencie pokazał:

### sensor-node-2

```text
associated:      yes
authenticated:   yes
connected time:  11861 s
inactive time:   4000 ms
signal/RSSI HB:  około -52 dBm
tx failed AP->STA: 0
```

### sensor-node-1

```text
associated:      yes
authenticated:   yes
connected time:  11876 s
inactive time:   8000 ms
signal/RSSI HB:  około -47 dBm
tx failed AP->STA: 1
```

Czasy `connected time` są ciągłe i zgodne z czasem pracy firmware. Nie ma śladu rozłączenia i ponownej asocjacji `sensor-node-2` podczas incydentu.

Pole `authorized=no` występowało dla obu stacji w otwartej sieci serwisowej, mimo prawidłowej asocjacji, uwierzytelnienia i rzeczywistego przepływu danych. Nie jest ono samo w sobie dowodem awarii.

Licznik `tx failed` z `iw station dump` opisuje transmisję AP do stacji, natomiast heartbeat płynie ze stacji do AP. Wartość `0` dla węzła 2 nie mierzy więc bezpośrednio utraty jego datagramów przychodzących, ale potwierdza brak widocznego problemu w kierunku przeciwnym.

## 5. Stan CM5 i sieci serwisowej

NetworkManager raportował:

```text
wlan0 state:       100 connected
profile:           wvc-sensor-service
address:           10.55.0.1/24
driver:            brcmfmac 7.45.16.144
firmware:          01-b677b91b
```

W zebranym oknie nie znaleziono zdarzeń kernela dotyczących:

```text
wlan0
brcmfmac
deauthentication
disassociation
disconnect
timeout
```

Agent działał bez restartu, a drugi węzeł pozostał online. Nie ma dowodu na globalną awarię AP, procesu agenta ani interfejsu Wi-Fi CM5.

Tablica sąsiadów zawierała oba adresy jako `STALE`, co jest normalnym stanem wpisu ARP bez bieżącej potrzeby transmisji zwrotnej i nie oznacza utraty asocjacji.

Pierwsza wersja kolektora sprawdzała błędną ścieżkę `/var/lib/misc/dnsmasq.leases`. Konfiguracja tej instalacji zapisuje dzierżawy w:

```text
/var/lib/misc/dnsmasq-wvc.leases
```

Kolektor został poprawiony.

## 6. Najbardziej prawdopodobna klasyfikacja

Na obecnym materiale incydent należy klasyfikować jako:

```text
około 50-sekundowa przerwa w dostarczaniu heartbeat UDP
z sensor-node-2 do CM5
przy ciągłej asocjacji Wi-Fi
bez restartu firmware i bez awarii Modbus RTU
```

Najbardziej prawdopodobne scenariusze:

1. utrata kilku kolejnych datagramów w ścieżce ESP32 Wi-Fi -> radio -> AP,
2. chwilowa degradacja radiowa niewywołująca utraty asocjacji,
3. pakiety przyjęte przez lokalny stos UDP ESP32, ale niedostarczone przez sterownik lub warstwę radiową,
4. rzadki problem sterownika/firmware Wi-Fi pojedynczego KAmod.

Po odczytaniu ciągłego `connected time` scenariusz pełnego rozłączenia i ponownej asocjacji stał się mało prawdopodobny.

Nie ma podstaw, aby przypisywać incydent do:

- restartu KAmod,
- awarii `wvc-service-agent.service`,
- awarii całego AP,
- błędu HMAC lub replay protection,
- awarii produkcyjnego SENSOR BUS.

W journalu agenta nie było wpisów `rejected heartbeat`.

## 7. Defekt walidatora ujawniony przez incydent

Pierwsza wersja soak walidatora:

- wypisywała tylko ogólne `not all service nodes are online`,
- kasowała katalog tymczasowy przy wyjściu,
- nie zachowywała snapshotu awarii,
- nie dołączała logów agenta, stanu stacji Wi-Fi ani danych `boot_id`/`seq`.

To ograniczenie zostało poprawione.

Walidator po poprawce:

- podaje stan każdego węzła,
- zapisuje `node_id`, `received_unix_ms`, `source_ip`, `boot_id`, `seq`, uptime, RSSI i licznik zapytań Modbus,
- zachowuje pełne snapshoty JSON po awarii,
- zachowuje journal agenta i kernela oraz stan sieci,
- drukuje ścieżkę katalogu diagnostycznego.

Dodano także kolektor:

```text
tools/diagnose_cm5_service_agent_dropout.sh
```

## 8. Dodana obserwowalność transportu heartbeat

Service Agent został rozszerzony o trwałe, per-node liczniki przechowywane w:

```text
/var/lib/wvc-service-heartbeat/diagnostics/<node_id>.json
```

API `wvc-servicectl status|nodes` publikuje teraz sekcję `transport` zawierającą:

```text
accepted_heartbeats
online_transitions
offline_transitions
boot_changes
sequence_gap_events
missing_heartbeats_total
max_sequence_gap
last_sequence_gap
last_receive_gap_ms
max_receive_gap_ms
last_boot_id
last_seq
last_received_unix_ms
last_offline_unix_ms
```

Przy wykryciu luki `seq` agent zapisuje ostrzeżenie z poprzednią i bieżącą sekwencją, liczbą brakujących heartbeat oraz odstępem odbioru. Liczniki przetrwają restart samego agenta.

Kolektor diagnostyczny został rozszerzony o te dane, journal NetworkManagera i wpa_supplicant oraz prawidłową ścieżkę pliku dzierżaw DHCP.

Checkpoint przeszedł CI:

```text
Ventilation Core Tests #460: success
```

## 9. Dalsze działania

Przed końcowym soak testem należy:

1. wdrożyć nową wersję Service Agent z licznikami transportu,
2. potwierdzić pojawienie się sekcji `transport` dla obu węzłów,
3. wykonać krótki test kontrolny licznika sekwencji,
4. powtórzyć 30-minutowy soak z zachowywaniem pełnych artefaktów przy pierwszym incydencie,
5. osobno zaplanować rozszerzenie firmware o liczniki rozłączeń Wi-Fi, uzyskań IP oraz prób i błędów wysyłki heartbeat.

Nie należy zwiększać progu offline ponad 35 sekund wyłącznie w celu ukrycia tej przerwy.

## 10. Status

```text
soak #1:                         FAIL
węzeł:                           sensor-node-2
czas przerwy dostarczania:        około 50 s
ciągłość asocjacji Wi-Fi:         TAK
restart firmware:                 NIE
awaria całego AP/CM5:             NIE
błąd HMAC/replay:                 BRAK DOWODÓW
ciągłość produkcyjnego Modbus:    zachowana
przyczyna transportowa:           utrata datagramów / degradacja ścieżki Wi-Fi
obserwowalność transportu:        ROZSZERZONA
Stage 1 final validation:         BLOCKED UNTIL REPEATED SOAK
```

PR #12 pozostaje Draft. Nie wykonano merge ani nie oznaczono Ready for Review.
