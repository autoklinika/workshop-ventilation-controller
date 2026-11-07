# WVC AUTO V1 — przełączanie fizyczne AUTO / MANUAL i reakcja na awarie

Data: 2026-11-07. Gałąź: agent/wvc-auto-v1-manual-switch-20261107.

## Obsługa z HMI i WebGUI

Na stronie `/automation` znajduje się osobny panel **Sterowanie rzeczywiste · EC + AERO**. Nie należy mylić go z wcześniejszymi przyciskami **AUTO (SHADOW)** i **MANUAL (SHADOW)**, które są tylko symulacją logiki i nie wykonują poleceń na wyjściach.

**MANUAL**:
- Dostępne zawsze bez PIN; przez wąskie `POST /api/v1/physical-mode` z jedynym polem `{"mode":"MANUAL"}`.
- Core zapisuje trwałe `OPERATOR_SELECTED_MANUAL` i natychmiast zatrzymuje wydawanie kolejnych poleceń przez AUTO.
- Ostatnie wyjścia pozostają bez zmian, operator steruje przez ekran STREFY. Ręczny STOP wentylatorów EC pozostaje niezależnym przyciskiem; MANUAL **nie** jest równoznaczny ze STOP.
- Ręczne SET, STOP, AERO speed/airing również zatrzaskują MANUAL. Stan trwa przez restart CM5.

**AUTO**:
- Wymaga, aby aktywne AUTO było faktycznie dozwolone przez runtime (`--enable-active-auto` i profil zatwierdzonego commissioning).
- W HMI wymagane są PIN operatora, jawne zaznaczenie potwierdzenia oraz kontrola origin. PIN nie jest przesyłany do core ani zapisany w logach, a jego hash weryfikuje WebUI; pięć niepoprawnych prób powoduje blokadę na pięć minut.
- WebGUI nie wysyła napięć bezpośrednio: jedynie `auto-resume` do core po autoryzacji; core ocenia sprzęt, komunikację AERO, oba SEN55, TACHO, aktywne alarmy i latched fault.
- Po restarcie system startuje z trwale zapisanym MANUAL (nawet gdy AUTO jest dozwolone). Nie występuje samoczynny start EC od samego bootu.

Konfiguracja PIN na lokalnym CM5:

```bash
cd /home/wentylacja/wvc-webgui-automation-stage3-runtime
PYTHONPATH=src python3 tools/configure_auto_mode_pin.py
```

PIN: 6–12 cyfr, wpisywane interaktywnie; plik `/var/lib/workshop-ventilation/auto-mode-pin.json`, prawa 0600, sól i scrypt. Nie ma domyślnego PIN. Nie wolno umieszczać go w repozytorium lub w parametrze linii poleceń.

**Sieć:** WebGUI obecnie działa po HTTP na porcie 18091. PIN nie powinien być używany z niezaufanej sieci; przed regularnym używaniem AUTO z HMI wymagane jest zabezpieczenie ruchu (HTTPS lub równoważny zaufany kanał sieciowy). Origin-check chroni przed prostym CSRF, nie szyfruje transportu.

## Awaryjne zatrzymanie wentylatorów EC

Po potwierdzonej utracie sygnału TACHO z nawiewu, wyciągu lub obu jednocześnie:
1. Sprawdza się obecność sygnału po 12 s na rozpędzenie od ostatniej zmiany napięcia, a następnie **ciągłą utratę przez 4 s**.
2. AUTO trwale zapisuje powód, maskę (SUPPLY/EXTRACT/BOTH) oraz `fault_latched=true`.
3. Core wydaje polecenie **STOP obu wentylatorów EC (0 V / 0 V)**. Jeżeli nie da się potwierdzić 0 V, zapisuje krytyczny błąd wykonania.
4. Zatrzymuje dalsze próby aktuacji AUTO do lokalnego skasowania awarii przez serwis.
5. Nie zmienia stanu rekuperatora AERO (osobna strefa).

Ręczna kontrola i diagnostyka:

```bash
cd /home/wentylacja/wvc-webgui-automation-stage3-runtime
PYTHONPATH=src python3 -m ventilation_core.ctl auto-status
PYTHONPATH=src python3 -m ventilation_core.ctl auto-manual
PYTHONPATH=src python3 -m ventilation_core.ctl auto-ack-fault
PYTHONPATH=src python3 -m ventilation_core.ctl auto-resume
```

`auto-ack-fault` wymaga EC STOP/0 V, gotowego DAC/TACHO, braku alarmu krytycznego. Nie wznawia AUTO — pozostawia MANUAL. Dopiero osobne `auto-resume` ma prawo wznowić sterowanie po sprawdzeniu preflight.

**Ważne ograniczenie bezpieczeństwa:** STOP obu wentylatorów zapobiega dalszej niekontrolowanej nierównowadze, ale przy emisji szkodliwych substancji może oznaczać utratę wentylacji. Operator musi przerwać emisję, użyć niezależnych odciągów i procedur BHP, a w razie zagrożenia opuścić pomieszczenie. Sama reakcja 0 V nie zastępuje oceny ryzyka i nie jest certyfikowanym systemem bezpieczeństwa.

## Testy i wdrożenie

- Testy syntetyczne: TACHO SUPPLY, EXTRACT, BOTH; potwierdzanie usterki 4 s, STOP obu EC, trwały zapis błędu i odmowa AUTO bez serwisowego potwierdzenia.
- Weryfikacja WebGUI: MANUAL zawsze bez PIN, AUTO wymaga PIN i potwierdzenia; tylko dokładnie określone komendy trafiają do core. Nie ma ogólnego proxy komend ani autoryzacji automatu przez SHADOW.
- Testy uruchomienia: po bootie MANUAL i brak samoczynnych poleceń.
- Wcześniejsze testy fizyczne AERO 1/2/3/MAX i pomiary RPM EC pozostają ważne. Nie wykonano kontrolowanego fizycznego zatrzymania wentylatora w warunkach produkcji.

Bramka commissioning pozostaje wymagana. Nie generujemy fikcyjnego `APPROVED`; obowiązujące braki z protokołu `docs/commissioning/WVC_AUTO_V1_WORKSHOP_AUDIT_2026-11-07_PL.md` trzeba zamknąć podczas montażu i prób w miejscu pracy. Bez niej aktywne AUTO jest wyłączone, lecz MANUAL i pozostałe funkcje systemu działają normalnie.

Zmiana powinna być wdrożona do bieżącego runtime CM5 z kopią poprzedniej wersji i bazy konfiguracji, restartem Core/WebGUI, niezależnym sprawdzeniem 0 V/0%, stanu obu SEN55 i możliwość rollbacku. Bez automatycznego merge do main.
