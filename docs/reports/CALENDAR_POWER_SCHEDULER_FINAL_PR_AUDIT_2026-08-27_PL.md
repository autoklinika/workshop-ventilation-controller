# Calendar Engine + Power Scheduler — finalny audyt PR

Data: 2026-08-27  
Repozytorium: `autoklinika/workshop-ventilation-controller`  
PR: `#85 Integrate Calendar Engine and Power Scheduler with RTC wake`  
Gałąź: `agent/automation-v1-scheduler-assumptions`  
Baza produkcyjna: `main` = `7628c407cfc9c0ea72d262566759ea2d4598fec8`

## 1. Wynik

**FINAL AUDIT: PASS**

Na moment zakończenia audytu kodu nie stwierdzono otwartych blockerów do review/merge.
PR pozostaje Draft i nie wykonano merge do `main`.

Audytowany końcowy SHA kodu przed tym commitem dokumentacyjnym:

`3dd10046d1786483bd25ad5bd62713ab9379a8ea`

GitHub Actions dla dokładnie tego SHA:

- workflow: `Ventilation Core Tests`
- run: `33088601507`
- wynik: `SUCCESS`

## 2. Zakres porównania

Porównanie:

`7628c407cfc9c0ea72d262566759ea2d4598fec8...3dd10046d1786483bd25ad5bd62713ab9379a8ea`

Wynik:

- status: `ahead`
- ahead: 73 commity
- behind: 0
- merge-base: dokładnie produkcyjny `main` `7628c407...`
- 80 zmienionych plików przed dodaniem niniejszego raportu.

Zmiany należą do jednego spójnego zakresu:

- założenia automatyki,
- migracja starego Schedule Engine do Calendar Engine,
- Calendar Engine model/resolver/store/core API/WebGUI,
- RTC wake backend + lokalny agent uprzywilejowany,
- Power Scheduler i runtime,
- AlertV2,
- systemd,
- testy automatyczne,
- harnessy i raporty fizycznych walidacji CM5.

Dwa testy spoza bezpośredniego modułu kalendarza (`history` i `service dashboard`) zmieniają wyłącznie oczekiwany hash `runtime/server.py`, ponieważ migracja Calendar Engine świadomie zmienia protokół core. Nie wykryto przypadkowych zmian funkcjonalnych w tych obszarach.

## 3. Usunięcie starego schedulera

Stary scheduler nie pozostaje jako druga równoległa implementacja.

Usunięte zostały m.in.:

- `application/schedule_controller.py`,
- `domain/schedule.py`,
- `infrastructure/sqlite_schedule_store.py`,
- stare API/GUI schedule,
- testy starego schedule.

Docelowym i jedynym kontraktem kalendarza jest Calendar Engine.

## 4. Bezpieczeństwo planowanego shutdownu

Produkcja nadal nie włącza automatycznego shutdownu.

`deploy/systemd/ventilation-core.service`:

- nie zawiera `--enable-scheduled-shutdown`,
- core nadal działa jako `User=wentylacja`,
- core nadal ma `NoNewPrivileges=true`,
- dodaje tylko zależność startową na lokalny `wvc-rtc-wake.service` oraz jawne ścieżki socketów RTC/host-power.

Power Scheduler przekracza granicę `wvc-host-power` wyłącznie po:

1. poprawnym rozstrzygnięciu Calendar Engine,
2. shutdown-eligible `INACTIVE` + `STANDBY/OFF`,
3. poprawnym `next_wake`,
4. uzbrojeniu RTC,
5. dokładnym read-back RTC zgodnym z oczekiwanym epoch.

Brak poprawnego RTC = brak automatycznego shutdownu.

## 5. Granice uprawnień

RTC agent:

- działa jako root wyłącznie z powodu dostępu do sysfs `wakealarm`,
- jest dostępny tylko przez `AF_UNIX`,
- protokół zawiera wyłącznie `read`, `clear`, `arm`,
- nie ma shell forwarding,
- nie ma `subprocess/systemctl`,
- nie ma ścieżki host-power ani sterowania wentylacją.

`wvc-host-power` zachowuje dotychczasowy protokół:

- `shutdown`,
- `restart`.

Klient host-power został przeniesiony do warstwy infrastructure, a WebUI re-eksportuje ten sam wąski interfejs. Nie dodano nowej komendy uprzywilejowanej.

## 6. Persistence / migracja

Calendar Engine używa istniejącego pliku:

`/var/lib/workshop-ventilation/automation.sqlite3`

ale zapisuje własną tabelę:

`calendar_configuration`.

Stare tabele Schedule Engine mogą pozostać w SQLite jako nieużywane dane historyczne. Runtime Calendar Engine ich nie odczytuje. Nie wykonuje się destrukcyjnego DROP podczas migracji.

Pierwszy start bez konfiguracji Calendar Engine tworzy neutralny `DEFAULT_STANDBY`; nie są wymyślane godziny pracy.

## 7. Poprawki znalezione podczas finalnego audytu

Finalny review przed merge znalazł i usunął dwa problemy jakościowe.

### 7.1. Globalna walidacja konfliktów Calendar

Pierwotnie `replace_configuration()` sprawdzał konflikty przez rozstrzygnięcie jednej daty referencyjnej. Konflikt istniejący wyłącznie w przyszłym `DATE_RANGE` mógł zostać zapisany i ujawnić się dopiero później.

Naprawa:

- dodano `validate_calendar_configuration()`,
- konflikt jest odrzucany przed `store.replace()`,
- sprawdzane są reguły tego samego priorytetu,
- uwzględniane są WEEKLY, SEASON, DATE_RANGE i DATE_EXCEPTION,
- sprawdzane są okna nocne,
- sprawdzane są rozszerzenia PREVENTILATION/PURGE,
- zakres przesunięć dat startowych obejmuje `-3..+3 dni`, co pokrywa maksymalne dozwolone guard-window.

Dodatkowo resolver uwzględnia przyszłą datę reguły, gdy PREVENTILATION zaczyna się poprzedniego dnia, oraz długie PURGE z wcześniejszej daty reguły.

Regresje testują m.in.:

- konflikt przyszłego DATE_RANGE przed zapisem,
- overlap nocnego okna z następnym weekday,
- PREVENTILATION zaczynające się poprzedniego dnia,
- ekstremalny konflikt przy przesunięciu dat reguł o +3 dni.

### 7.2. Ścisłe typy JSON

Parser Calendar wcześniej wykonywał część niejawnych konwersji Pythona (`int(...)`, `str(...)`). W efekcie np. JSON `true` mógł zachowywać się jak integer `1`.

Naprawa:

- brak konwersji bool/text do integer,
- `schema_version=true` jest odrzucane,
- `preventilation_minutes=true` i `"30"` są odrzucane,
- `weekdays=[true]` i `weekdays=["1"]` są odrzucane,
- ID wymagają tekstu,
- godziny wymagają tekstu `HH:MM`,
- enumy wymagają prawidłowych wartości tekstowych.

Core pozostaje autorytatywną granicą walidacji niezależnie od sanitizacji WebGUI.

## 8. Fizyczna walidacja

Zakończone etapy:

- Calendar Engine M3: PASS,
- RTC hardware wake: PASS,
- M4 RTC arm/read-back/clear: PASS,
- M5A RTC gate -> exact shutdown intent: PASS,
- M5B real host-power -> DFR0473 OFF -> CM5 poweroff -> RTC wake -> recovery: PASS,
- M6 runtime integration: PASS,
- M6A non-actuating runtime na CM5: PASS.

M5B potwierdził rzeczywisty restart z RTC około 7,2 s od zaprogramowanego wake.

M6A potwierdził na rzeczywistym CM5, że runtime z scheduled shutdown wyłączonym:

- nie uzbraja RTC,
- nie wysyła host-power,
- nie odcina 12 V,
- nie rebootuje/poweroff CM5,
- przeżywa restart branch core,
- poprawnie wraca do produkcyjnego `main`.

## 9. AlertV2

Polityka:

`2026-08-27.1`

52 wpisy.

Nowe alerty:

- `RTC_WAKE_ARM_FAILED`,
- `HOST_POWER_REQUEST_FAILED`.

Oba pozostają diagnostyczne wobec sterowania wentylacją:

- `affects_control=false`,
- `reaction=continue_degraded`.

Validator nie pozwala nadać im authority nad wentylacją.

## 10. Stan do decyzji właściciela projektu

Po finalnym audycie:

- blockerów kodowych: **0**,
- fizyczne wymagane walidacje: **PASS**,
- CI audytowanego kodu: **PASS**,
- `main`: **nietknięty**,
- PR #85: **Draft**,
- scheduled shutdown w produkcyjnym unit: **OFF**.

Następna akcja wymaga osobnej, jednoznacznej decyzji właściciela projektu o przejściu PR do Ready for Review i/lub merge. Sam finalny audyt nie stanowi zgody na merge.
