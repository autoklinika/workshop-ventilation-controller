# AlertV2 — heartbeat KAmod jako telemetria serwisowa

**Data decyzji:** 2026-08-21  
**Zakres:** korelacja `SENSOR BUS / Modbus` z heartbeat `WVC-SERVICE`  
**Status:** zmiana polityki runtime na gałęzi roboczej; bez wpływu na sterowanie

## Cel

Heartbeat KAmod pozostaje mechanizmem service-plane używanym do diagnostyki, obserwacji dostępności węzła, wersji firmware, RSSI i operacji OTA. Nie jest jednak produkcyjnym źródłem prawdy o zdolności wentylacji do pracy.

Produkcyjnym źródłem prawdy dla węzła KAmod/SEN55 pozostaje ścieżka `CM5 -> RS-485 / Modbus -> KAmod -> SEN55`.

## Obowiązująca macierz

| SENSOR BUS / Modbus | Heartbeat WVC-SERVICE | Znaczenie | Alert operatora |
|---|---|---|---|
| działa | brak | wentylacja i produkcyjny tor pomiarowy są zdrowe; service Wi-Fi jest niedostępne lub traci pakiety | **brak alertu heartbeat**; stan pozostaje w diagnostyce serwisowej |
| nie działa | działa | problem produkcyjnego SENSOR BUS / RS-485 przy dostępnym kanale diagnostycznym | alert produkcyjny SENSOR BUS, ewentualnie dokładniejszy alert korelacyjny na podstawie diagnostyki KAmod |
| nie działa | brak | niezależne ścieżki jednocześnie wskazują niedostępność węzła | `KAMOD_NODE_UNAVAILABLE` |
| działa | działa | stan prawidłowy | brak alertu |

## Zasady implementacyjne

1. Sam brak heartbeat nie emituje już `KAMOD_HEARTBEAT_LOST` do `AlertRegistry`.
2. Offline heartbeat przy zdrowym produkcyjnym SENSOR BUS jest zapisywany wyłącznie w diagnostyce korelatora jako `service_only_offline_nodes`.
3. Jeżeli produkcyjny SENSOR BUS zgłasza awarię tego samego adresu Modbus i heartbeat jest offline, ogólny alert produkcyjny jest korelowany do `KAMOD_NODE_UNAVAILABLE`.
4. Jeżeli SENSOR BUS zgłasza awarię, ale heartbeat działa, istniejące informacje `sensor_state` i `rs485_ready` mogą nadal doprecyzować przyczynę (`KAMOD_SENSOR_STATE_ERROR`, `KAMOD_RS485_NOT_READY`). W przeciwnym razie pozostaje zwykły alert produkcyjny.
5. `KAMOD_HEARTBEAT_LOST` pozostaje w enumie/modelu i polityce dla zgodności wstecznej z historią oraz starymi zapisami. Runtime nie generuje nowego operatorowego alertu tego typu przy zdrowym SENSOR BUS.
6. Po wdrożeniu nowej logiki wcześniej aktywny, historyczny `KAMOD_HEARTBEAT_LOST` zostanie automatycznie wyczyszczony przez normalny lifecycle `AlertRegistry.reconcile()`.
7. Zmiana nie uruchamia żadnej reakcji sterującej. `control_policy_applied` pozostaje `false`.

## Poza zakresem

Ta decyzja nie usuwa service-plane ani heartbeat z firmware i nie zmienia:

- okresu heartbeat,
- timeoutu Service Agent,
- HMAC/protokołu WVC-HB1,
- OTA,
- produkcyjnego Modbus/RS-485,
- SEN55,
- automatyki wentylacji,
- alertów infrastrukturalnych samego CM5 Service Agent / WVC-SERVICE.

Diagnostyczny PR dotyczący jakości transportu Wi-Fi może pozostać osobnym eksperymentem. Nie jest warunkiem poprawnego działania produkcyjnych alertów wentylacji.
