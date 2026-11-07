# WVC AUTO V1 — wykonawcza automatyka warsztatowa

Status 2026-11-07: kod wykonawczy i testy, lecz NIE WŁĄCZONY W PRODUKCJI.
Przygotowanie na osobnej gałęzi; bez merge do main i bez zmian systemd.

## Architektura

AUTO jest aktywną pętlą wykonawczą WEWNĄTRZ ventilation-core, a nie zewnętrznym
agentem monitorującym. Steruje rzeczywistym DAC (EC) i kontrolerem AERO przez
dotychczasowe zweryfikowane interfejsy core. Stan aktywnego regulatora
jest dołączany do normalnego CoreState i zapisywany w istniejącej telemetrii.

Pomieszczenie 1: 36 m3, EC nawiew/wyciąg 0–10 V, kanały Ø160 mm, SEN55 #1.
Pomieszczenie 2: 36 m3, Prodmax/COMPIT AERO, kanały Ø120 mm, SEN55 #2.
TACHO EC: GPIO17/GPIO27, trzy impulsy na obrót.

## Robocze presety wykonawcze

Edycja: config/active-auto-v1.json. Napięcia i prędkości to propozycje
komisjonowania z pomiarów punktowych, NIE legalne wartości NDS ani
zweryfikowany bilans przepływów.

| Tryb | EC nawiew | EC wyciąg | AERO |
|---|---:|---:|---|
| ECO | 2 V | 1 V | bieg 1 |
| NORMAL | 4 V | 3 V | bieg 1 |
| BOOST | 7 V | 5 V | bieg 2 |
| HIGH | 9 V | 6 V | bieg 3 |
| MAX | 10 V | 7 V | bieg 3 + wietrzenie |
| SENSOR_FAULT | 4 V | 3 V | bieg 2 |

W obu pomieszczeniach niezależne poziomy:
- BOOST: PM2.5 >15 ug/m3 albo VOC >=150 albo NOx >10.
- HIGH: PM2.5 >25 ug/m3 albo VOC >=200 albo NOx >50.
- MAX: PM2.5 >50 ug/m3 albo VOC >300 albo NOx >100.
- Zwiększenie BOOST po 15 s, HIGH/MAX po 5 s; przy pierwszym starcie
  nastawa może odzwierciedlać bieżącą jakość powietrza natychmiast.
- Opadanie poziomu: 180 s. TEMP<18 C ogranicza WYŁĄCZNIE zwykłe
  żądanie przy dobrym powietrzu — do ECO; nie dławi BOOST/HIGH/MAX.
- Nawet przy kalendarzu INACTIVE utrzymywane jest ECO, a przy pogorszeniu
  powietrza regulator reaguje niezależnie od harmonogramu.
- Brak SEN55 oznacza SENSOR_FAULT, a nie dobre powietrze.
- PM10 rejestrowany do historii; jego wartość WHO 45 ug/m3 na dobę
  nie staje się automatycznie progiem chwilowym.

## Wykonanie i sterowanie

- Manualny STOP/SET albo ręczna zmiana AERO blokują kolejne rozkazy AUTO
  do jawnego RESUME. HOLD przetrwa restart CM5.
- STOP zatrzymuje oba EC, ale NIE jest tym samym co STOP AERO.
- Niezależny watchdog TACHO co około 2 s w osobnym zadaniu rdzenia, również gdy AERO
  czeka na fizyczne potwierdzenie. Kontrola po rozruchu; błąd -> HOLD,
  alarm w stanie AUTO i dzienniku, zachowanie ostatniego wyjścia.
- AERO: wyłącznie polecenia istniejącą ścieżką control_aero;
  po pierwszym potwierdzeniu fizycznej zmiany AUTO dodatkowo wymaga
  osiągnięcia docelowej mocy przez OBA wentylatory (maks. 25 s).
  Nieudane potwierdzenie prowadzi do trwałego HOLD.
- Monitorowaniu podlega mode AUTO i actual setpoints; każda decyzja
  jest dostępna z CoreState.active_auto i istniejącą historią, bez
  tworzenia oddzielnej usługi obserwacyjnej.
- CLI po wdrożeniu: python3 -m ventilation_core.ctl auto-status,
  auto-hold, auto-resume. WebAPI udostępnia tylko GET /api/v1/auto.
  Krytyczne HOLD/RESUME nie jest wystawiane jako nieautoryzowany HTTP
  endpoint; jest dostępne tylko przez lokalny socket core (CLI).

## Twarda bramka pierwszej aktywacji

Sama flaga --enable-active-auto nie uruchomi fizycznych wyjść.
Konieczne są: validny profil config/active-auto-v1.json oraz plik
/var/lib/workshop-ventilation/active-auto-approval.json z jawnie
zatwierdzonymi dowodami. Bez nich core pozostaje w ręcznym trybie
i udostępnia powód zablokowania AUTO; jego praca nie jest przerywana.

Szablon formularza: config/active-auto-commissioning.example.json.
Akceptacja PENDING jest celowo niezdatna do uruchomienia.

Przed wpisaniem APPROVED trzeba:
1. Udokumentować ocenę ryzyka procesowego i wymagania NDS/odciągów.
2. Potwierdzić miejscowe odciągi oparów lutowniczych.
3. Wyznaczyć wiarygodną średnią strugę z kilku punktów przekroju/
   kaptura i bilans nawiew–wyciąg przy czystym oraz zabrudzonym filtrze.
4. Fizycznie sprawdzić AERO: bieg 1,2,3, MAX i powrót do stanu.
5. Zwalidować procedury przy TACHO: SUPPLY, EXTRACT, BOTH.
6. Sprawdzić fallback przy SEN55 nr 1, nr 2 i obu niedostępnych.
7. Zabezpieczyć CO niezależną aparaturą, jeżeli możliwe są spaliny.
8. Sprawdzić ręczny STOP i HOLD, restart, brak sieci i zanik zasilania.

Nie wolno stosować SEN55 jako detektora CO ani czujnika stężeń
określonych substancji toksycznych. Pomiar punktowy m/s nie jest
dowodem poziomu m3/h ani spełnienia wymagań BHP.
Nie istnieje uniwersalne ACH zapewniające bezpieczeństwo dla każdej
operacji warsztatowej.

## Źródła

- Ogólne przepisy BHP, § 32: wymagania funkcji pomieszczenia,
  zanieczyszczeń oraz NDS: https://lexeva.pl/akt/du/1997/844/przepis/par-32
- Rozporządzenie warunków technicznych, §148: zależnie od zastosowania
  odciągi miejscowe i wentylacja awaryjna:
  https://isap.sejm.gov.pl/isap.nsf/download.xsp/WDU20220001225/O/D20221225.pdf
- WHO Air Quality Guidelines (2021):
  https://www.who.int/Publications/i/Item/9789240034228
- Sensirion SEN5x Engineering Guidelines:
  https://admin.sensirion.com/media/documents/25AB572C/62B463AA/Sensirion_Engineering_Guidelines_SEN5x.pdf
- HSE HSG258 — LEV:
  https://www.hse.gov.uk/pubns/books/hsg258.htm

## Kryteria zakończenia

Przed aktywacją konieczne: testy jednostkowe, kontrakty WebAPI/CLI,
aktualne pomiary i osobno dokumentowana walidacja w warsztacie.
Żadnego automatycznego merge do main.
