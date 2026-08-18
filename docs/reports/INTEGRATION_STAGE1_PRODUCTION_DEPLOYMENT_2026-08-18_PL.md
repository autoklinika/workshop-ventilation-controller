# Integration Stage 1 — raport wdrożenia produkcyjnego

Data: 2026-08-18

## 1. Zakres

Raport zamyka wdrożenie produkcyjne Integration Stage 1 dla `workshop-ventilation-controller` oraz zgodność transportu telemetrycznego z `AI-server` / AI Bridge.

Zakres funkcjonalny wdrożony na CM5:

- zintegrowany `CoreState` z SENSOR/SEN55, AERO, TACHO, Zigbee, harmonogramami i SHADOW,
- lokalny zapis surowej telemetrii i rollupy 1 min / 15 min,
- lokalne API historii,
- zdalna synchronizacja CM5 -> AI Bridge,
- GUI ustawień Zigbee i harmonogramów,
- SHADOW pozostający wyłącznie warstwą nieaktuującą.

Automatyczne sterowanie pozostaje wyłączone. SHADOW ma `actuation_supported=false` i status oczekiwany przy nieukończonym tuningu: `TUNING_REQUIRED`.

## 2. Kluczowe merge do main

### workshop-ventilation-controller

- Integration Stage 1, PR #34: `43028d24f53fba0db6ab043fd3795c386c1e505b`
- Web history SQLite/WAL hotfix, PR #35: `2a5082c80c9a5a2df1284e471bc3d08350434fdc`
- Telemetry oversized-batch recovery, PR #36: `6688fc1e10d2576361bf85d442af77bcb1e702f5`

Końcowy produkcyjny checkout CM5 został fast-forward do:

`6688fc1e10d2576361bf85d442af77bcb1e702f5`

### AI-server

AI Bridge CoreState extension, PR #6:

`b8e9fde9a286dfa624c252072cd0c6ed68de23da`

Zmiana rozszerza akceptowany `schema_version=1` o aktualny autorytatywny stan CM5: `aero_bus`, `tacho`, `zigbee`, `schedule`, `shadow_automation`, metadane alertów i diagnostykę SEN55. Nie dodaje endpointów sterujących ani aktuacji.

## 3. Walidacja Integration Stage 1 na CM5

Przed merge PR #34 wykonano pełną walidację laboratoryjną:

- 353 testy: PASS,
- realny SENSOR/SEN55: PASS,
- realny AERO: PASS,
- dual TACHO: PASS,
- Zigbee2MQTT + Mosquitto + core: PASS,
- 3 urządzenia Zigbee i role: PASS,
- harmonogramy + SHADOW w tym samym `CoreState`: PASS,
- lokalny capture/history/rollups: PASS,
- API historii: PASS,
- wspólne ustawienia GUI: PASS,
- `permit_join=false`,
- brak aktuacji podczas walidacji.

Raport laboratoryjny: `docs/reports/INTEGRATION_STAGE1_CM5_LAB_VALIDATION_2026-08-18_PL.md`.

## 4. Hotfix Web history

Po pierwszym wdrożeniu `/api/v1/history/status` zwracało HTTP 503 `unable to open database file` wyłącznie wewnątrz sandboxa `wvc-web-ui.service`.

Przyczyną był `ProtectSystem=strict` w połączeniu z SQLite WAL, który wymaga dostępu do plików bookkeeping obok `telemetry.sqlite3`.

PR #35 zachował `ProtectSystem=strict` i dodał wyłącznie:

`ReadWritePaths=/var/lib/workshop-ventilation`

Po wdrożeniu API historii zwróciło HTTP 200, a core pozostawał bez zmian.

## 5. AI Bridge — naprawa HTTP 422

Po integracji CM5 lokalny capture działał, ale AI Bridge odrzucał aktualny pełny `CoreState` HTTP 422. Pierwszym wskazanym polem było `metrics.aero_bus`.

AI-server PR #6 rozszerzył walidację i serializację istniejącego transportu v1 bez tworzenia konkurencyjnego modelu stanu.

Produkcja AI Bridge:

- host: `192.168.1.55`,
- katalog: `/opt/ai-bridge`,
- wersja: `0.3.0`,
- instalacja editable z `/opt/ai-bridge`,
- `control_commands_supported=false`,
- baza: `ok`.

Backup przed podmianą produkcyjnego schematu:

`/opt/ai-bridge/src/ai_bridge/adapters/ventilation/schemas.py.bak-20260818-145926`

Walidacja na produkcyjnym virtualenv:

- kompilacja schematu: PASS,
- walidacja zintegrowanego CoreState: PASS,
- testowy POST do `/api/v1/ventilation/telemetry/batches`: HTTP 200,
- `received=1`, `stored=1`, `rejected=0`,
- po restarcie `ai-bridge.service` realne POST-y z CM5 (`192.168.1.64`) zaczęły zwracać HTTP 200.

`pytest` nie był zainstalowany w produkcyjnym venv, więc nie instalowano narzędzi developerskich do środowiska produkcyjnego. Zamiast tego wykonano bezpośredni test schematu i endpointu z użyciem dokładnie bibliotek produkcyjnego AI Bridge.

## 6. Oversized telemetry batch — HTTP 413 / TCP reset

Po usunięciu 422 backlog zaczął schodzić, ale przy pełnym CoreState 100-próbkowy batch przekroczył limit AI Bridge 1 MiB.

Pomiar realnego zablokowanego batcha na CM5:

- 1 próbka: 10 952 B,
- 5 próbek: 54 092 B,
- 10 próbek: 95 087 B,
- 20 próbek: 177 087 B,
- 25 próbek: 218 087 B,
- 50 próbek: 492 305 B,
- 100 próbek: 1 150 808 B — 109,7% limitu 1 MiB.

Pierwsza wersja recovery opierała się na odebraniu HTTP 413. Produkcyjna walidacja wykazała jednak, że serwer może zamknąć połączenie jeszcze podczas wysyłania body. CM5 widział wtedy `BrokenPipeError` / `ConnectionResetError`, zanim `urllib` otrzymało odpowiedź HTTP.

PR #36 wprowadził rozwiązanie deterministyczne:

- produkcyjny cap `--batch-size 50`,
- lokalne sprawdzenie rozmiaru gotowego JSON przed otwarciem połączenia,
- zachowanie obsługi otrzymanego HTTP 413,
- `release_batch()` czyszczące wyłącznie `batch_id` i `batch_created_at`, bez kasowania próbek, liczników prób ani diagnostyki,
- po oversized multi-sample batch: release -> zmniejszenie batcha o połowę -> ponowienie,
- pojedyncza zbyt duża próbka pozostaje pending i nie jest kasowana.

Regresja finalnej wersji PR #36:

- targeted: 7 testów — PASS,
- full suite: 361 testów — PASS.

## 7. Produkcyjna walidacja backlogu

Przed finalną walidacją:

- telemetry sync: `inactive`,
- core: `STOP / 0 V`,
- `hardware_ready=true`,
- `output_state_known=true`,
- pending: 2762,
- zarezerwowany stary batch: `f6cb4822-13a7-42f1-99e4-2ed0833207a8`, 100 próbek, sequence 28513..28612.

Po uruchomieniu kodu PR #36:

- stary batch został wykryty lokalnie jako oversized,
- `released=100`, próbki zachowane,
- kolejne batch-e po 50 próbek synchronizowały się z `stored=50`, `duplicates=0`,
- końcówka backlogu: batch 16, następnie świeże batch-e po 1 próbce,
- brak nowych `Broken pipe`, `Connection reset`, HTTP 422 i HTTP 413,
- pending: 2762 -> 0,
- po zakończeniu nie pozostał żaden zarezerwowany batch,
- końcowy core: `STOP / 0 V`.

W czasie wcześniejszej nieudanej próby walidacyjnej precheck wykrył, że core był ustawiony ręcznie na `MANUAL 4.5 / 4.5 V`. Walidację zatrzymano, wykonano `ctl stop`, potwierdzono `STOP / 0 V`, a następne testy prowadzono już z fail-fast `set -euo pipefail`. Nie była to zmiana wykonana przez telemetrykę.

Backup bazy wykonany przed próbami recovery:

`/var/lib/workshop-ventilation/backups/telemetry-20260818-151943/telemetry.sqlite3`

Dodatkowy wcześniejszy backup wdrożenia Integration Stage 1:

`/var/lib/workshop-ventilation/backups/20260818-134721`

## 8. Finalny stan produkcji CM5

Po merge PR #36 i kanonizacji checkoutu:

- produkcyjny HEAD: `6688fc1e10d2576361bf85d442af77bcb1e702f5`,
- tymczasowy systemd override usunięty,
- `wvc-telemetry-sync.service`: active,
- `WorkingDirectory=/home/wentylacja/workshop-ventilation-controller`,
- `PYTHONPATH=/home/wentylacja/workshop-ventilation-controller/src`,
- finalny `--batch-size 50`,
- świeże próbki synchronizują się `stored=1`, `duplicates=0`.

Ostatni potwierdzony `/api/v1/history/status`:

- `available=true`,
- `total_samples=20760`,
- `pending_samples=0`,
- `synced_samples=20760`,
- `rollup_1m_samples=2631`,
- `rollup_15m_samples=185`,
- `database_bytes=169250816`,
- `configured=true`.

Końcowy safety check:

- mode: `STOP`,
- supply: `0.0 V`,
- extract: `0.0 V`,
- `hardware_ready=true`,
- `output_state_known=true`.

## 9. Wnioski

Integration Stage 1 jest wdrożone produkcyjnie i zsynchronizowane z AI Bridge.

Warstwa telemetryczna jest fail-open względem sterowania wentylacją: awaria AI Bridge lub synchronizacji nie wpływa na `ventilation-core`, a niesynchronizowane próbki pozostają lokalnie. Recovery oversized batch nie usuwa danych.

SHADOW pozostaje nieaktuujący. Dalsze uruchamianie automatyki wykonawczej wymaga osobnego, świadomego etapu projektu i nie jest częścią tego wdrożenia.
