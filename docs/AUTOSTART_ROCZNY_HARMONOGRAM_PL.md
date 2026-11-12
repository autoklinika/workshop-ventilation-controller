# WVC — Ustawienia → Autostart (wersja przygotowawcza)

## Zakres
Nowa zakładka **AUTOSTART** w `/settings`, odseparowana od istniejących
zakładek **KALENDARZ** (kontekst pracy automatyki) i **ZIGBEE**.

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

## Granica bezpieczeństwa — etap bez aktuacji

**Żaden zapis ani przełącznik Autostartu nie wyłącza, nie uruchamia
i nie wybudza CM5, EC ani AERO.** Ta funkcja stanowi trwały **plan**
pracy hosta, a nie upoważnienie do sterowania. Nie zmienia:
- istniejącej konfiguracji Calendar Engine / Control Engine,
- `--enable-scheduled-shutdown` i Power Scheduler Runtime,
- układu RTC wake i weryfikacji `wakealarm`,
- sterowania MANUAL/AUTO i priorytetów bezpieczeństwa,
- poleceń host-power i stanu usług systemd.

### Dalsza integracja (oddzielne zatwierdzenie)
1. Zweryfikować rozróżnienie harmonogramu zasilania CM5 od minimum
   wentylacji i polityk jakości powietrza.
2. Dodać wykonawcę czytającego `autostart_plan` z explicit authority,
   weryfikacją RTC readback, awarii czasu/NTP/DST, odmową bez zaplanowanego
   następnego wake oraz ochroną przed wyłączeniem przy aktywnym alarmie.
3. Rozstrzygnąć zachowanie aktywnego AUTO, MANUAL, PURGE i alertów.
4. Wykonać testy na CM5 oraz HMI, symulację przerwy zasilania i test
   fizyczny RTC przed dopuszczeniem aktuacji.

## Testy
`PYTHONPATH=src python3 -m unittest tests.test_autostart_plan -v`
oraz `node --check src/ventilation_core/web/static/autostart.js`.

**Bez wdrożenia na produkcyjny CM5 i bez merge do `main`.**
