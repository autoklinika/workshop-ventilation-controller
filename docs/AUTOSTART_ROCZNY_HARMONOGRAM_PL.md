# WVC — Ustawienia → Autostart (wersja produkcyjna)

## Zakres
Nowa zakładka **AUTOSTART** w `/settings`, odseparowana od istniejących
zakładek **HARMONOGRAMY** (obecność w strefach) i **ZIGBEE**.

- **Autostart włącz/wyłącz** — nadrzędny przełącznik planu.
- **Harmonogram włącz/wyłącz** — niezależny przełącznik harmonogramu.
- **Tydzień (ISO 1–7)** — każdy dzień ma opcję aktywny/nieaktywny, godzinę
  włączenia i godzinę wyłączenia (od 00:00 do 23:59, w obrębie jednego dnia).
- **Kalendarz 12 miesięcy** — nawigacja między latami 2025–2100, włączenie
  lub wyłączenie dowolnego dnia, przywrócenie domyślnego stanu, oznaczenia
  świąt i ręcznych wyjątków.
- Domyślnie **niedziele i polskie ustawowe święta są wyłączone**; pozostałe
  dni, **w tym soboty**, są włączone. Godziny są **nieustawione**, aby nie
  zgadywać czasu pracy warsztatu.
- Święta ruchome: Wielkanoc, Poniedziałek Wielkanocny, Zesłanie Ducha
  Świętego, Boże Ciało. Święta stałe obejmują także Wigilię (dzień wolny
  ustawowo od 2025 roku).

## Kontrakt i przechowywanie

`GET /api/v1/autostart/YYYY` zwraca konfigurację, rewizję, pełną listę
365/366 dni, oznaczenia świąt oraz `actuation_enabled: false`.
`POST /api/v1/autostart` przyjmuje dokładnie:
`{ "year": YYYY, "expected_revision": N, "config": {...} }`.

Konfigurację weryfikuje **ventilation-core**, który przechowuje ją w
`automation.sqlite3`, tabela `autostart_plan` (singleton, JSON,
rewizja, transakcyjny zapis). Zapis jest odporny na konflikt rewizji.
Widok nie używa `localStorage` jako źródła prawdy.

Wewnętrzne pole `config`:
- `enabled`: boolean,
- `schedule_enabled`: boolean,
- `week`: dokładnie 7 wierszy `weekday, enabled, start_local, end_local`,
- `overrides`: 0–512 wpisów `date, enabled` z wyjątkami dat.

Wyjątek ma wyższy priorytet niż święto/niedziela i tydzień. Brak
wpisu oznacza przywrócenie wartości domyślnej.

## Granica bezpieczeństwa — plan i wykonanie

**Samo zapisanie planu w API nie wyłącza ani nie uruchamia CM5 ani
wentylatorów.** Pole `actuation_enabled: false` dotyczy braku bezpośredniej
aktuacji z API/ventilation-core, **nie stanowi diagnozy aktualnego stanu
timera systemd**. Do rzeczywistego wykonania harmonogramu służy odrębna
usługa `wvc-auto-poweroff.service` wywoływana przez
`wvc-auto-poweroff.timer`.

Po instalacji drop-inów produkcyjnych usługa co minutę sprawdza czas
zapisany w Autostarcie. Wyłącznie na końcu aktywnego dnia pracy
wyznacza następny dozwolony termin i wykonuje dawny, zweryfikowany
proces `wvc-power-schedule.py` → RTC readback → `wvc-host-power`.
Niedziela i święta pozostają wyłączone; ręczny wyjątek jest nadrzędny.

**Aktualny stan produkcyjnego wykonawcy ustala się przez systemd**, nie
samą wartość `actuation_enabled`. Pozostałe niezależne automatyki i
zabezpieczenia wentylacji nie ulegają zmianie. Po wybudzeniu CM5
AUTO wentylacji nadal wymaga potwierdzenia/operatora, jeśli Core
pozostaje w HOLD/MANUAL — nie przełączamy go bez audytu interlocków.

Dokumentacja instalacji, walidacji i rollbacku:
`docs/AUTOSTART_HOST_POWER_RUNTIME_INTEGRATION_PL.md`.

## Testy

- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_autostart_plan.py'`
- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_autostart_power_gate.py'`
- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_autostart_core_runtime.py'`
- `node --check src/ventilation_core/web/static/autostart.js`

Wdrożenie na produkcyjnym CM5 wykonano i zweryfikowano
13 listopada 2026 r. (harmonogram systemd co minutę, bez wstrzymania
aktualnej pracy CM5). Pierwszy fizyczny cykl shutdown/RTC wake należy
zweryfikować po jego wykonaniu.
