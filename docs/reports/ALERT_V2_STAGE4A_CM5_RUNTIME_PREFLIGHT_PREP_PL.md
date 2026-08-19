# AlertV2 — Stage 4A CM5 Runtime Preflight — przygotowanie

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Draft PR:** #44  
**Baza:** `main` `0f156cc6fe6e7d64df82a7a748108a93783c5fb7`

## 1. Cel

Stage 4A jest pierwszą walidacją na rzeczywistym CM5 po implementacji korelacji AlertV2 Service Agent ↔ SENSOR BUS.

Ten podetap jest celowo **wyłącznie pasywny**. Nie uruchamia jeszcze testowego `ventilation-core`, nie przełącza produkcyjnych usług i nie wykonuje fault injection.

Ma odpowiedzieć na cztery pytania przed jakąkolwiek zmianą runtime:

1. czy gałąź AlertV2 potrafi poprawnie czytać rzeczywisty `/run/wvc-service-agent/service-agent.sock`,
2. czy rzeczywiste mapowanie jest dokładnie `sensor-node-1 -> Modbus 1` i `sensor-node-2 -> Modbus 2`,
3. czy produkcyjny SENSOR BUS widzi dokładnie adresy 1 i 2 jako `online+usable`,
4. czy read-only odczyty Service Plane nie zmieniają stanu wyjść i nie powodują fałszywych alertów korelatora przy zdrowym systemie.

## 2. Narzędzie walidacyjne

Dodano:

```text
tools/validate_alert_v2_stage4a_preflight.py
```

Narzędzie korzysta z kodu gałęzi AlertV2, ale komunikuje się z działającym produkcyjnym runtime wyłącznie przez lokalne Unix sockety.

Do `ventilation-core` dopuszcza tylko:

```json
{"command":"status"}
{"command":"sensors"}
```

Do Service Agent wysyłany jest tylko:

```json
{"command":"status"}
```

Narzędzie nie zawiera ścieżki do:

- `set`,
- `stop`,
- `shutdown`,
- ACK alertów,
- sterowania AERO,
- zmian harmonogramu,
- zmian Zigbee,
- OTA,
- edycji konfiguracji.

## 3. Warunek bezpieczeństwa przed startem

Stage 4A nie próbuje samodzielnie zatrzymywać systemu. Zamiast tego wymaga, aby produkcyjny core już znajdował się w:

```text
mode = STOP
supply_voltage = 0.0 V
extract_voltage = 0.0 V
output_state_known = true
```

Jeżeli którykolwiek z tych warunków nie jest spełniony, test kończy się `FAIL` bez wysyłania polecenia sterującego.

To chroni przed sytuacją, w której narzędzie walidacyjne samo stałoby się źródłem aktuacji.

## 4. Walidacja rzeczywistego mapowania

Service Agent musi zwrócić dokładnie:

```text
sensor-node-1 -> modbus_address 1
sensor-node-2 -> modbus_address 2
```

Oba węzły muszą jednocześnie raportować:

```text
online = true
rs485_ready = true
modbus_monitor_ready = true
```

Produkcja musi równolegle zwrócić SENSOR BUS:

```text
slave 1 -> online + usable
slave 2 -> online + usable
```

Nie dopuszczamy automatycznego dopasowania „po kolejności listy”. Korelacja ma być oparta o jawny adres Modbus.

## 5. Live dry-run korelatora

Stage 4A tworzy w pamięci:

```text
ServicePlaneMonitor
+
ServicePlaneCorrelatingAlertRegistry
+
MemoryAlertStore
```

i wykonuje jeden rzeczywisty odczyt lokalnego Service Agent.

Przy zdrowym runtime oczekujemy:

```text
derived_codes = []
control_policy_applied = false
```

Żaden testowy rekord nie jest zapisywany do produkcyjnego `alerts.sqlite3`.

## 6. Pomiar latencji

Domyślnie wykonywane jest 30 próbek:

```text
core status
service agent status
```

z przerwą `0.25 s`.

Raport zawiera osobno:

```text
mean
p50
p95
max
```

dla obu lokalnych socketów.

Na Stage 4A nie wprowadzamy arbitralnego nowego progu PASS/FAIL dla latencji core. Celem jest zebranie rzeczywistego baseline przed uruchomieniem gałęzi AlertV2 jako testowego runtime. Twardy timeout Service Agent pozostaje `0.35 s`, zgodnie z implementacją Stage 3.

## 7. Ochrona stanu wyjść podczas testu

Każda próbka `status` ponownie sprawdza:

```text
STOP / 0 V / 0 V
```

oraz na końcu wykonywana jest ponowna kontrola stanu i SENSOR BUS.

Jeżeli stan wyjść zmieni się w trakcie testu, Stage 4A natychmiast kończy się `FAIL`.

Narzędzie samo nie wysyła żadnego polecenia przywracającego — jest obserwatorem, nie sterownikiem.

## 8. Test kontraktu narzędzia

Dodano:

```text
tests/test_alert_v2_stage4a_preflight_tool.py
```

Test CI sprawdza m.in.:

- poprawność składni Python,
- allowlistę tylko `status` / `sensors`,
- brak komend aktuacji i konfiguracji,
- wymóg `STOP / 0 V`,
- wymóg `output_state_known=true`,
- dokładne mapowanie node 1/2 ↔ Modbus 1/2,
- użycie rzeczywistego `ServicePlaneCorrelatingAlertRegistry`,
- zachowanie `control_policy_applied=false`,
- ograniczone czasowo lokalne odczyty socketów.

## 9. Plan uruchomienia na CM5

Nie uruchamiać z głównego katalogu produkcyjnego repo.

Docelowo przygotować osobny worktree, np.:

```text
/home/wentylacja/wvc-alert-v2-stage4
```

z gałęzi:

```text
agent/core-alert-v2-design-stage1
```

Produkcja pozostaje na swoim aktualnym kodzie i usługach.

Po ręcznym potwierdzeniu STOP / 0 V uruchomienie będzie miało postać:

```bash
cd /home/wentylacja/wvc-alert-v2-stage4
PYTHONPATH=src python3 tools/validate_alert_v2_stage4a_preflight.py
```

Nie używamy `set -e` w interaktywnym bloku terminala.

## 10. Kryteria PASS Stage 4A

Stage 4A jest PASS tylko jeżeli:

1. oba lokalne sockety odpowiadają,
2. Service Agent i jego sieć raportują stan gotowy,
3. oba KAmod są online,
4. mapowanie wynosi dokładnie `sensor-node-1 -> 1`, `sensor-node-2 -> 2`,
5. SENSOR BUS ma dokładnie slave 1 i 2 `online+usable`,
6. live dry-run korelatora nie tworzy żadnego alertu przy zdrowym systemie,
7. `control_policy_applied=false`,
8. przez cały test core pozostaje `STOP / 0 V / 0 V`,
9. narzędzie wysyła 0 poleceń zapisu/aktuacji.

## 11. Czego Stage 4A jeszcze nie robi

Stage 4A celowo nie obejmuje:

- uruchomienia testowego core z gałęzi AlertV2,
- podmiany `ventilation-core.service`,
- zatrzymywania `wvc-service-agent`,
- blokowania heartbeat KAmod,
- odłączania SENSOR BUS,
- symulacji Modbus timeout,
- równoczesnego dropout heartbeat + Modbus,
- wykonywania `reaction` z TOML,
- sterowania RGB HMI.

Te działania należą do kolejnych, osobno zatwierdzanych podetapów Stage 4B/4C.

## 12. Następny krok po PASS

Dopiero po PASS Stage 4A przygotować **Stage 4B — testowy runtime AlertV2 w osobnym środowisku**, nadal bez merge i bez wykonywania reakcji TOML.

Stage 4B powinien najpierw porównać latencję i stan core bez fault injection. Dopiero osobny Stage 4C może wprowadzić kontrolowany heartbeat-only dropout, a następnie skorelowany heartbeat + SENSOR BUS dropout.
