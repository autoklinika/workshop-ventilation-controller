# AlertV2 Policy Loader / Validator — Stage 1

**Data:** 2026-08-18  
**Repozytorium:** `autoklinika/workshop-ventilation-controller`  
**Gałąź:** `agent/core-alert-v2-design-stage1`  
**Draft PR:** #44  
**Baza:** `main` `0f156cc6fe6e7d64df82a7a748108a93783c5fb7`

## 1. Cel kroku

Zaimplementować bezpieczny loader i validator deklaratywnej polityki AlertV2 bez podłączania jej jeszcze do produkcyjnego `ventilation-core` i bez wpływu na sterowanie sprzętem.

Ten krok realizuje wcześniej ustalony podział:

```text
detector -> stwierdza fakt
policy TOML -> określa wagę, reakcję, scope, kolor HMI i tekst operatora
```

Plik domyślny:

```text
config/alerts-v2.default.toml
```

Docelowy plik runtime CM5 pozostaje:

```text
/etc/workshop-ventilation/alerts-v2.toml
```

## 2. Zaimplementowane elementy

### 2.1. Loader

Dodano:

```text
src/ventilation_core/alert_policy.py
```

Loader:

- czyta TOML przez standardowe `tomllib` z Python 3.11,
- nie wymaga nowej zależności zewnętrznej,
- zwraca niemutowalny model `AlertPolicy` / `AlertPolicyEntry`,
- oblicza SHA-256 dokładnej zawartości pliku,
- publikuje wersję schema, wersję policy i liczbę alertów,
- nie stosuje polityki do sterowania i nie zmienia `CoreState`.

### 2.2. Validator

Validator odrzuca m.in.:

- błędny TOML,
- inną wersję schema niż `1`,
- brak wymaganych sekcji/pól,
- nieznane pola wynikające np. z literówki,
- wagę poza `0..4`,
- niezgodność `weight -> severity -> hmi_color`,
- nieznany typ `reaction`,
- błędne `correlation_priority`,
- nieprawidłowe identyfikatory alertów i scope/category,
- próbę osłabienia twardych niezmienników bezpieczeństwa.

Dodatkowe parametry detektora mogą być przechowywane wyłącznie w kontrolowanej podsekcji:

```toml
[alerts.CODE.parameters]
...
```

Nie tworzy to języka skryptowego. Parametry same nie wykonują logiki na `CoreState`.

## 3. Twarde niezmienniki wymuszane już przez validator

### 3.1. TACHO

Dla:

```text
TACHO_MONITOR_UNAVAILABLE
TACHO_CONFIGURATION_INVALID
```

validator wymusza:

```text
affects_control = false
reaction = continue | continue_degraded
```

Konfiguracja nie może więc zmienić samej utraty TACHO w `safe_state` ani inną reakcję zatrzymującą wentylację.

Dla alertów wykonania:

```text
FAN_NO_ROTATION_FEEDBACK
FAN_RPM_OUT_OF_RANGE
```

obecny kontrakt zabrania reakcji `safe_state` i `recover_safe_outputs`.

### 3.2. DAC

`DAC_COMMUNICATION_LOST` musi zachować:

```text
weight = 4
reaction = safe_state
affects_control = true
```

`DAC_STATE_UNCERTAIN` musi zachować:

```text
reaction = recover_safe_outputs
affects_control = true
```

Jeżeli obecna macierz zawiera `DAC_OUTPUT_MISMATCH`, validator wymaga dla niego `safe_state` i `affects_control=true`.

### 3.3. HMI / zewnętrzne warstwy

`HMI_CM5_COMMUNICATION_LOST` pozostaje lokalnym `block_gui` i nie otrzymuje prawa do zatrzymania autonomicznego core.

Dla pogody, AI/NAS/synchronizacji i service-plane validator nie pozwala ustawić bezpośredniego wpływu na sterowanie wentylacją.

## 4. CLI serwisowe

Dodano entry point:

```text
wvc-alertctl
```

Podstawowa walidacja aktywnego pliku:

```bash
wvc-alertctl validate
```

Walidacja dowolnego pliku:

```bash
wvc-alertctl validate config/alerts-v2.default.toml
```

Wynik pozytywny zawiera:

- schema version,
- policy version,
- liczbę alertów,
- SHA-256 konfiguracji.

Dostępny jest także wynik maszynowy:

```bash
wvc-alertctl validate --json config/alerts-v2.default.toml
```

Kody wyjścia:

```text
0 = polityka poprawna
2 = błąd odczytu / TOML / kontraktu / niezmiennika bezpieczeństwa
```

CLI **tylko waliduje**. Nie zapisuje pliku do `/etc`, nie przeładowuje core i nie zmienia sterowania.

## 5. Walidacja programowa

Dodano testy obejmujące:

- załadowanie pełnej domyślnej macierzy 49 alertów,
- TACHO -> zakaz `safe_state`,
- TACHO -> zakaz `affects_control=true`,
- DAC -> zakaz osłabienia `DAC_COMMUNICATION_LOST`,
- zgodność wagi, severity i koloru HMI,
- zakaz nadania pogodzie prawa do sterowania,
- kontrolowaną podsekcję `.parameters`,
- odrzucanie literówek/nieznanych pól,
- odrzucanie błędnego TOML,
- CLI human-readable i JSON,
- niezerowy kod wyjścia dla błędnej polityki.

GitHub Actions:

```text
Ventilation Core Tests #1501
run id: 32185058642
compileall: PASS
372/372 tests: PASS
```

## 6. Czego ten krok świadomie NIE robi

- `ventilation-core` nie ładuje jeszcze polityki przy starcie,
- istniejący Alert Stage 1 nadal działa dokładnie po staremu,
- nie zmieniono `AlarmCode`, `AlarmSeverity`, `AlertRecord` ani SQLite alertów,
- nie dodano korelacji service-plane / SENSOR BUS,
- nie dodano `FAN_NO_ROTATION_FEEDBACK` do runtime,
- nie sterujemy jeszcze paskiem RGB HMI na podstawie wag,
- nie wdrożono pliku do `/etc/workshop-ventilation`,
- nie wykonano restartu produkcyjnego core,
- `main` pozostaje bez zmian.

## 7. Następny bezpieczny krok

Przed podłączeniem polityki do lifecycle Alert Stage 1 należy dodać **runtime policy manager w trybie read-only**:

1. załadowanie zwalidowanego TOML przy starcie,
2. fail-safe startup: błędny plik nie może po cichu zastąpić poprawnej polityki,
3. publikację `policy_version` i SHA-256 w diagnostyce core,
4. mapowanie istniejących kodów Stage 1 na `AlertPolicyEntry`, ale jeszcze bez zmiany reakcji sprzętowych,
5. test regresyjny potwierdzający, że polityka nie może zmienić zwalidowanej reakcji DAC ani zatrzymać wentylacji przy awarii TACHO.

Dopiero po tym można rozpocząć dokładanie nowych detektorów i korelacji AlertV2.

## 8. Status

```text
pełna macierz TOML:        GOTOWA
loader TOML:               GOTOWY
validator kontraktu:       GOTOWY
validator safety rules:    GOTOWY — Stage 1
wvc-alertctl validate:     GOTOWY
testy repo:                372/372 PASS
integracja runtime core:   JESZCZE NIE
wpływ na produkcję:        BRAK
merge do main:             NIE
```
