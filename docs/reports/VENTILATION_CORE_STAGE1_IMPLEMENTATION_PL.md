# ventilation-core — Stage 1

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Cel

Pierwszy działający rdzeń oddziela logikę sterowania od sprzętu i od przyszłych interfejsów użytkownika.

## Podział odpowiedzialności

```text
ventilationctl / przyszłe GUI
        ↓ lokalny kontrakt JSON przez Unix socket
runtime/server.py
        ↓
application/service.py
        ↓
domain/policy.py + domain/models.py
        ↓
infrastructure/process_actuator.py
        ↓ osobny proces
infrastructure/hardware_worker.py
        ↓
infrastructure/dfr0971_actuator.py
        ↓
GP8403 / I²C / DFR0971
```

## Procesy i rdzenie CPU

- proces główny: stan autorytatywny, walidacja komend, lokalne API i nadzór,
- proces sprzętowy: wyłączny właściciel magistrali I²C i DFR0971,
- przyszłe procesy: Modbus/RS-485, akwizycja pomiarów, historia i publiczne API.

Proces sprzętowy jest izolowany, aby błąd komunikacji lub biblioteki sprzętowej nie uszkodził stanu warstwy domenowej. Nadzorca wykonuje cykliczny health-check i uruchamia workera ponownie, jeżeli proces zniknie. Nowy worker przy starcie zawsze ustawia oba kanały na 0 V.

## Obowiązujące reguły

- `0 V` oznacza STOP,
- zakres pracy wynosi `1–10 V`,
- wartości pomiędzy `0 V` i `1 V` są odrzucane,
- kanał 0 oznacza nawiew,
- kanał 1 oznacza wyciąg,
- tylko proces sprzętowy ma dostęp do I²C,
- przy kontrolowanym zamknięciu oba kanały są zerowane,
- funkcja nieulotnego `store` nie jest implementowana.

## Zakres Stage 1

Stage 1 udostępnia lokalne komendy:

```text
ventilationctl status
ventilationctl set --supply 2 --extract 3
ventilationctl stop
ventilationctl shutdown
```

Nie obejmuje jeszcze automatyki jakości powietrza, harmonogramów, Modbus, Tacho, historii ani publicznego REST API.

## Walidacja programowa

Lokalnie wykonano:

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Wynik: `9/9 PASS`.

Testy obejmują:

- domenową walidację zakresu napięć,
- aktualizację autorytatywnego stanu aplikacji,
- zatrzymanie przed zamknięciem rdzenia,
- mapowanie kanałów GP8403,
- konwersję napięcia na kod DAC,
- zerowanie obu kanałów.

GitHub Actions wykonuje również `compileall` i pełny zestaw testów jednostkowych.

## Ograniczenie programowego fail-safe

Miękki restart CM5 lub nagłe zakończenie procesu może pozostawić ostatnie napięcie na zasilanym DAC. Nadzorca skraca ten okres przez automatyczne ponowne uruchomienie procesu sprzętowego, który zeruje kanały podczas startu, ale nie zastępuje sprzętowego mechanizmu fail-safe.

## Następna walidacja na CM5

1. pobrać aktualny kod,
2. uruchomić testy jednostkowe,
3. zainstalować pakiet w trybie edytowalnym,
4. uruchomić rdzeń ręcznie,
5. potwierdzić, że start rdzenia zeruje oba kanały,
6. sprawdzić `status`, `set`, `stop` i kontrolowane zamknięcie,
7. dopiero po walidacji ręcznej włączyć usługę `systemd`.
