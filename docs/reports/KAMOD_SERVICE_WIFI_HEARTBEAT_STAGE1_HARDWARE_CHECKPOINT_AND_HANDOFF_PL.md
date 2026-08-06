# KAmod Service Wi-Fi Heartbeat Stage 1 — checkpoint sprzętowy i handoff

Data: **2026-08-06**

## 1. Repozytorium

```text
repo: autoklinika/workshop-ventilation-controller
branch: agent/kamod-service-wifi-heartbeat-stage1
PR: #11, Draft
base main at stage start: 2ed28a8a5ba2e219493984732eca890ae0700cab
```

Nie wykonywać merge ani nie oznaczać PR jako Ready for Review bez wyraźnego polecenia użytkownika.

## 2. Stan architektury

- RS-485 Modbus RTU pozostaje jedynym kanałem produkcyjnym.
- Wi-Fi jest niezależnym kanałem serwisowym.
- AP `WVC-SERVICE` jest celowo otwarty, bez WPA2-PSK.
- Heartbeat pozostaje uwierzytelniony HMAC-SHA256 osobnym kluczem per node.
- KAmod wysyła UDP unicast do `10.55.0.1:45551` co około 10 s.
- Receiver jest osobnym procesem systemd i nie wpływa na `ventilation-core`.
- Węzły nie mają bramy, DNS, Internetu ani routingu do sieci warsztatowej.

## 3. Zwalidowane węzły

| Pole | sensor-node-1 | sensor-node-2 |
|---|---|---|
| Modbus slave | 1 | 2 |
| MAC | `88:13:BF:00:52:D0` | `88:13:BF:01:37:28` |
| DHCP | `10.55.0.106` | `10.55.0.110` |
| firmware | `0.4.0-stage1` | `0.4.0-stage1` |
| RSSI próbki | `-32 dBm` | `-57 dBm` |
| sensor state | `running` | `running` |
| RS-485 ready | `true` | `true` |
| błędy SEN55 | 0 | 0 |
| HMAC zaakceptowany | tak | tak |
| online | `true` | `true` |

CM5 zalogował:

```text
node=sensor-node-1 service heartbeat online
node=sensor-node-2 service heartbeat online
```

## 4. Incydenty wykryte podczas wdrożenia

### 4.1. WPA2

Wspólny PSK powodował problemy z zestawieniem połączenia. Na decyzję użytkownika usunięto obsługę hasła:

- firmware używa `WIFI_AUTH_OPEN`,
- provisioning nie pyta o PSK,
- NVS nie wymaga `wifi_psk`,
- installer CM5 usuwa legacy `802-11-wireless-security`,
- HMAC heartbeatów pozostaje bez zmian.

### 4.2. Fałszywy FAIL power saving

NetworkManager zwracał `disable` zamiast liczby `2`. Validator akceptuje oba zapisy.

### 4.3. Rejestr drugiego węzła

Po skopiowaniu rejestru z dwoma węzłami receiver nadal odrzucał `sensor-node-2` jako unknown node, ponieważ proces działał ze starą allowlistą w pamięci. Ręczny restart rozwiązał problem.

Installer zawsze restartuje teraz `wvc-service-heartbeat.service` po wymianie `keys.json`.

## 5. Checkpoint PASS

Potwierdzono sprzętowo:

- dwa fizyczne KAmod z osobnymi adresami Modbus,
- dwa fizyczne SEN55 w stanie `running`,
- otwarty AP i poprawne DHCP,
- dwa osobne klucze HMAC,
- dwa zaakceptowane strumienie heartbeat,
- poprawne `node_id`, MAC, slave, firmware, RSSI i liczniki,
- brak błędów SEN55 w obserwowanych próbkach.

Wynik: **dual-node service heartbeat bring-up PASS**.

## 6. Testy wymagane przed merge

1. Równoległy odczyt obu slave podczas wyłączenia i ponownego uruchomienia AP.
2. Restart DHCP i receivera podczas aktywnego Modbus.
3. Odłączenie RS-485 i kontrola pól aktywności Modbus w heartbeat.
4. Odłączenie SEN55 i kontrola diagnostyki Modbus oraz heartbeat.
5. Fałszywy HMAC i replay na docelowym CM5.
6. Potwierdzenie braku dostępu do SSH, Ethernetu i Internetu z `wlan0`.
7. Minimum 30 min soak testu dwóch węzłów z cyklicznym Modbus i heartbeat.

## 7. Następna sesja

Najpierw sprawdzić rzeczywisty HEAD gałęzi oraz status workflowów dla końcowego checkpointu. Następnie wykonać wyłącznie powyższy plan fault-injection/soak. Nie rozpoczynać OTA, zdalnego restartu ani zdalnego provisioningu.
