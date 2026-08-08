# Prompt do nowej rozmowy — po zamknięciu KAmod Service OTA Stage 1

Kontynuujemy projekt **Workshop Ventilation Controller**.

Repozytorium:

`autoklinika/workshop-ventilation-controller`

`KAmod Service OTA Stage 1` jest zakończony i zwalidowany sprzętowo na obu fizycznych węzłach `KAmod ESP32 POW RS485 + SEN55`.

Nie zakładaj, że podane niżej SHA lub stany PR nadal są aktualne. **Najpierw sprawdź rzeczywisty aktualny HEAD odpowiednich gałęzi i stan otwartych PR-ów na GitHub.**

Przeczytaj dokładnie:

- `docs/reports/KAMOD_SERVICE_OTA_STAGE1_FINAL_REPORT_AND_HANDOFF_PL.md`
- `docs/reports/KAMOD_SERVICE_OTA_STAGE1_DUAL_NODE_FINAL_VALIDATION_PL.md`
- `docs/reports/KAMOD_SERVICE_OTA_STAGE1_NEGATIVE_PATH_VALIDATION_PL.md`
- `docs/DUAL_CHANNEL_NODE_COMMUNICATION_PL.md`
- `docs/DECISIONS_PL.md`

Kontekst końcowy OTA:

```text
sensor-node-1: 0.5.1-stage1-fix1, ota_1, valid, pending=false
sensor-node-2: 0.5.1-stage1-fix1, ota_1, valid, pending=false
SENSOR BUS: ready=true, worker_alive=true, worker_restarts=0
oba slave: online=true, usable=true, measurement_valid=true,
           measurement_stale=false, consecutive_failures=0
```

Na `sensor-node-1` wykonano pełną walidację mechanizmu:

```text
normalne OTA: PASS
przerwany transfer: PASS
bad HMAC: PASS
bad SHA-256: PASS
rollback obrazu niepotwierdzonego: PASS
```

Na `sensor-node-2` wykonano jednorazowy USB `app-flash` bootstrap z zachowaniem NVS, sprawdzono provisioning, SEN55 i Modbus slave 2, a następnie normalne OTA `ota_0 -> ota_1`: PASS.

Nie powtarzaj testów negatywnych OTA tylko dlatego, że zaczyna się nowa rozmowa. Nie flashuj żadnego KAmod podczas orientacji.

Obowiązujące niezmienniki:

```text
RS-485 Modbus RTU = jedyny kanał produkcyjny dla SEN55
Wi-Fi WVC-SERVICE = best-effort kanał serwisowy
OTA = ręczne, jeden węzeł naraz
ventilation-core = niezależny od Wi-Fi i OTA
```

Nie wolno używać produkcyjnie:

- `kamod_sen55_sensor_node-0.5.1-stage1.bin` — stary podatny obraz,
- `kamod_sen55_sensor_node-0.5.2-stage1-rollback-test.bin` — wyłącznie test rollbacku.

Na moment zamknięcia etapu OTA gałąź robocza to:

`agent/kamod-service-ota-stage1`

Draft PR:

`#14`

Checkpoint dual-node hardware validation:

`83de49494a69fab179a36353701dff6f0213bf4d`

Po nim dodano końcowy raport i ten handoff, więc ponownie: **sprawdź rzeczywisty HEAD, nie zakładaj, że 83de494 jest aktualnym końcem gałęzi.**

PR #14 ma pozostać Draft i nie może być scalony ani oznaczony Ready for Review bez mojego wyraźnego polecenia.

W repo istnieją także inne stacked/open Draft PR-y warstwy serwisowej i AERO BUS. Nie zamykaj ich ani nie scalaj automatycznie w ramach samego porządkowania po OTA.

## Pierwsze zadanie w nowej rozmowie

1. Sprawdź aktualny stan repozytorium, HEAD i otwarte PR-y.
2. Potwierdź na podstawie raportów, że OTA Stage 1 jest zamknięty sprzętowo.
3. Oceń, jaki jest **następny logiczny etap projektu po OTA**, uwzględniając aktualny kod, istniejące Draft PR-y i dokumentację architektury.
4. Przed rozpoczęciem nowej implementacji przedstaw krótko:
   - co jest już zakończone,
   - co pozostaje otwarte,
   - który etap proponujesz jako następny i dlaczego.
5. Nie wykonuj merge ani nie oznaczaj żadnego PR jako Ready bez mojego wyraźnego polecenia.
