# WVC — harmonogram zdarzeniowy RTC + AUTO (2026-11-14)

## Założenie i granice

Zastępuje eksperymentalny nadzorca wyzwalany co minutę
`wvc-schedule-keeper.timer`, a także stary minutowy
`wvc-auto-poweroff.timer` jako źródło automatycznego zamknięcia.
Nie zmienia mechanizmu bezpiecznego wyłączenia:
`wvc-autostart-gate.py tick` → RTC readback →
`wvc-power-schedule.py` → `wvc-host-power`.
Core i AUTO pozostają właścicielem sterowania wentylatorami.

Harmonogram jest **zdarzeniowy** — bez stałego odpytywania każdego
dnia/minuty i bez zakodowanych godzin lub dni tygodnia:

- **BOOT CM5:** `wvc-schedule-boot.service` czyta bieżący Autostart przez
  lokalny socket `ventilation-core`, sprawdza RTC i tworzy dwa
  jednorazowe, dokładne timery `systemd-run --on-calendar`:
  następny *START* i następny *STOP* wynikające z kalendarza
  i pełnej listy świąt/wyjątków.
- **ZAPIS W HMI:** po skutecznym zatwierdzeniu rewizji konfiguracji WebGUI
  zapisuje sygnał `autostart-changed.signal` na NVMe. `systemd.path`
  uruchamia jednorazowo `wvc-schedule-change.service`, który
  reprogramuje RTC i oba zdarzenia (nie wywołuje STOP ani AUTO przy
  zwykłym zapisie poza godziną rozpoczęcia).
- **PLANOWANY START:** jednorazowy timer uruchamia
  `wvc-schedule-keeper.py start`. Sprawdza interlocki AUTO, znacznik
  zaplanowanego dnia, czujniki SEN55, TACHO, DAC, AERO, HOLD i fault.
  Przy niedostępnym czujniku próbuje tylko przez maksymalnie 135 s;
  nie wykonuje ślepego AUTO. Zapisuje jednorazowy claim przed komendą
  `auto-resume` — ręcznego STOP później już nie cofnie.
- **PLANOWANY STOP:** jednorazowy timer woła istniejące
  `wvc-autostart-gate.py tick`. Bramka powtórnie sprawdza aktualny
  kalendarz i minutę zakończenia, a następnie wykonuje niezmienioną
  procedurę bezpiecznego zatrzymania, uzbrojenia RTC i wyłączenia CM5.
- **RĘCZNE ZAMKNIĘCIE CM5:** alarm RTC jest stale przygotowywany przy
  BOOT i po zapisanej zmianie. Na kolejnym uruchomieniu procesu
  `wvc-host-power` dodatkowo uruchamia jednostkę
  `wvc-schedule-keeper-arm.service` przed STOP i poweroff.
  Nie restartować `wvc-host-power` w trakcie aktywnej pracy,
  ponieważ zarządza domeną zasilania 12 V.

Trwałe źródło prawdy: `automation.sqlite3`, nie pliki w repo.
Kopię zmian kalendarza należy zapisywać przez API HMI; zapisane
bezpośrednio w SQLite dane omijają zdarzenie WebUI i wymagają
ręcznego uruchomienia `wvc-schedule-change.service`.
Na kolejnym boocie harmonogram jest zawsze odczytywany od nowa.

## Ręczne działanie poza harmonogramem

Jeśli operator uruchomi CM5 lub wentylację w sobotę OFF i później
wyłączy, system nie zmienia kolejnego dozwolonego startu.
Przy aktualnej rewizji 4:

- w sobotę 14.11.2026 AUTO nie uruchamia się z harmonogramu,
- poniedziałek 16.11.2026 08:00 — następny START,
- poniedziałek 16.11.2026 18:30 — następny STOP.

Jeśli operator w sobotę użyje AUTO/MANUAL, HOLD zostanie zachowany do
poniedziałkowego startu; wtedy dopuszczony jest wyłącznie zwykły
MANUAL/STOP powstały **przed** planowanym rozpoczęciem.
Późniejszy ręczny STOP tego samego dnia, trwały EXPLICIT HOLD, fault,
brak danych, nieważny zegar lub niesprawny sprzęt blokują AUTO.

## Wdrożenie

Po zmergowaniu do `main` i zsynchronizowaniu CM5:

```bash
sudo bash /home/wentylacja/workshop-ventilation-controller/tools/install_wvc_event_schedule.sh
```

Instalator:
- sprawdza obecne usługi, stan zegara, RTC i zakres okna planowego STOP;
- robi backup do `/var/backups/wvc-event-schedule-<timestamp>`;
- instaluje root-owned skrypt, BOOT unit, jednostkę pre-shutdown
  i `systemd.path` do zapisu kalendarza;
- uzbraja RTC i jednorazowe START/STOP; **dopiero potem**
  wyłącza stary minutowy `wvc-auto-poweroff.timer`;
- restartuje **tylko** `wvc-web-ui.service`, aby włączyć
  nowy notifier HMI; nie restartuje Core, host-power, wentylatorów
  ani CM5;
- sprawdza statusy, udostępnia rollback.

Po instalacji:

```bash
systemctl list-timers --all | grep 'wvc-scheduled-'
systemctl is-active wvc-schedule-change.path
systemctl is-enabled wvc-schedule-boot.service
python3 /usr/local/libexec/wvc-schedule-keeper.py plan
date -d @"$(cat /sys/class/rtc/rtc0/wakealarm)" -Is
```

Jeśli systemd-run nie zdoła utworzyć dokładnych timerów,
instalator nie powinien dezaktywować starego mechanizmu. Podczas
rollbacku należy sprawdzić stan przejściowych timerów, ponieważ
`systemd-run` tworzy jednostki w systemowym managerze.

**Ograniczenie:** przy normalnej pracy Core i WebUI dostępne są przy
zmianie kalendarza. Bez zasilania CM5 harmonogram nie może reagować
na zdalną zmianę bazy. Niezbędna jest także sprawna bateria RTC i
zgodna konfiguracja bootloadera. Sprzętowe wybudzenie i pierwsze
wznowienie AUTO należy potwierdzić logami po fizycznym cyklu.

## Weryfikacja

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_wvc_event_scheduler.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_wvc_schedule_keeper.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

Nie wykonywać `wvc-autostart-gate.py tick` ręcznie o godzinie
zakończenia: byłoby to realne polecenie wyłączenia CM5.

## Korekta potwierdzania timera systemd-run (14.11.2026)

Pierwsza próba instalacji około 09:36 utworzyła transient timer START,
ale skrypt błędnie uznał brak standardowego wyjścia `stdout` za błąd.
Logi systemd potwierdziły utworzenie jednostki i późniejsze
anulowanie jej podczas rollbacku. Stary minutowy timer pozostał aktywny,
RTC dalej wskazywał poniedziałek 16.11.2026 o 08:00, a Core i WebGUI
nie zostały wyłączone.

Po poprawce `systemd-run` jest uznawany za skuteczny wyłącznie gdy:
- jego kod zakończenia oznacza sukces (komunikat na stderr lub brak
  komunikatu nie stanowi błędu),
- `systemctl is-active --quiet <unit>.timer` potwierdza aktywny timer,
- `systemctl show -p Unit --value <unit>.timer` wskazuje oczekiwaną
  usługę `<unit>.service`.

Na niepowodzenie skrypt próbuje zatrzymać nową jednostkę i nie aktualizuje
zapisu trwałego. Do testów dołożono wariant poprawnego `systemd-run`
z pustym stdout oraz scenariusze braku aktywnego timera i błędnej
jednostki wykonawczej. Instalator przy ponownej próbie tworzy
i weryfikuje **zarówno START, jak i STOP**, zanim wyłączy
dotychczasowy timer.
