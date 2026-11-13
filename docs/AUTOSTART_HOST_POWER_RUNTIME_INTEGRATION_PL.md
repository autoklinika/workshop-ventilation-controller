# WVC CM5 — Autostart → istniejący RTC + host-power (2026-11-13)

## Stan przed integracją (potwierdzony na fizycznym CM5)

- WVC Core/WebUI działają produkcyjnie, w oddzielnych nakładkach źródeł.
- `/api/v1/autostart/2026`: rewizja 3; `enabled=true`,
  `schedule_enabled=true`, poniedziałek–sobota `08:00–18:30`,
  niedziela wyłączona i ustawowe święta wyłączone, bez ręcznych wyjątków.
- Istniejący `wvc-auto-poweroff.timer` miał `OnCalendar=*-*-* 19:00:00`,
  uruchamiał `wvc-auto-poweroff.service`, a ten
  `/usr/local/libexec/wvc-power-schedule.py shutdown`.
- Istniejący skrypt uzbrajał następne **08:00 bez kalendarza**, następnie
  przekazywał polecenie `shutdown` do `wvc-host-power` po preflight i
  odczycie RTC wakealarm. Ten szlak bezpieczeństwa **pozostaje bez zmian**.
- `POWER_OFF_ON_HALT=1`, `WAKE_ON_GPIO=0`, `NTPSynchronized=yes`,
  `/dev/rtc0` i `wakealarm` istnieją, `wvc-host-power` aktywny.
  Oryginalny skrypt `check` wykonał się z wynikiem **PASS**.
- Wbudowany w `ventilation-core` eksperymentalny PowerScheduler pozostaje
  wyłączony (`scheduled_shutdown_enabled=false`), aby nie tworzyć
  drugiego wykonawcy.

## Projekt integracji

Uruchomienie nadal wykonuje ta sama para
`wvc-auto-poweroff.timer` / `wvc-auto-poweroff.service`.
Dwa niewielkie drop-iny przełączają:

1. Timer z twardej godziny 19:00 na regularne sprawdzanie raz na minutę,
   przy `Persistent=false`.
2. `ExecStart` usługi na root-owned
   `/usr/local/libexec/wvc-autostart-gate.py tick`.

Nowa bramka pobiera wyłącznie przez loopback i WebUI dane
`GET /api/v1/autostart/YYYY` z Core (jedno źródło prawdy, konfiguracja
zapisywana jest w SQLite). Waliduje strukturę całego kalendarza (365/366
dni), wybrany dzień, godziny oraz globalne przełączniki.

Bramka **nie wywołuje shutdown** przy:
- wyłączonym Autostarcie lub wyłączonym harmonogramie;
- niedzieli, święcie lub innym wyłączonym dniu;
- niekompletnych godzinach, braku następnej daty wybudzenia;
- błędzie API, błędnej dacie/czasie, konflikcie rewizji;
- jakiejkolwiek minucie innej niż skonfigurowana minuta zakończenia.

Dopiero w minucie zakończenia aktywnego dnia pracy (w aktualnej
konfiguracji **18:30**, maksymalnie 60 sekund okna) skrypt wybiera następny
dzień oznaczony `enabled=true` z poprawną godziną włączenia.
Następnie importuje **bez zmian** istniejący, root-owned plik
`/usr/local/libexec/wvc-power-schedule.py` i wykonuje:

1. `validate_hardware()` (bootloader, RTC, socket host-power),
2. `arm_wakeup(next_start)` (uzbrojenie i readback RTC),
3. `request_safe_shutdown()` (przez istniejący `wvc-host-power`).

RTC nie jest uzbrajany przy samym zapisie konfiguracji ani przy instalacji.

### Przykłady dla aktualnej konfiguracji

| Zakończenie | Następne wybudzenie |
| --- | --- |
| Piątek 13.11.2026, 18:30 | Sobota 14.11.2026, 08:00 |
| Sobota 14.11.2026, 18:30 | Poniedziałek 16.11.2026, 08:00 |
| Środa 23.12.2026, 18:30 | Poniedziałek 28.12.2026, 08:00 |
| Czwartek 31.12.2026, 18:30 | Sobota 02.01.2027, 08:00 |

Wyjątki dzienne z UI mają pierwszeństwo nad dniem tygodnia i świętem.
Aby wyjątkowo automatycznie uruchomić CM5 w niedzielę, trzeba również
podać godziny niedzieli w szablonie tygodniowym. Data aktywna bez
godzin nie jest uznawana za termin wybudzenia.

## Instalacja na fizycznym CM5

**Jednorazowa czynność operatora wymagająca sudo** (root-owned
`/etc/systemd/system` i `/usr/local/libexec`).

Z terminala CM5:

```bash
sudo bash /home/wentylacja/wvc-autostart-power-integration/tools/install_wvc_autostart_host_timer.sh
```

Instalator:
- wykonuje read-only `wvc-power-schedule.py check`;
- sprawdza faktyczny harmonogram przez API, odmawia instalacji w
  bezpośrednim sąsiedztwie momentu wyłączenia;
- robi backup dotychczasowej usługi i timera oraz oryginalnego skryptu
  w `/var/backups/wvc-autostart-deploy-<data>`;
- instaluje root-owned `wvc-autostart-gate.py` (0755) i dwa drop-iny;
- wykonuje wyłącznie `daemon-reload` i restart **timera**;
  nie restartuje `ventilation-core`, WebUI ani wvc-host-power;
- sprawdza faktycznie załadowane `ExecStart`, `TimersCalendar`,
  działanie timera oraz stan usług;
- przy błędzie odtwarza poprzednie drop-iny i przywraca timer.

Instalator nie wykonuje testowego wyłączenia ani nie uzbraja RTC.
Do testu wykonania trzeba zachować czas do planowego końca pracy.

**Ważne**: dopóki instalator nie zostanie uruchomiony z uprawnieniami
administratora, w systemie nadal pozostaje **stary timer 19:00**.
Sama obecność plików w repo lub ustawień w HMI nie zmienia jego działania.

### Kontrola po instalacji

```bash
systemctl list-timers --all wvc-auto-poweroff.timer
systemctl cat wvc-auto-poweroff.service wvc-auto-poweroff.timer
python3 /usr/local/libexec/wvc-autostart-gate.py plan
systemctl is-active wvc-auto-poweroff.timer ventilation-core.service wvc-web-ui.service
```

Oczekiwane: timer co minutę, ExecStart bramki, odpowiedź
`WVC_AUTOSTART_PLAN` bez aktywnego shutdown poza 18:30, aktywne
usługi. W momencie 18:30 potwierdzić w journalu:

```bash
journalctl -u wvc-auto-poweroff.service --no-pager -n 40
```

### Wycofanie

W pierwszej kolejności zatrzymać timer (wymaga sudo),
przywrócić lub usunąć dwa pliki `50-autostart-calendar.conf`
z katalogów `wvc-auto-poweroff.*.d` i wydać
`sudo systemctl daemon-reload && sudo systemctl start wvc-auto-poweroff.timer`.
Oryginalny skrypt `wvc-power-schedule.py` **nie został zmodyfikowany**.

## Weryfikacja kodu (bez aktuacji)

```bash
cd /home/wentylacja/wvc-autostart-power-integration
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_autostart_power_gate.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_autostart_plan.py' -v
bash -n tools/install_wvc_autostart_host_timer.sh
python3 deploy/cm5/wvc-autostart-power-gate.py plan
```

**Granice**: harmonogram dotyczy zasilania CM5, a nie poleceń start/stop
wentylatorów. Bezpieczny shutdown przez `wvc-host-power` zatrzymuje
urządzenia według dotychczasowej procedury. Po wybudzeniu tryb AUTO wentylacji pozostaje w HOLD/MANUAL, chyba że
osobna root-owned usługa jednorazowego wznowienia AUTO została
zainstalowana i zweryfikowała planowy boot, potwierdzone wcześniejsze
AUTO i wszystkie interlocki. Dokumentacja:
`docs/WVC_RTC_SCHEDULED_AUTO_RESUME_PL.md`. Nie łączyć równolegle z Core PowerScheduler
bez jawnej decyzji architektonicznej.
