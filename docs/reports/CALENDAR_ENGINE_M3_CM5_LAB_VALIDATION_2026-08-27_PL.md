# Calendar Engine M3 — walidacja na fizycznym CM5 w trybie LAB

Data: 2026-08-27

Repozytorium: `autoklinika/workshop-ventilation-controller`

Gałąź walidowana: `agent/automation-v1-scheduler-assumptions`

Walidowany SHA: `6f1ed56b3a7059c56f771d33a62850ff28ed1e3c`

Produkcyjny `main` podczas testu: `7628c407cfc9c0ea72d262566759ea2d4598fec8`

## Cel

Zweryfikować Calendar Engine M3 na rzeczywistym Raspberry Pi Compute Module 5 bez wykonywania fizycznej aktuacji wentylatorów, AERO ani innych urządzeń wykonawczych.

Test wykonano w warunkach laboratoryjnych. Fizycznie podłączone było Zigbee; DAC/DFR0971, SEN55 i AERO były odłączone. Z tego powodu `ventilation-core` mógł poprawnie pozostawać w stanie `FAULT` i raportować nieznany stan wyjść sprzętowych. Tryb LAB nie zmienia wymagań dotyczących braku aktuacji: logiczne setpointy EC muszą pozostać na 0.0 V, TACHO na 0 RPM, a shadow automation nie może wspierać aktuacji.

## Wynik końcowy

**PASS**

Kod wyjścia harnessu: `0`.

Końcowy komunikat:

```text
PASS: Calendar Engine M3 validated on CM5 without ventilation/AERO control commands
lab mode:          1
branch SHA:        6f1ed56b3a7059c56f771d33a62850ff28ed1e3c
main before PID:   7776
branch prepare PID:18035
branch verify PID: 18156
main after PID:    18366
final CWD:         /home/wentylacja/workshop-ventilation-controller
```

## Zweryfikowane elementy

### 1. Preflight produkcyjnego main

**PASS**

- produkcyjny checkout był na `main`,
- HEAD: `7628c407cfc9c0ea72d262566759ea2d4598fec8`,
- working tree był czysty,
- tryb LAB poprawnie zaakceptował oczekiwany `FAULT` przy odłączonym sprzęcie,
- logiczne setpointy EC: 0.0 V / 0.0 V,
- TACHO: brak wykrytego ruchu,
- brak wykrytej aktuacji AERO.

### 2. Rollout testowego core z osobnego worktree

**PASS**

Testowy core uruchomiono z dokładnego, przypiętego SHA:

`6f1ed56b3a7059c56f771d33a62850ff28ed1e3c`

Po rollout:

- testowy core działał z odseparowanego worktree,
- produkcyjny checkout `main` nie był modyfikowany,
- użyto izolowanych danych testowych,
- logiczne wyjścia pozostały na 0.0 V.

### 3. Izolowany WebGUI Calendar Engine

**PASS**

Uruchomiono osobny WebGUI wyłącznie lokalnie:

`http://127.0.0.1:18092`

Endpoint Calendar Engine był dostępny i współpracował z testowym core.

### 4. Semantyka Calendar Engine

**PASS** dla wszystkich sprawdzanych przypadków:

- `PREVENTILATION`,
- `ACTIVE`,
- `PURGE`,
- `DATE_EXCEPTION`,
- `next_wake`.

### 5. WebGUI roundtrip i zapis konfiguracji

**PASS**

Konfiguracja została zapisana przez WebGUI do Calendar Engine.

Po zapisie:

- `calendar_revision = 2`,
- SHA256 konfiguracji:
  `228f217a9c7d76dadc063a00666a8723d6b8c05b85fb02b3bcc01b60604dfa65`,
- odczyt z core był zgodny z konfiguracją zapisaną przez WebGUI.

### 6. Brak fizycznej aktuacji

**PASS**

Podczas całej fazy PREPARE:

- `physical_actuation = false`,
- runtime pozostawał w oczekiwanym LAB `FAULT`,
- `supply_voltage = 0.0`,
- `extract_voltage = 0.0`.

Validator dopuszczał tylko niekontrolujące komendy Calendar Engine (`status`, `calendar`, `calendar-replace`).

### 7. Restart testowego ventilation-core i persistence

**PASS**

Testowy `ventilation-core` został zrestartowany.

Po restarcie:

- Calendar Engine odzyskał `calendar_revision = 2`,
- konfiguracja zachowała ten sam SHA256,
- persistence: `PASS`,
- WebGUI recovery: `PASS`,
- `physical_actuation = false`,
- logiczne setpointy nadal wynosiły 0.0 V / 0.0 V.

### 8. Powrót do produkcyjnego main

**PASS**

Po zakończeniu testu:

- testowy drop-in został usunięty,
- testowy core został zastąpiony produkcyjnym core z `main`,
- końcowy CWD core:
  `/home/wentylacja/workshop-ventilation-controller`,
- produkcyjny `main` nie został zmodyfikowany,
- końcowy stan LAB pozostał bez aktuacji.

## Wnioski

Calendar Engine M3 został pomyślnie zweryfikowany na fizycznym CM5 w warunkach laboratoryjnych.

Potwierdzono:

1. poprawną semantykę kalendarza,
2. zapis konfiguracji przez WebGUI,
3. zgodny odczyt konfiguracji przez core,
4. trwałość konfiguracji po restarcie `ventilation-core`,
5. poprawne odzyskanie stanu przez WebGUI,
6. brak komend sterujących i brak fizycznej aktuacji,
7. bezpieczny rollback do produkcyjnego `main`.

M3 można uznać za **zamknięte / PASS**.

## Uwagi z wcześniejszych prób

Podczas pierwszych prób ujawniono dwa problemy wyłącznie w harnessie walidacyjnym:

- cleanup wykonywał restart produkcyjnego core nawet przy błędzie przed rolloutem,
- wewnętrzny validator Pythona nie respektował trybu LAB i wymagał `mode == STOP` / `output_state_known == true` mimo celowo odłączonego sprzętu.

Oba problemy zostały poprawione przed finalną walidacją. Finalny przebieg zakończył się kodem `0` i pełnym PASS.
