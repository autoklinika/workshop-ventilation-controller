# WVC – harmonogram POWER OFF 19:00 / POWER ON 08:00

## Cel i zakres

Codziennie o **19:00 czasu Europe/Warsaw**: kontrolowany POWER OFF CM5 przez istniejącą usługę `wvc-host-power` (STOP lokalnych EC, próba zatrzymania AERO, 12 V OFF, systemctl poweroff), wraz z istniejącym `wvc-hmi-power` (Android SLEEP w ExecStop). Codziennie o **08:00**: sprzętowe wybudzenie CM5 z RTC, zwykły boot i automatyczne wybudzenie HMI po gotowości WebGUI. Nie zmieniamy logiki AUTO/MANUAL.

## Implementacja

- `tools/wvc_power_schedule.py`: sprawdza RTC, `POWER_OFF_ON_HALT=1`, `WAKE_ON_GPIO=0`, obecność socketu host-power; wyznacza następne 08:00 według `Europe/Warsaw` (również DST), uzbraja i weryfikuje `/sys/class/rtc/rtc0/wakealarm`, dopiero potem wysyła istniejącą akcję `{"action":"shutdown"}` do `/run/wvc-host-power/host-power.sock`.
- `deploy/systemd/wvc-auto-poweroff.timer`: codziennie 19:00, `Persistent=false` zapobiega zaległemu wyłączeniu tuż po ręcznym uruchomieniu w nocy.
- `deploy/systemd/wvc-auto-poweroff.service`: jednorazowa akcja uruchamiana przez timer. W razie niepoprawnego alarmu RTC lub nieosiągalnego host-power **nie wyłącza** CM5.
- `wvc-hmi-power.service` już obsługuje Android WAKE (ExecStart) / SLEEP (ExecStop), `192.168.1.123:5555`; bez dodatkowych timerów HMI.

## Wdrożenie / weryfikacja

Wdrożenie celowo jest niezależne od gałęzi produkcyjnej main:

```bash
sudo install -m 0755 tools/wvc_power_schedule.py /usr/local/libexec/wvc-power-schedule.py
sudo install -m 0644 deploy/systemd/wvc-auto-poweroff.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/wvc-auto-poweroff.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo python3 /usr/local/libexec/wvc-power-schedule.py check
sudo python3 /usr/local/libexec/wvc-power-schedule.py arm-only
sudo systemctl enable --now wvc-auto-poweroff.timer
systemctl list-timers --all wvc-auto-poweroff.timer
```

**Uwaga:** samo uzbrojenie alarmu potwierdza zapis RTC, nie potwierdza rzeczywistego wybudzenia sprzętowego. Pierwsze pełne wyłączenie o 19:00 i start o 08:00 wymagają kontroli po fakcie. Ręczny `PWR_BUT` pozostaje drogą awaryjną. Zegar RTC potrzebuje podtrzymania VBAT w razie utraty głównego zasilania; przy stabilnym 5 V alarm może działać bez baterii.

## Wyłączenie harmonogramu

```bash
sudo systemctl disable --now wvc-auto-poweroff.timer
```

Wyłączenie timera nie kasuje już ustawionego alarmu RTC. Żeby go świadomie wyczyścić: `echo 0 | sudo tee /sys/class/rtc/rtc0/wakealarm`.
