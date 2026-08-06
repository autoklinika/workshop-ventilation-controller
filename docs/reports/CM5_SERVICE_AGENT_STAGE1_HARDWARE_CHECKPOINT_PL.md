# CM5 Service Agent Stage 1 — checkpoint sprzętowy

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

## 1. Wynik pierwszego wdrożenia po poprawkach

`wvc-service-agent.service` został zainstalowany na docelowym CM5 i uruchomiony jako niezależna usługa systemowa.

Potwierdzono:

```text
service:                 active (running)
legacy receiver:         inactive
UDP bind:                10.55.0.1:45551
Unix socket:             /run/wvc-service-agent/service-agent.sock
registered nodes:        2
online nodes:            2
network ready:           true
```

Walidator zakończył wszystkie kontrole wynikiem `PASS`:

- agent aktywny,
- legacy receiver nieaktywny,
- rejestr kluczy zabezpieczony,
- lokalny socket API zabezpieczony,
- UDP/45551 związany z prywatnym adresem AP,
- minimalna reguła nftables obecna,
- brak nowych portów TCP,
- routing IPv4 i IPv6 wyłączony,
- lokalne API odpowiada,
- komendy API dostępne.

## 2. Stan sieci serwisowej

Agent raportuje:

```text
interface:          wlan0
profile:            wvc-sensor-service
bind_address:       10.55.0.1
ap_active:          true
address_present:    true
dhcp_active:        true
firewall_active:    true
ready:              true
```

Pierwszy bring-up wykrył fałszywe `address_present=false`. Przyczyną była metoda parsowania wyniku `ip -4 -o address`. Implementację poprawiono tak, aby czytała `IP4.ADDRESS` przez NetworkManager. Po poprawce stan jest prawidłowy.

## 3. Stan węzłów KAmod

### sensor-node-1

```text
online:                         true
source_ip:                      10.55.0.106
MAC:                            88:13:BF:00:52:D0
firmware:                       0.4.0-stage1
RSSI:                           około -51 dBm
sensor_state:                   running
rs485_ready:                    true
modbus_monitor_ready:           true
modbus_address:                 1
modbus_requests_last_60s:       56
modbus_service_errors:          0
sensor communication failures: 0
sensor detection failures:     0
sensor CRC failures:           0
OTA pending:                    false
```

### sensor-node-2

```text
online:                         true
source_ip:                      10.55.0.110
MAC:                            88:13:BF:01:37:28
firmware:                       0.4.0-stage1
RSSI:                           około -47 dBm
sensor_state:                   running
rs485_ready:                    true
modbus_monitor_ready:           true
modbus_address:                 2
modbus_requests_last_60s:       56
modbus_service_errors:          0
sensor communication failures: 3
sensor detection failures:     32
sensor CRC failures:           0
OTA pending:                    false
```

Liczniki `3 + 32` dla drugiego węzła odpowiadają wcześniej potwierdzonemu chwilowemu odłączeniu SEN55. Bieżący stan jest poprawny: `sensor_state=running`, świeże pomiary, brak aktywnego błędu i brak wzrostu błędów Modbus service.

Pierwszy bring-up wykrył `modbus_address=null`, ponieważ firmware publikuje pole `modbus_slave`. Agent został poprawiony i mapuje teraz `modbus_slave` na znormalizowane `modbus_address`.

## 4. Niezależność od produkcyjnego SENSOR BUS

Po instalacji i restarcie agenta produkcyjny kanał Modbus RTU pozostał aktywny.

Stan `ventilationctl sensors`:

```text
port:                 /dev/ttyAMA0
baud:                 19200
addresses:            1,2
ready:                true
worker_alive:         true
worker_restarts:      0
last_error:           null
```

Dla obu slave:

```text
online:                  true
usable:                  true
measurement_valid:       true
measurement_stale:       false
sensor_present:          true
communication_errors:    0
consecutive_failures:    0
invalid_measurements:    0
stale_measurements:      0
map_version_errors:      0
polls:                   3256
successful_polls:        3256
```

Wynik:

```text
restart i migracja service-agent nie wpłynęły na SENSOR BUS
```

## 5. Restart agenta podczas aktywnego Modbus

Wykonano kontrolowany restart `wvc-service-agent.service` podczas ciągłego odpytywania obu slave przez `ventilation-core`.

Wynik:

```text
ventilation-core PID przed: 23824
ventilation-core PID po:    23824
```

Dla obu slave w 20-sekundowym oknie:

```text
polls:                  3464 -> 3482, delta +18
successful_polls:       3464 -> 3482
online:                 true
usable:                 true
communication_errors:   0
consecutive_failures:   0
```

Stan workera po restarcie agenta:

```text
ready:             true
worker_alive:      true
worker_restarts:   0
last_error:        null
```

Agent po restarcie odzyskał oba węzły:

```text
registered_nodes: 2
online_nodes:     2
network.ready:    true
```

Logi potwierdziły uporządkowane zatrzymanie i ponowne uruchomienie agenta oraz ponowne przejście obu węzłów do `online`.

Wynik:

```text
restart wvc-service-agent podczas aktywnego Modbus: PASS
izolacja failure domains service plane / SENSOR BUS: PASS
```

## 6. Utrata heartbeat pojedynczego węzła

Na CM5 dodano tymczasową regułę nftables blokującą wyłącznie heartbeat UDP/45551 z adresu `10.55.0.110`, należącego do `sensor-node-2`. Zasilanie, SEN55 i RS-485 pozostały podłączone.

Przed blokadą:

```text
sensor-node-1 online=true, modbus_address=1
sensor-node-2 online=true, modbus_address=2
```

Po 45 sekundach blokady:

```text
sensor-node-1 online=true,  modbus_address=1
sensor-node-2 online=false, modbus_address=2
```

Agent poprawnie zachował ostatnią uwierzytelnioną diagnostykę i adres Modbus węzła oznaczonego offline.

W tym samym okresie produkcyjny SENSOR BUS pracował bez przerwy:

```text
przed blokadą:       polls=3853, successful=3853
podczas blokady:     polls=3895, successful=3895
po odblokowaniu:     polls=3914, successful=3914
```

Dla obu slave przez cały test:

```text
online=true
usable=true
communication_errors=0
worker_restarts=0
last_error=null
```

Po usunięciu tymczasowej reguły `sensor-node-2` automatycznie wrócił do `online=true`, bez restartu agenta, firmware ani `ventilation-core`.

Logi zawierają prawidłową parę przejść:

```text
2026-08-06 12:55:42,962 WARNING node=sensor-node-2 service heartbeat offline
2026-08-06 12:55:57,132 INFO    node=sensor-node-2 service heartbeat online
```

Wynik:

```text
pojedynczy heartbeat offline/online detection: PASS
brak fałszywego oznaczenia awarii Modbus:      PASS
izolacja sensor-node-1 od awarii node-2:       PASS
ciągłość SENSOR BUS podczas awarii Wi-Fi:      PASS
```

## 7. Defekty wykryte i poprawione podczas bring-up

1. Installer wykonywał `wvc-servicectl status` zanim daemon utworzył Unix socket.
   - Poprawka: oczekiwanie na realną odpowiedź API z limitem czasu.
2. Agent raportował `address_present=false` mimo aktywnego `10.55.0.1` i prawidłowego bindu UDP.
   - Poprawka: odczyt `nmcli -g IP4.ADDRESS device show wlan0`.
3. Agent nie rozpoznawał pola `modbus_slave` publikowanego przez firmware.
   - Poprawka: alias do znormalizowanego `modbus_address`.

Po poprawkach:

```text
network.ready=true
sensor-node-1 modbus_address=1
sensor-node-2 modbus_address=2
installer kończy się bez przejściowego błędu socketu
```

## 8. Pozostałe testy Stage 1

Do wykonania przed końcowym raportem:

1. zatrzymanie całego agenta na ponad 35 s i potwierdzenie braku wpływu na `ventilation-core`,
2. potwierdzenie odtworzenia stanu obu węzłów po ponownym uruchomieniu agenta,
3. minimum 30 min soak testu obu heartbeat przy aktywnym Modbus,
4. końcowa kontrola braku portów TCP i braku routingu.

## 9. Status

```text
pierwszy sprzętowy bring-up po poprawkach: PASS
restart agent / Modbus isolation:          PASS
single-node heartbeat isolation:           PASS
Stage 1 final validation:                  IN PROGRESS
```

PR #12 pozostaje Draft. Nie wykonano merge ani nie oznaczono Ready for Review.