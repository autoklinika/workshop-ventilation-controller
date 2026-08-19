# AlertV2 Stage 6 — wynik walidacji reboot / soak / persistence na CM5

Data walidacji: 2026-08-19

Status: **PASS**

## Cel

Stage 6 miał potwierdzić, że produkcyjny rollout AlertV2 Stage 5 pozostaje stabilny po pełnym restarcie CM5, bez uruchamiania jakiejkolwiek automatyki sterującej AlertV2.

Twarde założenie projektowe pozostaje bez zmian:

- `reaction` i `affects_control` są wyłącznie metadanymi diagnostycznymi,
- `control_policy_applied=false`,
- `reaction_execution_enabled=false`,
- validator nie wysyła żadnych komend sterujących,
- jedynym automatycznym wyjątkiem pozostaje lokalny watchdog HMI/Web GUI dla utraty komunikacji z CM5; watchdog nie steruje wentylacją,
- istniejące, niezależne mechanizmy bezpieczeństwa `ventilation-core` nie są częścią automatyki AlertV2 i pozostają bez zmian.

## Baseline przed reboot

Walidator Stage 6 `prepare` zakończył się PASS i zapisał baseline do:

`/var/lib/workshop-ventilation/alert-v2-stage6-reboot-baseline.json`

Stan przed restartem:

- boot_id: `c3292517-56d4-48a2-bb4b-a95a257d91f3`,
- core PID: `44317`,
- Service Agent PID: `1130`,
- core CWD: `/home/wentylacja/wvc-alert-v2-stage4`,
- mode: `STOP`,
- supply: `0.0 V`,
- extract: `0.0 V`,
- `output_state_known=true`,
- `control_policy_applied=false`,
- `reaction_execution_enabled=false`,
- Web GUI 18091: `/api/v1/state`, `/api/v1/alerts`, `/api/v1/health` — dostępne,
- policy_version: `2026-08-18.1`,
- alert_count: `49`,
- policy SHA-256: `c197a28055ef05ab6c5e8663068068160d23fea5eef2935c1aa604906b5fc2a3`,
- zapisano 50 bazowych incident IDs: `68..19`.

## Reboot

Po pełnym reboot CM5:

- `ventilation-core.service` — active,
- `wvc-service-agent.service` — active,
- `wvc-web-ui.service` — active,
- post-reboot core PID: `1175`,
- post-reboot Service Agent PID: `1128`,
- post-reboot boot_id: `e461fd1a-81e4-4705-97ed-69443946ec1b`,
- core CWD nadal: `/home/wentylacja/wvc-alert-v2-stage4`.

Zmiana boot_id oraz obu PID-ów potwierdza rzeczywisty restart systemu i ponowne uruchomienie usług.

## Pierwsza próba verify — przejściowy timeout

Pierwsze uruchomienie `verify --duration 180 --interval 1` po świeżym boot zakończyło się komunikatem `FAIL: timed out`.

Diagnostyka bez restartu usług wykazała następnie:

- bezpośredni `status`: ok. `1.63 ms`,
- bezpośredni `alerts`: ok. `2.58 ms`,
- core PID i Service Agent PID stabilne,
- poprawny production CWD.

Dodatkowy probe Web GUI wykonał 10 cykli × 3 endpointy = 30 GET-ów bez błędu. Najwyższe zaobserwowane czasy:

- `/api/v1/state`: `17.207 ms`,
- `/api/v1/alerts`: `11.447 ms`,
- `/api/v1/health`: `4.914 ms`.

Nie zmieniano timeoutów validatora i nie osłabiano kryterium walidacji.

## Druga próba 180 s soak — błąd końcowego porównania historii

Drugi pełny przebieg `verify --duration 180 --interval 1` wykonał soak i zatrzymał się dopiero w końcowej kontroli persistence komunikatem:

`FAIL: alert lifecycle history lost across reboot: missing incident IDs [20, 19]`

Analiza wykazała błąd validatora, a nie utratę danych. Baseline zawierał 50 najnowszych ID, a po reboot validator porównywał go z nową listą ograniczoną ponownie do 50 najnowszych ID. Nowe incydenty po restarcie przesunęły najstarsze bazowe ID `19` i `20` poza okno top-50.

Nie było podstaw do wniosku o usunięciu rekordów z bazy.

## Lifecycle persistence recheck

Dodano osobny read-only recheck:

`tools/validate_alert_v2_stage6_lifecycle_recheck_cm5.py`

Recheck pobiera historię z limitem 1000 i szuka wszystkich 50 bazowych incident IDs w pełnym zwróconym oknie, bez ponownego obcinania wyniku do top-50.

Wynik na realnym CM5:

- result: `PASS`,
- `baseline_incident_ids_checked=50`,
- `history_request_limit=1000`,
- `returned_unique_incident_ids=71`,
- `missing_baseline_incident_ids=[]`,
- wszystkie bazowe incident IDs `68..19` znalezione po reboot,
- ID `20` i `19` potwierdzone w `history`,
- `control_policy_applied=false`,
- `reaction_execution_enabled=false`,
- mode: `read_only_mapping`,
- production mode: `STOP`,
- supply: `0.0 V`,
- extract: `0.0 V`,
- `output_state_known=true`,
- validator wysłał `0` komend sterujących.

## Wniosek

**AlertV2 Stage 6 = PASS.**

Potwierdzono na produkcyjnym CM5:

1. pełny reboot systemu,
2. automatyczny powrót core, Service Agent i Web GUI,
3. zachowanie Stage 5 runtime CWD przez systemd drop-in,
4. zachowanie identycznej polityki AlertV2,
5. brak aktywacji automatyki sterującej AlertV2,
6. stabilny read-only soak po reboot,
7. zachowanie historii alertów przez reboot,
8. brak utraty bazowych 50 incydentów,
9. zachowanie `STOP / 0 V / 0 V` oraz znanego stanu wyjść,
10. zero komend sterujących ze strony narzędzi Stage 6.

Pierwszy timeout po świeżym boot i false-negative persistence są zachowane w raporcie jako istotne obserwacje walidacyjne. Nie są ukrywane ani klasyfikowane jako PASS bez wyjaśnienia.

## Stan po Stage 6

Produkcja nadal działa na niezmienionym kodzie Stage 5 z worktree:

`/home/wentylacja/wvc-alert-v2-stage4`

Stage 6 tooling działa z osobnego worktree i nie zmienia produkcyjnego runtime.

PR #44 pozostaje Draft i nie jest mergowany do `main` bez osobnej zgody operatora.
