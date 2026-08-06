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

Stosunek `seq` do uptime pozostaje zgodny z nominalnym okresem około 10 sekund. To silnie wskazuje, że zadanie heartbeat nadal wykonywało kolejne cykle albo co najmniej nie zatrzymało się na około 50 sekund. Samo powodzenie UDP `sendto()` nie potwierdza jednak dostarczenia pakietu do CM5.

## 4. Stan CM5 i sieci serwisowej

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

Brak wpisów kernela nie wyklucza krótkiego problemu radiowego lub stacyjnego po stronie pojedynczego ESP32. Zebrany dotychczas journal nie obejmuje pełnej telemetrii NetworkManager/wpa_supplicant dla historycznego momentu incydentu.

## 5. Najbardziej prawdopodobna klasyfikacja

Na obecnym materiale incydent należy klasyfikować jako:

```text
około 50-sekundowa przerwa w dostarczaniu heartbeat UDP
z sensor-node-2 do CM5
bez restartu firmware i bez awarii Modbus RTU
```

Najbardziej prawdopodobne scenariusze:

1. chwilowa utrata lub degradacja łącza radiowego pojedynczego węzła,
2. utrata kilku kolejnych datagramów mimo pozornie aktywnej asocjacji,
3. krótkie rozłączenie/reasocjacja niewidoczne w zebranym journalu kernela,
4. pakiety przyjęte przez stos UDP ESP32, ale niedostarczone przez warstwę Wi-Fi.

Nie ma podstaw, aby przypisywać incydent do:

- restartu KAmod,
- awarii `wvc-service-agent.service`,
- awarii całego AP,
- błędu HMAC lub replay protection,
- awarii produkcyjnego SENSOR BUS.

W journalu agenta nie było wpisów `rejected heartbeat`.

## 6. Defekt walidatora ujawniony przez incydent

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

## 7. Dalsze działania

Przed ponownym końcowym soak testem należy:

1. sprawdzić historyczne logi NetworkManager/wpa_supplicant w dokładnym oknie 13:22:30–13:25:30,
2. dodać do diagnostyki firmware liczniki rozłączeń Wi-Fi, ponownych uzyskań IP oraz prób i błędów wysyłki heartbeat,
3. dodać po stronie odbiornika licznik luk sekwencji i maksymalnego odstępu między zaakceptowanymi heartbeat,
4. powtórzyć soak z zachowywaniem pełnych artefaktów przy pierwszym incydencie.

Nie należy zwiększać progu offline ponad 35 sekund wyłącznie w celu ukrycia tej przerwy.

## 8. Status

```text
soak #1:                         FAIL
węzeł:                           sensor-node-2
czas przerwy dostarczania:        około 50 s
restart firmware:                 NIE
awaria całego AP/CM5:             NIE POTWIERDZONA; MAŁO PRAWDOPODOBNA
błąd HMAC/replay:                 BRAK DOWODÓW
ciągłość produkcyjnego Modbus:    zachowana poza service-plane incident
przyczyna transportowa:           DO DALSZEGO USTALENIA
Stage 1 final validation:         BLOCKED BY INVESTIGATION
```

PR #12 pozostaje Draft. Nie wykonano merge ani nie oznaczono Ready for Review.
