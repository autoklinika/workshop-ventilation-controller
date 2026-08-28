# Control Engine V1 — Stage9: walidacja tuningu i commissioning

Data: 2026-08-28

## 1. Cel

Stage9 rozdziela trzy rzeczy, które wcześniej mogły wyglądać podobnie w samym JSON-ie konfiguracji:

1. pole tuningu ma wartość liczbową,
2. mechanizm software został sprawdzony syntetycznie,
3. wartość została zwalidowana na właściwym obiekcie i może być rozważana jako przyszła nastawa produkcyjna.

Sama obecność liczby nie może odblokować przyszłej aktuacji.

Zgodnie z `docs/ZALOZENIA_AUTOMATYKI_PL.md` parametry wyjść, dynamiki i reakcji awaryjnych wymagają rzeczywistych danych o wydajności, kubaturze, stratach cieplnych i zachowaniu finalnego obiektu. Odczyty środowiskowe z LAB nie są reprezentatywne dla warsztatu i nie mogą być użyte do promowania nastaw do poziomu produkcyjnego.

Control Engine nadal pozostaje SHADOW-only.

## 2. Stage9A — Tuning Validation Ledger

Dodano:

- `src/ventilation_core/domain/tuning_validation.py`
- `config/control-engine-tuning-validation-v1.json`
- `tests/test_tuning_validation.py`

Poziomy dowodów:

- `UNVALIDATED`
- `SYNTHETIC_VALIDATED`
- `PHYSICAL_VALIDATED`
- `WORKSHOP_VALIDATED`

Wymagany poziom dla przyszłych preconditions aktuacji:

| Grupa | Wymagany poziom |
|---|---|
| `fan_outputs` | `WORKSHOP_VALIDATED` |
| `aero_outputs` | `WORKSHOP_VALIDATED` |
| `dynamics` | `WORKSHOP_VALIDATED` |
| `fan_sensor_fallback` | `WORKSHOP_VALIDATED` |
| `aero_sensor_fallback` | `WORKSHOP_VALIDATED` |
| `tacho_confirmation` | `PHYSICAL_VALIDATED` |
| `tacho_supply_fallback` | `WORKSHOP_VALIDATED` |
| `tacho_extract_fallback` | `WORKSHOP_VALIDATED` |
| `tacho_both_fallback` | `WORKSHOP_VALIDATED` |

Aktualnie tylko `tacho_confirmation` spełnia wymagany poziom. `4.0 s` ma fizyczne dowody Stage7B/7C/7D i fizyczny kod testowy `f899f0589fb05bbb56c7df298ee6a268d85d7941`.

Pozostałe mechanizmy mogą być sprawdzone syntetycznie, lecz ich wartości produkcyjne nadal nie są znane.

Checkpoint Stage9A:

`5334fc3d825c077b8cc29949c0a2ebbecd876d70`

GitHub Actions `33174971277`: SUCCESS.

## 3. Readiness Gate wymaga teraz również dowodów

`assess_actuation_readiness()` dostał opcjonalny `validation_profile`.

Zasady:

- pełny numeric tuning bez profilu dowodów => blocker `TUNING_VALIDATION_PROFILE_NOT_BOUND`,
- związany profil poniżej wymaganego poziomu => jawny blocker `VALIDATION_<GROUP>_REQUIRES_<LEVEL>`,
- nawet przy kompletnych preconditions nadal wymagany jest osobny authority bit,
- w PR #86 authority nie istnieje i `ACTUATION_AUTHORITY_NOT_IMPLEMENTED` pozostaje twardą blokadą.

Domyślny runtime **nie wiąże automatycznie** repozytoryjnego profilu dowodów. Jest to celowe fail-closed. Osobny etap bindingu będzie dopuszczalny dopiero po rzeczywistym commissioning i jawnej decyzji projektu.

Fail-closed contract:

`tests/test_control_engine_validation_fail_closed_contract.py`

Checkpoint:

`b16c880e2f13bc5f5d8ec1f9e9ff4b988da11e5d`

Compile PASS, unit tests PASS.

## 4. Stage9B — wersjonowany plan commissioning

Dodano:

- `config/control-engine-commissioning-plan-v1.json`
- `tools/control_engine_commissioning_status.py`
- `tests/test_control_engine_commissioning_status.py`

Plan wymaga `environment_required = WORKSHOP` i jawnie zabrania promowania wartości na podstawie odczytów środowiskowych z LAB.

Dla każdej z 9 grup zapisano:

- cel,
- wymagane obserwacje,
- kryteria ukończenia,
- wymagany poziom dowodów.

Status tool jest read-only. Nie zna socketu sterującego, `systemctl`, DAC, AERO executora ani komendy zastosowania konfiguracji.

Bieżący status commissioning:

- ukończone na wymaganym poziomie: `tacho_confirmation`,
- oczekujące: `fan_outputs`, `aero_outputs`, `dynamics`, `fan_sensor_fallback`, `aero_sensor_fallback`, `tacho_supply_fallback`, `tacho_extract_fallback`, `tacho_both_fallback`.

Checkpoint plan/status:

`c4c9b8512b87ee0c3f5388ed8a2e74a490dd4d70`

GitHub Actions `33175133636`: SUCCESS.

## 5. Workshop commissioning candidate

Dodano:

- `src/ventilation_core/domain/commissioning_candidate.py`
- `config/control-engine-commissioning-candidate-template-v1.json`
- `tools/control_engine_validate_commissioning_candidate.py`
- `tests/test_control_engine_commissioning_candidate.py`

Candidate jest osobnym, read-only artefaktem przygotowującym przyszłe wartości do review. Nie jest plikiem, który można bezpośrednio zastosować do core.

Najważniejsze reguły:

- `environment` musi być dokładnie `WORKSHOP`,
- wszystkie grupy i wszystkie przypisane do nich pola muszą istnieć dokładnie raz,
- wartości są walidowane przez ten sam `ShadowOutputTuning`, którego używa Control Engine,
- zachowane są zakresy, pary fallbacków i monotoniczność,
- każda grupa musi mieć odpowiedni poziom evidence,
- read-only validator nie posiada ścieżki `control-engine-replace`, socketu, `systemctl` ani aktuatorów,
- `actuation_authority_granted=false`, `writes_performed=false`.

Template zawiera dokładnie jedną gotową nie-null nastawę:

`tacho_failure_confirmation_seconds = 4.0`

Wszystkie pozostałe wartości pozostają `null`.

Checkpoint candidate framework:

`0daaf956516b40ed1eacc5a9ef19b07ea9127c15`

GitHub Actions `33175532680`: SUCCESS.

## 6. Polityki fallback TACHO

Stage9 nie przypisuje wartości fallbacków `SUPPLY`, `EXTRACT` ani `BOTH`.

Każdy przypadek ma osobny commissioning:

### SUPPLY failure

W finalnym pomieszczeniu należy sprawdzić zachowanie układu przy niedostępnym nawiewie / supply held at zero, obserwując m.in. balans pomieszczenia, efekt pracy wyciągu, temperaturę oraz procedurę operatora.

### EXTRACT failure

W finalnym pomieszczeniu należy osobno sprawdzić brak wyciągu. Wymagana jest obserwacja ryzyka nadciśnienia i migracji zanieczyszczeń. Wartości z SUPPLY failure nie mogą być kopiowane.

### BOTH failure

Wymagana jest analiza dual fan loss vs. uszkodzenie toru feedback, procedura alarmowa/operatora oraz osobna ocena strategii awaryjnej w realnym pomieszczeniu.

Żadna z tych polityk nie jest deklaracją BHP ani dowodem bezpiecznej jakości powietrza.

## 7. Co Stage9 celowo NIE robi

Stage9:

- nie ustawia produkcyjnych procentów fanów,
- nie dobiera AERO speed,
- nie ustawia histerez/timingów z danych LAB,
- nie ustawia fallbacków SEN55/TACHO,
- nie zapisuje produkcyjnego `automation.sqlite3`,
- nie grantuje authority,
- nie tworzy portu do GP8403/AERO/GPIO,
- nie włącza scheduled shutdown,
- nie zmienia `main`.

## 8. Wynik

**PASS — framework przygotowania i walidacji przyszłego tuningu jest gotowy software’owo.**

Aktualny stan dowodów: **1/9 grup spełnia wymagany poziom** (`tacho_confirmation`). Pozostałe **8/9 wymagają reprezentatywnego commissioning w finalnym warsztacie**.

PR #86 ma pozostać Draft i SHADOW-only. Nie wykonywać merge ani nie włączać aktuacji na podstawie Stage9.
