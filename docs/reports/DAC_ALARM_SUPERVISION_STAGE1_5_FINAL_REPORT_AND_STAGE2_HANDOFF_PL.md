# DAC Alarm Supervision Stage 1.5 — raport końcowy i przekazanie do Stage 2

Data: 2026-08-01

Gałąź: `agent/dac-alarm-supervision-stage1-5`

Baza: `main`, commit `54e61c4756a7bf73a8f9d838490ea22372d4b325`.

## Wynik etapu

Stage 1.5 został zakończony funkcjonalnie i zwalidowany na docelowym Raspberry Pi Compute Module 5 z rzeczywistym DFRobot DFR0971 / GP8403 oraz fanem EC.

Etap wprowadza wspólny fundament diagnostyki i alarmów, który będzie wykorzystany w kolejnych etapach dla RS-485, SEN55, modułów KAmod i rekuperatora.

## Zrealizowane funkcje

- rzeczywisty okresowy test komunikacji I2C z GP8403,
- rozróżnienie stanu procesu sprzętowego od stanu komunikacji z DAC,
- tryb `FAULT`,
- alarm krytyczny `DAC_COMMUNICATION_LOST`,
- pola `output_state_known`, `consecutive_hardware_failures` i `active_alarms`,
- natychmiastowe oznaczenie stanu wyjść jako nieznanego po pierwszym błędzie,
- aktywacja alarmu po trzech kolejnych błędach okresowych,
- natychmiastowa aktywacja alarmu po błędzie komendy wykonawczej,
- blokada nowych nastaw podczas awarii,
- pozostawienie procesu rdzenia aktywnego przy braku DAC,
- automatyczne wykrycie powrotu urządzenia,
- bezpieczne odzyskanie zawsze do `STOP / 0 V / 0 V`,
- brak automatycznego przywracania wcześniejszych napięć,
- bezpieczna obsługa restartu procesu sprzętowego.

## Walidacja automatyczna

Lokalnie wykonano pełny zestaw testów:

```text
Ran 18 tests
OK
```

Dodatkowo wykonano pełną kompilację modułów przez `python -m compileall`.

## Walidacja sprzętowa CM5

### Start z podłączonym DAC

PASS:

- `mode: STOP`,
- `hardware_ready: true`,
- `output_state_known: true`,
- brak aktywnych alarmów,
- fan nie uruchomił się.

### Odłączenie DAC przy 0 V

PASS:

- rdzeń pozostał dostępny,
- `mode: FAULT`,
- `hardware_ready: false`,
- `output_state_known: false`,
- aktywny alarm `DAC_COMMUNICATION_LOST`,
- poprawnie zarejestrowany błąd `Errno 121 Remote I/O error`,
- licznik kolejnych błędów zwiększał się,
- fan pozostał zatrzymany.

### Ponowne podłączenie DAC

PASS z obserwacją:

- komunikacja została automatycznie odzyskana,
- alarm został wyczyszczony,
- licznik błędów wrócił do zera,
- stan wrócił do `STOP`,
- oba kanały zostały zapisane jako 0 V,
- poprzednia nastawa nie została przywrócona.

Obserwacja: przy ponownym podłączeniu całego przewodu Gravity/I2C fan wykonuje krótki, delikatny ruch. Zjawisko jest powtarzalne i związane najprawdopodobniej z ponownym zasileniem DAC przed wykonaniem konfiguracji i zapisem 0 V. Nie jest to przywrócenie wcześniejszej nastawy przez aplikację.

## Ograniczenie fizyczne

Przy utracie I2C podczas pracy na niezerowym napięciu oprogramowanie nie może zagwarantować wymuszenia 0 V, ponieważ GP8403 może utrzymać ostatnią wartość. Pełne sprzętowe fail-safe wymagałoby niezależnego układu odcinającego lub zwierającego sygnał sterujący do 0 V.

Dla obecnego lokalnego wdrożenia ograniczenie jest jawnie udokumentowane i zaakceptowane do dalszego rozwoju.

## Stan końcowy Stage 1.5

Etap uznaje się za zakończony.

Stabilne kryteria przekazania:

- alarm braku komunikacji DAC działa,
- stan awaryjny jest jawny i dostępny przez API,
- odzyskanie komunikacji jest automatyczne,
- odzyskanie nie uruchamia poprzedniej nastawy,
- rdzeń pozostaje aktywny podczas awarii,
- testy automatyczne i sprzętowe zakończone wynikiem PASS.

## Stage 2 — RS-485 bring-up

Następny etap powinien objąć wyłącznie fundament komunikacyjny RS-485, bez pełnej logiki urządzeń:

1. wybór i uruchomienie interfejsu RS-485 na CM5,
2. identyfikację portu i stabilnej nazwy urządzenia,
3. test nadawania i odbioru,
4. test Modbus RTU z jednym urządzeniem,
5. weryfikację timeoutów, CRC i zachowania po odłączeniu,
6. przygotowanie osobnego procesu `rs485-worker`,
7. przygotowanie neutralnego interfejsu aplikacyjnego dla przyszłych urządzeń.

Stage 3 wykorzysta model alarmów z Stage 1.5 do obsługi awarii urządzeń RS-485.
