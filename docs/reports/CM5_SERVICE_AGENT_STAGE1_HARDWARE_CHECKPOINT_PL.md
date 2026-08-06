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

## 5. Defekty wykryte i poprawione podczas bring-up

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

## 6. Pozostałe testy Stage 1

Do wykonania przed końcowym raportem:

1. restart `wvc-service-agent.service` podczas aktywnego Modbus i potwierdzenie ciągłości liczników SENSOR BUS,
2. zatrzymanie agenta na ponad 35 s i potwierdzenie braku wpływu na `ventilation-core`,
3. utrata heartbeat pojedynczego węzła bez wpływu na drugi,
4. kontrola odtworzenia stanu po ponownym uruchomieniu agenta,
5. minimum 30 min soak testu obu heartbeat przy aktywnym Modbus,
6. końcowa kontrola braku portów TCP i braku routingu.

## 7. Status

```text
pierwszy sprzętowy bring-up po poprawkach: PASS
Stage 1 final validation:                 IN PROGRESS
```

PR #12 pozostaje Draft. Nie wykonano merge ani nie oznaczono Ready for Review.
