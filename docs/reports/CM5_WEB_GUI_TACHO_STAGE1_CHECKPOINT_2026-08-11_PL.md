# Web GUI + CM5 TACHO Stage 1 — checkpoint integracji prezentacyjnej

**Projekt:** Workshop Ventilation Controller  
**Data:** 2026-08-11  
**Gałąź GUI:** `agent/web-gui-manual-control-stage1`  
**PR GUI:** #20 — Draft  
**Gałąź TACHO:** `agent/cm5-tacho-stage1`  
**PR TACHO:** #21 — Draft

## 1. Stan bazowy repozytorium

W chwili rozpoczęcia integracji `main` pozostawał na:

```text
e689a991f9e71bf77f1771ca2cec31cd9b5716f6
```

PR #20 i PR #21 są równoległymi Draft PR bazującymi na tym samym `main`.

Aktualny zweryfikowany head PR #21 podczas analizy:

```text
d20a89c8d0a74b0cc209be4e26d022f3963df3cb
```

PR #21 pozostaje osobnym etapem TACHO i nie został scalony ani oznaczony Ready.

## 2. Zweryfikowany kontrakt TACHO

`CoreState` publikuje opcjonalne pole:

```text
tacho
```

`TachoMonitorState` zawiera:

```text
chip_path
ready
worker_alive
last_error
supply
extract
```

Kanał `FanTachoState` zawiera:

```text
line_name
line_offset
frequency_hz
rpm
sample_count
age_seconds
valid
```

Stage 1 ma zwalidowany tylko kanał EXTRACT:

```text
EXTRACT command -> DFR0971 DAC CH1 / VOUT1
EXTRACT TACHO   -> GPIO27 / physical pin 13 / gpiochip0 offset 27
```

`GPIO17 / pin 11` pozostaje zarezerwowane dla przyszłego kanału SUPPLY. Dlatego obecne:

```text
tacho.supply == null
```

jest stanem oczekiwanym i GUI nie traktuje go jako awarii.

Potwierdzony przelicznik:

```text
3 impulsy / obrót
RPM = frequency_hz * 20
```

GUI nie przelicza jednak RPM samodzielnie. Prezentuje wartość `rpm` wyliczoną i opublikowaną przez `ventilation-core`.

## 3. Semantyka zachowana w GUI

Integracja celowo nie zmienia semantyki Stage 1.

### `valid=true`

GUI prezentuje:

- rzeczywiste RPM,
- status `TACHO: sygnał OK`,
- pomocniczo bieżącą częstotliwość i nazwę GPIO.

### `valid=false`

GUI prezentuje:

```text
Obroty: —
TACHO: brak sygnału
```

Wartość `rpm=0` obecna w kontrakcie runtime przy nieważnym pomiarze nie jest pokazywana jako potwierdzone `0 RPM`.

### Problem infrastruktury monitora

Jeżeli skonfigurowany kanał istnieje, ale:

```text
last_error != null
```

lub:

```text
worker_alive != true
```

GUI pokazuje `TACHO: błąd monitora` oraz dostępny `last_error`.

Jeżeli worker działa, lecz `ready != true`, GUI pokazuje `TACHO: monitor niegotowy`.

Globalny pasek stanu ma osobną pozycję `TACHO`, dzięki czemu problem infrastruktury można odróżnić od zwykłego braku impulsów.

## 4. COMMAND i ACTUAL pozostają rozdzielone

Dla każdego wentylatora EC panel pokazuje osobno:

```text
Sterowanie: xx %
Napięcie:   x,x V
Obroty:     xxxx RPM lub —
```

`Sterowanie [%]` jest wyłącznie prezentacją liniowego zakresu komendy 0–10 V:

```text
0 V  -> 0 %
5 V  -> 50 %
10 V -> 100 %
```

Nie jest to oczekiwana prędkość, wydajność ani potwierdzenie wykonania.

`Napięcie` pochodzi z autorytatywnego `CoreState.setpoints`.

`Obroty` pochodzą wyłącznie z read-only `CoreState.tacho` i są wyświetlane tylko przy `valid=true`.

## 5. Brak sprzężenia TACHO ze sterowaniem

TACHO nie zostało dodane do warunku dostępności ręcznego sterowania GUI.

Nie dodano:

- alarmu command-vs-actual,
- fan-stopped alarm,
- under-speed,
- over-speed,
- expected RPM,
- blokady sterowania przy braku TACHO,
- automatycznego STOP,
- closed-loop RPM,
- charakterystyki 0–10 V -> RPM.

Read-only renderer TACHO wykonuje wyłącznie `GET /api/v1/state` i nie zawiera żadnego endpointu POST ani wywołania `/api/v1/manual/*`.

## 6. API Web GUI

Nie dodano nowego endpointu TACHO.

Istniejący endpoint:

```text
GET /api/v1/state
```

korzysta z istniejącego polecenia Unix socket:

```json
{"command":"status"}
```

`ventilation-core` serializuje całe `CoreState`, dlatego po wejściu kontraktu PR #21 pole `tacho` jest przekazywane do GUI bez dodatkowej ścieżki API.

GUI pozostaje kompatybilne ze starszym core bez pola TACHO: brak `state.tacho` jest prezentowany jako `TACHO: nieaktywne`, bez alarmu i bez blokady sterowania.

## 7. Zmiany w PR #20

Dodano/zmieniono wyłącznie warstwę Web GUI:

- `src/ventilation_core/web/static/index.html`
  - osobne pola command / voltage / RPM,
  - status TACHO per kanał,
  - globalny status TACHO,
- `src/ventilation_core/web/static/tacho.js`
  - read-only prezentacja opcjonalnego `CoreState.tacho`,
- `src/ventilation_core/web/static/styles.css`
  - układ nowych pól dostosowany do desktop/touch,
- `src/ventilation_core/web/server.py`
  - dopuszczenie statycznego assetu `tacho.js`,
- `tests/test_web_tacho.py`
  - regresje kontraktu prezentacyjnego i read-only.

Nie zmieniono modułów sterowania DAC, SENSOR BUS, AERO BUS ani TACHO runtime.

## 8. Konflikt PR #20 vs PR #21

Na poziomie listy zmienianych plików PR #20 i PR #21 nie mają wspólnych plików.

PR #20 dotyka warstwy `src/ventilation_core/web/*`, konfiguracji Web GUI i dokumentacji GUI.

PR #21 dotyka domeny/runtime TACHO, `ventilation-core.service`, pinoutu, testów TACHO i narzędzia sprzętowego.

Wniosek: nie ma obecnie bezpośredniego konfliktu plikowego pomiędzy implementacją TACHO i GUI.

Istnieje natomiast ważny aspekt wdrożeniowy na CM5: trwały `/etc/systemd/system/ventilation-core.service` został już skonfigurowany z argumentami TACHO i uruchamia kod z katalogu `/home/wentylacja/workshop-ventilation-controller`. Nie należy więc przełączać tego produkcyjnego checkoutu na gałąź GUI pozbawioną kodu PR #21 i następnie restartować/rebootować core.

Do walidacji GUI z działającym TACHO przed formalnym pogodzeniem gałęzi należy użyć osobnego `git worktree` dla Web GUI lub innego osobnego katalogu roboczego. `ventilation-core` powinien nadal pracować z checkoutu zawierającego zwalidowany kod TACHO.

## 9. AERO BUS

Aktualny niezależny problem:

```text
online=false
usable=false
last_error="No response or incomplete Modbus header"
```

nie jest częścią tego checkpointu.

GUI nadal prezentuje stan AERO niezależnie. Integracja TACHO nie zmienia diagnostyki ani sterowania AERO.

## 10. Walidacja CI

Po implementacji kontraktu prezentacyjnego GitHub Actions:

```text
Ventilation Core Tests #842
Ran 157 tests
OK
```

Zaliczone regresje obejmują m.in.:

- przekazanie opcjonalnego `tacho` przez istniejący endpoint state,
- rozdzielenie command / voltage / RPM w dashboardzie,
- `valid=false` -> `RPM: —`,
- rozróżnienie `brak sygnału` / `nie skonfigurowano` / `błąd monitora`,
- read-only charakter renderer TACHO,
- brak TACHO w warunku blokowania manualnego sterowania,
- dostępność statycznego `tacho.js` przez Web UI server.

## 11. Następny checkpoint sprzętowy GUI

Przed scalaniem PR #20 należy uruchomić Web GUI z osobnego worktree przeciwko działającemu produkcyjnemu `ventilation-core` z TACHO i potwierdzić co najmniej:

1. STOP: EXTRACT pokazuje napięcie 0,0 V, sterowanie 0%, `RPM: —`, `TACHO: brak sygnału` przy zdrowym monitorze.
2. EXTRACT 5 V: GUI pokazuje 50%, 5,0 V oraz rzeczywiste RPM z GPIO27.
3. Fizyczne odłączenie TACHO przy 5 V: GUI przechodzi na `RPM: — / TACHO: brak sygnału`, ale sterowanie pozostaje 50% / 5,0 V i nie jest blokowane.
4. Ponowne podłączenie: RPM wraca automatycznie bez restartu core.
5. SUPPLY: `TACHO: nie skonfigurowano` i brak fałszywego alarmu.
6. AERO offline pozostaje osobnym stanem i nie wpływa na prezentację TACHO.

PR #20 i PR #21 pozostają Draft. Ten checkpoint nie wykonuje merge ani Ready for Review.
