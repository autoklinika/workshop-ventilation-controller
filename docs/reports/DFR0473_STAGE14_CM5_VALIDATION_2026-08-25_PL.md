# DFR0473 Stage14 – walidacja na fizycznym CM5 — 2026-08-25

## Zakres

Walidacja nieinwazyjna domeny zasilania 12 V sterowanej przez DFRobot DFR0473 na fizycznym Raspberry Pi Compute Module 5.

Gałąź:

```text
agent/power-domain-dfr0473-stage14
```

Zweryfikowany HEAD podczas pierwszego harnessu:

```text
e5e1f95f79542cf8b9c1f0beff0e656899e46087
```

Użyty harness:

```text
tools/install_validate_dfr0473_power_domain_cm5.sh
```

Pierwszy harness nie wykonywał `poweroff` ani `reboot` hosta. Następnie wykonano osobny kontrolowany pełny cykl POWER OFF / POWER ON przy nadal fizycznie odłączonym BOX-ie oraz test krótkiego `PWR_BUT` podczas RUNNING.

## Stan wejściowy

Przed testem obie usługi były aktywne:

```text
ventilation-core.service: active
wvc-host-power.service:   active
```

Polecenie lokalnego STOP nie mogło zostać potwierdzone, ponieważ DFR0971 / GP8403 był w czasie testu **fizycznie odłączony od CM5**. Odpowiedź I²C:

```text
No response from GP8403 at 0x58: [Errno 121] Remote I/O error
```

Nie jest to dowód uszkodzenia DAC. Jest to oczekiwany stan software przy fizycznie odłączonym urządzeniu.

Stan core:

```text
mode: FAULT
supply_voltage: 0.0
extract_voltage: 0.0
hardware_ready: false
output_state_known: false
```

Aktywny był alert:

```text
DAC_COMMUNICATION_LOST
severity: critical
```

W tym samym czasie fizycznie niedostępne były również pozostałe odłączone peryferia, dlatego oba SEN55 oraz AERO były raportowane jako offline. Te stany nie są w tym teście interpretowane jako awarie sprzętu.

## Zdegradowany warunek wejściowy

Harness rozpoznał wąski, jawnie dozwolony stan zdegradowany:

```text
requested EC setpoints: 0 V / 0 V
DAC_COMMUNICATION_LOST: present
physical EC output confirmation: UNAVAILABLE
DEGRADED ZERO-REQUEST PRECONDITION: ACCEPTED FOR POWER-DOMAIN TEST
```

Ten wynik NIE oznacza, że fizyczne wyjścia 0–10 V DFR0971 zostały potwierdzone jako 0 V. W czasie testu DFR0971 był fizycznie odłączony, więc pomiar VOUT0/VOUT1 nie był możliwy ani potrzebny do samej walidacji sekwencji DFR0473.

## Instalacja i zależności systemd

Harness utworzył backup aktualnie zainstalowanych plików w:

```text
/var/tmp/wvc-dfr0473-stage14-backup-20260825-111326
```

Zainstalowano konfigurację Stage14 oraz sprawdzono graf zależności systemd.

Wynik:

```text
systemd dependency/config: PASS
```

## Test DFR0473 OFF

`wvc-host-power.service` został zatrzymany. Zależność `Requires/After` spowodowała także zatrzymanie `ventilation-core.service`.

Stan usług po zatrzymaniu:

```text
wvc-host-power: inactive
ventilation-core: inactive
```

Operator fizycznie potwierdził:

```text
DFR0473 OFF
relay released / LED OFF
```

## Test DFR0473 ON

Następnie uruchomiono `ventilation-core.service`.

Systemd najpierw uruchomił `wvc-host-power`, który przejął GPIO22, załączył domenę 12 V i odczekał czas stabilizacji, a następnie pozwolił wystartować core.

Log potwierdził:

```text
12 V power domain commanded ON via DFR0473 line=GPIO22
```

Operator fizycznie potwierdził:

```text
DFR0473 ON
relay energized / LED ON
```

Obie usługi wróciły do `active`.

## Stan po ponownym starcie core

Ponieważ DFR0971 / GP8403 nadal był fizycznie odłączony, core zgodnie z projektem wrócił do:

```text
mode: FAULT
supply_voltage: 0.0
extract_voltage: 0.0
output_state_known: false
```

Harness ponownie zaakceptował wyłącznie jawny stan zdegradowany z `DAC_COMMUNICATION_LOST` i żądanymi setpointami `0.0 / 0.0`.

## Wynik harnessu

```text
STAGE14 NON-DESTRUCTIVE POWER-DOMAIN VALIDATION: PASS (DAC FAULT DEGRADED)
```

Potwierdzono:

- GPIO22 steruje DFR0473 zgodnie z oczekiwaniem,
- DFR0473 fizycznie przechodzi OFF po zatrzymaniu warstwy host-power,
- DFR0473 fizycznie przechodzi ON przy starcie warstwy host-power,
- zależności systemd wymuszają właściwą kolejność `wvc-host-power -> ventilation-core`,
- fizycznie odłączony DAC i inne peryferia nie blokują walidacji domeny 12 V,
- harness nie wykonał restartu ani wyłączenia CM5.

## Pełny cykl POWER OFF / POWER ON

Po zakończeniu harnessu wykonano pierwszy kontrolowany pełny POWER OFF z aplikacji przy nadal całkowicie odłączonym BOX-ie.

Operator fizycznie potwierdził kluczową kolejność wyłączania:

```text
DFR0473 OFF / przekaźnik puścił
-> dopiero później CM5 zgasł
```

To potwierdza na sprzęcie, że domena 12 V jest odłączana przed pełnym wyłączeniem CM5.

Po ponownym uruchomieniu CM5 bieżący boot pokazał:

```text
wvc-host-power.service: active
ventilation-core.service: active

11:26:41 Starting wvc-host-power.service
11:26:41 12 V power domain commanded ON via DFR0473 line=GPIO22
11:26:42 Started wvc-host-power.service
11:26:42 host-power agent listening
```

Czyli podczas POWER ON warstwa host-power przejmuje GPIO22, załącza DFR0473 i kończy własną inicjalizację przed normalną pracą core.

## Dlaczego brak logów poprzedniego bootu jest oczekiwany

Polecenia:

```text
journalctl -b -1 ...
```

zwróciły:

```text
Specifying boot ID or boot offset has no effect, no persistent journal was found.
```

To jest zgodne z konfiguracją ochrony eMMC projektu:

```ini
[Journal]
Storage=volatile
```

Systemowy journal jest celowo runtime-only, więc po pełnym power cycle poprzedni boot nie jest dostępny. Weryfikacja kolejności POWER OFF opiera się w tym teście na bezpośredniej fizycznej obserwacji operatora.

## Test krótkiego PWR_BUT podczas RUNNING

Po ponownym uruchomieniu CM5 zweryfikowano aktywną konfigurację logind:

```text
#HandlePowerKey=poweroff
#HandlePowerKeyLongPress=ignore
HandlePowerKey=ignore
HandlePowerKeyLongPress=ignore
```

Stan przed krótkim naciśnięciem fizycznego przycisku POWER:

```text
11:31:02 up 4 min
wvc-host-power.service: active
ventilation-core.service: active
```

Po krótkim naciśnięciu `PWR_BUT`:

```text
11:31:13 up 4 min
wvc-host-power.service: active
ventilation-core.service: active
```

Uptime nie został przerwany, sesja pozostała aktywna, a obie kluczowe usługi pozostały `active`.

Wynik:

```text
SHORT PWR_BUT WHILE RUNNING: PASS
```

Potwierdzono, że normalne krótkie naciśnięcie fizycznego `PWR_BUT` przy działającym Linuxie jest ignorowane i nie tworzy alternatywnej ścieżki shutdown poza `wvc-host-power`.

> Uwaga: software nie może wyłączyć sprzętowego emergency hard-off wynikającego z bardzo długiego przytrzymania PWR_BUT/PMIC. Długiego przytrzymania nie traktujemy jako normalnej procedury i nie testujemy go jako funkcji użytkowej.

## Aktualny wynik etapu

Dla testu z odłączonym BOX-em:

```text
DFR0473 standalone GPIO22 LOW/HIGH: PASS
systemd OFF/ON sequencing:          PASS
GUI POWER OFF -> DFR0473 OFF:      PASS (fizycznie)
DFR0473 OFF przed CM5 OFF:         PASS (fizycznie)
boot -> DFR0473 ON:                PASS
wvc-host-power po boot:            active
ventilation-core po boot:          active
short PWR_BUT while RUNNING:       PASS
```

Walidację samego toru POWER przy odłączonym BOX-ie można uznać za zakończoną sukcesem.

Nie potwierdzono jeszcze:

- zachowania DFR0971 / VOUT0 / VOUT1 przy pełnym, podłączonym stanowisku,
- zachowania VOUT0/VOUT1 podczas prawdziwego `poweroff` CM5,
- pełnego shutdown z podłączonymi AERO/SEN55/BOX,
- finalnego zachowania po utracie i powrocie głównego zasilania.

## Następne kroki

1. Po ponownym podłączeniu BOX/DFR0971 i peryferiów potwierdzić prawidłową komunikację.
2. Wykonać osobną walidację toru 0–10 V podczas kontrolowanego shutdown przy podłączonym DAC.
3. Powtórzyć pełny shutdown z podłączonymi peryferiami i potwierdzić, że ich brak komunikacji nie blokuje wyłączenia.
4. Osobno zwalidować zachowanie po utracie i powrocie głównego zasilania zgodnie z docelową konfiguracją `POWER_OFF_ON_HALT` / `WAIT_FOR_POWER_BUTTON`.
