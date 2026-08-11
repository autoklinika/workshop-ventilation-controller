# CM5 Service Agent Stage 1 — incydent soak #2

Data: 2026-08-06

Gałąź:

```text
agent/cm5-service-agent-stage1
```

Draft PR:

```text
#12
```

## 1. Przebieg

Drugi 30-minutowy soak uruchomiono po wdrożeniu trwałej telemetrii transportowej CM5. Walidator przeszedł 24 próbki, po czym zakończył się przy `sensor-node-2` w stanie offline.

Stan procesu i sieci pozostał prawidłowy:

```text
ventilation-core PID: 23824
agent.ready:          true
network.ready:        true
online_nodes:         1
```

## 2. Węzeł dotknięty incydentem

```text
node_id:             sensor-node-2
boot_id:             6e02bc0cb541fb76
last seq:            1324
last uptime_s:       13258
last RSSI:           -51 dBm
last received:       1786017911563 ms
marked offline:      1786017947146 ms
```

Odstęp między ostatnim zaakceptowanym heartbeat a oznaczeniem offline wyniósł około 35,6 s.

`sensor-node-1` pozostał online i raportował heartbeat z odstępami około 10 s.

## 3. Telemetria transportowa przed dropout

Dla `sensor-node-2`:

```text
accepted_heartbeats:       27
sequence_gap_events:       2
missing_heartbeats_total:  2
max_sequence_gap:          1
last_sequence_gap:         1
last_receive_gap_ms:       20333
max_receive_gap_ms:        20333
offline_transitions:       1
boot_changes:              0
```

Oznacza to, że przed końcowym dropout agent dwukrotnie odebrał pakiet z luką dokładnie jednego numeru `seq`. Potwierdzono więc dwa pojedyncze datagramy, które nie dotarły do agenta, mimo że późniejszy pakiet z wyższym `seq` został zaakceptowany.

Następnie nie dotarł żaden kolejny heartbeat przez ponad 35 s.

## 4. Co można już wykluczyć

- restart ESP32 — `boot_id` i uptime pozostały ciągłe,
- restart Service Agent — proces i socket działały,
- globalną awarię AP — drugi węzeł pozostał online,
- awarię konfiguracji CM5 — AP, adres, DHCP i firewall raportowały ready,
- błąd HMAC/replay — brak `rejected heartbeat`,
- degradację produkcyjnego SENSOR BUS jako przyczynę service dropout.

## 5. Dane stacji Wi-Fi

Snapshot `iw station dump` z wcześniejszego incydentu wykazał dla obu KAmod:

```text
associated:     yes
authenticated:  yes
connected time: ciągły
```

Dla node-2 nie było błędów TX po stronie AP. Parametr ten opisuje jednak kierunek AP -> STA i nie potwierdza dostarczenia heartbeat STA -> AP.

## 6. Brakująca obserwowalność firmware

Telemetria CM5 rozpoznaje luki w odebranym `seq`, ale nie rozróżnia:

1. lokalnego błędu `sendto()` na ESP32 — sekwencja nie rośnie,
2. sukcesu `sendto()` i utraty datagramu później — sekwencja rośnie,
3. zdarzenia Wi-Fi disconnect/reconnect,
4. zatrzymania lub opóźnienia taska heartbeat.

Dlatego powstała osobna gałąź firmware:

```text
agent/kamod-service-wifi-transport-diagnostics
```

Nie zmienia ona PR #11 ani zachowania transportu. Dodaje wyłącznie liczniki prób/sukcesów/błędów wysyłki oraz zdarzeń Wi-Fi.

## 7. Status

```text
soak #2:                         FAIL
węzeł:                           sensor-node-2
potwierdzone luki seq:            2 x 1 pakiet
końcowy brak heartbeat:           >35 s
restart firmware:                 NIE
agent / AP global failure:        NIE
przyczyna dokładna:               WYMAGA TELEMETRII FIRMWARE 0.4.1-stage1
Stage 1 final validation:         BLOCKED
```

PR #12 pozostaje Draft. Nie wykonano merge ani nie oznaczono Ready for Review.
