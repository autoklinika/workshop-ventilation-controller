# WVC — bezpieczne wznowienie AUTO po planowym wybudzeniu CM5 przez RTC

## Cel i stan przed zmianą (13.11.2026)

Obowiązujący harmonogram CM5 z `Ustawienia → Autostart` włącza CM5
o 08:00 i wyłącza o 18:30 w aktywne dni pracy.
Zapis z HMI trafia do `automation.sqlite3` i jest odczytywany przez
`wvc-auto-poweroff.timer` → `wvc-auto-poweroff.service` →
`/usr/local/libexec/wvc-autostart-gate.py` →
**dotychczasowy** `wvc-power-schedule.py` → `wvc-host-power`.

Gdy host-power zatrzymuje DAC i AERO, core celowo zapisuje trwały
HOLD/MANUAL. Bez nowej procedury kolejny start CM5 nie przechodzi
automatycznie w AUTO. Wykonano audyt: przed zmianą bieżące AUTO było
aktywne, bez fault latch, a kontrola RTC/timera działała.

## Rozwiązanie

Nie usuwamy zabezpieczenia MANUAL po dowolnym restarcie.

1. **Tylko planowe zamknięcie** z aktywnego dnia kalendarza może zapisać
   jednorazowe upoważnienie do wznowienia AUTO.
2. Bramkę zasilania wykonuje wciąż systemowy timer; przed przekazaniem
   polecenia do **niezmienionego** RTC/host-power pobiera status
   `ventilation-core` przez lokalny socket Unix.
3. Upoważnienie tworzy tylko wtedy, gdy AUTO było **rzeczywiście aktywne**
   (bez HOLD, zatrzaśniętej awarii ani krytycznych alarmów).
   Przy ręcznym MANUAL, awarii, nieznanym stanie lub wyłączonej automatyce
   *nie powstaje* upoważnienie i boot pozostaje MANUAL.
4. Przed shutdown root zapisuje plik
   `/var/lib/wvc-scheduled-auto/next-wake.json`
   (katalog root 0700, ticket 0600). Zawiera czas wybudzenia UTC,
   identyfikator bieżącego uruchomienia Linux, rewizję kalendarza i
   znacznik utworzenia. Sam zapis nie wykonuje poleceń sprzętowych.
5. Przy następnym rozruchu root-owned
   `wvc-rtc-auto-resume.service` sprawdza token, **nowe boot ID**,
   zsynchronizowany czas, datę początku systemu blisko zaplanowanego
   wybudzenia oraz aktualny Autostart (ta sama rewizja i godzina).
   Poza oknem 08:00 +20 min i bez tokenu brak wznowienia.
6. Przed wysłaniem istniejącej komendy `auto-resume` musi zostać
   potwierdzony STOP-related HOLD po zamknięciu host-power,
   gotowość DAC, obu TACHO, obu SEN55, AERO i brak krytycznych alarmów
   i fault latch. Po weryfikacji token jest **zużywany jednorazowo**.
7. Dopiero istniejące `ActiveWorkshopAuto.resume()` zwalnia HOLD.
   Ta metoda nadal weryfikuje interlocki i dopiero normalna pętla
   wentylacji dobiera nastawy EC i AERO.

**Bezpośrednia, ręczna komenda AUTO/MANUAL pozostaje dostępna w HMI.**
Ręczne STOP, MANUAL i awarie nie są kasowane przez nową usługę.

### Zakres ograniczeń

Linux/RPi nie udostępnia tutaj potwierdzonego, stabilnego sygnału
atrybucji, czy boot zainicjował właśnie alarm RTC, a nie fizyczny
przycisk dokładnie w tym samym czasie. Dlatego upoważnienie bazuje na:
poprzednim autoryzowanym planowym shutdownie, jednorazowym pliku root,
nowym boot ID, lokalnym btime i wąskim oknie RTC. Nie jest to formalne
potwierdzenie przyczyny startu sprzętu. W razie niepewności system
zostaje w MANUAL.

Jeżeli AUTO przed zamknięciem było MANUAL, po wybudzeniu nadal będzie
MANUAL. Jeśli po wybudzeniu TACHO, SEN55, AERO lub DAC nie są gotowe,
AUTO pozostaje zablokowane. Nie uruchamiamy wentylacji bez potwierdzonych
warunków wykonawczych.

## Instalacja produkcyjna (po merge do main)

Pakiet wymaga jednej **jawnej autoryzacji sudo** na CM5:

```bash
sudo bash /home/wentylacja/workshop-ventilation-controller/tools/install_wvc_rtc_auto_resume.sh
```

Instalator:
- wykonuje odczyt i kontrolę źródła timera, RTC i statusu usług;
- nie wykonuje `shutdown`, `arm-only`, `auto-resume` ani nie modyfikuje
  bieżącego trybu wentylacji;
- tworzy backup do `/var/backups/wvc-rtc-auto-resume-...`;
- instaluje root-owned `wvc-rtc-auto-resume.py`, zaktualizowaną bramkę
  `wvc-autostart-gate.py` i nowy unit `wvc-rtc-auto-resume.service`;
- `systemctl daemon-reload` + `systemctl enable` (bez `--now`);
- **nie restartuje** `ventilation-core`, WebGUI, host-power ani HMI;
- przy błędzie próbuje przywrócić poprzednie pliki i unit.

Dotychczasowa godzina zamknięcia 18:30 i RTC 08:00 nie zmieniają się.
Bramka działa co minutę, nowa usługa włącza się wyłącznie na kolejnym
boocie i tylko gdy istnieje ticket.

## Kontrola

Po instalacji (bez zmiany wyjść):

```bash
systemctl is-enabled wvc-rtc-auto-resume.service
systemctl is-active wvc-auto-poweroff.timer ventilation-core.service wvc-web-ui.service
python3 /usr/local/libexec/wvc-autostart-gate.py plan
python3 /usr/local/libexec/wvc-rtc-auto-resume.py inspect
```

Przed pierwszym rzeczywistym zamknięciem:

```bash
curl -fsS http://127.0.0.1:18091/api/v1/state
```

Prawidłowa sesja przed 18:30 powinna zawierać
`active_auto.active=true`, brak `fault_latched`.
Jeśli użytkownik wcześniej ustawi MANUAL, nie należy spodziewać się
automatycznego przejścia na AUTO następnego dnia.

Po planowym shutdown (w ramach logu sprzed odłączenia):

```bash
journalctl -u wvc-auto-poweroff.service -n 40 --no-pager
```

Szukamy `WVC_RTC_AUTO_RESUME_TICKET_ARMED_NEXT_BOOT` oraz
`WVC_AUTOSTART_SHUTDOWN_ACCEPTED_BY_EXISTING_HOST_POWER`.

Po jutrzejszym wybudzeniu:

```bash
journalctl -b -u wvc-rtc-auto-resume.service --no-pager
```

Oczekiwane: `WVC_RTC_AUTO_RESUME_RESULT resumed_auto` oraz
`active_auto.mode=AUTO` w `GET /api/v1/state`.
Bez pełnego fizycznego cyklu shutdown/RTC-boot wynik należy oznaczyć
jako zweryfikowany w testach logicznych, lecz nie jeszcze sprzętowo.

## Wycofanie

```bash
sudo systemctl disable wvc-rtc-auto-resume.service
```

Następnie przywrócić `wvc-autostart-gate.py` z katalogu backup i
wykonać `sudo systemctl daemon-reload`. Nie trzeba dotykać
`ventilation-core` ani zmieniać harmonogramu. Usunąć nieaktualny ticket
wyłącznie świadomie przez procedurę serwisową.

## Testy

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_wvc_rtc_auto_resume.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_autostart_power_gate.py' -v
bash -n tools/install_wvc_rtc_auto_resume.sh
python3 -m py_compile deploy/cm5/wvc-rtc-auto-resume.py
```
