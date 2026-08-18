# AlertV2 — Service Plane Correlation Stage 3

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Draft PR:** #44  
**Baza:** `main` `0f156cc6fe6e7d64df82a7a748108a93783c5fb7`

## 1. Cel etapu

Wprowadzić do AlertV2 pierwszą rzeczywistą korelację dwóch niezależnych źródeł diagnostycznych:

1. produkcyjnego `SENSOR BUS` / Modbus RTU widzianego przez `ventilation-core`,
2. niezależnego `WVC-SERVICE` / heartbeat KAmod widzianego przez `wvc-service-agent`.

Stage 3 nadal jest **diagnostic/read-only względem sterowania**:

- nie wykonuje `reaction` z TOML,
- nie zmienia napięć DAC,
- nie zatrzymuje wentylatorów,
- nie steruje AERO,
- nie zmienia automatyki,
- nie używa Service Agent jako kanału produkcyjnego.

Alert Registry pozostaje właścicielem lifecycle, ACK, SQLite i historii.

## 2. Lokalny monitor Service Agent

Dodano:

```text
src/ventilation_core/service_plane_monitor.py
```

Core wykonuje wyłącznie lokalny, ograniczony czasowo odczyt:

```text
/run/wvc-service-agent/service-agent.sock
command=status
```

Domyślny timeout wynosi `0.35 s`.

Monitor:

- używa tylko `AF_UNIX`,
- wysyła tylko read-only `status`,
- ma limit wielkości odpowiedzi 256 KiB,
- nie wykonuje OTA,
- nie zapisuje niczego do Service Agent,
- nie otwiera Wi-Fi ani UDP bezpośrednio,
- przechowuje ostatni poprawny snapshot wyłącznie diagnostycznie,
- liczy kolejne błędy odczytu.

## 3. Correlating Alert Registry

Dodano:

```text
src/ventilation_core/application/service_plane_alert_registry.py
```

`ServicePlaneCorrelatingAlertRegistry` opakowuje istniejący `AlertRegistry`.

Ważna własność architektury: istniejący `AlertingVentilationService` nadal generuje swoje dotychczasowe sygnały. Dopiero przed `AlertRegistry.reconcile()` warstwa korelacji może zastąpić ogólny objaw bardziej precyzyjnym skorelowanym alertem.

Nie zmieniono mechanizmu trwałości SQLite, ACK ani historii.

## 4. Zaimplementowane reguły korelacji

### 4.1 SENSOR BUS fail + heartbeat KAmod fail

Jeżeli dla tego samego adresu Modbus:

```text
SENSOR_NODE_UNAVAILABLE lub SENSOR_DATA_INVALID
+
KAmod online=false
+
WVC-SERVICE jest zdrowe
```

wtedy ogólny objaw produkcyjny jest zastępowany przez:

```text
KAMOD_NODE_UNAVAILABLE
```

Przykład:

```text
sensor-node:1:communication  -> suppressed
KAMOD_NODE_UNAVAILABLE      -> ACTIVE
```

Operator dostaje jeden skorelowany komunikat zamiast dwóch niezależnych alarmów o tej samej awarii.

### 4.2 Heartbeat fail + produkcyjny SENSOR BUS działa

Jeżeli:

```text
KAmod online=false
+
brak produkcyjnego błędu tego węzła
```

powstaje:

```text
KAMOD_HEARTBEAT_LOST
```

Jest to wyłącznie awaria/degradacja kanału serwisowego. Produkcyjny Modbus pozostaje niezależny.

### 4.3 Produkcyjny problem + KAmod online + `sensor_state=offline`

Jeżeli heartbeat jest dostępny i KAmod jawnie raportuje:

```text
sensor_state=offline
```

oraz produkcyjny SENSOR BUS równocześnie raportuje problem, ogólny objaw zostaje zastąpiony przez:

```text
KAMOD_SENSOR_STATE_ERROR
```

To daje silniejsze wskazanie, że problem znajduje się lokalnie przy SEN55 / węźle KAmod, a nie w samym CM5.

### 4.4 Produkcyjny problem + KAmod online + `rs485_ready=false`

Jeżeli niezależny heartbeat działa, ale KAmod jawnie raportuje:

```text
rs485_ready=false
```

oraz produkcyjny tor także raportuje problem, powstaje:

```text
KAMOD_RS485_NOT_READY
```

Ogólny `SENSOR_NODE_UNAVAILABLE`/`SENSOR_DATA_INVALID` dla tego samego węzła jest wtedy tłumiony jako objaw wtórny.

### 4.5 Produkcyjny problem + zdrowy heartbeat + `sensor_state=running` + `rs485_ready=true`

W tej sytuacji korelator **nie wymyśla przyczyny**.

Pozostaje dotychczasowy:

```text
SENSOR_NODE_UNAVAILABLE
```

ponieważ dane nie pozwalają jeszcze uczciwie stwierdzić, gdzie leży przyczyna.

## 5. Korelacja jest zawieszana przy awarii samego WVC-SERVICE

To jest ważna ochrona przed fałszywą diagnozą.

Jeżeli Service Agent raportuje problem z:

- AP/adresem `10.55.0.1`,
- DHCP,
- firewallem,

core nie interpretuje brakujących heartbeatów jako awarii KAmod.

Wtedy generowane są odpowiednio:

```text
SERVICE_NETWORK_AP_UNAVAILABLE
SERVICE_NETWORK_DHCP_UNAVAILABLE
SERVICE_NETWORK_FIREWALL_INVALID
```

a produkcyjne alerty SENSOR BUS pozostają niezależne.

Czyli awaria samej sieci serwisowej nie może stworzyć fałszywego `KAMOD_NODE_UNAVAILABLE`.

## 6. Niedostępny Service Agent

Brak odpowiedzi Service Agent jest debouncowany.

Domyślnie dopiero po:

```text
3 kolejnych błędach
```

powstaje:

```text
SERVICE_AGENT_UNAVAILABLE
```

Jednocześnie istniejące alerty produkcyjne nie są tłumione ani reinterpretowane, ponieważ korelator nie ma wtedy wiarygodnego drugiego źródła danych.

## 7. Grace period po starcie Service Agent

Service Agent rejestruje znane węzły początkowo jako `offline`, zanim przyjdzie pierwszy heartbeat.

Aby nie wygenerować fałszywego alarmu przy starcie, dla węzła, który jeszcze nigdy nie dostarczył heartbeat, obowiązuje domyślnie:

```text
40 s initial grace
```

Jest to celowo nieco więcej niż produkcyjne `stale-after=35 s` używane przez Service Agent.

Jeżeli węzeł wcześniej dostarczył heartbeat (`received_unix_ms` istnieje), jego późniejsze `online=false` jest traktowane jako rzeczywisty stan offline bez dodatkowego 40 s oczekiwania — ponieważ debounce 35 s został już wykonany przez Service Agent.

## 8. Nowe AlarmCode

Do domeny dodano kody istniejące już w macierzy AlertV2:

```text
KAMOD_HEARTBEAT_SINGLE_GAP
KAMOD_HEARTBEAT_DEGRADED
KAMOD_HEARTBEAT_LOST
KAMOD_UNEXPECTED_RESTART
KAMOD_RS485_NOT_READY
KAMOD_SENSOR_STATE_ERROR
KAMOD_NODE_UNAVAILABLE
SERVICE_AGENT_UNAVAILABLE
SERVICE_NETWORK_AP_UNAVAILABLE
SERVICE_NETWORK_DHCP_UNAVAILABLE
SERVICE_NETWORK_FIREWALL_INVALID
```

Stage 3 aktywnie wykorzystuje podzbiór wymagany do podstawowej korelacji. `SINGLE_GAP`, `DEGRADED` i `UNEXPECTED_RESTART` pozostają przygotowane w kontrakcie, ale nie są jeszcze aktywowane na podstawie historycznych liczników transportowych, aby nie stworzyć nieustającego alertu z kumulatywnego countera.

## 9. Integracja z runtime core

`ventilation-core` otrzymał parametry:

```text
--service-agent-socket /run/wvc-service-agent/service-agent.sock
--service-agent-timeout 0.35
--service-agent-failure-threshold 3
--service-node-initial-grace 40
--disable-service-plane-correlation
```

Ostatnia flaga jest prostą granicą rollbacku: można wyłączyć cały Stage 3 bez zmiany istniejącego Alert Stage 1.

Nie dodano zależności systemd `Requires=` ani `After=` na `wvc-service-agent.service`. Core pozostaje autonomiczny. Brak Service Agent powoduje tylko alert diagnostyczny po debounce.

## 10. Projekcja diagnostyczna

`state.alert_v2.service_plane` publikuje wyłącznie zsanityzowany stan potrzebny do diagnostyki AlertV2 i wynik ostatniej korelacji, m.in.:

```text
mode=read_only
reason=correlation_complete
derived_codes=[...]
suppressed_legacy_keys=[...]
control_policy_applied=false
```

Do publicznej projekcji nie są przekazywane surowe heartbeat payloady, MAC, `source_ip` ani wewnętrzne struktury `transport`. Dla węzłów publikowane są tylko pola potrzebne do diagnostyki: `node_id`, `online`, czas ostatniego odbioru, adres Modbus, `sensor_state`, `rs485_ready` i `modbus_monitor_ready`.

GUI nie wykonuje żadnej klasyfikacji. Wszystkie decyzje korelacyjne powstają po stronie core.

## 11. Niezmienniki bezpieczeństwa

Stage 3 zachowuje:

- `control_policy_applied=false`,
- brak wykonania `reaction` z TOML,
- brak wpływu awarii Service Agent na DAC,
- brak wpływu awarii WVC-SERVICE na produkcyjny Modbus,
- brak wpływu TACHO na globalny STOP,
- brak zmian w ręcznym sterowaniu wentylatorami,
- brak zmian w AERO,
- brak zmian w Zigbee,
- brak zmian w SHADOW actuation (`actuation_supported=false`).

## 12. Testy

Dodano:

```text
tests/test_alert_v2_service_plane_correlation.py
```

Pokryte przypadki:

1. Modbus fail + heartbeat fail -> jeden `KAMOD_NODE_UNAVAILABLE`,
2. heartbeat fail + zdrowa produkcja -> `KAMOD_HEARTBEAT_LOST`,
3. awaria WVC-SERVICE blokuje fałszywą korelację node-level,
4. `sensor_state=offline` + produkcyjny problem -> `KAMOD_SENSOR_STATE_ERROR`,
5. `rs485_ready=false` + produkcyjny problem -> `KAMOD_RS485_NOT_READY`,
6. zdrowy service snapshot nie ukrywa niewyjaśnionego błędu Modbus,
7. initial grace przed pierwszym heartbeat,
8. debounce niedostępności Service Agent,
9. sanitizacja publicznej projekcji Service Plane,
10. TACHO przechodzi przez korelator bez zmiany reakcji sterującej.

GitHub Actions po finalnym hardeningu Stage 3:

```text
Ventilation Core Tests #1547
compileall: PASS
391 tests: PASS
```

## 13. Stan po Stage 3

Gotowe:

- edytowalna macierz AlertV2,
- validator + CLI,
- read-only runtime policy mapping,
- policy version + SHA-256,
- lokalny read-only monitor Service Agent,
- trwałe alerty Service Plane poprzez istniejący Alert Registry,
- podstawowa korelacja Service Agent ↔ SENSOR BUS,
- tłumienie wtórnego objawu, gdy przyczyna jest wystarczająco potwierdzona,
- ochrona przed fałszywą korelacją przy awarii samego WVC-SERVICE,
- zsanityzowana projekcja diagnostyczna dla klientów core.

Niezaimplementowane nadal:

- wykonywanie `reaction` z TOML,
- operational TACHO `FAN_NO_ROTATION_FEEDBACK`,
- `KAMOD_HEARTBEAT_SINGLE_GAP`, `KAMOD_HEARTBEAT_DEGRADED`, `KAMOD_UNEXPECTED_RESTART` jako aktywne detektory eventowe,
- korelacja AERO command/readback na poziomie AlertV2,
- alerty core process restart/system health,
- fizyczne sterowanie kolorem paska RGB HMI z najwyższej aktywnej wagi,
- produkcyjny deployment Stage 3 na CM5.

## 14. Następny zalecany etap

Przed dalszym rozszerzaniem detektorów należy wykonać **hardware/runtime validation Stage 3 na CM5** w osobnym worktree i bez merge do `main`:

1. sprawdzić odczyt rzeczywistego `/run/wvc-service-agent/service-agent.sock`,
2. potwierdzić mapowanie `sensor-node-1/2` ↔ Modbus 1/2,
3. sprawdzić brak dodatkowego opóźnienia API/core,
4. zasymulować wyłącznie service heartbeat dropout przy działającym Modbus,
5. zasymulować jednoczesny dropout heartbeat + Modbus,
6. potwierdzić, że DAC/setpoints nie zmieniają się w żadnym teście Stage 3,
7. zakończyć test w STOP / 0 V.
