# WebGUI Automation Stage1 — walidacja fizyczna CM5

Data: 2026-08-28

## Wynik

**PASS**

WebGUI Automation Stage1 został zwalidowany na rzeczywistym CM5 przy użyciu izolowanego harnessu, bez dostępu testowanego WebGUI do produkcyjnego socketu `ventilation-core` i bez wywoływania fizycznej ścieżki sterowania.

## Walidowany kod

- gałąź: `agent/web-gui-automation-stage1`
- exact CI-tested candidate SHA: `f5992fa39fcea325fada9f0128adb382170b727e`
- produkcyjny `main`: `7628c407cfc9c0ea72d262566759ea2d4598fec8`
- wcześniejszy GitHub Actions run dla kandydata: `33188087787` — SUCCESS

## Środowisko walidacji

- produkcyjny katalog: `/home/wentylacja/workshop-ventilation-controller`
- produkcyjny `ventilation-core` PID przed testem: `1216`
- produkcyjny `ventilation-core` CWD: `/home/wentylacja/workshop-ventilation-controller`
- `wvc-host-power.service`: `active`, PID `712`
- RTC wakealarm przed testem: pusty (`<empty>`)
- izolowany WebGUI testowy: `http://127.0.0.1:18093`
- PID izolowanego WebGUI podczas testu: `2768`

## Zakres sprawdzenia

Harness potwierdził:

1. Produkcyjny `ventilation-core` przed testem działał z katalogu `main`.
2. Remote pin `main` był równy dokładnie `7628c407cfc9c0ea72d262566759ea2d4598fec8`.
3. Remote pin gałęzi GUI był równy dokładnie `f5992fa39fcea325fada9f0128adb382170b727e`.
4. Walidacyjny fake-core został uruchomiony na osobnym Unix socket i staged WebGUI nie używało produkcyjnego socketu core.
5. `/automation` poprawnie serwował cztery zakładki SHADOW oraz współdzielony klient Calendar Engine.
6. Początkowy stan WebGUI był AUTO SHADOW przy fizycznym fixture 0 V.
7. Istniejący endpoint Calendar Engine był osiągalny przez staged WebGUI.
8. Ledger tuning był read-only, `default_runtime_binding=false` i raportował dokładnie `1/9` ukończonych grup.
9. MANUAL operator intent zmieniał wyłącznie stan SHADOW; fixture pozostawał przy 0 V.
10. Powrót do AUTO był widoczny przez WebGUI i pozostawał non-actuating.
11. Log fake-core zawierał wyłącznie dozwolone komendy status/calendar/operator SHADOW.
12. Payload AUTO był kanoniczny: `{"mode":"AUTO"}` — bez pozostałości pól MANUAL ustawionych na `null`.
13. Po zakończeniu testu produkcyjny `ventilation-core` zachował ten sam PID i CWD.
14. `wvc-host-power.service` zachował ten sam status i PID.
15. RTC wakealarm pozostał niezmieniony.
16. Boot ID pozostał niezmieniony.
17. Produkcyjny `main` pozostał czysty i nadal wskazywał `7628c407cfc9c0ea72d262566759ea2d4598fec8`.

## Kluczowy rezultat bezpieczeństwa

Walidacja potwierdziła rozdzielenie GUI automatyki od fizycznej ścieżki wykonawczej:

- staged WebGUI nie otrzymał produkcyjnego socketu `ventilation-core`,
- użyty został wyłącznie walidacyjny fake-core,
- nie wykonano restartu produkcyjnego `ventilation-core`,
- nie wykonano komend fizycznych `set`, `stop`, `aero-speed`, `aero-airing`,
- nie wykonano shutdown/reboot,
- MANUAL w `/automation` pozostaje wyłącznie operator intent warstwy SHADOW,
- Control Engine pozostaje bez authority do aktuacji.

## Dowód końcowy z CM5

```text
===== RESULT =====
PASS: WebGUI Automation Stage1 validated on CM5 without access to the production core socket or physical control path
branch SHA:      f5992fa39fcea325fada9f0128adb382170b727e
production SHA:  7628c407cfc9c0ea72d262566759ea2d4598fec8
production PID:  1216 (unchanged)
WebGUI test port: 18093
```

## Status po walidacji

- WebGUI Automation Stage1: **PHYSICAL CM5 PASS**
- PR #87: pozostaje **Draft**
- merge do `main`: **NIE WYKONANO**
- Ready for Review: **NIE WYKONANO**
- `main`: **bez zmian**

Następny krok integracyjny może obejmować uruchomienie WebGUI Automatyki przeciwko rzeczywistemu Control Engine na CM5, nadal z zachowaniem SHADOW/non-actuating boundary. Wymaga to osobnego, kontrolowanego etapu walidacji i nie jest częścią niniejszego testu.
