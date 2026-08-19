# AlertV2 Stage 4D — skorelowana utrata węzła, przygotowanie

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Draft PR:** #44  
**Status:** przygotowanie zakończone; rzeczywista walidacja CM5 zakończona PASS. Wynik: `docs/reports/ALERT_V2_STAGE4D_NODE_POWER_LOSS_CM5_VALIDATION_RESULT_PL.md`. Bez merge do `main`, bez produkcyjnego deploymentu AlertV2 i bez wykonywania `reaction` z TOML.

## 1. Cel

Stage 4D ma zweryfikować na rzeczywistym CM5 korelację dwóch niezależnych dowodów awarii tego samego węzła:

```text
service heartbeat KAmod = OFFLINE
+
production SENSOR BUS / Modbus tego samego węzła = OFFLINE
=
KAMOD_NODE_UNAVAILABLE
```

Oczekiwana polityka AlertV2:

```text
weight = 3
severity = alarm
hmi_color = orange
reaction = fallback_local
affects_control = true
control_policy_applied = false
```

`reaction=fallback_local` i `affects_control=true` są w Stage 4D wyłącznie metadanymi polityki. Shadow runtime nadal nie wykonuje reakcji sterującej.

## 2. Dlaczego fault injection jest fizyczny

Heartbeat jest kanałem IP/UDP i Stage 4C mógł bezpiecznie odizolować go pojedynczą regułą nftables. Produkcyjny SENSOR BUS jest natomiast fizycznym RS-485 Modbus RTU należącym do działającego `ventilation-core`.

Stage 4D celowo NIE próbuje:

- przejąć UART/RS-485 od produkcyjnego core,
- wstrzykiwać ramek Modbus,
- zatrzymywać workera SENSOR BUS,
- restartować core,
- zmieniać konfiguracji systemd,
- blokować portu szeregowego programowo.

Takie metody naruszałyby granicę produkcyjnego ownera sprzętu i wprowadzałyby dodatkową przyczynę awarii.

Dlatego fault injection polega na **ręcznym odłączeniu zasilania tylko jednego kompletnego węzła KAmod + SEN55**, a następnie jego ponownym zasileniu.

## 3. Krytyczny warunek przed uruchomieniem

Test wolno wykonać tylko wtedy, gdy target można odłączyć od zasilania **niezależnie** od:

- CM5,
- drugiego KAmod/SEN55,
- wspólnego konwertera/interfejsu RS-485,
- pozostałej infrastruktury SENSOR BUS.

Jeżeli fizyczna topologia zasilania lub okablowania powoduje, że odłączenie targetu może przerwać drugi węzeł albo całą magistralę, **Stage 4D nie może zostać uruchomiony w tej formie**. Najpierw trzeba zapewnić niezależne odłączanie testowanego węzła.

Validator wymaga jawnej flagi:

```text
--confirm-manual-power-cycle
```

Jest to potwierdzenie operatora, że powyższy warunek został sprawdzony.

## 4. Narzędzie

Dodano:

```text
tools/validate_alert_v2_stage4d_node_power_loss_cm5.py
```

Domyślny target:

```text
sensor-node-1 -> Modbus slave 1
```

Alternatywnie można wskazać `sensor-node-2`.

Narzędzie samo NIE wyłącza i NIE włącza zasilania. Zatrzymuje się w dwóch punktach i prosi operatora o:

1. fizyczne wyłączenie tylko targetu,
2. po potwierdzeniu korelacji — ponowne włączenie targetu.

## 5. Safety preflight

Przed pierwszym komunikatem o wyłączeniu zasilania validator wymaga:

```text
ventilation-core.service = active
wvc-service-agent.service = active
mode = STOP
supply = 0.0 V
extract = 0.0 V
output_state_known = true
SENSOR BUS worker = ready + alive
slave 1 = online + usable + valid
slave 2 = online + usable + valid
sensor-node-1 heartbeat = online
sensor-node-2 heartbeat = online
WVC-SERVICE AP/DHCP/firewall = healthy
mapowanie sensor-node-1 -> Modbus 1
mapowanie sensor-node-2 -> Modbus 2
```

Zapisywane są PID core i Service Agent oraz baseline liczników błędów nietestowanego slave.

Jeżeli docelowy `SENSOR_NODE_UNAVAILABLE` jest już aktywny przed testem, validator odmawia rozpoczęcia fault injection.

## 6. Faza A — produkcyjny dowód Modbus

Po ręcznym wyłączeniu targetu produkcyjny `ventilation-core` powinien zgodnie z istniejącym Stage 1 wykryć:

```text
SENSOR_NODE_UNAVAILABLE
key = sensor-node:<adres>:communication
source = sensor:<adres>
```

Obecny detector wymaga co najmniej trzech kolejnych nieudanych prób komunikacji przed aktywacją tego alertu.

Validator potwierdza, że:

- alert naprawdę pochodzi z produkcyjnego core,
- target osiągnął wymagany debounce,
- core pozostał `STOP / 0 V / 0 V`,
- PID core nie zmienił się,
- PID Service Agent nie zmienił się,
- nietestowany slave pozostaje online/usable/valid,
- jego liczniki błędów nie wzrastają,
- nietestowany heartbeat pozostaje online.

## 7. Faza B — korelacja dwóch kanałów

Service Agent uznaje heartbeat za offline po swoim zwalidowanym progu około 35 s.

Gdy jednocześnie istnieją:

```text
SENSOR_NODE_UNAVAILABLE dla sensor:<adres>
heartbeat targetu = OFFLINE
```

prawdziwy Stage 3 correlator w shadow runtime ma:

1. stłumić legacy symptom tylko w projekcji shadow:

```text
sensor-node:<adres>:communication
```

2. utworzyć jeden bardziej przyczynowy alert:

```text
KAMOD_NODE_UNAVAILABLE
key = sensor-node:<adres>:correlated-unavailable
```

3. opublikować:

```text
correlation.derived_codes = ["KAMOD_NODE_UNAVAILABLE"]
correlation.suppressed_legacy_keys zawiera sensor-node:<adres>:communication
control_policy_applied = false
```

4. zmapować alert przez TOML na:

```text
weight = 3
hmi_color = orange
reaction = fallback_local
affects_control = true
```

Ważne: stłumienie legacy alertu odbywa się tylko w read-only projekcji AlertV2. Produkcyjny Stage 1 nadal jest właścicielem swojego rzeczywistego incydentu.

## 8. Recovery

Po potwierdzeniu `KAMOD_NODE_UNAVAILABLE` validator prosi operatora o przywrócenie zasilania targetu.

Pełny PASS recovery wymaga jednocześnie:

```text
target Modbus online = true
target usable = true
target measurement_valid = true
target measurement_stale = false
target consecutive_failures = 0
target heartbeat online = true
production SENSOR_NODE_UNAVAILABLE = cleared
KAMOD_NODE_UNAVAILABLE = nieaktywny
przejściowy KAMOD_HEARTBEAT_LOST = nieaktywny
non-target nadal healthy
core PID bez zmiany
Service Agent PID bez zmiany
STOP / 0 V / 0 V
```

W recovery dopuszczalna jest naturalna kolejność powrotu kanałów. Przykładowo Modbus może odzyskać komunikację przed kolejnym 10-sekundowym heartbeat. Validator ocenia dopiero stan końcowy.

## 9. Świadomy ślad w produkcyjnej historii alertów

Stage 4D różni się od Stage 4B/4C tym, że fizyczne wyłączenie węzła wywoła **rzeczywisty produkcyjny Alert Stage 1**:

```text
SENSOR_NODE_UNAVAILABLE
```

Incydent zostanie zapisany przez produkcyjny core w:

```text
/var/lib/workshop-ventilation/alerts.sqlite3
```

Po odzyskaniu węzła alert ma przejść do `CLEARED`, ale **pozostanie w historii**. To jest oczekiwany i celowy ślad walidacji sprzętowej. Validator:

- nie usuwa tego rekordu,
- nie edytuje bazy,
- nie wykonuje ACK,
- po recovery wymaga znalezienia odpowiadającego rekordu jako `active=false` z ustawionym `cleared_at`.

## 10. Brak automatycznego cleanup fizycznego faultu

W Stage 4C program mógł usunąć tymczasową regułę nftables w `finally`. W Stage 4D nie jest to możliwe, ponieważ fault jest fizycznym odłączeniem zasilania.

Jeżeli test zostanie przerwany lub zakończy się błędem po wyłączeniu targetu, validator wypisuje:

```text
ACTION REQUIRED FOR RECOVERY
```

Operator musi wtedy ręcznie upewnić się, że zasilanie targetu zostało przywrócone, a następnie sprawdzić oba węzły oraz stan core.

Narzędzie nie może i nie będzie twierdzić, że automatycznie przywróciło fizyczne zasilanie.

## 11. Granice bezpieczeństwa Stage 4D

Validator korzysta z istniejącego `CoreReadOnlyClient`, którego allowlista obejmuje wyłącznie:

```text
status
alerts
```

Stage 4D:

- nie wysyła `set`, `stop` ani `shutdown`,
- nie używa nftables,
- nie restartuje żadnej usługi,
- nie zatrzymuje SENSOR BUS,
- nie posiada DAC/UART/GPIO,
- nie steruje AERO ani Zigbee,
- nie otwiera produkcyjnej bazy alertów bezpośrednio,
- nie wykonuje `reaction` z TOML,
- utrzymuje `write_commands_sent=0`,
- utrzymuje `control_policy_applied=false`.

## 12. Testy automatyczne

Dodano:

```text
tests/test_alert_v2_stage4d_node_power_loss.py
```

Testy kontraktu sprawdzają m.in.:

- obowiązkową flagę świadomego manualnego power-cycle,
- dwa jawne punkty interakcji POWER OFF / RESTORE POWER,
- oczekiwane `SENSOR_NODE_UNAVAILABLE -> KAMOD_NODE_UNAVAILABLE`,
- wagę 3 / pomarańczowy / `fallback_local`,
- read-only `control_policy_applied=false`,
- brak poleceń sterowania i software fault injection,
- ochronę nietestowanego węzła,
- jawne zachowanie rekordu `CLEARED` w produkcyjnej historii,
- komunikat ręcznego recovery w `finally`.

## 13. Kryterium PASS

Stage 4D został sprzętowo zaliczony na rzeczywistym CM5. Szczegółowy wynik zapisano w:

```text
docs/reports/ALERT_V2_STAGE4D_NODE_POWER_LOSS_CM5_VALIDATION_RESULT_PL.md
```

Potwierdzono:

```text
production SENSOR_NODE_UNAVAILABLE = ACTIVE
+
target heartbeat = OFFLINE
-> shadow KAMOD_NODE_UNAVAILABLE
   weight 3 / orange / fallback_local
   control_policy_applied=false

następnie po przywróceniu zasilania:
production SENSOR_NODE_UNAVAILABLE = CLEARED
KAMOD_NODE_UNAVAILABLE = CLEARED
target Modbus = healthy
target heartbeat = online
non-target = healthy
core/service-agent PID unchanged
STOP / 0 V / 0 V
write_commands_sent = 0
```

**Status Stage 4D: PASS — HARDWARE VALIDATED.**
