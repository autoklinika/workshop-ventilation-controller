# AlertV2 Runtime Policy — Stage 2

**Data:** 2026-08-19  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Draft PR:** #44  
**Baza:** `main` `0f156cc6fe6e7d64df82a7a748108a93783c5fb7`

## 1. Cel etapu

Włączyć zwalidowaną politykę `alerts-v2.toml` do runtime `ventilation-core` **wyłącznie w trybie read-only mapping**.

Etap NIE wykonuje jeszcze pola `reaction`, nie zmienia logiki sterowania, nie zmienia zachowania DAC, TACHO, SENSOR BUS, AERO, Zigbee ani automatyki. Jego zadaniem jest:

- załadowanie i zwalidowanie polityki przy starcie core,
- zachowanie last-known-good po nieudanej próbie przeładowania,
- publikacja `policy_version` i SHA-256,
- mapowanie istniejących alertów Stage 1 do metadanych AlertV2,
- wyliczenie najwyższej aktywnej wagi i docelowego koloru HMI,
- zachowanie legacy pól alertów dla kompatybilności.

## 2. Runtime manager

Dodano:

```text
src/ventilation_core/alert_policy_runtime.py
```

`RuntimeAlertPolicyManager`:

1. czyta wskazany plik TOML,
2. korzysta z wcześniej zaimplementowanego pełnego validatora,
3. przyjmuje nową politykę dopiero po pełnym PASS,
4. przy błędzie I/O lub walidacji zachowuje poprzednią poprawną politykę,
5. publikuje metadane diagnostyczne:
   - `runtime_mode = read_only_mapping`,
   - `loaded`,
   - `policy_version`,
   - `sha256`,
   - `alert_count`,
   - `source_path`,
   - `loaded_at`,
   - `last_attempt_at`,
   - `last_error`,
   - `control_policy_applied = false`.

Brak lub błędny plik przy pierwszym starcie jest jawnie raportowany, ale w tym etapie nie zatrzymuje core, ponieważ polityka nie ma jeszcze prawa sterować sprzętem. Legacy Alert Stage 1 działa wtedy bez zmian.

## 3. Read-only service decorator

Dodano:

```text
src/ventilation_core/application/alert_v2_policy_service.py
```

`AlertV2ReadOnlyPolicyService` opakowuje istniejący serwis i deleguje wszystkie metody sterujące bez zmian.

Dekorowane są wyłącznie wyniki odczytu:

- `state()`,
- `active_alerts()`,
- `alert_history()`,
- `acknowledge_alert()`.

Nie ma żadnego wywołania kodu wykonującego `reaction` z TOML.

## 4. Kontrakt pojedynczego alertu

Legacy pola pozostają bez zmian. Przykład: obecny Stage 1 może nadal zwrócić:

```json
{
  "code": "AERO_BUS_UNAVAILABLE",
  "severity": "warning",
  "message": "..."
}
```

Stage 2 dodaje obok zagnieżdżony opis:

```json
{
  "alert_v2": {
    "mapped": true,
    "policy_version": "2026-08-18.1",
    "enabled": true,
    "weight": 3,
    "severity": "alarm",
    "reaction": "fallback_local",
    "scope": "aero",
    "affects_control": true,
    "hmi_color": "orange",
    "category": "aero",
    "correlation_group": "aero_health",
    "correlation_priority": 90,
    "title": "Rekuperator AERO niedostępny"
  }
}
```

W tym etapie `affects_control` i `reaction` są wyłącznie metadanymi kontraktu. Pole:

```text
control_policy_applied = false
```

jest publikowane jawnie, żeby nie było wątpliwości, że polityka TOML nie steruje jeszcze urządzeniami.

## 5. Projekcja stanu dla HMI

`state.to_dict()` otrzymuje sekcję:

```json
{
  "alert_v2": {
    "runtime_mode": "read_only_mapping",
    "loaded": true,
    "policy_version": "2026-08-18.1",
    "sha256": "...",
    "alert_count": 49,
    "control_policy_applied": false,
    "active_weight": 3,
    "hmi_color": "orange",
    "mapped_active_alerts": 1,
    "disabled_active_alerts": 0,
    "unmapped_active_alerts": 0
  }
}
```

Reguły:

- najwyższa aktywna waga wygrywa,
- brak aktywnych alertów przy poprawnie załadowanej polityce daje `weight=0 / green`,
- ACK nie zmniejsza wagi i nie zmienia koloru,
- wpis `enabled=false` pozostaje widoczny w legacy liście, ale nie zwiększa docelowej wagi V2,
- alert bez wpisu w polityce jest liczony jako `unmapped_active_alerts` i nie jest ukrywany.

Lokalny watchdog HMI ↔ CM5 pozostaje osobnym mechanizmem nadrzędnym przy utracie komunikacji.

## 6. Integracja z core

`src/ventilation_core/main.py` otrzymał argument:

```text
--alert-policy /etc/workshop-ventilation/alerts-v2.toml
```

Ścieżka domyślna pochodzi z kontraktu AlertV2.

Po utworzeniu istniejącego `ShadowAlertingVentilationService` core tworzy `RuntimeAlertPolicyManager` oraz read-only decorator. Dopiero udekorowany serwis jest przekazywany do istniejącego `CoreServer`.

Nie zmieniono protokołu sterowania ani implementacji `CoreServer`.

## 7. Bezpieczeństwo

W Stage 2 zachowane są następujące granice:

- TOML nie wykonuje reakcji sterujących,
- TACHO nadal nie może zatrzymać wentylacji,
- kontrola DAC pozostaje wyłącznie w dotychczasowej zwalidowanej logice,
- błędny plik polityki nie nadpisuje last-known-good,
- brak polityki nie blokuje legacy Alert Stage 1,
- nie ma endpointu GUI/HMI do edycji polityki,
- nie ma automatycznego reloadu po zmianie pliku,
- nie ma runtime API do zmiany wag, reakcji lub progów.

## 8. Testy

Dodano `tests/test_alert_v2_runtime_policy.py`.

Testy obejmują:

- poprawne załadowanie policy version i SHA-256,
- jawny `control_policy_applied=false`,
- last-known-good po błędnym reloadzie,
- niekrytyczny brak pliku podczas pierwszego odczytu Stage 2,
- wzbogacenie istniejącego alertu Stage 1 bez nadpisania jego legacy pól,
- obliczanie najwyższej aktywnej wagi i koloru HMI,
- brak zmiany koloru po ACK,
- delegację sterowania bez wykonania `reaction`.

GitHub Actions po implementacji:

```text
Ventilation Core Tests #1527
compileall: PASS
381 tests: PASS
```

## 9. Stan po Stage 2

Gotowe:

- pełna macierz TOML,
- loader i validator,
- `wvc-alertctl validate`,
- runtime manager,
- last-known-good w pamięci procesu,
- read-only mapping istniejących alertów,
- policy version + SHA-256 w stanie core,
- najwyższa aktywna waga + kolor HMI jako projekcja read-only.

Jeszcze nie zaimplementowano:

- zastosowania `reaction` do sterowania,
- nowych detektorów AlertV2,
- korelacji przyczynowej między wieloma detektorami,
- `FAN_NO_ROTATION_FEEDBACK`,
- integracji Service Agent ↔ Core AlertV2,
- sterowania fizycznym paskiem RGB HMI z polityki,
- automatycznego/hot reloadu polityki.

## 10. Następny zalecany etap

Przed jakimkolwiek włączeniem reakcji sterujących należy wykonać **Stage 3 — detektor/korelacja bez actuation**:

1. włączyć read-only dane Service Agent do kontekstu diagnostycznego core,
2. dodać korelację SENSOR BUS ↔ KAmod service-plane,
3. dodać nowe skorelowane kody, np. `KAMOD_NODE_UNAVAILABLE`,
4. nadal nie wykonywać `reaction` z TOML,
5. zwalidować wyniki na CM5 i rzeczywistych węzłach.

Operational TACHO (`FAN_NO_ROTATION_FEEDBACK`) powinno wejść jako osobny, sprzętowo walidowany podetap, ponieważ próg zadania, debounce i minimalne RPM nie zostały jeszcze zatwierdzone.
