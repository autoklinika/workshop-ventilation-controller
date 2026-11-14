> **Wersja historyczna (14.11.2026 rano).** Ten dokument opisuje poprzedni
> projekt sprawdzania kalendarza co minutę. Projekt został zastąpiony
> rozwiązaniem wyzwalanym zdarzeniowo; aktualna dokumentacja operacyjna:
> [WVC_EVENT_DRIVEN_SCHEDULE_PL.md](WVC_EVENT_DRIVEN_SCHEDULE_PL.md).
> Jednostki `wvc-schedule-keeper.timer` i `wvc-schedule-keeper.service`
> zostały wycofane. Nie instalować starego skryptu `install_wvc_schedule_keeper.sh`.

# WVC — uniwersalna ciągłość harmonogramu po ręcznej pracy (14.11.2026)

## Problem potwierdzony na CM5

W sobotę 14.11.2026 użytkownik uruchomił CM5 ręcznie przy sobocie OFF
(rewizja 4). RTC nadal wskazywał poniedziałek 16.11 o 08:00, ale
dotychczasowa jednorazowa usługa AUTO odrzuciła piątkowy ticket
(rejected_boot_window). Po wybudzeniu w aktywnym dniu fizyczny CM5
mógł wystartować w stanie MANUAL/HOLD.

## Zasada uniwersalna

Harmonogram jest niezależny od ręcznych sesji operatora.
Nie kodujemy stałych dni tygodnia; obowiązuje roczny kalendarz Core,
jego wyjątki, święta, godziny i zmiany roku.

- Co minutę root-owned wvc-schedule-keeper.timer pobiera bieżący kalendarz
  przez lokalny Unix socket Core, wyznacza następny dzień aktywny
  i porównuje alarm RTC. RTC zapisuje tylko przy zmianie terminu.
- Ręczny shutdown przez host-power, po następnym uruchomieniu jego
  uaktualnionego kodu, dodatkowo uruchamia jednostkę armowania RTC.
  Nie blokuje awaryjnego wyłączenia, gdy RTC jest niedostępny.
- Jeśli CM5 pozostaje włączony w chwili startu zaplanowanego dnia,
  przez maksimum 20 minut może jednorazowo wznowić AUTO bez rebootu.
- Zwykły MANUAL/STOP sprzed nowego planowanego startu przestaje
  blokować ten start. MANUAL/STOP wybrany po godzinie startu nie
  zostaje automatycznie nadpisany.
- EXPLICIT_OPERATOR_HOLD, zatrzaśnięte błędy, alarmy krytyczne,
  nieważne pomiary SEN55, niegotowe TACHO/DAC/AERO i uszkodzony
  plik HOLD zawsze uniemożliwiają automatyczne wznowienie.
- Znacznik root-owned scheduled-start-claim.json powstaje przed
  komendą AUTO, co zapobiega ponownemu AUTO po ręcznym STOP w tym samym
  oknie startowym.
- Istniejąca jednorazowa usługa RTC AUTO pozostaje bez zmian. Nadzorca
  czeka z wznowieniem, jeśli istnieje jej oczekujący ticket.

## Scenariusze

| Sytuacja | Oczekiwany wynik |
| --- | --- |
| Ręczny start CM5 w nieaktywnym dniu | AUTO nie startuje samoczynnie, RTC wskazuje kolejny aktywny dzień |
| Ręczne AUTO i MANUAL/STOP w dniu wolnym | Następny aktywny start może uruchomić AUTO, po preflight |
| Ręczne wyłączenie całego CM5 | Kolejny alarm RTC jest podtrzymywany i odświeżany |
| CM5 pozostawiony uruchomiony przez noc | AUTO startuje o najbliższej dozwolonej godzinie |
| Ręczny STOP już po starcie planowym | Nie jest cofany przez minutowy timer |
| Niedziela, święto, wyłączony wyjątek | Nie powoduje planowanego AUTO |
| Brak gotowości sprzętu lub fault | AUTO pozostaje zablokowane |

## Instalacja

Po scaleniach kodu i synchronizacji main na CM5:

    sudo bash /home/wentylacja/workshop-ventilation-controller/tools/install_wvc_schedule_keeper.sh

Instalator tworzy backup, instaluje nowe jednostki systemd i timer,
oraz uzgadnia RTC z kalendarzem. Nie restartuje ventilation-core,
host-power, WebGUI ani całego CM5. Kod host_power_agent.py zacznie
wywoływać dodatkowe armowanie przed ręcznym shutdown dopiero po
kolejnym planowym starcie tej usługi.

Kontrola tylko do odczytu:

    python3 /usr/local/libexec/wvc-schedule-keeper.py plan
    systemctl list-timers wvc-schedule-keeper.timer
    date -d @"$(cat /sys/class/rtc/rtc0/wakealarm)" -Is
    journalctl -u wvc-schedule-keeper.service -n 30 --no-pager

Po uruchomieniu w dozwolonym dniu należy potwierdzić logi
WVC_KEEPER_AUTO resumed_auto oraz rzeczywisty tryb AUTO w Core.

## Ograniczenia

Nie da się zagwarantować wybudzenia po zaniku zasilania, awarii RTC
lub po nieudanym programowaniu alarmu. Podtrzymywanie RTC jest
wykonywane co minutę, więc ręczny shutdown niemal natychmiast
po starcie CM5, przed pierwszą kontrolą, może nie odświeżyć alarmu.
Od następnego restartu host-power dodatkowe armowanie następuje
bezpośrednio przed ręcznym shutdown. Pierwszy fizyczny cykl
RTC i AUTO należy zweryfikować w produkcji.

## Wycofanie

    sudo systemctl disable --now wvc-schedule-keeper.timer

Pliki systemd i skrypt można odtworzyć z kopii
/var/backups/wvc-schedule-keeper-*. Wycofanie nie wymaga
restartowania wentylacji.
