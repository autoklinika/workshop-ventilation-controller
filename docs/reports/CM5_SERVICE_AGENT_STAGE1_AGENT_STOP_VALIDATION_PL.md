# CM5 Service Agent Stage 1 — walidacja zatrzymania całego agenta

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

## 1. Cel testu

Potwierdzić, że całkowite zatrzymanie `wvc-service-agent.service` na czas przekraczający próg offline heartbeat nie wpływa na produkcyjny `ventilation-core` ani SENSOR BUS Modbus RTU.

Podczas testu nie odłączano:

- zasilania CM5,
- zasilania KAmod,
- SEN55,
- RS-485,
- AP `WVC-SERVICE`,
- DHCP ani firewalla.

Zatrzymano wyłącznie proces:

```text
wvc-service-agent.service
```

na około 45 sekund.

## 2. Niezależność procesu głównego

PID `ventilation-core` pozostał identyczny przez cały test:

```text
przed zatrzymaniem agenta:  23824
podczas zatrzymania agenta: 23824
po uruchomieniu agenta:     23824
```

Wynik:

```text
brak restartu ventilation-core: PASS
```

## 3. Ciągłość SENSOR BUS

### Slave 1

```text
polls:             4280 -> 4322 -> 4327
successful_polls:  4280 -> 4322 -> 4327
online:            true
usable:            true
communication_errors:  0
consecutive_failures:  0
```

### Slave 2

```text
polls:             4280 -> 4322 -> 4327
successful_polls:  4280 -> 4322 -> 4327
online:            true
usable:            true
communication_errors:  0
consecutive_failures:  0
```

Stan workera po teście:

```text
ready:             true
worker_alive:      true
worker_restarts:   0
last_error:        null
```

W okresie zatrzymania agenta oba slave wykonały po 42 kolejne poprawne transakcje Modbus. Po ponownym uruchomieniu agenta wykonano jeszcze pięć kolejnych poprawnych cykli przed końcowym snapshotem.

Wynik:

```text
ciągłość SENSOR BUS przy całkowitym braku service-agent: PASS
```

## 4. Odtworzenie stanu serwisowego

Po uruchomieniu `wvc-service-agent.service` agent automatycznie:

1. związał UDP `10.55.0.1:45551`,
2. utworzył lokalny Unix socket,
3. przyjął pierwszy poprawny heartbeat `sensor-node-1`,
4. przyjął pierwszy poprawny heartbeat `sensor-node-2`,
5. odtworzył stan `online_nodes=2`.

Stan końcowy:

```text
agent.ready:       true
online_nodes:      2
network.ready:     true
```

Logi:

```text
Started wvc-service-agent.service
CM5 service agent listening on UDP 10.55.0.1:45551
node=sensor-node-1 service heartbeat online
node=sensor-node-2 service heartbeat online
```

Wynik:

```text
automatyczne odtworzenie service plane po pełnym zatrzymaniu: PASS
```

## 5. Wniosek architektoniczny

Test sprzętowy potwierdził założony podział domen odpowiedzialności:

```text
wvc-service-agent.service
    = diagnostyka serwisowa Wi-Fi

ventilation-core.service + SENSOR BUS
    = niezależny produkcyjny kanał sterowania i pomiarów
```

Brak procesu Service Agent nie powoduje:

- restartu `ventilation-core`,
- restartu workera SENSOR BUS,
- przerwania odczytów Modbus,
- wzrostu błędów komunikacji,
- oznaczenia czujników jako offline lub unusable.

## 6. Wynik

```text
full service-agent stop isolation: PASS
ventilation-core continuity:       PASS
SENSOR BUS continuity:             PASS
service-plane recovery:            PASS
```

PR #12 pozostaje Draft. Nie wykonano merge ani nie oznaczono Ready for Review.
