# CM5 Service Agent Stage 1 — incydent soak #3 po resecie obu KAmod

Data: 2026-08-06

Gałąź:

```text
agent/cm5-service-agent-stage1
```

Draft PR:

```text
#12
```

## 1. Cel testu

Po dwóch wcześniejszych dropoutach `sensor-node-2` wykonano pełny power-cycle obu fizycznych KAmod bez zmiany firmware. Celem było sprawdzenie, czy problem wynikał z przejściowego stanu stosu Wi-Fi po długiej pracy lub wcześniejszych testach.

Oba węzły uruchomiły się poprawnie z nowymi `boot_id`, zachowując provisioning NVS, adresy Modbus i klucze HMAC.

## 2. Krótki soak po resecie

Uruchomiono walidator:

```text
duration: 120 s
interval: 10 s
ventilation-core PID: 23824
```

Historyczne liczniki SENSOR BUS po celowym wyłączeniu zasilania przyjęto jako baseline:

```text
slave 1: polls=10012 successful=10002 communication_errors=10
slave 2: polls=10012 successful=10002 communication_errors=10
```

Przez próbki 1–9 liczniki te nie wzrosły. Produkcyjny SENSOR BUS działał poprawnie.

Przy kolejnej próbce walidator wykrył `sensor-node-2` offline.

## 3. Stan węzłów w chwili incydentu

### sensor-node-1

```text
online:       true
boot_id:      b9dfa1228a665be1
seq:          105
uptime_s:     1054
RSSI:         -53 dBm
last receive: 1786020410606 ms
```

### sensor-node-2

```text
online:       false
boot_id:      6fc74947bbf4f954
seq:          102
uptime_s:     1025
RSSI:         -58 dBm
last receive: 1786020381384 ms
marked offline: 1786020416616 ms
```

Odstęp między ostatnim zaakceptowanym heartbeat node-2 a oznaczeniem offline wyniósł około 35,2 s.

`boot_id` node-2 nie zmienił się w trakcie incydentu. Nie nastąpił restart firmware.

## 4. Stan CM5 i SENSOR BUS

W chwili incydentu:

```text
agent.ready:       true
network.ready:     true
registered_nodes:  2
online_nodes:      1
ventilation-core:  ten sam PID 23824
worker_alive:      true
worker_restarts:   0
last_error:        null
```

Oba slave Modbus pozostawały:

```text
online: true
usable: true
measurement_valid: true
measurement_stale: false
consecutive_failures: 0
```

Liczniki po próbce:

```text
slave 1: polls=10098 successful=10088 communication_errors=10
slave 2: polls=10098 successful=10088 communication_errors=10
```

Oznacza to, że podczas samego krótkiego soak nie pojawił się żaden nowy błąd Modbus. Historyczne 10 timeoutów i po jednej próbce invalid/stale pochodziły z celowego power-cycle obu urządzeń.

## 5. Wniosek

Reset obu KAmod nie rozwiązał problemu service-plane.

Dropout:

- ponownie dotyczył wyłącznie `sensor-node-2`,
- wystąpił około 17 minut po restarcie urządzeń i około 90 s po rozpoczęciu krótkiego soak,
- nie spowodował restartu ESP32,
- nie wpłynął na `sensor-node-1`, AP, Service Agent ani produkcyjny SENSOR BUS.

Wynik potwierdza powtarzalny problem dostarczania heartbeat UDP dla konkretnego węzła, niezależny od długiego uptime i możliwego starego stanu stosu po wcześniejszych testach.

## 6. Następny krok diagnostyczny

Bez zmiany firmware należy po odzyskaniu node-2 odczytać:

```text
seq
last_sequence_gap
sequence_gap_events
missing_heartbeats_total
last_receive_gap_ms
max_receive_gap_ms
```

Skok `seq` po odzyskaniu pokaże, czy w czasie przerwy firmware nadal zwiększał sekwencję, co w obecnym firmware następuje wyłącznie po lokalnym sukcesie `sendto()`.

Pełne rozróżnienie lokalnego błędu `sendto()`, zdarzenia Wi-Fi i utraty pakietu po przyjęciu przez stos wymaga przygotowanego, lecz jeszcze niewgranego firmware `0.4.1-stage1` z Draft PR #13.

## 7. Status

```text
soak #3 po power-cycle:          FAIL
węzeł:                          sensor-node-2
restart jako rozwiązanie:        NIE
restart firmware w incydencie:   NIE
Modbus RTU podczas soak:         PASS, brak nowych błędów
Stage 1 final validation:        BLOCKED
```

PR #12 pozostaje Draft. Nie wykonano merge ani nie oznaczono Ready for Review.
