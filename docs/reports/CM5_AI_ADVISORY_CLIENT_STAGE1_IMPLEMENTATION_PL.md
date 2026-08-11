# CM5 AI Advisory Client – Stage 1

**Data:** 11.08.2026  
**Status:** CM5 TESTS + REAL ONE-SHOT PASS; systemd validation pending  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/ai-advisory-client-stage1`

## 1. Cel

Dodać po stronie CM5 osobny, read-only klient odbierający najnowszy zapisany raport AI z AI Servera.

Ten klient nie jest częścią `ventilation-core` i nie może wpływać na sterowanie.

```text
AI Server / ventilation_analysis_runs
        ↓
GET /api/v1/ventilation/analysis/latest
        ↓
wvc-ai-advisory.service
        ↓
lokalny cache JSON
        ↓
przyszły GUI/status operatora
```

## 2. Granica bezpieczeństwa

Niezmienna zasada:

```text
ventilation-core = sterowanie + safety
wvc-ai-advisory = tylko odczyt raportu i cache
```

Klient advisory:

- nie otwiera socketu `ventilation-core`,
- nie wysyła żadnych komend lokalnych,
- nie zapisuje do stanu sterownika,
- nie modyfikuje setpointów,
- nie jest wymagany do startu ani działania `ventilation-core`,
- przy awarii AI Servera zachowuje ostatni cache i ponawia odczyt później.

## 3. HTTP client

Moduł:

```text
src/ventilation_core/advisory/client.py
```

Wykonuje wyłącznie:

```text
GET /api/v1/ventilation/analysis/latest?source_id=...
```

HTTP 404 oznacza normalny stan `brak analizy` i nie jest awarią.

Klient waliduje transportowy kontrakt bezpieczeństwa:

```text
delivery_schema_version = 1
advisory_only = true
experimental = true
control_actions_supported = false
result.schema_version = 2
```

Jeżeli serwer kiedykolwiek zwróci `control_actions_supported=true`, payload zostaje odrzucony.

Walidacja dotyczy wyłącznie kontraktu transportowego i struktury. CM5 nie ocenia semantycznie tekstu Qwena.

## 4. Lokalny cache

Docelowy plik:

```text
/var/lib/workshop-ventilation/ai-advisory.json
```

Cache ma lokalny envelope:

```json
{
  "cache_schema_version": 1,
  "fetched_at": "...",
  "report": {
    "delivery_schema_version": 1,
    "analysis_id": "...",
    "advisory_only": true,
    "experimental": true,
    "control_actions_supported": false,
    "result": {}
  }
}
```

Zapis jest atomowy przez plik tymczasowy + `os.replace()`. Dzięki temu GUI nie powinno zobaczyć częściowo zapisanego JSON-a.

Ten sam `analysis_id` nie powoduje ponownego zapisu cache.

## 5. Agent

Moduł:

```text
src/ventilation_core/advisory/agent.py
```

Domyślny polling:

```text
60 s
```

Awaria sieci, HTTP lub lokalnego cache jest logowana jako warning w pętli advisory. Nie propaguje się do `ventilation-core`.

## 6. CLI

Dodano entrypoint:

```text
ventilation-ai-advisory
```

oraz tryb walidacyjny:

```text
python3 -m ventilation_core.advisory.main --once
```

## 7. Systemd

Jednostka:

```text
deploy/systemd/wvc-ai-advisory.service
```

Najważniejsze cechy:

```text
User=wentylacja
Group=wentylacja
After=network-online.target
Wants=network-online.target
StateDirectory=workshop-ventilation
```

Celowo brak:

```text
Requires=ventilation-core.service
After=ventilation-core.service
```

Klient advisory jest niezależnym procesem sieciowym.

## 8. Konfiguracja

Wzorzec:

```text
deploy/cm5/advisory/wvc-ai-advisory.env.example
```

Zmienne:

```text
WVC_AI_BRIDGE_URL=http://192.168.1.55:8080
WVC_AI_ADVISORY_SOURCE_ID=workshop-ventilation-cm5-01
WVC_AI_ADVISORY_POLL_INTERVAL=60
```

Docelowy plik hosta:

```text
/etc/default/wvc-ai-advisory
```

## 9. Testy na CM5 – PASS

Pierwsze uruchomienie `unittest discover` bez `PYTHONPATH=src` zwróciło `ModuleNotFoundError: ventilation_core`; był to błąd sposobu uruchomienia testów w repozytorium z layoutem `src/`, nie błąd implementacji.

Poprawna walidacja:

```text
PYTHONPATH=src python3 -m unittest discover -s tests
Ran 54 tests in 0.061s
OK
```

**Test suite CM5: PASS.**

Po walidacji dodano `.gitignore` dla artefaktów Pythona (`__pycache__`, `*.py[cod]`, `.pytest_cache`, `.venv`, `*.egg-info`), aby kolejne `compileall`/testy nie brudziły repozytorium.

Testy obejmują m.in.:

- poprawny GET i query `source_id`,
- 404 jako brak analizy,
- odrzucenie `control_actions_supported=true`,
- lokalny cache JSON,
- brak przepisywania tego samego `analysis_id`,
- brak cache przy braku zdalnej analizy,
- brak zależności systemd od `ventilation-core`,
- brak socketu core i telemetry SQLite w jednostce advisory.

## 10. Stan AI Servera – PASS

AI Bridge Stage 3 został zwalidowany produkcyjnie jako:

```text
version=0.3.0
status=ok
database=ok
control_commands_supported=false
```

Rzeczywisty endpoint:

```text
GET /api/v1/ventilation/analysis/latest?source_id=workshop-ventilation-cm5-01
```

zwrócił poprawny delivery schema v1 dla:

```text
analysis_id=5cf9d21e-e2d2-4b0c-920e-c4a67aef135a
advisory_only=true
experimental=true
control_actions_supported=false
result.schema_version=2
```

## 11. Rzeczywisty CM5 one-shot – PASS

Na rzeczywistym CM5 wykonano klienta advisory w trybie jednorazowym do tymczasowego cache:

```text
WVC_AI_BRIDGE_URL=http://192.168.1.55:8080
WVC_AI_ADVISORY_SOURCE_ID=workshop-ventilation-cm5-01
PYTHONPATH=src
python3 -m ventilation_core.advisory.main --once --cache /tmp/wvc-ai-advisory-test.json
```

Log potwierdził:

```text
AI advisory cached
analysis_id=5cf9d21e-e2d2-4b0c-920e-c4a67aef135a
source_id=workshop-ventilation-cm5-01
window=2026-08-10T15:15:00Z..2026-08-10T15:30:00Z
status=no_anomaly_detected
cache_updated=True
```

Plik `/tmp/wvc-ai-advisory-test.json` zawierał:

```text
cache_schema_version=1
report.delivery_schema_version=1
report.analysis_id=5cf9d21e-e2d2-4b0c-920e-c4a67aef135a
report.advisory_only=true
report.experimental=true
report.control_actions_supported=false
report.result.schema_version=2
report.result.status=no_anomaly_detected
```

**Rzeczywisty tor AI Server -> CM5 one-shot -> lokalny cache: PASS.**

## 12. Pozostała walidacja systemd

Do zakończenia Stage 1 pozostaje:

```text
instalacja /etc/default/wvc-ai-advisory
instalacja wvc-ai-advisory.service
start i enable usługi
sprawdzenie /var/lib/workshop-ventilation/ai-advisory.json
potwierdzenie pollingu
symulacja zatrzymania AI Bridge i potwierdzenie, że ventilation-core działa bez zmian
restart klienta advisory
```

## 13. Następny krok

Po walidacji systemd cache może zostać użyty przez przyszły GUI/status operatora jako źródło informacji.

Nie wolno tworzyć automatycznej ścieżki:

```text
AI report -> setpoint / START / STOP / safety
```

Stage pozostaje Draft. Nie oznaczać Ready i nie merge'ować bez wyraźnej decyzji użytkownika.
