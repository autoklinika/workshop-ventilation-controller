# Control Engine V1 Stage4 — operator AUTO / MANUAL w SHADOW

Data: 2026-08-28
Repozytorium: `autoklinika/workshop-ventilation-controller`
Gałąź: `agent/automation-v1-control-engine`
Kodowy checkpoint: `879b558a0a730b01affbd6d4d3ee7aeade508fae`
GitHub Actions: `Ventilation Core Tests` run `33160441985`
Wynik CI: **PASS**

## Cel

Stage4 dodaje operator-owned tryb `AUTO` / `MANUAL` jako osobną warstwę Control Engine. Calendar nie ustawia MANUAL i pozostaje właścicielem harmonogramu. Operator MANUAL nie otrzymuje żadnej bezpośredniej władzy nad DAC ani AERO — na tym etapie nadal powstają wyłącznie propozycje SHADOW.

## Kontrakt operatora

Stan operatora jest własnością `ventilation-core` i jest celowo **volatile**:

- po każdym starcie core domyślny tryb to `AUTO`,
- MANUAL nie jest zapisywany do SQLite,
- stary ręczny override nie może sam odżyć po restarcie,
- każda jawna zmiana operator intent zwiększa process-local revision,
- `actuation_supported=false` pozostaje niezmienne.

Payload MANUAL wymaga jednocześnie:

- `manual_supply_pct` 0..100,
- `manual_extract_pct` 0..100,
- `manual_aero_speed` 0..3.

Payload AUTO jest kanoniczny i nie może zawierać pól MANUAL.

## Semantyka

### AUTO

Zachowuje istniejący algorytm:

`Calendar + AQ + thermal + fallback + safety`.

### MANUAL przy dobrym powietrzu

Operator podaje logiczne wartości procentowe i prędkość AERO. Calendar jest diagnostyką i nie modyfikuje żądania MANUAL. Limit oszczędzania ciepła również nie obcina ręcznego żądania.

### MANUAL + pogorszenie jakości powietrza

AQ zachowuje nadrzędność bezpieczeństwa:

- BOOST/HIGH może podnieść żądanie operatora,
- MAX prowadzi do `EMERGENCY_VENT`,
- wynik jest maksimum z ręcznego żądania oraz żądania bezpiecznego AQ.

### MANUAL + utrata SEN55

Ręczny tryb nie omija polityki sensor-loss:

- używany jest skonfigurowany fallback jako dolna granica,
- stan pozostaje `FAULT`,
- brak tuningu fallback nie prowadzi do wymyślenia wartości.

### MANUAL + safety fault

Critical alarm, nieznany output state lub inny istniejący safety block mają najwyższy priorytet:

- `BLOCKED_SAFETY`,
- `FAULT`,
- brak finalnego requestu,
- brak AERO proposal,
- brak physical voltage proposal.

## Rozdzielenie od istniejącego sterowania ręcznego

Nowe komendy:

- `control-engine-operator`,
- `control-engine-operator-replace`.

Nie są mapowane na istniejące fizyczne komendy:

- `set`,
- `aero-speed`,
- `aero-airing`.

Nie powstał adapter z operator intent do aktuatorów.

## Replay

Dodano:

- `config/control-engine-scenarios/lab-operator-v1.json`,
- `tests/test_control_engine_operator_scenario.py`.

Replay sprawdza:

1. start w AUTO,
2. przejście do MANUAL przy Calendar OFF i temperaturze PROTECTION,
3. AQ HIGH nadpisujący ręczne minimum,
4. critical safety block,
5. fallback po utracie SEN55,
6. powrót do AUTO bez kasowania aktywnego hold/histerezy AQ.

To ostatnie jest ważnym kontraktem: zmiana trybu operatora nie resetuje stanowego bezpieczeństwa AQ.

## Operator matrix

Dodano osobną macierz:

`config/control-engine-scenarios/lab-operator-matrix-v1.json`

Zakres:

`2 operator × 3 Calendar × 4 AQ × 2 temperatura × 5 fault/context = 240 przypadków`.

Macierz została oddzielona od wcześniejszej 960-case AUTO matrix, aby oba zestawy pozostały stabilnymi, wersjonowanymi benchmarkami.

Łącznie istnieje obecnie 1200 przekrojowych przypadków SHADOW w dwóch macierzach.

## Walidacja

Exact code SHA:
`879b558a0a730b01affbd6d4d3ee7aeade508fae`

Workflow:
`Ventilation Core Tests` — run `33160441985`

- Compile sources: PASS
- Unit tests: PASS
- Overall: SUCCESS

## Bezpieczeństwo

We wszystkich nowych testach i replayach:

- `actuation_supported=false`,
- `proposed_supply_voltage=null`,
- `proposed_extract_voltage=null`,
- operator layer nie posiada DAC/GPIO/systemd/host-power/AERO executor boundary.

## Decyzja

**Stage4 operator AUTO/MANUAL: PASS w warstwie SHADOW.**

Nie jest to zgoda na uruchomienie fizycznej automatyki. Następnym etapem przed projektowaniem actuation gate jest jawna polityka reakcji na TACHO mismatch/loss oraz jej walidacja syntetyczna.
